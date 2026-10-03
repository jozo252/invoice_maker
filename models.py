from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone,date
from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import enum
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import validates
from sqlalchemy import Numeric
from uuid import uuid4


class EmailLog(db.Model):
    __tablename__ = "email_logs"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"), nullable=True)

    to_email = db.Column(db.String(255), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=False)

    status = db.Column(db.String(50), nullable=False, default="draft")
    # draft / sent / failed

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    sent_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", backref=db.backref("email_logs", lazy=True))
    client = db.relationship("Client", backref=db.backref("email_logs", lazy=True))
    invoice = db.relationship("Invoice", backref=db.backref("email_logs", lazy=True))
    job = db.relationship("Job", backref=db.backref("email_logs", lazy=True))

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


class Site(db.Model):
    """Place of work, deliberately separate from the client's billing address."""

    __tablename__ = "sites"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=True)
    label = db.Column(db.String(120), nullable=True)
    street = db.Column(db.String(200), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    zip_code = db.Column(db.String(20), nullable=True)
    country = db.Column(db.String(50), nullable=True)
    access_notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    client = db.relationship("Client", backref="sites")


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
        delivery_date = db.Column(db.Date, nullable=True)
        due_date = db.Column(db.Date, nullable=False)
        user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
        user = db.relationship('User', backref=db.backref('invoices', lazy=True))
        currency = db.Column(db.String(10), nullable=False)
        total_cost = db.Column(db.Float, nullable=False)  # Total cost calculated as quantity
        vat_rate = db.Column(db.Float, nullable=True, default=0.0)  # VAT rate in percentage
        client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=False)
        company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)  # Foreign key to the company
        job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=True)
        offer_revision_id = db.Column(db.Integer, db.ForeignKey('offer_revisions.id'), nullable=True)
        buyer_snapshot = db.Column(db.JSON, nullable=True)
        seller_snapshot = db.Column(db.JSON, nullable=True)
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
    customer_phone = db.Column(db.String(32))
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=True)
    site_id = db.Column(db.Integer, db.ForeignKey("sites.id"), nullable=True)
    source = db.Column(db.String(50), nullable=True)
    work_type = db.Column(db.String(50), nullable=True)
    next_action = db.Column(db.String(255), nullable=True)
    next_action_due = db.Column(db.Date, nullable=True)

    status = db.Column(db.String(50), default="new")  # new / quoted / closed

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    client = db.relationship("Client", backref="leads")
    site = db.relationship("Site", backref="leads")


