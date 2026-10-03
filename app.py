# app.py
from flask import Flask, abort, request
from extensions import db, mail  # <--- import from extensions
import os
from dotenv import load_dotenv
from flask_migrate import Migrate
from flask_wtf import CSRFProtect
from flask_login import LoginManager
from sqlalchemy import event
from sqlalchemy.engine import Engine
import sqlite3
from models import User  # <--- import User model here to avoid circular imports

csrf = CSRFProtect()


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    # zapni iba pre SQLite, na Postgres/MySQL sa toto nespustí
    if isinstance(dbapi_connection, sqlite3.Connection):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON;")
        cur.close()



load_dotenv()  # Load environment variables from .env file
login_manager=LoginManager()
def create_app(test_config=None):
    app = Flask(__name__)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///invoices.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
    app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT') or '587')
    app.config['MAIL_USE_TLS'] = (os.getenv('MAIL_USE_TLS') or 'false').lower() == 'true'
    app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')  # ✅ správne napísané
    app.config["STRIPE_WEBHOOK_SECRET"] = os.getenv("STRIPE_WEBHOOK_SECRET")
    app.config["STRIPE_API_KEY"] = os.getenv("STRIPE_API_KEY")
    app.config["STRIPE_PUBLIC_KEY"] = os.getenv("STRIPE_PUBLIC_KEY")
    app.config["STRIPE_PRICE_ID"] = os.getenv("STRIPE_PRICE_ID")
    app.config["STRIPE_PRODUCT_ID"] = os.getenv("STRIPE_PRODUCT_ID")
    app.config["SUCCESS_URL"] = os.getenv("SUCCESS_URL")    
    app.config["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
    app.config["VEDUCI_INTEGRATION_TOKEN"] = os.getenv("VEDUCI_INTEGRATION_TOKEN")
    integration_user_id = os.getenv("VEDUCI_INTEGRATION_USER_ID")
    try:
        app.config["VEDUCI_INTEGRATION_USER_ID"] = (
            int(integration_user_id) if integration_user_id else None
        )
    except ValueError as exc:
        raise RuntimeError("VEDUCI_INTEGRATION_USER_ID must be an integer") from exc

    token = app.config["VEDUCI_INTEGRATION_TOKEN"]
    user_id = app.config["VEDUCI_INTEGRATION_USER_ID"]
    if bool(token) != bool(user_id):
        raise RuntimeError(
            "VEDUCI_INTEGRATION_TOKEN and VEDUCI_INTEGRATION_USER_ID must be configured together"
        )
    if token and len(token) < 32:
        raise RuntimeError("VEDUCI_INTEGRATION_TOKEN must contain at least 32 characters")
    app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024
    if test_config:
        app.config.update(test_config)

    #-------------------------------------------------------------------stamp

    app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'uploads')
    app.config['ALLOWED_STAMP_EXT'] = {'png', 'jpg', 'jpeg', 'webp'}
    

    

    db.init_app(app)
    migrate = Migrate(app, db)  # Initialize Flask-Migrate
    csrf.init_app(app)
    mail.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'main.login'  # redirect here if @login_required fails

    @app.before_request
    def protect_legacy_job_uploads():
        # The Flask static route must not expose old job files without owner
        # checks. Deployments serving /static directly need the same deny rule.
        if request.endpoint == 'static' and request.path.startswith('/static/uploads/jobs/'):
            abort(404)

    @login_manager.user_loader
    def load_user(user_id):
            return User.query.get(int(user_id))

    from routes import main as main_blueprint
    from aibot_routes import aibot as aibot_bp
    from offers import offers
    from jobs.routes import jobs_bp
    from assistant.routes import assistant_bp
    from crm.routes import crm_bp
    from workboard import workboard
    from pricebook import pricebook
    from integrations.routes import integrations_bp
    app.register_blueprint(main_blueprint)
    app.register_blueprint(aibot_bp)
    app.register_blueprint(offers)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(assistant_bp)
    app.register_blueprint(crm_bp)
    app.register_blueprint(workboard)
    app.register_blueprint(pricebook)
    app.register_blueprint(integrations_bp)

    return app
