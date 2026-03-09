from flask import Blueprint, render_template, request, redirect, url_for,session, flash, send_file, abort, jsonify, current_app,send_from_directory
from models import Client, Invoice, Company, InvoiceItem, User, InvoiceStatus, PaymentMethod, InvoiceCounter
from datetime import datetime, timezone
from difflib import get_close_matches
from ai_chat import invoice_maker
from extensions import db, mail
from flask_mail import Message
from uuid import uuid4
from werkzeug.utils import secure_filename
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
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import io
from segno import helpers as segno_helpers
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from PIL import Image
import base64
import mimetypes




ALLOWED_EXT = {"jpg", "jpeg"}

def allowed_file(filename: str) -> bool:
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_EXT




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

@main.route('/')
def home():
    return render_template('home.html')




@main.route('/account')
@login_required
def account():
    return render_template('account.html',user=current_user)


@main.route('/pricing')
@login_required
def pricing():
    return render_template('pricing.html')

@main.route('/priceing')
@login_required
def priceing():
    return render_template('priceing.html')

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
    domain = request.url_root.rstrip('/')
    session = stripe.checkout.Session.create(
        payment_method_types=['card'],
        mode='subscription',
        line_items=[{
            'price': current_app.config['STRIPE_PRICE_ID'],  # replace with your price ID
            'quantity': 1,
        }],
        success_url=f"{domain}/success?session_id={{CHECKOUT_SESSION_ID}}",
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

    if invoice.company:
        stamp_abs = os.path.join(
            current_app.static_folder, 'uploads', f'stamp_{invoice.company.user_id}.png'
        )
        if os.path.exists(stamp_abs):
            mime, _ = mimetypes.guess_type(stamp_abs)
            mime = mime or "image/png"
            with open(stamp_abs, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            stamp_data_uri = f"data:{mime};base64,{b64}"
    context = {
        "invoice": invoice,
        "qr_svg": qr_svg,   
        "stamp_data_uri": stamp_data_uri

    }

    pdf_path = render_invoice_to_pdf("invoice_pdf.html", context)
    return send_file(pdf_path, as_attachment=True, download_name=f"{invoice.invoice_number}.pdf")


@main.route('/invoice/<int:invoice_id>/send_email', methods=['POST'])
@login_required
def send_invoice_email_route(invoice_id):
    invoice = Invoice.query.filter_by(id=invoice_id, user_id=current_user.id).first_or_404()
    try:
        result = send_invoice_email(invoice, attachment_file=request.files.get("attachment"))
        flash(result, 'success')
    except Exception as e:
        flash(f'Chyba při odesílání emailu: {str(e)}', 'danger')

    return redirect(url_for('main.view_invoice', invoice_id=invoice_id))


def send_invoice_email(invoice,attachment_file=None):
    # Kontext pre HTML renderovanie PDF
    context = {
        "invoice": invoice,
        "client": invoice.client,
        "company": invoice.company
    }

    # Vytvorenie dočasného PDF súboru
    pdf_path = render_invoice_to_pdf("invoice_pdf.html", context)
    temp_attachment_path = None
    original_attachment_name = None

    try:
        if attachment_file:
            temp_attachment_path, original_attachment_name = save_temp_attachment(attachment_file)
        msg = Message(
            subject=f"Faktúra č. {invoice.invoice_number}",
            recipients=[invoice.client.email],  # ← Reálne použitie
            body=f"Dobrý deň,\n\nV prílohe vám posielam  faktúru {invoice.invoice_number}."
        )

        with open(pdf_path, "rb") as fp:
            msg.attach(f"{invoice.invoice_number}.pdf", "application/pdf",fp.read())
        if temp_attachment_path:
            ext = os.path.splitext(original_attachment_name)[1].lower()

            content_type_map = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".pdf": "application/pdf",
            }
            with open(temp_attachment_path, "rb") as fp:
                msg.attach(
                    original_attachment_name,
                    content_type_map.get(ext, "application/octet-stream"),
                    fp.read())

        mail.send(msg)
        print(f"[✓] Email odoslaný na {msg.recipients}")


        return f"✅ Faktúra {invoice.invoice_number} bola úspešne odoslaná na {invoice.client.email}."

    except Exception as e:
        print(f"[✗] Chyba pri odosielaní e-mailu: {str(e)}")
        return f"❌ Chyba pri odosielaní e-mailu: {str(e)}"

    finally:
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        if temp_attachment_path and os.path.exists(temp_attachment_path):
            os.remove(temp_attachment_path)
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".pdf"}
def save_temp_attachment(file):
    if not file or not file.filename:
        return None, None

    original_name = secure_filename(file.filename)
    ext = os.path.splitext(original_name)[1].lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Nepovolený typ súboru.")

    upload_dir = current_app.config["UPLOAD_FOLDER"]
    os.makedirs(upload_dir, exist_ok=True)

    temp_name = f"{uuid4().hex}{ext}"
    file_path = os.path.join(upload_dir, temp_name)
    file.save(file_path)

    return file_path, original_name
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
#-----------------------stamp
        file=request.files.get('stamp')

        if file and file.filename:
            if '.' in file.filename:
                ext = file.filename.rsplit('.', 1)[1].lower()
            else:
                ext = ''
            ext=file.filename.rsplit('.',1)[1].lower()
            if ext not in current_app.config['ALLOWED_STAMP_EXT']:
                flash('Nepovolený formát obrázka (použi PNG/JPG/WEBP).')
                return redirect(request.url)
            
            static_upload_dir = os.path.join(current_app.static_folder, 'uploads')
            os.makedirs(static_upload_dir, exist_ok=True)

            filename = f"stamp_{current_user.id}.png"
            save_path = os.path.join(static_upload_dir, filename)

            try:
                # 3) Načítanie obrázka + normalizácia do PNG (transparentné pozadie, menší rozmer)
                img = Image.open(file.stream).convert('RGBA')
                img.thumbnail((800, 800))
                img.save(save_path, format='PNG', optimize=True)

            except Exception as e:
                current_app.logger.exception("Stamp upload failed")
                flash('Súbor neviem spracovať ako obrázok.', 'danger')
                return redirect(request.url)
            company.stamp_url = url_for('static', filename=f'uploads/{filename}', _external=False)


        db.session.commit()
        flash("Údaje o firme boli úspešne uložené.", "success")
        return redirect(url_for('main.my_company'))

    return render_template('my_company.html', company=company)

