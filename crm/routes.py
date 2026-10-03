from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import uuid
from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from extensions import db
from models import Client, Company, Job, JobNote, JobPlan, JobReceipt
from .receipts import ValidationError, clean_text, ensure_storage_capacity, format_money, original_path, parse_cents, parse_date, store_original, validate_image
from .ai_receipts import ExtractionError, available as ai_available, extract_fields

crm_bp = Blueprint('crm', __name__, url_prefix='/crm')
STATUSES = {'new':'Dopyt', 'inspection':'Obhliadka', 'offer_sent':'Ponuka', 'approved':'Schválené', 'in_progress':'Realizácia', 'done':'Hotovo', 'invoiced':'Fakturované', 'cancelled':'Zrušené'}

@crm_bp.before_request
def private_request():
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        origin = request.headers.get('Origin')
        if origin and origin != request.host_url.rstrip('/'):
            abort(403)

@crm_bp.after_request
def private_response(response):
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

@crm_bp.app_template_filter('crm_money')
def money_filter(value):
    return format_money(value)

@crm_bp.app_template_filter('crm_datetime')
def datetime_filter(value):
    if not value:
        return ''
    utc_value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    try:
        return utc_value.astimezone(ZoneInfo('Europe/Bratislava')).strftime('%d. %m. %Y, %H:%M')
    except ZoneInfoNotFoundError:
        return utc_value.strftime('%d. %m. %Y, %H:%M UTC')

@crm_bp.context_processor
def template_values():
    return {'crm_statuses': STATUSES}

def owned_job(job_id):
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    # Old records may carry links written before owner validation was introduced.
    if ((job.client_id is not None and not Client.query.filter_by(id=job.client_id,user_id=current_user.id).first())
            or (job.company_id is not None and not Company.query.filter_by(id=job.company_id,user_id=current_user.id).first())):
        abort(404)
    return job

def owned_receipt(receipt_id):
    return JobReceipt.query.filter_by(id=receipt_id, user_id=current_user.id).first_or_404()

def receipts_folder():
    return current_app.config.get('CRM_RECEIPT_FOLDER', current_app.instance_path + '/private_receipts')

def form_int(name):
    try:
        value = int(request.form.get(name, ''))
        if value < 0:
            raise ValueError
        return value
    except (TypeError, ValueError):
        raise ValidationError('Neplatný záznam. Obnovte stránku a skúste znova.') from None

def job_summary(job):
    rows = JobReceipt.query.filter_by(job_id=job.id, user_id=current_user.id).order_by(JobReceipt.created_at.desc()).all()
    notes = JobNote.query.filter_by(job_id=job.id, user_id=current_user.id).order_by(JobNote.created_at.desc(), JobNote.id.desc()).all()
    total = sum(row.amount_cents for row in rows if row.status == 'confirmed')
    plan = JobPlan.query.filter_by(job_id=job.id, user_id=current_user.id).first()
    return {'job_receipts':rows, 'job_notes':notes, 'receipt_total_cents':total, 'job_plan':plan}

@crm_bp.route('/')
@login_required
def index():
    jobs = Job.query.filter_by(user_id=current_user.id).order_by(Job.created_at.desc()).all()
    plans = {p.job_id:p for p in JobPlan.query.filter_by(user_id=current_user.id)}
    totals = dict(db.session.query(JobReceipt.job_id, func.sum(JobReceipt.amount_cents)).filter_by(user_id=current_user.id, status='confirmed').group_by(JobReceipt.job_id).all())
    clients = {c.id:c for c in Client.query.filter_by(user_id=current_user.id)}
    return render_template('crm/index.html', jobs=jobs, plans=plans, totals=totals, clients=clients, total=sum(totals.values()), price_total=sum(p.agreed_price_cents or 0 for p in plans.values()))

@crm_bp.route('/clients', methods=['GET', 'POST'])
@login_required
def clients():
    if request.method == 'POST':
        try:
            name = clean_text(request.form.get('name'),100,'meno',True)
            phone = clean_text(request.form.get('phone'),20,'telefón')
            email = clean_text(request.form.get('email'),100,'e-mail')
            if email:
                from email_validator import validate_email, EmailNotValidError
                try:
                    email=validate_email(email,check_deliverability=False).normalized
                except EmailNotValidError:
                    raise ValidationError('Skontrolujte e-mail.') from None
            client = Client(user_id=current_user.id, name=name, phone=phone, email=email, is_vat_payer=False)
            db.session.add(client)
            db.session.commit()
            flash('Zákazník je uložený. Teraz vytvorte zákazku.','success')
            return redirect(url_for('crm.create_job'))
        except ValidationError as error:
            flash(str(error),'danger')
    return render_template('crm/clients.html', clients=Client.query.filter_by(user_id=current_user.id).order_by(Client.name).all())

