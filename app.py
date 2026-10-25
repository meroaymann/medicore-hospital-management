import os
import re
from datetime import date, datetime, time as dtime, timedelta

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv
from sqlalchemy import or_, func

from models import (
    db, User, Patient, Doctor, Appointment, Bill, Prescription, PrescriptionItem,
    BLOOD_TYPES, SPECIALTIES, APPOINTMENT_STATUSES, PAYMENT_METHODS,
)
from markupsafe import Markup, escape
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

@app.template_filter("money")
def money_filter(value):
    """Format numbers as money: 1250 → '1,250 EGP'."""
    return f"{value or 0:,.0f} EGP"

@app.template_filter("highlight")
def highlight_filter(text, query):
    """Wrap the matching part of the text in <mark> (safely escaped)."""
    text = "" if text is None else str(text)
    if not query:
        return escape(text)

    pattern = re.compile(re.escape(query), re.IGNORECASE)
    parts, last = [], 0
    for match in pattern.finditer(text):
        parts.append(escape(text[last:match.start()]))
        parts.append(Markup("<mark>") + escape(match.group()) + Markup("</mark>"))
        last = match.end()
    parts.append(escape(text[last:]))
    return Markup("").join(parts)

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


# ================= DASHBOARD =================
STATUS_LABELS = {"scheduled": "Scheduled", "completed": "Completed", "cancelled": "Cancelled", "no_show": "No-show"}
AGE_GROUPS = [("0–17", 0, 17), ("18–35", 18, 35), ("36–60", 36, 60), ("60+", 61, 200)]


def percent(part, whole):
    return round(part / whole * 100, 1) if whole else 0


def change(current, previous):
    """Percentage change vs the previous period (None if there's nothing to compare)."""
    if not previous:
        return None
    return round((current - previous) / previous * 100, 1)


def last_n_months(n, today):
    """[(year, month), ...] for the last n months, oldest first."""
    months, year, month = [], today.year, today.month
    for _ in range(n):
        months.append((year, month))
        month -= 1
        if month == 0:
            month, year = 12, year - 1
    return list(reversed(months))


