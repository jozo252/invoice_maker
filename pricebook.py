"""A small owner-managed quote price list with explicit cost provenance."""

from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import PriceEntry


pricebook = Blueprint("pricebook", __name__)


def cents(raw, *, optional=False):
    if optional and (raw is None or str(raw).strip() == ""):
        return None
    try:
        value = Decimal(str(raw).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Cena musí byť platné číslo v EUR.") from None
    if not value.is_finite() or value < 0 or value > 1000000 or value.as_tuple().exponent < -2:
        raise ValueError("Cena musí byť nezáporná a mať najviac dve desatinné miesta.")
    return int(value * 100)


@pricebook.route("/pricebook", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        kind = (request.form.get("kind") or "").strip()
        description = (request.form.get("description") or "").strip()
        unit = (request.form.get("unit") or "").strip()
        source_note = (request.form.get("source_note") or "").strip()
        try:
            sale = cents(request.form.get("sale_price"))
            cost = cents(request.form.get("cost"), optional=True)
            if (kind not in {"labor", "material"} or not description or len(description) > 200
                    or not unit or len(unit) > 20 or len(source_note) > 200 or sale <= 0):
                raise ValueError("Vyplň platný druh, názov, jednotku a kladnú predajnú cenu.")
            db.session.add(PriceEntry(user_id=current_user.id, kind=kind,
                                      description=description, unit=unit,
                                      sale_price_cents=sale, cost_cents=cost,
                                      source_note=source_note or None))
            db.session.commit()
            flash("Položka cenníka je uložená.", "success")
            return redirect(url_for("pricebook.index"))
        except ValueError as error:
            flash(str(error), "danger")
    entries = PriceEntry.query.filter_by(user_id=current_user.id).order_by(PriceEntry.kind, PriceEntry.description).all()
    return render_template("pricebook.html", entries=entries)


@pricebook.route("/pricebook/<int:entry_id>/update", methods=["POST"])
@login_required
def update(entry_id):
    entry = PriceEntry.query.filter_by(id=entry_id, user_id=current_user.id).first_or_404()
    try:
        sale = cents(request.form.get("sale_price"))
        cost = cents(request.form.get("cost"), optional=True)
        source_note = (request.form.get("source_note") or "").strip()
        if sale <= 0 or len(source_note) > 200:
            raise ValueError("Skontroluj cenu a zdroj.")
        entry.sale_price_cents = sale
        entry.cost_cents = cost
        entry.source_note = source_note or None
        db.session.commit()
        flash("Cenník je aktualizovaný; staré ponuky sa nemenia.", "success")
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")
    return redirect(url_for("pricebook.index"))
