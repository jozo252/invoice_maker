# app.py
from flask import Flask
from extensions import db, mail  # <--- import from extensions
import os
from dotenv import load_dotenv
from flask_migrate import Migrate
from flask_wtf import CSRFProtect
from flask_login import LoginManager
from models import User
load_dotenv()  # Load environment variables from .env file
login_manager=LoginManager()
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
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')  # ✅ správne napísané

    csrf = CSRFProtect(app)
    

    db.init_app(app)
    migrate = Migrate(app, db)  # Initialize Flask-Migrate
    csrf.init_app(app)
    mail.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'main.login'  # redirect here if @login_required fails

    @login_manager.user_loader
    def load_user(user_id):
            return User.query.get(int(user_id))

    from routes import main as main_blueprint
    app.register_blueprint(main_blueprint)

    return app
