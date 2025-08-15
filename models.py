from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone,date
from app import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import enum
from sqlalchemy.ext.hybrid import hybrid_property



class User(db.Model,UserMixin):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    is_paid = db.Column(db.Boolean, default=False)
    stripe_customer_id = db.Column(db.String(100), nullable=True)



    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.email}>'
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
        user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
        user = db.relationship('User', backref=db.backref('clients', lazy=True))
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


class InvoiceStatus(enum.Enum):
    unpaid = "unpaid"
    paid = "paid"
    canceled = "canceled"



class Invoice(db.Model):
        __tablename__ = 'invoices'
        id = db.Column(db.Integer, primary_key=True)
        invoice_number = db.Column(db.String(50), nullable=False)
        date = db.Column(db.Date, nullable=False)
        due_date = db.Column(db.Date, nullable=False)
        user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
        user = db.relationship('User', backref=db.backref('invoices', lazy=True))
        currency = db.Column(db.String(10), nullable=False)
        total_cost = db.Column(db.Float, nullable=False)  # Total cost calculated as quantity
        vat_rate = db.Column(db.Float, nullable=True, default=0.0)  # VAT rate in percentage
        client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
        company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)  # Foreign key to the company
        company= db.relationship('Company', backref=db.backref('invoices', lazy=True))
        client = db.relationship('Client', backref=db.backref('invoices', lazy=True))
        items = db.relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")
        created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))  # Timestamp when the invoice was created
        status = db.Column(db.Enum(InvoiceStatus), nullable=False, default=InvoiceStatus.unpaid)
        @hybrid_property
        def is_overdue(self):
            return self.status == InvoiceStatus.unpaid and date.today() > self.due_date
        @hybrid_property
        def days_overdue(self):
            return (date.today() - self.due_date).days if self.is_overdue else 0
        @hybrid_property
        def days_until_due(self):
            return (self.due_date - date.today()).days if self.status == InvoiceStatus.unpaid else 0
        @property
        def display_status(self):
            if self.status == InvoiceStatus.paid:
                return "paid"
            return "overdue" if self.is_overdue else "waiting"
        


     

class Company(db.Model):
        __tablename__ = 'companies'
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(100), nullable=False)        
        ico = db.Column(db.String(20), nullable=False)
        dic = db.Column(db.String(20), nullable=False)
        street = db.Column(db.String(100), nullable=False)
        user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
        user = db.relationship('User', backref=db.backref('companies', lazy=True))
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
       