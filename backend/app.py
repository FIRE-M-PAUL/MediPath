import os
import re
import sys
import socket
import threading
import time
import webbrowser
import shutil
import sqlite3
import secrets
from flask import Flask, request, jsonify, session, render_template, redirect, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_cors import CORS
from flask_wtf.csrf import CSRFProtect, generate_csrf
from functools import wraps
from sqlalchemy import event
from sqlalchemy.engine import Engine
try:
    from backend.models import (
        db,
        User,
        DoctorProfile,
        Appointment,
        Message,
        Admin,
        Patient,
        Doctor,
        Facility,
        ClinicalAppointment,
        MedicalRecord,
        SymptomLog,
        Notification,
        SystemLog,
    )
    from backend.db_config import build_database_uri, resolve_sqlite_path_from_uri
    from backend.relational_schema import init_relational_schema
except ModuleNotFoundError:
    from models import (
        db,
        User,
        DoctorProfile,
        Appointment,
        Message,
        Admin,
        Patient,
        Doctor,
        Facility,
        ClinicalAppointment,
        MedicalRecord,
        SymptomLog,
        Notification,
        SystemLog,
    )
    from db_config import build_database_uri, resolve_sqlite_path_from_uri
    from relational_schema import init_relational_schema
import json
from datetime import datetime, timedelta, timezone
from werkzeug.utils import secure_filename
from sqlalchemy import or_, and_
from sqlalchemy.exc import IntegrityError

# ── PyInstaller-safe path resolver ───────────────────────────
def resource_path(relative_path):
    """Get absolute path — works in dev and in PyInstaller bundle."""
    if hasattr(sys, '_MEIPASS'):
        base = sys._MEIPASS
    else:
        base = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base, relative_path)

# Writable directory beside the .exe (for SQLite DB & logs)
if hasattr(sys, '_MEIPASS'):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

os.makedirs(os.path.join(APP_DIR, 'backend', 'instance'), exist_ok=True)

app = Flask(__name__, static_folder=None)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", secrets.token_hex(32))
# DB stored in APP_DIR by default so it stays writable when running as .exe.
# If MySQL environment variables are provided, Flask will use MySQL instead.
app.config['SQLALCHEMY_DATABASE_URI'] = build_database_uri(APP_DIR)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=15)
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['WTF_CSRF_TIME_LIMIT'] = 7200
is_production = os.getenv('FLASK_ENV', '').lower() == 'production'
app.config['SESSION_COOKIE_SECURE'] = is_production

# File upload config
UPLOAD_FOLDER = os.path.join(APP_DIR, 'uploads', 'qualifications')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Initialize extensions
db.init_app(app)
login_manager = LoginManager(app)
csrf = CSRFProtect(app)
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": [
                "http://localhost:3000",
                "https://yourdomain.com",
                "http://127.0.0.1:5005",
                "http://localhost:5005",
            ]
        }
    },
    supports_credentials=True
)


