"""Isolated, loopback-only preview. Does not import payment, mail, AI or the production factory."""
from pathlib import Path
import secrets
from flask import Flask, abort, jsonify, redirect, request, url_for
from flask_login import LoginManager, login_user
from flask_wtf import CSRFProtect
from flask_migrate import Migrate
from extensions import db
from models import User
from crm.routes import crm_bp

ROOT=Path(__file__).resolve().parent

def create_local_app(test_config=None):
    local_instance=ROOT/'instance'/'crm_local'
    local_instance.mkdir(parents=True,exist_ok=True)
    secret_path=local_instance/'session.key'
    if not secret_path.exists():
        try:
            with secret_path.open('x',encoding='ascii') as output:
                output.write(secrets.token_hex(32))
        except FileExistsError:
            pass
    app=Flask(__name__,instance_path=str(local_instance))
    app.config.update(SECRET_KEY=secret_path.read_text(encoding='ascii'),SQLALCHEMY_DATABASE_URI='sqlite:///'+(local_instance/'crm.sqlite3').as_posix(),SQLALCHEMY_TRACK_MODIFICATIONS=False,CRM_RECEIPT_FOLDER=str(local_instance/'private_receipts'),CRM_LOCAL_ONLY=True,MAX_CONTENT_LENGTH=9*1024*1024,MAX_FORM_MEMORY_SIZE=128*1024,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_HTTPONLY=True)
    if test_config:
        app.config.update(test_config)
    db.init_app(app)
    Migrate(app,db)
    CSRFProtect(app)
    manager=LoginManager(app)
    manager.login_view='local_home'
    @manager.user_loader
    def load_user(user_id):
        try:return db.session.get(User,int(user_id))
        except (ValueError,TypeError):return None
    @manager.unauthorized_handler
    def unauthorized():
        return 'Najprv otvorte lokálny pracovný priestor na /.',401
    @app.before_request
    def loopback_only():
        if request.remote_addr not in {'127.0.0.1','::1'} or request.host not in {'127.0.0.1:5180','localhost:5180','localhost'}:
            abort(403)
        if request.method not in {'GET','HEAD','OPTIONS'} and request.headers.get('Origin') not in {request.host_url.rstrip('/')}:
            abort(403)
    @app.route('/')
    def local_home():
        user=User.query.filter_by(email='local-crm@example.invalid').first()
        if user is None:
            user=User(email='local-crm@example.invalid',username='local_crm',password_hash='local-preview-login-disabled')
            db.session.add(user);db.session.commit()
        login_user(user)
        return redirect(url_for('crm.index'))
    @app.errorhandler(413)
    def too_large(error):
        return 'Požiadavka je príliš veľká. Bloček môže mať najviac 8 MB.',413
    app.register_blueprint(crm_bp)
    return app

if __name__=='__main__':
    import argparse
    import json
    import socket
    import threading
    import time
    import urllib.request
    import webbrowser
    parser=argparse.ArgumentParser()
    parser.add_argument('--init',action='store_true')
    parser.add_argument('--open',action='store_true',help='Otvoriť prehliadač až po spustení servera.')
    args=parser.parse_args()
    def ready():
        try:
            with urllib.request.urlopen('http://127.0.0.1:5180/crm/health',timeout=1) as response:
                return json.load(response).get('app')=='invoicemaker-crm'
        except (OSError,ValueError):
            return False
    # A repeated click reuses this pilot instead of racing its database initialization.
    with socket.socket() as check:
        occupied=check.connect_ex(('127.0.0.1',5180))==0
    if occupied:
        if args.open and ready():
            webbrowser.open('http://127.0.0.1:5180/')
            raise SystemExit(0)
        parser.error('Port 5180 už používa iný proces. Najprv ukončite staré okno CRM.')
    app=create_local_app()
    with app.app_context():
        database=Path(app.instance_path)/'crm.sqlite3'
        if args.init:
            # This explicit path can never be invoices.db. Only a new, isolated pilot is initialized.
            if database.exists():
                print('Lokálna databáza už existuje. Schému aktualizujte migráciami; údaje sa nemenia.')
            else:
                db.create_all()
                print('Inicializovaný nový lokálny pilot.')
        elif not database.exists():
            parser.error('Najprv spustite crm_local.py --init.')
    if args.open:
        def open_when_ready():
            for _ in range(60):
                if ready():
                    webbrowser.open('http://127.0.0.1:5180/')
                    return
                time.sleep(.25)
        threading.Thread(target=open_when_ready,daemon=True).start()
    print('InvoiceMaker CRM: http://127.0.0.1:5180/ — iba lokálne, ukončenie Ctrl+C.')
    app.run(host='127.0.0.1',port=5180,debug=False,use_reloader=False)
