# app.py
from flask import Flask
from extensions import db, mail  # <--- import from extensions
import os
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file

def create_app():
    app = Flask(__name__)
    
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///invoices.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = 'adamgallik11@gmail.com'
    app.config['MAIL_PASSWORD'] = os.getenv('SMTP_password')
    app.config['MAIL_DEFAULT_SENDER'] = 'adamgallik11@gmail.com'

    db.init_app(app)
    mail.init_app(app)

    from routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    return app
