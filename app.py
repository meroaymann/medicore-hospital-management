import os
import re
from datetime import date, datetime

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv
from sqlalchemy import or_, func

from models import db, User, Patient, Doctor, Appointment, Bill, Prescription, BLOOD_TYPES, SPECIALTIES

load_dotenv()

APP_NAME = "MediCore"  # change the app name here only

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-only-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///hospital.db"  # saved in the instance/ folder
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)

# ---------- Login manager ----------
login_manager = LoginManager(app)
login_manager.login_view = "login"  # where to send users who aren't logged in
login_manager.login_message = "Please log in to continue."
login_manager.login_message_category = "warning"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


with app.app_context():
    db.create_all()

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[0-9\s-]{7,20}$")


SPECIALTY_ICONS = {
    "General Medicine": "🩺", "Cardiology": "❤️", "Pediatrics": "🧸", "Orthopedics": "🦴",
    "Dermatology": "🧴", "Neurology": "🧠", "Gynecology": "🤰", "ENT": "👂",
    "Ophthalmology": "👁️", "Dentistry": "🦷",
}


@app.context_processor
def inject_globals():
    """Variables available in every template."""
    return {"app_name": APP_NAME, "today": date.today(), "specialty_icons": SPECIALTY_ICONS}


def is_safe_next(target):
    """Only allow redirects inside our own site."""
    return bool(target) and target.startswith("/") and not target.startswith("//")


# ================= AUTH =================
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    email = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        remember = request.form.get("remember") == "on"

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user, remember=remember)
            flash(f"Welcome back, {user.name}! 👋", "success")
            next_url = request.args.get("next")
            return redirect(next_url if is_safe_next(next_url) else url_for("dashboard"))

        flash("Incorrect email or password.", "error")

    return render_template("auth/login.html", email=email)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    form = {"name": "", "email": ""}
    if request.method == "POST":
        form["name"] = request.form.get("name", "").strip()
        form["email"] = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        error = None
        if not form["name"] or not form["email"] or not password:
            error = "Please fill in all fields."
        elif len(form["name"]) > 80:
            error = "Name is too long."
        elif not EMAIL_RE.match(form["email"]):
            error = "Please enter a valid email."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm:
            error = "Passwords don't match."
        elif User.query.filter_by(email=form["email"]).first():
            error = "An account with this email already exists."

        if error:
            flash(error, "error")
        else:
            # The very first account becomes the admin
            role = "admin" if User.query.count() == 0 else "staff"
            user = User(name=form["name"], email=form["email"], role=role)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()

            login_user(user)
            flash(f"Account created. Welcome, {user.name}! 🎉", "success")
            return redirect(url_for("dashboard"))

    return render_template("auth/signup.html", form=form)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ================= PAGES =================
@app.route("/")
@login_required
def dashboard():
    """Temporary dashboard (the real one comes in Phase 10)."""
    counts = {
        "Patients": Patient.query.count(),
        "Doctors": Doctor.query.count(),
        "Appointments": Appointment.query.count(),
        "Bills": Bill.query.count(),
        "Prescriptions": Prescription.query.count(),
    }
    return render_template("dashboard.html", counts=counts)

# ================= PATIENTS =================
PATIENT_FIELDS = ["name", "gender", "date_of_birth", "phone", "email", "address", "blood_type"]


def read_patient_form(form):
    """Read and check the patient form. Returns (data, date_of_birth, errors)."""
    data = {field: form.get(field, "").strip() for field in PATIENT_FIELDS}
    errors = []
    dob = None

    if not data["name"]:
        errors.append("Name is required.")
    elif len(data["name"]) > 100:
        errors.append("Name is too long.")

    if data["gender"] not in ("Male", "Female"):
        errors.append("Please choose a gender.")

    try:
        dob = datetime.strptime(data["date_of_birth"], "%Y-%m-%d").date()
        if dob > date.today():
            errors.append("Date of birth can't be in the future.")
        elif dob.year < 1900:
            errors.append("Please enter a valid date of birth.")
    except ValueError:
        errors.append("Please enter a valid date of birth.")

    if not PHONE_RE.match(data["phone"]):
        errors.append("Please enter a valid phone number.")

    if data["email"] and not EMAIL_RE.match(data["email"]):
        errors.append("Please enter a valid email.")

    if data["blood_type"] and data["blood_type"] not in BLOOD_TYPES:
        errors.append("Please choose a valid blood type.")

    return data, dob, errors