@app.route("/")
@login_required
def dashboard():
    today = date.today()
    now = datetime.now()
    month_start = today.replace(day=1)
    prev_month_start = (month_start - timedelta(days=1)).replace(day=1)
    month_start_dt = datetime.combine(month_start, dtime.min)
    prev_month_start_dt = datetime.combine(prev_month_start, dtime.min)

    # ---------- KPI cards ----------
    total_patients = Patient.query.count()
    new_patients = Patient.query.filter(Patient.created_at >= month_start_dt).count()
    new_patients_prev = Patient.query.filter(
        Patient.created_at >= prev_month_start_dt, Patient.created_at < month_start_dt
    ).count()

    todays = Appointment.query.filter(Appointment.date == today).order_by(Appointment.time).all()
    today_done = sum(1 for a in todays if a.status == "completed")
    today_left = sum(1 for a in todays if a.status == "scheduled")

    upcoming = Appointment.query.filter(Appointment.date > today, Appointment.status == "scheduled").count()
    active_doctors = Doctor.query.filter_by(status="active").count()
    total_doctors = Doctor.query.count()

    revenue_month = db.session.query(func.coalesce(func.sum(Bill.paid_amount), 0)).filter(
        Bill.created_at >= month_start_dt).scalar()
    revenue_prev = db.session.query(func.coalesce(func.sum(Bill.paid_amount), 0)).filter(
        Bill.created_at >= prev_month_start_dt, Bill.created_at < month_start_dt).scalar()

    unpaid_amount, unpaid_count = db.session.query(
        func.coalesce(func.sum(Bill.amount - Bill.paid_amount), 0), func.count(Bill.id)
    ).filter(Bill.status != "paid").one()

    billed_total, collected_total = db.session.query(
        func.coalesce(func.sum(Bill.amount), 0), func.coalesce(func.sum(Bill.paid_amount), 0)
    ).one()

    # Rates are based on appointments that already happened
    past = dict(
        db.session.query(Appointment.status, func.count(Appointment.id))
        .filter(Appointment.date < today).group_by(Appointment.status).all()
    )
    past_total = sum(past.values())

    billed_patients = db.session.query(func.count(func.distinct(Bill.patient_id))).scalar()

    visits = db.session.query(Appointment.patient_id, func.count(Appointment.id)).filter(
        Appointment.status == "completed").group_by(Appointment.patient_id).all()
    returning = sum(1 for _, count in visits if count >= 2)

    kpis = {
        "total_patients": total_patients,
        "new_patients": new_patients,
        "new_patients_change": change(new_patients, new_patients_prev),
        "today_total": len(todays),
        "today_done": today_done,
        "today_left": today_left,
        "upcoming": upcoming,
        "active_doctors": active_doctors,
        "total_doctors": total_doctors,
        "revenue_month": revenue_month,
        "revenue_change": change(revenue_month, revenue_prev),
        "unpaid_amount": unpaid_amount,
        "unpaid_count": unpaid_count,
        "cancellation_rate": percent(past.get("cancelled", 0), past_total),
        "collection_rate": percent(collected_total, billed_total),
        "no_show_rate": percent(past.get("no_show", 0), past_total),
        "completion_rate": percent(past.get("completed", 0), past_total),
        "avg_revenue": collected_total / billed_patients if billed_patients else 0,
        "returning_rate": percent(returning, len(visits)),
    }

    # ---------- Chart 1: appointments over the last 30 days ----------
    start = today - timedelta(days=29)
    days = [start + timedelta(days=i) for i in range(30)]
    per_day = dict(db.session.query(Appointment.date, func.count(Appointment.id))
                   .filter(Appointment.date >= start, Appointment.date <= today)
                   .group_by(Appointment.date).all())
    completed_per_day = dict(db.session.query(Appointment.date, func.count(Appointment.id))
                             .filter(Appointment.date >= start, Appointment.date <= today,
                                     Appointment.status == "completed")
                             .group_by(Appointment.date).all())

    # ---------- Chart 2: status breakdown ----------
    status_counts = dict(db.session.query(Appointment.status, func.count(Appointment.id))
                         .group_by(Appointment.status).all())

    # ---------- Chart 3: revenue for the last 6 months ----------
    months = last_n_months(6, today)
    first_month = datetime(months[0][0], months[0][1], 1)
    billed_by_month = {m: 0 for m in months}
    collected_by_month = {m: 0 for m in months}
    for bill in Bill.query.filter(Bill.created_at >= first_month).all():
        key = (bill.created_at.year, bill.created_at.month)
        if key in billed_by_month:
            billed_by_month[key] += bill.amount
            collected_by_month[key] += bill.paid_amount

    # ---------- Chart 4: busiest departments ----------
    by_specialty = (db.session.query(Doctor.specialty, func.count(Appointment.id))
                    .join(Appointment, Appointment.doctor_id == Doctor.id)
                    .group_by(Doctor.specialty)
                    .order_by(func.count(Appointment.id).desc()).all())

    # ---------- Chart 5: patients by age group + gender ----------
    ages = {label: {"Male": 0, "Female": 0} for label, _, _ in AGE_GROUPS}
    for patient in Patient.query.all():
        for label, low, high in AGE_GROUPS:
            if low <= patient.age <= high:
                ages[label][patient.gender] = ages[label].get(patient.gender, 0) + 1
                break

    chart_data = {
        "trend": {
            "labels": [d.strftime("%d %b") for d in days],
            "total": [per_day.get(d, 0) for d in days],
            "completed": [completed_per_day.get(d, 0) for d in days],
        },
        "status": {
            "keys": APPOINTMENT_STATUSES,
            "labels": [STATUS_LABELS[s] for s in APPOINTMENT_STATUSES],
            "values": [status_counts.get(s, 0) for s in APPOINTMENT_STATUSES],
        },
        "revenue": {
            "labels": [datetime(y, m, 1).strftime("%b %Y") for y, m in months],
            "billed": [round(billed_by_month[m]) for m in months],
            "collected": [round(collected_by_month[m]) for m in months],
        },
        "specialty": {
            "labels": [s for s, _ in by_specialty],
            "values": [c for _, c in by_specialty],
        },
        "ages": {
            "labels": [label for label, _, _ in AGE_GROUPS],
            "male": [ages[label]["Male"] for label, _, _ in AGE_GROUPS],
            "female": [ages[label]["Female"] for label, _, _ in AGE_GROUPS],
        },
    }

    # ---------- Tables ----------
    pending_bills = (Bill.query.filter(Bill.status != "paid")
                     .order_by((Bill.amount - Bill.paid_amount).desc()).limit(5).all())
    recent_patients = Patient.query.order_by(Patient.created_at.desc()).limit(5).all()

    completed_by_doctor = dict(db.session.query(Appointment.doctor_id, func.count(Appointment.id))
                               .filter(Appointment.status == "completed")
                               .group_by(Appointment.doctor_id).all())
    revenue_by_doctor = dict(db.session.query(Appointment.doctor_id, func.sum(Bill.paid_amount))
                             .join(Bill, Bill.appointment_id == Appointment.id)
                             .group_by(Appointment.doctor_id).all())
    top_doctors = sorted(Doctor.query.all(), key=lambda d: completed_by_doctor.get(d.id, 0), reverse=True)[:5]
    top_doctors = [
        {"doctor": d, "visits": completed_by_doctor.get(d.id, 0), "revenue": revenue_by_doctor.get(d.id, 0) or 0}
        for d in top_doctors
    ]

    hour = now.hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"

    return render_template(
        "dashboard.html",
        kpis=kpis,
        chart_data=chart_data,
        todays=todays,
        pending_bills=pending_bills,
        recent_patients=recent_patients,
        top_doctors=top_doctors,
        greeting=greeting,
    )

