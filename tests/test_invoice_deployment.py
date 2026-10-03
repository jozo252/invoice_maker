"""Migration release rehearsal with existing linked records and a legacy guard."""

from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from flask_migrate import upgrade

from app import create_app
from extensions import db
from scripts.audit_invoice_db import audit
from scripts.preflight_invoice_migration import PreflightError, rehearse
from scripts.verify_invoice_migration import verify


ROOT = Path(__file__).resolve().parents[1]


class InvoiceDeploymentTests(unittest.TestCase):
    def test_versioned_database_upgrades_without_changing_existing_rows(self):
        with tempfile.TemporaryDirectory(prefix="invoice-release-test-") as folder:
            source = Path(folder) / "source.sqlite3"
            copy = Path(folder) / "copy.sqlite3"
            app = create_app({
                "TESTING": True, "SECRET_KEY": "deployment-test",
                "SQLALCHEMY_DATABASE_URI": "sqlite:///" + source.as_posix(),
            })
            with app.app_context():
                upgrade(directory=str(ROOT / "migrations"), revision="631e160e6364")
                db.session.remove()
                db.engine.dispose()
            with closing(sqlite3.connect(source)) as connection:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute(
                    "INSERT INTO users (id, email, username, password_hash) "
                    "VALUES (1, 'test@example.invalid', 'electrician', 'unused')"
                )
                connection.execute(
                    "INSERT INTO clients (id, user_id, name) VALUES (1, 1, 'Test klient')"
                )
                connection.execute(
                    "INSERT INTO companies (id, user_id, name, ico, dic, street, city, zip_code, "
                    "country, email, phone, iban, bic) VALUES "
                    "(1, 1, 'Test firma', '12345678', '1234567890', 'Ulica 1', 'Poprad', "
                    "'05801', 'SK', 'test@example.invalid', '0900000000', 'SK00', 'TESTSKBX')"
                )
                connection.execute(
                    "INSERT INTO lead (id, user_id, name, customer_name, status) "
                    "VALUES (1, 1, 'Servis', 'Test klient', 'new')"
                )
                connection.execute(
                    "INSERT INTO jobs (id, user_id, client_id, company_id, title, status) "
                    "VALUES (1, 1, 1, 1, 'Montáž', 'done')"
                )
                connection.execute(
                    "INSERT INTO offer (id, user_id, company_id, lead_id, job_id, currency, "
                    "customer_name, items, status) VALUES "
                    "(1, 1, 1, 1, 1, 'EUR', 'Test klient', '[]', 'sent')"
                )
                connection.execute(
                    "INSERT INTO invoices (id, invoice_number, date, due_date, delivery_date, "
                    "user_id, currency, total_cost, client_id, company_id, status, "
                    "discount_total, payment_method) VALUES "
                    "(1, '2026-0001', '2026-10-01', '2026-10-15', '2026-10-01', "
                    "1, 'EUR', 50, 1, 1, 'unpaid', 0, 'bank_transfer')"
                )
                connection.execute(
                    "INSERT INTO invoice_items (id, invoice_id, description, quantity, unit, "
                    "price_per_item, total_cost) VALUES (1, 1, 'Montáž', 1, 'ks', 50, 50)"
                )
                connection.execute(
                    "INSERT INTO job_attachments (id, job_id, user_id, filename, "
                    "original_filename, file_path) VALUES "
                    "(1, 1, 1, 'photo.png', 'photo.png', 'uploads/jobs/1/photo.png')"
                )
                connection.execute(
                    "INSERT INTO job_notes (id, job_id, user_id, content, note_type) "
                    "VALUES (1, 1, 1, 'Rozvádzač', 'note')"
                )
                connection.commit()
            before_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            completed = subprocess.run(
                [sys.executable, "-B", str(ROOT / "scripts/preflight_invoice_migration.py"),
                 "--source", str(source), "--copy", str(copy)],
                cwd=ROOT, capture_output=True, text=True, check=True,
            )
            result = json.loads(completed.stdout)
            after_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            self.assertEqual(before_hash, after_hash)
            self.assertEqual(result["source_revision"], "631e160e6364")
            self.assertEqual(result["copy_revision"], "b47a19de0c62")
            inspected = audit(copy)
            self.assertEqual(inspected["quick_check"], "ok")
            self.assertEqual(inspected["foreign_key_violations"], 0)
            self.assertEqual(inspected["row_counts"]["invoices"], 1)
            self.assertEqual(inspected["row_counts"]["job_attachments"], 1)
            self.assertEqual(verify(source, copy)["preserved_rows"], result["preserved_rows"])
            with closing(sqlite3.connect(copy)) as connection:
                connection.execute("UPDATE invoices SET total_cost = 51 WHERE id = 1")
                connection.commit()
            with self.assertRaisesRegex(PreflightError, "zmenila pôvodné dáta"):
                verify(source, copy)

    def test_unversioned_legacy_database_is_rejected_before_copy(self):
        with tempfile.TemporaryDirectory(prefix="invoice-legacy-test-") as folder:
            source = Path(folder) / "legacy.sqlite3"
            copy = Path(folder) / "copy.sqlite3"
            with closing(sqlite3.connect(source)) as connection:
                connection.execute("CREATE TABLE lead (id INTEGER PRIMARY KEY)")
                connection.commit()
            with self.assertRaisesRegex(PreflightError, "alembic_version"):
                rehearse(source, copy)
            self.assertFalse(copy.exists())


if __name__ == "__main__":
    unittest.main()
