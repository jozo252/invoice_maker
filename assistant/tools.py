from datetime import date, datetime, timezone
from flask_login import current_user
from extensions import db
from models import (
    Client,
    Invoice,
    InvoiceStatus,
    Company,
    Job,
    JobNote,
    Offer,
    Lead,
    EmailLog,
)
from flask_mail import Message
from extensions import mail


def _money(value):
    if value is None:
        return None
    return float(value)


def find_client(client_name: str):
    clients = Client.query.filter(
        Client.user_id == current_user.id,
        Client.name.ilike(f"%{client_name}%")
    ).all()

    if not clients:
        return {
            "status": "not_found",
            "message": f"Klient '{client_name}' sa nenašiel."
        }

    return {
        "status": "success",
        "clients": [
            {
                "id": c.id,
                "name": c.name,
                "ico": c.ico,
                "dic": c.dic,
                "email": c.email,
                "phone": c.phone,
                "city": c.city,
                "street": c.street,
                "zip_code": c.zip_code,
                "country": c.country,
            }
            for c in clients
        ]
    }


def get_overdue_invoices():
    invoices = Invoice.query.filter(
        Invoice.user_id == current_user.id,
        Invoice.status == InvoiceStatus.unpaid,
        Invoice.due_date < date.today()
    ).order_by(Invoice.due_date.asc()).all()

    return {
        "status": "success",
        "invoices": [
            {
                "id": inv.id,
                "invoice_number": inv.invoice_number,
                "client_id": inv.client_id,
                "client_name": inv.client.name if inv.client else None,
                "client_email": inv.client.email if inv.client else None,
                "company_name": inv.company.name if inv.company else None,
                "amount": _money(inv.total_cost),
                "currency": inv.currency,
                "due_date": inv.due_date.isoformat(),
                "days_overdue": inv.days_overdue,
                "status": inv.status.value,
                "pdf_path": inv.pdf_path,
            }
            for inv in invoices
        ]
    }


def get_unpaid_invoices_for_client(client_id: int):
    invoices = Invoice.query.filter(
        Invoice.user_id == current_user.id,
        Invoice.client_id == client_id,
        Invoice.status == InvoiceStatus.unpaid
    ).order_by(Invoice.due_date.asc()).all()

    return {
        "status": "success",
        "invoices": [
            {
                "id": inv.id,
                "invoice_number": inv.invoice_number,
                "amount": _money(inv.total_cost),
                "currency": inv.currency,
                "date": inv.date.isoformat(),
                "due_date": inv.due_date.isoformat(),
                "days_overdue": inv.days_overdue,
                "is_overdue": inv.is_overdue,
                "status": inv.status.value,
                "client_name": inv.client.name if inv.client else None,
                "client_email": inv.client.email if inv.client else None,
            }
            for inv in invoices
        ]
    }


def get_invoice_detail(invoice_id: int):
    invoice = Invoice.query.filter(
        Invoice.id == invoice_id,
        Invoice.user_id == current_user.id
    ).first()

    if not invoice:
        return {
            "status": "not_found",
            "message": "Faktúra sa nenašla."
        }

    return {
        "status": "success",
        "invoice": {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "variable_symbol": invoice.variable_symbol,
            "date": invoice.date.isoformat(),
            "due_date": invoice.due_date.isoformat(),
            "amount": _money(invoice.total_cost),
            "currency": invoice.currency,
            "vat_rate": invoice.vat_rate,
            "status": invoice.status.value,
            "client": {
                "id": invoice.client.id,
                "name": invoice.client.name,
                "email": invoice.client.email,
                "ico": invoice.client.ico,
            } if invoice.client else None,
            "company": {
                "id": invoice.company.id,
                "name": invoice.company.name,
                "email": invoice.company.email,
                "iban": invoice.company.iban,
            } if invoice.company else None,
            "items": [
                {
                    "description": item.description,
                    "quantity": float(item.quantity),
                    "unit": item.unit,
                    "price_per_item": _money(item.price_per_item),
                    "total_cost": _money(item.total_cost),
                }
                for item in invoice.items
            ]
        }
    }


