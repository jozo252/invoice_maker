"""Small action board assembled from canonical case records."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from models import Invoice, InvoiceStatus, Job, JobMaterial, Lead, Offer, OfferRevision, WorkActivity


workboard = Blueprint("workboard", __name__)


@workboard.route("/today")
@login_required
def today():
    owner_id = current_user.id
    local_now = datetime.now(ZoneInfo("Europe/Bratislava")).replace(tzinfo=None)
    today_date = local_now.date()
    leads = (Lead.query.filter(Lead.user_id == owner_id,
                               Lead.status.notin_(["won", "lost", "closed"]))
             .order_by(Lead.next_action_due.asc(), Lead.created_at.desc()).limit(20).all())
    sent_offers = Offer.query.filter_by(user_id=owner_id, status="sent").all()
    cutoff = datetime.utcnow() - timedelta(days=7)
    stale = []
    for offer in sent_offers:
        latest = (OfferRevision.query.filter_by(user_id=owner_id, offer_id=offer.id)
                  .order_by(OfferRevision.version.desc()).first())
        if latest and latest.sent_at and latest.sent_at.replace(tzinfo=None) <= cutoff:
            stale.append((offer, latest))
    stale.sort(key=lambda pair: pair[1].sent_at)
    activities = (WorkActivity.query.filter(
        WorkActivity.user_id == owner_id, WorkActivity.status == "planned",
        WorkActivity.starts_at <= local_now + timedelta(days=7))
        .order_by(WorkActivity.starts_at.asc()).limit(20).all())
    materials = (JobMaterial.query.join(Job, JobMaterial.job_id == Job.id)
                 .filter(JobMaterial.user_id == owner_id, Job.user_id == owner_id,
                         JobMaterial.status == "needed")
                 .order_by(JobMaterial.created_at.asc()).limit(30).all())
    billable = (Job.query.filter(Job.user_id == owner_id, Job.status == "done",
                                 Job.offer_revision_id.isnot(None),
                                 ~Job.id.in_(Invoice.query.with_entities(Invoice.job_id)
                                             .filter(Invoice.user_id == owner_id,
                                                     Invoice.job_id.isnot(None))))
                .order_by(Job.updated_at.asc()).limit(20).all())
    overdue = (Invoice.query.filter_by(user_id=owner_id, status=InvoiceStatus.unpaid)
               .filter(Invoice.due_date < today_date)
               .order_by(Invoice.due_date.asc()).limit(20).all())
    return render_template("workboard.html", leads=leads, stale=stale,
                           activities=activities, materials=materials,
                           billable=billable, overdue=overdue)
