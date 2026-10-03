"""Private single-firm CRM pilot behind a trusted, loopback Nginx proxy.

No production factory, dotenv, payments, mail jobs or existing invoice DB.
"""
from collections import deque
from datetime import timedelta
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit

from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for
from flask_login import LoginManager, current_user, login_user, logout_user
from flask_wtf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db
from models import User
from crm.routes import crm_bp
from crm.ai_receipts import api_key

ROOT = Path(__file__).resolve().parent


class LoopbackProxyOnly:
    """Check the transport peer before any forwarded header is trusted."""
    def __init__(self, application):
        self.application = application

    def __call__(self, environ, start_response):
        if environ.get('REMOTE_ADDR') not in {'127.0.0.1', '::1'}:
            start_response('403 Forbidden', [('Content-Type', 'text/plain'), ('Content-Length', '9')])
            return [b'Forbidden']
        return self.application(environ, start_response)


def create_pilot_app(config=None):
    settings = dict(config or {})
    instance = Path(settings.get('CRM_INSTANCE_DIR') or os.environ.get('CRM_INSTANCE_DIR', ROOT / 'instance' / 'crm_pilot')).resolve()
    origin = settings.get('CRM_PUBLIC_ORIGIN') or os.environ.get('CRM_PUBLIC_ORIGIN')
    prefix = settings.get('CRM_URL_PREFIX') or os.environ.get('CRM_URL_PREFIX', '/remeselnici')
    parsed = urlsplit(origin or '')
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment or parsed.port not in {None, 443}):
        raise ValueError('Explicitný CRM_PUBLIC_ORIGIN musí byť presná HTTPS adresa bez cesty.')
    if not prefix.startswith('/') or prefix.endswith('/') or '//' in prefix or '..' in prefix:
        raise ValueError('Neplatný CRM_URL_PREFIX.')
    if not settings.get('CRM_ACCESS_HASH') or not settings.get('SECRET_KEY'):
        auth = json.loads((instance / 'pilot-auth.json').read_text(encoding='utf-8'))
        settings.setdefault('CRM_ACCESS_HASH', auth['access_hash'])
        settings.setdefault('SECRET_KEY', auth['secret_key'])
    if not settings['CRM_ACCESS_HASH'] or len(settings['SECRET_KEY']) < 24:
        raise ValueError('Chýba bezpečná konfigurácia prihlásenia.')

    app = Flask(__name__, instance_path=str(instance))
    app.config.update(
        SQLALCHEMY_DATABASE_URI='sqlite:///' + (instance / 'crm.sqlite3').as_posix(),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        CRM_RECEIPT_FOLDER=str(instance / 'private_receipts'),
        CRM_LOCAL_ONLY=True, CRM_PILOT=True,
        CRM_PUBLIC_ORIGIN=origin, CRM_URL_PREFIX=prefix,
        MAX_CONTENT_LENGTH=9 * 1024 * 1024, MAX_FORM_MEMORY_SIZE=128 * 1024,
        MAX_FORM_PARTS=30,
        CRM_RECEIPT_MAX_BYTES=500 * 1024 * 1024,
        CRM_AI_STATE_PATH=str(instance / 'ai-state.sqlite3'),
        CRM_AI_DAILY_LIMIT=30,
        SESSION_COOKIE_NAME='crm_pilot_session', SESSION_COOKIE_PATH=prefix,
        SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax', PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        SESSION_REFRESH_EACH_REQUEST=False,
    )
    app.config.update(settings)
    app.config['CRM_OPENAI_API_KEY']=api_key(settings,instance)
    db.init_app(app)
    manager = LoginManager(app)
    manager.login_view = 'pilot_login'
    attempts = deque()
    attempt_lock = threading.Lock()
    auth_version = hashlib.sha256(app.config['CRM_ACCESS_HASH'].encode()).hexdigest()

    @manager.user_loader
    def load_user(user_id):
        try:
            return db.session.get(User, int(user_id))
        except (ValueError, TypeError):
            return None

    @app.before_request
    def private_pilot():
        if request.host != parsed.netloc or not request.is_secure or request.script_root != prefix:
            abort(403)
        if request.method not in {'GET', 'HEAD', 'OPTIONS'} and request.headers.get('Origin') != origin:
            abort(403)
        public = request.endpoint in {'pilot_login', 'pilot_health'} or (
            request.endpoint == 'static' and request.path in {'/static/crm/crm.css', '/static/crm/favicon.svg'})
        authenticated = current_user.is_authenticated and session.get('pilot_auth_version') == auth_version
        if not public and not authenticated:
            session.clear()
            if request.method not in {'GET', 'HEAD'}:
                abort(401)
            return redirect(url_for('pilot_login'))

    # Guard host/origin/auth before parsing a submitted form; then protect every POST.
    CSRFProtect(app)

    @app.after_request
    def private_headers(response):
        response.headers['Cache-Control'] = 'private, no-store'
        if request.endpoint == 'static' and request.path.startswith('/static/crm/vendor/ocr/') and response.status_code == 200:
            response.headers['Cache-Control'] = 'private, max-age=86400'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self'; "
            "img-src 'self' blob: data:; worker-src 'self' blob:; connect-src 'self'; "
            "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
        return response

    @app.route('/login', methods=['GET', 'POST'])
    def pilot_login():
        error = None
        if request.method == 'POST':
            # One Gunicorn worker: the lock shares the rate limit across its threads.
            with attempt_lock:
                now = time.monotonic()
                while attempts and attempts[0] <= now - 60:
                    attempts.popleft()
                if len(attempts) >= 20:
                    return render_template('crm/login.html', error='Príliš veľa pokusov. Počkajte minútu a skúste znova.'), 429, {'Retry-After': '60'}
                attempts.append(now)
            entered = request.form.get('access_code', '').strip()
            if not entered or len(entered) > 128 or not check_password_hash(app.config['CRM_ACCESS_HASH'], entered):
                error = 'Prístupový kód nie je správny.'
                return render_template('crm/login.html', error=error), 401
            user = User.query.filter_by(email='pilot@example.invalid').first()
            if user is None:
                abort(503)
            session.clear()
            login_user(user, remember=False)
            session['pilot_auth_version'] = auth_version
            session.permanent = True
            return redirect(url_for('crm.index'))
        return render_template('crm/login.html', error=error)

    @app.post('/logout')
    def pilot_logout():
        logout_user()
        session.clear()
        return redirect(url_for('pilot_login'))

    @app.get('/')
    def pilot_home():
        return redirect(url_for('crm.index'))

    @app.get('/health')
    def pilot_health():
        return jsonify(app='invoicemaker-crm-pilot', version=1)

    @app.errorhandler(413)
    def too_large(error):
        return 'Požiadavka je príliš veľká. Bloček môže mať najviac 8 MB.', 413

    app.register_blueprint(crm_bp)
    app.wsgi_app = LoopbackProxyOnly(ProxyFix(app.wsgi_app, x_for=0, x_proto=1, x_host=0, x_port=0, x_prefix=1))
    return app


