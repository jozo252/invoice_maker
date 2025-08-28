from flask import Blueprint, render_template, request, redirect, url_for,session, flash, send_file, abort, jsonify, current_app
from models import Client, Invoice, Company, InvoiceItem, User, InvoiceStatus, PaymentMethod, InvoiceCounter
from datetime import datetime, timezone
from difflib import get_close_matches
from ai_chat import invoice_maker
from extensions import db, mail
from flask_mail import Message
from pdf_generator import render_invoice_to_pdf
import os
import stripe
from dotenv import load_dotenv
from app import CSRFProtect, csrf
from sqlalchemy import func, and_, or_, text
from datetime import timedelta, date
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from decimal import Decimal, ROUND_HALF_UP
import io
from segno import helpers as segno_helpers
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP





from forms import RegistrationForm, LoginForm
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
load_dotenv()
main = Blueprint('main', __name__)




def _D(x, default="0"):
    if x in (None, ""):
        return Decimal(default)
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)

# Initialize Stripe with your secret key


def _parse_date(s, default_val):
    if not s:
        return default_val
    s = s.strip()
    # 1) HTML input type="date" posílá YYYY-MM-DD
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return default_val



@main.route('/account')
@login_required
def account():
    return render_template('account.html',user=current_user)


@main.route('/pricing')
@login_required
def pricing():
    return render_template('pricing.html')

@csrf.exempt
@main.route('/webhook', methods=['POST'])
def stripe_webhook():
    stripe.api_key = current_app.config["STRIPE_API_KEY"]
    print(stripe.api_key)
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature", "")
    endpoint_secret = current_app.config["STRIPE_WEBHOOK_SECRET"]
    

    

    if not endpoint_secret:
        return 'Webhook secret missing', 500

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        print("❌ Invalid payload", e)
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError as e:
        print("❌ Invalid signature", e)
        return 'Invalid signature', 400

    print("✅ Webhook event parsed:", event['type'])

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        print("✅ Session data:", session)
        user_id = session.get('metadata', {}).get('user_id')
        if user_id:
            user = User.query.get(int(user_id))
            if user:
                user.is_paid = True
                db.session.commit()
                print(f"🔓 User {user.email} marked as paid.")
            else:
                print("❌ User not found.")
        else:
            print("❌ Metadata missing user_id.")
    
    return '', 200






@main.route('/create-checkout-session')
@login_required
def create_checkout_session():
    stripe.api_key = current_app.config['STRIPE_API_KEY']
    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        mode='subscription',
        line_items=[{
            'price': current_app.config['STRIPE_PRICE_ID'],  # replace with your price ID
            'quantity': 1,
        }],
        success_url=url_for('main.success', _external=True) + '?session_id={CHECKOUT_SESSION_ID}',
        cancel_url=url_for('main.cancel', _external=True),  # you'll want to make a cancel page too
        customer_email=current_user.email,
        metadata={
            'user_id': current_user.id
        }
)
    
    return redirect(session.url, code=303)



@main.route('/success')
def success():
    session_id = request.args.get('session_id')
    if not session_id:
        return redirect(url_for('main.dashboard'))

    session = stripe.checkout.Session.retrieve(session_id)
    customer = stripe.Customer.retrieve(session.customer)

    return render_template('success.html', customer_email=customer.email)


@main.route('/cancel')
def cancel():
    return 'Platba bola zrušená.'






# Registration and Login Routes


@main.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data
        )
        user.set_password(form.password.data)

        db.session.add(user)
        db.session.commit()
        flash('Registrácia prebehla úspešne!', 'success')
        return redirect(url_for('main.login'))

    return render_template('register.html', form=form)







@main.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        print("Form validated")
        user = User.query.filter_by(email=form.email.data).first()
        
        if user and check_password_hash(user.password_hash, form.password.data):
            login_user(user)
            print("Login successful")
            return redirect(url_for('main.dashboard'))
        else:
            print("Invalid credentials")
    else:
        print("Form errors:", form.errors)

    return render_template('login.html', form=form)



@main.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Bol si odhlásený.', 'info')
    return redirect(url_for('main.login'))



