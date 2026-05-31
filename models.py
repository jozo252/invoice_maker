from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone,date
from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import enum
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import validates
from sqlalchemy import Numeric




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
    quantity = db.Column(Numeric(10, 3, asdecimal=True), nullable=False)    
    unit=db.Column(db.String(50), nullable=False)  # e.g., "pcs", "kg", etc.
    price_per_item = db.Column(db.Float, nullable=False)
    total_cost = db.Column(db.Float, nullable=False)

    invoice = db.relationship("Invoice", back_populates="items")



class Client(db.Model):
        __tablename__ = 'clients'
        id = db.Column(db.Integer, primary_key=True)
        name = db.Column(db.String(100), nullable=False)        
        ico = db.Column(db.String(20), nullable=True)
        dic = db.Column(db.String(20), nullable=True)
        street = db.Column(db.String(100), nullable=True)
        user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
        user = db.relationship('User', backref=db.backref('clients', lazy=True))
        city = db.Column(db.String(50), nullable=True)
        zip_code = db.Column(db.String(20), nullable=True)
        country = db.Column(db.String(50), nullable=True)
        email = db.Column(db.String(100), nullable=True)       
        phone = db.Column(db.String(20), nullable=True)
        iban = db.Column(db.String(34), nullable=True)
        bic = db.Column(db.String(11), nullable=True)
        is_vat_payer = db.Column(db.Boolean, default=True)
        ic_dph = db.Column(db.String(20), nullable=True)  # Optional field for VAT ID if the client is a VAT payer


class InvoiceStatus(enum.Enum):
    unpaid = "unpaid"
    paid = "paid"
    canceled = "canceled"
    accepted="accepted"


class PaymentMethod(enum.Enum):
    bank_transfer = "bank_transfer"
    cash = "cash"
    card = "card"          # ak nechceš karty, kľudne vyhoď
    other = "other"



class Invoice(db.Model):
        __tablename__ = 'invoices'
        __table_args__ = (
        db.UniqueConstraint('user_id', 'invoice_number', name='uq_user_invoice'),
        )
        id = db.Column(db.Integer, primary_key=True)
        invoice_number = db.Column(db.String(50), nullable=False)
        variable_symbol = db.Column(db.String(20), nullable=True)
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
        created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))        
        status = db.Column(db.Enum(InvoiceStatus, name="invoicestatus",
                           native_enum=False, validate_strings=True), nullable=False, default=InvoiceStatus.unpaid)
        discount_total = db.Column(db.Numeric(10, 2), nullable=False, default=0)
        pdf_path = db.Column(db.String(255), nullable=True)
        payment_method = db.Column(db.Enum(PaymentMethod, name="paymentmethod",
                                   native_enum=False, validate_strings=True), nullable=False, default=PaymentMethod.bank_transfer)
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
        
        @validates('invoice_number')
        def _normalize(self, key, value):
            return (value or '').strip().upper()
        





class InvoiceCounter(db.Model):
    __tablename__ = 'invoice_counters'
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), primary_key=True)
    year = db.Column(db.Integer, primary_key=True)
    last_no = db.Column(db.Integer, nullable=False, default=0)

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
        is_vat_payer = db.Column(db.Boolean, default=False)
        ic_dph = db.Column(db.String(20), nullable=True)  # Optional field for VAT ID if the 
        stamp_url=db.Column(db.String(256),nullable=True)
       


#-------------------------------------------------------------------------------------------Offers--------------------------------

class Lead(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=False)

    name = db.Column(db.String(255))  # napr. "Rekonštrukcia bytu"
    description = db.Column(db.Text)  # raw text od usera

    customer_name = db.Column(db.String(255))
    customer_email = db.Column(db.String(255))

    status = db.Column(db.String(50), default="new")  # new / quoted / closed

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

class Offer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    offer_number = db.Column(db.String(50), nullable=True)
    user_id = db.Column(db.Integer, nullable=False)
    lead_id = db.Column(db.Integer, db.ForeignKey("lead.id"))
    company_id = db.Column(db.Integer, nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"), nullable=True)
    currency = db.Column(db.String(10), nullable=False)

    customer_name = db.Column(db.String(255))
    customer_email = db.Column(db.String(255))

    items = db.Column(db.JSON)  # [{name, qty, unit_price}]
    notes = db.Column(db.Text)

    subtotal = db.Column(db.Numeric(10, 2))
    discount_total = db.Column(db.Numeric(10, 2), default=0)
    total = db.Column(db.Numeric(10, 2))

    status = db.Column(db.String(50), default="draft")  # draft / sent / accepted

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    job = db.relationship("Job", backref="offers")


#---------------------------------------------------------------------- Jobs ---------------------------------------
class Job(db.Model):
    __tablename__ = "jobs"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True)

    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)

    status = db.Column(db.String(50), nullable=False, default="new")
    # new, inspection, offer_sent, approved, done, invoiced, cancelled

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    client = db.relationship("Client", backref="jobs")
    company = db.relationship("Company", backref="jobs")
    notes = db.relationship("JobNote", backref="job", lazy=True, cascade="all, delete-orphan")
    attachments = db.relationship("JobAttachment", backref="job", lazy=True, cascade="all, delete-orphan")

class JobNote(db.Model):
    __tablename__ = "job_notes"

    id = db.Column(db.Integer, primary_key=True)

    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)


    content = db.Column(db.Text, nullable=False)
    note_type = db.Column(db.String(50), nullable=False, default="text")
    # text, inspection, material, task, ai

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class JobAttachment(db.Model):
    __tablename__ = "job_attachments"

    id = db.Column(db.Integer, primary_key=True)

    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_type = db.Column(db.String(50), nullable=True)
    mime_type = db.Column(db.String(100), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)