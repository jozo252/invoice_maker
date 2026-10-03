from flask import Blueprint, flash, redirect, request, url_for
from flask import render_template, send_file, abort
from flask_login import login_required, current_user
from models import Client, Company, Job, JobNote, JobAttachment, JobMaterial, JobCost, JobChange
from extensions import db
import uuid
from werkzeug.utils import secure_filename
from flask import current_app
from io import BytesIO
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from sqlalchemy import or_
from datetime import date, datetime, timedelta
from sqlalchemy.exc import IntegrityError
from models import Invoice, WorkActivity
from workflows import (MATERIAL_STATES, WorkflowError, add_job_cost,
                       add_job_material, approve_job_change, issue_job_invoice,
                       job_financials, job_invoice_source, propose_job_change)


jobs_bp = Blueprint("jobs", __name__, template_folder="templates/jobs")


ALLOWED_JOB_EXTENSIONS = {"jpg", "jpeg", "png", "pdf", "webp"}
MAX_JOB_FILE_BYTES = 12 * 1024 * 1024
JOB_IMAGE_MIME = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def allowed_job_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_JOB_EXTENSIONS




@jobs_bp.route("/jobs")
@login_required
def jobs_list():
    jobs = Job.query.filter_by(user_id=current_user.id).order_by(Job.created_at.desc()).all()
    return render_template("jobs/list.html", jobs=jobs)
@jobs_bp.route("/jobs/<int:job_id>")
@login_required
def job_detail(job_id):
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    invoice = Invoice.query.filter_by(job_id=job.id, user_id=current_user.id).first()
    photo_query = (request.args.get("q") or "").strip()[:100]
    attachments_query = JobAttachment.query.filter_by(job_id=job.id, user_id=current_user.id)
    if photo_query:
        match = f"%{photo_query}%"
        attachments_query = attachments_query.filter(or_(
            JobAttachment.room_label.ilike(match), JobAttachment.element_label.ilike(match),
            JobAttachment.cable_type.ilike(match), JobAttachment.route_note.ilike(match),
            JobAttachment.original_filename.ilike(match)))
    attachments = attachments_query.order_by(JobAttachment.created_at.desc()).all()
    materials = JobMaterial.query.filter_by(job_id=job.id, user_id=current_user.id).order_by(JobMaterial.id.desc()).all()
    costs = JobCost.query.filter_by(job_id=job.id, user_id=current_user.id).order_by(JobCost.occurred_on.desc(), JobCost.id.desc()).all()
    changes = JobChange.query.filter_by(job_id=job.id, user_id=current_user.id).order_by(JobChange.id.desc()).all()
    activities = WorkActivity.query.filter_by(job_id=job.id, user_id=current_user.id).order_by(WorkActivity.starts_at.desc()).all()
    finances = job_financials(job, current_user.id)
    return render_template("jobs/detail.html", job=job, job_invoice=invoice,
                           attachments=attachments, photo_query=photo_query,
                           materials=materials, costs=costs, changes=changes,
                           finances=finances,
                           activities=activities,
                           today=date.today())


