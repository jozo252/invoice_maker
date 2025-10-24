from openai import OpenAI
import json
import os
from dotenv import load_dotenv
from decimal import Decimal, ROUND_HALF_UP
from extensions import db
from models import Invoice, InvoiceItem, InvoiceStatus, PaymentMethod
from pydantic_models import InvoiceModel
from datetime import datetime
load_dotenv()  # load .env file if present


SYSTEM = (
    "You are an invoice extraction assistant. "
    "Your task is to read unstructured user text and extract invoice data. "
    "Return ONLY a JSON object with these keys: \n"
    "- customer_name: string (required)\n"
    "- customer_email: string or null\n"
    "- issue_date: string in format YYYY-MM-DD or null\n"
    "- due_date: string in format YYYY-MM-DD or null\n"
    "- currency: 3-letter code (EUR, USD, CZK, PLN, etc.) or null\n"
    "- vat_rate: number (percentage, e.g., 20.0) or null\n"
    "- payment_method: one of [bank_transfer, cash, card] or null\n"
    "- status: one of [unpaid, paid] or null (do not use overdue/waiting)\n"
    "- items: list of objects with {name, qty, unit_price} "
    "  where qty is number, unit_price is number\n"
    "- notes: string or null\n"
    "- confidence: number between 0.0 and 1.0 estimating your extraction confidence\n\n"
    "Rules:\n"
    "- Always return valid JSON only, no explanations.\n"
    "- If a field is missing in the text, set it to null.\n"
    "- Ensure at least one item in the 'items' list.\n"
)


def call_llm_extract(user_text: str) -> dict:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        response_format={"type": "json_object"},  # force JSON
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_text},
        ],
        temperature=0.2,
    )
    raw = resp.choices[0].message.content
    print(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # extreme fallback
        return {"customer_name": "", "items": []}



def _round2(x: float) -> float:
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

def create_invoice_from_model(data: dict) -> int:
    inv = InvoiceModel.model_validate(data)

    if inv.due_date < inv.inv_date:
        raise ValueError("due_date must be >= inv_date")

    subtotal = 0.0
    fixed_items = []
    for it in inv.items:
        total = it.total_cost if it.total_cost is not None else it.quantity * it.price_per_item
        total = _round2(total)
        subtotal += total
        fixed_items.append(dict(
            description=it.description,
            quantity=it.quantity,
            unit=it.unit,
            price_per_item=_round2(it.price_per_item),
            total_cost=total
        ))

    vat_amount = _round2(subtotal * (inv.vat_rate / 100.0))
    grand_total = _round2(subtotal + vat_amount)
    #grand_total = _round2(subtotal)

    status = InvoiceStatus[inv.status] if inv.status in InvoiceStatus.__members__ else InvoiceStatus.unpaid
    paym = PaymentMethod[inv.payment_method] if inv.payment_method in PaymentMethod.__members__ else PaymentMethod.bank_transfer

    db_inv = Invoice(
        invoice_number=inv.invoice_number,
        date=inv.inv_date,
        due_date=inv.due_date,
        user_id=inv.user_id,
        currency=inv.currency,
        total_cost=grand_total,
        vat_rate=inv.vat_rate,
        client_id=inv.client_id,
        company_id=inv.company_id,
        payment_method=paym,
        status=status,
    )
    db.session.add(db_inv)
    db.session.flush()

    for it in fixed_items:
        db.session.add(InvoiceItem(invoice_id=db_inv.id, **it))

    db.session.commit()
    return db_inv.id
