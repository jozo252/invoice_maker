"""Authenticated mobile pilot regressions using only disposable SQLite data."""
from datetime import datetime, timezone
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image
from werkzeug.security import generate_password_hash

from extensions import db
from models import Client, Job, JobReceipt, User


ORIGIN = "https://invoicemakerai.com"
PREFIX = "/remeselnici"
CODE = "synthetic-test-access-code-72f441b59f"


class Inputs(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.values = {}
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "input" and "name" in values:
            self.values[values["name"]] = values.get("value", "")


class PilotTests(unittest.TestCase):
    def setUp(self):
        from crm_pilot import create_pilot_app
        self.temporary = tempfile.TemporaryDirectory(prefix="invoicemaker-mobile-test-")
        self.folder = Path(self.temporary.name)
        self.app = create_pilot_app({
            "TESTING": True,
            "CRM_INSTANCE_DIR": str(self.folder),
            "CRM_PUBLIC_ORIGIN": ORIGIN,
            "CRM_URL_PREFIX": PREFIX,
            # Cheap, deterministic verification belongs only in this isolated test.
            "CRM_ACCESS_HASH": generate_password_hash(CODE, method="pbkdf2:sha256:1000"),
            "SECRET_KEY": "synthetic-disposable-mobile-session-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///" + (self.folder / "test.sqlite3").as_posix(),
            "WTF_CSRF_ENABLED": True,
        })
        with self.app.app_context():
            self.assertTrue(Path(db.engine.url.database).resolve().is_relative_to(self.folder.resolve()))
            db.create_all()
            db.session.add(User(
                email="pilot@example.invalid", username="crm_pilot", password_hash="unused-test-only",
            ))
            db.session.commit()
        self.browser = self.app.test_client()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.temporary.cleanup()

    def request(self, path, method="GET", data=None, headers=None, environ=None, base_url=None):
        proxy_headers = {
            "Host": "invoicemakerai.com",
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Prefix": PREFIX,
        }
        if method not in {"GET", "HEAD", "OPTIONS"}:
            proxy_headers.update(Origin=ORIGIN, Referer=ORIGIN + PREFIX + "/login")
        proxy_headers.update(headers or {})
        for key in [key for key, value in proxy_headers.items() if value is None]:
            proxy_headers.pop(key)
        environment = {"REMOTE_ADDR": "127.0.0.1"}
        environment.update(environ or {})
        return self.browser.open(
            path, method=method, data=data, headers=proxy_headers,
            environ_overrides=environment, base_url=base_url or ORIGIN + PREFIX,
        )

    def csrf(self, path="/login"):
        response = self.request(path)
        self.assertEqual(response.status_code, 200)
        return Inputs(response.get_data(as_text=True)).values["csrf_token"]

    def login(self):
        return self.request("/login", method="POST", data={
            "csrf_token": self.csrf(), "access_code": CODE,
        })

    def counts(self):
        with self.app.app_context():
            return User.query.count(), Client.query.count()

    def receipt_fixture(self):
        with self.app.app_context():
            user = User.query.filter_by(email="pilot@example.invalid").one()
            now = datetime.now(timezone.utc)
            job = Job(user_id=user.id, title="Synthetic quota test", status="new",
                      created_at=now, updated_at=now)
            db.session.add(job)
            db.session.commit()
            job_id = job.id
        output = BytesIO()
        Image.new("RGB", (30, 20), "white").save(output, format="PNG")
        return job_id, output.getvalue()

    def upload(self, job_id, content):
        return self.request(f"/crm/jobs/{job_id}/receipts/upload", method="POST", data={
            "csrf_token": self.csrf("/crm/clients"), "file": (BytesIO(content), "synthetic.png"),
        })

    def original_files(self):
        root = Path(self.app.config["CRM_RECEIPT_FOLDER"])
        return {path.relative_to(root).as_posix(): path.read_bytes()
                for path in root.rglob("*") if path.is_file()}

    def receipt_count(self):
        with self.app.app_context():
            return JobReceipt.query.count()

    def test_health_discloses_marker_without_creating_user(self):
        response = self.request("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json().get("app"), "invoicemaker-crm-pilot")
        self.assertEqual(self.counts(), (1, 0))

    def test_login_get_does_not_automatically_create_or_authenticate_user(self):
        self.assertEqual(self.request("/login").status_code, 200)
        response = self.request("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn(PREFIX + "/login", response.headers["Location"])
        self.assertEqual(self.counts(), (1, 0))

    def test_all_private_reads_redirect_before_accessing_records(self):
        for path in (
            "/crm/", "/crm/clients", "/crm/progress", "/crm/jobs/1",
            "/crm/receipts/test-id", "/crm/receipts/test-id/original",
            "/static/crm/vendor/ocr/worker.min.js", "/static/crm/receipt-ui.js",
            "/static/crm/job-notes.js",
        ):
            with self.subTest(path=path):
                response = self.request(path)
                self.assertEqual(response.status_code, 302)
                self.assertIn(PREFIX + "/login", response.headers["Location"])
        self.assertEqual(self.counts(), (1, 0))

    def test_only_login_stylesheet_and_favicon_are_public(self):
        for path in ("/static/crm/crm.css", "/static/crm/favicon.svg"):
            with self.subTest(path=path):
                response = self.request(path)
                try:
                    self.assertEqual(response.status_code, 200)
                finally:
                    response.close()

    def test_unauthenticated_write_with_valid_csrf_does_not_change_data(self):
        token = self.csrf()
        response = self.request("/crm/clients", method="POST", data={
            "csrf_token": token, "name": "Blocked synthetic client",
        })
        self.assertIn(response.status_code, {302, 401})
        self.assertEqual(self.counts(), (1, 0))

    def test_private_post_routes_block_before_parsing_files_or_records(self):
        for path in (
            "/crm/receipts/test-id", "/crm/receipts/test-id/original",
            "/crm/jobs/1/receipts/upload", "/crm/jobs/1/status",
            "/crm/jobs/1/notes", "/api/jobs",
        ):
            with self.subTest(path=path):
                response = self.request(path, method="POST", data={"untrusted": "synthetic"})
                self.assertEqual(response.status_code, 401)
        self.assertEqual(self.counts(), (1, 0))

    def test_wrong_access_code_does_not_create_user_or_session(self):
        response = self.request("/login", method="POST", data={
            "csrf_token": self.csrf(), "access_code": "wrong-test-code",
        })
        self.assertIn(response.status_code, {200, 401})
        self.assertEqual(self.counts(), (1, 0))
        self.assertEqual(self.request("/crm/").status_code, 302)

    def test_access_login_requires_csrf(self):
        response = self.request("/login", method="POST", data={"access_code": CODE})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.counts(), (1, 0))

    def test_exact_origin_is_required_even_with_valid_csrf_and_code(self):
        token = self.csrf()
        for origin in (None, "https://foreign.example", "http://invoicemakerai.com", ORIGIN + ".foreign.example"):
            with self.subTest(origin=origin):
                response = self.request("/login", method="POST", data={
                    "csrf_token": token, "access_code": CODE,
                }, headers={"Origin": origin})
                self.assertEqual(response.status_code, 403)
        self.assertEqual(self.counts(), (1, 0))

    def test_host_scheme_and_prefix_are_exactly_allowlisted(self):
        cases = (
            {"Host": "foreign.example"},
            {"Host": "invoicemakerai.com.foreign.example"},
            {"Host": "localhost:5180"},
            {"X-Forwarded-Proto": "http"},
            {"X-Forwarded-Proto": None},
            {"X-Forwarded-Prefix": "/other"},
            {"X-Forwarded-Prefix": None},
            {"X-Forwarded-Prefix": PREFIX + "/../other"},
        )
        for headers in cases:
            with self.subTest(headers=headers):
                response = self.request(
                    "/login", headers=headers, base_url="http://invoicemakerai.com" + PREFIX,
                    # Nginx strips the URL prefix; only its trusted header adds SCRIPT_NAME.
                    environ={"SCRIPT_NAME": ""},
                )
                self.assertEqual(response.status_code, 403)
        self.assertEqual(self.counts(), (1, 0))

    def test_forwarded_headers_cannot_spoof_nonloopback_peer_or_allowed_host(self):
        response = self.request("/login", environ={"REMOTE_ADDR": "192.0.2.15"}, headers={
            "X-Forwarded-For": "127.0.0.1", "X-Forwarded-Host": "invoicemakerai.com",
        })
        self.assertEqual(response.status_code, 403)
        response = self.request("/login", headers={
            "Host": "foreign.example", "X-Forwarded-Host": "invoicemakerai.com",
        })
        self.assertEqual(response.status_code, 403)

    def test_valid_login_uses_only_synthetic_user_and_secure_prefixed_cookie(self):
        response = self.login()
        self.assertEqual(response.status_code, 302)
        self.assertIn(PREFIX + "/crm/", response.headers["Location"])
        cookie = response.headers["Set-Cookie"]
        for flag in ("crm_pilot_session=", "Secure", "HttpOnly", "SameSite=Lax", "Path=" + PREFIX):
            self.assertIn(flag, cookie)
        self.assertIn("Expires=", cookie)
        self.assertEqual(self.request("/crm/").status_code, 200)
        with self.app.app_context():
            self.assertEqual(User.query.count(), 1)
            self.assertEqual(User.query.one().email, "pilot@example.invalid")

    def test_flask_login_session_requires_pilot_authentication_marker(self):
        self.assertEqual(self.login().status_code, 302)
        with self.browser.session_transaction(base_url=ORIGIN + PREFIX) as session:
            self.assertIn("_user_id", session)
            session.pop("pilot_auth_version")
        response = self.request("/crm/")
        self.assertEqual(response.status_code, 302)
        self.assertIn(PREFIX + "/login", response.headers["Location"])

    def test_authenticated_client_creation_requires_csrf_and_origin(self):
        self.assertEqual(self.login().status_code, 302)
        response = self.request("/crm/clients", method="POST", data={"name": "Missing CSRF"})
        self.assertEqual(response.status_code, 400)
        token = self.csrf("/crm/clients")
        response = self.request("/crm/clients", method="POST", data={
            "csrf_token": token, "name": "Wrong Origin",
        }, headers={"Origin": "https://foreign.example"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.counts(), (1, 0))
        response = self.request("/crm/clients", method="POST", data={
            "csrf_token": token, "name": "Synthetic Mobile Client", "phone": "0900123456",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn(PREFIX + "/crm/jobs/create", response.headers["Location"])
        self.assertEqual(self.counts(), (1, 1))

    def test_logout_is_post_only_csrf_protected_and_clears_authentication(self):
        self.assertEqual(self.login().status_code, 302)
        self.assertEqual(self.request("/logout").status_code, 405)
        self.assertEqual(self.request("/logout", method="POST").status_code, 400)
        self.assertEqual(self.request("/crm/").status_code, 200)
        response = self.request("/logout", method="POST", data={"csrf_token": self.csrf("/crm/clients")})
        self.assertEqual(response.status_code, 302)
        self.assertIn(PREFIX + "/login", response.headers["Location"])
        self.assertEqual(self.request("/crm/").status_code, 302)

    def test_invalid_attempt_limit_is_global_across_browser_sessions(self):
        for number in range(20):
            # A cookie reset cannot bypass the process-wide attempt limit.
            self.browser = self.app.test_client()
            response = self.request("/login", method="POST", data={
                "csrf_token": self.csrf(), "access_code": "wrong-test-code",
            })
            self.assertNotEqual(response.status_code, 429, msg=f"Attempt {number + 1}")
        self.browser = self.app.test_client()
        response = self.request("/login", method="POST", data={
            "csrf_token": self.csrf(), "access_code": CODE,
        })
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["Retry-After"], "60")
        self.assertEqual(self.counts(), (1, 0))

    def test_attempt_limit_expires_after_one_minute(self):
        token = self.csrf()
        with patch("crm_pilot.time.monotonic", return_value=100):
            for _ in range(20):
                self.assertEqual(self.request("/login", method="POST", data={
                    "csrf_token": token, "access_code": "wrong-test-code",
                }).status_code, 401)
            self.assertEqual(self.request("/login", method="POST", data={
                "csrf_token": token, "access_code": CODE,
            }).status_code, 429)
        with patch("crm_pilot.time.monotonic", return_value=161):
            self.assertEqual(self.request("/login", method="POST", data={
                "csrf_token": token, "access_code": CODE,
            }).status_code, 302)

    def test_storage_quota_counts_orphans_and_rejects_upload_without_new_data(self):
        self.assertEqual(self.login().status_code, 302)
        job_id, image = self.receipt_fixture()
        root = Path(self.app.config["CRM_RECEIPT_FOLDER"])
        root.mkdir(parents=True)
        (root / "orphan-object").write_bytes(b"preserved")
        before = self.original_files()
        # The image alone fits; the unreferenced original must still count.
        self.app.config["CRM_RECEIPT_MAX_BYTES"] = len(image)
        response = self.upload(job_id, image)
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"{PREFIX}/crm/jobs/{job_id}", response.headers["Location"])
        self.assertEqual(self.receipt_count(), 0)
        self.assertEqual(self.original_files(), before)

    def test_duplicate_receipt_opens_existing_record_even_when_quota_exhausted(self):
        self.assertEqual(self.login().status_code, 302)
        job_id, image = self.receipt_fixture()
        self.app.config["CRM_RECEIPT_MAX_BYTES"] = 1024 * 1024
        with patch("crm.receipts.shutil.disk_usage", return_value=SimpleNamespace(free=1024 ** 3)):
            first = self.upload(job_id, image)
        self.assertEqual(first.status_code, 302)
        self.assertIn(f"{PREFIX}/crm/receipts/", first.headers["Location"])
        before = self.original_files()
        self.app.config["CRM_RECEIPT_MAX_BYTES"] = 0
        with patch("crm.routes.ensure_storage_capacity", side_effect=AssertionError("Duplicate checked quota")):
            repeated = self.upload(job_id, image)
        self.assertEqual(repeated.status_code, 302)
        self.assertEqual(repeated.headers["Location"], first.headers["Location"])
        self.assertEqual(self.receipt_count(), 1)
        self.assertEqual(self.original_files(), before)

    def test_low_free_disk_rejects_upload_without_draft_or_original(self):
        self.assertEqual(self.login().status_code, 302)
        job_id, image = self.receipt_fixture()
        self.app.config["CRM_RECEIPT_MAX_BYTES"] = 1024 * 1024
        almost_enough = len(image) + 256 * 1024 * 1024 - 1
        with patch("crm.receipts.shutil.disk_usage", return_value=SimpleNamespace(free=almost_enough)):
            response = self.upload(job_id, image)
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"{PREFIX}/crm/jobs/{job_id}", response.headers["Location"])
        self.assertEqual(self.receipt_count(), 0)
        self.assertEqual(self.original_files(), {})


if __name__ == "__main__":
    unittest.main()
