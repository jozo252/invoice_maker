from datetime import datetime,timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_file,
)
from flask_login import login_required, current_user
from ai import call_llm_extract_offer
from app import db
from models import Lead, Offer, Invoice,Company
import json
from pydantic import ValidationError
from pydantic_models import OfferAI, OfferAIItem
from pdf_generator import render_invoice_to_pdf

offers = Blueprint("offers", __name__, url_prefix="/offers")

#____________________________________________HELPERS__________________________
def generate_invoice_number():
    last_invoice = Invoice.query.filter_by(user_id=current_user.id).order_by(Invoice.id.desc()).first()
    new_number = (int(last_invoice.invoice_number.split("-")[-1]) + 1) if last_invoice else 1
    return f"INV-{datetime.now().year}-{new_number:04d}"
def to_decimal(value, default="0.00"):
    try:
        if value is None or value == "":
            return Decimal(default)
        return Decimal(str(value).replace(",", ".").strip())
    except (InvalidOperation, ValueError):
        return Decimal(default)

def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def normalize_offer_items(items: list[dict]) -> tuple[list[dict], Decimal]:
    normalized_items = []
    subtotal = Decimal("0.00")

    for item in items:
        name = (item.get("name") or "").strip()
        if not name:
            continue

        qty_raw = item.get("qty")
        unit_raw = item.get("unit")
        unit_price_raw = item.get("unit_price")

        qty = to_decimal(qty_raw, default="1.00") if qty_raw is not None else Decimal("1.00")
        unit_price = to_decimal(unit_price_raw, default="0.00") if unit_price_raw is not None else Decimal("0.00")

        line_total = money(qty * unit_price)
        subtotal += line_total

        normalized_items.append({
            "description": name,
            "quantity": float(qty),
            "unit": (unit_raw.strip() if isinstance(unit_raw, str) and unit_raw.strip() else None),
            "price_per_item": float(money(unit_price)),
            "total_cost": float(line_total),
        })

    subtotal = money(subtotal)
    return normalized_items, subtotal

def calculate_totals(items, discount_total=Decimal("0.00")):
    subtotal = Decimal("0.00")

    for item in items:
        qty = to_decimal(item.get("quantity", 0))
        unit_price = to_decimal(item.get("unit_price", 0))

        if qty < 0:
            qty = Decimal("0.00")
        if unit_price < 0:
            unit_price = Decimal("0.00")

        subtotal += qty * unit_price

    if discount_total < 0:
        discount_total = abs(discount_total)

    total = subtotal - discount_total
    if total < 0:
        total = Decimal("0.00")

    return subtotal.quantize(Decimal("0.01")), total.quantize(Decimal("0.01"))


def normalize_items_from_form():
    item_names = request.form.getlist("item_name[]")
    item_quantities = request.form.getlist("item_quantity[]")
    item_unit_prices = request.form.getlist("item_unit_price[]")

    items = []

    for name, qty, price in zip(item_names, item_quantities, item_unit_prices):
        name = (name or "").strip()
        if not name:
            continue

        qty_dec = to_decimal(qty, "1.00")
        price_dec = to_decimal(price, "0.00")

        if qty_dec < 0:
            qty_dec = Decimal("0.00")
        if price_dec < 0:
            price_dec = Decimal("0.00")

        items.append({
            "description": name,
            "quantity": float(qty_dec),
            "price_per_item": float(price_dec),
        })
    print(f"items from func {items}")
    return items

def generate_offer_from_text(user_text: str, company_id: int, user_id: int) -> dict:
    ai_raw = call_llm_extract_offer(user_text)

    try:
        ai_obj = OfferAI.model_validate(ai_raw)
    except ValidationError as e:
        return {
            "ok": False,
            "errors": e.errors(),
            "raw": ai_raw,
        }

    normalized_items, subtotal = normalize_offer_items(
        [item.model_dump() for item in ai_obj.items]
    )

    discount_total = Decimal("0.00")
    total = subtotal - discount_total
    total = money(total)

    db_ready = {
        "user_id": user_id,
        "company_id": company_id,
        "currency": ai_obj.currency or "EUR",
        "customer_name": ai_obj.customer_name,
        "customer_email": ai_obj.customer_email,
        "items": normalized_items,
        "notes": ai_obj.notes,
        "subtotal": subtotal,
        "discount_total": discount_total,
        "total": total,
        "status": "draft",
        "warnings": ai_obj.warnings,
        "missing_fields": ai_obj.missing_fields,
    }

    return {
        "ok": True,
        "data": db_ready,
    }
