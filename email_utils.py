from flask import current_app
from flask_mail import Message
from extensions import mail


def send_email_offer(to_email, subject, body, pdf_path=None, reply_to=None):
    msg = Message(
        subject=subject,
        recipients=[to_email],
        sender=current_app.config["MAIL_DEFAULT_SENDER"],
        reply_to=reply_to,
        body=body,
    )

    if pdf_path:
        with current_app.open_resource(pdf_path) as fp:
            msg.attach(
                filename=pdf_path.split("/")[-1],
                content_type="application/pdf",
                data=fp.read(),
            )

    mail.send(msg)


    