@event.listens_for(Engine, "connect")
def enable_sqlite_fk(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# --- Static File Serving ---

@app.route('/')
def home():
    return send_from_directory(APP_DIR, 'index.html')

@app.route('/messages.html')
def messages_alias():
    return redirect('/user/messages.html')

@app.route('/api/csrf-token', methods=['GET'])
@csrf.exempt
def get_csrf_token():
    return jsonify({'success': True, 'csrf_token': generate_csrf()})

@app.route('/<path:path>')
def serve_static(path):
    full_path = os.path.join(APP_DIR, path)
    if os.path.exists(full_path):
        return send_from_directory(APP_DIR, path)
    doctor_pages = {
        'doctor-login.html', 'doctor-register.html', 'doctor-dashboard.html',
        'doctor-appointments.html', 'doctor-messages.html', 'doctor-profile.html',
        'doctor-pending.html'
    }
    user_pages = {
        'login.html', 'register.html', 'dashboard.html', 'appointments.html',
        'ai-assistant.html', 'doctors.html', 'messages.html', 'alerts.html', 'emergency.html', 'contact.html'
    }
    shared_root_files = {'index.html', 'styles.css', 'script.js'}
    clean_path = path.replace('\\', '/')
    basename = clean_path.split('/')[-1]

    if basename in doctor_pages:
        mapped = f'doctor/{basename}'
        if os.path.exists(os.path.join(APP_DIR, mapped)):
            return send_from_directory(APP_DIR, mapped)
    if basename in user_pages:
        mapped = f'user/{basename}'
        if os.path.exists(os.path.join(APP_DIR, mapped)):
            return send_from_directory(APP_DIR, mapped)
    if basename in shared_root_files and os.path.exists(os.path.join(APP_DIR, basename)):
        return send_from_directory(APP_DIR, basename)
    return jsonify({'success': False, 'message': 'Resource not found.'}), 404

# --- Robust Validation Layer ---
EMAIL_REGEX = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
PHONE_REGEX = r'^\d{10,15}$'
PASSWORD_REGEX = r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$'

def validate_email(email):
    return re.match(EMAIL_REGEX, email) is not None


def validate_phone(phone):
    return re.match(PHONE_REGEX, phone or '') is not None


def validate_password(password):
    return bool(password) and re.match(PASSWORD_REGEX, password) is not None


def validate_iso_datetime(value):
    if value is None or value == '':
        return False
    try:
        s = str(value).strip()
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        datetime.fromisoformat(s)
        return True
    except Exception:
        return False


def _parse_pagination(default_limit=25, max_limit=100):
    try:
        limit = int(request.args.get('limit', default_limit))
    except (TypeError, ValueError):
        limit = default_limit
    try:
        offset = int(request.args.get('offset', 0))
    except (TypeError, ValueError):
        offset = 0
    limit = max(1, min(limit, max_limit))
    offset = max(0, offset)
    return limit, offset


def _wants_paginated():
    return 'limit' in request.args or 'offset' in request.args


def _is_doctor_available_for_booking(availability_value):
    value = (availability_value or '').strip().lower()
    if not value:
        return True
    return value not in {'inactive', 'off duty', 'offline', 'on leave', 'unavailable'}


def _parse_appointment_request_datetime(data):
    """
    Parse booking time from JSON: full ISO in appointment_date (browser),
    or appointment_date (YYYY-MM-DD) plus appointment_time (e.g. '09:00 AM').
    Returns aware/naive datetime or None.
    """
    if not isinstance(data, dict):
        return None
    ad = data.get('appointment_date')
    if not ad:
        return None
    ad_s = str(ad).strip()
    at_raw = data.get('appointment_time')
    at_s = str(at_raw).strip() if at_raw else ''
    combined = None
    if at_s and 'T' not in ad_s and len(ad_s) <= 12:
        for fmt in ('%Y-%m-%d %I:%M %p', '%Y-%m-%d %H:%M', '%Y-%m-%d %H:%M:%S'):
            try:
                combined = datetime.strptime(f'{ad_s} {at_s}', fmt)
                break
            except ValueError:
                continue
    if combined is None:
        try:
            s = ad_s
            if s.endswith('Z'):
                s = s[:-1] + '+00:00'
            combined = datetime.fromisoformat(s)
        except Exception:
            return None
    return combined


def log_system_action(action, details='', user=None):
    entry = SystemLog(
        user_id=user.id if user else None,
        user_role=getattr(user, 'role', None) if user else None,
        action=action,
        details=details
    )
    db.session.add(entry)


def _is_api_request():
    return request.path.startswith('/api/')


@app.before_request
def enforce_session_timeout():
    if not current_user.is_authenticated:
        return None
    now = datetime.utcnow()
    last_seen_raw = session.get('last_seen_at')
    if last_seen_raw:
        try:
            last_seen = datetime.fromisoformat(last_seen_raw)
            if now - last_seen > app.config['PERMANENT_SESSION_LIFETIME']:
                user = current_user
                logout_user()
                session.clear()
                log_system_action('SESSION_TIMEOUT', 'Session expired after inactivity', user)
                db.session.commit()
                if _is_api_request():
                    return jsonify({'success': False, 'message': 'Your session has expired. Please log in again.'}), 401
                return redirect('/login.html')
        except Exception:
            pass
    session['last_seen_at'] = now.isoformat()
    session.permanent = True
    return None


def require_role(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if current_user.role not in roles:
                log_system_action(
                    'UNAUTHORIZED_ACCESS',
                    f'{current_user.email} tried to access {request.path} requiring {",".join(roles)}',
                    current_user
                )
                db.session.commit()
                if _is_api_request():
                    return jsonify({'success': False, 'message': 'Unauthorized. Please log in again.'}), 403
                return redirect('/login.html')
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def create_patient_notification(patient_id, message):
    if not patient_id:
        return
    note = Notification(patient_id=patient_id, message=message, status='Unread')
    db.session.add(note)


def _split_user_display_name(name):
    parts = (name or '').strip().split()
    first = parts[0] if parts else 'Patient'
    last = ' '.join(parts[1:]) if len(parts) > 1 else 'User'
    return first, last


def ensure_patient_row_from_user(user, raw_password=None):
    """
    Insert a PATIENT row for an app user with role patient (idempotent by email).
    raw_password: plaintext used for PATIENT.password (academic API); if None, uses a placeholder.
    """
    if not user or getattr(user, 'role', None) != 'patient':
        return None
    email = (user.email or '').strip()
    if not email:
        return None
    existing = Patient.query.filter_by(email=email).first()
    if existing:
        return existing
    first, last = _split_user_display_name(user.name)
    now_iso = datetime.utcnow().isoformat()
    patient = Patient(
        first_name=first,
        last_name=last,
        gender='Unknown',
        date_of_birth='',
        phone=(user.phone or '').strip(),
        email=email,
        address='',
        password='',
        date_created=now_iso,
    )
    pw = raw_password if raw_password else 'placeholder123'
    patient.set_secure_password(pw)
    db.session.add(patient)
    db.session.flush()
    return patient


def backfill_patient_rows_from_app_users():
    """Migrate existing users.role=patient rows missing from PATIENT (no plaintext password)."""
    for user in User.query.filter_by(role='patient').all():
        email = (user.email or '').strip()
        if not email:
            continue
        if Patient.query.filter_by(email=email).first():
            continue
        try:
            with db.session.begin_nested():
                ensure_patient_row_from_user(user, raw_password=None)
        except IntegrityError:
            pass


def get_or_create_clinical_patient(user):
    if not user:
        return None
    patient = Patient.query.filter_by(email=(user.email or '').strip()).first()
    if patient:
        return patient
    if getattr(user, 'role', None) == 'patient':
        return ensure_patient_row_from_user(user, raw_password='placeholder123')
    first, last = _split_user_display_name(user.name)
    patient = Patient(
        first_name=first,
        last_name=last,
        gender='Unknown',
        date_of_birth='',
        phone=user.phone or '',
        email=user.email,
        address='',
        password='',
        date_created=datetime.utcnow().isoformat(),
    )
    patient.set_secure_password('placeholder123')
    db.session.add(patient)
    db.session.flush()
    return patient


def ensure_clinical_doctors_seeded():
    if Doctor.query.first():
        return
    seeded = [
        ('John', 'Banda', 'Cardiologist', 'john.banda@medipath.local'),
        ('Mary', 'Phiri', 'Pediatrician', 'mary.phiri@medipath.local'),
        ('Peter', 'Mwansa', 'General Practitioner', 'peter.mwansa@medipath.local'),
        ('Grace', 'Tembo', 'Dermatologist', 'grace.tembo@medipath.local'),
        ('Kelvin', 'Zulu', 'Surgeon', 'kelvin.zulu@medipath.local'),
        ('Ruth', 'Mulenga', 'Dentist', 'ruth.mulenga@medipath.local')
    ]
    for first, last, specialty, email in seeded:
        d = Doctor(
            first_name=first,
            last_name=last,
            specialty=specialty,
            phone='',
            email=email,
            availability='Weekdays',
            password=''
        )
        d.set_secure_password('doctor123')
        db.session.add(d)


# Password for Flask-Login doctor portal (must satisfy register() password rules).
DEMO_DOCTOR_PORTAL_PASSWORD = 'DemoDoctor2026!'
DEMO_MODE = os.getenv('MEDIPATH_DEMO_MODE', 'true').lower() == 'true'


def ensure_demo_doctor_user_links():
    """
    For each clinical DOCTOR row, ensure an approved User(doctor) + DoctorProfile
    with clinical_doctor_id so doctor-login and /api/auth/me work for demos.
    """
    for d in Doctor.query.order_by(Doctor.doctor_id).all():
        email = (d.email or '').strip()
        if not email:
            continue
        display = f"Dr. {(d.first_name or '').strip()} {(d.last_name or '').strip()}".strip() or 'Dr. Demo'
        display = (display[:100] if len(display) > 100 else display)
        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(
                name=display,
                email=email,
                role='doctor',
                phone=(d.phone or '')[:20] if d.phone else '',
                status='approved',
            )
            user.set_password(DEMO_DOCTOR_PORTAL_PASSWORD)
            user.is_default_password = True
            db.session.add(user)
            db.session.flush()
            prof = DoctorProfile(
                user_id=user.id,
                specialty=d.specialty or 'General Doctor',
                hospital='MediPath Demo',
                clinical_doctor_id=d.doctor_id,
            )
            db.session.add(prof)
            continue
        if user.role != 'doctor':
            continue
        if user.status == 'pending_approval':
            user.status = 'approved'
        prof = user.doctor_profile
        if not prof:
            prof = DoctorProfile(
                user_id=user.id,
                specialty=d.specialty or 'General Doctor',
                hospital='MediPath Demo',
                clinical_doctor_id=d.doctor_id,
            )
            db.session.add(prof)
        elif prof.clinical_doctor_id is None:
            prof.clinical_doctor_id = d.doctor_id
            if not prof.specialty and d.specialty:
                prof.specialty = d.specialty


def ensure_clinical_doctor_from_user(user):
    """
    Ensure an approved portal doctor has a matching DOCTOR row and profile link.
    Returns DOCTOR row or None.
    """
    if not user or user.role != 'doctor':
        return None

    profile = user.doctor_profile
    if profile and profile.clinical_doctor_id:
        linked = Doctor.query.get(profile.clinical_doctor_id)
        if linked:
            return linked

    email = (user.email or '').strip()
    doctor_row = Doctor.query.filter_by(email=email).first() if email else None
    if not doctor_row:
        first, last = _split_user_display_name(user.name)
        specialty = (profile.specialty if profile and profile.specialty else 'General Doctor')
        doctor_row = Doctor(
            first_name=first or 'Doctor',
            last_name=last or 'Profile',
            specialty=specialty,
            phone=(user.phone or '')[:20] if user.phone else '',
            email=email,
            availability='Available Now',
            password=''
        )
        doctor_row.set_secure_password(secrets.token_urlsafe(16))
        db.session.add(doctor_row)
        db.session.flush()

    if not profile:
        profile = DoctorProfile(
            user_id=user.id,
            specialty=doctor_row.specialty or 'General Doctor',
            hospital='',
            clinical_doctor_id=doctor_row.doctor_id,
        )
        db.session.add(profile)
    else:
        profile.clinical_doctor_id = doctor_row.doctor_id
        if not profile.specialty and doctor_row.specialty:
            profile.specialty = doctor_row.specialty
    return doctor_row


def sync_approved_doctors_to_clinical_directory():
    """
    Backfill/sync every approved portal doctor into DOCTOR + clinical_doctor_id link.
    Safe to run repeatedly.
    """
    users = User.query.filter(
        User.role == 'doctor',
        User.status.in_(('approved', 'active'))
    ).all()
    synced = 0
    for user in users:
        row = ensure_clinical_doctor_from_user(user)
        if row:
            synced += 1
    return synced


def _is_demo_doctor_user(user):
    if not user:
        return False
    email = (user.email or '').strip().lower()
    if email.endswith('@medipath.local'):
        return True
    return bool(getattr(user, 'is_default_password', False))


_legacy_appt_fk_users_cache = None


def _legacy_appointments_fk_to_users():
    """
    True when the physical SQLite `appointments` table was created by the legacy
    Flask schema (patient_id / doctor_id reference users.id). In that case clinical
    booking must persist users.id, not PATIENT.patient_id / DOCTOR.doctor_id, or
    INSERT fails when PRAGMA foreign_keys=ON.
    """
    global _legacy_appt_fk_users_cache
    if _legacy_appt_fk_users_cache is not None:
        return _legacy_appt_fk_users_cache
    try:
        with db.engine.connect() as conn:
            row = conn.execute(
                db.text("SELECT sql FROM sqlite_master WHERE type='table' AND lower(name)='appointments'")
            ).fetchone()
            sql = (row[0] or '').lower() if row else ''
            # Relational-only schema references PATIENT / DOCTOR.
            if 'references patient' in sql or 'references doctor' in sql:
                _legacy_appt_fk_users_cache = False
            else:
                _legacy_appt_fk_users_cache = 'references users' in sql
    except Exception:
        _legacy_appt_fk_users_cache = False
    return _legacy_appt_fk_users_cache


def _portal_user_for_clinical_doctor(clinical_doctor_id):
    """Resolve DOCTOR.doctor_id to the linked approved User(doctor) for legacy FK rows."""
    doc = Doctor.query.get(int(clinical_doctor_id))
    if not doc:
        return None
    email = (doc.email or '').strip()
    if not email:
        return None
    return User.query.filter_by(email=email, role='doctor').first()


def _clinical_appointment_row_authorized(row):
    """ORM ClinicalAppointment instance."""
    if current_user.role == 'admin':
        return True
    if current_user.role == 'patient':
        patient = get_or_create_clinical_patient(current_user)
        if not patient:
            return False
        if _legacy_appointments_fk_to_users():
            return row.patient_id in (current_user.id, patient.patient_id)
        return row.patient_id == patient.patient_id
    if current_user.role == 'doctor':
        prof = getattr(current_user, 'doctor_profile', None)
        if not prof:
            return False
        # Support hybrid datasets where appointments.doctor_id may contain either
        # users.id (legacy) or DOCTOR.doctor_id (relational) values.
        allowed_ids = {int(current_user.id)}
        if prof.clinical_doctor_id:
            allowed_ids.add(int(prof.clinical_doctor_id))
        try:
            doctor_id_val = int(row.doctor_id)
        except (TypeError, ValueError):
            return False
        return doctor_id_val in allowed_ids
    return False


def _normalize_clinical_status(value):
    if not value:
        return value
    aliases = {
        'approved': 'Confirmed',
        'rejected': 'Cancelled',
        'confirmed': 'Confirmed',
        'cancelled': 'Cancelled',
        'completed': 'Completed',
        'pending': 'Pending',
    }
    return aliases.get(str(value).strip().lower(), value)


def _patient_display_name_for_clinical_list(patient_id):
    if patient_id is None:
        return 'Unknown patient'
    try:
        pid = int(patient_id)
    except (TypeError, ValueError):
        return 'Unknown patient'

    # Prefer portal patient user when available (works for legacy/hybrid rows).
    u = User.query.get(pid)
    if u and u.role == 'patient' and (u.name or '').strip():
        return u.name.strip()

    # Fallback to relational PATIENT row.
    p = Patient.query.get(pid)
    if p:
        name = f'{(p.first_name or "").strip()} {(p.last_name or "").strip()}'.strip()
        if name:
            return name
        # If PATIENT row has email, resolve portal display name from User.
        p_user = User.query.filter_by(email=(p.email or '').strip(), role='patient').first() if p.email else None
        if p_user and (p_user.name or '').strip():
            return p_user.name.strip()
    return 'Unknown patient'


def _portal_user_for_patient_identifier(patient_id):
    """Resolve appointment patient identifier to portal User(role=patient)."""
    if patient_id is None:
        return None
    try:
        pid = int(patient_id)
    except (TypeError, ValueError):
        return None

    # Always prefer direct portal user-id mapping first (legacy/hybrid-safe).
    u = User.query.get(pid)
    if u and u.role == 'patient':
        return u

    p = Patient.query.get(pid)
    if p:
        email = (p.email or '').strip()
        if email:
            u = User.query.filter_by(email=email, role='patient').first()
            if u:
                return u
    # Fallback for mixed legacy data.
    u = User.query.get(pid)
    return u if u and u.role == 'patient' else None


def _message_enabled_status(status_value):
    normalized = str(_normalize_clinical_status(status_value) or '').strip().lower()
    return normalized in ('confirmed', 'approved', 'completed')


def _doctor_patient_confirmed_appointment_exists(doctor_user_id, patient_user_id):
    """
    True when doctor/patient have an appointment in a confirmed-like state.
    Supports both legacy user-id FKs and relational patient/doctor-id FKs.
    """
    # Legacy user-to-user appointment rows.
    legacy_row = Appointment.query.filter_by(
        doctor_id=int(doctor_user_id),
        patient_id=int(patient_user_id),
    ).order_by(Appointment.id.desc()).first()
    if legacy_row and _message_enabled_status(legacy_row.status):
        return True

    # Clinical table also uses users.id in legacy mode.
    if _legacy_appointments_fk_to_users():
        row = ClinicalAppointment.query.filter_by(
            doctor_id=int(doctor_user_id),
            patient_id=int(patient_user_id),
        ).order_by(ClinicalAppointment.id.desc()).first()
        return bool(row and _message_enabled_status(row.status))

    # Relational mode maps to DOCTOR.doctor_id / PATIENT.patient_id
    doctor_user = User.query.get(int(doctor_user_id))
    patient_user = User.query.get(int(patient_user_id))
    if not doctor_user or not patient_user:
        return False
    profile = getattr(doctor_user, 'doctor_profile', None)
    clinical_doctor_id = profile.clinical_doctor_id if profile else None
    patient_row = Patient.query.filter_by(email=(patient_user.email or '').strip()).first() if patient_user.email else None
    if not clinical_doctor_id or not patient_row:
        return False
    row = ClinicalAppointment.query.filter_by(
        doctor_id=int(clinical_doctor_id),
        patient_id=int(patient_row.patient_id),
    ).order_by(ClinicalAppointment.id.desc()).first()
    return bool(row and _message_enabled_status(row.status))


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- API ENDPOINTS ---

@app.route('/api/auth/register', methods=['POST'])
def register():
    # Support both JSON and multipart form (for file uploads)
    if request.content_type and 'multipart/form-data' in request.content_type:
        data = request.form.to_dict()
        file = request.files.get('qualification')
    else:
        data = request.json or {}
        file = None

    name     = data.get('name')
    email    = data.get('email')
    password = data.get('password')
    role     = (data.get('role') or 'patient').strip().lower()
    phone    = data.get('phone')

    if role not in ('patient', 'doctor'):
        role = 'patient'

    if not all([name, email, password]):
        return jsonify({'success': False, 'message': 'Please fill all required fields.'}), 400

    if not validate_email(email):
        return jsonify({'success': False, 'message': 'Invalid email format (e.g., student@gmail.com).'}), 400

    if phone and not validate_phone(phone):
        return jsonify({'success': False, 'message': 'Invalid phone number.'}), 400

    if not validate_password(password):
        return jsonify({'success': False, 'message': 'Password must be at least 8 characters and include uppercase, lowercase, and a number.'}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({'success': False, 'message': 'This email is already registered.'}), 409

    try:
        new_user = User(name=name, email=email, role=role, phone=phone)
        new_user.set_password(password)

        if role == 'doctor':
            new_user.status = 'pending_approval'
            db.session.add(new_user)
            db.session.flush()  # get new_user.id before committing

            # Handle qualification file upload
            qual_path = None
            if file and allowed_file(file.filename):
                filename = secure_filename(f"doc_{new_user.id}_{file.filename}")
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                qual_path = filename

            profile = DoctorProfile(
                user_id         = new_user.id,
                specialty       = data.get('specialty'),
                hospital        = data.get('hospital'),
                license_number  = data.get('license'),
                experience      = data.get('experience'),
                qualification_path = qual_path
            )
            db.session.add(profile)
        else:
            db.session.add(new_user)
            db.session.flush()
            if role == 'patient':
                ensure_patient_row_from_user(new_user, raw_password=password)

        log_system_action('USER_REGISTER', f'{email} registered as {role}')
        db.session.commit()
        return jsonify({'success': True, 'message': 'Account created successfully.'})
    except IntegrityError:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'This email is already registered or conflicts with existing data.'}), 409
    except Exception:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Registration could not be completed. Please try again.'}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')

    user = User.query.filter_by(email=email).first()
    if user and user.lock_until and user.lock_until > datetime.utcnow():
        return jsonify({'success': False, 'message': 'Account temporarily locked due to multiple failed login attempts.'}), 423

    if user and user.check_password(password):
        if user.role == 'doctor' and user.status == 'rejected':
            return jsonify({'success': False, 'message': 'Application declined.'}), 403
        if user.is_default_password and not DEMO_MODE:
            return jsonify({
                'success': False,
                'message': 'Password reset required before login.',
                'force_password_change': True,
                'redirect': '/force-password-change',
            }), 403

        login_user(user)
        session.permanent = True
        session['last_seen_at'] = datetime.utcnow().isoformat()
        user.failed_login_attempts = 0
        user.lock_until = None
        log_system_action('USER_LOGIN', f'{user.email} logged in', user)
        db.session.commit()
        return jsonify({'success': True, 'user': user.to_dict()})

    if user:
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= 5:
            user.lock_until = datetime.utcnow() + timedelta(minutes=10)
            log_system_action('ACCOUNT_LOCKED', f'{user.email} locked for 10 minutes after failed login attempts')
        db.session.commit()
    return jsonify({'success': False, 'message': 'Invalid credentials.'}), 401