# ================= PATIENTS =================
PATIENT_FIELDS = ["name", "gender", "date_of_birth", "phone", "email", "address", "blood_type"]


def read_patient_form(form):
    """Read and check the patient form. Returns (data, date_of_birth, errors)."""
    data = {field: form.get(field, "").strip() for field in PATIENT_FIELDS}
    errors = []
    dob = None

    if data["name"].islower():
        data["name"] = data["name"].title()  # "tom cruise" → "Tom Cruise"

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

# ================= APPOINTMENTS =================
TIME_SLOTS = [dtime(h, m) for h in range(9, 17) for m in (0, 30)]  # 09:00 → 16:30
CLOSED_WEEKDAY = 4  # Friday


def booked_times(doctor_id, day, exclude_id=None):
    """Times already taken for a doctor on a day (cancelled ones don't count)."""
    query = db.session.query(Appointment.time).filter(
        Appointment.doctor_id == doctor_id,
        Appointment.date == day,
        Appointment.status != "cancelled",
    )
    if exclude_id:
        query = query.filter(Appointment.id != exclude_id)
    return {t for (t,) in query.all()}


def read_appointment_form(form, exclude_id=None):
    """Read and check the booking form.
    Returns (data, patient, doctor, day, slot, errors)."""
    fields = ["patient_id", "doctor_id", "date", "time", "reason", "notes"]
    data = {field: form.get(field, "").strip() for field in fields}
    errors = []
    patient = doctor = day = slot = None
    today = date.today()

    if data["patient_id"].isdigit():
        patient = db.session.get(Patient, int(data["patient_id"]))
    if not patient:
        errors.append("Please choose a patient.")

    if data["doctor_id"].isdigit():
        doctor = db.session.get(Doctor, int(data["doctor_id"]))
    if not doctor:
        errors.append("Please choose a doctor.")
    elif doctor.status != "active":
        errors.append(f"{doctor.name} is off and not taking appointments.")

    try:
        day = datetime.strptime(data["date"], "%Y-%m-%d").date()
        if day < today:
            errors.append("You can't book an appointment in the past.")
        elif day.weekday() == CLOSED_WEEKDAY:
            errors.append("The clinic is closed on Fridays.")
    except ValueError:
        errors.append("Please choose a valid date.")

    try:
        slot = datetime.strptime(data["time"], "%H:%M").time()
        if slot not in TIME_SLOTS:
            errors.append("Please choose a valid time slot.")
        elif day == today and slot <= datetime.now().time():
            errors.append("That time has already passed today.")
    except ValueError:
        errors.append("Please choose a time.")

    if len(data["reason"]) > 200:
        errors.append("Reason is too long (max 200 characters).")

    # Double-booking checks (only if everything else is valid)
    if not errors:
        if slot in booked_times(doctor.id, day, exclude_id):
            errors.append(f"{doctor.name} is already booked at {slot.strftime('%I:%M %p')} on {day.strftime('%d %b')}.")

        clash = Appointment.query.filter(
            Appointment.patient_id == patient.id,
            Appointment.date == day,
            Appointment.time == slot,
            Appointment.status != "cancelled",
        )
        if exclude_id:
            clash = clash.filter(Appointment.id != exclude_id)
        if clash.first():
            errors.append(f"{patient.name} already has another appointment at that time.")

    return data, patient, doctor, day, slot, errors


def appointment_choices(current_doctor=None):
    """Patients and doctors for the booking form."""
    doctors = Doctor.query.filter_by(status="active").order_by(Doctor.name).all()
    if current_doctor and current_doctor not in doctors:
        doctors.append(current_doctor)  # keep the current doctor visible when editing
    return {
        "patients": Patient.query.order_by(Patient.name).all(),
        "doctors": doctors,
    }