class WorkActivity(db.Model):
    """A visit, scheduled work slot or explicit follow-up on one case."""

    __tablename__ = "work_activities"
    __table_args__ = (db.CheckConstraint(
        "(lead_id IS NOT NULL) != (job_id IS NOT NULL)",
        name="ck_work_activity_one_case"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    lead_id = db.Column(db.Integer, db.ForeignKey("lead.id"), nullable=True)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"), nullable=True)
    kind = db.Column(db.String(30), nullable=False)
    starts_at = db.Column(db.DateTime, nullable=False)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(30), nullable=False, default="planned")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    lead = db.relationship("Lead", backref="activities")
    job = db.relationship("Job", backref="activities")

class Offer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    offer_number = db.Column(db.String(50), nullable=True)
    user_id = db.Column(db.Integer, nullable=False)
    lead_id = db.Column(db.Integer, db.ForeignKey("lead.id"))
    company_id = db.Column(db.Integer, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=True)
    site_id = db.Column(db.Integer, db.ForeignKey("sites.id"), nullable=True)
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
    client = db.relationship("Client", backref="offers")
    site = db.relationship("Site", backref="offers")


class OfferRevision(db.Model):
    """The immutable commercial terms actually sent to or accepted by a client."""

    __tablename__ = "offer_revisions"
    __table_args__ = (db.UniqueConstraint("offer_id", "version", name="uq_offer_revision_version"),)

    id = db.Column(db.Integer, primary_key=True)
    offer_id = db.Column(db.Integer, db.ForeignKey("offer.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    version = db.Column(db.Integer, nullable=False)
    payload = db.Column(db.JSON, nullable=False)
    channel = db.Column(db.String(40), nullable=False)
    delivery_note = db.Column(db.String(500), nullable=True)
    sent_at = db.Column(db.DateTime, nullable=False)
    accepted_at = db.Column(db.DateTime, nullable=True)
    acceptance_note = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    offer = db.relationship("Offer", backref=db.backref("revisions", order_by="OfferRevision.version"))


#---------------------------------------------------------------------- Jobs ---------------------------------------
class Job(db.Model):
    __tablename__ = "jobs"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True)
    lead_id = db.Column(db.Integer, db.ForeignKey("lead.id"), nullable=True)
    site_id = db.Column(db.Integer, db.ForeignKey("sites.id"), nullable=True)
    offer_revision_id = db.Column(db.Integer, db.ForeignKey("offer_revisions.id"), nullable=True, unique=True)

    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)

    status = db.Column(db.String(50), nullable=False, default="new")
    # new, inspection, offer_sent, approved, done, invoiced, cancelled

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    client = db.relationship("Client", backref="jobs")
    company = db.relationship("Company", backref="jobs")
    lead = db.relationship("Lead", backref="jobs")
    site = db.relationship("Site", backref="jobs")
    offer_revision = db.relationship("OfferRevision", backref=db.backref("accepted_job", uselist=False))
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
    room_label = db.Column(db.String(100), nullable=True)
    element_label = db.Column(db.String(100), nullable=True)
    cable_type = db.Column(db.String(100), nullable=True)
    route_note = db.Column(db.String(500), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class JobMaterial(db.Model):
    """A job shopping checklist, deliberately not a warehouse ledger."""

    __tablename__ = "job_materials"
    __table_args__ = (db.CheckConstraint("quantity > 0", name="ck_job_material_quantity_positive"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Numeric(10, 3), nullable=False)
    unit = db.Column(db.String(20), nullable=False, default="ks")
    status = db.Column(db.String(20), nullable=False, default="needed")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    job = db.relationship("Job", backref="materials")


class JobCost(db.Model):
    """Manually confirmed internal labor or non-receipt direct cost in cents."""

    __tablename__ = "job_costs"
    __table_args__ = (
        db.CheckConstraint("amount_cents >= 0", name="ck_job_cost_nonnegative"),
        db.CheckConstraint("minutes IS NULL OR minutes > 0", name="ck_job_cost_minutes_positive"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"), nullable=False)
    category = db.Column(db.String(20), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    amount_cents = db.Column(db.BigInteger, nullable=False)
    minutes = db.Column(db.Integer, nullable=True)
    hourly_cost_cents = db.Column(db.BigInteger, nullable=True)
    occurred_on = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    job = db.relationship("Job", backref="direct_costs")


class JobChange(db.Model):
    """One priced extra-work line, frozen after customer approval."""

    __tablename__ = "job_changes"
    __table_args__ = (
        db.CheckConstraint("quantity > 0", name="ck_job_change_quantity_positive"),
        db.CheckConstraint("unit_price_cents >= 0", name="ck_job_change_price_nonnegative"),
        db.CheckConstraint("total_cents >= 0", name="ck_job_change_total_nonnegative"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Numeric(10, 3), nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    unit_price_cents = db.Column(db.BigInteger, nullable=False)
    total_cents = db.Column(db.BigInteger, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="proposed")
    approval_note = db.Column(db.String(500), nullable=True)
    approved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    job = db.relationship("Job", backref="changes")


class PriceEntry(db.Model):
    """Owner maintained labor/material quote shortcut; not a supplier feed."""

    __tablename__ = "price_entries"
    __table_args__ = (
        db.CheckConstraint("sale_price_cents >= 0", name="ck_price_entry_sale_nonnegative"),
        db.CheckConstraint("cost_cents IS NULL OR cost_cents >= 0", name="ck_price_entry_cost_nonnegative"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    kind = db.Column(db.String(20), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    sale_price_cents = db.Column(db.BigInteger, nullable=False)
    cost_cents = db.Column(db.BigInteger, nullable=True)
    source_note = db.Column(db.String(200), nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class JobPlan(db.Model):
    """Optional local CRM planning details; money is stored in integer cents."""

    __tablename__ = "job_plans"
    __table_args__ = (
        db.CheckConstraint(
            "agreed_price_cents IS NULL OR agreed_price_cents >= 0",
            name="ck_job_plans_agreed_price_nonnegative",
        ),
    )

    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    agreed_price_cents = db.Column(db.BigInteger, nullable=True)
    due_date = db.Column(db.Date, nullable=True)


class JobReceipt(db.Model):
    """A receipt draft becomes a cost only after explicit confirmation.

    object_name identifies a generated private object, never a user path. It is
    assigned on upload and remains immutable when receipt details are edited.
    These additive tables deliberately do not add relationships to Job: existing
    invoice routes can continue to operate before this migration is applied.
    """

    __tablename__ = "job_receipts"
    __table_args__ = (
        db.UniqueConstraint("user_id", "sha256", name="uq_job_receipts_user_sha256"),
        db.Index("ix_job_receipts_user_job", "user_id", "job_id"),
        db.CheckConstraint(
            "status IN ('draft', 'confirmed')",
            name="ck_job_receipts_status",
        ),
        db.CheckConstraint(
            "amount_cents IS NULL OR (amount_cents >= 0 AND amount_cents <= 1000000000)",
            name="ck_job_receipts_amount_range",
        ),
        db.CheckConstraint(
            "status != 'confirmed' OR (amount_cents IS NOT NULL AND amount_cents > 0 "
            "AND receipt_date IS NOT NULL AND length(trim(vendor)) > 0 "
            "AND confirmed_at IS NOT NULL)",
            name="ck_job_receipts_confirmed_complete",
        ),
        db.CheckConstraint("revision >= 0", name="ck_job_receipts_revision_nonnegative"),
    )

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    job_id = db.Column(db.Integer, db.ForeignKey("jobs.id"), nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    object_name = db.Column(db.String(100), nullable=False)
    original_name = db.Column(db.String(200), nullable=False)
    mime = db.Column(db.String(30), nullable=False)
    vendor = db.Column(db.String(120), nullable=False, default="", server_default="")
    receipt_date = db.Column(db.Date, nullable=True)
    amount_cents = db.Column(db.BigInteger, nullable=True)
    status = db.Column(db.String(16), nullable=False, default="draft", server_default="draft")
    ocr_text = db.Column(db.Text, nullable=False, default="", server_default="")
    revision = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=db.func.current_timestamp(),
    )
    confirmed_at = db.Column(db.DateTime, nullable=True)
