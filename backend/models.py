from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class User(db.Model, UserMixin):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20))
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='patient') # patient, doctor, admin
    status = db.Column(db.String(20), nullable=False, default='active') # active, pending_approval, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    failed_login_attempts = db.Column(db.Integer, nullable=False, default=0)
    lock_until = db.Column(db.DateTime, nullable=True)
    is_default_password = db.Column(db.Boolean, nullable=False, default=False)
    
    # Relationships
    doctor_profile = db.relationship('DoctorProfile', backref='user', uselist=False)
    patient_appointments = db.relationship('Appointment', foreign_keys='Appointment.patient_id', backref='patient')
    doctor_appointments = db.relationship('Appointment', foreign_keys='Appointment.doctor_id', backref='doctor')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        d = {
            'id': self.id,
            'name': self.name,
            'email': self.email,
            'phone': self.phone,
            'role': self.role,
            'status': self.status,
            'is_default_password': self.is_default_password,
            'created_at': self.created_at.isoformat()
        }
        if self.doctor_profile:
            d.update(self.doctor_profile.to_dict())
        # Surface patient demographics (age/gender/residence) for profile/admin views.
        if self.role == 'patient' and self.email:
            p = Patient.query.filter_by(email=self.email.strip()).first()
            if p:
                d['age'] = p.age
                d['gender'] = p.gender
                d['residence'] = p.residence or p.address
        return d

class DoctorProfile(db.Model):
    __tablename__ = 'doctor_profiles'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    specialty = db.Column(db.String(100))
    hospital = db.Column(db.String(100))
    bio = db.Column(db.Text)
    license_number = db.Column(db.String(50))
    experience = db.Column(db.String(20))  # years of experience
    qualification_path = db.Column(db.String(300))  # uploaded file path
    profile_image = db.Column(db.Text)  # base64 data URL for doctor avatar
    rejection_reason = db.Column(db.Text)
    # Links an app-user doctor to a row in DOCTOR for clinical APIs / booking.
    clinical_doctor_id = db.Column(db.Integer, nullable=True)

    def to_dict(self):
        return {
            'specialty': self.specialty,
            'hospital': self.hospital,
            'bio': self.bio,
            'license_number': self.license_number,
            'experience': self.experience,
            'qualification_path': self.qualification_path,
            'profile_image': self.profile_image,
            'rejection_reason': self.rejection_reason,
            'clinical_doctor_id': self.clinical_doctor_id,
        }

class Appointment(db.Model):
    """Legacy user-to-user appointments; shares SQLite `appointments` with clinical rows."""
    __tablename__ = 'appointments'

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date_time = db.Column(db.DateTime, nullable=False)  # DB NOT NULL; required on every insert
    status = db.Column(db.String(20), default='Pending') # Pending, Approved, Completed, Cancelled
    reason = db.Column(db.Text)
    cancellation_reason = db.Column(db.Text)
    cancelled_by = db.Column(db.String(20)) # Patient, Doctor, Admin

    def to_dict(self):
        return {
            'id': self.id,
            'patient_id': self.patient_id,
            'doctor_id': self.doctor_id,
            'date_time': self.date_time.isoformat(),
            'status': self.status,
            'reason': self.reason
        }

class Message(db.Model):
    __tablename__ = 'messages'
    
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)


class PasswordMixin:
    def set_secure_password(self, raw_password):
        self.password = generate_password_hash(raw_password)

    def verify_secure_password(self, raw_password):
        return bool(self.password) and check_password_hash(self.password, raw_password)


class Admin(db.Model, PasswordMixin):
    __tablename__ = 'ADMIN'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.Text, nullable=False)
    username = db.Column(db.Text, unique=True, nullable=False)
    password = db.Column(db.Text, nullable=False)


class Patient(db.Model, PasswordMixin):
    __tablename__ = 'PATIENT'
    patient_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    first_name = db.Column(db.Text, nullable=False)
    last_name = db.Column(db.Text, nullable=False)
    gender = db.Column(db.Text)
    date_of_birth = db.Column(db.Text)
    phone = db.Column(db.Text)
    email = db.Column(db.Text, unique=True)
    address = db.Column(db.Text)
    password = db.Column(db.Text, nullable=False)
    # Optional: synced at registration / migration (SQLite ALTER adds column if missing)
    date_created = db.Column(db.Text)
    # Documentation scope: collected at registration.
    age = db.Column(db.Integer)
    residence = db.Column(db.Text)


class Doctor(db.Model, PasswordMixin):
    __tablename__ = 'DOCTOR'
    doctor_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    first_name = db.Column(db.Text, nullable=False)
    last_name = db.Column(db.Text, nullable=False)
    specialty = db.Column(db.Text)
    phone = db.Column(db.Text)
    email = db.Column(db.Text, unique=True)
    availability = db.Column(db.Text)
    password = db.Column(db.Text, nullable=False)


