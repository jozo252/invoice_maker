# adapters/normalize_ai.py
from decimal import Decimal, ROUND_HALF_UP
from datetime import date

def _r2(x) -> float:
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

def normalize_ai_payload(
    ai_raw: dict,
    *,
    user_id: int,
    client_id: int,
    company_id: int,
    invoice_number: str,
    default_unit: str = "ks",
    default_currency: str = "EUR",
    default_vat: float = 0.0,
    default_payment_method: str = "bank_transfer",
    default_status: str = "unpaid",
):
    items = []
    for it in ai_raw.get("items", []) or []:
        name = it.get("name") or it.get("description") or ""
        qty = it.get("qty") or it.get("quantity") or 1
        unit_price = it.get("unit_price") or it.get("price_per_item") or 0
        unit = it.get("unit") or default_unit
        try:
            q = int(Decimal(str(qty)))
            p = Decimal(str(unit_price).replace("\u00a0","").replace(" ","").replace(",","."))
        except Exception:
            q, p = 1, Decimal("0")
        total = _r2(p * q)
        items.append({
            "description": name,
            "quantity": q,
            "unit": unit,
            "price_per_item": float(p.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            "total_cost": total
        })

    payload = {
        "invoice_number": (invoice_number or "").strip().upper(),
        "inv_date": ai_raw.get("issue_date") or ai_raw.get("date") or "",
        "due_date": ai_raw.get("due_date") or "",
        "user_id": user_id,
        "currency": (ai_raw.get("currency") or default_currency).upper(),
        "vat_rate": float(ai_raw.get("vat_rate") or default_vat),
        "client_id": client_id,
        "company_id": company_id,
        "payment_method": (ai_raw.get("payment_method") or default_payment_method),
        "status": (ai_raw.get("status") or default_status),
        "items": items,
        # voliteľne si môžeš preniesť poznámku, ak ju máš v InvoiceModel
        # "notes": ai_raw.get("notes")
    }
    return payload
