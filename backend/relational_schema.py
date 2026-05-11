import os
from sqlalchemy import text
try:
    from backend.models import db
except ModuleNotFoundError:
    from models import db


def _load_sql_script(filename):
    base = os.path.abspath(os.path.dirname(__file__))
    path = os.path.join(base, 'sql', filename)
    with open(path, 'r', encoding='utf-8') as fh:
        return fh.read()


def init_relational_schema():
    """
    Apply relational schema for SQLite/MySQL safely.
    """
    engine = db.engine.url.get_backend_name()
    script = 'medipath_relational_schema_sqlite.sql' if engine == 'sqlite' else 'medipath_relational_schema.sql'

    statements = [s.strip() for s in _load_sql_script(script).split(';') if s.strip()]
    with db.engine.begin() as conn:
        if engine == 'sqlite':
            conn.execute(text('PRAGMA foreign_keys = ON'))
            _apply_sqlite_compat_migrations(conn)
        for stmt in statements:
            try:
                conn.execute(text(stmt))
            except Exception:
                # Keep migration idempotent on pre-existing legacy schemas.
                pass


def _apply_sqlite_compat_migrations(conn):
    # appointments/APPOINTMENTS naming collides in SQLite (case-insensitive)
    cols = {row[1] for row in conn.execute(text("PRAGMA table_info(appointments)")).fetchall()}
    if cols:
        if 'appointment_date' not in cols:
            conn.execute(text("ALTER TABLE appointments ADD COLUMN appointment_date TEXT"))
        if 'facility_id' not in cols:
            conn.execute(text("ALTER TABLE appointments ADD COLUMN facility_id INTEGER"))
        if 'notes' not in cols:
            conn.execute(text("ALTER TABLE appointments ADD COLUMN notes TEXT"))
        # Fresh relational schema has no date_time; legacy app schema requires NOT NULL date_time.
        # Add a nullable column on clinical-only DBs so ORM can always populate both fields.
        if 'date_time' not in cols:
            conn.execute(text("ALTER TABLE appointments ADD COLUMN date_time TEXT"))
        conn.execute(text("UPDATE appointments SET appointment_date = date_time WHERE appointment_date IS NULL AND date_time IS NOT NULL"))