def save_offer_from_generated_data(db_ready: dict) -> Offer:
    offer = Offer(
        user_id=db_ready["user_id"],
        company_id=db_ready["company_id"],
        currency=db_ready["currency"],
        customer_name=db_ready["customer_name"],
        customer_email=db_ready["customer_email"],
        items=db_ready["items"],
        notes=db_ready["notes"],
        subtotal=db_ready["subtotal"],
        discount_total=db_ready["discount_total"],
        total=db_ready["total"],
        status=db_ready["status"],
    )

    db.session.add(offer)
    db.session.commit()
    return offer
def build_preview_data_from_offer(offer, user_id):
    today_date = datetime.utcnow().date()
    due_date = today_date + timedelta(days=14)
    

    client_data = {
        "name": offer.customer_name or "",
        "email": offer.customer_email or "",
        "ico": getattr(offer, "customer_ico", "") or "",
        "dic": getattr(offer, "customer_dic", "") or "",
        "street": getattr(offer, "customer_street", "") or "",
        "city": getattr(offer, "customer_city", "") or "",
        "zip_code": getattr(offer, "customer_zip_code", "") or "",
        "country": getattr(offer, "customer_country", "") or "",
        "phone": getattr(offer, "customer_phone", "") or "",
        "iban": getattr(offer, "customer_iban", "") or "",
        "bic": getattr(offer, "customer_bic", "") or "",
        "ic_dph": getattr(offer, "customer_ic_dph", "") or "",
    }

    db_json = {
        "invoice_number": generate_invoice_number(),
        "user_id": user_id,
        "client_id": getattr(offer, "client_id", None),
        "company_id": offer.company_id,
        "inv_date": today_date.isoformat(),
        "due_date": due_date.isoformat(),
        "currency": offer.currency or "EUR",
        #"notes": offer.notes or "",
        "items": offer.items or [],
        "status": "unpaid",
        "payment_method": getattr(offer, "payment_method", "bank_transfer"),
    }

    return db_json, client_data

@offers.route("/")
@login_required
def offers_list():
    offers_list = (
        Offer.query
        .filter_by(user_id=current_user.id)
        .order_by(Offer.created_at.desc())
        .all()
    )
    return render_template("offers_list.html", offers=offers_list)


@offers.route("/leads/new")
@login_required
def new_lead():
    return render_template("new_lead.html")


@offers.route("/leads/create", methods=["POST"])
@login_required
def create_lead():
    name = (request.form.get("name") or "").strip()
    customer_name = (request.form.get("customer_name") or "").strip()
    customer_email = (request.form.get("customer_email") or "").strip()
    description = (request.form.get("description") or "").strip()

    if not description:
        flash("Popis dopytu je povinný.", "danger")
        return render_template("new_lead.html")

    lead = Lead(
        user_id=current_user.id,
        name=name or "Bez názvu",
        description=description,
        customer_name=customer_name or None,
        customer_email=customer_email or None,
        status="new",
        created_at=datetime.utcnow(),
    )

    db.session.add(lead)
    db.session.commit()

    return redirect(url_for("offers.generate_offer_from_lead", lead_id=lead.id))

@offers.route("/generate-from-text", methods=["POST"])
@login_required
def generate_offer_from_text_route():
    user_text = (request.form.get("user_input") or "").strip()
    company_id = request.form.get("company_id", type=int)

    if not user_text:
        flash("Vlož text pre AI.", "warning")
        return redirect(url_for("offers.new_offer"))

    if not company_id:
        flash("Vyber firmu.", "warning")
        return redirect(url_for("offers.new_offer"))

    result = generate_offer_from_text(
        user_text=user_text,
        company_id=company_id,
        user_id=current_user.id,
    )

    if not result["ok"]:
        flash("AI výstup sa nepodarilo spracovať.", "danger")
        return render_template(
            "offers/new_offer.html",
            ai_errors=result.get("errors"),
            ai_raw=result.get("raw"),
        )

    db_ready = result["data"]

    if not db_ready["items"]:
        flash("AI nenašla žiadne položky pre ponuku.", "warning")
        return render_template(
            "offers/new_offer.html",
            draft_offer=db_ready,
        )

    offer = save_offer_from_generated_data(db_ready)

    warnings = db_ready.get("warnings") or []
    if warnings:
        flash("Pozor: " + " | ".join(warnings), "warning")

    flash("Ponuka bola vytvorená.", "success")
    return redirect(url_for("offers.edit_offer", offer_id=offer.id))