@app.route('/api/academic/login', methods=['POST'])
def academic_login():
    data = request.json or {}
    role = (data.get('role') or '').lower()
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if not username or not password:
        return jsonify({'success': False, 'message': 'username and password are required.'}), 400

    account = None
    if role == 'admin':
        account = Admin.query.filter_by(username=username).first()
    elif role == 'patient':
        account = Patient.query.filter_by(email=username).first()
    elif role == 'doctor':
        account = Doctor.query.filter_by(email=username).first()
    else:
        return jsonify({'success': False, 'message': 'Invalid role.'}), 400

    if account and account.verify_secure_password(password):
        log_system_action('ACADEMIC_LOGIN', f'{role}:{username}')
        db.session.commit()
        return jsonify({'success': True, 'message': 'Login successful.'})
    return jsonify({'success': False, 'message': 'Invalid credentials.'}), 401

@app.route('/api/auth/logout')
@login_required
def logout():
    log_system_action('USER_LOGOUT', 'User logged out', current_user)
    db.session.commit()
    logout_user()
    session.clear()
    return jsonify({'success': True})

@app.route('/api/auth/me', methods=['GET'])
@login_required
def get_me():
    return jsonify({'success': True, 'user': current_user.to_dict()})


@app.route('/api/auth/force-password-change', methods=['POST'])
@login_required
def force_password_change():
    data = request.json or {}
    new_password = data.get('new_password') or ''
    if not validate_password(new_password):
        return jsonify({'success': False, 'message': 'Password must be at least 8 characters and include uppercase, lowercase, and a number.'}), 400
    current_user.set_password(new_password)
    current_user.is_default_password = False
    log_system_action('PASSWORD_FORCE_CHANGE', 'Default password rotated', current_user)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Password updated successfully.'})


@app.route('/api/doctor/profile', methods=['GET', 'PUT'])
@login_required
@require_role('doctor')
def doctor_profile_api():
    profile = current_user.doctor_profile
    if not profile:
        profile = DoctorProfile(user_id=current_user.id)
        db.session.add(profile)
        db.session.flush()
    if not profile.clinical_doctor_id:
        linked = ensure_clinical_doctor_from_user(current_user)
        if linked:
            profile.clinical_doctor_id = linked.doctor_id

    if request.method == 'GET':
        availability_value = ''
        if profile.clinical_doctor_id:
            doctor_row = Doctor.query.get(profile.clinical_doctor_id)
            availability_value = (doctor_row.availability or '').strip() if doctor_row else ''
        is_active = _is_doctor_available_for_booking(availability_value)
        payload = current_user.to_dict()
        payload.update({
            'bio': profile.bio,
            'availability': availability_value,
            'is_active': is_active,
            'profile_image': profile.profile_image or '',
        })
        return jsonify({'success': True, 'doctor': payload})

    data = request.json or {}
    if data.get('name'):
        current_user.name = data['name'].strip()
    if data.get('phone'):
        if not validate_phone(data['phone']):
            return jsonify({'success': False, 'message': 'Invalid phone number.'}), 400
        current_user.phone = data['phone'].strip()
    if data.get('hospital'):
        profile.hospital = str(data['hospital']).strip()
    if data.get('experience'):
        profile.experience = str(data['experience']).strip()
    if data.get('bio') is not None:
        profile.bio = str(data['bio']).strip()
    if data.get('profile_image') is not None:
        image_value = str(data.get('profile_image') or '').strip()
        # Data URL expected (e.g. data:image/png;base64,...); cap payload size for DB safety.
        if image_value and len(image_value) > 2_000_000:
            return jsonify({'success': False, 'message': 'Profile image is too large. Please upload a smaller image.'}), 400
        if image_value and not image_value.startswith('data:image/'):
            return jsonify({'success': False, 'message': 'Invalid image format.'}), 400
        profile.profile_image = image_value
    if profile.clinical_doctor_id:
        doctor_row = Doctor.query.get(profile.clinical_doctor_id)
        if doctor_row:
            active_flag_provided = 'is_active' in data
            is_active = None
            if 'is_active' in data:
                raw_active = data.get('is_active')
                is_active = bool(raw_active) if isinstance(raw_active, bool) else str(raw_active).strip().lower() in ('1', 'true', 'yes', 'active')
                doctor_row.availability = 'Active' if is_active else 'Inactive'
            # Do not let free-text availability overwrite an explicit inactive toggle.
            if data.get('availability') is not None and (not active_flag_provided or is_active):
                doctor_row.availability = str(data['availability']).strip()
    log_system_action('DOCTOR_PROFILE_UPDATE', f'doctor_user_id={current_user.id}', current_user)
    db.session.commit()
    return jsonify({'success': True, 'doctor': current_user.to_dict()})


@app.route('/api/doctor/notifications', methods=['GET'])
@login_required
@require_role('doctor')
def doctor_notifications():
    """
    Notification feed for doctors based on newly booked pending appointments.
    """
    rows = ClinicalAppointment.query.order_by(ClinicalAppointment.id.desc()).limit(150).all()
    out = []
    for row in rows:
        if not _clinical_appointment_row_authorized(row):
            continue
        status = (row.status or '').strip().lower()
        if status not in ('pending', 'confirmed'):
            continue
        patient_name = _patient_display_name_for_clinical_list(row.patient_id)
        when = row.appointment_date or (row.date_time.isoformat() if row.date_time else '')
        out.append({
            'appointment_id': row.id,
            'type': 'new_booking' if status == 'pending' else 'booking_update',
            'message': f'{patient_name} booked an appointment.',
            'patient_name': patient_name,
            'status': row.status or 'Pending',
            'appointment_date': when,
        })
        if len(out) >= 12:
            break
    return jsonify({'success': True, 'items': out})


@app.route('/api/messages/conversations', methods=['GET'])
@login_required
def list_message_conversations():
    if current_user.role == 'doctor':
        rows = db.session.query(User).join(Message, User.id == Message.sender_id).filter(Message.receiver_id == current_user.id).all()
        outbound = db.session.query(User).join(Message, User.id == Message.receiver_id).filter(Message.sender_id == current_user.id).all()
        users = {u.id: u for u in rows + outbound if u.id != current_user.id and u.role == 'patient'}

        # Include patients who booked appointments with this doctor.
        clinical_rows = ClinicalAppointment.query.order_by(ClinicalAppointment.id.desc()).limit(300).all()
        for appt in clinical_rows:
            if not _clinical_appointment_row_authorized(appt):
                continue
            patient_user = _portal_user_for_patient_identifier(appt.patient_id)
            if patient_user:
                users[patient_user.id] = patient_user

        legacy_rows = Appointment.query.filter_by(doctor_id=current_user.id).order_by(Appointment.id.desc()).limit(300).all()
        for appt in legacy_rows:
            patient_user = User.query.get(appt.patient_id)
            if patient_user and patient_user.role == 'patient':
                users[patient_user.id] = patient_user

        payload = [{'id': u.id, 'name': u.name, 'email': u.email} for u in users.values()]
        return jsonify({'success': True, 'items': sorted(payload, key=lambda x: x['name'].lower())})
    if current_user.role == 'patient':
        rows = db.session.query(User).join(Message, User.id == Message.sender_id).filter(
            Message.receiver_id == current_user.id,
            User.role == 'doctor'
        ).all()
        outbound = db.session.query(User).join(Message, User.id == Message.receiver_id).filter(
            Message.sender_id == current_user.id,
            User.role == 'doctor'
        ).all()
        users = {u.id: u for u in rows + outbound if u.id != current_user.id}
        return jsonify({'success': True, 'items': [{'id': u.id, 'name': u.name, 'email': u.email} for u in users.values()]})
    return jsonify({'success': True, 'items': []})


