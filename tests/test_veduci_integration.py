from datetime import UTC, date, datetime, timedelta

import pytest
from flask import Flask

from extensions import db
from integrations.routes import integrations_bp
from models import Client, Company, Invoice, InvoiceStatus, User

TOKEN = "test-token-with-more-than-thirty-two-characters"


@pytest.fixture
def app():
    test_app = Flask(__name__)
    test_app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite+pysqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        VEDUCI_INTEGRATION_TOKEN=TOKEN,
        VEDUCI_INTEGRATION_USER_ID=1,
    )
    db.init_app(test_app)
    test_app.register_blueprint(integrations_bp)

    with test_app.app_context():
        db.create_all()
        yield test_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _user(*, email: str, username: str) -> User:
    return User(email=email, username=username, password_hash="not-used-in-this-test")


def _company(user: User, *, vat_payer: bool) -> Company:
    return Company(
        user=user,
        name=f"Company {user.username}",
        ico="12345678",
        dic="1234567890",
        street="Test 1",
        city="Bratislava",
        zip_code="81101",
        country="Slovensko",
        email=f"company-{user.email}",
        phone="+421900000000",
        iban="SK0000000000000000000000",
        bic="TESTSKBX",
        is_vat_payer=vat_payer,
    )


def _invoice(
    *,
    user: User,
    company: Company,
    client: Client,
    number: str,
    due_date: date,
    total: float,
    currency: str = "EUR",
    status: InvoiceStatus = InvoiceStatus.unpaid,
    vat_rate: float = 0,
) -> Invoice:
    return Invoice(
        invoice_number=number,
        date=due_date - timedelta(days=14),
        due_date=due_date,
        user=user,
        company=company,
        client=client,
        currency=currency,
        total_cost=total,
        vat_rate=vat_rate,
        status=status,
    )


@pytest.fixture
def invoice_data(app):
    with app.app_context():
        owner = _user(email="owner@example.com", username="owner")
        other = _user(email="other@example.com", username="other")
        db.session.add_all([owner, other])
        db.session.flush()

        owner_company = _company(owner, vat_payer=True)
        other_company = _company(other, vat_payer=False)
        owner_client = Client(name="Owner Client", user=owner)
        other_client = Client(name="Other Client", user=other)
        db.session.add_all([owner_company, other_company, owner_client, other_client])
        db.session.flush()

        today = datetime.now(UTC).date()
        db.session.add_all(
            [
                _invoice(
                    user=owner,
                    company=owner_company,
                    client=owner_client,
                    number="2026-001",
                    due_date=today - timedelta(days=5),
                    total=1000,
                    vat_rate=23,
                ),
                _invoice(
                    user=owner,
                    company=owner_company,
                    client=owner_client,
                    number="2026-002",
                    due_date=today - timedelta(days=2),
                    total=10,
                    currency="usd",
                    vat_rate=23,
                ),
                _invoice(
                    user=owner,
                    company=owner_company,
                    client=owner_client,
                    number="2026-003",
                    due_date=today + timedelta(days=2),
                    total=300,
                ),
                _invoice(
                    user=owner,
                    company=owner_company,
                    client=owner_client,
                    number="2026-004",
                    due_date=today - timedelta(days=10),
                    total=400,
                    status=InvoiceStatus.paid,
                ),
                _invoice(
                    user=other,
                    company=other_company,
                    client=other_client,
                    number="2026-005",
                    due_date=today - timedelta(days=7),
                    total=500,
                ),
            ]
        )
        db.session.commit()


def _headers(token: str = TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Basic abc"},
        _headers("wrong-token-with-more-than-thirty-two-characters"),
    ],
)
def test_endpoint_rejects_missing_or_invalid_bearer_token(client, headers):
    response = client.get(
        "/api/v1/integrations/veduci/invoices/overdue", headers=headers
    )

    assert response.status_code == 401
    assert response.json == {"error": "unauthorized"}
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.headers["Cache-Control"] == "no-store"


def test_endpoint_returns_only_configured_users_overdue_invoices(
    client,
    invoice_data,
):
    response = client.get(
        "/api/v1/integrations/veduci/invoices/overdue",
        headers=_headers(),
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json["count"] == 2
    assert response.json["totals_by_currency"] == {
        "EUR": "1230.00",
        "USD": "12.30",
    }
    assert [item["invoice_number"] for item in response.json["invoices"]] == [
        "2026-001",
        "2026-002",
    ]
    assert response.json["invoices"][0]["days_overdue"] == 5
    assert response.json["invoices"][0]["amount"] == "1230.00"
    assert response.json["invoices"][0]["client_name"] == "Owner Client"
    assert "client_email" not in response.json["invoices"][0]


def test_endpoint_fails_closed_when_integration_is_not_configured(app, client):
    app.config["VEDUCI_INTEGRATION_TOKEN"] = None
    app.config["VEDUCI_INTEGRATION_USER_ID"] = None

    response = client.get("/api/v1/integrations/veduci/invoices/overdue")

    assert response.status_code == 503
    assert response.json == {"error": "integration_not_configured"}


def test_endpoint_fails_closed_for_missing_configured_user(app, client):
    app.config["VEDUCI_INTEGRATION_USER_ID"] = 999

    response = client.get(
        "/api/v1/integrations/veduci/invoices/overdue",
        headers=_headers(),
    )

    assert response.status_code == 503
    assert response.json == {"error": "integration_user_not_found"}