@offers.route("/from-lead/<int:lead_id>", methods=["GET", "POST"])
@login_required
def generate_offer_from_lead(lead_id):
    lead = Lead.query.filter_by(id=lead_id, user_id=current_user.id).first_or_404()
    company = Company.query.filter_by(user_id=current_user.id).first()

    if not company:
        flash("Najprv si vytvor firmu.", "warning")
        return redirect(url_for("companies.add_company"))

    existing_offer = (
        Offer.query
        .filter_by(user_id=current_user.id, lead_id=lead.id)
        .order_by(Offer.created_at.desc())
        .first()
    )
    if existing_offer:
        return redirect(url_for("offers.edit_offer", offer_id=existing_offer.id))

    result = generate_offer_from_text(
        user_text=lead.description or "",
        company_id=company.id,
        user_id=current_user.id
    )

    if not result.get("ok"):
        flash("AI výstup sa nepodarilo spracovať.", "danger")
        return redirect(url_for("leads.edit_lead", lead_id=lead.id))

    ai_data = result["data"]

    items = ai_data.get("items") or []
    notes = ai_data.get("notes") or lead.description
    customer_name = ai_data.get("customer_name") or lead.customer_name
    customer_email = ai_data.get("customer_email") or lead.customer_email
    currency = ai_data.get("currency") or "EUR"

    discount_total = ai_data.get("discount_total", Decimal("0.00"))
    subtotal = ai_data.get("subtotal", Decimal("0.00"))
    total = ai_data.get("total", Decimal("0.00"))

    offer = Offer(
        user_id=current_user.id,
        lead_id=lead.id,
        customer_name=customer_name or None,
        customer_email=customer_email or None,
        company_id=company.id,
        currency=currency,
        items=items,
        notes=notes,
        subtotal=subtotal,
        discount_total=discount_total,
        total=total,
        status="draft",
        created_at=datetime.utcnow(),
    )

    db.session.add(offer)

    lead.status = "quoted"

    db.session.commit()

    warnings = ai_data.get("warnings") or []
    if warnings:
        flash("Pozor: " + " | ".join(warnings), "warning")

    flash("Návrh ponuky bol vytvorený.", "success")
    return redirect(url_for("offers.edit_offer", offer_id=offer.id))


@offers.route("/<int:offer_id>/convert-to-invoice", methods=["POST"])
@login_required
def convert_offer_to_invoice(offer_id):
    offer = Offer.query.filter_by(id=offer_id, user_id=current_user.id).first_or_404()

    if not offer.items:
        flash("Ponuka nemá žiadne položky.", "danger")
        return redirect(url_for("offers.edit_offer", offer_id=offer.id))

    db_json, client_data = build_preview_data_from_offer(offer, current_user.id)

    return render_template(
        "invoice_preview.html",
        db_json=db_json,
        client_data=client_data,
        match_type="offer"
    )

    
@offers.route("/<int:offer_id>")
@login_required
def edit_offer(offer_id):
    offer = Offer.query.filter_by(id=offer_id, user_id=current_user.id).first_or_404()
    return render_template("offer_edit.html", offer=offer)


