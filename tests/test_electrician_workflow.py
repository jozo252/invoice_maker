"""P0 case lifecycle and additive migration against disposable SQLite files."""

import importlib.util
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import sqlalchemy as sa
from PIL import Image
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask_migrate import upgrade
from flask import render_template

from app import create_app
from extensions import db
from models import (Client, Company, Invoice, Job, JobAttachment, JobChange, JobCost,
                    JobMaterial, JobPlan, Lead, Offer, OfferRevision,
                    PriceEntry, Site, User, WorkActivity)
from offers import generate_offer_from_text
from routes import InvoiceDocument


ROOT = Path(__file__).resolve().parents[1]


class ElectricianWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="electrician-workflow-test-")
        self.folder = Path(self.temporary.name)
        self.app = create_app({
            "TESTING": True,
            "SECRET_KEY": "isolated-workflow-test",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///" + (self.folder / "test.sqlite3").as_posix(),
            "WTF_CSRF_ENABLED": False,
            "MAIL_SUPPRESS_SEND": True,
            "CRM_RECEIPT_FOLDER": str(self.folder / "receipts"),
            "JOB_ATTACHMENT_FOLDER": str(self.folder / "private_job_attachments"),
        })
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        owner = User(username="electrician", email="electrician@example.invalid", password_hash="unused")
        other = User(username="other", email="other@example.invalid", password_hash="unused")
        db.session.add_all([owner, other])
        db.session.flush()
        self.owner_id, self.other_id = owner.id, other.id
        company = Company(
            user_id=owner.id, name="Elektro Test", ico="12345678", dic="1234567890",
            street="Test 1", city="Poprad", zip_code="05801", country="SK",
            email="office@example.invalid", phone="0900123456", iban="SK0000000000000000000000",
            bic="TESTSKBX", is_vat_payer=False,
        )
        db.session.add(company)
        db.session.commit()
        self.company_id = company.id
        self.browser = self.app.test_client()
        with self.browser.session_transaction() as session:
            session["_user_id"] = str(self.owner_id)
            session["_fresh"] = True

    def tearDown(self):
        db.session.remove()
        db.engine.dispose()
        self.context.pop()
        self.temporary.cleanup()

    def test_lead_visit_quote_accept_job_invoice_without_retyping(self):
        response = self.browser.post("/offers/leads/create", data={
            "name": "TV zásuvky", "customer_name": "Novák",
            "customer_phone": "0900111222", "description": "Dve zásuvky v obývačke",
            "source": "phone", "work_type": "service",
            "site_street": "Hlavná 7", "site_city": "Poprad",
            "site_zip_code": "05801", "site_country": "SK",
        })
        self.assertEqual(response.status_code, 302)
        lead = Lead.query.filter_by(user_id=self.owner_id).one()
        self.assertEqual(lead.site.city, "Poprad")
        self.assertEqual(self.browser.get(f"/offers/leads/{lead.id}").status_code, 200)
        self.assertEqual(self.browser.get("/offers/leads").status_code, 200)

        response = self.browser.post(f"/offers/leads/{lead.id}/visits", data={
            "starts_at": "2026-10-03T10:30", "notes": "Za TV 2x zásuvka, 1x CAT6",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(WorkActivity.query.filter_by(lead_id=lead.id).count(), 1)

        self.assertEqual(self.browser.get(f"/offers/offers/create-from-lead/{lead.id}").status_code, 200)
        response = self.browser.post(f"/offers/offers/create-from-lead/{lead.id}", data={
            "company_id": str(self.company_id), "customer_name": "Novák",
            "customer_email": "novak@example.invalid", "currency": "EUR",
            "notes": "Dve zásuvky v obývačke", "item_name[]": ["Zásuvka", "CAT6"],
            "item_qty[]": ["2", "1"], "item_unit[]": ["ks", "ks"],
            "item_price[]": ["50", "30"],
        })
        self.assertEqual(response.status_code, 302)
        offer = Offer.query.filter_by(lead_id=lead.id).one()
        self.assertEqual(offer.site_id, lead.site_id)
        self.assertEqual(self.browser.get(f"/offers/{offer.id}").status_code, 200)

        # No price review means no commercial send state.
        self.browser.post(f"/offers/{offer.id}/mark-sent", data={"delivery_note": "WhatsApp 3.10.2026"})
        self.assertEqual(OfferRevision.query.count(), 0)
        self.browser.post(f"/offers/{offer.id}/mark-sent", data={
            "delivery_note": "WhatsApp 3.10.2026", "prices_confirmed": "yes",
        })
        revision = OfferRevision.query.filter_by(offer_id=offer.id).one()
        self.assertEqual(revision.payload["total"], "130.00")
        self.assertEqual(lead.status, "quoted")

        response = self.browser.post(f"/offers/{offer.id}/mark_accepted", data={
            "acceptance_note": "WhatsApp 3.10.2026", "create_client": "yes",
        })
        self.assertEqual(response.status_code, 302)
        job = Job.query.filter_by(offer_revision_id=revision.id).one()
        self.assertEqual(job.client_id, lead.client_id)
        self.assertEqual(job.site_id, lead.site_id)
        self.assertEqual(job.status, "approved")
        self.assertEqual(Client.query.filter_by(user_id=self.owner_id).count(), 1)
        self.browser.post(f"/offers/{offer.id}/mark_accepted", data={
            "acceptance_note": "WhatsApp 3.10.2026", "create_client": "yes",
        })
        self.assertEqual(Job.query.filter_by(offer_revision_id=revision.id).count(), 1)

        self.browser.post(f"/jobs/{job.id}/changes", data={
            "description": "Ďalšia zásuvka", "quantity": "1", "unit": "ks",
            "unit_price": "20",
        })
        change = JobChange.query.filter_by(job_id=job.id).one()
        self.assertEqual(change.status, "proposed")
        self.browser.post(f"/jobs/{job.id}/changes/{change.id}/approve", data={"approval_note": ""})
        self.assertEqual(change.status, "proposed")
        self.browser.post(f"/jobs/{job.id}/changes/{change.id}/approve", data={
            "approval_note": "WhatsApp 3.10.2026",
        })
        self.assertEqual(change.status, "approved")
        self.browser.post(f"/jobs/{job.id}/changes", data={
            "description": "Nevyžiadaná práca", "quantity": "1", "unit": "ks",
            "unit_price": "99",
        })

        client = db.session.get(Client, job.client_id)
        client.street, client.city, client.zip_code, client.country = "Fakturačná 1", "Poprad", "05801", "SK"
        legacy_invoice = Invoice(
            user_id=self.owner_id, client_id=client.id, company_id=self.company_id,
            invoice_number="2026-0001", date=date(2026, 10, 1),
            due_date=date(2026, 10, 15), currency="EUR", total_cost=10,
        )
        db.session.add(legacy_invoice)
        db.session.commit()
        self.assertEqual(self.browser.get(f"/jobs/{job.id}/invoice").status_code, 302)
        self.browser.post(f"/jobs/{job.id}/status", data={"status": "done"})
        self.assertEqual(self.browser.get(f"/jobs/{job.id}/invoice").status_code, 200)
        response = self.browser.post(f"/jobs/{job.id}/invoice", data={
            "issue_date": "2026-10-03", "delivery_date": "2026-10-03",
            "due_date": "2026-10-17", "vat_rate": "0",
            "payment_method": "bank_transfer", "confirmed": "yes",
        })
        self.assertEqual(response.status_code, 302)
        invoice = Invoice.query.filter_by(job_id=job.id).one()
        self.assertEqual(invoice.invoice_number, "2026-0002")
        self.assertEqual(invoice.offer_revision_id, revision.id)
        self.assertEqual(Decimal(str(invoice.total_cost)), Decimal("150.0"))
        self.assertEqual(len(invoice.items), 3)
        self.assertEqual(sum(Decimal(str(item.total_cost)) for item in invoice.items)
                         - Decimal(str(invoice.discount_total)), Decimal(str(invoice.total_cost)))
        self.assertEqual(job.status, "invoiced")
        client.name = "Neskorší nový názov"
        db.session.commit()
        issued_page = self.browser.get(f"/invoice/{invoice.id}")
        self.assertEqual(issued_page.status_code, 200)
        self.assertIn("Novák", issued_page.get_data(as_text=True))
        self.assertNotIn("Neskorší nový názov", issued_page.get_data(as_text=True))
        with self.app.test_request_context():
            pdf_html = render_template("invoice_pdf.html", invoice=InvoiceDocument(invoice),
                                       qr_svg=None, stamp_data_uri=None,
                                       grand_total=invoice.total_cost, vat_amount=Decimal("0"))
        self.assertIn("Novák", pdf_html)
        self.assertNotIn("Neskorší nový názov", pdf_html)
        self.browser.post(f"/jobs/{job.id}/invoice", data={})
        self.assertEqual(Invoice.query.filter_by(job_id=job.id).count(), 1)

    def test_foreign_records_and_invalid_numbers_are_rejected(self):
        self.assertEqual(self.browser.get("/offers/leads/9999").status_code, 404)
        foreign = Lead(user_id=self.other_id, name="Cudzí", description="test")
        db.session.add(foreign)
        db.session.commit()
        self.assertEqual(self.browser.get(f"/offers/leads/{foreign.id}").status_code, 404)
        response = self.browser.post("/offers/offers/create", data={
            "company_id": str(self.company_id), "customer_name": "Test",
            "currency": "EUR", "item_name[]": "Zásuvka",
            "item_qty[]": "-1", "item_unit[]": "ks", "item_price[]": "50",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Offer.query.count(), 0)
        response = self.browser.post("/offers/offers/create", data={
            "company_id": str(self.company_id), "customer_name": "Test",
            "currency": "EUR", "item_name[]": "Zásuvka",
            "item_qty[]": "1", "item_unit[]": "ks", "item_price[]": "1.234",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Offer.query.count(), 0)

    def test_ai_scope_never_supplies_sale_price(self):
        with patch("offers.call_llm_extract_offer", return_value={
            "customer_name": "Test", "currency": "EUR", "items": [
                {"name": "Zásuvka", "quantity": 2, "unit": "ks", "price_per_item": 500},
            ], "discount_total": 10,
        }):
            result = generate_offer_from_text("2 zásuvky", self.company_id, self.owner_id)
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["items"][0]["price_per_item"], 0)
        self.assertEqual(result["data"]["total"], Decimal("0.00"))
        self.assertTrue(result["data"]["warnings"])

    def test_pricebook_item_is_copied_into_quote_without_future_price_drift(self):
        self.browser.post("/pricebook", data={
            "kind": "labor", "description": "Montáž zásuvky", "unit": "ks",
            "sale_price": "50.00", "cost": "20.00",
            "source_note": "Vlastná kalkulácia 2026",
        })
        entry = PriceEntry.query.filter_by(user_id=self.owner_id).one()
        self.assertEqual(entry.sale_price_cents, 5000)
        self.assertIn("Montáž zásuvky", self.browser.get("/offers/offers/create").get_data(as_text=True))
        self.browser.post("/offers/offers/create", data={
            "company_id": str(self.company_id), "customer_name": "Test",
            "currency": "EUR", "item_name[]": "Montáž zásuvky",
            "item_qty[]": "2", "item_unit[]": "ks", "item_price[]": "50.00",
            "item_catalog_id[]": str(entry.id),
        })
        offer = Offer.query.filter_by(user_id=self.owner_id).one()
        self.assertEqual(offer.items[0]["unit_cost_cents"], 2000)
        self.browser.post(f"/offers/{offer.id}/mark-sent", data={
            "delivery_note": "Osobne 3.10.2026", "prices_confirmed": "yes",
        })
        revision = OfferRevision.query.filter_by(offer_id=offer.id).one()
        self.assertEqual(revision.payload["internal_estimated_direct_cost_cents"], 4000)
        self.browser.post(f"/pricebook/{entry.id}/update", data={
            "sale_price": "70.00", "cost": "30.00", "source_note": "Nová cena",
        })
        self.assertEqual(revision.payload["total"], "100.00")
        self.assertEqual(revision.payload["internal_estimated_direct_cost_cents"], 4000)

    def test_quote_from_job_renders_pricebook_and_rejects_foreign_entry(self):
        job = Job(user_id=self.owner_id, title="Servis", status="new",
                  company_id=self.company_id)
        foreign_entry = PriceEntry(user_id=self.other_id, kind="labor",
                                   description="Cudzia práca", unit="ks",
                                   sale_price_cents=10000)
        db.session.add_all([job, foreign_entry])
        db.session.commit()
        page = self.browser.get(f"/offers/offers/create-from-job/{job.id}")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn("Cudzia práca", page.get_data(as_text=True))
        response = self.browser.post(f"/offers/offers/create-from-job/{job.id}", data={
            "company_id": str(self.company_id), "customer_name": "Test",
            "currency": "EUR", "item_name[]": "Cudzia práca",
            "item_qty[]": "1", "item_unit[]": "ks", "item_price[]": "100.00",
            "item_catalog_id[]": str(foreign_entry.id),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Offer.query.count(), 0)

    def test_job_photo_is_private_tagged_searchable_and_owner_checked(self):
        own = Job(user_id=self.owner_id, title="TV kábel", status="in_progress")
        foreign = Job(user_id=self.other_id, title="Cudzí kábel", status="in_progress")
        db.session.add_all([own, foreign])
        db.session.commit()
        photo = BytesIO()
        Image.new("RGB", (24, 24), "white").save(photo, format="PNG")
        photo.seek(0)
        response = self.browser.post(f"/jobs/{own.id}/attachments/add", data={
            "file": (photo, "pred-zakrytim.png"), "room_label": "Obývačka",
            "element_label": "Zásuvka za TV", "cable_type": "CYKY 3x2,5",
            "route_note": "20 cm pod stropom",
        }, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 302)
        attachment = JobAttachment.query.filter_by(job_id=own.id).one()
        self.assertTrue(attachment.file_path.startswith(f"private/{self.owner_id}/{own.id}/"))
        self.assertNotIn("static", str(self.folder / "private_job_attachments"))
        view = self.browser.get(f"/jobs/{own.id}/attachments/{attachment.id}")
        self.assertEqual(view.status_code, 200)
        self.assertEqual(view.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("image/png", view.headers["Content-Type"])
        view.close()
        self.assertEqual(self.browser.get(f"/jobs/{foreign.id}/attachments/{attachment.id}").status_code, 404)
        self.assertEqual(self.browser.get("/static/uploads/jobs/1/legacy.png").status_code, 404)
        page = self.browser.get(f"/jobs/{own.id}?q=stropom")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Zásuvka za TV", page.get_data(as_text=True))
        self.browser.post(f"/jobs/{own.id}/attachments/add", data={
            "file": (BytesIO(b"<script>bad</script>"), "fake.png"),
        }, content_type="multipart/form-data")
        self.assertEqual(JobAttachment.query.filter_by(job_id=own.id).count(), 1)
        self.browser.post(f"/jobs/{own.id}/attachments/{attachment.id}/delete")
        self.assertEqual(JobAttachment.query.filter_by(job_id=own.id).count(), 0)

    def test_material_checklist_and_labor_cost_are_owner_checked(self):
        own = Job(user_id=self.owner_id, company_id=self.company_id,
                  title="Materiál a práca", status="in_progress")
        foreign = Job(user_id=self.other_id, title="Cudzí", status="in_progress")
        db.session.add_all([own, foreign])
        db.session.flush()
        db.session.add(JobPlan(job_id=own.id, user_id=self.owner_id, agreed_price_cents=100000))
        db.session.commit()
        self.assertEqual(self.browser.post(f"/jobs/{foreign.id}/materials", data={
            "description": "Kábel", "quantity": "2", "unit": "m",
        }).status_code, 404)
        self.browser.post(f"/jobs/{own.id}/materials", data={
            "description": "CYKY", "quantity": "10", "unit": "m",
        })
        material = JobMaterial.query.filter_by(job_id=own.id).one()
        self.assertEqual(material.status, "needed")
        board = self.browser.get("/today")
        self.assertEqual(board.status_code, 200)
        self.assertIn("CYKY", board.get_data(as_text=True))
        self.assertNotIn("Cudzí", board.get_data(as_text=True))
        self.browser.post(f"/jobs/{own.id}/activities", data={
            "kind": "work", "starts_at": date.today().isoformat() + "T10:00",
            "notes": "Montáž rozvádzača",
        })
        self.assertIn("Montáž rozvádzača", self.browser.get("/today").get_data(as_text=True))
        self.browser.post(f"/jobs/{own.id}/materials/{material.id}/status", data={"status": "used"})
        self.assertEqual(material.status, "used")
        self.assertNotIn("CYKY", self.browser.get("/today").get_data(as_text=True))
        self.browser.post(f"/jobs/{own.id}/costs", data={
            "category": "labor", "description": "Montáž", "minutes": "90",
            "hourly_cost": "20", "occurred_on": "2026-10-03",
        })
        labor = JobCost.query.filter_by(job_id=own.id).one()
        self.assertEqual(labor.amount_cents, 3000)
        self.browser.post(f"/jobs/{own.id}/costs", data={
            "category": "travel", "description": "Cesta", "amount": "7.50",
            "occurred_on": "2026-10-03",
        })
        self.assertEqual(JobCost.query.filter_by(job_id=own.id).count(), 2)
        page = self.browser.get(f"/jobs/{own.id}")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Neúplné údaje", page.get_data(as_text=True))
        self.assertEqual(self.browser.post(f"/jobs/{foreign.id}/costs/{labor.id}/delete").status_code, 404)
        self.browser.post(f"/jobs/{own.id}/costs/{labor.id}/delete")
        self.assertEqual(JobCost.query.filter_by(job_id=own.id).count(), 1)


class MigrationTests(unittest.TestCase):
    def test_complete_revision_chain_on_empty_disposable_database(self):
        with tempfile.TemporaryDirectory(prefix="electrician-chain-test-") as folder:
            path = Path(folder) / "chain.sqlite3"
            app = create_app({
                "TESTING": True, "SECRET_KEY": "migration-test",
                "SQLALCHEMY_DATABASE_URI": "sqlite:///" + path.as_posix(),
            })
            with app.app_context():
                upgrade(directory=str(ROOT / "migrations"), revision="b47a19de0c62")
                inspector = sa.inspect(db.engine)
                self.assertIn("offer_revisions", inspector.get_table_names())
                self.assertIn("job_materials", inspector.get_table_names())
                self.assertIn("job_costs", inspector.get_table_names())
                self.assertIn("job_changes", inspector.get_table_names())
                self.assertIn("price_entries", inspector.get_table_names())
                self.assertIn("buyer_snapshot", {column["name"] for column in inspector.get_columns("invoices")})
                db.session.remove()
                db.engine.dispose()

    def test_additive_upgrade_keeps_existing_rows(self):
        with tempfile.TemporaryDirectory(prefix="electrician-migration-test-") as folder:
            engine = sa.create_engine("sqlite:///" + (Path(folder) / "migration.sqlite3").as_posix())
            metadata = sa.MetaData()
            for name in ("users", "clients", "lead", "offer", "jobs", "invoices", "job_attachments"):
                sa.Table(name, metadata, sa.Column("id", sa.Integer, primary_key=True),
                         sa.Column("legacy_marker", sa.String(30)))
            metadata.create_all(engine)
            spec = importlib.util.spec_from_file_location(
                "electrician_migration", ROOT / "migrations/versions/ea42d6a90b17_electrician_workflow_foundation.py")
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            self.assertEqual(migration.down_revision, "d72c913f1b08")
            p1_spec = importlib.util.spec_from_file_location(
                "electrician_p1_migration", ROOT / "migrations/versions/f36b7c0912da_job_materials_and_costs.py")
            p1_migration = importlib.util.module_from_spec(p1_spec)
            p1_spec.loader.exec_module(p1_migration)
            self.assertEqual(p1_migration.down_revision, migration.revision)
            change_spec = importlib.util.spec_from_file_location(
                "electrician_change_migration", ROOT / "migrations/versions/c42f980d7b25_job_changes.py")
            change_migration = importlib.util.module_from_spec(change_spec)
            change_spec.loader.exec_module(change_migration)
            self.assertEqual(change_migration.down_revision, p1_migration.revision)
            price_spec = importlib.util.spec_from_file_location(
                "electrician_price_migration", ROOT / "migrations/versions/b47a19de0c62_price_entries.py")
            price_migration = importlib.util.module_from_spec(price_spec)
            price_spec.loader.exec_module(price_migration)
            self.assertEqual(price_migration.down_revision, change_migration.revision)
            with engine.begin() as connection:
                connection.execute(sa.text("INSERT INTO lead (id, legacy_marker) VALUES (1, 'keep-me')"))
                context = MigrationContext.configure(connection)
                with Operations.context(context):
                    migration.upgrade()
                    p1_migration.upgrade()
                    change_migration.upgrade()
                    price_migration.upgrade()
                inspector = sa.inspect(connection)
                self.assertTrue({"sites", "offer_revisions", "work_activities"}.issubset(inspector.get_table_names()))
                self.assertTrue({"job_materials", "job_costs"}.issubset(inspector.get_table_names()))
                self.assertIn("job_changes", inspector.get_table_names())
                self.assertIn("price_entries", inspector.get_table_names())
                self.assertIn("site_id", {column["name"] for column in inspector.get_columns("lead")})
                self.assertIn("room_label", {column["name"] for column in inspector.get_columns("job_attachments")})
                self.assertIn("buyer_snapshot", {column["name"] for column in inspector.get_columns("invoices")})
                self.assertEqual(connection.execute(sa.text("SELECT legacy_marker FROM lead WHERE id=1")).scalar_one(), "keep-me")
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
