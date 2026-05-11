PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS ADMIN (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS PATIENT (
    patient_id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    gender TEXT,
    date_of_birth TEXT,
    phone TEXT,
    email TEXT UNIQUE,
    address TEXT,
    password TEXT NOT NULL,
    date_created TEXT
);

CREATE TABLE IF NOT EXISTS DOCTOR (
    doctor_id INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name TEXT NOT NULL,
    last_name TEXT NOT NULL,
    specialty TEXT,
    phone TEXT,
    email TEXT UNIQUE,
    availability TEXT,
    password TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS FACILITY (
    facility_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT,
    location TEXT,
    emergency_available INTEGER NOT NULL DEFAULT 0 CHECK (emergency_available IN (0,1)),
    phone TEXT
);

CREATE TABLE IF NOT EXISTS APPOINTMENTS (
    appointment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    doctor_id INTEGER NOT NULL,
    facility_id INTEGER,
    appointment_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Pending' CHECK (status IN ('Pending','Confirmed','Completed','Cancelled')),
    notes TEXT,
    FOREIGN KEY (patient_id) REFERENCES PATIENT(patient_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (doctor_id) REFERENCES DOCTOR(doctor_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (facility_id) REFERENCES FACILITY(facility_id) ON DELETE SET NULL ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS MEDICAL_RECORDS (
    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    doctor_id INTEGER NOT NULL,
    diagnosis TEXT,
    prescription TEXT,
    treatment TEXT,
    visit_date TEXT NOT NULL,
    FOREIGN KEY (patient_id) REFERENCES PATIENT(patient_id) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (doctor_id) REFERENCES DOCTOR(doctor_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS SYMPTOM_LOGS (
    symptom_id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    symptoms TEXT,
    urgency_level TEXT,
    recommended_specialist TEXT,
    date_created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES PATIENT(patient_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS NOTIFICATIONS (
    notification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL,
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Unread' CHECK (status IN ('Unread','Read')),
    date_created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (patient_id) REFERENCES PATIENT(patient_id) ON DELETE CASCADE ON UPDATE CASCADE
);

CREATE TABLE IF NOT EXISTS system_logs (
    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    user_role TEXT,
    action TEXT NOT NULL,
    details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_admin_username ON ADMIN(username);
CREATE INDEX IF NOT EXISTS idx_patient_email ON PATIENT(email);
CREATE INDEX IF NOT EXISTS idx_doctor_email ON DOCTOR(email);
CREATE INDEX IF NOT EXISTS idx_doctor_specialty ON DOCTOR(specialty);
CREATE INDEX IF NOT EXISTS idx_appointments_patient ON APPOINTMENTS(patient_id);
CREATE INDEX IF NOT EXISTS idx_appointments_doctor ON APPOINTMENTS(doctor_id);
CREATE INDEX IF NOT EXISTS idx_appointments_date ON APPOINTMENTS(appointment_date);
CREATE INDEX IF NOT EXISTS idx_appointments_status ON APPOINTMENTS(status);
CREATE INDEX IF NOT EXISTS idx_records_patient ON MEDICAL_RECORDS(patient_id);
CREATE INDEX IF NOT EXISTS idx_records_doctor ON MEDICAL_RECORDS(doctor_id);
CREATE INDEX IF NOT EXISTS idx_symptoms_patient ON SYMPTOM_LOGS(patient_id);
CREATE INDEX IF NOT EXISTS idx_symptoms_created ON SYMPTOM_LOGS(date_created);
CREATE INDEX IF NOT EXISTS idx_notifications_patient ON NOTIFICATIONS(patient_id);
CREATE INDEX IF NOT EXISTS idx_notifications_status ON NOTIFICATIONS(status);
CREATE INDEX IF NOT EXISTS idx_logs_created ON system_logs(created_at);