@app.route('/api/messages/thread/<int:peer_id>', methods=['GET'])
@login_required
def get_message_thread(peer_id):
    peer = User.query.get(peer_id)
    if not peer:
        return jsonify({'success': False, 'message': 'User not found.'}), 404
    rows = Message.query.filter(
        or_(
            and_(Message.sender_id == current_user.id, Message.receiver_id == peer_id),
            and_(Message.sender_id == peer_id, Message.receiver_id == current_user.id),
        )
    ).order_by(Message.timestamp.asc()).all()
    out = [{
        'id': m.id,
        'sender_id': m.sender_id,
        'receiver_id': m.receiver_id,
        'content': m.content,
        'timestamp': m.timestamp.isoformat(),
        'is_read': m.is_read,
    } for m in rows]
    return jsonify({'success': True, 'items': out})


@app.route('/api/messages', methods=['POST'])
@login_required
def send_message():
    data = request.json or {}
    receiver_id = data.get('receiver_id')
    content = (data.get('content') or '').strip()
    if not receiver_id or not content:
        return jsonify({'success': False, 'message': 'receiver_id and content are required.'}), 400
    receiver = User.query.get(int(receiver_id))
    if not receiver:
        return jsonify({'success': False, 'message': 'Receiver not found.'}), 404

    if current_user.role == 'doctor' and receiver.role == 'patient':
        allowed = _doctor_patient_confirmed_appointment_exists(current_user.id, receiver.id)
        if not allowed:
            return jsonify({
                'success': False,
                'message': 'You can message this patient only after confirming their appointment.'
            }), 403

    if current_user.role == 'patient' and receiver.role == 'doctor':
        allowed = _doctor_patient_confirmed_appointment_exists(receiver.id, current_user.id)
        if not allowed:
            return jsonify({
                'success': False,
                'message': 'You can message this doctor only after appointment confirmation.'
            }), 403
        initiated = Message.query.filter_by(sender_id=receiver.id, receiver_id=current_user.id).first()
        if not initiated:
            return jsonify({
                'success': False,
                'message': 'Please wait for the doctor to start the conversation first.'
            }), 403

    row = Message(sender_id=current_user.id, receiver_id=receiver.id, content=content)
    db.session.add(row)
    db.session.commit()
    return jsonify({'success': True, 'message_id': row.id})


@app.route('/api/admin/reports/summary', methods=['GET'])
@login_required
@require_role('admin')
def admin_reports_summary():
    patients = User.query.filter_by(role='patient').count()
    doctors = User.query.filter_by(role='doctor').count()
    appts = Appointment.query.all()
    completed = sum(1 for a in appts if (a.status or '').lower() == 'completed')
    pending = sum(1 for a in appts if (a.status or '').lower() == 'pending')
    cancelled = sum(1 for a in appts if (a.status or '').lower() == 'cancelled')
    return jsonify({
        'success': True,
        'patients': patients,
        'doctors': doctors,
        'appointments': {
            'total': len(appts),
            'completed': completed,
            'pending': pending,
            'cancelled': cancelled,
        },
    })

# --- ADMIN & CLINICAL API ---

@app.route('/api/doctors', methods=['GET'])
def get_doctors():
    """
    Unified doctor listing for patient-facing pages.
    Includes both clinical DOCTOR records and approved app-user doctors.
    """
    rows = []
    seen_emails = set()

    # Clinical doctors visible only when linked to approved non-demo portal doctors.
    for d in Doctor.query.all():
        email = (d.email or '').strip().lower()
        linked_user = User.query.filter_by(email=(d.email or '').strip(), role='doctor').first() if d.email else None
        if not linked_user or linked_user.status not in ('approved', 'active') or _is_demo_doctor_user(linked_user):
            continue
        if not _is_doctor_available_for_booking(d.availability):
            continue
        if email:
            seen_emails.add(email)
        linked_profile = linked_user.doctor_profile if linked_user else None
        full_name = f"{(d.first_name or '').strip()} {(d.last_name or '').strip()}".strip() or 'Doctor'
        display_name = full_name if full_name.lower().startswith('dr.') else f"Dr. {full_name}"
        rows.append({
            'id': d.doctor_id,  # clinical doctor id (used by /api/clinical/appointments)
            'name': display_name,
            'email': d.email,
            'specialty': d.specialty or 'General Doctor',
            'hospital': (linked_profile.hospital if linked_profile and linked_profile.hospital else ''),
            'bio': (linked_profile.bio if linked_profile and linked_profile.bio else ''),
            'availability': d.availability or 'Available Now',
            'profile_image': (linked_profile.profile_image if linked_profile and linked_profile.profile_image else ''),
            'source': 'clinical'
        })

    # Approved app-user doctors not present in DOCTOR table
    approved_users = User.query.filter(
        User.role == 'doctor',
        User.status.in_(('approved', 'active'))
    ).all()
    for u in approved_users:
        if _is_demo_doctor_user(u):
            continue
        clinical_row = ensure_clinical_doctor_from_user(u)
        availability_text = (clinical_row.availability if clinical_row and clinical_row.availability else 'Available Now')
        if not _is_doctor_available_for_booking(availability_text):
            continue
        email = (u.email or '').strip().lower()
        if email and email in seen_emails:
            continue
        profile = u.doctor_profile
        name = (u.name or '').strip() or 'Doctor'
        display_name = name if name.lower().startswith('dr.') else f"Dr. {name}"
        rows.append({
            'id': clinical_row.doctor_id if clinical_row else u.id,
            'portal_user_id': u.id,
            'name': display_name,
            'email': u.email,
            'specialty': (profile.specialty if profile and profile.specialty else 'General Doctor'),
            'hospital': (profile.hospital if profile and profile.hospital else ''),
            'bio': (profile.bio if profile and profile.bio else ''),
            'availability': availability_text,
            'profile_image': (profile.profile_image if profile and profile.profile_image else ''),
            'booking_id': clinical_row.doctor_id if clinical_row else u.id,
            'source': 'app'
        })

    rows.sort(key=lambda x: (x.get('name') or '').lower())
    if _wants_paginated():
        limit, offset = _parse_pagination()
        total = len(rows)
        return jsonify({
            'success': True,
            'items': rows[offset:offset + limit],
            'total': total,
            'limit': limit,
            'offset': offset,
        })
    return jsonify(rows)

# --- APPOINTMENT ENDPOINTS ---

@app.route('/api/appointments/user', methods=['GET'])
@login_required
def get_user_appointments():
    """Return appointments for the currently logged-in patient."""
    appts = Appointment.query.filter_by(patient_id=current_user.id).all()
    results = []
    for a in appts:
        doctor = User.query.get(a.doctor_id)
        results.append({
            'id':         a.id,
            'doctorName': f'Dr. {doctor.name}' if doctor else 'Unknown Doctor',
            'doctorId':   a.doctor_id,
            'dateTime':   a.date_time.isoformat(),
            'status':     a.status,
            'reason':     a.reason
        })
    return jsonify(results)

@app.route('/api/appointments/doctor', methods=['GET'])
@login_required
def get_doctor_appointments():
    """Return appointments assigned to the currently logged-in doctor."""
    appts = Appointment.query.filter_by(doctor_id=current_user.id).all()
    results = []
    for a in appts:
        patient = User.query.get(a.patient_id)
        results.append({
            'id':          a.id,
            'patientName': patient.name if patient else 'Unknown Patient',
            'patientId':   a.patient_id,
            'dateTime':    a.date_time.isoformat(),
            'status':      a.status,
            'reason':      a.reason
        })
    return jsonify(results)

@app.route('/api/appointments', methods=['GET', 'POST'])
@login_required
def appointments_collection():
    if request.method == 'GET':
        if current_user.role == 'doctor':
            base = Appointment.query.filter_by(doctor_id=current_user.id).order_by(Appointment.date_time.desc())
        elif current_user.role == 'admin':
            base = Appointment.query.order_by(Appointment.date_time.desc())
        else:
            base = Appointment.query.filter_by(patient_id=current_user.id).order_by(Appointment.date_time.desc())
        total = base.count()
        limit, offset = _parse_pagination()
        appts = base.offset(offset).limit(limit).all()
        rows = []
        for a in appts:
            patient = User.query.get(a.patient_id)
            doctor = User.query.get(a.doctor_id)
            rows.append({
                'id': a.id,
                'patientId': a.patient_id,
                'patientName': patient.name if patient else 'Unknown Patient',
                'doctorId': a.doctor_id,
                'doctorName': f"Dr. {doctor.name}" if doctor else 'Unknown Doctor',
                'dateTime': a.date_time.isoformat(),
                'status': a.status,
                'reason': a.reason,
                'notes': a.reason or '',
            })
        return jsonify({'success': True, 'items': rows, 'total': total, 'limit': limit, 'offset': offset})

    return book_appointment()


def book_appointment():
    """Book a new appointment (patient only)."""
    data = request.json
    doctor_id = data.get('doctor_id')
    date_time_str = data.get('date_time')
    reason = data.get('reason', '')

    if not doctor_id or not date_time_str:
        return jsonify({'success': False, 'message': 'Doctor and date/time are required.'}), 400

    if not validate_iso_datetime(date_time_str):
        return jsonify({'success': False, 'message': 'Invalid date/time format.'}), 400
    date_time = datetime.fromisoformat(date_time_str)

    appt = Appointment(
        patient_id=current_user.id,
        doctor_id=int(doctor_id),
        date_time=date_time,
        reason=reason,
        status='Pending'
    )
    db.session.add(appt)

    # Mirror in required academic APPOINTMENTS table
    clinical_patient = get_or_create_clinical_patient(current_user)
    clinical_doctor = Doctor.query.filter(Doctor.doctor_id == int(doctor_id)).first()
    if not clinical_doctor:
        return jsonify({'success': False, 'message': 'Selected doctor does not exist.'}), 400
    facility = Facility.query.first()
    if _legacy_appointments_fk_to_users():
        portal_dr = _portal_user_for_clinical_doctor(clinical_doctor.doctor_id)
        if not portal_dr:
            return jsonify({'success': False, 'message': 'Selected doctor is not linked to a portal account.'}), 400
        persist_pid, persist_did = current_user.id, portal_dr.id
    else:
        persist_pid, persist_did = clinical_patient.patient_id, clinical_doctor.doctor_id
    clinical_appt = ClinicalAppointment(
        patient_id=persist_pid,
        doctor_id=persist_did,
        facility_id=facility.facility_id if facility else None,
        appointment_date=date_time.isoformat(),
        date_time=date_time,
        status='Pending',
        notes=reason
    )
    db.session.add(clinical_appt)
    create_patient_notification(clinical_patient.patient_id, 'Appointment booked successfully')
    log_system_action('APPOINTMENT_CREATE', f'Appointment with doctor_id={doctor_id}', current_user)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Appointment booked successfully.', 'id': appt.id})