@app.route("/patients")
@login_required
def patients_list():
    q = request.args.get("q", "").strip()
    gender = request.args.get("gender", "")
    sort = request.args.get("sort", "newest")
    page = request.args.get("page", 1, type=int)

    query = Patient.query
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Patient.name.ilike(like),
            Patient.phone.ilike(like),
            Patient.email.ilike(like),
        ))
    if gender in ("Male", "Female"):
        query = query.filter(Patient.gender == gender)

    if sort == "name":
        query = query.order_by(Patient.name.asc())
    elif sort == "oldest":
        query = query.order_by(Patient.created_at.asc())
    else:
        query = query.order_by(Patient.created_at.desc())

    pager = query.paginate(page=page, per_page=10, error_out=False)
    return render_template("patients/list.html", pager=pager, q=q, gender=gender, sort=sort)


@app.route("/patients/new", methods=["GET", "POST"])
@login_required
def patient_new():
    form = {}
    if request.method == "POST":
        form, dob, errors = read_patient_form(request.form)
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            patient = Patient(
                name=form["name"],
                gender=form["gender"],
                date_of_birth=dob,
                phone=form["phone"],
                email=form["email"] or None,
                address=form["address"] or None,
                blood_type=form["blood_type"] or None,
            )
            db.session.add(patient)
            db.session.commit()
            flash(f"{patient.name} was registered successfully. ✅", "success")
            return redirect(url_for("patient_view", patient_id=patient.id))

    return render_template("patients/form.html", form=form, patient=None, blood_types=BLOOD_TYPES)


@app.route("/patients/<int:patient_id>")
@login_required
def patient_view(patient_id):
    patient = db.get_or_404(Patient, patient_id)

    appointments = sorted(patient.appointments, key=lambda a: (a.date, a.time), reverse=True)
    bills = sorted(patient.bills, key=lambda b: b.created_at, reverse=True)
    prescriptions = sorted(patient.prescriptions, key=lambda p: p.created_at, reverse=True)

    stats = {
        "visits": sum(1 for a in appointments if a.status == "completed"),
        "upcoming": sum(1 for a in appointments if a.status == "scheduled" and a.date >= date.today()),
        "billed": sum(b.amount for b in bills),
        "balance": sum(b.balance for b in bills),
    }

    return render_template(
        "patients/profile.html",
        patient=patient,
        appointments=appointments,
        bills=bills,
        prescriptions=prescriptions,
        stats=stats,
    )


@app.route("/patients/<int:patient_id>/edit", methods=["GET", "POST"])
@login_required
def patient_edit(patient_id):
    patient = db.get_or_404(Patient, patient_id)

    if request.method == "POST":
        form, dob, errors = read_patient_form(request.form)
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            patient.name = form["name"]
            patient.gender = form["gender"]
            patient.date_of_birth = dob
            patient.phone = form["phone"]
            patient.email = form["email"] or None
            patient.address = form["address"] or None
            patient.blood_type = form["blood_type"] or None
            db.session.commit()
            flash("Patient details updated. ✅", "success")
            return redirect(url_for("patient_view", patient_id=patient.id))
    else:
        # Fill the form with the current details
        form = {
            "name": patient.name,
            "gender": patient.gender,
            "date_of_birth": patient.date_of_birth.isoformat(),
            "phone": patient.phone,
            "email": patient.email or "",
            "address": patient.address or "",
            "blood_type": patient.blood_type or "",
        }

    return render_template("patients/form.html", form=form, patient=patient, blood_types=BLOOD_TYPES)