@crm_bp.route('/jobs/create', methods=['GET', 'POST'])
@login_required
def create_job():
    if request.method == 'POST':
        try:
            title = clean_text(request.form.get('title'),255,'názov zákazky',True)
            description = clean_text(request.form.get('description'),3000,'poznámky')
            client = Client.query.filter_by(id=form_int('client_id'), user_id=current_user.id).first()
            if not client:
                raise ValidationError('Vyberte vlastného zákazníka.')
            price = parse_cents(request.form.get('price'),optional=True)
            due = parse_date(request.form.get('due_date'),optional=True)
            job=Job(user_id=current_user.id,client_id=client.id,title=title,description=description,status='new')
            db.session.add(job)
            db.session.flush()
            db.session.add(JobPlan(job_id=job.id,user_id=current_user.id,agreed_price_cents=price,due_date=due))
            db.session.commit()
            flash('Zákazka je uložená.','success')
            return redirect(url_for('crm.detail',job_id=job.id))
        except ValidationError as error:
            db.session.rollback()
            flash(str(error),'danger')
    return render_template('crm/create.html',clients=Client.query.filter_by(user_id=current_user.id).order_by(Client.name).all())

@crm_bp.route('/jobs/<int:job_id>')
@login_required
def detail(job_id):
    job=owned_job(job_id)
    return render_template('crm/detail.html',job=job,note_draft='',note_error=None,**job_summary(job))

@crm_bp.route('/jobs/<int:job_id>/notes', methods=['POST'])
@login_required
def add_note(job_id):
    job = owned_job(job_id)
    draft = request.form.get('content', '')
    try:
        content = clean_text(draft, 3000, 'poznámka', True)
        db.session.add(JobNote(job_id=job.id, user_id=current_user.id, content=content, note_type='text'))
        db.session.commit()
        flash('Poznámka je uložená.', 'success')
        return redirect(url_for('crm.detail', job_id=job.id))
    except ValidationError as error:
        db.session.rollback()
        return render_template('crm/detail.html', job=job, note_draft=draft,
                               note_error=str(error), **job_summary(job))
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.error('Job note save failed')
        return render_template('crm/detail.html', job=job, note_draft=draft,
                               note_error='Poznámku sa nepodarilo uložiť. Skúste znova.',
                               **job_summary(job)), 503

@crm_bp.route('/jobs/<int:job_id>/status',methods=['POST'])
@login_required
def status(job_id):
    job=owned_job(job_id)
    value=request.form.get('status')
    if value not in STATUSES:
        abort(400)
    job.status=value
    db.session.commit()
    flash('Stav zákazky je uložený.','success')
    return redirect(url_for('crm.detail',job_id=job.id))

@crm_bp.route('/jobs/<int:job_id>/receipts/upload',methods=['POST'])
@login_required
def upload(job_id):
    job=owned_job(job_id)
    try:
        content,mime,digest=validate_image(request.files.get('file'))
        existing=JobReceipt.query.filter_by(user_id=current_user.id,sha256=digest).first()
        if existing:
            flash('Tento súbor už je uložený. Otváram existujúci bloček.','info')
            return redirect(url_for('crm.receipt',receipt_id=existing.id))
        original_name=clean_text(request.files['file'].filename,200,'názov súboru')
        maximum=current_app.config.get('CRM_RECEIPT_MAX_BYTES')
        if maximum is not None:
            ensure_storage_capacity(receipts_folder(),len(content),maximum)
        name=store_original(receipts_folder(),current_user.id,digest,content)
        row=JobReceipt(id=str(uuid.uuid4()),user_id=current_user.id,job_id=job.id,sha256=digest,object_name=name,
            original_name=original_name,mime=mime,status='draft')
        db.session.add(row)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            # A concurrent upload of the same image may have won. Do not delete shared immutable bytes.
            row=JobReceipt.query.filter_by(user_id=current_user.id,sha256=digest).first()
            if not row:
                raise
        return redirect(url_for('crm.receipt',receipt_id=row.id))
    except ValidationError as error:
        flash(str(error),'danger')
        return redirect(url_for('crm.detail',job_id=job.id))
    except (OSError,SQLAlchemyError):
        db.session.rollback()
        current_app.logger.error('Receipt upload failed')
        flash('Bloček sa nepodarilo uložiť. Skúste nahratie zopakovať.','danger')
        return redirect(url_for('crm.detail',job_id=job.id)),503