@app.route("/appointments")
@login_required
def appointments_list():
    view = request.args.get("view", "upcoming")
    q = request.args.get("q", "").strip()
    doctor_id = request.args.get("doctor_id", type=int)
    status = request.args.get("status", "")
    day_str = request.args.get("date", "")
    page = request.args.get("page", 1, type=int)
    today = date.today()

    query = Appointment.query.join(Patient)

    selected_day = None
    if day_str:
        try:
            selected_day = datetime.strptime(day_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    ascending = True
    if selected_day:
        query = query.filter(Appointment.date == selected_day)
    elif view == "today":
        query = query.filter(Appointment.date == today)
    elif view == "past":
        query = query.filter(Appointment.date < today)
        ascending = False
    elif view == "all":
        ascending = False
    else:
        view = "upcoming"
        query = query.filter(Appointment.date >= today)

    if q:
        query = query.filter(Patient.name.ilike(f"%{q}%"))
    if doctor_id:
        query = query.filter(Appointment.doctor_id == doctor_id)
    if status in APPOINTMENT_STATUSES:
        query = query.filter(Appointment.status == status)

    if ascending:
        query = query.order_by(Appointment.date.asc(), Appointment.time.asc())
    else:
        query = query.order_by(Appointment.date.desc(), Appointment.time.desc())

    pager = query.paginate(page=page, per_page=12, error_out=False)

    tab_counts = {
        "today": Appointment.query.filter(Appointment.date == today).count(),
        "upcoming": Appointment.query.filter(Appointment.date >= today).count(),
        "past": Appointment.query.filter(Appointment.date < today).count(),
        "all": Appointment.query.count(),
    }

    return render_template(
        "appointments/list.html",
        pager=pager,
        view=view,
        q=q,
        doctor_id=doctor_id,
        status=status,
        selected_day=selected_day,
        tab_counts=tab_counts,
        doctors=Doctor.query.order_by(Doctor.name).all(),
        statuses=APPOINTMENT_STATUSES,
    )


@app.route("/appointments/new", methods=["GET", "POST"])
@login_required
def appointment_new():
    # Pre-fill patient/doctor when coming from a profile page
    form = {
        "patient_id": request.args.get("patient_id", ""),
        "doctor_id": request.args.get("doctor_id", ""),
    }

    if request.method == "POST":
        form, patient, doctor, day, slot, errors = read_appointment_form(request.form)
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            appointment = Appointment(
                patient_id=patient.id,
                doctor_id=doctor.id,
                date=day,
                time=slot,
                reason=form["reason"] or None,
                notes=form["notes"] or None,
                status="scheduled",
            )
            db.session.add(appointment)
            db.session.commit()
            flash(
                f"Appointment booked for {patient.name} with {doctor.name} on "
                f"{day.strftime('%d %b')} at {slot.strftime('%I:%M %p')}. ✅",
                "success",
            )
            return redirect(url_for("appointment_view", appointment_id=appointment.id))

    return render_template("appointments/form.html", form=form, appointment=None, **appointment_choices())


@app.route("/appointments/<int:appointment_id>")
@login_required
def appointment_view(appointment_id):
    appointment = db.get_or_404(Appointment, appointment_id)
    return render_template("appointments/view.html", a=appointment)


@app.route("/appointments/<int:appointment_id>/edit", methods=["GET", "POST"])
@login_required
def appointment_edit(appointment_id):
    appointment = db.get_or_404(Appointment, appointment_id)

    if appointment.status != "scheduled":
        flash("Only scheduled appointments can be rescheduled.", "warning")
        return redirect(url_for("appointment_view", appointment_id=appointment.id))

    if request.method == "POST":
        form, patient, doctor, day, slot, errors = read_appointment_form(request.form, exclude_id=appointment.id)
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            appointment.patient_id = patient.id
            appointment.doctor_id = doctor.id
            appointment.date = day
            appointment.time = slot
            appointment.reason = form["reason"] or None
            appointment.notes = form["notes"] or None
            db.session.commit()
            flash("Appointment updated. ✅", "success")
            return redirect(url_for("appointment_view", appointment_id=appointment.id))
    else:
        form = {
            "patient_id": str(appointment.patient_id),
            "doctor_id": str(appointment.doctor_id),
            "date": appointment.date.isoformat(),
            "time": appointment.time.strftime("%H:%M"),
            "reason": appointment.reason or "",
            "notes": appointment.notes or "",
        }

    return render_template(
        "appointments/form.html",
        form=form,
        appointment=appointment,
        **appointment_choices(current_doctor=appointment.doctor),
    )


@app.route("/appointments/<int:appointment_id>/status", methods=["POST"])
@login_required
def appointment_status(appointment_id):
    appointment = db.get_or_404(Appointment, appointment_id)
    new_status = request.form.get("status", "")

    messages = {
        "completed": "Appointment marked as completed. ✅",
        "cancelled": "Appointment cancelled.",
        "no_show": "Appointment marked as no-show.",
        "scheduled": "Appointment set back to scheduled.",
    }

    if new_status not in APPOINTMENT_STATUSES:
        flash("Unknown status.", "error")
    elif new_status in ("completed", "no_show") and appointment.date > date.today():
        flash("You can't complete or mark a future appointment as no-show.", "warning")
    else:
        appointment.status = new_status
        db.session.commit()
        flash(messages[new_status], "success" if new_status == "completed" else "info")

    next_url = request.form.get("next")
    return redirect(next_url if is_safe_next(next_url) else url_for("appointment_view", appointment_id=appointment.id))


@app.route("/api/available-slots")
@login_required
def api_available_slots():
    """Used by the booking form to show free and booked times."""
    doctor_id = request.args.get("doctor_id", type=int)
    exclude_id = request.args.get("exclude", type=int)
    today = date.today()

    try:
        day = datetime.strptime(request.args.get("date", ""), "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"slots": [], "message": "Choose a date."})

    if not doctor_id:
        return jsonify({"slots": [], "message": "Choose a doctor."})
    if day < today:
        return jsonify({"slots": [], "message": "That date is in the past."})
    if day.weekday() == CLOSED_WEEKDAY:
        return jsonify({"slots": [], "message": "The clinic is closed on Fridays."})

    taken = booked_times(doctor_id, day, exclude_id)
    now = datetime.now().time()

    slots = [
        {
            "value": t.strftime("%H:%M"),
            "label": t.strftime("%I:%M %p"),
            "available": t not in taken and not (day == today and t <= now),
        }
        for t in TIME_SLOTS
    ]
    free = sum(1 for s in slots if s["available"])
    message = f"{free} of {len(slots)} slots available." if free else "No free slots on this day. Try another date."
    return jsonify({"slots": slots, "message": message})

# ================= BILLING =================
def parse_money(value):
    """Turn form text into a number, or None if it isn't one."""
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


@app.route("/billing")
@login_required
def bills_list():
    status = request.args.get("status", "")
    q = request.args.get("q", "").strip()
    method = request.args.get("method", "")
    page = request.args.get("page", 1, type=int)

    query = Bill.query.join(Patient)
    if status in ("paid", "partial", "unpaid"):
        query = query.filter(Bill.status == status)
    if q:
        query = query.filter(Patient.name.ilike(f"%{q}%"))
    if method in PAYMENT_METHODS:
        query = query.filter(Bill.payment_method == method)

    pager = query.order_by(Bill.created_at.desc()).paginate(page=page, per_page=12, error_out=False)

    # Summary numbers (all bills)
    billed, collected = db.session.query(
        func.coalesce(func.sum(Bill.amount), 0),
        func.coalesce(func.sum(Bill.paid_amount), 0),
    ).one()
    summary = {
        "billed": billed,
        "collected": collected,
        "outstanding": billed - collected,
        "rate": round(collected / billed * 100, 1) if billed else 0,
    }

    status_counts = dict(db.session.query(Bill.status, func.count(Bill.id)).group_by(Bill.status).all())
    status_counts["all"] = sum(status_counts.values())

    # Completed appointments that don't have a bill yet
    unbilled_query = Appointment.query.filter(
        Appointment.status == "completed",
        ~Appointment.bill.has(),
    ).order_by(Appointment.date.desc(), Appointment.time.desc())

    return render_template(
        "billing/list.html",
        pager=pager,
        status=status, q=q, method=method,
        summary=summary,
        status_counts=status_counts,
        unbilled=unbilled_query.limit(5).all(),
        unbilled_count=unbilled_query.count(),
        methods=PAYMENT_METHODS,
    )


@app.route("/billing/new", methods=["GET", "POST"])
@login_required
def bill_new():
    appointment_id = request.values.get("appointment_id", type=int)
    appointment = db.session.get(Appointment, appointment_id) if appointment_id else None

    if not appointment:
        flash("Choose a completed appointment to bill.", "warning")
        return redirect(url_for("bills_list"))
    if appointment.bill:
        flash("This appointment already has a bill.", "info")
        return redirect(url_for("bill_view", bill_id=appointment.bill.id))
    if appointment.status != "completed":
        flash("Only completed appointments can be billed.", "warning")
        return redirect(url_for("appointment_view", appointment_id=appointment.id))

    fee = appointment.doctor.consultation_fee
    form = {"amount": f"{fee:g}", "paid_now": "0", "payment_method": ""}

    if request.method == "POST":
        form = {key: request.form.get(key, "").strip() for key in ("amount", "paid_now", "payment_method")}
        amount = parse_money(form["amount"])
        paid = parse_money(form["paid_now"] or "0")

        errors = []
        if amount is None or amount <= 0 or amount > 1_000_000:
            errors.append("Please enter a valid bill amount.")
        if paid is None or paid < 0:
            errors.append("Please enter a valid payment amount.")
        elif amount and paid > amount:
            errors.append("The payment can't be more than the bill amount.")
        if paid and paid > 0 and form["payment_method"] not in PAYMENT_METHODS:
            errors.append("Please choose a payment method.")

        if errors:
            for error in errors:
                flash(error, "error")
        else:
            bill = Bill(
                patient_id=appointment.patient_id,
                appointment_id=appointment.id,
                amount=amount,
                paid_amount=paid,
                payment_method=form["payment_method"] if paid > 0 else None,
            )
            bill.update_status()
            db.session.add(bill)
            db.session.commit()
            flash(f"Bill #{bill.id} created for {appointment.patient.name}. 🧾", "success")
            return redirect(url_for("bill_view", bill_id=bill.id))

    return render_template("billing/form.html", a=appointment, form=form, fee=fee, methods=PAYMENT_METHODS)


@app.route("/billing/<int:bill_id>")
@login_required
def bill_view(bill_id):
    bill = db.get_or_404(Bill, bill_id)
    appointment = bill.appointment

    # Split the total into consultation + extra services for the invoice
    fee = appointment.doctor.consultation_fee if appointment else bill.amount
    consultation = min(fee, bill.amount)
    extras = round(bill.amount - consultation, 2)

    return render_template("billing/invoice.html", b=bill, a=appointment,
                           consultation=consultation, extras=extras, methods=PAYMENT_METHODS)


@app.route("/billing/<int:bill_id>/pay", methods=["POST"])
@login_required
def bill_payment(bill_id):
    bill = db.get_or_404(Bill, bill_id)
    amount = parse_money(request.form.get("amount"))
    method = request.form.get("payment_method", "")

    if bill.balance <= 0:
        flash("This bill is already fully paid.", "info")
    elif amount is None or amount <= 0:
        flash("Please enter a valid payment amount.", "error")
    elif amount > bill.balance + 0.01:
        flash(f"The payment can't be more than the balance ({bill.balance:,.0f} EGP).", "error")
    elif method not in PAYMENT_METHODS:
        flash("Please choose a payment method.", "error")
    else:
        bill.paid_amount = round(bill.paid_amount + amount, 2)
        bill.payment_method = method
        bill.update_status()
        db.session.commit()
        if bill.status == "paid":
            flash(f"Payment of {amount:,.0f} EGP recorded. The bill is fully paid. 🎉", "success")
        else:
            flash(f"Payment of {amount:,.0f} EGP recorded. Remaining: {bill.balance:,.0f} EGP.", "success")

    return redirect(url_for("bill_view", bill_id=bill.id))

# ================= PRESCRIPTIONS =================
MEDICINE_SUGGESTIONS = [
    "Paracetamol 500mg", "Ibuprofen 400mg", "Amoxicillin 500mg", "Azithromycin 250mg",
    "Omeprazole 20mg", "Cetirizine 10mg", "Vitamin D3 1000 IU", "Metformin 500mg",
    "Amlodipine 5mg", "Salbutamol inhaler", "Saline nasal spray", "Loratadine 10mg",
]
FREQUENCY_SUGGESTIONS = [
    "Once daily", "Twice daily", "Three times daily", "Every 8 hours",
    "Once daily at night", "Twice daily after meals", "When needed",
]


def read_prescription_form(form):
    """Read the diagnosis + all medicine rows. Returns (data, errors)."""
    data = {
        "diagnosis": form.get("diagnosis", "").strip(),
        "notes": form.get("notes", "").strip(),
        "items": [],
    }
    errors = []

    rows = zip(
        form.getlist("medicine"),
        form.getlist("dosage"),
        form.getlist("frequency"),
        form.getlist("duration"),
    )
    for medicine, dosage, frequency, duration in rows:
        item = {
            "medicine": medicine.strip(),
            "dosage": dosage.strip(),
            "frequency": frequency.strip(),
            "duration": duration.strip(),
        }
        if not any(item.values()):
            continue  # skip completely empty rows
        if not item["medicine"]:
            errors.append("Each medicine row needs a medicine name.")
        elif len(item["medicine"]) > 100 or any(len(item[k]) > 50 for k in ("dosage", "frequency", "duration")):
            errors.append(f"Some details for {item['medicine']} are too long.")
        data["items"].append(item)

    if not data["diagnosis"]:
        errors.append("Diagnosis is required.")
    elif len(data["diagnosis"]) > 200:
        errors.append("Diagnosis is too long (max 200 characters).")

    if not data["items"]:
        errors.append("Add at least one medicine.")

    return data, list(dict.fromkeys(errors))  # remove repeated messages


def prescription_form_context():
    return {"medicine_suggestions": MEDICINE_SUGGESTIONS, "frequency_suggestions": FREQUENCY_SUGGESTIONS}


@app.route("/prescriptions")
@login_required
def prescriptions_list():
    q = request.args.get("q", "").strip()
    doctor_id = request.args.get("doctor_id", type=int)
    page = request.args.get("page", 1, type=int)

    query = Prescription.query.join(Patient)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(
            Patient.name.ilike(like),
            Prescription.diagnosis.ilike(like),
            Prescription.items.any(PrescriptionItem.medicine.ilike(like)),
        ))
    if doctor_id:
        query = query.filter(Prescription.doctor_id == doctor_id)

    pager = query.order_by(Prescription.created_at.desc()).paginate(page=page, per_page=12, error_out=False)

    # Recent completed visits that don't have a prescription yet
    pending_query = Appointment.query.filter(
        Appointment.status == "completed",
        ~Appointment.prescription.has(),
    ).order_by(Appointment.date.desc(), Appointment.time.desc())

    return render_template(
        "prescriptions/list.html",
        pager=pager,
        q=q,
        doctor_id=doctor_id,
        doctors=Doctor.query.order_by(Doctor.name).all(),
        pending=pending_query.limit(5).all(),
        pending_count=pending_query.count(),
    )


@app.route("/prescriptions/new", methods=["GET", "POST"])
@login_required
def prescription_new():
    appointment_id = request.values.get("appointment_id", type=int)
    appointment = db.session.get(Appointment, appointment_id) if appointment_id else None

    if not appointment:
        flash("Choose a completed appointment to write a prescription for.", "warning")
        return redirect(url_for("prescriptions_list"))
    if appointment.prescription:
        flash("This appointment already has a prescription.", "info")
        return redirect(url_for("prescription_view", prescription_id=appointment.prescription.id))
    if appointment.status != "completed":
        flash("Prescriptions can only be written for completed appointments.", "warning")
        return redirect(url_for("appointment_view", appointment_id=appointment.id))

    form = {"diagnosis": "", "notes": "", "items": []}

    if request.method == "POST":
        form, errors = read_prescription_form(request.form)
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            prescription = Prescription(
                appointment_id=appointment.id,
                patient_id=appointment.patient_id,
                doctor_id=appointment.doctor_id,
                diagnosis=form["diagnosis"],
                notes=form["notes"] or None,
            )
            for item in form["items"]:
                prescription.items.append(PrescriptionItem(**item))
            db.session.add(prescription)
            db.session.commit()
            flash(f"Prescription saved for {appointment.patient.name}. 💊", "success")
            return redirect(url_for("prescription_view", prescription_id=prescription.id))

    return render_template("prescriptions/form.html", form=form, a=appointment, prescription=None,
                           **prescription_form_context())


@app.route("/prescriptions/<int:prescription_id>")
@login_required
def prescription_view(prescription_id):
    prescription = db.get_or_404(Prescription, prescription_id)
    return render_template("prescriptions/view.html", rx=prescription)


@app.route("/prescriptions/<int:prescription_id>/edit", methods=["GET", "POST"])
@login_required
def prescription_edit(prescription_id):
    prescription = db.get_or_404(Prescription, prescription_id)

    if request.method == "POST":
        form, errors = read_prescription_form(request.form)
        if errors:
            for error in errors:
                flash(error, "error")
        else:
            prescription.diagnosis = form["diagnosis"]
            prescription.notes = form["notes"] or None
            prescription.items.clear()  # old rows are deleted automatically
            for item in form["items"]:
                prescription.items.append(PrescriptionItem(**item))
            db.session.commit()
            flash("Prescription updated. ✅", "success")
            return redirect(url_for("prescription_view", prescription_id=prescription.id))
    else:
        form = {
            "diagnosis": prescription.diagnosis,
            "notes": prescription.notes or "",
            "items": [
                {"medicine": i.medicine, "dosage": i.dosage or "", "frequency": i.frequency or "", "duration": i.duration or ""}
                for i in prescription.items
            ],
        }

    return render_template("prescriptions/form.html", form=form, a=prescription.appointment,
                           prescription=prescription, **prescription_form_context())


@app.route("/prescriptions/<int:prescription_id>/delete", methods=["POST"])
@login_required
def prescription_delete(prescription_id):
    prescription = db.get_or_404(Prescription, prescription_id)
    patient_id = prescription.patient_id
    db.session.delete(prescription)  # its medicine rows are deleted too
    db.session.commit()
    flash("Prescription deleted.", "info")
    return redirect(url_for("patient_view", patient_id=patient_id))

# ================= GLOBAL SEARCH =================
SEARCH_LIMIT = 6  # results shown per section


@app.route("/search")
@login_required
def search():
    q = request.args.get("q", "").strip()
    sections = []

    if len(q) >= 2:
        like = f"%{q}%"
        id_match = re.fullmatch(r"#?(\d+)", q)
        number = int(id_match.group(1)) if id_match else None

        # Patients
        patients = Patient.query.filter(or_(
            Patient.name.ilike(like), Patient.phone.ilike(like), Patient.email.ilike(like),
        )).order_by(Patient.name)

        # Doctors
        doctors = Doctor.query.filter(or_(
            Doctor.name.ilike(like), Doctor.specialty.ilike(like), Doctor.email.ilike(like),
        )).order_by(Doctor.name)

        # Appointments
        appt_conditions = [Patient.name.ilike(like), Doctor.name.ilike(like), Appointment.reason.ilike(like)]
        if number:
            appt_conditions.append(Appointment.id == number)
        appointments = (Appointment.query
                        .join(Patient, Appointment.patient_id == Patient.id)
                        .join(Doctor, Appointment.doctor_id == Doctor.id)
                        .filter(or_(*appt_conditions))
                        .order_by(Appointment.date.desc(), Appointment.time.desc()))

        # Prescriptions
        rx_conditions = [
            Patient.name.ilike(like),
            Prescription.diagnosis.ilike(like),
            Prescription.items.any(PrescriptionItem.medicine.ilike(like)),
        ]
        if number:
            rx_conditions.append(Prescription.id == number)
        prescriptions = (Prescription.query.join(Patient)
                         .filter(or_(*rx_conditions))
                         .order_by(Prescription.created_at.desc()))

        # Bills
        bill_conditions = [Patient.name.ilike(like)]
        if number:
            bill_conditions.append(Bill.id == number)
        bills = Bill.query.join(Patient).filter(or_(*bill_conditions)).order_by(Bill.created_at.desc())

        for key, title, icon, query, see_all in [
            ("patients", "Patients", "👥", patients, url_for("patients_list", q=q)),
            ("doctors", "Doctors", "🩺", doctors, url_for("doctors_list", q=q)),
            ("appointments", "Appointments", "📅", appointments, url_for("appointments_list", view="all", q=q)),
            ("prescriptions", "Prescriptions", "💊", prescriptions, url_for("prescriptions_list", q=q)),
            ("bills", "Bills", "💰", bills, url_for("bills_list", q=q)),
        ]:
            count = query.count()
            if count:
                sections.append({
                    "key": key, "title": title, "icon": icon, "count": count,
                    "items": query.limit(SEARCH_LIMIT).all(), "see_all": see_all,
                })

    total = sum(s["count"] for s in sections)
    return render_template("search.html", q=q, sections=sections, total=total)

# ================= ERROR PAGES =================
@app.errorhandler(404)
def not_found(error):
    return render_template(
        "error.html", code=404, icon="🧭", title="Page not found",
        message="The page you're looking for doesn't exist or was moved.",
    ), 404


@app.errorhandler(500)
def server_error(error):
    db.session.rollback()  # undo any half-finished database change
    return render_template(
        "error.html", code=500, icon="🩹", title="Something went wrong",
        message="An unexpected error happened on our side. Please try again.",
    ), 500

if __name__ == "__main__":
    app.run(debug=True)