@app.route("/patients/<int:patient_id>/delete", methods=["POST"])
@login_required
def patient_delete(patient_id):
    patient = db.get_or_404(Patient, patient_id)
    name = patient.name
    db.session.delete(patient)  # also deletes their appointments, bills and prescriptions
    db.session.commit()
    flash(f"{name} was deleted.", "info")
    return redirect(url_for("patients_list"))

# ================= DOCTORS =================
DOCTOR_FIELDS = ["name", "specialty", "phone", "email", "consultation_fee", "status"]
DR_PREFIX_RE = re.compile(r"^dr\.?\s", re.IGNORECASE)


def read_doctor_form(form):
    """Read and check the doctor form. Returns (data, fee, errors)."""
    data = {field: form.get(field, "").strip() for field in DOCTOR_FIELDS}
    errors = []
    fee = None

    if not data["name"]:
        errors.append("Name is required.")
    elif len(data["name"]) > 100:
        errors.append("Name is too long.")
    elif not DR_PREFIX_RE.match(data["name"]):
        data["name"] = f"Dr. {data['name']}"  # add "Dr." automatically

    if data["specialty"] not in SPECIALTIES:
        errors.append("Please choose a specialty.")

    if data["phone"] and not PHONE_RE.match(data["phone"]):
        errors.append("Please enter a valid phone number.")

    if data["email"] and not EMAIL_RE.match(data["email"]):
        errors.append("Please enter a valid email.")

    try:
        fee = float(data["consultation_fee"])
        if fee < 0 or fee > 100_000:
            errors.append("Please enter a valid consultation fee.")
    except ValueError:
        errors.append("Please enter a valid consultation fee.")

    if data["status"] not in ("active", "off"):
        data["status"] = "active"

    return data, fee, errors


@app.route("/doctors")
@login_required
def doctors_list():
    q = request.args.get("q", "").strip()
    specialty = request.args.get("specialty", "")
    status = request.args.get("status", "")

    query = Doctor.query
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Doctor.name.ilike(like),
            Doctor.specialty.ilike(like),
            Doctor.email.ilike(like),
        ))
    if specialty in SPECIALTIES:
        query = query.filter(Doctor.specialty == specialty)
    if status in ("active", "off"):
        query = query.filter(Doctor.status == status)

    doctors = query.order_by(Doctor.status.asc(), Doctor.name.asc()).all()

    # Appointment counts per doctor (one query each, not one per doctor)
    total_counts = dict(
        db.session.query(Appointment.doctor_id, func.count(Appointment.id))
        .group_by(Appointment.doctor_id).all()
    )
    today_counts = dict(
        db.session.query(Appointment.doctor_id, func.count(Appointment.id))
        .filter(Appointment.date == date.today(), Appointment.status != "cancelled")
        .group_by(Appointment.doctor_id).all()
    )

    return render_template(
        "doctors/list.html",
        doctors=doctors,
        total_counts=total_counts,
        today_counts=today_counts,
        active_count=Doctor.query.filter_by(status="active").count(),
        specialties=SPECIALTIES,
        q=q, specialty=specialty, status=status,
    )


@app.route("/doctors/new", methods=["GET", "POST"])
@login_required
def doctor_new():
    form = {"status": "active"}
    if request.method == "POST":
        form, fee, errors = read_doctor_form(request.form)
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            doctor = Doctor(
                name=form["name"],
                specialty=form["specialty"],
                phone=form["phone"] or None,
                email=form["email"] or None,
                consultation_fee=fee,
                status=form["status"],
            )
            db.session.add(doctor)
            db.session.commit()
            flash(f"{doctor.name} was added. ✅", "success")
            return redirect(url_for("doctor_view", doctor_id=doctor.id))

    return render_template("doctors/form.html", form=form, doctor=None, specialties=SPECIALTIES)