@main.route('/dashboard')
@login_required
def dashboard():
    q = (request.args.get('q') or '').strip()

    query = (Invoice.query
             .join(Client, Client.id == Invoice.client_id)
             .filter(Invoice.user_id == current_user.id))

    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Invoice.invoice_number.ilike(like),
            Client.name.ilike(like),
            Invoice.currency.ilike(like)
        ))

    invoices = (query
                .order_by(Invoice.date.desc(), Invoice.id.desc())
                .limit(10)             # <-- max 10
                .all())

    return render_template('dashboard.html',
                           invoices=invoices,
                           q=q,
                           InvoiceStatus=InvoiceStatus)


@main.route('/status-by-client')
@login_required
def status_by_client():
    months = int(request.args.get("months", 12))
    top_n = int(request.args.get("top", 8))
    since = date.today() - timedelta(days=30 * months)

    # Sum per client & status
    rows = (
        Invoice.query
        .join(Client, Client.id == Invoice.client_id)
        .with_entities(
            Client.id.label("client_id"),
            Client.name.label("client"),
            Invoice.status.label("status"),
            func.sum(Invoice.total_cost).label("amount")
        )
        .filter(
            Invoice.user_id == current_user.id,
            Invoice.date >= since
        )
        .group_by(Client.id, Client.name, Invoice.status)
        .all()
    )

    # Pivot to {client: {"paid": x, "unpaid": y}}
    agg = {}
    for r in rows:
        c = agg.setdefault((r.client_id, r.client), {"paid": 0.0, "unpaid": 0.0})
        if r.status == InvoiceStatus.paid:
            c["paid"] += float(r.amount or 0)
        elif r.status == InvoiceStatus.unpaid:
            c["unpaid"] += float(r.amount or 0)
        # canceled ignored for cash picture

    # Sort by total (paid + unpaid) desc
    items = [ (cid, name, v["paid"], v["unpaid"]) for (cid, name), v in agg.items() ]
    items.sort(key=lambda t: t[2] + t[3], reverse=True)

    # Top N + Others
    top = items[:top_n]
    others = items[top_n:]
    if others:
        others_paid = round(sum(t[2] for t in others), 2)
        others_unpaid = round(sum(t[3] for t in others), 2)
        top.append( (None, "Others", others_paid, others_unpaid) )

    labels = [name for _, name, _, _ in top]
    paid =   [round(p, 2) for _, _, p, _ in top]
    unpaid = [round(u, 2) for _, _, _, u in top]

    return jsonify({
        "labels": labels,
        "datasets": [
            {"label": "Paid", "data": paid},
            {"label": "Unpaid", "data": unpaid},
        ],
        "currency": "EUR"
    })


@main.route('/')
@login_required
def index():
    return render_template('my_company.html')