@crm_bp.route('/receipts/<receipt_id>',methods=['GET','POST'])
@login_required
def receipt(receipt_id):
    row=owned_receipt(receipt_id)
    error=None;code=200
    if request.method=='POST':
        try:
            if request.form.get('confirmed')!='yes':
                raise ValidationError('Potvrďte kontrolu údajov podľa originálu bločka.')
            job=owned_job(form_int('job_id'))
            vendor=clean_text(request.form.get('vendor'),120,'predajca',True)
            receipt_date=parse_date(request.form.get('receipt_date'))
            amount=parse_cents(request.form.get('amount'))
            if amount<=0:
                raise ValidationError('Suma musí byť väčšia ako nula. Vrátenie peňazí zatiaľ nemá samostatný postup.')
            revision=form_int('revision')
            ocr_text=clean_text(request.form.get('ocr_text'),20000,'prečítaný text')
            result=db.session.execute(update(JobReceipt).where(JobReceipt.id==row.id,JobReceipt.user_id==current_user.id,JobReceipt.revision==revision).values(
                job_id=job.id,vendor=vendor,receipt_date=receipt_date,amount_cents=amount,ocr_text=ocr_text,
                status='confirmed',confirmed_at=datetime.now(timezone.utc),revision=revision+1))
            if result.rowcount!=1:
                db.session.rollback()
                error='Bloček medzitým niekto upravil. Údaje neboli prepísané. Otvorte aktuálny záznam v novej karte a porovnajte ich.'
                code=409
            else:
                db.session.commit()
                flash('Náklad je potvrdený a uložený.','success')
                return redirect(url_for('crm.detail',job_id=job.id))
        except ValidationError as exc:
            db.session.rollback()
            error=str(exc);code=400
        except SQLAlchemyError:
            db.session.rollback()
            current_app.logger.error('Receipt confirmation failed')
            error='Uloženie sa nepodarilo potvrdiť. Formulár zostal zachovaný. Skúste znova.';code=503
    return render_template('crm/receipt.html',receipt=row,error=error,ai_available=ai_available(),jobs=Job.query.filter_by(user_id=current_user.id).order_by(Job.title).all()),code

@crm_bp.route('/receipts/<receipt_id>/extract', methods=['POST'])
@login_required
def extract(receipt_id):
    row=owned_receipt(receipt_id)
    owned_job(row.job_id)
    payload=request.get_json(silent=True)
    revision=payload.get('revision') if isinstance(payload,dict) else None
    manual=payload.get('manual',False) if isinstance(payload,dict) else False
    if type(revision) is not int or revision<0 or type(manual) is not bool:
        return jsonify(message='Neplatná revízia bločka. Obnovte stránku.'),400
    if row.revision!=revision or (row.status!='draft' and not (row.status=='confirmed' and manual)):
        return jsonify(message='Bloček sa medzitým zmenil alebo je potvrdený. Obnovte stránku a porovnajte údaje.'),409
    user_id=int(current_user.id)
    digest=row.sha256
    initial_status=row.status
    try:
        path=original_path(receipts_folder(),row)
        # Release the read transaction while waiting for the external provider.
        db.session.rollback()
        result=extract_fields(current_app.config.get('CRM_OPENAI_API_KEY',''),
            current_app.config.get('CRM_AI_STATE_PATH',current_app.instance_path+'/ai-state.sqlite3'),
            user_id,digest,path,daily_limit=current_app.config.get('CRM_AI_DAILY_LIMIT',30))
        fresh=JobReceipt.query.filter_by(id=receipt_id,user_id=user_id).first()
        if not fresh or fresh.status!=initial_status or fresh.revision!=revision or fresh.sha256!=digest:
            return jsonify(message='Bloček sa počas čítania zmenil. Obnovte stránku a porovnajte údaje.'),409
        return jsonify(result)
    except ValidationError:
        return jsonify(message='Originál bločka nie je dostupný.'),404
    except ExtractionError as error:
        return jsonify(message=str(error)),error.status
    except (OSError,SQLAlchemyError):
        db.session.rollback()
        current_app.logger.error('AI receipt extraction failed')
        return jsonify(message='AI čítanie nie je dostupné. Údaje môžete zadať ručne.'),503
    except Exception:
        db.session.rollback()
        current_app.logger.error('AI receipt extraction returned an unexpected failure')
        return jsonify(message='AI čítanie sa nepodarilo. Údaje môžete zadať ručne.'),503

@crm_bp.route('/receipts/<receipt_id>/original')
@login_required
def original(receipt_id):
    row=owned_receipt(receipt_id)
    try:
        path=original_path(receipts_folder(),row)
    except ValidationError:
        abort(404)
    response=send_file(path,mimetype=row.mime,download_name='blocek.'+{'image/jpeg':'jpg','image/png':'png','image/webp':'webp'}[row.mime])
    response.headers['Content-Security-Policy']="default-src 'none'; img-src 'self'; frame-ancestors 'self'"
    return response

@crm_bp.route('/progress')
@login_required
def progress():
    return render_template('crm/progress.html',clients=Client.query.filter_by(user_id=current_user.id).count(),jobs=Job.query.filter_by(user_id=current_user.id).count(),receipts=JobReceipt.query.filter_by(user_id=current_user.id,status='confirmed').count())

@crm_bp.route('/health')
def health():
    return jsonify(app='invoicemaker-crm',version=1)
