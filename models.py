from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
from app import db



class InvoiceItem(db.Model):
    __tablename__ = 'invoice_items'
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoices.id'), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit=db.Column(db.String(50), nullable=False)  # e.g., "pcs", "kg", etc.
    price_per_item = db.Column(db.Float, nullable=False)
    total_cost = db.Column(db.Float, nullable=False)

    invoice = db.relationship("Invoice", back_populates="items")



class Client(db.Model):
        __tablename__ = 'clients'
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(100), nullable=False)        
        ico = db.Column(db.String(20), nullable=False)
        dic = db.Column(db.String(20), nullable=False)
        street = db.Column(db.String(100), nullable=False)
        city = db.Column(db.String(50), nullable=False)
        zip_code = db.Column(db.String(20), nullable=False)
        country = db.Column(db.String(50), nullable=False)
        email = db.Column(db.String(100), nullable=False)       
        phone = db.Column(db.String(20), nullable=False)
        iban = db.Column(db.String(34), nullable=False)
        bic = db.Column(db.String(11), nullable=False)
        payment_method = db.Column(db.String(50), nullable=False)
        is_vat_payer = db.Column(db.Boolean, default=False)
        ic_dph = db.Column(db.String(20), nullable=True)  # Optional field for VAT ID if the client is a VAT payer






class Invoice(db.Model):
        __tablename__ = 'invoices'
        id = db.Column(db.Integer, primary_key=True)
        invoice_number = db.Column(db.String(50), nullable=False)
        date = db.Column(db.Date, nullable=False)
        due_date = db.Column(db.Date, nullable=False)
        currency = db.Column(db.String(10), nullable=False)
        total_cost = db.Column(db.Float, nullable=False)  # Total cost calculated as quantity
        vat_rate = db.Column(db.Float, nullable=True, default=0.0)  # VAT rate in percentage
        client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
        company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)  # Foreign key to the company
        company= db.relationship('Company', backref=db.backref('invoices', lazy=True))
        client = db.relationship('Client', backref=db.backref('invoices', lazy=True))
        items = db.relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")

        created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))  # Timestamp when the invoice was created
        

     

class Company(db.Model):
        __tablename__ = 'companies'
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(100), nullable=False)        
        ico = db.Column(db.String(20), nullable=False)
        dic = db.Column(db.String(20), nullable=False)
        street = db.Column(db.String(100), nullable=False)
        city = db.Column(db.String(50), nullable=False)
        zip_code = db.Column(db.String(20), nullable=False)
        country = db.Column(db.String(50), nullable=False)
        email = db.Column(db.String(100), nullable=False)       
        phone = db.Column(db.String(20), nullable=False)
        iban = db.Column(db.String(34), nullable=False)
        bic = db.Column(db.String(11), nullable=False)
        payment_method = db.Column(db.String(50), nullable=False)
        is_vat_payer = db.Column(db.Boolean, default=False)
        ic_dph = db.Column(db.String(20), nullable=True)  # Optional field for VAT ID if the 
       