@offers.route("/<int:offer_id>/update", methods=["POST"])
@login_required
def update_offer(offer_id):
    offer = Offer.query.filter_by(id=offer_id, user_id=current_user.id).first_or_404()

    customer_name = (request.form.get("customer_name") or "").strip()
    customer_email = (request.form.get("customer_email") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    discount_total = to_decimal(request.form.get("discount_total"), "0.00")

    items = normalize_items_from_form()

    if not items:
        flash("Ponuka musí obsahovať aspoň jednu položku.", "danger")
        return render_template("offer_edit.html", offer=offer)

    subtotal, total = calculate_totals(items, discount_total)

    offer.customer_name = customer_name or None
    offer.customer_email = customer_email or None
    offer.notes = notes or None
    offer.items = items
    offer.discount_total = discount_total
    offer.subtotal = subtotal
    offer.total = total
    
    db.session.commit()

    flash("Ponuka bola uložená.", "success")
    return redirect(url_for("offers.edit_offer", offer_id=offer.id))


@offers.route("/<int:offer_id>/preview")
@login_required
def preview_offer(offer_id):
    offer = Offer.query.filter_by(id=offer_id, user_id=current_user.id).first_or_404()
    company = Company.query.filter_by(id=offer.company_id, user_id=current_user.id).first_or_404()

    return render_template(
        "offer_preview.html",
        offer_data=offer,
        company=company,
        stamp_data_uri=None,
    )
@offers.route("/<int:offer_id>/download")
@login_required
def download_offer(offer_id):
    offer = Offer.query.filter_by(id=offer_id, user_id=current_user.id).first_or_404()
    company = Company.query.filter_by(id=offer.company_id, user_id=current_user.id).first_or_404()

    context = {
        "offer": offer,
        "company": company,
        "stamp_data_uri": None,
    }
    print(offer.items)
    pdf_path = render_invoice_to_pdf("offer_pdf.html", context)
    return send_file(pdf_path, as_attachment=True, download_name=f"{offer.id}.pdf")

@offers.route("/save-from-preview", methods=["POST"])
@login_required
def save_offer_from_preview():
    company_id = request.form.get("company_id", type=int)

    if not company_id:
        flash("Chýba firma.", "danger")
        return redirect(url_for("offers.list_offers"))

    # --- BASIC FIELDS ---
    customer_name = (request.form.get("customer_name") or "").strip()
    customer_email = (request.form.get("customer_email") or "").strip()
    currency = request.form.get("currency") or "EUR"
    notes = (request.form.get("notes") or "").strip()

    # --- ITEMS ---
    names = request.form.getlist("item_name[]")
    qtys = request.form.getlist("item_qty[]")
    prices = request.form.getlist("item_unit_price[]")

    items = []
    subtotal = Decimal("0.00")

    for name, qty, price in zip(names, qtys, prices):
        name = (name or "").strip()
        if not name:
            continue

        try:
            qty_val = Decimal(str(qty).replace(",", "."))
        except:
            qty_val = Decimal("0.00")

        try:
            price_val = Decimal(str(price).replace(",", "."))
        except:
            price_val = Decimal("0.00")

        line_total = qty_val * price_val
        subtotal += line_total

        items.append({
            "description": name,
            "quantity": float(qty_val),
            "price_per_item": float(price_val),
        })

    discount_total = Decimal("0.00")
    total = subtotal - discount_total

    # --- CREATE OFFER ---
    offer = Offer(
        user_id=current_user.id,
        company_id=company_id,
        customer_name=customer_name or None,
        customer_email=customer_email or None,
        currency=currency,
        items=items,
        notes=notes,
        subtotal=subtotal,
        discount_total=discount_total,
        total=total,
        status="draft",
        created_at=datetime.utcnow(),
    )

    db.session.add(offer)
    db.session.commit()

    # --- ACTION LOGIC ---
    action = request.form.get("action")

    if action == "download":
        return redirect(url_for("offers.download_offer", offer_id=offer.id))

    flash("Ponuka bola uložená.", "success")
    return redirect(url_for("offers.edit_offer", offer_id=offer.id))
"""@offers.route("/<int:offer_id>/convert-to-invoice", methods=["POST"])
@login_required
def convert_offer_to_invoice(offer_id):
    offer = Offer.query.filter_by(id=offer_id, user_id=current_user.id).first_or_404()

    if not offer.items:
        flash("Ponuka nemá žiadne položky.", "danger")
        return redirect(url_for("offers.edit_offer", offer_id=offer.id))

    # Toto je iba jednoduchý MVP fallback.
    # Pravdepodobne si to napojíš na svoj existujúci Invoice model.
    today_date=datetime.utcnow().date()
    invoice = Invoice(
        invoice_number=generate_invoice_number(),    #-------------------------------------------
        user_id=current_user.id,
        customer_name=offer.customer_name or "Bez mena",
        customer_email=offer.customer_email,
        date=today_date,
        # ak máš due_date required, pridaj default
        due_date=today_date + timedelta(days=14),
        currency=offer.currency or "EUR", #------------- poriesit currency
        vat_rate=vat_rate, #---------------------vat rate
        items=offer.items,
        notes=offer.notes,
        #subtotal=offer.subtotal,
        client_id=offer.user_id,
        #discount_total=offer.discount_total or Decimal("0.00"),
        total_cost=offer.total,
        company_id=offer.company_id,
        status=InvoiceStatus.unpaid,
        created_at=datetime.utcnow(),
        payment_method=PaymentMethod(pm_raw),
    )

    db.session.add(invoice)

    offer.status = "accepted"

    if offer.lead_id:
        lead = Lead.query.filter_by(id=offer.lead_id, user_id=current_user.id).first()
        if lead:
            lead.status = "closed"

    db.session.commit()

    flash("Faktúra bola vytvorená z ponuky.", "success")

    # Uprav endpoint podľa tvojej invoice časti
    # napr. invoices.edit_invoice, main.invoice_detail, atď.
    return redirect(url_for("invoices.edit_invoice", invoice_id=invoice.id))"""
