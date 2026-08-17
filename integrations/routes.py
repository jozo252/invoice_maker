from flask import Blueprint, g, jsonify

from integrations.auth import require_veduci_token
from integrations.service import overdue_invoice_summary
from models import User

integrations_bp = Blueprint(
    "integrations",
    __name__,
    url_prefix="/api/v1/integrations/veduci",
)


@integrations_bp.after_request
def prevent_sensitive_caching(response):
    response.headers["Cache-Control"] = "no-store"
    return response


@integrations_bp.get("/invoices/overdue")
@require_veduci_token
def overdue_invoices():
    if User.query.filter_by(id=g.integration_user_id).first() is None:
        return jsonify({"error": "integration_user_not_found"}), 503
    return jsonify(overdue_invoice_summary(g.integration_user_id))
