from flask import Blueprint, app, flash, redirect, request, url_for
from flask import render_template
from flask_login import login_required, current_user
from models import Client, Company, Job, JobNote, JobAttachment
from extensions import db
import os
import uuid
from werkzeug.utils import secure_filename
from flask import current_app


jobs_bp = Blueprint("jobs", __name__, template_folder="templates/jobs")


ALLOWED_JOB_EXTENSIONS = {"jpg", "jpeg", "png", "pdf", "webp"}


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
    return render_template("jobs/detail.html", job=job)



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

        job = Job(
            user_id=current_user.id,
            title=title,
            description=description,
            client_id=int(client_id) if client_id else None,
            company_id=int(company_id) if company_id else None,
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

    original_filename = secure_filename(file.filename)
    ext = original_filename.rsplit(".", 1)[1].lower()
    unique_filename = f"{uuid.uuid4().hex}.{ext}"

    folder = os.path.join(current_app.root_path, "static", "uploads", "jobs", str(job.id))
    os.makedirs(folder, exist_ok=True)

    file_path = os.path.join(folder, unique_filename)
    file.save(file_path)

    db_path = f"uploads/jobs/{job.id}/{unique_filename}"

    attachment = JobAttachment(
        job_id=job.id,
        user_id=current_user.id,
        filename=unique_filename,
        original_filename=original_filename,
        file_path=db_path,
        file_type=ext,
        mime_type=file.mimetype
    )

    db.session.add(attachment)
    db.session.commit()

    flash("Príloha bola nahraná.", "success")
    return redirect(url_for("jobs.job_detail", job_id=job.id))


@jobs_bp.route("/jobs/<int:job_id>/status", methods=["POST"])
@login_required
def job_update_status(job_id):
    job = Job.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()

    allowed_statuses = {
        "new",
        "inspection",
        "offer_sent",
        "approved",
        "done",
        "invoiced",
        "cancelled",
    }

    status = request.form.get("status")

    if status not in allowed_statuses:
        flash("Neplatný stav zákazky.", "danger")
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

    full_path = os.path.join(current_app.root_path, "static", attachment.file_path)

    if os.path.exists(full_path):
        os.remove(full_path)

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