@app.route('/api/appointments/<int:appt_id>/status', methods=['POST'])
@login_required
def update_appointment_status(appt_id):
    """Doctor or admin can update appointment status."""
    appt = Appointment.query.get(appt_id)
    if not appt:
        return jsonify({'success': False, 'message': 'Appointment not found.'}), 404
    if current_user.role not in ('doctor', 'admin'):
        return jsonify({'success': False, 'message': 'Unauthorized.'}), 403
    data = request.json
    appt.status = data.get('status', appt.status)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Status updated.'})

@app.route('/api/appointments/<int:appt_id>/cancel', methods=['POST'])
@login_required
def cancel_appointment(appt_id):
    """Patient or doctor can cancel an appointment."""
    appt = Appointment.query.get(appt_id)
    if not appt:
        return jsonify({'success': False, 'message': 'Appointment not found.'}), 404
    if current_user.id not in (appt.patient_id, appt.doctor_id) and current_user.role != 'admin':
        return jsonify({'success': False, 'message': 'Unauthorized.'}), 403
    data = request.json or {}
    appt.status = 'Cancelled'
    appt.cancellation_reason = data.get('reason', 'Cancelled by user.')
    appt.cancelled_by = current_user.role.capitalize()
    db.session.commit()
    return jsonify({'success': True, 'message': 'Appointment cancelled.'})

@app.route('/api/admin/users', methods=['GET'])
@login_required
@require_role('admin')
def get_all_users():
    users = User.query.filter(User.role != 'doctor').all()
    return jsonify([u.to_dict() for u in users])


@app.route('/api/patients', methods=['GET'])
@login_required
@require_role('admin')
def get_patients_paginated():
    base = User.query.filter_by(role='patient').order_by(User.created_at.desc())
    total = base.count()
    limit, offset = _parse_pagination()
    rows = [u.to_dict() for u in base.offset(offset).limit(limit).all()]
    return jsonify({'success': True, 'items': rows, 'total': total, 'limit': limit, 'offset': offset})


@app.route('/api/patients/<int:patient_user_id>', methods=['DELETE'])
@login_required
@require_role('admin')
def delete_patient(patient_user_id):
    user = User.query.get(patient_user_id)
    if not user or user.role != 'patient':
        return jsonify({'success': False, 'message': 'Patient not found.'}), 404
    if user.id == current_user.id:
        return jsonify({'success': False, 'message': 'You cannot delete your own admin session.'}), 400

    email = (user.email or '').strip()
    patient_row = Patient.query.filter_by(email=email).first() if email else None
    if patient_row:
        Notification.query.filter_by(patient_id=patient_row.patient_id).delete()
        SymptomLog.query.filter_by(patient_id=patient_row.patient_id).delete()
        MedicalRecord.query.filter_by(patient_id=patient_row.patient_id).delete()
        ClinicalAppointment.query.filter(
            or_(
                ClinicalAppointment.patient_id == patient_row.patient_id,
                ClinicalAppointment.patient_id == user.id,
            )
        ).delete(synchronize_session=False)
        db.session.delete(patient_row)

    Appointment.query.filter(or_(Appointment.patient_id == user.id, Appointment.doctor_id == user.id)).delete(synchronize_session=False)
    Message.query.filter(or_(Message.sender_id == user.id, Message.receiver_id == user.id)).delete(synchronize_session=False)
    db.session.delete(user)
    log_system_action('PATIENT_DELETE', f'user_id={patient_user_id}', current_user)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Patient deleted successfully.'})

@app.route('/api/admin/promote', methods=['POST'])
@login_required
@require_role('admin')
def promote_user():
    data = request.json
    user = User.query.get(data.get('user_id'))
    if user:
        user.role = 'admin'
        db.session.commit()
        return jsonify({'success': True, 'message': f'{user.name} promoted to Admin.'})
    return jsonify({'success': False, 'message': 'User not found.'}), 404

@app.route('/api/admin/pending-doctors', methods=['GET'])
@login_required
@require_role('admin')
def get_pending_doctors():
    pending = User.query.filter_by(role='doctor', status='pending_approval').all()
    return jsonify([p.to_dict() for p in pending])


@app.route('/api/admin/clinical-doctors', methods=['GET'])
@login_required
@require_role('admin')
def admin_clinical_doctors():
    """Seeded DOCTOR directory rows with linked portal accounts (demo)."""
    out = []
    for d in Doctor.query.order_by(Doctor.doctor_id).all():
        email = (d.email or '').strip()
        linked = User.query.filter_by(email=email, role='doctor').first() if email else None
        name = f"Dr. {(d.first_name or '').strip()} {(d.last_name or '').strip()}".strip()
        out.append({
            'clinical_doctor_id': d.doctor_id,
            'name': name or 'Doctor',
            'email': email,
            'specialty': d.specialty or '',
            'availability': d.availability or '',
            'linked_user_id': linked.id if linked else None,
            'portal_login_email': email if linked else None,
        })
    return jsonify(out)


@app.route('/api/admin/approved-doctors', methods=['GET'])
@login_required
@require_role('admin')
def admin_approved_doctor_users():
    """Approved portal doctors (User rows) for admin directory tab and modals."""
    rows = User.query.filter(
        User.role == 'doctor',
        User.status.in_(('approved', 'active'))
    ).order_by(User.id).all()
    return jsonify([u.to_dict() for u in rows])


@app.route('/api/admin/verify-doctor', methods=['POST'])
@login_required
@require_role('admin')
def verify_doctor():
    data = request.json
    doctor = User.query.get(data.get('doctor_id'))
    if doctor:
        approved = data.get('action') == 'approve'
        doctor.status = 'approved' if approved else 'rejected'
        if data.get('reason') and doctor.doctor_profile:
            doctor.doctor_profile.rejection_reason = data.get('reason')
        if approved:
            ensure_clinical_doctor_from_user(doctor)
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

@app.route('/api/admin/doctor-detail/<int:doctor_id>', methods=['GET'])
@login_required
@require_role('admin')
def get_doctor_detail(doctor_id):
    doctor = User.query.get(doctor_id)
    if not doctor or doctor.role != 'doctor':
        return jsonify({'success': False, 'message': 'Doctor not found.'}), 404
    return jsonify({'success': True, 'doctor': doctor.to_dict()})

@app.route('/uploads/qualifications/<path:filename>')
@login_required
@require_role('admin')
def serve_qualification(filename):
    """Serve uploaded qualification documents — admin only."""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/api/admin/update-doctor/<int:doctor_id>', methods=['POST'])