@jobs_bp.route("/jobs/<int:job_id>/activities", methods=["POST"])
@login_required
def job_add_activity(job_id):
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    kind = (request.form.get("kind") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    try:
        starts_at = datetime.fromisoformat(request.form.get("starts_at") or "")
    except ValueError:
        flash("Zadaj platný termín.", "danger")
        return redirect(url_for("jobs.job_detail", job_id=job.id))
    if kind not in {"service", "work"} or not notes or len(notes) > 3000 or starts_at.tzinfo is not None:
        flash("Zadaj druh práce a krátku poznámku.", "danger")
        return redirect(url_for("jobs.job_detail", job_id=job.id))
    db.session.add(WorkActivity(user_id=current_user.id, job_id=job.id,
                                kind=kind, starts_at=starts_at, notes=notes,
                                status="planned"))
    db.session.commit()
    flash("Termín je uložený.", "success")
    return redirect(url_for("jobs.job_detail", job_id=job.id))


@jobs_bp.route("/jobs/<int:job_id>/activities/<int:activity_id>/done", methods=["POST"])
@login_required
def job_finish_activity(job_id, activity_id):
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    activity = WorkActivity.query.filter_by(id=activity_id, job_id=job.id,
                                             user_id=current_user.id).first_or_404()
    activity.status = "done"
    db.session.commit()
    return redirect(url_for("jobs.job_detail", job_id=job.id))


@jobs_bp.route("/jobs/<int:job_id>/materials", methods=["POST"])
@login_required
def job_add_material(job_id):
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    try:
        add_job_material(job, current_user.id,
                         description=request.form.get("description"),
                         quantity=request.form.get("quantity"),
                         unit=request.form.get("unit"))
        db.session.commit()
        flash("Materiál je v zozname zákazky.", "success")
    except WorkflowError as error:
        db.session.rollback()
        flash(str(error), "danger")
    return redirect(url_for("jobs.job_detail", job_id=job.id))


@jobs_bp.route("/jobs/<int:job_id>/materials/<int:material_id>/status", methods=["POST"])
@login_required
def job_material_status(job_id, material_id):
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    material = JobMaterial.query.filter_by(id=material_id, job_id=job.id,
                                           user_id=current_user.id).first_or_404()
    status = request.form.get("status")
    if status not in MATERIAL_STATES:
        flash("Neplatný stav materiálu.", "danger")
    else:
        material.status = status
        db.session.commit()
        flash("Stav materiálu je uložený.", "success")
    return redirect(url_for("jobs.job_detail", job_id=job.id))


@jobs_bp.route("/jobs/<int:job_id>/costs", methods=["POST"])
@login_required
def job_add_cost(job_id):
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    try:
        occurred_on = date.fromisoformat(request.form.get("occurred_on", ""))
        add_job_cost(job, current_user.id,
                     category=request.form.get("category"),
                     description=request.form.get("description"),
                     occurred_on=occurred_on,
                     minutes=request.form.get("minutes"),
                     hourly_cost=request.form.get("hourly_cost"),
                     amount=request.form.get("amount"))
        db.session.commit()
        flash("Priamy náklad je uložený.", "success")
    except (ValueError, WorkflowError) as error:
        db.session.rollback()
        flash(str(error) if isinstance(error, WorkflowError) else "Zadaj platný dátum.", "danger")
    return redirect(url_for("jobs.job_detail", job_id=job.id))


@jobs_bp.route("/jobs/<int:job_id>/costs/<int:cost_id>/delete", methods=["POST"])
@login_required
def job_delete_cost(job_id, cost_id):
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    cost = JobCost.query.filter_by(id=cost_id, job_id=job.id, user_id=current_user.id).first_or_404()
    db.session.delete(cost)
    db.session.commit()
    flash("Nesprávny náklad bol odstránený.", "success")
    return redirect(url_for("jobs.job_detail", job_id=job.id))


@jobs_bp.route("/jobs/<int:job_id>/changes", methods=["POST"])
@login_required
def job_propose_change(job_id):
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    try:
        propose_job_change(job, current_user.id,
                           description=request.form.get("description"),
                           quantity=request.form.get("quantity"),
                           unit=request.form.get("unit"),
                           unit_price=request.form.get("unit_price"))
        db.session.commit()
        flash("Dodatok je pripravený na odsúhlasenie.", "success")
    except WorkflowError as error:
        db.session.rollback()
        flash(str(error), "danger")
    return redirect(url_for("jobs.job_detail", job_id=job.id))


@jobs_bp.route("/jobs/<int:job_id>/changes/<int:change_id>/approve", methods=["POST"])
@login_required
def job_approve_change(job_id, change_id):
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    change = JobChange.query.filter_by(id=change_id, job_id=job.id,
                                       user_id=current_user.id).first_or_404()
    try:
        approve_job_change(change, current_user.id,
                           approval_note=request.form.get("approval_note"))
        db.session.commit()
        flash("Odsúhlasený dodatok sa zahrnie do faktúry.", "success")
    except WorkflowError as error:
        db.session.rollback()
        flash(str(error), "danger")
    return redirect(url_for("jobs.job_detail", job_id=job.id))


@jobs_bp.route("/jobs/<int:job_id>/invoice", methods=["GET", "POST"])
@login_required
def job_invoice(job_id):
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    existing = Invoice.query.filter_by(job_id=job.id, user_id=current_user.id).first()
    if existing:
        return redirect(url_for("main.view_invoice", invoice_id=existing.id))
    try:
        revision, client, company, payload = job_invoice_source(job, current_user.id)
    except WorkflowError as error:
        flash(str(error), "danger")
        return redirect(url_for("jobs.job_detail", job_id=job.id))
    if request.method == "POST":
        try:
            issue_date = date.fromisoformat(request.form.get("issue_date", ""))
            delivery_date = date.fromisoformat(request.form.get("delivery_date", ""))
            due_date = date.fromisoformat(request.form.get("due_date", ""))
            if request.form.get("confirmed") != "yes":
                raise WorkflowError("Pred vystavením potvrď kontrolu údajov.")
            invoice = issue_job_invoice(
                job, current_user.id, issue_date=issue_date,
                delivery_date=delivery_date, due_date=due_date,
                vat_rate=request.form.get("vat_rate", ""),
                payment_method=request.form.get("payment_method", "bank_transfer"),
            )
            db.session.commit()
            flash("Faktúra bola vystavená zo schválenej ponuky.", "success")
            return redirect(url_for("main.view_invoice", invoice_id=invoice.id))
        except (ValueError, WorkflowError, IntegrityError) as error:
            db.session.rollback()
            flash(str(error) if isinstance(error, WorkflowError) else "Faktúru sa nepodarilo vystaviť. Skontroluj dátumy a číslo.", "danger")
    today = date.today()
    return render_template("jobs/invoice_review.html", job=job, revision=revision,
                           client=client, company=company, payload=payload,
                           today=today, suggested_due=today + timedelta(days=14))



@jobs_bp.route("/jobs/create", methods=["GET", "POST"])
@login_required
def job_create():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        client_id = request.form.get("client_id") or None
        company_id = request.form.get("company_id") or None

        if not title:
            flash("Názov zákazky je povinný.", "danger")
            return redirect(url_for("jobs.job_create"))

        # A submitted ID must belong to the signed-in account, not only exist.
        try:
            client_id = int(client_id) if client_id else None
            company_id = int(company_id) if company_id else None
        except (ValueError, TypeError):
            flash("Vyberte platného zákazníka a firmu.", "danger")
            return redirect(url_for("jobs.job_create"))
        if ((client_id is not None and not Client.query.filter_by(id=client_id, user_id=current_user.id).first())
                or (company_id is not None and not Company.query.filter_by(id=company_id, user_id=current_user.id).first())):
            flash("Zákazník a firma musia patriť k vášmu účtu.", "danger")
            return redirect(url_for("jobs.job_create"))

        job = Job(
            user_id=current_user.id,
            title=title,
            description=description,
            client_id=client_id,
            company_id=company_id,
            status="new",
        )

        db.session.add(job)
        db.session.commit()

        flash("Zákazka bola vytvorená.", "success")
        return redirect(url_for("jobs.job_detail", job_id=job.id))

    clients = (
        Client.query
        .filter_by(user_id=current_user.id)
        .order_by(Client.name.asc())
        .all()
    )

    companies = (
        Company.query
        .filter_by(user_id=current_user.id)
        .all()
    )

    return render_template(
        "jobs/create.html",
        clients=clients,
        companies=companies,
    )





@jobs_bp.route("/jobs/<int:job_id>/notes/add", methods=["POST"])
@login_required
def job_add_note(job_id):
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()

    content = request.form.get("content")
    note_type = request.form.get("note_type", "text")

    if not content:
        flash("Poznámka nemôže byť prázdna.", "danger")
        return redirect(url_for("jobs.job_detail", job_id=job.id))

    note = JobNote(
        job_id=job.id,
        user_id=current_user.id,
        content=content,
        note_type=note_type
    )

    db.session.add(note)
    db.session.commit()

    flash("Poznámka bola pridaná.", "success")
    return redirect(url_for("jobs.job_detail", job_id=job.id))

@jobs_bp.route("/jobs/<int:job_id>/attachments/add", methods=["POST"])
@login_required
def job_add_attachment(job_id):
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()

    file = request.files.get("file")

    if not file or file.filename == "":
        flash("Nevybral si žiadny súbor.", "danger")
        return redirect(url_for("jobs.job_detail", job_id=job.id))

    if not allowed_job_file(file.filename):
        flash("Nepovolený typ súboru.", "danger")
        return redirect(url_for("jobs.job_detail", job_id=job.id))

    original_filename = secure_filename(file.filename) or "priloha"
    ext = original_filename.rsplit(".", 1)[1].lower()
    unique_filename = f"{uuid.uuid4().hex}.{ext}"
    content = file.stream.read(MAX_JOB_FILE_BYTES + 1)
    if not content or len(content) > MAX_JOB_FILE_BYTES:
        flash("Príloha musí mať najviac 12 MB.", "danger")
        return redirect(url_for("jobs.job_detail", job_id=job.id))
    if ext == "pdf":
        valid = content.startswith(b"%PDF-")
        mime_type = "application/pdf"
    else:
        try:
            image = Image.open(BytesIO(content))
            valid = image.format.lower() == ("jpeg" if ext in {"jpg", "jpeg"} else ext) and image.width * image.height <= 50_000_000
            image.verify()
        except (UnidentifiedImageError, ValueError, OSError):
            valid = False
        mime_type = JOB_IMAGE_MIME[ext]
    if not valid:
        flash("Súbor nezodpovedá povolenému typu obrázka alebo PDF.", "danger")
        return redirect(url_for("jobs.job_detail", job_id=job.id))

    fields = {name: (request.form.get(name) or "").strip() for name in
              ("room_label", "element_label", "cable_type", "route_note")}
    if any(len(fields[name]) > limit for name, limit in
           (("room_label", 100), ("element_label", 100), ("cable_type", 100), ("route_note", 500))):
        flash("Popis fotografie je príliš dlhý.", "danger")
        return redirect(url_for("jobs.job_detail", job_id=job.id))

    root = Path(current_app.config.get("JOB_ATTACHMENT_FOLDER") or Path(current_app.instance_path) / "private_job_attachments")
    folder = root / str(current_user.id) / str(job.id)
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / unique_filename
    file_path.write_bytes(content)
    db_path = f"private/{current_user.id}/{job.id}/{unique_filename}"

    attachment = JobAttachment(
        job_id=job.id,
        user_id=current_user.id,
        filename=unique_filename,
        original_filename=original_filename,
        file_path=db_path,
        file_type=ext,
        mime_type=mime_type,
        **{key: value or None for key, value in fields.items()},
    )

    try:
        db.session.add(attachment)
        db.session.commit()
    except Exception:
        db.session.rollback()
        file_path.unlink(missing_ok=True)
        raise

    flash("Príloha bola nahraná.", "success")
    return redirect(url_for("jobs.job_detail", job_id=job.id))


def _attachment_path(attachment, job):
    """Resolve only server generated names in an owner checked job directory."""
    name = attachment.filename
    if not name or secure_filename(name) != name or "/" in name or "\\" in name:
        abort(404)
    private_name = f"private/{current_user.id}/{job.id}/{name}"
    if attachment.file_path == private_name:
        root = Path(current_app.config.get("JOB_ATTACHMENT_FOLDER") or Path(current_app.instance_path) / "private_job_attachments")
        return root / str(current_user.id) / str(job.id) / name
    legacy_name = f"uploads/jobs/{job.id}/{name}"
    if attachment.file_path == legacy_name:
        return Path(current_app.static_folder) / "uploads" / "jobs" / str(job.id) / name
    abort(404)


@jobs_bp.route("/jobs/<int:job_id>/attachments/<int:attachment_id>")
@login_required
def job_attachment(job_id, attachment_id):
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    attachment = JobAttachment.query.filter_by(
        id=attachment_id, job_id=job.id, user_id=current_user.id).first_or_404()
    path = _attachment_path(attachment, job)
    if not path.is_file():
        abort(404)
    mime_type = JOB_IMAGE_MIME.get(attachment.file_type)
    inline = mime_type is not None
    response = send_file(path, mimetype=mime_type or "application/pdf",
                         as_attachment=not inline,
                         download_name=attachment.original_filename)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "private, no-store"
    return response


@jobs_bp.route("/jobs/<int:job_id>/status", methods=["POST"])
@login_required
def job_update_status(job_id):
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()

    allowed_statuses = {
        "new",
        "inspection",
        "offer_sent",
        "approved",
        "in_progress",
        "done",
        "invoiced",
        "cancelled",
    }

    status = request.form.get("status")

    if status not in allowed_statuses:
        flash("Neplatný stav zákazky.", "danger")
        return redirect(url_for("jobs.job_detail", job_id=job.id))

    if status == "invoiced" and not Invoice.query.filter_by(job_id=job.id, user_id=current_user.id).first():
        flash("Stav fakturovaná nastaví vystavenie faktúry zo zákazky.", "danger")
        return redirect(url_for("jobs.job_detail", job_id=job.id))

    job.status = status
    db.session.commit()

    flash("Stav zákazky bol zmenený.", "success")
    return redirect(url_for("jobs.job_detail", job_id=job.id))


@jobs_bp.route("/jobs/<int:job_id>/attachments/<int:attachment_id>/delete", methods=["POST"])
@login_required
def job_delete_attachment(job_id, attachment_id):
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()

    attachment = JobAttachment.query.filter_by(
        id=attachment_id,
        job_id=job.id,
        user_id=current_user.id
    ).first_or_404()

    full_path = _attachment_path(attachment, job)

    try:
        full_path.unlink(missing_ok=True)
    except OSError:
        flash("Príloha je práve otvorená alebo súbor nemožno odstrániť. Skús to znovu.", "danger")
        return redirect(url_for("jobs.job_detail", job_id=job.id))

    db.session.delete(attachment)
    db.session.commit()

    flash("Príloha bola odstránená.", "success")
    return redirect(url_for("jobs.job_detail", job_id=job.id))


@jobs_bp.route("/jobs/<int:job_id>/notes/<int:note_id>/delete", methods=["POST"])
@login_required
def job_delete_note(job_id, note_id):
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()

    note = JobNote.query.filter_by(
        id=note_id,
        job_id=job.id,
        user_id=current_user.id
    ).first_or_404()

    db.session.delete(note)
    db.session.commit()

    flash("Poznámka bola odstránená.", "success")
    return redirect(url_for("jobs.job_detail", job_id=job.id))

@jobs_bp.route("/jobs/<int:job_id>/notes/<int:note_id>/edit", methods=["GET", "POST"])
@login_required
def job_edit_note(job_id, note_id):
    job = Job.query.filter_by(
        id=job_id,
        user_id=current_user.id
    ).first_or_404()

    note = JobNote.query.filter_by(
        id=note_id,
        job_id=job.id,
        user_id=current_user.id
    ).first_or_404()

    if request.method == "POST":
        content = request.form.get("content", "").strip()
        note_type = request.form.get("note_type", "text")

        allowed_types = {
            "text",
            "inspection",
            "material",
            "task",
            "ai",
        }

        if not content:
            flash("Poznámka nemôže byť prázdna.", "danger")
            return redirect(url_for(
                "jobs.job_edit_note",
                job_id=job.id,
                note_id=note.id
            ))

        if note_type not in allowed_types:
            flash("Neplatný typ poznámky.", "danger")
            return redirect(url_for(
                "jobs.job_edit_note",
                job_id=job.id,
                note_id=note.id
            ))

        note.content = content
        note.note_type = note_type

        db.session.commit()

        flash("Poznámka bola upravená.", "success")
        return redirect(url_for("jobs.job_detail", job_id=job.id))

    return render_template(
        "jobs/edit_note.html",
        job=job,
        note=note
    )

