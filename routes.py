from flask import Blueprint, render_template, request, redirect, url_for
from models import Client, Invoice, Company
from datetime import datetime, timezone
from difflib import get_close_matches
from ai_chat import invoice_maker
from extensions import db, mail
from flask_mail import Message
from pdf_generator import render_invoice_to_pdf
import os

main = Blueprint('main', __name__)

@main.route('/')
def index():
    return render_template('my_company.html')

@main.route('/invoice/<int:invoice_id>/download')
def download_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
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
    all_clients = Client.query.all()
    names = [client.name for client in all_clients]
    client_name_from_ai = data.get('client_name')
    if not client_name_from_ai:
        return None
    closest_matches = get_close_matches(client_name_from_ai, names, n=1, cutoff=0.6)
    if closest_matches:
        return Client.query.filter_by(name=closest_matches[0]).first()
    return None

def generate_invoice_number():
    last_invoice = Invoice.query.order_by(Invoice.id.desc()).first()
    new_number = (int(last_invoice.invoice_number.split("-")[-1]) + 1) if last_invoice else 1
    return f"INV-{datetime.now().year}-{new_number:04d}"

def create_invoice_from_ai_data(data):
    invoice_data = invoice_maker(data)
    if not invoice_data:
        return None
    client = get_client_by_name(invoice_data)
    if not client:
        return None
    company = Company.query.first()
    if not company:
        return None

    invoice = Invoice(
        invoice_number=generate_invoice_number(),
        date=datetime.strptime(invoice_data['date'], '%Y-%m-%d').date(),
        due_date=datetime.strptime(invoice_data['due_date'], '%Y-%m-%d').date(),
        description=invoice_data['description'],
        quantity=invoice_data['quantity'],
        unit=invoice_data['unit'],
        price_per_item=invoice_data['price_per_item'],
        currency=invoice_data['currency'],
        total_cost=invoice_data['total_cost'],
        vat_rate=0.0,
        client_id=client.id,
        company_id=company.id,
        created_at=datetime.now(timezone.utc)
    )

    db.session.add(invoice)
    send_invoice_email(invoice, client, company)
    db.session.commit()
    return invoice


@main.route('/clients')
def list_clients():
    return render_template('clients.html', clients=Client.query.all())

@main.route('/add_client', methods=['GET', 'POST'])
def add_client():
    if request.method == 'POST':
        client = Client(
            name=request.form['name'],
            street=request.form['street'],
            city=request.form['city'],
            zip_code=request.form['zip'],
            country=request.form['country'],
            ico=request.form['ICO'],
            dic=request.form['DIC'],
            email=request.form['email'],
            phone=request.form['phone'],
            iban=request.form['iban'],
            bic=request.form['bic'],
            payment_method=request.form['payment_method'],
            is_vat_payer='is_vat_payer' in request.form,
            ic_dph=request.form.get('ic_dph') if 'is_vat_payer' in request.form else None
        )
        db.session.add(client)
        db.session.commit()
        return redirect(url_for('main.list_clients'))
    return render_template('add_client.html')

@main.route('/edit_client/<int:client_id>', methods=['GET', 'POST'])
def edit_client(client_id):
    client = Client.query.get_or_404(client_id)
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
def delete_client(client_id):
    client = Client.query.get_or_404(client_id)
    db.session.delete(client)
    db.session.commit()
    return redirect(url_for('main.list_clients'))

@main.route("/my_company", methods=['GET', 'POST'])
def my_company():
    if request.method == 'POST':
        existing = Company.query.first()
        if existing:
            db.session.delete(existing)
            db.session.commit()

        company = Company(
            name=request.form['name'],
            street=request.form['street'],
            city=request.form['city'],
            zip_code=request.form['zip_code'],
            country=request.form['country'],
            ico=request.form['ico'],
            dic=request.form['dic'],
            email=request.form['email'],
            phone=request.form['phone'],
            iban=request.form['iban'],
            bic=request.form['bic'],
            payment_method=request.form['payment_method'],
            is_vat_payer=request.form['is_vat_payer'] == 'True',
            ic_dph=request.form.get('ic_dph', '').strip() if request.form['is_vat_payer'] == 'True' else None
        )
        db.session.add(company)
        db.session.commit()
        message = "Údaje o firme boli úspešne uložené."
        return render_template('my_company.html', message=message, company=company)

    return render_template('my_company.html', company=Company.query.first())

@main.route('/add_invoice', methods=['GET', 'POST'])
def add_invoice():
    clients = Client.query.all()
    companies = Company.query.all()
    if request.method == 'POST':
        invoice = Invoice(
            invoice_number=request.form['invoice_number'],
            date=datetime.strptime(request.form['date'], '%Y-%m-%d').date(),
            due_date=datetime.strptime(request.form['due_date'], '%Y-%m-%d').date(),
            description=request.form['description'],
            quantity=float(request.form['quantity']),
            unit=request.form['unit'],
            price_per_item=float(request.form['price_per_item']),
            currency=request.form['currency'],
            total_cost=float(request.form['quantity']) * float(request.form['price_per_item']),
            vat_rate=float(request.form.get('vat_rate', 0.0)),
            client_id=int(request.form['client_id']),
            company_id=int(request.form['company_id']),
            created_at=datetime.now(timezone.utc)
        )
        db.session.add(invoice)
        db.session.commit()
        return redirect(url_for('main.view_invoice', invoice_id=invoice.id))
    return render_template('add_invoice.html', clients=clients, companies=companies)

@main.route('/invoice/<int:invoice_id>')
def view_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    if not invoice.company:
        return "Company information is not set up. Please set up your company first.", 400
    return render_template("invoice.html", invoice_data=invoice, client_data=invoice.client, company_data=invoice.company)

@main.route('/invoices')
def list_invoices():
    return render_template('invoices.html', invoices=Invoice.query.all())

@main.route('/ai_invoice', methods=['GET', 'POST'])
def ai_invoice():
    if request.method == 'POST':
        invoice_description = request.form.get('invoice_description')
        invoice = create_invoice_from_ai_data(invoice_description)
        if not invoice:
            return render_template('ai_invoice.html', error="Failed to create invoice. Please check the input data.")
        return redirect(url_for('main.view_invoice', invoice_id=invoice.id))
    return render_template('ai_invoice.html')

@main.route('/delete_invoice/<int:invoice_id>', methods=['POST'])
def delete_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    db.session.delete(invoice)
    db.session.commit()
    return redirect(url_for('main.list_invoices'))



