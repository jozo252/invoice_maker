"""Small, explicit application operations for the electrician job lifecycle.

Routes and the AI assistant should call these operations instead of writing
related tables independently. Callers own the transaction and commit only
after the whole operation succeeds.
"""

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from extensions import db
from sqlalchemy import text
from models import (Client, Company, Invoice, InvoiceItem, InvoiceStatus,
                    Job, JobChange, JobCost, JobMaterial, JobPlan, JobReceipt, Lead,
                    Offer, OfferRevision, PaymentMethod, Site)


CENT = Decimal("0.01")
PARTY_FIELDS = ("name", "street", "city", "zip_code", "country", "ico", "dic",
                "ic_dph", "email", "phone", "iban", "bic", "is_vat_payer", "stamp_url")


class WorkflowError(ValueError):
    pass


def _decimal(value, label):
    try:
        number = Decimal(str(value).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        raise WorkflowError(f"{label}: zadaj platné číslo.") from None
    if not number.is_finite():
        raise WorkflowError(f"{label}: číslo musí byť konečné.")
    return number


def _money(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _owned(model, record_id, owner_id, label):
    if record_id is None:
        return None
    record = model.query.filter_by(id=record_id, user_id=owner_id).first()
    if record is None:
        raise WorkflowError(f"{label} nepatrí k tomuto účtu.")
    return record


def snapshot_offer(offer, owner_id):
    """Recalculate every visible number from editable inputs; never trust LLM totals."""
    if offer.user_id != owner_id:
        raise WorkflowError("Ponuka nepatrí k tomuto účtu.")
    _owned(Company, offer.company_id, owner_id, "Firma")
    if offer.lead_id:
        _owned(Lead, offer.lead_id, owner_id, "Dopyt")
    if offer.client_id:
        _owned(Client, offer.client_id, owner_id, "Klient")
    site = _owned(Site, offer.site_id, owner_id, "Miesto") if offer.site_id else None
    if site and offer.client_id and site.client_id not in (None, offer.client_id):
        raise WorkflowError("Miesto je priradené inému klientovi.")

    items = []
    subtotal = Decimal("0.00")
    estimated_cost_cents = 0
    estimate_complete = True
    for number, item in enumerate(offer.items or [], start=1):
        description = (item.get("description") or item.get("name") or "").strip()
        if not description:
            raise WorkflowError(f"Položka {number}: chýba názov.")
        qty = _decimal(item.get("quantity", 1), f"Položka {number} množstvo")
        price = _decimal(item.get("price_per_item", 0), f"Položka {number} cena")
        if qty <= 0 or qty > 100000 or price < 0 or price > 10000000:
            raise WorkflowError(f"Položka {number}: neplatné množstvo alebo cena.")
        if qty * 1000 != (qty * 1000).to_integral_value() or price != _money(price):
            raise WorkflowError(f"Položka {number}: množstvo môže mať najviac 3 a cena 2 desatinné miesta.")
        line_total = _money(qty * price)
        subtotal += line_total
        row = {
            "description": description,
            "quantity": str(qty),
            "unit": (item.get("unit") or "ks").strip() or "ks",
            "price_per_item": str(_money(price)),
            "total_cost": str(line_total),
        }
        unit_cost_cents = item.get("unit_cost_cents")
        if unit_cost_cents is None:
            estimate_complete = False
        else:
            try:
                unit_cost_cents = int(unit_cost_cents)
            except (TypeError, ValueError):
                raise WorkflowError(f"Položka {number}: neplatný interný náklad.") from None
            if unit_cost_cents < 0:
                raise WorkflowError(f"Položka {number}: záporný interný náklad.")
            estimated_cost_cents += int((qty * unit_cost_cents).quantize(
                Decimal("1"), rounding=ROUND_HALF_UP))
            row["unit_cost_cents"] = unit_cost_cents
            row["price_origin"] = item.get("price_origin") or "manual"
            row["price_source_note"] = item.get("price_source_note")
            row["catalog_id"] = item.get("catalog_id")
        items.append(row)
    if not items:
        raise WorkflowError("Ponuka musí mať aspoň jednu položku.")
    subtotal = _money(subtotal)
    discount = _decimal(offer.discount_total or 0, "Zľava")
    if discount != _money(discount):
        raise WorkflowError("Zľava môže mať najviac 2 desatinné miesta.")
    discount = _money(discount)
    if discount < 0 or discount > subtotal:
        raise WorkflowError("Zľava musí byť medzi nulou a medzisúčtom.")
    total = _money(subtotal - discount)
    if total <= 0:
        raise WorkflowError("Pred odoslaním potvrď kladnú predajnú cenu.")
    currency = (offer.currency or "EUR").strip().upper()
    if currency != "EUR":
        raise WorkflowError("Tento pracovný tok zatiaľ podporuje iba EUR.")
    return {
        "offer_number": offer.offer_number,
        "company_id": offer.company_id,
        "client_id": offer.client_id,
        "site_id": offer.site_id,
        "customer_name": (offer.customer_name or "").strip(),
        "customer_email": (offer.customer_email or "").strip(),
        "site": None if site is None else {
            "label": site.label, "street": site.street, "city": site.city,
            "zip_code": site.zip_code, "country": site.country,
        },
        "items": items,
        "notes": offer.notes or "",
        "currency": currency,
        "subtotal": str(subtotal),
        "discount_total": str(discount),
        "total": str(total),
        "tax_treatment": "manual-review-before-invoice",
        "internal_estimated_direct_cost_cents": estimated_cost_cents if estimate_complete else None,
    }


def record_offer_sent(offer, owner_id, channel, delivery_note="", *, prices_confirmed=False):
    if not prices_confirmed:
        raise WorkflowError("Pred odoslaním musíš skontrolovať ceny a výpočet.")
    if channel not in {"email", "manual", "legacy-manual"}:
        raise WorkflowError("Neplatný kanál odoslania.")
    if offer.status == "accepted":
        raise WorkflowError("Prijatú ponuku nemožno znovu odoslať bez novej ponuky.")
    delivery_note = (delivery_note or "").strip()
    if channel == "manual" and not 4 <= len(delivery_note) <= 500:
        raise WorkflowError("Zapíš kanál a dátum odoslania ponuky (4–500 znakov).")
    payload = snapshot_offer(offer, owner_id)
    latest = (OfferRevision.query.filter_by(offer_id=offer.id, user_id=owner_id)
              .order_by(OfferRevision.version.desc()).first())
    if latest and latest.payload == payload and latest.channel == channel and latest.delivery_note == delivery_note:
        offer.status = "sent"
        return latest
    revision = OfferRevision(
        offer_id=offer.id, user_id=owner_id,
        version=(latest.version + 1 if latest else 1),
        payload=payload, channel=channel, delivery_note=delivery_note,
        sent_at=datetime.now(timezone.utc),
    )
    db.session.add(revision)
    offer.subtotal = Decimal(payload["subtotal"])
    offer.discount_total = Decimal(payload["discount_total"])
    offer.total = Decimal(payload["total"])
    offer.status = "sent"
    if offer.lead_id:
        lead = _owned(Lead, offer.lead_id, owner_id, "Dopyt")
        lead.status = "quoted"
        lead.next_action = "Čakať na odpoveď k ponuke"
    return revision


def link_lead_client(lead, owner_id, *, client_id=None, create_new=False):
    if lead.user_id != owner_id:
        raise WorkflowError("Dopyt nepatrí k tomuto účtu.")
    if lead.client_id:
        existing = _owned(Client, lead.client_id, owner_id, "Klient")
        if client_id and int(client_id) != existing.id:
            raise WorkflowError("Dopyt je už priradený inému klientovi.")
        return existing
    if client_id:
        client = _owned(Client, int(client_id), owner_id, "Klient")
    elif create_new:
        name = (lead.customer_name or "").strip()
        if not name:
            raise WorkflowError("Pre nového klienta chýba meno.")
        client = Client(user_id=owner_id, name=name,
                        email=(lead.customer_email or "").strip() or None,
                        phone=(lead.customer_phone or "").strip() or None,
                        is_vat_payer=False)
        db.session.add(client)
        db.session.flush()
    else:
        raise WorkflowError("Vyber klienta alebo potvrď vytvorenie nového.")
    site = _owned(Site, lead.site_id, owner_id, "Miesto") if lead.site_id else None
    if site:
        if site.client_id not in (None, client.id):
            raise WorkflowError("Miesto je priradené inému klientovi.")
        site.client_id = client.id
    lead.client_id = client.id
    return client


def accept_offer(offer, owner_id, *, acceptance_note, client_id=None, create_client=False):
    if offer.user_id != owner_id:
        raise WorkflowError("Ponuka nepatrí k tomuto účtu.")
    note = (acceptance_note or "").strip()
    if len(note) < 4 or len(note) > 500:
        raise WorkflowError("Zapíš spôsob a dátum potvrdenia od zákazníka (4–500 znakov).")
    revision = (OfferRevision.query.filter_by(offer_id=offer.id, user_id=owner_id)
                .order_by(OfferRevision.version.desc()).first())
    if revision is None or offer.status not in {"sent", "accepted"}:
        raise WorkflowError("Najprv odošli alebo označ presnú verziu ponuky ako odoslanú.")
    existing = Job.query.filter_by(offer_revision_id=revision.id, user_id=owner_id).first()
    if existing:
        return existing
    if revision.accepted_at is not None:
        raise WorkflowError("Táto verzia je už prijatá, ale nemá zodpovedajúcu zákazku.")
    if offer.status == "accepted":
        raise WorkflowError("Ponuka má už prijatú inú verziu.")
    lead = _owned(Lead, offer.lead_id, owner_id, "Dopyt") if offer.lead_id else None
    if lead and lead.client_id:
        client = _owned(Client, lead.client_id, owner_id, "Klient")
    elif offer.client_id:
        client = _owned(Client, offer.client_id, owner_id, "Klient")
    elif lead:
        client = link_lead_client(lead, owner_id, client_id=client_id, create_new=create_client)
    elif client_id:
        client = _owned(Client, int(client_id), owner_id, "Klient")
    elif create_client:
        name = (offer.customer_name or "").strip()
        if not name:
            raise WorkflowError("Pre nového klienta chýba meno.")
        client = Client(user_id=owner_id, name=name,
                        email=(offer.customer_email or "").strip() or None,
                        is_vat_payer=False)
        db.session.add(client)
        db.session.flush()
    else:
        raise WorkflowError("Vyber klienta alebo potvrď vytvorenie nového.")
    site_id = offer.site_id or (lead.site_id if lead else None)
    site = _owned(Site, site_id, owner_id, "Miesto") if site_id else None
    if site:
        if site.client_id not in (None, client.id):
            raise WorkflowError("Miesto je priradené inému klientovi.")
        site.client_id = client.id
    offer.client_id = client.id
    offer.site_id = site.id if site else None
    if lead:
        lead.client_id = client.id
        lead.status = "won"
        lead.next_action = "Naplánovať realizáciu"
        lead.next_action_due = None
    if offer.job_id:
        job = _owned(Job, offer.job_id, owner_id, "Zákazka")
        if job.offer_revision_id not in (None, revision.id):
            raise WorkflowError("Zákazka má už inú prijatú ponuku.")
        job.client_id = client.id
        job.site_id = site.id if site else None
        job.lead_id = lead.id if lead else None
        job.offer_revision_id = revision.id
        job.status = "approved"
    else:
        job = Job(user_id=owner_id, client_id=client.id,
                  company_id=offer.company_id,
                  lead_id=lead.id if lead else None,
                  site_id=site.id if site else None,
                  offer_revision_id=revision.id,
                  title=(lead.name if lead and lead.name else offer.customer_name or offer.offer_number or "Elektro zákazka")[:255],
                  description=offer.notes,
                  status="approved")
        db.session.add(job)
        db.session.flush()
        offer.job_id = job.id
    agreed_cents = int(Decimal(revision.payload["total"]) * 100)
    plan = JobPlan.query.filter_by(job_id=job.id, user_id=owner_id).first()
    if plan is None:
        db.session.add(JobPlan(job_id=job.id, user_id=owner_id,
                               agreed_price_cents=agreed_cents))
    else:
        plan.agreed_price_cents = agreed_cents
    revision.accepted_at = datetime.now(timezone.utc)
    revision.acceptance_note = note
    offer.status = "accepted"
    return job


def job_invoice_source(job, owner_id):
    """Validate a completed job and return the accepted commercial snapshot."""
    if job.user_id != owner_id:
        raise WorkflowError("Zákazka nepatrí k tomuto účtu.")
    if job.status != "done":
        raise WorkflowError("Najprv označ zákazku ako hotovú.")
    revision = _owned(OfferRevision, job.offer_revision_id, owner_id, "Prijatá ponuka")
    if revision is None or revision.accepted_at is None:
        raise WorkflowError("Zákazka nemá prijatú verziu ponuky.")
    client = _owned(Client, job.client_id, owner_id, "Klient")
    company = _owned(Company, job.company_id, owner_id, "Firma")
    if client is None or company is None:
        raise WorkflowError("Zákazke chýba klient alebo firma.")
    if not all((client.name, client.street, client.city, client.zip_code, client.country)):
        raise WorkflowError("Pred fakturáciou doplň fakturačnú adresu klienta.")
    payload = dict(revision.payload or {})
    if payload.get("currency") != "EUR" or not payload.get("items"):
        raise WorkflowError("Prijatá verzia ponuky nemá platné položky v EUR.")
    if _decimal(payload.get("total"), "Cena") <= 0:
        raise WorkflowError("Prijatá ponuka nemá kladnú cenu.")
    approved_changes = JobChange.query.filter_by(job_id=job.id, user_id=owner_id,
                                                  status="approved").order_by(JobChange.id).all()
    payload["items"] = list(payload["items"])
    extra_total = Decimal("0.00")
    for change in approved_changes:
        line_total = Decimal(change.total_cents) / 100
        extra_total += line_total
        payload["items"].append({
            "description": change.description, "quantity": str(change.quantity),
            "unit": change.unit,
            "price_per_item": str(Decimal(change.unit_price_cents) / 100),
            "total_cost": str(line_total), "job_change_id": change.id,
        })
    payload["base_total"] = payload["total"]
    payload["extras_total"] = str(_money(extra_total))
    payload["subtotal"] = str(_money(_decimal(payload["subtotal"], "Medzisúčet") + extra_total))
    payload["total"] = str(_money(_decimal(payload["total"], "Cena") + extra_total))
    return revision, client, company, payload


def issue_job_invoice(job, owner_id, *, issue_date, delivery_date, due_date,
                      vat_rate, payment_method):
    """Copy accepted offer values exactly once; caller commits the transaction."""
    existing = Invoice.query.filter_by(job_id=job.id, user_id=owner_id).first()
    if existing:
        return existing
    revision, client, company, payload = job_invoice_source(job, owner_id)
    if not all(isinstance(value, date) for value in (issue_date, delivery_date, due_date)):
        raise WorkflowError("Zadaj platné dátumy faktúry.")
    if due_date < issue_date:
        raise WorkflowError("Splatnosť nemôže byť pred vystavením.")
    rate = _decimal(vat_rate, "Sadzba DPH")
    if rate < 0 or rate > 100 or (not company.is_vat_payer and rate != 0):
        raise WorkflowError("Skontroluj sadzbu DPH a status platiteľa firmy.")
    if payment_method not in {method.value for method in PaymentMethod}:
        raise WorkflowError("Neplatný spôsob platby.")
    amount = _money(_decimal(payload["total"], "Cena"))
    discount = _money(_decimal(payload.get("discount_total", 0), "Zľava"))
    if amount <= 0 or discount < 0:
        raise WorkflowError("Neplatná cena alebo zľava v prijatej ponuke.")

    # Counter update and invoice insert take place in the same transaction.
    # Current application database is SQLite; RETURNING is used already by
    # existing invoice numbering code.
    for _ in range(1000):
        sequence = db.session.execute(text("""
            INSERT INTO invoice_counters (user_id, year, last_no)
            VALUES (:owner_id, :year, 1)
            ON CONFLICT(user_id, year) DO UPDATE SET last_no = last_no + 1
            RETURNING last_no
        """), {"owner_id": owner_id, "year": issue_date.year}).scalar_one()
        number = f"{issue_date.year}-{int(sequence):04d}"
        if not Invoice.query.filter_by(user_id=owner_id, invoice_number=number).first():
            break
    else:
        raise WorkflowError("Nie je dostupné ďalšie číslo faktúry; skontroluj číselný rad.")
    invoice = Invoice(
        user_id=owner_id, job_id=job.id, offer_revision_id=revision.id,
        client_id=client.id, company_id=company.id,
        invoice_number=number, variable_symbol=number,
        date=issue_date, delivery_date=delivery_date, due_date=due_date,
        currency="EUR", vat_rate=float(rate),
        total_cost=float(amount), discount_total=discount,
        buyer_snapshot={field: getattr(client, field, None) for field in PARTY_FIELDS},
        seller_snapshot={field: getattr(company, field, None) for field in PARTY_FIELDS},
        status=InvoiceStatus.unpaid, payment_method=PaymentMethod(payment_method),
    )
    for row in payload["items"]:
        quantity = _decimal(row.get("quantity"), "Množstvo")
        price = _money(_decimal(row.get("price_per_item"), "Cena"))
        if quantity <= 0 or price < 0:
            raise WorkflowError("Prijatá ponuka obsahuje neplatnú položku.")
        invoice.items.append(InvoiceItem(
            description=row["description"], quantity=quantity,
            unit=row.get("unit") or "ks", price_per_item=float(price),
            total_cost=float(_money(quantity * price)),
        ))
    db.session.add(invoice)
    job.status = "invoiced"
    return invoice


MATERIAL_STATES = {"needed", "ordered", "ready", "used", "returned"}


def add_job_material(job, owner_id, *, description, quantity, unit):
    if job.user_id != owner_id:
        raise WorkflowError("Zákazka nepatrí k tomuto účtu.")
    description = (description or "").strip()
    unit = (unit or "ks").strip()
    amount = _decimal(quantity, "Množstvo materiálu")
    if not description or len(description) > 200 or not unit or len(unit) > 20:
        raise WorkflowError("Zadaj krátky názov materiálu a jednotku.")
    if amount <= 0 or amount > 100000:
        raise WorkflowError("Množstvo materiálu musí byť kladné.")
    item = JobMaterial(user_id=owner_id, job_id=job.id, description=description,
                       quantity=amount, unit=unit, status="needed")
    db.session.add(item)
    return item


def add_job_cost(job, owner_id, *, category, description, occurred_on,
                 minutes=None, hourly_cost=None, amount=None):
    if job.user_id != owner_id:
        raise WorkflowError("Zákazka nepatrí k tomuto účtu.")
    if category not in {"labor", "travel", "subcontract", "other"}:
        raise WorkflowError("Neplatný typ nákladu; materiál zaeviduj potvrdeným bločkom.")
    description = (description or "").strip()
    if not description or len(description) > 200 or not isinstance(occurred_on, date):
        raise WorkflowError("Doplň popis a dátum nákladu.")
    if category == "labor":
        try:
            minutes_value = int(minutes)
        except (ValueError, TypeError):
            raise WorkflowError("Zadaj odpracované minúty.") from None
        hourly = _money(_decimal(hourly_cost, "Interný náklad za hodinu"))
        if minutes_value <= 0 or minutes_value > 100000 or hourly <= 0 or hourly > 10000:
            raise WorkflowError("Skontroluj minúty a interný hodinový náklad.")
        rate_cents = int(hourly * 100)
        amount_cents = int((Decimal(minutes_value) * Decimal(rate_cents) / 60)
                           .quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    else:
        expense = _money(_decimal(amount, "Náklad"))
        if expense <= 0 or expense > 1000000:
            raise WorkflowError("Náklad musí byť kladný a v EUR.")
        minutes_value = None
        rate_cents = None
        amount_cents = int(expense * 100)
    item = JobCost(user_id=owner_id, job_id=job.id, category=category,
                   description=description, occurred_on=occurred_on,
                   minutes=minutes_value, hourly_cost_cents=rate_cents,
                   amount_cents=amount_cents)
    db.session.add(item)
    return item


def job_financials(job, owner_id):
    """Direct contribution with explicit incompleteness, never called profit."""
    if job.user_id != owner_id:
        raise WorkflowError("Zákazka nepatrí k tomuto účtu.")
    plan = JobPlan.query.filter_by(job_id=job.id, user_id=owner_id).first()
    receipt_cents = sum(row.amount_cents for row in JobReceipt.query.filter_by(
        job_id=job.id, user_id=owner_id, status="confirmed").all())
    costs = JobCost.query.filter_by(job_id=job.id, user_id=owner_id).all()
    manual_cents = sum(row.amount_cents for row in costs)
    extras_cents = sum(row.total_cents for row in JobChange.query.filter_by(
        job_id=job.id, user_id=owner_id, status="approved").all())
    base_cents = plan.agreed_price_cents if plan else None
    agreed = base_cents + extras_cents if base_cents is not None else None
    revision = _owned(OfferRevision, job.offer_revision_id, owner_id, "Prijatá ponuka") if job.offer_revision_id else None
    planned_cost_cents = ((revision.payload or {}).get("internal_estimated_direct_cost_cents")
                          if revision and not extras_cents else None)
    missing = []
    if agreed is None:
        missing.append("Dohodnutá cena")
    if planned_cost_cents is None:
        missing.append("Úplný odhad priamych nákladov pred zákazkou")
    if not any(row.category == "labor" for row in costs):
        missing.append("Odpracovaný čas a interný náklad práce")
    if (JobMaterial.query.filter_by(job_id=job.id, user_id=owner_id, status="used").first()
            and receipt_cents == 0):
        missing.append("Potvrdené náklady na použitý materiál")
    company = _owned(Company, job.company_id, owner_id, "Firma") if job.company_id else None
    if company and company.is_vat_payer and receipt_cents:
        missing.append("Bločky sú v hrubej sume; treba oddeliť odpočítateľnú DPH")
    return {
        "agreed_cents": agreed, "base_cents": base_cents,
        "extras_cents": extras_cents, "receipt_cents": receipt_cents,
        "manual_cents": manual_cents, "direct_costs_cents": receipt_cents + manual_cents,
        "contribution_cents": None if agreed is None else agreed - receipt_cents - manual_cents,
        "planned_cost_cents": planned_cost_cents,
        "missing": missing,
    }


def propose_job_change(job, owner_id, *, description, quantity, unit, unit_price):
    if job.user_id != owner_id:
        raise WorkflowError("Zákazka nepatrí k tomuto účtu.")
    if Invoice.query.filter_by(job_id=job.id, user_id=owner_id).first():
        raise WorkflowError("Po vystavení faktúry založ samostatnú zákazku pre ďalšiu prácu.")
    description = (description or "").strip()
    unit = (unit or "ks").strip()
    qty = _decimal(quantity, "Množstvo extra práce")
    price = _money(_decimal(unit_price, "Cena extra práce"))
    if (not description or len(description) > 200 or not unit or len(unit) > 20
            or qty <= 0 or qty > 100000 or price < 0 or price > 1000000):
        raise WorkflowError("Skontroluj popis, množstvo, jednotku a cenu dodatku.")
    unit_price_cents = int(price * 100)
    total_cents = int((qty * unit_price_cents).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    change = JobChange(user_id=owner_id, job_id=job.id, description=description,
                       quantity=qty, unit=unit, unit_price_cents=unit_price_cents,
                       total_cents=total_cents, status="proposed")
    db.session.add(change)
    return change


def approve_job_change(change, owner_id, *, approval_note):
    if change.user_id != owner_id:
        raise WorkflowError("Dodatok nepatrí k tomuto účtu.")
    if change.status == "approved":
        return change
    if change.status != "proposed":
        raise WorkflowError("Dodatok nie je pripravený na schválenie.")
    if Invoice.query.filter_by(job_id=change.job_id, user_id=owner_id).first():
        raise WorkflowError("Po vystavení faktúry nemožno schváliť ďalší dodatok na tú istú faktúru.")
    note = (approval_note or "").strip()
    if not 4 <= len(note) <= 500:
        raise WorkflowError("Zapíš spôsob a dátum súhlasu zákazníka (4–500 znakov).")
    change.approval_note = note
    change.approved_at = datetime.now(timezone.utc)
    change.status = "approved"
    return change
