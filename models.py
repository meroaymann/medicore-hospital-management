from datetime import datetime, date

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

# ---------- Fixed choices used in forms ----------
SPECIALTIES = [
    "General Medicine", "Cardiology", "Pediatrics", "Orthopedics", "Dermatology",
    "Neurology", "Gynecology", "ENT", "Ophthalmology", "Dentistry",
]
BLOOD_TYPES = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
APPOINTMENT_STATUSES = ["scheduled", "completed", "cancelled", "no_show"]
PAYMENT_METHODS = ["Cash", "Card", "Insurance"]


def now():
    return datetime.now()


# ---------- Staff who log in ----------
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="staff")  # admin / staff
    created_at = db.Column(db.DateTime, default=now)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == "admin"


# ---------- Patients ----------
class Patient(db.Model):
    __tablename__ = "patients"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    gender = db.Column(db.String(10), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=False)
    phone = db.Column(db.String(20), nullable=False, index=True)
    email = db.Column(db.String(120))
    address = db.Column(db.String(200))
    blood_type = db.Column(db.String(5))
    created_at = db.Column(db.DateTime, default=now)

    # Deleting a patient also deletes their records
    appointments = db.relationship("Appointment", backref="patient", lazy=True, cascade="all, delete-orphan")
    bills = db.relationship("Bill", backref="patient", lazy=True, cascade="all, delete-orphan")
    prescriptions = db.relationship("Prescription", backref="patient", lazy=True, cascade="all, delete-orphan")

    @property
    def age(self):
        today = date.today()
        dob = self.date_of_birth
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


# ---------- Doctors ----------
class Doctor(db.Model):
    __tablename__ = "doctors"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, index=True)
    specialty = db.Column(db.String(50), nullable=False)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    consultation_fee = db.Column(db.Float, nullable=False, default=0)
    status = db.Column(db.String(10), nullable=False, default="active")  # active / off
    created_at = db.Column(db.DateTime, default=now)

    appointments = db.relationship("Appointment", backref="doctor", lazy=True)
    prescriptions = db.relationship("Prescription", backref="doctor", lazy=True)


# ---------- Appointments ----------
class Appointment(db.Model):
    __tablename__ = "appointments"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=False)
    date = db.Column(db.Date, nullable=False, index=True)
    time = db.Column(db.Time, nullable=False)
    reason = db.Column(db.String(200))
    status = db.Column(db.String(20), nullable=False, default="scheduled")
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=now)

    bill = db.relationship("Bill", backref="appointment", uselist=False)
    prescription = db.relationship("Prescription", backref="appointment", uselist=False)


# ---------- Bills ----------
class Bill(db.Model):
    __tablename__ = "bills"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    appointment_id = db.Column(db.Integer, db.ForeignKey("appointments.id"), unique=True)
    amount = db.Column(db.Float, nullable=False)
    paid_amount = db.Column(db.Float, nullable=False, default=0)
    status = db.Column(db.String(10), nullable=False, default="unpaid")  # paid / partial / unpaid
    payment_method = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=now)

    @property
    def balance(self):
        """What's left to pay, rounded to 2 decimals (avoids tiny float errors)."""
        return round(max(self.amount - self.paid_amount, 0), 2)

    def update_status(self):
        if self.balance <= 0:
            self.status = "paid"
        elif self.paid_amount > 0:
            self.status = "partial"
        else:
            self.status = "unpaid"


# ---------- Prescriptions ----------
class Prescription(db.Model):
    __tablename__ = "prescriptions"

    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey("appointments.id"), unique=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey("doctors.id"), nullable=False)
    diagnosis = db.Column(db.String(200), nullable=False)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=now)

    items = db.relationship("PrescriptionItem", backref="prescription", lazy=True, cascade="all, delete-orphan")


class PrescriptionItem(db.Model):
    __tablename__ = "prescription_items"

    id = db.Column(db.Integer, primary_key=True)
    prescription_id = db.Column(db.Integer, db.ForeignKey("prescriptions.id"), nullable=False)
    medicine = db.Column(db.String(100), nullable=False)
    dosage = db.Column(db.String(50))
    frequency = db.Column(db.String(50))
    duration = db.Column(db.String(50))