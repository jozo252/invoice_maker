# routes_pages.py (výňatok)
import json
from random import randint
from datetime import date as date_cls, timedelta
from types import SimpleNamespace
import unicodedata
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import login_required, current_user
from sqlalchemy import and_, null
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError
from datetime import date

from models import User, Invoice, InvoiceItem, Client, Company, PaymentMethod, InvoiceStatus
from extensions import db

from ai import call_llm_extract
from pydantic_models import InvoiceModel, InvoiceAI
from normalize_ai import normalize_ai_payload
from ai import create_invoice_from_model  # alebo importni odkiaľ ju máš

aibot = Blueprint("aibot", __name__)

def invoice_number_generator():
    last_invoice = Invoice.query.filter_by(user_id=current_user.id).order_by(Invoice.id.desc()).first()
    number=last_invoice.invoice_number if last_invoice else None
    number_int = int(number.split("-")[-1]) if number and number.startswith("INV-") else 0
    number_int += 1
    today_str = date_cls.today().strftime("%Y")
    return f"INV-{today_str}-{number_int}"

def normalize_name(name: str) -> str:
    if not name:
        return ""

    name = name.strip().lower()

    
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))

    
    for ch in [".", ",", "-", "_"]:
        name = name.replace(ch, " ")
    name = " ".join(name.split())

    return name
def get_client_company_from_ai(ai_data: dict, user_id: int):
    raw_name = ai_data.get("customer_name")
    customer_name = normalize_name(raw_name) if raw_name else None
    customer_email = ai_data.get("customer_email")
    customer_ico = ai_data.get("customer_ico")

    client = None
    match_type = None

    if customer_email:
        client = Client.query.filter_by(
            user_id=user_id,
            email=customer_email
        ).first()
        match_type = "email"

    if customer_ico and not client:
        client = Client.query.filter_by(
            user_id=user_id,
            ico=customer_ico
        ).first()
        match_type = "ico"

    if customer_name and not client:
        client = Client.query.filter_by(
            user_id=user_id,
            name=customer_name
        ).first()
        match_type = "name"

    company = Company.query.filter_by(user_id=user_id).first()

    return client, company, match_type
def build_preview_data_from_form(form):
    try:
        items_count = int(form.get("items_count", 0))
    except ValueError:
        items_count = 0

    db_json = {
        "invoice_number": form.get("invoice_number", ""),
        "inv_date": form.get("inv_date", ""),
        "due_date": form.get("due_date", ""),
        "variable_symbol": form.get("variable_symbol", ""),
        "currency": form.get("currency", "EUR"),
        "payment_method": form.get("payment_method", "bank_transfer"),
    }

    vat_raw = (form.get("vat_rate") or "").strip()
    try:
        db_json["vat_rate"] = float(vat_raw) if vat_raw else 0
    except ValueError:
        db_json["vat_rate"] = vat_raw

    items = []
    for i in range(items_count):
        qty_raw = (form.get(f"item_quantity_{i}") or "").strip()
        price_raw = (form.get(f"item_price_{i}") or "").strip()

        try:
            quantity = float(qty_raw) if qty_raw else 1.0
        except ValueError:
            quantity = qty_raw

        try:
            price_per_item = float(price_raw) if price_raw else 0.0
        except ValueError:
            price_per_item = price_raw

        if isinstance(quantity, (int, float)) and isinstance(price_per_item, (int, float)):
            total_cost = round(quantity * price_per_item, 2)
        else:
            total_cost = 0

        items.append({
            "description": form.get(f"item_description_{i}", ""),
            "unit": form.get(f"item_unit_{i}", "ks"),
            "quantity": quantity,
            "price_per_item": price_per_item,
            "total_cost": total_cost,
        })

    db_json["items"] = items

    client_data = SimpleNamespace(
        id=form.get("client_id", ""),
        name=form.get("client_name", ""),
        ico=form.get("client_ico", ""),
        dic=form.get("client_dic", ""),
        street=form.get("client_street", ""),
        city=form.get("client_city", ""),
        zip_code=form.get("client_zip_code", ""),
        country=form.get("client_country", ""),
        email=form.get("client_email", ""),
        phone=form.get("client_phone", ""),
        iban=form.get("client_iban", ""),
        bic=form.get("client_bic", ""),
        ic_dph=form.get("client_ic_dph", ""),
    )

    return db_json, client_data
