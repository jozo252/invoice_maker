from flask import Blueprint, render_template, request, redirect, url_for,session, flash, send_file, abort
from models import Client, Invoice, Company, InvoiceItem, User
from datetime import datetime, timezone
from difflib import get_close_matches
from ai_chat import invoice_maker
from extensions import db, mail
from flask_mail import Message
from pdf_generator import render_invoice_to_pdf
import os
from forms import RegistrationForm, LoginForm
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

main = Blueprint('main', __name__)


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
    invoices = Invoice.query.filter_by(user_id=current_user.id).order_by(Invoice.date.desc()).limit(5).all()
    return render_template('dashboard.html', invoices=invoices)





@main.route('/')
@login_required
def index():
    return render_template('my_company.html')

@main.route('/invoice/<int:invoice_id>/download')
@login_required
def download_invoice(invoice_id):
    invoice = Invoice.query.filter_by(id=invoice_id,user_id=current_user.id).first_or_404()
    context = {
        "invoice_data": invoice,
        "client_data": invoice.client,
        "company_data": invoice.company,
    }

    pdf_path = render_invoice_to_pdf("invoice.html", context)
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
            recipients=[client.email],  # ← Reálne použitie
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
    send_invoice_email(invoice, client, company)
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
            payment_method=request.form['payment_method'],
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
        client.payment_method = request.form['payment_method']
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
        company.payment_method = request.form['payment_method']
        company.is_vat_payer = request.form['is_vat_payer'] == 'True'
        company.ic_dph = request.form.get('ic_dph', '').strip() if company.is_vat_payer else None

        db.session.commit()
        flash("Údaje o firme boli úspešne uložené.", "success")
        return redirect(url_for('main.my_company'))

    return render_template('my_company.html', company=company)



@main.route('/add_invoice', methods=['GET', 'POST'])
@login_required
def add_invoice():
    clients = Client.query.filter_by(user_id=current_user.id).all()
    companies = Company.query.filter_by(user_id=current_user.id).all()


    if request.method == 'POST':
        items = []
        total_cost = 0

        descriptions = request.form.getlist('description[]')
        quantities = request.form.getlist('quantity[]')
        units = request.form.getlist('unit[]')
        prices = request.form.getlist('price_per_item[]')

        for desc, qty, unit, price in zip(descriptions, quantities, units, prices):
            qty = float(qty)
            price = float(price)
            item_total = qty * price
            total_cost += item_total

            items.append(InvoiceItem(
                description=desc,
                quantity=qty,
                unit=unit,
                price_per_item=price,
                total_cost=item_total
            ))

        invoice = Invoice(
            invoice_number=request.form['invoice_number'],
            date=datetime.strptime(request.form['date'], '%Y-%m-%d').date(),
            due_date=datetime.strptime(request.form['due_date'], '%Y-%m-%d').date(),
            currency=request.form['currency'],
            vat_rate=float(request.form.get('vat_rate', 0.0)),
            total_cost=total_cost,
            user_id=current_user.id,
            
            client_id=int(request.form['client_id']),
            company_id=int(request.form['company_id']),
            created_at=datetime.now(timezone.utc)
        )

        db.session.add(invoice)
        db.session.flush()  # vloží invoice.id bez commitu

        for item in items:
            item.invoice_id = invoice.id
            db.session.add(item)

        db.session.commit()
        return redirect(url_for('main.view_invoice', invoice_id=invoice.id))

    return render_template('add_invoice.html', clients=clients, companies=companies)

@main.route('/invoice/<int:invoice_id>')
@login_required
def view_invoice(invoice_id):
    invoice = Invoice.query.filter_by(id=invoice_id, user_id=current_user.id).first_or_404()
    if not invoice.company:
        return "Company information is not set up. Please set up your company first.", 400
    return render_template("invoice.html", invoice_data=invoice, client_data=invoice.client, company_data=invoice.company, items=invoice.items)

@main.route('/invoices')
@login_required
def list_invoices():
    return render_template('invoices.html', invoices=Invoice.query.filter_by(user_id=current_user.id).all())

@main.route('/ai_invoice', methods=['GET', 'POST'])
@login_required
def ai_invoice():
    if request.method == 'POST':
        invoice_description = request.form.get('invoice_description')
        invoice = create_invoice_from_ai_data(invoice_description)
        if not invoice:
            return render_template('ai_invoice.html', error="Failed to create invoice. Please check the input data.")
        return redirect(url_for('main.view_invoice', invoice_id=invoice.id))
    return render_template('ai_invoice.html')

@main.route('/delete_invoice/<int:invoice_id>', methods=['POST'])
@login_required
def delete_invoice(invoice_id):
    invoice = Invoice.query.filter_by(id=invoice_id, user_id=current_user.id).first_or_404()
    db.session.delete(invoice)
    db.session.commit()
    return redirect(url_for('main.list_invoices'))