def initialize_pilot():
    """Explicit first initialization only; existing credentials/data are preserved."""
    instance = Path(os.environ['CRM_INSTANCE_DIR']).resolve()
    instance.mkdir(parents=True, exist_ok=True, mode=0o700)
    database = instance / 'crm.sqlite3'
    auth_path = instance / 'pilot-auth.json'
    if database.exists():
        raise SystemExit('Pilot už má databázu. --init ju ani prihlasovanie nemení.')
    access_code = None
    if not auth_path.exists():
        access_code = secrets.token_urlsafe(18)
        auth = {'access_hash': generate_password_hash(access_code), 'secret_key': secrets.token_hex(32)}
        descriptor = os.open(auth_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
            json.dump(auth, output)
    app = create_pilot_app()
    with app.app_context():
        db.create_all()
        db.session.add(User(email='pilot@example.invalid', username='crm_pilot', password_hash='login-only-via-private-pilot-code'))
        db.session.commit()
    os.chmod(database, 0o600)
    if access_code:
        print('NOVY_PRISTUPOVY_KOD=' + access_code)
    print('Inicializovaný samostatný CRM pilot; neobsahuje produkčné zákaznícke dáta.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--init', action='store_true')
    args = parser.parse_args()
    if args.init:
        initialize_pilot()
    else:
        parser.error('Na VPS spúšťajte cez Gunicorn. Prvá inicializácia: --init.')