@aibot.route("/ai_bot", methods=["GET"])
@login_required
def ai_bot():
    clients = Client.query.filter_by(user_id=current_user.id).all()
    companies = Company.query.filter_by(user_id=current_user.id).all()
    return render_template("ai_bot.html", clients=clients, companies=companies)



#prvotný návrh, ešte to chce doladiť, ale už to funguje v základe

@aibot.route("/invoice_preview", methods=["POST"])
@login_required
def ai_preview():
    clients = Client.query.filter_by(user_id=current_user.id).all()
    companies = Company.query.filter_by(user_id=current_user.id).all()

    user_text = (request.form.get("user_input") or "").strip()
    #client_id = int(request.form.get("client_id") or 0)
    #company_id = int(request.form.get("company_id") or 0)
    invoice_number = (request.form.get("invoice_number") or invoice_number_generator()).upper()
    if not user_text:
            flash("Vlož text pre AI.", "warning")
            return render_template("ai_bot.html", clients=clients, companies=companies)
    ai_raw = call_llm_extract(user_text)
    # základná kontrola klient/firmy
    #client_ok = Client.query.filter_by(id=client_id, user_id=current_user.id).first()
    #company_ok = Company.query.filter_by(id=company_id, user_id=current_user.id).first()
    client_ok, company_ok, match_type = get_client_company_from_ai(ai_raw, current_user.id)
    if not ai_raw.get("items"):
        flash("AI nenašla žádné položky. Uprav text.", "warning")
        return render_template("ai_bot.html", clients=clients, companies=companies)
    if not company_ok:
        flash("Nemáš vytvorenú firmu.", "warning")
        return render_template("ai_bot.html", clients=clients, companies=companies)
    company_id = company_ok.id
    
    if not client_ok:
        flash("Nemáš vytvoreného klienta. AI sa pokúsi ho vytvoriť podľa textu.", "info")
        client_data = {
        "name": ai_raw.get("customer_name", ""),
        "email": ai_raw.get("customer_email", ""),
        "ico": ai_raw.get("customer_ico", ""),
        "dic": ai_raw.get("customer_dic", ""),
        "street": ai_raw.get("customer_street", ""),
        "city": ai_raw.get("customer_city", ""),
        "zip_code": ai_raw.get("customer_zip_code", ""),
        "country": ai_raw.get("customer_country", ""),
        "phone": ai_raw.get("customer_phone", ""),
        "iban": ai_raw.get("customer_iban", ""),
        "ic_dph": ai_raw.get("customer_ic_dph", ""),
    }
        

    else:
        flash("Nájdený existujúci klient: " + client_ok.name, "success")
        client_id = client_ok.id
        client_data = {
            "name": client_ok.name,
            "email": client_ok.email,
            "ico": client_ok.ico,
            "dic": client_ok.dic,
            "street": client_ok.street,
            "city": client_ok.city,
            "zip_code": client_ok.zip_code,
            "country": client_ok.country,
            "phone": client_ok.phone,
            "iban": client_ok.iban,
            "bic": client_ok.bic,
            "ic_dph": client_ok.ic_dph,
        }
    issue_date = ai_raw.get("issue_date")
    due_date = ai_raw.get("due_date")
    due_in_days = ai_raw.get("due_in_days")

    # --- ISSUE DATE ---
    if not issue_date:
        issue_date_obj = date.today()
    else:
        issue_date_obj = date.fromisoformat(issue_date)

    # --- DUE DATE ---
    if due_date:
        due_date_obj = date.fromisoformat(due_date)

    elif due_in_days:
        try:
            days = int(due_in_days)
        except ValueError:
            days = 14
        due_date_obj = issue_date_obj + timedelta(days=days)

    else:
        # default splatnosť
        due_date_obj = issue_date_obj + timedelta(days=14)

    # --- Ulož späť ako string ---
    ai_raw["issue_date"] = issue_date_obj.isoformat()
    ai_raw["due_date"] = due_date_obj.isoformat()
        
    
    

    # 1) AI draft
    
    try:
        ai_obj = InvoiceAI(**ai_raw)     # validácia AI výstupu (len AI polia)
    except ValidationError as e:
        return render_template("ai_bot.html", clients=clients, companies=companies, ai_errors=e.errors())
    client_id = client_ok.id if client_ok else None
    # 2) Map AI → DB tvar
    db_ready = normalize_ai_payload(
        ai_obj.model_dump(),
        user_id=current_user.id,
        client_id=client_id,
        company_id=company_id,
        invoice_number=invoice_number
    )

    # 3) DB schéma
    try:
        inv = InvoiceModel.model_validate(db_ready)
    except ValidationError as e:
        # ukáž chyby späť na AI stránke (nech vieš čo opraviť)
        flash(f"Zle vyplneny formulár.", "danger")
        db_json, client_data = build_preview_data_from_form(request.form)
        return render_template(
            "aibot/ai_preview.html",
            db_json=db_json,
            client_data=client_data,
            client_match_type=request.form.get("client_match_type"),
        )
    
    #tu pridat clienta do DB ak neexistuje, aby sa zobrazil v náhľade a potom sa už len potvrdí a uloží
    # 4) Náhľad 
    return render_template("invoice_preview.html", db_json=inv.model_dump(), client_data=client_data, match_type=match_type)


