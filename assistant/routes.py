from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required
from assistant.agent import run_assistant

assistant_bp = Blueprint("assistant", __name__, url_prefix="/assistant")

@assistant_bp.route("/", methods=["GET"])
@login_required
def assistant_page():
    return render_template("assistant.html")

@assistant_bp.route("/chat", methods=["POST"])
@login_required
def chat():
    data = request.get_json()

    if not data or "message" not in data:
        return jsonify({
            "error": "Chýba správa."
        }), 400

    answer = run_assistant(data["message"])

    return jsonify({
        "answer": answer
    })