def draft_payment_reminder(invoice_id: int, tone: str = "normal"):
    detail = get_invoice_detail(invoice_id)

    if detail["status"] != "success":
        return detail

    inv = detail["invoice"]
    client = inv["client"]
    company = inv["company"]

    if not client or not client.get("email"):
        return {
            "status": "missing_email",
            "message": "Klient nemá uložený email."
        }

    if tone == "strict":
        intro = "dovoľujeme si Vás opätovne upozorniť"
        request = "Prosíme o bezodkladnú úhradu."
    else:
        intro = "radi by sme Vám pripomenuli"
        request = "Prosíme o preverenie úhrady."

    subject = f"Pripomenutie neuhradenej faktúry č. {inv['invoice_number']}"

    body = f"""
Dobrý deň,

{intro}, že faktúra č. {inv['invoice_number']} vo výške {inv['amount']} {inv['currency']} so splatnosťou {inv['due_date']} zatiaľ nie je evidovaná ako uhradená.

{request}

Ak už bola platba zrealizovaná, považujte túto správu za bezpredmetnú.

S pozdravom
{company['name'] if company else ''}
""".strip()
    
    saved = save_email_draft(
    to_email=client["email"],
    subject=subject,
    body=body,
    client_id=client["id"],
    invoice_id=inv["id"]
)

    return {
    "status": "success",
    "requires_confirmation": True,
    "email": {
        "id": saved["email_log_id"],
        "to": client["email"],
        "subject": subject,
        "body": body,
        "invoice_id": inv["id"],
        "client_id": client["id"],
    }
    }


def get_client_jobs(client_id: int):
    jobs = Job.query.filter(
        Job.user_id == current_user.id,
        Job.client_id == client_id
    ).order_by(Job.updated_at.desc()).all()

    return {
        "status": "success",
        "jobs": [
            {
                "id": job.id,
                "title": job.title,
                "description": job.description,
                "status": job.status,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "updated_at": job.updated_at.isoformat() if job.updated_at else None,
                "notes_count": len(job.notes),
                "attachments_count": len(job.attachments),
            }
            for job in jobs
        ]
    }


def get_job_detail(job_id: int):
    job = Job.query.filter(
        Job.id == job_id,
        Job.user_id == current_user.id
    ).first()

    if not job:
        return {
            "status": "not_found",
            "message": "Zákazka sa nenašla."
        }

    return {
        "status": "success",
        "job": {
            "id": job.id,
            "title": job.title,
            "description": job.description,
            "status": job.status,
            "client_name": job.client.name if job.client else None,
            "company_name": job.company.name if job.company else None,
            "notes": [
                {
                    "id": note.id,
                    "content": note.content,
                    "note_type": note.note_type,
                    "created_at": note.created_at.isoformat() if note.created_at else None,
                }
                for note in job.notes
            ],
            "attachments": [
                {
                    "id": att.id,
                    "filename": att.filename,
                    "original_filename": att.original_filename,
                    "file_type": att.file_type,
                    "mime_type": att.mime_type,
                }
                for att in job.attachments
            ]
        }
    }


def add_job_note(job_id: int, content: str, note_type: str = "ai"):
    job = Job.query.filter(
        Job.id == job_id,
        Job.user_id == current_user.id
    ).first()

    if not job:
        return {
            "status": "not_found",
            "message": "Zákazka sa nenašla."
        }

    note = JobNote(
        job_id=job.id,
        user_id=current_user.id,
        content=content,
        note_type=note_type
    )

    db.session.add(note)
    db.session.commit()

    return {
        "status": "success",
        "message": "Poznámka bola uložená k zákazke.",
        "note_id": note.id
    }


def search_jobs(query: str):
    jobs = Job.query.filter(
        Job.user_id == current_user.id,
        Job.title.ilike(f"%{query}%")
    ).order_by(Job.updated_at.desc()).all()

    return {
        "status": "success",
        "jobs": [
            {
                "id": job.id,
                "title": job.title,
                "status": job.status,
                "client_name": job.client.name if job.client else None,
                "updated_at": job.updated_at.isoformat() if job.updated_at else None,
            }
            for job in jobs
        ]
    }

def save_email_draft(to_email: str, subject: str, body: str, client_id=None, invoice_id=None, job_id=None):
    email_log = EmailLog(
        user_id=current_user.id,
        client_id=client_id,
        invoice_id=invoice_id,
        job_id=job_id,
        to_email=to_email,
        subject=subject,
        body=body,
        status="draft"
    )

    db.session.add(email_log)
    db.session.commit()

    return {
        "status": "success",
        "message": "Email draft bol uložený.",
        "email_log_id": email_log.id
    }

def send_email_log(email_log_id: int):
    email_log = EmailLog.query.filter(
        EmailLog.id == email_log_id,
        EmailLog.user_id == current_user.id
    ).first()

    if not email_log:
        return {
            "status": "not_found",
            "message": "Email draft sa nenašiel."
        }

    if email_log.status == "sent":
        return {
            "status": "already_sent",
            "message": "Tento email už bol odoslaný."
        }

    try:
        msg = Message(
            subject=email_log.subject,
            recipients=[email_log.to_email],
            body=email_log.body
        )

        mail.send(msg)

        email_log.status = "sent"
        email_log.sent_at = datetime.now(timezone.utc)

        db.session.commit()

        return {
            "status": "success",
            "message": "Email bol odoslaný."
        }

    except Exception as e:
        email_log.status = "failed"
        db.session.commit()

        return {
            "status": "error",
            "message": f"Email sa nepodarilo odoslať: {str(e)}"
        }