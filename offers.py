import base64
from datetime import datetime,timedelta,date
from email.utils import parsedate_to_datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import mimetypes
import os
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_file,
    current_app,
)
from flask_login import login_required, current_user
from flask_mail import Message
from matplotlib.pylab import rint
from ai import call_llm_extract_offer, call_llm_generate_offer_description
from app import db
from models import Job, Lead, Offer, Invoice,Company,Client
import json
from pydantic import ValidationError
from pydantic_models import OfferAI, OfferAIItem, InvoiceModel
from pdf_generator import render_invoice_to_pdf
from extensions import mail
from aibot_routes import invoice_number_generator


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

        qty_raw = item.get("quantity")
        unit_raw = item.get("unit")
        unit_price_raw = item.get("price_per_item")

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
        unit_price = to_decimal(item.get("price_per_item", 0))

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
    item_names = request.form.getlist("item_description[]")
    item_quantities = request.form.getlist("item_quantity[]")
    item_unit_prices = request.form.getlist("item_price_per_item[]")

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
    #print(f"items from func {items}")
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

    discount_total = Decimal(str(ai_obj.discount_total)) if ai_obj.discount_total is not None else Decimal("0.00")
    
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
    print("discount_total from db:", offer.discount_total, type(offer.discount_total))

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
        "invoice_number": invoice_number_generator().upper(),
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
        "discount_total": str(offer.discount_total) if offer.discount_total is not None else "0.00",
    }

    return db_json, client_data