#------------------------AI potvrdenie a uloženie do DB------------------------

@aibot.route("/ai/confirm", methods=["POST"])
@login_required
def ai_confirm():
    db_json_raw = request.form.get("db_json") or ""
    if not db_json_raw:
        flash("Chýbajú dáta na potvrdenie.", "danger")
        return redirect(url_for("aibot.ai_bot"))

    try:
        db_json = json.loads(db_json_raw)
    except Exception:
        flash("Neplatný JSON náhľadu.", "danger")
        return redirect(url_for("aibot.ai_bot"))

    # -----------------------------
    # 1. Firma používateľa
    # -----------------------------
    company = Company.query.filter_by(user_id=current_user.id).first()
    if not company:
        flash("Nemáš vytvorenú firmu.", "danger")
        return redirect(url_for("aibot.ai_bot"))

    # -----------------------------
    # 2. Načítanie upravených invoice polí z formulára
    # -----------------------------
    invoice_number = (request.form.get("invoice_number") or "").strip().upper()
    inv_date = (request.form.get("inv_date") or "").strip()
    due_date = (request.form.get("due_date") or "").strip()
    variable_symbol = (request.form.get("variable_symbol") or "").strip()
    currency = (request.form.get("currency") or "EUR").strip().upper()
    payment_method = (request.form.get("payment_method") or "bank_transfer").strip()

    vat_rate_raw = (request.form.get("vat_rate") or "").strip()
    try:
        vat_rate = float(vat_rate_raw) if vat_rate_raw else 0.0
    except ValueError:
        flash("DPH musí byť číslo.", "danger")
        return redirect(url_for("aibot.ai_bot"))

    # -----------------------------
    # 3. Načítanie klienta z formulára
    # -----------------------------
    client_name = (request.form.get("client_name") or "").strip()
    client_ico = (request.form.get("client_ico") or "").strip()
    client_dic = (request.form.get("client_dic") or "").strip()
    client_street = (request.form.get("client_street") or "").strip()
    client_city = (request.form.get("client_city") or "").strip()
    client_zip_code = (request.form.get("client_zip_code") or "").strip()
    client_country = (request.form.get("client_country") or "").strip()
    client_email = (request.form.get("client_email") or "").strip()
    client_phone = (request.form.get("client_phone") or "").strip()
    client_iban = (request.form.get("client_iban") or "").strip()
    client_ic_dph = (request.form.get("client_ic_dph") or "").strip()

    # minimálna validácia klienta
    required_client_fields = {
        "Názov / meno klienta": client_name,
        
        #"Ulica": client_street,
        #"Mesto": client_city,
        #"PSČ": client_zip_code,
        #"Krajina": client_country,
        #"Email": client_email,
        #"Telefón": client_phone,
        #"IBAN": client_iban,
    }

    missing_client_fields = [label for label, value in required_client_fields.items() if not value]
    if missing_client_fields:
        flash(
            "Doplň povinné údaje klienta: " + ", ".join(missing_client_fields),
            "danger"
        )
        return redirect(url_for("aibot.ai_bot"))

    # -----------------------------
    # 4. Lookup alebo create klienta
    # -----------------------------
    client = None

    if client_email:
        client = Client.query.filter_by(
            user_id=current_user.id,
            email=client_email
        ).first()

    if not client and client_name:
        client = Client.query.filter_by(
            user_id=current_user.id,
            name=client_name
        ).first()

    if client:
        # ak chceš, môžeš existujúceho klienta aj aktualizovať
        client.name = client_name
        client.ico = client_ico
        client.dic = client_dic
        client.street = client_street
        client.city = client_city
        client.zip_code = client_zip_code
        client.country = client_country
        client.email = client_email
        client.phone = client_phone
        client.iban = client_iban
        client.ic_dph = client_ic_dph or None
    else:
        client = Client(
            name=client_name,
            ico=client_ico,
            dic=client_dic,
            street=client_street,
            user_id=current_user.id,
            city=client_city,
            zip_code=client_zip_code,
            country=client_country,
            email=client_email,
            phone=client_phone,
            iban=client_iban,
            ic_dph=client_ic_dph or None,
        )
        db.session.add(client)
        db.session.flush()

    # -----------------------------
    # 5. Načítanie položiek z formulára
    # -----------------------------
    try:
        items_count = int(request.form.get("items_count", 0))
    except ValueError:
        items_count = 0

    items = []
    for i in range(items_count):
        description = (request.form.get(f"item_description_{i}") or "").strip()
        unit = (request.form.get(f"item_unit_{i}") or "ks").strip()

        qty_raw = (request.form.get(f"item_quantity_{i}") or "").strip()
        price_raw = (request.form.get(f"item_price_{i}") or "").strip()

        if not description:
            continue

        try:
            quantity = float(qty_raw) if qty_raw else 1.0
        except ValueError:
            flash(f"Položka {i+1}: množstvo musí byť číslo.", "danger")
            return redirect(url_for("aibot.ai_bot"))

        try:
            price_per_item = float(price_raw) if price_raw else 0.0
        except ValueError:
            flash(f"Položka {i+1}: cena musí byť číslo.", "danger")
            return redirect(url_for("aibot.ai_bot"))

        total_cost = round(quantity * price_per_item, 2)

        items.append({
            "description": description,
            "quantity": quantity,
            "unit": unit or "ks",
            "price_per_item": round(price_per_item, 2),
            "total_cost": total_cost,
        })

    if not items:
        flash("Faktúra musí obsahovať aspoň jednu položku.", "danger")
        db_json, client_data = build_preview_data_from_form(request.form)
        return render_template(
            "invoice_preview.html",
            db_json=db_json,
            client_data=client_data,
            client_match_type=request.form.get("client_match_type"),
        )

    # -----------------------------
    # 6. Poskladanie finálneho payloadu
    # -----------------------------
    db_json["invoice_number"] = invoice_number
    db_json["inv_date"] = inv_date
    db_json["due_date"] = due_date
    db_json["variable_symbol"] = variable_symbol
    db_json["currency"] = currency
    db_json["vat_rate"] = vat_rate
    db_json["payment_method"] = payment_method
    db_json["user_id"] = current_user.id
    db_json["company_id"] = company.id
    db_json["client_id"] = client.id
    db_json["items"] = items

    # -----------------------------
    # 7. Preflight unikátnosti čísla
    # -----------------------------
    inv_no = (db_json.get("invoice_number") or "").strip().upper()
    if not inv_no:
        flash("Chýba číslo faktúry.", "danger")
        db_json, client_data = build_preview_data_from_form(request.form)
        return render_template(
            "invoice_preview.html",
            db_json=db_json,
            client_data=client_data,
            client_match_type=request.form.get("client_match_type"),
        )
    dup = db.session.query(
        db.exists().where(and_(
            Invoice.user_id == current_user.id,
            Invoice.invoice_number == inv_no
        ))
    ).scalar()

    if dup:
        flash("Toto číslo faktúry už používaš. Zvoľ iné.", "danger")
        db_json, client_data = build_preview_data_from_form(request.form)
        return render_template(
            "invoice_preview.html",
            db_json=db_json,
            client_data=client_data,
            client_match_type=request.form.get("client_match_type"),
        )

    # -----------------------------
    # 8. Uloženie faktúry
    # -----------------------------
    try:
        invoice_id = create_invoice_from_model(db_json)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"Chyba pri ukladaní: {e}", "danger")
        return redirect(url_for("aibot.ai_bot"))

    return redirect(url_for("main.view_invoice", invoice_id=invoice_id))


"""Ahoj, prosím vystaviť faktúru.

Odberateľ: Jano Novák, ferko.lizak69@gmail.com
Mena: €
Dátum vystavenia: 21.09.2025
Splatnosť: 30.09.2025
Spôsob úhrady: bank transfer
DPH: 20 %

Položky:
- Webdesign – množstvo 2 ks, cena 500,00 € / ks
- Hosting – množstvo 1 ks, cena 100 € / ks
- Úpravy loga – množstvo 1 hod, cena 35,50 € / hod

Poznámka: dodať prístupové údaje po úhrade.

--
Ďakujem,
Adam
"""