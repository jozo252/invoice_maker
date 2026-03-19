# adapters/normalize_ai.py
from decimal import Decimal, ROUND_HALF_UP
from datetime import date

def _r2(x) -> float:
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def parse_decimal(value, default="0"):
    if value is None or value == "":
        return Decimal(default)
    s = str(value).replace("\u00a0", "").replace(" ", "").replace(",", ".").replace("%", "")
    return Decimal(s)

def normalize_ai_payload(
    ai_raw: dict,
    *,
    user_id: int,
    client_id: int | None,
    company_id: int,
    invoice_number: str,
    default_unit: str = "ks",
    default_currency: str = "EUR",
    default_vat: float = 0.0,
    default_payment_method: str = "bank_transfer",
    default_status: str = "unpaid",
):
    items = []
    warnings = []

    allowed_payment_methods = {"bank_transfer", "cash", "card", "other"}

    for idx, it in enumerate(ai_raw.get("items", []) or []):
        name = it.get("name")
        if name is None:
            name = it.get("description")
        if name is None:
            name = ""

        qty = it.get("qty")
        if qty is None:
            qty = it.get("quantity")
        if qty is None:
            qty = 1

        unit_price = it.get("unit_price")
        if unit_price is None:
            unit_price = it.get("price_per_item")
        if unit_price is None:
            unit_price = 0

        unit = it.get("unit") or default_unit

        try:
            q = parse_decimal(qty, "1")
            p = parse_decimal(unit_price, "0")
        except Exception:
            warnings.append(f"Item {idx + 1}: invalid quantity or price")
            q = Decimal("1")
            p = Decimal("0")

        total = (p * q).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        items.append({
            "description": name,
            "quantity": float(q),
            "unit": unit,
            "price_per_item": float(p.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "total_cost": float(total),
        })

    try:
        vat_rate = float(parse_decimal(ai_raw.get("vat_rate"), str(default_vat)))
    except Exception:
        vat_rate = default_vat
        warnings.append("Invalid vat_rate, default used")

    payment_method = ai_raw.get("payment_method") or default_payment_method
    if payment_method not in allowed_payment_methods:
        warnings.append("Invalid payment_method, default used")
        payment_method = default_payment_method

    payload = {
        "invoice_number": (invoice_number or "").strip().upper(),
        "inv_date": ai_raw.get("issue_date") or ai_raw.get("date") or "",
        "due_date": ai_raw.get("due_date") or "",
        "user_id": user_id,
        "currency": (ai_raw.get("currency") or default_currency).upper(),
        "vat_rate": vat_rate,
        "client_id": client_id,
        "company_id": company_id,
        "payment_method": payment_method,
        "status": ai_raw.get("status") or default_status,
        "items": items,
        "warnings": warnings,
    }
    return payload