@main.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)



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
                q = Decimal(str(qty))
                p = Decimal(str(price))
            except Exception:
                continue
            if q <= 0 or p < 0:
                continue

            item_total = (p * q).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            items.append(InvoiceItem(
                description=desc,
                quantity=float(q),
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

        
        set_variable_symbol= request.form.get('variable_symbol')
        if set_variable_symbol:
            variable_symbol=set_variable_symbol
        else:
            variable_symbol=invoice_number

        pm_raw = (request.form.get('payment_method') or 'bank_transfer').strip()
        allowed = {'bank_transfer','cash','card','other'}
        if pm_raw not in allowed:
            pm_raw = 'bank_transfer'

        invoice = Invoice(
            invoice_number=invoice_number,
            variable_symbol=variable_symbol,
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





def _to_decimal(val, default="0"):
    if val is None:
        val = default
    if isinstance(val, (int, float, Decimal)):
        # str() avoids binary float artifacts
        val = str(val)
    # normalize "12,34" -> "12.34"
    val = val.strip().replace(",", ".")
    try:
        return Decimal(val)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Invalid numeric input")

def _money(val):
    return _to_decimal(val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def _qty(val):
    # keep 3 decimals if you want, or 2
    return _to_decimal(val).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

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
        inv.variable_symbol = request.form.get("variable_symbol") or inv.variable_symbol

        # VAT as Decimal (percent)
        try:
            inv.vat_rate = _to_decimal(request.form.get("vat_rate", inv.vat_rate or "0"))
        except ValueError:
            flash("Neplatná DPH sadzba.", "danger")
            return redirect(request.url)
        inv.currency = request.form.get("currency") or inv.currency

        # Guard client exists
        if not inv.client:
            flash("Klient nie je priradený.", "danger")
            return redirect(request.url)

        inv.client.name   = request.form.get("client_name")   or inv.client.name
        inv.client.street = request.form.get("client_street") or inv.client.street
        inv.client.city   = request.form.get("client_city")   or inv.client.city
        inv.client.zip_code = request.form.get("client_zip")  or inv.client.zip_code
        inv.client.country  = request.form.get("client_country") or inv.client.country
        inv.client.ico    = request.form.get("client_ico")    or inv.client.ico
        inv.client.dic    = request.form.get("client_dic")    or inv.client.dic
        inv.client.ic_dph = request.form.get("client_ic_dph") or inv.client.ic_dph

        # Replace items
        descriptions = request.form.getlist('description[]')
        quantities   = request.form.getlist('quantity[]')
        units        = request.form.getlist('unit[]')
        prices       = request.form.getlist('price_per_item[]')

        rows = []
        total_cost = Decimal("0.00")

        

        for i, (desc, qty, unit, price) in enumerate(zip(descriptions, quantities, units, prices), start=1):
            desc = (desc or "").strip()
            unit = (unit or "").strip()
            if not desc:
                continue

            q = _to_decimal(qty)
            p = _to_decimal(price)
            if q is None or p is None or q <= 0 or p < 0:
                flash(f"Neplatná položka {i}.", "danger")
                return redirect(request.url)

            # precision: quantity 3dp, price 2dp, total 2dp
            q = q.quantize(Decimal("0.001"))
            p = p.quantize(Decimal("0.01"))
            line_total = (q * p).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            rows.append(InvoiceItem(
                invoice_id=inv.id,
                description=desc,
                quantity=q,           # keep Decimal if your model uses Numeric(asdecimal=True)
                unit=unit,
                price_per_item=p,
                total_cost=line_total
            ))
            total_cost += line_total

        if not rows:
            flash("Žiadne platné položky neboli odoslané.", "danger")
            return redirect(request.url)

        # Only now replace existing items
        InvoiceItem.query.filter_by(invoice_id=inv.id).delete()
        db.session.add_all(rows)

        inv.total_cost = total_cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
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