@login_required
@require_role('admin')
def update_doctor_profile(doctor_id):
    """Admin can manually fill in or update a doctor's profile details."""
    doctor = User.query.get(doctor_id)
    if not doctor or doctor.role != 'doctor':
        return jsonify({'success': False, 'message': 'Doctor not found.'}), 404

    # Support multipart (with file) or plain JSON
    if request.content_type and 'multipart/form-data' in request.content_type:
        data = request.form.to_dict()
        file = request.files.get('qualification')
    else:
        data = request.json or {}
        file = None

    # Update User-level fields
    if data.get('phone'):
        doctor.phone = data['phone']

    # Ensure profile exists
    if not doctor.doctor_profile:
        profile = DoctorProfile(user_id=doctor.id)
        db.session.add(profile)
        db.session.flush()
    profile = doctor.doctor_profile

    if data.get('license'):    profile.license_number = data['license']
    if data.get('experience'): profile.experience     = data['experience']
    if data.get('specialty'):  profile.specialty      = data['specialty']
    if data.get('hospital'):   profile.hospital       = data['hospital']

    # Handle new qualification file upload
    if file and allowed_file(file.filename):
        filename = secure_filename(f"doc_{doctor.id}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        profile.qualification_path = filename

    db.session.commit()
    return jsonify({'success': True, 'message': 'Profile updated successfully.', 'doctor': doctor.to_dict()})

@app.route('/api/admin/appointments', methods=['GET'])
@login_required
@require_role('admin')
def get_global_appointments():
    base = Appointment.query.order_by(Appointment.date_time.desc())
    total = base.count()
    limit, offset = _parse_pagination(default_limit=50, max_limit=200)
    appts = base.offset(offset).limit(limit).all()
    # Join with User to get names for the dashboard
    results = []
    for a in appts:
        patient = User.query.get(a.patient_id)
        doctor = User.query.get(a.doctor_id)
        results.append({
            'id': a.id,
            'patientName': patient.name if patient else 'Deleted User',
            'doctorName': f'Dr. {doctor.name}' if doctor else 'Deleted Doctor',
            'dateTime': a.date_time.isoformat(),
            'status': a.status
        })
    if _wants_paginated():
        return jsonify({'success': True, 'items': results, 'total': total, 'limit': limit, 'offset': offset})
    return jsonify(results)


@app.route('/api/admin/appointments/<int:appointment_id>/cancel', methods=['POST'])
@login_required
@require_role('admin')
def admin_cancel_appointment(appointment_id):
    data = request.json or {}
    reason = (data.get('reason') or '').strip() or 'Administrative override.'
    appt = Appointment.query.get(appointment_id)
    if not appt:
        return jsonify({'success': False, 'message': 'Appointment not found.'}), 404
    appt.status = 'Cancelled'
    appt.cancellation_reason = reason
    appt.cancelled_by = 'Admin'
    clinical_rows = ClinicalAppointment.query.filter(
        or_(
            ClinicalAppointment.id == appointment_id,
            ClinicalAppointment.patient_id == appt.patient_id,
        )
    ).all()
    for row in clinical_rows:
        row.status = 'Cancelled'
        row.notes = reason
    patient = get_or_create_clinical_patient(appt.patient)
    if patient:
        create_patient_notification(patient.patient_id, f'Appointment cancelled by admin: {reason}')
    log_system_action('ADMIN_APPOINTMENT_CANCEL', f'appointment_id={appointment_id}; reason={reason}', current_user)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Appointment cancelled.'})


def _sqlite_db_path():
    """Resolve the active SQLite file path from SQLAlchemy URI."""
    uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    return resolve_sqlite_path_from_uri(uri, APP_DIR)


@app.route('/api/clinical/appointments', methods=['GET'])
@login_required
def list_clinical_appointments():
    """
    Return appointments safely from SQLite with defensive schema checks.
    """
    conn = None
    try:
        print('[clinical/appointments] request received')
        db_path = _sqlite_db_path()
        if not db_path or not os.path.exists(db_path):
            raise RuntimeError('SQLite database file not found or invalid path.')

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Step 1: Ensure appointments table exists (case-insensitive lookup).
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        table_names = [r['name'] for r in cursor.fetchall()]
        appt_table = next((t for t in table_names if t.lower() == 'appointments'), None)
        if not appt_table:
            raise RuntimeError('appointments table does not exist.')

        # Step 2: Inspect columns and build a safe query from what actually exists.
        cursor.execute(f'PRAGMA table_info("{appt_table}")')
        cols = [r['name'] for r in cursor.fetchall()]
        if not cols:
            raise RuntimeError('appointments table schema is unreadable.')

        id_col = 'appointment_id' if 'appointment_id' in cols else ('id' if 'id' in cols else None)
        patient_col = 'patient_id' if 'patient_id' in cols else None
        doctor_col = 'doctor_id' if 'doctor_id' in cols else None
        status_col = 'status' if 'status' in cols else None
        notes_col = 'notes' if 'notes' in cols else ('reason' if 'reason' in cols else None)
        facility_col = 'facility_id' if 'facility_id' in cols else None
        if not all([id_col, patient_col, doctor_col]):
            raise RuntimeError('appointments schema missing required id/patient_id/doctor_id columns.')

        # date column can be either appointment_date (clinical) or date_time (legacy)
        if 'appointment_date' in cols and 'date_time' in cols:
            date_expr = "COALESCE(NULLIF(TRIM(appointment_date), ''), date_time)"
        elif 'appointment_date' in cols:
            date_expr = "appointment_date"
        elif 'date_time' in cols:
            date_expr = "date_time"
        else:
            raise RuntimeError('appointments schema missing date column.')

        select_sql = f"""
            SELECT
                {id_col} AS appointment_id,
                {patient_col} AS patient_id,
                {doctor_col} AS doctor_id,
                {date_expr} AS appointment_date,
                {status_col if status_col else "'Pending'"} AS status,
                {notes_col if notes_col else "''"} AS notes,
                {facility_col if facility_col else "NULL"} AS facility_id
            FROM "{appt_table}"
        """

        params = []
        if current_user.role == 'patient':
            patient = get_or_create_clinical_patient(current_user)
            if not patient:
                return jsonify([])
            # Accept legacy rows keyed by users.id and clinical rows keyed by PATIENT.patient_id.
            select_sql += f" WHERE {patient_col} IN (?, ?)"
            params = [patient.patient_id, current_user.id]
            select_sql += " ORDER BY appointment_date ASC"
        elif current_user.role == 'doctor':
            profile = getattr(current_user, 'doctor_profile', None)
            cid = profile.clinical_doctor_id if profile else None
            if not current_user.id and not cid:
                return jsonify([])
            # Support hybrid datasets by accepting both portal and clinical doctor ids.
            if cid and int(cid) != int(current_user.id):
                select_sql += f" WHERE {doctor_col} IN (?, ?)"
                params = [current_user.id, cid]
            else:
                select_sql += f" WHERE {doctor_col} = ?"
                params = [current_user.id]
            select_sql += " ORDER BY appointment_date DESC"
        elif current_user.role == 'admin':
            select_sql += " ORDER BY appointment_date DESC"
        else:
            return jsonify([])

        print(f"[clinical/appointments] executing query on table={appt_table}")
        cursor.execute(select_sql, params)
        rows = cursor.fetchall()

        out = []
        for r in rows:
            ad = r['appointment_date']
            if ad is not None:
                ad = str(ad)
            out.append({
                'appointment_id': r['appointment_id'],
                'patient_id': r['patient_id'],
                'doctor_id': r['doctor_id'],
                'facility_id': r['facility_id'],
                'appointment_date': ad,
                'status': r['status'],
                'notes': r['notes'] or ''
            })
        if current_user.role in ('doctor', 'admin'):
            for item in out:
                item['patient_name'] = _patient_display_name_for_clinical_list(item.get('patient_id'))
        print(f"[clinical/appointments] response rows={len(out)}")
        return jsonify(out)
    except Exception as exc:
        print(f'[clinical/appointments] error: {exc}')
        return jsonify({
            'status': 'error',
            'message': 'Unable to load appointments'
        }), 500
    finally:
        if conn is not None:
            conn.close()


@app.route('/api/clinical/appointments', methods=['POST'])
@login_required
def create_clinical_appointment():
    """
    Book a clinical appointment. Accepts the live frontend payload (doctor_id,
    ISO appointment_date, notes) or explicit patient_id / appointment_time / reason.
    """
    try:
        data = request.get_json(silent=True)
        print('[clinical/appointments POST] Incoming appointment data:', data)
        if data is None:
            return jsonify({'success': False, 'message': 'No data received'}), 400
        if not isinstance(data, dict):
            return jsonify({'success': False, 'message': 'Invalid JSON body'}), 400

        appointment_date_raw = data.get('appointment_date')
        if appointment_date_raw is None or (
            isinstance(appointment_date_raw, str) and not str(appointment_date_raw).strip()
        ):
            return jsonify({'success': False, 'message': 'appointment_date is required.'}), 400

        doctor_id = data.get('doctor_id')
        reason = (data.get('reason') if data.get('reason') is not None else data.get('notes', ''))
        if reason is None:
            reason = ''
        reason = str(reason).strip()

        required_fields = (
            'patient_id',
            'doctor_id',
            'appointment_date',
            'appointment_time',
            'reason',
        )
        missing = [f for f in required_fields if f not in data]
        if 'patient_id' in missing:
            missing = [f for f in missing if f != 'patient_id']
        if 'reason' in missing and 'notes' in data:
            missing = [f for f in missing if f != 'reason']
        if 'appointment_time' in missing:
            ad_chk = data.get('appointment_date')
            if ad_chk and 'T' in str(ad_chk):
                missing = [f for f in missing if f != 'appointment_time']

        if missing:
            return jsonify({
                'success': False,
                'message': f"Missing field: {missing[0]}",
            }), 400

        if not doctor_id:
            return jsonify({'success': False, 'message': 'Missing field: doctor_id'}), 400

        starts_at = _parse_appointment_request_datetime(data)
        if starts_at is None:
            return jsonify({'success': False, 'message': 'Invalid appointment_date / appointment_time.'}), 400

        if not validate_iso_datetime(starts_at.isoformat()):
            return jsonify({'success': False, 'message': 'Invalid appointment date.'}), 400

        try:
            doctor = Doctor.query.get(int(doctor_id))
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'doctor_id must be an integer.'}), 400
        if not doctor:
            return jsonify({'success': False, 'message': 'Doctor must exist.'}), 400
        if not _is_doctor_available_for_booking(doctor.availability):
            return jsonify({'success': False, 'message': 'This doctor is currently inactive and cannot receive bookings.'}), 400

        patient = get_or_create_clinical_patient(current_user)
        if not patient:
            return jsonify({'success': False, 'message': 'Unable to resolve patient profile.'}), 400

        if data.get('patient_id') is not None:
            try:
                requested_pid = int(data['patient_id'])
            except (TypeError, ValueError):
                return jsonify({'success': False, 'message': 'patient_id must be an integer.'}), 400
            if requested_pid != patient.patient_id and getattr(current_user, 'role', None) != 'admin':
                return jsonify({'success': False, 'message': 'patient_id does not match the logged-in patient.'}), 403

        facility_id = data.get('facility_id')
        if facility_id and not Facility.query.get(int(facility_id)):
            return jsonify({'success': False, 'message': 'Facility must exist.'}), 400

        # Persist JSON appointment_date as both TEXT (clinical) and DateTime (legacy NOT NULL column).
        appointment_date_storage = starts_at.isoformat()
        date_time_value = starts_at
        if date_time_value.tzinfo is not None:
            date_time_value = date_time_value.replace(tzinfo=None)

        if _legacy_appointments_fk_to_users():
            portal_dr = _portal_user_for_clinical_doctor(doctor.doctor_id)
            if not portal_dr:
                return jsonify({
                    'success': False,
                    'message': 'This doctor is not linked to a portal account. Restart the server after init_db or contact admin.',
                }), 400
            persist_patient_id = current_user.id
            persist_doctor_id = portal_dr.id
        else:
            persist_patient_id = patient.patient_id
            persist_doctor_id = doctor.doctor_id

        row = ClinicalAppointment(
            patient_id=persist_patient_id,
            doctor_id=persist_doctor_id,
            facility_id=int(facility_id) if facility_id else None,
            appointment_date=appointment_date_storage,
            date_time=date_time_value,
            status='Pending',
            notes=reason,
        )
        db.session.add(row)
        create_patient_notification(patient.patient_id, 'Your appointment has been booked')
        log_system_action('APPOINTMENT_CREATE', 'clinical_appointment_id=pending', current_user)
        db.session.commit()
        print(f'[clinical/appointments POST] booked id={row.appointment_id} patient={patient.patient_id} doctor={doctor.doctor_id}')
        return jsonify({
            'success': True,
            'message': 'Appointment booked successfully',
            'appointment_id': row.appointment_id,
        }), 201
    except IntegrityError as exc:
        db.session.rollback()
        print('[clinical/appointments POST] IntegrityError:', exc)
        return jsonify({
            'success': False,
            'message': 'Could not book appointment (database constraint). Please verify selections and try again.',
        }), 409
    except Exception as exc:
        db.session.rollback()
        print('[clinical/appointments POST] Appointment Error:', str(exc))
        return jsonify({'success': False, 'message': str(exc)}), 500


@app.route('/api/clinical/appointments/<int:appointment_id>', methods=['PUT'])
@login_required
def update_clinical_appointment(appointment_id):
    row = ClinicalAppointment.query.get(appointment_id)
    if not row:
        return jsonify({'success': False, 'message': 'Appointment not found.'}), 404
    if not _clinical_appointment_row_authorized(row):
        return jsonify({'success': False, 'message': 'Unauthorized.'}), 403
    data = request.json or {}
    if data.get('doctor_id'):
        doctor = Doctor.query.get(int(data['doctor_id']))
        if not doctor:
            return jsonify({'success': False, 'message': 'Doctor must exist.'}), 400
        if _legacy_appointments_fk_to_users():
            portal_dr = _portal_user_for_clinical_doctor(doctor.doctor_id)
            if not portal_dr:
                return jsonify({'success': False, 'message': 'Doctor must have a linked portal account.'}), 400
            row.doctor_id = portal_dr.id
        else:
            row.doctor_id = doctor.doctor_id
    if data.get('facility_id') is not None:
        if data['facility_id'] and not Facility.query.get(int(data['facility_id'])):
            return jsonify({'success': False, 'message': 'Facility must exist.'}), 400
        row.facility_id = int(data['facility_id']) if data['facility_id'] else None
    if data.get('appointment_date'):
        raw = data['appointment_date']
        if not validate_iso_datetime(str(raw)):
            return jsonify({'success': False, 'message': 'Invalid appointment date.'}), 400
        try:
            s = str(raw).strip()
            if s.endswith('Z'):
                s = s[:-1] + '+00:00'
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is not None:
                dt = dt.replace(tzinfo=None)
            row.appointment_date = s
            row.date_time = dt
        except Exception:
            return jsonify({'success': False, 'message': 'Invalid appointment_date.'}), 400
    if data.get('status'):
        row.status = _normalize_clinical_status(data['status'])
        create_patient_notification(row.patient_id, f'Your appointment has been {row.status.lower()}')
    if data.get('notes') is not None:
        row.notes = data['notes']
    log_system_action('APPOINTMENT_UPDATE', f'clinical_appointment_id={appointment_id}', current_user)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/clinical/appointments/<int:appointment_id>', methods=['DELETE'])
