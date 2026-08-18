from functools import wraps
from hmac import compare_digest

from flask import current_app, g, jsonify, request


def require_veduci_token(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        expected_token = current_app.config.get("VEDUCI_INTEGRATION_TOKEN")
        user_id = current_app.config.get("VEDUCI_INTEGRATION_USER_ID")
        if not expected_token or not user_id:
            return jsonify({"error": "integration_not_configured"}), 503

        scheme, separator, supplied_token = request.headers.get(
            "Authorization", ""
        ).partition(" ")
        token_is_valid = (
            bool(separator)
            and scheme.lower() == "bearer"
            and bool(supplied_token)
            and compare_digest(supplied_token, expected_token)
        )
        if not token_is_valid:
            response = jsonify({"error": "unauthorized"})
            response.status_code = 401
            response.headers["WWW-Authenticate"] = "Bearer"
            return response

        g.integration_user_id = user_id
        return view(*args, **kwargs)

    return wrapped
