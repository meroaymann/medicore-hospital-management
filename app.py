import os
import re
from datetime import date

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv

from models import db, User, Patient, Doctor, Appointment, Bill, Prescription

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


@app.context_processor
def inject_globals():
    """Variables available in every template."""
    return {"app_name": APP_NAME, "today": date.today()}


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


if __name__ == "__main__":
    app.run(debug=True)