@login_required
def delete_clinical_appointment(appointment_id):
    row = ClinicalAppointment.query.get(appointment_id)
    if not row:
        return jsonify({'success': False, 'message': 'Appointment not found.'}), 404
    if not _clinical_appointment_row_authorized(row):
        return jsonify({'success': False, 'message': 'Unauthorized.'}), 403
    db.session.delete(row)
    log_system_action('APPOINTMENT_DELETE', f'clinical_appointment_id={appointment_id}', current_user)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/medical-records', methods=['GET'])
@login_required
def list_medical_records():
    if current_user.role == 'patient':
        patient = get_or_create_clinical_patient(current_user)
        rows = MedicalRecord.query.filter_by(patient_id=patient.patient_id).all()
    else:
        rows = MedicalRecord.query.all()
    return jsonify([{
        'record_id': r.record_id,
        'patient_id': r.patient_id,
        'doctor_id': r.doctor_id,
        'diagnosis': r.diagnosis,
        'prescription': r.prescription,
        'treatment': r.treatment,
        'visit_date': r.visit_date
    } for r in rows])


@app.route('/api/medical-records', methods=['POST'])
@login_required
def create_medical_record():
    if current_user.role not in ('doctor', 'admin'):
        return jsonify({'success': False, 'message': 'Unauthorized.'}), 403
    data = request.json or {}
    if not validate_iso_datetime(data.get('visit_date', '')):
        return jsonify({'success': False, 'message': 'Invalid visit date.'}), 400
    patient = Patient.query.get(int(data.get('patient_id', 0)))
    doctor = Doctor.query.get(int(data.get('doctor_id', 0)))
    if not patient or not doctor:
        return jsonify({'success': False, 'message': 'Patient and doctor must exist.'}), 400
    row = MedicalRecord(
        patient_id=patient.patient_id,
        doctor_id=doctor.doctor_id,
        diagnosis=data.get('diagnosis', ''),
        prescription=data.get('prescription', ''),
        treatment=data.get('treatment', ''),
        visit_date=data['visit_date']
    )
    db.session.add(row)
    create_patient_notification(patient.patient_id, 'A new medical record has been added')
    log_system_action('MEDICAL_RECORD_CREATE', f'patient_id={patient.patient_id}', current_user)
    db.session.commit()
    return jsonify({'success': True, 'record_id': row.record_id})


@app.route('/api/medical-records/<int:record_id>', methods=['PUT'])
@login_required
def update_medical_record(record_id):
    if current_user.role not in ('doctor', 'admin'):
        return jsonify({'success': False, 'message': 'Unauthorized.'}), 403
    row = MedicalRecord.query.get(record_id)
    if not row:
        return jsonify({'success': False, 'message': 'Record not found.'}), 404
    data = request.json or {}
    for key in ('diagnosis', 'prescription', 'treatment'):
        if key in data:
            setattr(row, key, data[key])
    if data.get('visit_date'):
        if not validate_iso_datetime(data['visit_date']):
            return jsonify({'success': False, 'message': 'Invalid visit date.'}), 400
        row.visit_date = data['visit_date']
    log_system_action('MEDICAL_RECORD_UPDATE', f'record_id={record_id}', current_user)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Record updated successfully'})


@app.route('/api/medical-records/<int:record_id>', methods=['DELETE'])
@login_required
def delete_medical_record(record_id):
    if current_user.role not in ('doctor', 'admin'):
        return jsonify({'success': False, 'message': 'Unauthorized.'}), 403
    row = MedicalRecord.query.get(record_id)
    if not row:
        return jsonify({'success': False, 'message': 'Record not found.'}), 404
    db.session.delete(row)
    log_system_action('MEDICAL_RECORD_DELETE', f'record_id={record_id}', current_user)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/notifications', methods=['GET'])
@login_required
def get_notifications():
    patient = get_or_create_clinical_patient(current_user)
    rows = Notification.query.filter_by(patient_id=patient.patient_id).order_by(Notification.notification_id.desc()).all()
    return jsonify([{
        'notification_id': n.notification_id,
        'message': n.message,
        'status': n.status,
        'date_created': n.date_created
    } for n in rows])


@app.route('/api/notifications/<int:notification_id>/read', methods=['POST'])
@login_required
def mark_notification_read(notification_id):
    row = Notification.query.get(notification_id)
    if not row:
        return jsonify({'success': False, 'message': 'Notification not found.'}), 404
    patient = get_or_create_clinical_patient(current_user)
    if not patient or row.patient_id != patient.patient_id:
        return jsonify({'success': False, 'error': 'Unauthorized access'}), 403
    row.status = 'Read'
    db.session.commit()
    return jsonify({'success': True})


def _parse_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text_val = str(value).strip()
    if not text_val:
        return None
    if text_val.endswith('Z'):
        text_val = text_val[:-1] + '+00:00'
    # Handle common SQLite datetime formats safely.
    for candidate in (text_val, text_val.replace(' ', 'T')):
        try:
            return datetime.fromisoformat(candidate)
        except Exception:
            continue
    return None


def _naive_utc_for_compare(dt):
    """Compare safely with datetime.utcnow() (naive UTC)."""
    if dt is None:
        return None
    if not isinstance(dt, datetime):
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


@app.route('/api/activity/recent', methods=['GET'])
@login_required
def recent_activity():
    """
    Real-time user activity feed for the last 7 days.
    Sources: appointments, notifications, symptom logs, account creation.
    """
    if current_user.role != 'patient':
        return jsonify([])

    cutoff = datetime.utcnow() - timedelta(days=7)
    activities = []
    patient = get_or_create_clinical_patient(current_user)

    # Legacy user appointments (patient_id references users.id)
    legacy_rows = Appointment.query.filter_by(patient_id=current_user.id).all()
    for row in legacy_rows:
        when = _naive_utc_for_compare(_parse_datetime(row.date_time))
        if not when or when < cutoff:
            continue
        status = (row.status or 'Pending').capitalize()
        activities.append({
            'type': 'appointment',
            'icon': '✅' if status in ('Approved', 'Completed') else '📅',
            'dot': 'dot-green' if status in ('Approved', 'Completed') else 'dot-blue',
            'text': f'Appointment {status.lower()}',
            'timestamp': when.isoformat()
        })

    # Clinical appointments and symptom logs / notifications map to PATIENT.patient_id
    if patient:
        clinical_rows = ClinicalAppointment.query.filter(
            or_(
                ClinicalAppointment.patient_id == patient.patient_id,
                ClinicalAppointment.patient_id == current_user.id,
            )
        ).all()
        for row in clinical_rows:
            when = _naive_utc_for_compare(_parse_datetime(row.appointment_date))
            if not when or when < cutoff:
                continue
            status = (row.status or 'Pending').capitalize()
            activities.append({
                'type': 'clinical_appointment',
                'icon': '👨‍⚕️',
                'dot': 'dot-blue',
                'text': f'Clinical appointment {status.lower()}',
                'timestamp': when.isoformat()
            })

        notes = Notification.query.filter_by(patient_id=patient.patient_id).all()
        for n in notes:
            when = _naive_utc_for_compare(_parse_datetime(n.date_created))
            if not when or when < cutoff:
                continue
            activities.append({
                'type': 'notification',
                'icon': '🔔',
                'dot': 'dot-yellow',
                'text': n.message or 'Notification received',
                'timestamp': when.isoformat()
            })

        symptom_logs = SymptomLog.query.filter_by(patient_id=patient.patient_id).all()
        for s in symptom_logs:
            when = _naive_utc_for_compare(_parse_datetime(s.date_created))
            if not when or when < cutoff:
                continue
            activities.append({
                'type': 'symptom',
                'icon': '🔍',
                'dot': 'dot-blue',
                'text': 'Symptom check completed — AI guidance generated',
                'timestamp': when.isoformat()
            })

    # Account creation activity
    created = _naive_utc_for_compare(_parse_datetime(current_user.created_at))
    if created and created >= cutoff:
        activities.append({
            'type': 'account',
            'icon': '✅',
            'dot': 'dot-green',
            'text': 'Account registered successfully',
            'timestamp': created.isoformat()
        })

    activities.sort(key=lambda x: x['timestamp'], reverse=True)
    return jsonify(activities[:12])


