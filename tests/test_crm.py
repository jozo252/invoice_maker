"""Local CRM regressions using disposable data, never invoices.db or .env."""
import hashlib
import importlib.util
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask, g
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from PIL import Image
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from extensions import db
from models import Client, Company, Job, JobNote, JobPlan, JobReceipt, User
from crm.routes import crm_bp
from crm.receipts import MAX_FILE_BYTES, ValidationError, format_money, parse_cents, parse_date


ROOT = Path(__file__).resolve().parents[1]


class Inputs(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.values = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "input" and "name" in values:
            self.values[values["name"]] = values.get("value", "")


def photo(color="white"):
    output = BytesIO()
    Image.new("RGB", (30, 20), color).save(output, format="PNG")
    return output.getvalue()


class CrmTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="invoicemaker-crm-test-")
        self.folder = Path(self.temporary.name)
        self.app = Flask(
            __name__,
            template_folder=str(ROOT / "templates"),
            static_folder=str(ROOT / "static"),
            instance_path=str(self.folder / "instance"),
        )
        self.app.config.update(
            TESTING=True,
            SECRET_KEY="isolated-crm-regression-test",
            SQLALCHEMY_DATABASE_URI="sqlite:///" + (self.folder / "test.sqlite3").as_posix(),
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            CRM_RECEIPT_FOLDER=str(self.folder / "private_receipts"),
            CRM_LOCAL_ONLY=True,
            MAX_CONTENT_LENGTH=9 * 1024 * 1024,
            WTF_CSRF_ENABLED=True,
        )
        db.init_app(self.app)
        CSRFProtect(self.app)
        manager = LoginManager(self.app)

        @manager.user_loader
        def load_user(user_id):
            return db.session.get(User, int(user_id))

        @manager.unauthorized_handler
        def unauthorized():
            return "Login required", 401

        @self.app.before_request
        def fresh_request_user():
            # The fixture keeps an outer app context for database assertions.
            # Real HTTP requests get a fresh g; emulate that for Flask-Login.
            g.pop("_login_user", None)

        self.app.register_blueprint(crm_bp)
        self.context = self.app.app_context()
        self.context.push()
        with db.engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        db.create_all()
        first = User(email="first@example.invalid", username="first", password_hash="test-unused")
        second = User(email="second@example.invalid", username="second", password_hash="test-unused")
        db.session.add_all([first, second])
        db.session.flush()
        self.user_id, self.other_user_id = first.id, second.id
        own = Client(user_id=first.id, name="Vlastný zákazník", phone="0900123456")
        foreign = Client(user_id=second.id, name="Cudzí tajný zákazník", phone="0900999999")
        db.session.add_all([own, foreign])
        db.session.flush()
        self.client_id, self.other_client_id = own.id, foreign.id
        jobs = [
            Job(user_id=first.id, client_id=own.id, title="Elektro prvá", status="new"),
            Job(user_id=first.id, client_id=own.id, title="Elektro druhá", status="new"),
            Job(user_id=second.id, client_id=foreign.id, title="Cudzia tajná zákazka", status="new"),
        ]
        db.session.add_all(jobs)
        db.session.flush()
        self.job_id, self.second_job_id, self.other_job_id = [job.id for job in jobs]
        db.session.add(JobPlan(job_id=self.job_id, user_id=first.id, agreed_price_cents=200000))
        db.session.commit()
        self.browser = self.app.test_client()
        self.login(self.user_id)

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.context.pop()
        self.temporary.cleanup()

    def login(self, user_id):
        with self.browser.session_transaction() as session:
            session["_user_id"] = str(user_id)
            session["_fresh"] = True

    def csrf(self):
        page = self.browser.get("/crm/clients")
        self.assertEqual(page.status_code, 200)
        return Inputs(page.get_data(as_text=True)).values["csrf_token"]

    def post(self, path, data=None, **kwargs):
        values = dict(data or {})
        values.setdefault("csrf_token", self.csrf())
        return self.browser.post(path, data=values, **kwargs)

    def upload(self, job_id=None, content=None, filename="blocek.png"):
        return self.post(
            f"/crm/jobs/{job_id or self.job_id}/receipts/upload",
            {"file": (BytesIO(content if content is not None else photo()), filename)},
            content_type="multipart/form-data",
        )

    def new_receipt(self, color="white", job_id=None):
        response = self.upload(job_id, photo(color))
        self.assertEqual(response.status_code, 302)
        receipt_id = response.headers["Location"].rsplit("/", 1)[1]
        return db.session.get(JobReceipt, receipt_id)

    def confirmation(self, receipt, **changes):
        values = dict(
            confirmed="yes", job_id=str(self.job_id), vendor="Stavebniny Poprad",
            receipt_date="2026-09-16", amount="1 234,56", revision=str(receipt.revision),
            ocr_text="CELKOM 1 234,56 EUR",
        )
        values.update(changes)
        return values

    def test_reads_show_only_current_user_and_require_login(self):
        for path in ("/crm/", "/crm/clients", "/crm/progress"):
            with self.subTest(path=path):
                response = self.browser.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertNotIn("Cudz", response.get_data(as_text=True))
                self.assertEqual(response.headers["Cache-Control"], "private, no-store")
        with self.browser.session_transaction() as session:
            session.clear()
        self.assertEqual(self.browser.get("/crm/").status_code, 401)
        self.assertEqual(self.browser.get("/crm/health").status_code, 200)

    def test_other_owner_job_read_status_and_upload_are_blocked(self):
        self.assertEqual(self.browser.get(f"/crm/jobs/{self.other_job_id}").status_code, 404)
        self.assertEqual(self.post(f"/crm/jobs/{self.other_job_id}/status", {"status": "done"}).status_code, 404)
        self.assertEqual(self.upload(self.other_job_id).status_code, 404)
        self.assertEqual(db.session.get(Job, self.other_job_id).status, "new")
        self.assertEqual(JobReceipt.query.count(), 0)

    def test_other_owner_client_cannot_be_assigned_and_form_is_preserved(self):
        response = self.post("/crm/jobs/create", {
            "title": "Moja rozpracovaná zákazka", "description": "Ulica 12",
            "client_id": str(self.other_client_id), "price": "250,50", "due_date": "2026-10-03",
        })
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Vyberte vlastného zákazníka", html)
        self.assertNotIn("Cudzí tajný zákazník", html)
        self.assertEqual(Inputs(html).values["title"], "Moja rozpracovaná zákazka")
        self.assertEqual(Inputs(html).values["price"], "250,50")
        self.assertEqual(Job.query.count(), 3)

    def test_legacy_job_with_foreign_contact_never_reveals_contact(self):
        job = db.session.get(Job, self.job_id)
        job.client_id = self.other_client_id
        db.session.commit()
        dashboard = self.browser.get("/crm/")
        self.assertEqual(dashboard.status_code, 200)
        self.assertNotIn("Cudzí tajný zákazník", dashboard.get_data(as_text=True))
        self.assertNotIn("0900999999", dashboard.get_data(as_text=True))
        self.assertEqual(self.browser.get(f"/crm/jobs/{self.job_id}").status_code, 404)
        self.assertEqual(self.post(f"/crm/jobs/{self.job_id}/status", {"status": "done"}).status_code, 404)
        self.assertEqual(self.upload().status_code, 404)

    def test_legacy_job_with_foreign_company_is_blocked(self):
        foreign = Company(user_id=self.other_user_id, name="Cudzia firma", ico="12345678", dic="1234567890",
                          street="Test 1", city="Test", zip_code="00000", country="SK", email="company@example.invalid",
                          phone="0900999999", iban="SK000000", bic="TEST")
        db.session.add(foreign)
        db.session.flush()
        db.session.get(Job, self.job_id).company_id = foreign.id
        db.session.commit()
        self.assertEqual(self.browser.get(f"/crm/jobs/{self.job_id}").status_code, 404)
        self.assertEqual(self.upload().status_code, 404)

    def test_create_client_and_job_stores_exact_cents_and_date(self):
        created = self.post("/crm/clients", {"name": "Nový klient", "phone": "0911123456", "email": "test@example.com"})
        self.assertEqual(created.status_code, 302)
        client = Client.query.filter_by(name="Nový klient").one()
        self.assertEqual(client.user_id, self.user_id)
        response = self.post("/crm/jobs/create", {
            "title": "Nový rozvádzač", "client_id": str(client.id), "description": "Obhliadka",
            "price": "1 234,56", "due_date": "2026-09-30",
        })
        self.assertEqual(response.status_code, 302)
        job = Job.query.filter_by(title="Nový rozvádzač").one()
        plan = db.session.get(JobPlan, job.id)
        self.assertEqual((plan.user_id, plan.agreed_price_cents, plan.due_date), (self.user_id, 123456, date(2026, 9, 30)))

    def test_invalid_client_and_job_inputs_do_not_create_partial_records(self):
        client_count = Client.query.count()
        response = self.post("/crm/clients", {"name": "Zachované meno", "email": "neplatny-email"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Inputs(response.get_data(as_text=True)).values["name"], "Zachované meno")
        self.assertEqual(Client.query.count(), client_count)
        for price, due in (("12,345", "2026-09-16"), ("10,00", "2026-02-30")):
            with self.subTest(price=price, due=due):
                response = self.post("/crm/jobs/create", {"title": "Nesmie vzniknúť", "client_id": self.client_id, "price": price, "due_date": due})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(Job.query.count(), 3)
                self.assertEqual(JobPlan.query.count(), 1)

    def test_upload_validates_bytes_and_limits_before_storage(self):
        output = BytesIO()
        Image.new("RGB", (2, 2)).save(output, format="GIF")
        for content in (b"not an image", output.getvalue(), b"x" * (MAX_FILE_BYTES + 1)):
            with self.subTest(size=len(content)):
                response = self.upload(content=content, filename="fake.jpg")
                self.assertEqual(response.status_code, 302)
                self.assertEqual(JobReceipt.query.count(), 0)
                self.assertFalse((self.folder / "private_receipts").exists())
        oversized = self.upload(content=b"x" * (10 * 1024 * 1024))
        self.assertEqual(oversized.status_code, 413)

    def test_draft_is_private_and_excluded_from_costs(self):
        content = photo()
        receipt = self.new_receipt()
        self.assertEqual(receipt.status, "draft")
        self.assertIsNone(receipt.amount_cents)
        self.assertEqual(receipt.sha256, hashlib.sha256(content).hexdigest())
        self.assertEqual(receipt.object_name, f"{self.user_id}/{receipt.sha256}")
        path = self.folder / "private_receipts" / receipt.object_name
        self.assertEqual(path.read_bytes(), content)
        page = self.browser.get(f"/crm/jobs/{self.job_id}").get_data(as_text=True)
        self.assertIn("Čaká na kontrolu", page)
        self.assertIn("0,00 €", page)
        original = self.browser.get(f"/crm/receipts/{receipt.id}/original")
        self.assertEqual(original.status_code, 200)
        self.assertEqual(original.data, content)
        self.assertEqual(original.mimetype, "image/png")
        self.assertEqual(original.headers["X-Content-Type-Options"], "nosniff")
        original.close()
        self.assertEqual(self.browser.get("/static/private_receipts/" + receipt.object_name).status_code, 404)
        self.assertEqual(self.browser.get("/static/uploads/jobs/" + receipt.object_name).status_code, 404)

    def test_other_owner_receipt_read_original_and_edit_are_blocked(self):
        receipt = self.new_receipt()
        receipt_id = receipt.id
        self.login(self.other_user_id)
        for suffix in ("", "/original"):
            self.assertEqual(self.browser.get(f"/crm/receipts/{receipt_id}{suffix}").status_code, 404)
        response = self.post(f"/crm/receipts/{receipt_id}", self.confirmation(receipt, job_id=str(self.other_job_id)))
        self.assertEqual(response.status_code, 404)
        db.session.expire_all()
        self.assertEqual(db.session.get(JobReceipt, receipt_id).status, "draft")

    def test_confirmation_requires_explicit_check_and_valid_fields(self):
        receipt = self.new_receipt()
        for change in (
            {"confirmed": ""}, {"vendor": " "}, {"receipt_date": "2026-02-30"},
            {"amount": "0,00"}, {"amount": "-1,00"}, {"amount": "10,999"},
            {"amount": "10000000,01"}, {"revision": "bad"},
        ):
            with self.subTest(change=change):
                response = self.post(f"/crm/receipts/{receipt.id}", self.confirmation(receipt, **change))
                self.assertEqual(response.status_code, 400)
                db.session.expire_all()
                self.assertEqual(receipt.status, "draft")
                self.assertEqual(receipt.revision, 0)
                self.assertIsNone(receipt.confirmed_at)

    def test_invalid_confirmation_preserves_user_form_and_disables_auto_ocr(self):
        receipt = self.new_receipt()
        response = self.post(f"/crm/receipts/{receipt.id}", self.confirmation(receipt, vendor="Ručne opravený predajca", amount="12,345"))
        self.assertEqual(response.status_code, 400)
        html = response.get_data(as_text=True)
        fields = Inputs(html).values
        self.assertEqual(fields["vendor"], "Ručne opravený predajca")
        self.assertEqual(fields["amount"], "12,345")
        self.assertEqual(fields["receipt_date"], "2026-09-16")
        self.assertIn('data-auto-ocr="no"', html)
        self.assertEqual(receipt.vendor, "")

    def test_confirmed_cost_uses_exact_cents_and_can_move_to_owned_job(self):
        receipt = self.new_receipt()
        original_name = receipt.object_name
        response = self.post(f"/crm/receipts/{receipt.id}", self.confirmation(receipt, job_id=str(self.second_job_id)))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith(f"/jobs/{self.second_job_id}"))
        db.session.expire_all()
        self.assertEqual((receipt.amount_cents, receipt.receipt_date, receipt.status, receipt.revision), (123456, date(2026, 9, 16), "confirmed", 1))
        self.assertIsNotNone(receipt.confirmed_at)
        self.assertEqual(receipt.object_name, original_name)
        target = self.browser.get(f"/crm/jobs/{self.second_job_id}").get_data(as_text=True)
        self.assertIn("1 234,56 €", target)
        self.assertNotIn("Stavebniny Poprad", self.browser.get(f"/crm/jobs/{self.job_id}").get_data(as_text=True))

    def test_confirmation_cannot_move_receipt_to_foreign_job(self):
        receipt = self.new_receipt()
        response = self.post(f"/crm/receipts/{receipt.id}", self.confirmation(receipt, job_id=str(self.other_job_id)))
        self.assertEqual(response.status_code, 404)
        db.session.expire_all()
        self.assertEqual((receipt.job_id, receipt.status), (self.job_id, "draft"))

    def test_duplicate_image_is_idempotent_across_jobs_for_one_owner(self):
        receipt = self.new_receipt()
        first_path = receipt.object_name
        response = self.upload(self.second_job_id, photo(), "iny-nazov.jpg")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/" + receipt.id))
        self.assertEqual(JobReceipt.query.count(), 1)
        self.assertEqual(receipt.job_id, self.job_id)
        self.assertEqual(receipt.original_name, "blocek.png")
        self.assertEqual(receipt.object_name, first_path)
        self.assertEqual(len(list((self.folder / "private_receipts").rglob("*"))), 2)

    def test_identical_image_for_different_owner_gets_separate_private_object(self):
        receipt = self.new_receipt()
        first_id, first_object = receipt.id, receipt.object_name
        self.login(self.other_user_id)
        second = self.new_receipt(job_id=self.other_job_id)
        self.assertNotEqual(second.id, first_id)
        self.assertNotEqual(second.object_name, first_object)
        self.assertEqual(JobReceipt.query.count(), 2)
        self.assertEqual(self.browser.get(f"/crm/receipts/{first_id}/original").status_code, 404)

    def test_stale_revision_does_not_overwrite_confirmed_cost_or_original(self):
        receipt = self.new_receipt()
        receipt_id, object_name = receipt.id, receipt.object_name
        first = self.post(f"/crm/receipts/{receipt_id}", self.confirmation(receipt, amount="12,50", revision="0"))
        self.assertEqual(first.status_code, 302)
        stale = self.post(f"/crm/receipts/{receipt_id}", self.confirmation(receipt, amount="99,99", vendor="Stará karta", revision="0"))
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(Inputs(stale.get_data(as_text=True)).values["amount"], "99,99")
        db.session.expire_all()
        receipt = db.session.get(JobReceipt, receipt_id)
        self.assertEqual((receipt.amount_cents, receipt.vendor, receipt.revision, receipt.object_name), (1250, "Stavebniny Poprad", 1, object_name))
        corrected = self.post(f"/crm/receipts/{receipt_id}", self.confirmation(receipt, amount="13,00", revision="1"))
        self.assertEqual(corrected.status_code, 302)
        db.session.expire_all()
        self.assertEqual((receipt.amount_cents, receipt.revision), (1300, 2))

    def test_original_route_rejects_tampered_path(self):
        receipt = self.new_receipt()
        receipt.object_name = "../outside.png"
        db.session.commit()
        self.assertEqual(self.browser.get(f"/crm/receipts/{receipt.id}/original").status_code, 404)

    def test_upload_does_not_overwrite_corrupt_existing_original(self):
        receipt = self.new_receipt()
        path = self.folder / "private_receipts" / receipt.object_name
        path.write_bytes(b"corrupt original")
        # Removing only the disposable database record rehearses an orphaned
        # private object. A retry must fail rather than overwrite evidence.
        db.session.delete(receipt)
        db.session.commit()
        response = self.upload()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(path.read_bytes(), b"corrupt original")
        self.assertEqual(JobReceipt.query.count(), 0)

    def test_csrf_and_foreign_origin_block_mutations(self):
        endpoint = f"/crm/jobs/{self.job_id}/status"
        self.assertEqual(self.browser.post(endpoint, data={"status": "done"}).status_code, 400)
        self.assertEqual(self.post(endpoint, {"status": "done"}, headers={"Origin": "https://foreign.invalid"}).status_code, 403)
        self.assertEqual(db.session.get(Job, self.job_id).status, "new")
        valid = self.post(endpoint, {"status": "done"}, headers={"Origin": "http://localhost"})
        self.assertEqual(valid.status_code, 302)
        self.assertEqual(db.session.get(Job, self.job_id).status, "done")

    def test_job_note_is_saved_and_visible_only_on_its_job(self):
        content = "Obhliadka: skontrolovať rozvádzač a zásuvky."
        response = self.post(f"/crm/jobs/{self.job_id}/notes", {"content": content})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith(f"/crm/jobs/{self.job_id}"))
        note = JobNote.query.one()
        self.assertEqual((note.job_id, note.user_id, note.content),
                         (self.job_id, self.user_id, content))
        self.assertIn(content, self.browser.get(f"/crm/jobs/{self.job_id}").get_data(as_text=True))
        self.assertNotIn(content, self.browser.get(f"/crm/jobs/{self.second_job_id}").get_data(as_text=True))

    def test_invalid_job_note_does_not_save_and_keeps_draft(self):
        endpoint = f"/crm/jobs/{self.job_id}/notes"
        self.assertEqual(self.post(endpoint, {"content": "   "}).status_code, 200)
        self.assertEqual(JobNote.query.count(), 0)
        draft = "Rozpracovaná poznámka " + "x" * 3000
        response = self.post(endpoint, {"content": draft})
        self.assertEqual(response.status_code, 200)
        self.assertIn(draft, response.get_data(as_text=True))
        self.assertEqual(JobNote.query.count(), 0)

    def test_note_cannot_be_added_to_another_users_job(self):
        response = self.post(f"/crm/jobs/{self.other_job_id}/notes",
                             {"content": "Cudzia poznámka"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(JobNote.query.count(), 0)

    def test_database_rejects_incomplete_confirmation_and_duplicate_hash(self):
        receipt = self.new_receipt()
        receipt.status = "confirmed"
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        duplicate = JobReceipt(user_id=self.user_id, job_id=self.second_job_id, sha256=receipt.sha256,
                               object_name=receipt.object_name, original_name="duplicate.png", mime="image/png")
        db.session.add(duplicate)
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()
        self.assertEqual(JobReceipt.query.count(), 1)

    def test_database_enforces_confirmation_and_money_boundaries(self):
        receipt = self.new_receipt()
        self.assertEqual(self.post(f"/crm/receipts/{receipt.id}", self.confirmation(receipt)).status_code, 302)
        for field, value in (
            ("amount_cents", -1), ("amount_cents", 0), ("amount_cents", 1000000001),
            ("amount_cents", None), ("receipt_date", None), ("vendor", "   "),
            ("confirmed_at", None), ("status", "sent"), ("revision", -1),
        ):
            with self.subTest(field=field, value=value):
                setattr(receipt, field, value)
                with self.assertRaises(IntegrityError):
                    db.session.commit()
                db.session.rollback()
        plan = db.session.get(JobPlan, self.job_id)
        plan.agreed_price_cents = -1
        with self.assertRaises(IntegrityError):
            db.session.commit()
        db.session.rollback()


class ValidationTests(unittest.TestCase):
    def test_money_parsing_is_exact_and_refuses_ambiguous_inputs(self):
        for value, expected in (("0,01", 1), ("12.5", 1250), ("1\u00a0234,56", 123456), ("10000000", 1000000000)):
            with self.subTest(value=value):
                self.assertEqual(parse_cents(value), expected)
        for value in ("1,234.56", "1.234,56", "12 34,56", "1e3", "NaN", "-1", "12,345", "10000000,01"):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    parse_cents(value)
        self.assertIsNone(parse_cents("", optional=True))
        self.assertEqual(format_money(123456), "1 234,56 €")

    def test_date_rejects_calendar_normalization(self):
        self.assertEqual(parse_date("2024-02-29"), date(2024, 2, 29))
        for value in ("2026-02-29", "2026-02-30", "16.09.2026", "2026-9-16", None):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    parse_date(value)
        self.assertIsNone(parse_date("", optional=True))

    def test_migration_roundtrip_preserves_existing_schema_and_data(self):
        with tempfile.TemporaryDirectory(prefix="crm-migration-test-") as folder:
            engine = sa.create_engine("sqlite:///" + (Path(folder) / "migration.sqlite3").as_posix())
            try:
                old_tables = [table for table in db.metadata.sorted_tables if table.name not in {"job_plans", "job_receipts"}]
                db.metadata.create_all(engine, tables=old_tables)
                spec = importlib.util.spec_from_file_location("crm_receipt_migration", ROOT / "migrations/versions/d72c913f1b08_add_local_crm_receipts.py")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                self.assertEqual(module.down_revision, "631e160e6364")
                with engine.begin() as connection:
                    connection.execute(sa.insert(User.__table__).values(id=1, email="migration@example.invalid", username="migration", password_hash="unused"))
                    connection.execute(sa.insert(Job.__table__).values(id=1, user_id=1, title="Zachovať pôvodnú zákazku", status="new"))
                    context = MigrationContext.configure(connection)
                    with Operations.context(context):
                        module.upgrade()
                        self.assertTrue({"job_plans", "job_receipts"}.issubset(sa.inspect(connection).get_table_names()))
                        connection.execute(sa.insert(JobPlan.__table__).values(job_id=1, user_id=1, agreed_price_cents=123456))
                        with self.assertRaises(IntegrityError):
                            connection.execute(sa.insert(JobReceipt.__table__).values(id="invalid-confirmed", user_id=1, job_id=1, sha256="a" * 64, object_name="1/" + "a" * 64, original_name="sample.png", mime="image/png", status="confirmed"))
                        module.downgrade()
                    names = set(sa.inspect(connection).get_table_names())
                    self.assertNotIn("job_receipts", names)
                    self.assertNotIn("job_plans", names)
                    self.assertEqual(connection.execute(sa.select(Job.__table__.c.title)).scalar_one(), "Zachovať pôvodnú zákazku")
            finally:
                engine.dispose()

    def test_local_factory_guards_remote_access_in_disposable_directory(self):
        # Importing this preview factory neither loads .env nor imports app.py.
        import crm_local
        with tempfile.TemporaryDirectory(prefix="crm-local-factory-test-") as folder:
            with patch.object(crm_local, "ROOT", Path(folder)):
                app = crm_local.create_local_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
            browser = app.test_client()
            self.assertEqual(browser.get("/crm/health", base_url="http://127.0.0.1:5180", environ_overrides={"REMOTE_ADDR": "127.0.0.1"}).status_code, 200)
            self.assertEqual(browser.get("/crm/health", base_url="http://127.0.0.1:5180", environ_overrides={"REMOTE_ADDR": "192.0.2.1"}).status_code, 403)
            self.assertEqual(browser.get("/crm/health", base_url="http://foreign.invalid:5180", environ_overrides={"REMOTE_ADDR": "127.0.0.1"}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