def send_offer_email(offer: Offer):
    if not offer.customer_email:
        raise ValueError("Offer has no customer email.")

    company = Company.query.filter_by(
        id=offer.company_id,
        user_id=offer.user_id
    ).first()

    if not company:
        raise ValueError("Company for offer was not found.")
    stamp_data_uri = company.stamp_url
    if company.stamp_url:
        stamp_abs = os.path.join(
            current_app.static_folder, 'uploads', f'{stamp_data_uri}'.split('/')[-1]
        )
        if os.path.exists(stamp_abs):
            mime, _ = mimetypes.guess_type(stamp_abs)
            mime = mime or "image/png"
            with open(stamp_abs, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            stamp_data_uri = f"data:{mime};base64,{b64}"
        else:
            stamp_data_uri = None
    context = {
        "offer": offer,
        "company": company,
        "stamp_data_uri": stamp_data_uri,
    }
    pdf_path = render_invoice_to_pdf("offer_pdf.html", context)
    body = (
        f"Dobrý deň,\n\n"
        f"v prílohe Vám zasielame cenovú ponuku.\n\n"
        f"V prípade otázok nás neváhajte kontaktovať.\n\n"
        f"S pozdravom,\n"
        f"{company.name}"
    )
    msg = Message(
        subject=f"Cenová ponuka {offer.id}",
        recipients=[offer.customer_email],
        sender=current_app.config['MAIL_DEFAULT_SENDER'],
        reply_to=company.email if company.email else None,
        body=body,
    )
    with open(pdf_path, "rb") as f:
        msg.attach(f"cenová ponuka {offer.id}.pdf", "application/pdf", f.read())
   
    mail.send(msg)

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
    #print("RESULT:", result)

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
        print("Validation warnings:", warnings)
        flash("Pozor: " + " | ".join(warnings), "warning")

    flash("Ponuka bola vytvorená.", "success")
    return redirect(url_for("offers.offer_preview", offer_id=offer.id))

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
    #print("RESULT:", result)

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

@offers.route("/<int:offer_id>/from-offer-to-invoice", methods=["POST"])
@login_required
def from_offer_to_invoice(offer_id):
    offer = Offer.query.filter_by(id=offer_id, user_id=current_user.id).first_or_404()
    company = Company.query.filter_by(id=offer.company_id, user_id=current_user.id).first()

    if not company:
        flash("Nemáš vytvorenú firmu.", "warning")
        return redirect(url_for("offers.edit_offer", offer_id=offer.id))

    if not offer.items:
        flash("Ponuka nemá žiadne položky.", "warning")
        return redirect(url_for("offers.edit_offer", offer_id=offer.id))

    issue_date_obj = date.today()
    due_date_obj = issue_date_obj + timedelta(days=14)

    client = None
    match_type = "offer"

    if offer.customer_email:
        client = Client.query.filter_by(
            user_id=current_user.id,
            email=offer.customer_email
        ).first()

    if not client and offer.customer_name:
        client = Client.query.filter_by(
            user_id=current_user.id,
            name=offer.customer_name
        ).first()

    client_id = client.id if client else None

    client_data = {
        "name": client.name if client else (offer.customer_name or ""),
        "email": client.email if client else (offer.customer_email or ""),
        "ico": client.ico if client else "",
        "dic": client.dic if client else "",
        "street": client.street if client else "",
        "city": client.city if client else "",
        "zip_code": client.zip_code if client else "",
        "country": client.country if client else "",
        "phone": client.phone if client else "",
        "iban": client.iban if client else "",
        "bic": client.bic if client else "",
        "ic_dph": client.ic_dph if client else "",
    }

    items = []
    for item in offer.items or []:
        qty = item.get("quantity", 1)
        unit_price = item.get("price_per_item", 0)

        try:
            qty = float(qty)
        except (ValueError, TypeError):
            qty = 1.0

        try:
            unit_price = float(unit_price)
        except (ValueError, TypeError):
            unit_price = 0.0

        items.append({
            "description": item.get("description", ""),
            "quantity": qty,
            "unit": item.get("unit") or "ks",
            "price_per_item": unit_price,
            "total_cost": round(qty * unit_price, 2),
        })

    db_ready,client_data2 = build_preview_data_from_offer(offer, current_user.id)
    db_ready["items"] = items

    try:
        inv = InvoiceModel.model_validate(db_ready)
    except ValidationError as e:
        print("Validation error:", e)
        flash(f"Dáta z ponuky sa nepodarilo pripraviť na faktúru.", "danger" )
        return redirect(url_for("offers.edit_offer", offer_id=offer.id))

    return render_template(
        "invoice_preview.html",
        db_json=inv.model_dump(),
        client_data=client_data,
        match_type=match_type
    )

@offers.route("/ai_offer")
@login_required
def ai_offer_page():
    companies = Company.query.filter_by(user_id=current_user.id).all()
    return render_template("offer_bot.html", companies=companies)


@offers.route("/ai_offer_preview", methods=["POST"])
@login_required
def ai_offer_preview():
    companies = Company.query.filter_by(user_id=current_user.id).all()

    user_text = (request.form.get("user_input") or "").strip()
    company_id = request.form.get("company_id", type=int)

    if not user_text:
        flash("Vlož text pre AI.", "warning")
        return render_template("offer_bot.html", companies=companies)

    company = Company.query.filter_by(
        id=company_id,
        user_id=current_user.id
    ).first()

    if not company:
        flash("Vyber platnú firmu.", "warning")
        return render_template("offer_bot.html", companies=companies)

    result = generate_offer_from_text(
        user_text=user_text,
        company_id=company.id,
        user_id=current_user.id
    )
    #print("RESULT:", result)
    if not result.get("ok"):
        flash("AI výstup sa nepodarilo spracovať.", "danger")
        return render_template(
            "offer_bot.html",
            companies=companies,
            ai_errors=result.get("errors"),
            ai_raw=result.get("raw"),
            user_input=user_text
        )

    offer_data = result["data"]

    return render_template(
        "offer_preview.html",
        offer_data=offer_data,
        company=company,
        warnings=offer_data.get("warnings", []),
        form_action=url_for("offers.confirm_ai_offer"),
        cancel_url=url_for("offers.ai_offer_page")
    )

    
@offers.route("/confirm-ai-offer", methods=["POST"])
@login_required
def confirm_ai_offer():
    company_id = request.form.get("company_id", type=int)

    company = Company.query.filter_by(
        id=company_id,
        user_id=current_user.id
    ).first()

    if not company:
        flash("Firma neexistuje.", "danger")
        return redirect(url_for("offers.ai_offer_page"))

    customer_name = (request.form.get("customer_name") or "").strip()
    customer_email = (request.form.get("customer_email") or "").strip()
    currency = (request.form.get("currency") or "EUR").strip().upper()
    notes = (request.form.get("notes") or "").strip()
    discount_total = to_decimal(request.form.get("discount_total"), "0.00")

    names = request.form.getlist("item_description[]")
    qtys = request.form.getlist("item_quantity[]")
    prices = request.form.getlist("item_price_per_item[]")

    items = []
    subtotal = Decimal("0.00")

    for name, qty, price in zip(names, qtys, prices):
        name = (name or "").strip()
        if not name:
            continue

        try:
            qty_val = Decimal(str(qty).replace(",", "."))
        except Exception:
            qty_val = Decimal("0.00")

        try:
            price_val = Decimal(str(price).replace(",", "."))
        except Exception:
            price_val = Decimal("0.00")

        line_total = qty_val * price_val
        subtotal += line_total

        items.append({
            "description": name,
            "quantity": float(qty_val),
            "price_per_item": float(price_val),
        })

    total = subtotal - discount_total

    if not items:
        flash("Ponuka musí mať aspoň jednu položku.", "warning")
        return render_template(
            "offers/offer_preview.html",
            offer_data={
                "company_id": company.id,
                "customer_name": customer_name,
                "customer_email": customer_email,
                "currency": currency,
                "items": items,
                "notes": notes,
            },
            company=company,
            warnings=[],
            form_action=url_for("offers.confirm_ai_offer"),
            cancel_url=url_for("offers.ai_offer_page")
        )

    offer = Offer(
        user_id=current_user.id,
        company_id=company.id,
        customer_name=customer_name or None,
        customer_email=customer_email or None,
        currency=currency,
        items=items,
        notes=notes or None,
        subtotal=subtotal,
        discount_total=discount_total,
        total=total,
        status="draft",
        created_at=datetime.utcnow(),
    )

    db.session.add(offer)
    db.session.commit()

    flash("Ponuka bola vytvorená.", "success")
    return redirect(url_for("offers.edit_offer", offer_id=offer.id))


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
    stamp_data_uri = company.stamp_url
    if company.stamp_url:
        stamp_abs = os.path.join(
            current_app.static_folder, 'uploads', f'{stamp_data_uri}'.split('/')[-1]
        )
        if os.path.exists(stamp_abs):
            mime, _ = mimetypes.guess_type(stamp_abs)
            mime = mime or "image/png"
            with open(stamp_abs, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            stamp_data_uri = f"data:{mime};base64,{b64}"
    return render_template(
        "offer_preview.html",
        offer_data=offer,
        company=company,
        stamp_data_uri=stamp_data_uri,
    )
@offers.route("/<int:offer_id>/download")
@login_required
def download_offer(offer_id):
    offer = Offer.query.filter_by(id=offer_id, user_id=current_user.id).first_or_404()
    company = Company.query.filter_by(id=offer.company_id, user_id=current_user.id).first_or_404()
    
    stamp_data_uri = company.stamp_url
    if company.stamp_url:
        stamp_abs = os.path.join(
            current_app.static_folder, 'uploads', f'{stamp_data_uri}'.split('/')[-1]

        )
        if os.path.exists(stamp_abs):
            mime, _ = mimetypes.guess_type(stamp_abs)
            mime = mime or "image/png"
            with open(stamp_abs, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            stamp_data_uri = f"data:{mime};base64,{b64}"
    context = {
        "offer": offer,
        "company": company,
        "stamp_data_uri": stamp_data_uri,
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
    names = request.form.getlist("item_description[]")
    qtys = request.form.getlist("item_quantity[]")
    prices = request.form.getlist("item_price_per_item[]")

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

    discount_total = to_decimal(request.form.get("discount_total"), "0.00")
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
@offers.route("/<int:offer_id>/send-email", methods=["POST"])
@login_required
def send_offer_email_route(offer_id):
    offer = Offer.query.filter_by(id=offer_id, user_id=current_user.id).first_or_404()

    try:
        send_offer_email(offer)
        offer.status = "sent"
        db.session.commit()
        flash("Ponuka byla odeslána emailem.", "success")
    except Exception as e:
        print("Error sending email:", e)
        flash(f"Chyba při odesílání emailu.", "danger")

    return redirect(url_for("offers.edit_offer", offer_id=offer.id))

@offers.route("/<int:offer_id>/mark_accepted", methods=["POST"])
@login_required
def mark_offer_accepted(offer_id):
    offer = Offer.query.filter_by(id=offer_id, user_id=current_user.id).first_or_404()
    offer.status = "accepted"
    db.session.commit()
    flash(f"Ponuka {offer.id} bola označená ako prijatá.", "success")
    return redirect(url_for("offers.edit_offer", offer_id=offer.id))


@offers.route("/ai_expand_notes", methods=["POST"])
@login_required
def ai_expand_notes():
    data = request.get_json(silent=True) or {}
    item_text = (data.get("text") or "").strip()
    print("DATA:", data)
    print("TEXT:", item_text)

    if not item_text:
        return {"ok": False, "error": "Chýba text poznámky."}, 400

    try:
        improved_text = call_llm_generate_offer_description(item_text)
        return {"ok": True, "text": improved_text}
    except Exception as e:
        current_app.logger.exception("AI expand notes failed")
        return {"ok": False, "error": str(e)}, 500
    

def save_offer_from_form(job=None):
    company_id = request.form.get("company_id") or None
    customer_name = request.form.get("customer_name", "").strip()
    customer_email = request.form.get("customer_email", "").strip()
    currency = request.form.get("currency", "EUR").strip() or "EUR"
    notes = request.form.get("notes", "").strip()

    item_names = request.form.getlist("item_name[]")
    item_qtys = request.form.getlist("item_qty[]")
    item_units = request.form.getlist("item_unit[]")
    item_prices = request.form.getlist("item_price[]")

    items = []
    subtotal = Decimal("0.00")

    for name, qty_raw, unit, price_raw in zip(item_names, item_qtys, item_units, item_prices):
        name = name.strip()
        unit = unit.strip() or "ks"

        if not name:
            continue

        try:
            qty = Decimal(qty_raw.replace(",", "."))
        except Exception:
            qty = Decimal("1")

        try:
            price = Decimal(price_raw.replace(",", "."))
        except Exception:
            price = Decimal("0")

        line_total = qty * price
        subtotal += line_total

        items.append({
            "name": name,
            "quantity": float(qty),
            "unit": unit,
            "price_per_item": float(price),
            "total": float(line_total),
        })

    if not company_id:
        flash("Vyber firmu.", "danger")
        if job:
            return redirect(url_for("offers.create_offer_from_job", job_id=job.id))
        return redirect(url_for("offers.offer_create"))

    if not customer_name:
        flash("Zadaj meno zákazníka.", "danger")
        if job:
            return redirect(url_for("offers.create_offer_from_job", job_id=job.id))
        return redirect(url_for("offers.offer_create"))

    if not items:
        flash("Ponuka musí mať aspoň jednu položku.", "danger")
        if job:
            return redirect(url_for("offers.create_offer_from_job", job_id=job.id))
        return redirect(url_for("offers.offer_create"))

    offer = Offer(
        user_id=current_user.id,
        job_id=job.id if job else None,
        company_id=int(company_id),
        customer_name=customer_name,
        customer_email=customer_email,
        currency=currency,
        notes=notes,
        items=items,
        subtotal=subtotal,
        discount_total=Decimal("0.00"),
        total=subtotal,
        status="draft",
    )

    db.session.add(offer)

    if job:
        job.status = "offer_sent"

    db.session.commit()

    flash("Cenová ponuka bola vytvorená.", "success")
    return redirect(url_for("offers.edit_offer", offer_id=offer.id))

@offers.route("/offers/create", methods=["GET", "POST"])
@login_required
def offer_create():
    if request.method == "POST":
        return save_offer_from_form()

    companies = Company.query.filter_by(user_id=current_user.id).all()
    clients = Client.query.filter_by(user_id=current_user.id).order_by(Client.name.asc()).all()

    return render_template(
        "offers_create.html",
        companies=companies,
        clients=clients,
        job=None,
        default_customer_name="",
        default_customer_email="",
        default_notes="",
        default_company_id=None,
    )

@offers.route("/offers/create-from-job/<int:job_id>", methods=["GET", "POST"])
@login_required
def create_offer_from_job(job_id):
    job = Job.query.filter_by(
        id=job_id,
        user_id=current_user.id
    ).first_or_404()

    if request.method == "POST":
        return save_offer_from_form(job=job)

    companies = Company.query.filter_by(user_id=current_user.id).all()
    clients = Client.query.filter_by(user_id=current_user.id).order_by(Client.name.asc()).all()

    default_notes_parts = []

    if job.description:
        default_notes_parts.append(job.description)

    for note in job.notes:
        default_notes_parts.append(f"- {note.content}")

    default_notes = "\n".join(default_notes_parts)

    return render_template(
        "offers_create.html",
        companies=companies,
        clients=clients,
        job=job,
        default_customer_name=job.client.name if job.client else "",
        default_customer_email=job.client.email if job.client and job.client.email else "",
        default_notes=default_notes,
        default_company_id=job.company_id,
    )
    

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


"""
aibot_routes.py:180:            flash("Vlož text pre AI.", "warning")
aibot_routes.py:188:        flash("AI nenašla žádné položky. Uprav text.", "warning")
aibot_routes.py:191:        flash("Nemáš vytvorenú firmu.", "warning")
aibot_routes.py:196:        flash("Nemáš vytvoreného klienta. AI sa pokúsi ho vytvoriť podľa textu.", "info")
aibot_routes.py:213:        flash("Nájdený existujúci klient: " + client_ok.name, "success")
aibot_routes.py:282:        flash(f"Zle vyplneny formulár.", "danger")
aibot_routes.py:342:        flash("Chýbajú dáta na potvrdenie.", "danger")
aibot_routes.py:348:        flash("Neplatný JSON náhľadu.", "danger")
aibot_routes.py:356:        flash("Nemáš vytvorenú firmu.", "danger")
aibot_routes.py:373:        flash("DPH musí byť číslo.", "danger")
aibot_routes.py:406:        flash(
aibot_routes.py:482:            flash(f"Položka {i+1}: množstvo musí byť číslo.", "danger")
aibot_routes.py:488:            flash(f"Položka {i+1}: cena musí byť číslo.", "danger")
aibot_routes.py:502:        flash("Faktúra musí obsahovať aspoň jednu položku.", "danger")
aibot_routes.py:531:        flash("Chýba číslo faktúry.", "danger")
aibot_routes.py:547:        flash("Toto číslo faktúry už používaš. Zvoľ iné.", "danger")
aibot_routes.py:564:        flash(f"Chyba pri ukladaní: {e}", "danger")
offers.py:302:        flash("Popis dopytu je povinný.", "danger")
offers.py:327:        flash("Vlož text pre AI.", "warning")
offers.py:331:        flash("Vyber firmu.", "warning")
offers.py:342:        flash("AI výstup sa nepodarilo spracovať.", "danger")
offers.py:352:        flash("AI nenašla žiadne položky pre ponuku.", "warning")
offers.py:363:        flash("Pozor: " + " | ".join(warnings), "warning")
offers.py:365:    flash("Ponuka bola vytvorená.", "success")
offers.py:375:        flash("Najprv si vytvor firmu.", "warning")
offers.py:395:        flash("AI výstup sa nepodarilo spracovať.", "danger")
offers.py:434:        flash("Pozor: " + " | ".join(warnings), "warning")
offers.py:436:    flash("Návrh ponuky bol vytvorený.", "success")
offers.py:446:        flash("Ponuka nemá žiadne položky.", "danger")
offers.py:465:        flash("Nemáš vytvorenú firmu.", "warning")
offers.py:469:        flash("Ponuka nemá žiadne položky.", "warning")
offers.py:537:        flash(f"Dáta z ponuky sa nepodarilo pripraviť na faktúru.", "danger" )
offers.py:563:        flash("Vlož text pre AI.", "warning")
offers.py:572:        flash("Vyber platnú firmu.", "warning")
offers.py:582:        flash("AI výstup sa nepodarilo spracovať.", "danger")
offers.py:614:        flash("Firma neexistuje.", "danger")
offers.py:657:        flash("Ponuka musí mať aspoň jednu položku.", "warning")
offers.py:692:    flash("Ponuka bola vytvorená.", "success")
offers.py:716:        flash("Ponuka musí obsahovať aspoň jednu položku.", "danger")
offers.py:731:    flash("Ponuka bola uložená.", "success")
offers.py:790:        flash("Chýba firma.", "danger")
offers.py:859:    flash("Ponuka bola uložená.", "success")
offers.py:870:        flash("Ponuka byla odeslána emailem.", "success")
offers.py:873:        flash(f"Chyba při odesílání emailu.", "danger")
offers.py:883:    flash(f"Ponuka {offer.id} bola označená ako prijatá.", "success")
offers.py:912:        flash("Ponuka nemá žiadne položky.", "danger")
offers.py:951:    flash("Faktúra bola vytvorená z ponuky.", "success")
routes.py:219:            flash('Používateľ s týmto emailom alebo menom už existuje.', 'danger')
routes.py:222:        flash('Registrácia prebehla úspešne!', 'success')
routes.py:257:    flash('Bol si odhlásený.', 'info')
routes.py:421:        flash(result, 'success')
routes.py:423:        flash(f'Chyba při odesílání emailu: {str(e)}', 'danger')
routes.py:707:                flash("Súbor nemá príponu.", "danger")
routes.py:713:                flash("Nepovolený formát obrázka (použi PNG/JPG/WEBP).", "danger")
routes.py:731:                flash("Súbor neviem spracovať ako obrázok.", "danger")
routes.py:737:        flash("Údaje o firme boli úspešne uložené.", "success")
routes.py:750:    flash(f"Faktúra {invoice.invoice_number} bola označená ako zaplatená.", "success")
routes.py:758:        flash(f"Faktúra {invoice.invoice_number} je už zaplatená a nemôže byť označená ako oneskorená.", "warning")
routes.py:761:        flash(f"Faktúra {invoice.invoice_number} ešte nie je po termíne splatnosti.", "warning")
routes.py:766:    flash(f"Faktúra {invoice.invoice_number} bola označená ako oneskorená.", "success")
routes.py:793:            flash('Vyplň číslo faktúry (alebo si sprav autogeneráciu).', 'danger')
routes.py:803:            flash('Toto číslo faktúry už používaš. Zvoľ iné.', 'danger')
routes.py:811:            flash('Vyber klienta a firmu.', 'danger')
routes.py:853:            flash('Pridaj aspoň jednu platnú položku.', 'danger')
routes.py:861:            flash('Dátum alebo splatnosť sú neplatné.', 'danger')
routes.py:912:            flash('Toto číslo faktúry už používaš (DB). Zvoľ iné.', 'danger')
routes.py:930:            flash('Email odoslaný!', 'success')
routes.py:933:            flash(f'Chyba pri odosielaní emailu: {str(e)}', 'danger')
routes.py:1017:        flash("Faktúru možno upravovať len v stave 'draft'.", "warning")
routes.py:1032:            flash("Neplatná DPH sadzba.", "danger")
routes.py:1038:            flash("Klient nie je priradený.", "danger")
routes.py:1070:                flash(f"Neplatná položka {i}.", "danger")
routes.py:1089:            flash("Žiadne platné položky neboli odoslané.", "danger")
routes.py:1099:            flash("Faktúra bola upravená.", "success")
routes.py:1103:            flash("Chyba pri ukladaní. Skontroluj duplicitu čísla faktúry a formát dát.", "danger")
routes.py:1157:        flash("Potrebujete aktívne predplatné pre AI funkciu.", "danger")

"""