# routes_pages.py (výňatok)
import json
from random import randint
from datetime import date as date_cls
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, jsonify
from flask_login import login_required, current_user
from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError

from models import User, Invoice, InvoiceItem, Client, Company, PaymentMethod, InvoiceStatus
from extensions import db

from ai import call_llm_extract
from pydantic_models import InvoiceModel, InvoiceAI
from normalize_ai import normalize_ai_payload
from ai import create_invoice_from_model  # alebo importni odkiaľ ju máš

aibot = Blueprint("aibot", __name__)

@aibot.route("/ai_bot", methods=["GET"])
@login_required
def ai_bot():
    clients = Client.query.filter_by(user_id=current_user.id).all()
    companies = Company.query.filter_by(user_id=current_user.id).all()
    return render_template("ai_bot.html", clients=clients, companies=companies)

@aibot.route("/invoice_preview", methods=["POST"])
@login_required
def ai_preview():
    clients = Client.query.filter_by(user_id=current_user.id).all()
    companies = Company.query.filter_by(user_id=current_user.id).all()

    user_text = (request.form.get("user_input") or "").strip()
    client_id = int(request.form.get("client_id") or 0)
    company_id = int(request.form.get("company_id") or 0)
    invoice_number = (request.form.get("invoice_number") or f"INV-{date_cls.today():%Y}-{randint(1000,9999)}").upper()

    # základná kontrola klient/firmy
    client_ok = Client.query.filter_by(id=client_id, user_id=current_user.id).first()
    company_ok = Company.query.filter_by(id=company_id, user_id=current_user.id).first()
    if not client_ok or not company_ok:
        flash("Vyber platného klienta a firmu.", "danger")
        return render_template("ai_bot.html", clients=clients, companies=companies)

    if not user_text:
        flash("Vlož text pre AI.", "warning")
        return render_template("ai_bot.html", clients=clients, companies=companies)

    # 1) AI draft
    ai_raw = call_llm_extract(user_text)
    try:
        ai_obj = InvoiceAI(**ai_raw)     # validácia AI výstupu (len AI polia)
    except ValidationError as e:
        return render_template("ai_bot.html", clients=clients, companies=companies, ai_errors=e.errors())

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
        return render_template("ai_bot.html", clients=clients, companies=companies, ai_errors=e.errors())

    # 4) Náhľad
    return render_template("invoice_preview.html", db_json=inv.model_dump())

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

    # preflight unikátnosti čísla
    inv_no = (db_json.get("invoice_number") or "").strip().upper()
    if not inv_no:
        flash("Chýba číslo faktúry.", "danger")
        return redirect(url_for("aibot.ai_bot"))

    dup = db.session.query(
        db.exists().where(and_(
            Invoice.user_id == current_user.id,
            Invoice.invoice_number == inv_no
        ))
    ).scalar()
    if dup:
        flash("Toto číslo faktúry už používaš. Zvoľ iné.", "danger")
        return redirect(url_for("aibot.ai_bot"))

    # uloženie
    try:
        invoice_id = create_invoice_from_model(db_json)
        print('ide ')
    except Exception as e:
        print('nejde')
        flash(f"Chyba pri ukladaní: {e}", "danger")
        return redirect(url_for("aibot.ai_bot"))

    return redirect(url_for("main.view_invoice", invoice_id=invoice_id))


"""Ahoj, prosím vystaviť faktúru.

Odberateľ: Jano Novák, jano.novak@example.com
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