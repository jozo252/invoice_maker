from app import create_app
from extensions import db
from models import User  # uprav podľa tvojej štruktúry
from sqlalchemy import text

app = create_app()
with app.app_context():
    User.query.delete()
    db.session.execute(text("DROP TABLE IF EXISTS _alembic_tmp_clients;"))
    db.session.commit()