@app.route("/doctors/<int:doctor_id>")
@login_required
def doctor_view(doctor_id):
    doctor = db.get_or_404(Doctor, doctor_id)
    today = date.today()
    appts = doctor.appointments

    revenue = (
        db.session.query(func.coalesce(func.sum(Bill.paid_amount), 0))
        .join(Appointment, Bill.appointment_id == Appointment.id)
        .filter(Appointment.doctor_id == doctor.id)
        .scalar()
    )

    stats = {
        "total": len(appts),
        "completed": sum(1 for a in appts if a.status == "completed"),
        "today": sum(1 for a in appts if a.date == today and a.status != "cancelled"),
        "patients": len({a.patient_id for a in appts}),
        "revenue": revenue,
    }

    upcoming = sorted(
        (a for a in appts if a.status == "scheduled" and a.date >= today),
        key=lambda a: (a.date, a.time),
    )[:10]
    recent = sorted(
        (a for a in appts if a.date < today),
        key=lambda a: (a.date, a.time),
        reverse=True,
    )[:10]

    return render_template("doctors/profile.html", doctor=doctor, stats=stats,
                           upcoming=upcoming, recent=recent)


@app.route("/doctors/<int:doctor_id>/edit", methods=["GET", "POST"])
@login_required
def doctor_edit(doctor_id):
    doctor = db.get_or_404(Doctor, doctor_id)

    if request.method == "POST":
        form, fee, errors = read_doctor_form(request.form)
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            doctor.name = form["name"]
            doctor.specialty = form["specialty"]
            doctor.phone = form["phone"] or None
            doctor.email = form["email"] or None
            doctor.consultation_fee = fee
            doctor.status = form["status"]
            db.session.commit()
            flash("Doctor details updated. ✅", "success")
            return redirect(url_for("doctor_view", doctor_id=doctor.id))
    else:
        form = {
            "name": doctor.name,
            "specialty": doctor.specialty,
            "phone": doctor.phone or "",
            "email": doctor.email or "",
            "consultation_fee": f"{doctor.consultation_fee:g}",
            "status": doctor.status,
        }

    return render_template("doctors/form.html", form=form, doctor=doctor, specialties=SPECIALTIES)


@app.route("/doctors/<int:doctor_id>/toggle", methods=["POST"])
@login_required
def doctor_toggle(doctor_id):
    doctor = db.get_or_404(Doctor, doctor_id)
    doctor.status = "off" if doctor.status == "active" else "active"
    db.session.commit()

    label = "available again" if doctor.status == "active" else "set to off duty"
    flash(f"{doctor.name} is {label}.", "success")

    next_url = request.form.get("next")
    return redirect(next_url if is_safe_next(next_url) else url_for("doctor_view", doctor_id=doctor.id))


@app.route("/doctors/<int:doctor_id>/delete", methods=["POST"])
@login_required
def doctor_delete(doctor_id):
    doctor = db.get_or_404(Doctor, doctor_id)

    # Keep patient history safe: don't delete doctors who have appointments
    if doctor.appointments:
        flash(f"{doctor.name} has appointments, so they can't be deleted. Set them to Off instead.", "warning")
        return redirect(url_for("doctor_view", doctor_id=doctor.id))

    name = doctor.name
    db.session.delete(doctor)
    db.session.commit()
    flash(f"{name} was deleted.", "info")
    return redirect(url_for("doctors_list"))

# ================= PLACEHOLDER PAGES (replaced in the next phases) =================
def coming_soon(title, icon, phase):
    return render_template("coming_soon.html", title=title, icon=icon, phase=phase)






@app.route("/appointments")
@login_required
def appointments_list():
    return coming_soon("Appointments", "📅", 6)


@app.route("/billing")
@login_required
def bills_list():
    return coming_soon("Billing", "💰", 7)


@app.route("/prescriptions")
@login_required
def prescriptions_list():
    return coming_soon("Prescriptions", "💊", 8)


@app.route("/search")
@login_required
def search():
    q = request.args.get("q", "").strip()
    title = f'Search: "{q}"' if q else "Search"
    return coming_soon(title, "🔍", 11)

if __name__ == "__main__":
    app.run(debug=True)