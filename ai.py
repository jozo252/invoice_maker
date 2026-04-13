from openai import OpenAI
import json
import os
from dotenv import load_dotenv
from decimal import Decimal, ROUND_HALF_UP
from extensions import db
from models import Invoice, InvoiceItem, InvoiceStatus, PaymentMethod
from pydantic_models import InvoiceModel, OfferAI, OfferAIItem
from datetime import datetime
load_dotenv()  # load .env file if present


SYSTEM = (
    "You are an invoice data extraction assistant. "
    "Read the user's unstructured text and extract invoice data. "
    "Return ONLY a valid JSON object with exactly these keys:\n"
    "- customer_name: string or null\n"
    "- customer_email: string or null\n"
    "- customer_ico: string or null\n"
    "- customer_dic: string or null\n"
    "- issue_date: string in format YYYY-MM-DD or null\n"
    "- due_date: string in format YYYY-MM-DD or null\n"
    "- due_in_days: integer or null\n"
    "- currency: 3-letter code (EUR, USD, CZK, PLN, etc.) or null\n"
    "- vat_rate: number or null\n"
    "- payment_method: one of [bank_transfer, cash, card, other] or null\n"
    "- status: one of [unpaid, paid] or null\n"
    "- items: list of objects with {name, qty, unit, unit_price}\n"
    "  where name is string, qty is number or null, unit is string or null, unit_price is number or null\n"
    "- notes: string or null\n"
    "- missing_fields: list of strings\n"
    "- warnings: list of strings\n\n"
    "Rules:\n"
    "- Return valid JSON only. No markdown. No explanations.\n"
    "- Do not invent missing values.\n"
    "- If a field is not clearly present in the text, set it to null.\n"
    "- If no invoice items are clearly present, return an empty items list.\n"
    "- Do not calculate totals.\n"
    "- Do not guess customer email, dates, VAT, or payment method.\n"
    "- If due terms are relative (e.g. '7 days'), use due_in_days.\n"
    "- Add unclear or ambiguous extractions to warnings.\n"
    "- Add required missing business fields to missing_fields.\n"
    "- Return values in input language(days,dni,tags)\n"
)
OFFER_SYSTEM = (
    "You are an offer data extraction assistant for trade and construction work. "
    "Read the user's unstructured text and extract data for a price offer / quotation. "
    "Return ONLY a valid JSON object with exactly these keys:\n"
    "- customer_name: string or null\n"
    "- customer_email: string or null\n"
    "- currency: 3-letter code (EUR, USD, CZK, PLN, etc.) or null\n"
    "- items: list of objects with {name, qty, unit, unit_price}\n"
    "  where name is string, qty is number or null, unit is string or null, unit_price is number or null\n"
    "- notes: string or null\n"
    "- missing_fields: list of strings\n"
    "- warnings: list of strings\n\n"
    "Rules:\n"
    "- Return valid JSON only. No markdown. No explanations.\n"
    "- Do not invent missing values.\n"
    "- If a field is not clearly present in the text, set it to null.\n"
    "- If no offer items are clearly present, return an empty items list.\n"
    "- Each item should represent one material, service, or work task.\n"
    "- qty must be a number or null.\n"
    "- unit must be a short unit string like ks, hod, m, m2, m3, day, set, or null.\n"
    "- unit_price must be a number or null.\n"
    "- Do not calculate subtotal, VAT, discount, or total.\n"
    "- Do not guess customer email or currency.\n"
    "- If quantity or unit price is unclear, set it to null and mention ambiguity in warnings.\n"
    "- missing_fields may include only fields that can be extracted from the user's text.\n"
    "- Add important ambiguities to warnings.\n"
    "- Return values in input language(days,dni,tags)\n"
)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
def call_llm_extract(user_text: str) -> dict:
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

def transcribe_ai(temp_path):
    with open(temp_path, "rb") as f:
        transcript = client.audio.transcriptions.create(
            model="gpt-4o-transcribe",
            file=f
        )

    text = getattr(transcript, "text", None) or ""
    print(text)
    return text

    
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
        variable_symbol=inv.variable_symbol,
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


def call_llm_extract_offer(user_text: str) -> dict:
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": OFFER_SYSTEM},
            {"role": "user", "content": user_text},
        ],
        temperature=0,
    )

    content = response.choices[0].message.content
    print(f"result from ai:{content}")
    return json.loads(content)