class Facility(db.Model):
    __tablename__ = 'FACILITY'
    facility_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.Text, nullable=False)
    type = db.Column(db.Text)
    location = db.Column(db.Text)
    emergency_available = db.Column(db.Integer, default=0)
    phone = db.Column(db.Text)


class ClinicalAppointment(db.Model):
    __tablename__ = 'APPOINTMENTS'
    # Map to the shared appointments table primary key used in SQLite schema.
    id = db.Column('id', db.Integer, primary_key=True, autoincrement=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('PATIENT.patient_id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('DOCTOR.doctor_id'), nullable=False)
    facility_id = db.Column(db.Integer, db.ForeignKey('FACILITY.facility_id'))
    appointment_date = db.Column(db.Text, nullable=False)
    # Same physical table as legacy `Appointment`; SQLite requires NOT NULL date_time on many DBs.
    date_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.Text, default='Pending')
    notes = db.Column(db.Text)

    @property
    def appointment_id(self):
        # Backward-compatible accessor used by existing API responses.
        return self.id


class MedicalRecord(db.Model):
    __tablename__ = 'MEDICAL_RECORDS'
    record_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('PATIENT.patient_id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('DOCTOR.doctor_id'), nullable=False)
    diagnosis = db.Column(db.Text)
    prescription = db.Column(db.Text)
    treatment = db.Column(db.Text)
    visit_date = db.Column(db.Text, nullable=False)


class SymptomLog(db.Model):
    __tablename__ = 'SYMPTOM_LOGS'
    symptom_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('PATIENT.patient_id'), nullable=False)
    symptoms = db.Column(db.Text)
    urgency_level = db.Column(db.Text)
    recommended_specialist = db.Column(db.Text)
    date_created = db.Column(db.Text, default=lambda: datetime.utcnow().isoformat())


class Notification(db.Model):
    __tablename__ = 'NOTIFICATIONS'
    notification_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('PATIENT.patient_id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.Text, default='Unread')
    date_created = db.Column(db.Text, default=lambda: datetime.utcnow().isoformat())


class SystemLog(db.Model):
    __tablename__ = 'system_logs'
    log_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer)
    user_role = db.Column(db.Text)
    action = db.Column(db.Text, nullable=False)
    details = db.Column(db.Text)
    created_at = db.Column(db.Text, default=lambda: datetime.utcnow().isoformat())


# ============================================================
#  Subscription & Payment models (documentation scope)
#  - One Subscription row per portal user (patient/doctor).
#  - Payment rows are an immutable audit log of each payment.
#  - ContactMessage stores "Contact Care Team" submissions for admin.
# ============================================================
class Subscription(db.Model):
    __tablename__ = 'subscriptions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    role = db.Column(db.String(20))                      # patient | doctor
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    expiry_date = db.Column(db.DateTime)
    payment_status = db.Column(db.String(20), default='pending')   # pending | paid | overdue
    account_status = db.Column(db.String(20), default='active')    # active | frozen
    last_reminder_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'role': self.role,
            'start_date': self.start_date.isoformat() if self.start_date else None,
            'expiry_date': self.expiry_date.isoformat() if self.expiry_date else None,
            'payment_status': self.payment_status,
            'account_status': self.account_status,
        }


class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    payer_name = db.Column(db.String(120))
    role = db.Column(db.String(20))                      # patient | doctor
    payment_mode = db.Column(db.String(40))             # Airtel Money | MTN Mobile Money | Zamtel Money
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(8), default='ZMW')
    phone = db.Column(db.String(20))
    reference = db.Column(db.String(60))
    period_months = db.Column(db.Integer, default=3)
    expiry_date = db.Column(db.DateTime)               # subscription expiry produced by this payment
    status = db.Column(db.String(20), default='completed')  # completed
    paid_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'payer_name': self.payer_name,
            'role': self.role,
            'payment_mode': self.payment_mode,
            'amount': self.amount,
            'currency': self.currency,
            'phone': self.phone,
            'reference': self.reference,
            'period_months': self.period_months,
            'expiry_date': self.expiry_date.isoformat() if self.expiry_date else None,
            'status': self.status,
            'paid_at': self.paid_at.isoformat() if self.paid_at else None,
        }


class ContactMessage(db.Model):
    __tablename__ = 'contact_messages'
    id = db.Column(db.Integer, primary_key=True)
    sender_user_id = db.Column(db.Integer, nullable=True)   # set when sender is logged in
    name = db.Column(db.String(120))
    email = db.Column(db.String(120))
    subject = db.Column(db.String(200))
    message = db.Column(db.Text, nullable=False)
    role = db.Column(db.String(20), default='guest')        # patient | doctor | admin | guest
    status = db.Column(db.String(20), default='unread')     # unread | read
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'sender_user_id': self.sender_user_id,
            'name': self.name,
            'email': self.email,
            'subject': self.subject,
            'message': self.message,
            'role': self.role,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
