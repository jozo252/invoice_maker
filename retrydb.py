# migrate_statuses.py
from sqlalchemy import text
from app import create_app, db  # máš to v run.py, takže app factory existuje

app = create_app()

with app.app_context():
    # Premapuj staré statusy na nové hodnoty Enum
    db.session.execute(text("UPDATE invoices SET status = 'unpaid' WHERE status = 'pending'"))
    db.session.execute(text("UPDATE invoices SET status = 'unpaid' WHERE status = 'overdue'"))
    # voliteľne: normalizuj veľkosť písmen, ak by si mal 'Paid' apod.
    db.session.commit()
    print("Hotovo: statusy premapované na 'unpaid'.")