@app.route('/api/symptom-analyze', methods=['POST'])
@login_required
def symptom_analyze():
    data = request.json or {}
    raw_input = ((data.get('symptoms') or data.get('question') or data.get('text') or '')).strip().lower()
    if not raw_input:
        return jsonify({'success': False, 'message': 'Symptoms are required.'}), 400

    kb_path = os.path.join(APP_DIR, 'backend', 'knowledge_base.json')
    with open(kb_path, 'r', encoding='utf-8') as kb_file:
        kb_data = json.load(kb_file)

    normalized_text = ' '.join(raw_input.replace(',', ' ').replace('.', ' ').split())
    symptom_aliases = {
        'stomach hurts': 'stomach pain',
        'my stomach hurts': 'stomach pain',
        'tummy ache': 'stomach pain',
        'throat hurts': 'sore throat',
        'heart is racing': 'heart beating fast',
        'heart racing': 'heart beating fast',
        'passes out': 'loss of consciousness',
    }
    for src, dst in symptom_aliases.items():
        normalized_text = normalized_text.replace(src, dst)

    emergency_rules = {
        'chest pain': 'Go to hospital immediately.',
        'heavy bleeding': 'Seek urgent care immediately.',
        'loss of consciousness': 'Call emergency services immediately.',
        'difficulty breathing': 'Go to emergency room immediately.',
        'severe injury': 'Seek immediate emergency medical care.',
        'seizure': 'Call emergency services now.',
    }
    severity_overrides = {
        'very high fever': 'High',
        'uncontrolled pain': 'High',
        'difficulty walking': 'High',
        'continuous vomiting': 'Moderate',
        'persistent fever': 'Moderate',
        'severe headache': 'Moderate',
    }

    # Build specialist mappings from knowledge base (legacy list + extended schemas).
    specialist_keywords = {}
    keyword_meta = {}
    if isinstance(kb_data, list):
        for item in kb_data:
            if not isinstance(item, dict):
                continue
            kw = str(item.get('symptom', '')).lower().strip()
            sp = str(item.get('specialist', '')).strip()
            if kw and sp:
                specialist_keywords.setdefault(sp, []).append(kw)
                keyword_meta[kw] = {
                    'specialist': sp,
                    'urgency': str(item.get('urgency', 'Low')),
                    'advice': str(item.get('advice', f'Consult a {sp} for clinical evaluation.')),
                }
    elif isinstance(kb_data, dict):
        specialists_arr = kb_data.get('specialists', [])
        for item in specialists_arr:
            name = str(item.get('name', '')).strip()
            kws = item.get('keywords', [])
            if not name or not isinstance(kws, list):
                continue
            parsed = [str(k).lower().strip() for k in kws if str(k).strip()]
            specialist_keywords[name] = parsed
            for kw in parsed:
                keyword_meta[kw] = {
                    'specialist': name,
                    'urgency': 'Moderate' if name != 'General Practitioner' else 'Low',
                    'advice': f'Consult a {name} for clinical evaluation.'
                }

    # Specialist priority, to avoid always falling back to GP when there is a clear match.
    specialist_priority = {
        'Emergency Medicine Doctor': 100,
        'Cardiologist': 90,
        'Pulmonologist': 88,
        'Neurologist': 84,
        'Orthopedic Surgeon': 82,
        'Gastroenterologist': 80,
        'Dermatologist': 76,
        'ENT Specialist': 74,
        'Dentist': 72,
        'Ophthalmologist': 70,
        'Gynecologist': 68,
        'Obstetrician': 67,
        'Urologist': 66,
        'Endocrinologist': 64,
        'Nephrologist': 63,
        'Infectious Disease Specialist': 62,
        'Rheumatologist': 61,
        'Hematologist': 60,
        'Psychiatrist': 58,
        'Psychologist': 57,
        'Pediatrician': 56,
        'General Practitioner': 1,
    }

    # Step 4 emergency check
    emergency_match = next((k for k in emergency_rules if k in normalized_text), None)
    if emergency_match:
        urgency = 'Emergency'
        specialist = 'Emergency Medicine Doctor'
        matched_keywords = [emergency_match]
        reason = f'The symptom "{emergency_match}" is a critical red-flag requiring immediate care.'
        action = emergency_rules[emergency_match]
    else:
        def keyword_in_text(kw, text):
            if kw in text:
                return True
            tokens = [t for t in kw.split() if t]
            return bool(tokens) and all(t in text for t in tokens)

        matched_keywords = []
        specialist_scores = {}
        for name, keywords in specialist_keywords.items():
            base = specialist_priority.get(name, 10)
            score = 0
            for kw in keywords:
                if keyword_in_text(kw, normalized_text):
                    score += 1
                    matched_keywords.append(kw)
            if score > 0:
                specialist_scores[name] = base + (score * 10)

        # Step 6 question handling, no diagnosis.
        is_question_input = ('what causes' in normalized_text or '?' in raw_input)
        if is_question_input and not specialist_scores:
            specialist = 'General Practitioner'
            urgency = 'Low'
            reason = 'Your question needs clinical context, so a primary evaluation is the safest first step.'
            action = 'A general practitioner can assess your symptoms and refer you to a specialist if needed.'
        elif specialist_scores:
            # Pick best specialist by weighted symptom relevance.
            specialist = sorted(
                specialist_scores.items(),
                key=lambda x: (-x[1], x[0])
            )[0][0]
            primary_kw = matched_keywords[0] if matched_keywords else ''
            meta = keyword_meta.get(primary_kw, {})
            urgency = str(meta.get('urgency', 'Moderate' if specialist != 'General Practitioner' else 'Low'))
            reason_templates = [
                'Your symptoms are most consistent with {sp}, especially "{kw}".',
                'Based on the symptom pattern ({kw}), {sp} is the most relevant specialist.',
                'Given "{kw}" in your description, {sp} is the best next clinical match.',
            ]
            template_idx = abs(hash(normalized_text)) % len(reason_templates)
            reason = reason_templates[template_idx].format(
                sp=specialist,
                kw=primary_kw if primary_kw else 'your symptom profile'
            )
            action_templates = [
                'Book a consultation with a {sp} for focused evaluation.',
                'A {sp} should assess this to confirm the cause and next steps.',
                'Please consult a {sp}; they are best suited for these symptoms.',
            ]
            action_idx = (abs(hash(normalized_text + specialist)) % len(action_templates))
            action = action_templates[action_idx].format(sp=specialist)
        else:
            specialist = 'General Practitioner'
            urgency = 'Low'
            reason = 'The symptoms are broad and could have multiple causes, so primary triage is appropriate.'
            action = 'A general practitioner can evaluate your symptoms and direct you to the right specialist.'

        # Smart urgency escalation by severity phrases.
        for sev_kw, sev_level in severity_overrides.items():
            if sev_kw in normalized_text:
                urgency = sev_level
                break

    # Anti-repetition wording guard for repeated specialist recommendations.
    patient = get_or_create_clinical_patient(current_user)
    recent_query = SymptomLog.query.filter_by(patient_id=patient.patient_id)
    symptom_pk_col = getattr(SymptomLog, 'symptom_id', None)
    if symptom_pk_col is not None:
        recent = recent_query.order_by(symptom_pk_col.desc()).limit(3).all()
    else:
        # Safety fallback for unexpected schema/model drift.
        recent = recent_query.limit(3).all()
    same_specialist_recently = any((r.recommended_specialist or '') == specialist for r in recent)
    if same_specialist_recently:
        if specialist == 'General Practitioner':
            reason = 'Your current symptoms still look general rather than organ-specific, so primary care triage remains safest.'
        else:
            reason = f'This pattern again points to {specialist}; repeating symptoms suggest follow-up with the same specialist.'

    row = SymptomLog(
        patient_id=patient.patient_id,
        symptoms=normalized_text,
        urgency_level=urgency,
        recommended_specialist=specialist
    )
    db.session.add(row)
    if urgency == 'Emergency':
        create_patient_notification(patient.patient_id, 'EMERGENCY ALERT: Please seek immediate medical attention')
        log_system_action('EMERGENCY_DETECTED', f'symptoms={normalized_text}', current_user)
    db.session.commit()

    safety_note = 'This system does not replace a doctor.'
    return jsonify({
        'success': True,
        'urgency': urgency,
        'recommended_specialist': specialist,
        'reason': reason,
        'action': action,
        'safety_note': safety_note,
        'matched_symptoms': sorted(set(matched_keywords)),
        'emergency': urgency == 'Emergency',
        # backward compatibility for existing frontend fields
        'specialist': specialist,
        'advice': action,
    })


@app.route('/api/dashboard/stats', methods=['GET'])
@login_required
def dashboard_stats():
    emergency_count = SymptomLog.query.filter(SymptomLog.urgency_level.ilike('Emergency')).count()
    stats = {
        'total_patients': Patient.query.count(),
        'total_doctors': Doctor.query.count(),
        'total_appointments': ClinicalAppointment.query.count(),
        'total_emergencies': emergency_count,
        'total_medical_records': MedicalRecord.query.count()
    }
    return jsonify({'success': True, 'stats': stats})

# --- DATABASE INITIALIZATION & MIGRATION ---
def init_db():
    with app.app_context():
        db.session.execute(db.text('PRAGMA foreign_keys=ON'))
        db.create_all()  # creates any missing tables
        init_relational_schema()

        # ── Safe column migrations (SQLite doesn't support IF NOT EXISTS on ALTER) ──
        migrations = [
            ("ALTER TABLE users ADD COLUMN phone VARCHAR(20)",),
            ("ALTER TABLE doctor_profiles ADD COLUMN experience VARCHAR(20)",),
            ("ALTER TABLE doctor_profiles ADD COLUMN qualification_path VARCHAR(300)",),
            ("ALTER TABLE doctor_profiles ADD COLUMN profile_image TEXT",),
            ("ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER DEFAULT 0",),
            ("ALTER TABLE users ADD COLUMN lock_until DATETIME",),
            ("ALTER TABLE users ADD COLUMN is_default_password BOOLEAN DEFAULT 0",),
            ("ALTER TABLE PATIENT ADD COLUMN date_created TEXT",),
            ("ALTER TABLE doctor_profiles ADD COLUMN clinical_doctor_id INTEGER",),
        ]
        with db.engine.connect() as conn:
            for (sql,) in migrations:
                try:
                    conn.execute(db.text(sql))
                    conn.commit()
                except Exception:
                    pass  # column already exists — safe to ignore

        # Seed default admin account
        if DEMO_MODE:
            if not User.query.filter_by(email='admin@medipath.health').first():
                admin = User(name='MediPath Primary Admin', email='admin@medipath.health', role='admin')
                admin.set_password('admin123')
                admin.is_default_password = True
                db.session.add(admin)
            if not Admin.query.filter_by(username='admin').first():
                a = Admin(name='MediPath Primary Admin', username='admin', password='')
                a.set_secure_password('admin123')
                db.session.add(a)
            ensure_clinical_doctors_seeded()
            ensure_demo_doctor_user_links()
        backfill_patient_rows_from_app_users()
        # Ensure all approved doctors (including non-demo registrations) are mirrored in DOCTOR.
        sync_approved_doctors_to_clinical_directory()
        if not Facility.query.first():
            db.session.add(Facility(
                name='MediPath Central Hospital',
                type='Hospital',
                location='Main Campus',
                emergency_available=1,
                phone='0000000000'
            ))
        run_daily_backup()
        db.session.commit()


def run_daily_backup():
    db_path = _sqlite_db_path()
    backup_dir = os.path.join(APP_DIR, 'backup')
    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.utcnow().strftime('%Y_%m_%d')
    backup_path = os.path.join(backup_dir, f'medipath_backup_{stamp}.db')
    try:
        if not db_path:
            log_system_action('DB_BACKUP_SKIPPED', 'Backup skipped for non-SQLite database URI')
            return
        if os.path.exists(db_path) and not os.path.exists(backup_path):
            shutil.copy2(db_path, backup_path)
            log_system_action('DB_BACKUP_SUCCESS', f'Created backup: {os.path.basename(backup_path)}')
        elif os.path.exists(backup_path):
            log_system_action('DB_BACKUP_SKIPPED', f'Backup already exists: {os.path.basename(backup_path)}')
        else:
            log_system_action('DB_BACKUP_FAILED', 'Database file missing for backup')
    except Exception as exc:
        log_system_action('DB_BACKUP_FAILED', str(exc))

def _port_is_open(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex((host, port)) == 0

def _open_frontend_when_ready(host, port):
    url = f'http://{host}:{port}'
    # Wait briefly for Flask to bind the port before opening the browser.
    for _ in range(30):
        if _port_is_open(host, port):
            webbrowser.open(url)
            return
        time.sleep(0.5)

if __name__ == '__main__':
    HOST = os.getenv('MEDIPATH_HOST', '127.0.0.1')
    PORT = int(os.getenv('MEDIPATH_PORT', '5005'))

    init_db()
    if HOST in ('127.0.0.1', 'localhost'):
        threading.Thread(
            target=_open_frontend_when_ready,
            args=(HOST, PORT),
            daemon=True
        ).start()
    # debug=False and use_reloader=False are REQUIRED for PyInstaller
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)