@main.route('/invoice/<int:invoice_id>/download')
@login_required
def download_invoice(invoice_id):
    invoice = Invoice.query.filter_by(id=invoice_id, user_id=current_user.id).first_or_404()

    # compute amount (same as view_invoice)
    base = Decimal(str(invoice.total_cost or 0))
    if getattr(invoice.company, "is_vat_payer", False):
        vat_rate = Decimal(str(invoice.vat_rate or 0)) / Decimal("100")
        amount_due = (base * (Decimal("1") + vat_rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        amount_due = base.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    qr_svg = None
    if invoice.company and invoice.company.iban:
        amount_for_qr = amount_due if amount_due >= Decimal("0.01") else None
        qr_svg = epc_qr_svg(
            recipient_name=invoice.company.name,
            iban=invoice.company.iban,
            bic=invoice.company.bic,
            amount_eur=amount_for_qr,
            text=f"Invoice {invoice.invoice_number}"
        )

    context = {
        "invoice": invoice,
        "qr_svg": qr_svg,   # 👈 add QR to context
    }

    pdf_path = render_invoice_to_pdf("invoice_pdf.html", context)
    return send_file(pdf_path, as_attachment=True)




def send_invoice_email(invoice, client, company):
    # Kontext pre HTML renderovanie PDF
    context = {
        "invoice_data": invoice,
        "client_data": client,
        "company_data": company
    }

    # Vytvorenie dočasného PDF súboru
    pdf_path = render_invoice_to_pdf("invoice_pdf.html", context)

    try:
        msg = Message(
            subject=f"Faktúra č. {invoice.invoice_number}",
            recipients=['ferko.lizak69@gmail.com'],  # ← Reálne použitie
            body=f"Dobrý deň,\n\nV prílohe vám posielam  faktúru {invoice.invoice_number}."
        )

        with open(pdf_path, "rb") as fp:
            msg.attach(f"{invoice.invoice_number}.pdf", "application/pdf", fp.read())

        mail.send(msg)
        print(f"[✓] Email odoslaný na {msg.recipients}")


        return f"✅ Faktúra {invoice.invoice_number} bola úspešne odoslaná na {client.email}."

    except Exception as e:
        print(f"[✗] Chyba pri odosielaní e-mailu: {str(e)}")
        return f"❌ Chyba pri odosielaní e-mailu: {str(e)}"

    finally:
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
def get_client_by_name(data):
    all_clients = Client.query.filter_by(user_id=current_user.id)
    names = [client.name for client in all_clients]
    client_name_from_ai = data.get('client_name')
    if not client_name_from_ai:
        return None
    closest_matches = get_close_matches(client_name_from_ai, names, n=1, cutoff=0.6)
    if closest_matches:
        return Client.query.filter_by(user_id=current_user.id,name=closest_matches[0]).first()
    return None

def generate_invoice_number():
    last_invoice = Invoice.query.filter_by(user_id=current_user.id).order_by(Invoice.id.desc()).first()
    new_number = (int(last_invoice.invoice_number.split("-")[-1]) + 1) if last_invoice else 1
    return f"INV-{datetime.now().year}-{new_number:04d}"

def create_invoice_from_ai_data(data):
    invoice_data = invoice_maker(data)
    if not invoice_data:
        return None

    client = get_client_by_name(invoice_data)
    if not client:
        return None

    company = Company.query.filter_by(user_id=current_user.id).first()
    if not company:
        return None

    # Spočítaj total_cost
    total_cost = sum(
        item["quantity"] * item["price_per_item"] for item in invoice_data["items"]
    )

    invoice = Invoice(
        invoice_number=generate_invoice_number(),
        date=datetime.strptime(invoice_data["date"], "%Y-%m-%d").date(),
        due_date=datetime.strptime(invoice_data["due_date"], "%Y-%m-%d").date(),
        currency=invoice_data["currency"],
        total_cost=total_cost,
        vat_rate=0.0,
        client_id=client.id,
        company_id=company.id,
        user_id=current_user.id,
        created_at=datetime.now(timezone.utc)
    )

    # Pridaj položky do faktúry
    for item in invoice_data["items"]:
        invoice.items.append(InvoiceItem(
            description=item["description"],
            quantity=item["quantity"],
            unit=item["unit"],
            price_per_item=item["price_per_item"],
            total_cost=item["quantity"] * item["price_per_item"]
        ))

    db.session.add(invoice)
    #send_invoice_email(invoice, client, company)
    db.session.commit()
    return invoice



@main.route('/clients')
@login_required
def list_clients():
    return render_template('clients.html', clients=db.session.query(Client).filter_by(user_id=current_user.id).all())

@main.route('/add_client', methods=['GET', 'POST'])
@login_required
def add_client():
    if request.method == 'POST':
        is_vat_payer = 'is_vat_payer' in request.form
        client = Client(
            name=request.form['name'],
            street=request.form['street'],
            city=request.form['city'],
            zip_code=request.form['zip'],
            country=request.form['country'],
            ico=request.form['ICO'],
            dic=request.form['DIC'],
            email=request.form['email'],
            user_id=current_user.id,
            phone=request.form['phone'],
            iban=request.form['iban'],
            bic=request.form['bic'],
            is_vat_payer=is_vat_payer,
            ic_dph=request.form.get('ic_dph') if 'is_vat_payer' in request.form else None
        )
        db.session.add(client)
        db.session.commit()
        return redirect(url_for('main.list_clients'))
    return render_template('add_client.html')

@main.route('/edit_client/<int:client_id>', methods=['GET', 'POST'])
@login_required
def edit_client(client_id):
    client = Client.query.filter_by(id=client_id,user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        client.name = request.form['name']
        client.street = request.form['street']
        client.city = request.form['city']
        client.zip_code = request.form['zip']
        client.country = request.form['country']
        client.ico = request.form['ICO']
        client.dic = request.form['DIC']
        client.email = request.form['email']
        client.phone = request.form['phone']
        client.iban = request.form['iban']
        client.bic = request.form['bic']
        client.is_vat_payer = 'is_vat_payer' in request.form
        client.ic_dph = request.form.get('ic_dph') if client.is_vat_payer else None
        db.session.commit()
        return redirect(url_for('main.list_clients'))
    return render_template('edit_client.html', client=client)

@main.route('/delete_client/<int:client_id>', methods=['POST'])
@login_required
def delete_client(client_id):
    client = Client.query.filter_by(id=client_id, user_id=current_user.id).first_or_404()
    db.session.delete(client)
    db.session.commit()
    return redirect(url_for('main.list_clients'))

@main.route("/my_company", methods=['GET', 'POST'])
@login_required
def my_company():
    company = Company.query.filter_by(user_id=current_user.id).first()

    if request.method == 'POST':
        if not company:
            company = Company(user_id=current_user.id)
            db.session.add(company)

        company.name = request.form['name']
        company.street = request.form['street']
        company.city = request.form['city']
        company.zip_code = request.form['zip_code']
        company.country = request.form['country']
        company.ico = request.form['ico']
        company.dic = request.form['dic']
        company.email = request.form['email']
        company.phone = request.form['phone']
        company.iban = request.form['iban']
        company.bic = request.form['bic']
        company.is_vat_payer = request.form['is_vat_payer'] == 'True'
        company.ic_dph = request.form.get('ic_dph', '').strip() if company.is_vat_payer else None

        db.session.commit()
        flash("Údaje o firme boli úspešne uložené.", "success")
        return redirect(url_for('main.my_company'))

    return render_template('my_company.html', company=company)


@main.route("/invoice/<int:id>/mark_paid", methods=["POST"])
@login_required
def mark_invoice_paid(id):
    invoice = Invoice.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    invoice.status = "paid"   # assuming status is String, not Enum
    db.session.commit()
    flash(f"Faktúra {invoice.invoice_number} bola označená ako zaplatená.", "success")
    return redirect(url_for("main.list_invoices"))

@main.route("/invoice/<int:id>/overdue")
@login_required
def mark_invoice_overdue(id):
    invoice = Invoice.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    if invoice.status == "paid":
        flash(f"Faktúra {invoice.invoice_number} je už zaplatená a nemôže byť označená ako oneskorená.", "warning")
        return redirect(url_for("main.list_invoices"))
    if invoice.due_date >= datetime.now(timezone.utc).date():
        flash(f"Faktúra {invoice.invoice_number} ešte nie je po termíne splatnosti.", "warning")
        return redirect(url_for("main.list_invoices"))
    # Ak je faktúra oneskorená, nastavíme status na "overdue"
    invoice.status = "overdue"  # assuming status is String, not Enum
    db.session.commit()
    flash(f"Faktúra {invoice.invoice_number} bola označená ako oneskorená.", "success")
    return redirect(url_for("main.list_invoices"))

def next_invoice_number(user_id: int, d: date | None = None) -> str:
    d = d or date.today()
    y = d.year
    # INSERT ... ON CONFLICT ... DO UPDATE ... RETURNING last_no
    sql = text("""
        INSERT INTO invoice_counters (user_id, year, last_no)
        VALUES (:uid, :y, 0)
        ON CONFLICT(user_id, year) DO UPDATE SET last_no = last_no + 1
        RETURNING last_no
    """)
    res = db.session.execute(sql, {"uid": user_id, "y": y}).scalar_one()
    return f"{y}-{int(res):04d}"


@main.route('/add_invoice', methods=['GET', 'POST'])
@login_required
def add_invoice():
    clients = Client.query.filter_by(user_id=current_user.id).all()
    companies = Company.query.filter_by(user_id=current_user.id).all()

    if request.method == 'POST':
        # --- 1) číslo faktúry: normalizácia + preflight unikátnosti ---
        invoice_number = (request.form.get('invoice_number') or '').strip().upper()
        if not invoice_number:
            flash('Vyplň číslo faktúry (alebo si sprav autogeneráciu).', 'danger')
            return render_template('add_invoice.html', clients=clients, companies=companies)

        dup = db.session.query(
            db.exists().where(and_(
                Invoice.user_id == current_user.id,
                Invoice.invoice_number == invoice_number
            ))
        ).scalar()
        if dup:
            flash('Toto číslo faktúry už používaš. Zvoľ iné.', 'danger')
            return render_template('add_invoice.html', clients=clients, companies=companies)

        # --- 2) validácia klienta/firmy: musia patriť userovi ---
        try:
            client_id = int(request.form['client_id'])
            company_id = int(request.form['company_id'])
        except Exception:
            flash('Vyber klienta a firmu.', 'danger')
            return render_template('add_invoice.html', clients=clients, companies=companies)

        client_ok = Client.query.filter_by(id=client_id, user_id=current_user.id).first()
        company_ok = Company.query.filter_by(id=company_id, user_id=current_user.id).first()
        if not client_ok or not company_ok:
            abort(403)

        # --- 3) položky: vyčisti prázdne riadky + spočítaj total (Decimal) ---
        descriptions = request.form.getlist('description[]')
        quantities   = request.form.getlist('quantity[]')
        units        = request.form.getlist('unit[]')
        prices       = request.form.getlist('price_per_item[]')

        items: list[InvoiceItem] = []
        total_cost = Decimal('0.00')

        for desc, qty, unit, price in zip(descriptions, quantities, units, prices):
            desc = (desc or '').strip()
            unit = (unit or '').strip()
            if not desc or not qty or not price:
                continue
            try:
                # quantity máš v modeli Integer → drž sa int
                q = int(Decimal(str(qty)))
                p = Decimal(str(price))
            except Exception:
                continue
            if q <= 0 or p < 0:
                continue

            item_total = (p * q).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            items.append(InvoiceItem(
                description=desc,
                quantity=q,
                unit=unit,
                price_per_item=float(p),
                total_cost=float(item_total)
            ))
            total_cost += item_total

        if not items:
            flash('Pridaj aspoň jednu platnú položku.', 'danger')
            return render_template('add_invoice.html', clients=clients, companies=companies)

        # --- 4) vytvor invoice ---
        try:
            date_obj = datetime.strptime(request.form['date'], '%Y-%m-%d').date()
            due_obj  = datetime.strptime(request.form['due_date'], '%Y-%m-%d').date()
        except Exception:
            flash('Dátum alebo splatnosť sú neplatné.', 'danger')
            return render_template('add_invoice.html', clients=clients, companies=companies)

        vat_rate = request.form.get('vat_rate', '0').strip()
        try:
            vat_rate = float(vat_rate or 0.0)
        except Exception:
            vat_rate = 0.0



        pm_raw = (request.form.get('payment_method') or 'bank_transfer').strip()
        allowed = {'bank_transfer','cash','card','other'}
        if pm_raw not in allowed:
            pm_raw = 'bank_transfer'

        invoice = Invoice(
            invoice_number=invoice_number,
            date=date_obj,
            due_date=due_obj,
            currency=request.form['currency'],
            vat_rate=vat_rate,
            total_cost=float(total_cost),  # čistá suma podľa položiek (bez DPH, ak to tak máš)
            user_id=current_user.id,
            client_id=client_id,
            company_id=company_id,
            created_at=datetime.now(timezone.utc),
            status=InvoiceStatus.unpaid,
            payment_method=PaymentMethod(pm_raw)   # ← sem

        )

        db.session.add(invoice)
        # napoj položky cez relationship (žiadny ručný assign id)
        for item in items:
            invoice.items.append(item)

        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            # DB fallback – ak medzičasom niekto (ty v druhom tabu) zaregistroval rovnaké číslo
            flash('Toto číslo faktúry už používaš (DB). Zvoľ iné.', 'danger')
            return render_template('add_invoice.html', clients=clients, companies=companies)

        return redirect(url_for('main.view_invoice', invoice_id=invoice.id))

    # GET
    return render_template('add_invoice.html', clients=clients, companies=companies)

@main.route('/show_ai_invoice/<int:invoice_id>', methods=['GET', 'POST'])
@login_required
def view_ai_invoice(invoice_id):
    invoice = Invoice.query.filter_by(id=invoice_id, user_id=current_user.id).first_or_404()
    client = invoice.client
    company = invoice.company

    if request.method == 'POST':
        try:
            send_invoice_email(invoice, client, company)
            flash('Email odoslaný!', 'success')
            return redirect(url_for('main.list_invoices'))  # optional
        except Exception as e:
            flash(f'Chyba pri odosielaní emailu: {str(e)}', 'danger')

    return render_template(
        "show_ai_invoice.html",
        invoice_data=invoice,
        client_data=client,
        company_data=company,
        items=invoice.items
    )

def _epc_amount(value):
    """Vrátí částku pro EPC (float) nebo None, když je nevalidní."""
    if value is None:
        return None
    try:
        amt = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError):
        return None
    # EPC min je 0.01; horní limit nech konzervativní
    if amt < Decimal("0.01") or amt > Decimal("999999999.99"):
        return None
    return float(amt)

def epc_qr_svg(*, recipient_name: str, iban: str,
               amount_eur: Decimal | None, text: str,
               bic: str | None = None, scale: int = 4) -> str | None:
    name = (recipient_name or "")[:70]
    rem_text = (text or "")[:140]
    iban_clean = (iban or "").replace(" ", "")
    if not iban_clean:
        return None  # bez IBAN QR nemá smysl

    # amount musí být vždy – pokud None nebo <0.01 → 0.00
    if amount_eur is None or amount_eur < Decimal("0.01"):
        amt = Decimal("0.00")
    else:
        amt = amount_eur.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    qr = segno_helpers.make_epc_qr(
        name=name,
        iban=iban_clean,
        bic=bic or None,
        amount=amt,          # 👈 vždy předáme
        text=rem_text,
        encoding='UTF-8',
    )

    buf = io.BytesIO()
    qr.save(buf, kind="svg", scale=scale, xmldecl=False)
    return buf.getvalue().decode("utf-8")



@main.route("/inoices/<int:invoice_id>/edit", methods=["GET","POST"])
@login_required
def edit_invoice(invoice_id):
    inv = Invoice.query.get_or_404(invoice_id)
    # ownership/permissions
    if inv.user_id != current_user.id:
        abort(403)
    if inv.status != InvoiceStatus.unpaid:
        flash("Faktúru možno upravovať len v stave 'draft'.", "warning")
        return redirect(url_for('main.view_invoice', invoice_id=invoice_id))

    if request.method == "POST":
        # Basic fields
        inv.invoice_number = request.form.get("invoice_number", inv.invoice_number)
        inv.date = _parse_date(request.form.get("date"), inv.date)
        inv.due_date = _parse_date(request.form.get("due_date"), inv.due_date)
        inv.payment_method = request.form.get("payment_method") or inv.payment_method
        inv.vat_rate = float(request.form.get("vat_rate") or inv.vat_rate or 0)
        inv.currency = request.form.get("currency") or inv.currency

        # Company / Client (optional: lock company, only allow client changes)
        inv.client.name   = request.form.get("client_name")   or inv.client.name
        inv.client.street = request.form.get("client_street") or inv.client.street
        inv.client.city   = request.form.get("client_city")   or inv.client.city
        inv.client.zip_code = request.form.get("client_zip")  or inv.client.zip_code
        inv.client.country  = request.form.get("client_country") or inv.client.country
        inv.client.ico    = request.form.get("client_ico")    or inv.client.ico
        inv.client.dic    = request.form.get("client_dic")    or inv.client.dic
        inv.client.ic_dph = request.form.get("client_ic_dph") or inv.client.ic_dph

        # Replace items safely
        # 1) delete existing items (draft only)
        InvoiceItem.query.filter_by(invoice_id=inv.id).delete()

        # 2) rebuild from posted rows (items[0][...], items[1][...], …)
        rows = []
        i = 0
        while True:
            prefix = f"items[{i}]"
            desc = request.form.get(f"{prefix}[description]")
            if desc is None:
                break
            qty  = request.form.get(f"{prefix}[quantity]")
            unit = request.form.get(f"{prefix}[unit]")
            ppi  = request.form.get(f"{prefix}[price_per_item]")
            if desc.strip():
                try:
                    qty_f = float(qty or 0)
                    ppi_f = float(ppi or 0)
                    rows.append(InvoiceItem(
                        invoice_id=inv.id,
                        description=desc.strip(),
                        quantity=qty_f,
                        unit=(unit or "").strip(),
                        price_per_item=ppi_f,
                        total_cost=round(qty_f * ppi_f, 2),
                    ))
                except ValueError:
                    flash("Neplatné číslo v položkách.", "danger")
                    return redirect(request.url)
            i += 1

        db.session.add_all(rows)

        # Recompute totals server-side (don’t trust the browser)
        inv.total_cost = sum(it.total_cost for it in rows)

        try:
            db.session.commit()
            flash("Faktúra bola upravená.", "success")
            return redirect(url_for('main.view_invoice', invoice_id=inv.id))
        except IntegrityError:
            db.session.rollback()
            flash("Chyba pri ukladaní. Skontroluj duplicitu čísla faktúry a formát dát.", "danger")

    # GET: render edit form prefilled
    return render_template("edit_invoice.html", invoice=inv)





@main.route('/invoice/<int:invoice_id>')
@login_required
def view_invoice(invoice_id):
    invoice = (Invoice.query
        .options(joinedload(Invoice.company), joinedload(Invoice.client), joinedload(Invoice.items))
        .filter(Invoice.id==invoice_id, Invoice.user_id==current_user.id)
        .first_or_404())

    # základ a DPH bezpečně
    base = _D(invoice.total_cost)  # když None → 0
    if getattr(invoice.company, "is_vat_payer", False):
        vat_rate = _D(invoice.vat_rate) / Decimal("100")
        amount_due = (base * (Decimal("1") + vat_rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    else:
        amount_due = base.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    qr_svg = None
    if invoice.company and invoice.company.iban:
        # pokud je částka < 0.01, QR bude bez částky (validní EPC)
        amount_for_qr = amount_due if amount_due >= Decimal("0.01") else '0.00'
        qr_svg = epc_qr_svg(
            recipient_name=invoice.company.name,
            iban=invoice.company.iban,
            bic=invoice.company.bic,
            amount_eur=amount_for_qr,  # může být None
            text=f"Invoice {invoice.invoice_number}"
        )

    return render_template("invoice.html", invoice=invoice, qr_svg=qr_svg)


@main.route('/invoices')
@login_required
def list_invoices():
    invoices = Invoice.query.filter_by(user_id=current_user.id).all()
    return render_template(
        'invoices.html',
        invoices=invoices,
        InvoiceStatus=InvoiceStatus  # tu pošleš enum do šablóny
    )

@main.route('/ai_invoice', methods=['GET', 'POST'])
@login_required
def ai_invoice():
    if not current_user.is_paid:
        flash("Potrebujete aktívne predplatné pre AI funkciu.", "danger")
        return redirect(url_for('main.pricing'))
    else:
        if request.method == 'POST':
            invoice_description = request.form.get('invoice_description')
            invoice = create_invoice_from_ai_data(invoice_description)
            if not invoice:
                return render_template('ai_invoice.html', error="Failed to create invoice. Please check the input data.")
            return redirect(url_for('main.view_ai_invoice', invoice_id=invoice.id))
    return render_template('ai_invoice.html')

@main.route('/delete_invoice/<int:invoice_id>', methods=['POST'])
@login_required
def delete_invoice(invoice_id):
    invoice = Invoice.query.filter_by(id=invoice_id, user_id=current_user.id).first_or_404()
    db.session.delete(invoice)
    db.session.commit()
    return redirect(url_for('main.list_invoices'))


