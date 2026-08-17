from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import joinedload

from models import Invoice, InvoiceStatus

CENT = Decimal("0.01")


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(CENT, rounding=ROUND_HALF_UP)


def _amount_due(invoice: Invoice) -> Decimal:
    subtotal = _money(invoice.total_cost)
    if not invoice.company or not invoice.company.is_vat_payer:
        return subtotal

    vat_rate = Decimal(str(invoice.vat_rate or 0)) / Decimal(100)
    return (subtotal * (Decimal(1) + vat_rate)).quantize(CENT, rounding=ROUND_HALF_UP)


def overdue_invoice_summary(user_id: int, *, as_of: date | None = None) -> dict:
    today = as_of or datetime.now(UTC).date()
    invoices = (
        Invoice.query.options(joinedload(Invoice.client), joinedload(Invoice.company))
        .filter(
            Invoice.user_id == user_id,
            Invoice.status == InvoiceStatus.unpaid,
            Invoice.due_date < today,
        )
        .order_by(Invoice.due_date.asc(), Invoice.id.asc())
        .all()
    )

    totals: dict[str, Decimal] = {}
    serialized = []
    for invoice in invoices:
        currency = (invoice.currency or "EUR").upper()
        amount = _amount_due(invoice)
        totals[currency] = totals.get(currency, Decimal("0.00")) + amount
        serialized.append(
            {
                "id": invoice.id,
                "invoice_number": invoice.invoice_number,
                "client_name": invoice.client.name if invoice.client else None,
                "amount": f"{amount:.2f}",
                "currency": currency,
                "due_date": invoice.due_date.isoformat(),
                "days_overdue": (today - invoice.due_date).days,
            }
        )

    return {
        "as_of": today.isoformat(),
        "count": len(serialized),
        "totals_by_currency": {
            currency: f"{amount.quantize(CENT, rounding=ROUND_HALF_UP):.2f}"
            for currency, amount in sorted(totals.items())
        },
        "invoices": serialized,
    }
