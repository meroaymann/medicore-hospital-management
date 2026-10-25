"""Fill the database with realistic sample data.
Run:  python seed.py
⚠️ This DELETES all existing data first.
"""
import random
from datetime import date, datetime, time, timedelta

from app import app
from models import (
    db, User, Patient, Doctor, Appointment, Bill, Prescription, PrescriptionItem,
)

random.seed(42)  # same data every time you run it
TODAY = date.today()

MALE_NAMES = ["Ahmed", "Mohamed", "Omar", "Youssef", "Karim", "Mahmoud", "Ali", "Hassan",
              "Mostafa", "Khaled", "Tarek", "Amr", "Ziad", "Adam", "Hamza"]
FEMALE_NAMES = ["Mariam", "Nour", "Salma", "Hana", "Farida", "Malak", "Laila", "Yasmin",
                "Aya", "Rana", "Dina", "Habiba", "Jana", "Mona", "Sara"]
LAST_NAMES = ["Hassan", "Ibrahim", "Mostafa", "Adel", "Nabil", "Samir", "Fathy", "Tarek",
              "Mahmoud", "Ashraf", "Saeed", "Gamal", "Fawzy", "Kamal", "Hosny", "Salem", "Ezzat"]
AREAS = ["Nasr City", "Heliopolis", "Maadi", "Zamalek", "Dokki", "Mohandessin",
         "New Cairo", "6th of October", "Sheikh Zayed", "Shoubra"]
BLOOD_TYPES = ["O+", "A+", "B+", "AB+", "O-", "A-", "B-", "AB-"]
BLOOD_WEIGHTS = [35, 30, 18, 6, 5, 3, 2, 1]

DOCTORS = [
    ("Dr. Ahmed Hassan", "Cardiology", 600),
    ("Dr. Mona Ibrahim", "Pediatrics", 400),
    ("Dr. Karim Mostafa", "Orthopedics", 500),
    ("Dr. Sara Adel", "Dermatology", 450),
    ("Dr. Youssef Nabil", "Neurology", 700),
    ("Dr. Nour Samir", "General Medicine", 300),
    ("Dr. Hana Fathy", "Gynecology", 550),
    ("Dr. Omar Tarek", "ENT", 400),
    ("Dr. Laila Mahmoud", "Ophthalmology", 450),
    ("Dr. Tamer Ashraf", "Dentistry", 350),
]

REASONS = ["Routine check-up", "Follow-up visit", "Chest pain", "Fever and cough", "Back pain",
           "Skin rash", "Headache", "Blood pressure check", "Vaccination", "Eye examination",
           "Ear pain", "Toothache", "Pregnancy follow-up", "Joint pain"]

DIAGNOSES = {
    "Cardiology": ["Hypertension", "Arrhythmia", "Stable angina"],
    "Pediatrics": ["Common cold", "Tonsillitis", "Gastroenteritis"],
    "Orthopedics": ["Lower back strain", "Knee osteoarthritis", "Ankle sprain"],
    "Dermatology": ["Eczema", "Acne", "Contact dermatitis"],
    "Neurology": ["Migraine", "Tension headache", "Peripheral neuropathy"],
    "General Medicine": ["Upper respiratory infection", "Type 2 diabetes", "Vitamin D deficiency"],
    "Gynecology": ["Routine pregnancy follow-up", "Anemia", "Urinary tract infection"],
    "ENT": ["Sinusitis", "Otitis media", "Allergic rhinitis"],
    "Ophthalmology": ["Conjunctivitis", "Dry eye syndrome", "Myopia"],
    "Dentistry": ["Dental caries", "Gingivitis", "Tooth sensitivity"],
}

MEDICINES = [
    ("Paracetamol 500mg", "1 tablet", "Every 8 hours", "5 days"),
    ("Ibuprofen 400mg", "1 tablet", "Twice daily after meals", "5 days"),
    ("Amoxicillin 500mg", "1 capsule", "Every 8 hours", "7 days"),
    ("Omeprazole 20mg", "1 capsule", "Once daily before breakfast", "14 days"),
    ("Cetirizine 10mg", "1 tablet", "Once daily at night", "10 days"),
    ("Vitamin D3 1000 IU", "1 tablet", "Once daily", "30 days"),
    ("Metformin 500mg", "1 tablet", "Twice daily with meals", "30 days"),
    ("Amlodipine 5mg", "1 tablet", "Once daily", "30 days"),
    ("Azithromycin 250mg", "1 tablet", "Once daily", "3 days"),
    ("Saline nasal spray", "2 sprays", "Three times daily", "7 days"),
]

TIME_SLOTS = [time(h, m) for h in range(9, 17) for m in (0, 30)]  # 9:00 → 16:30


def random_phone():
    return "01" + random.choice("0125") + "".join(random.choices("0123456789", k=8))


def random_datetime(day):
    return datetime.combine(day, time(random.randint(8, 20), random.randint(0, 59)))


with app.app_context():
    print("🗑️  Clearing old data...")
    db.drop_all()
    db.create_all()

    # ---------- Demo admin account ----------
    admin = User(name="Admin", email="admin@demo.com", role="admin")
    admin.set_password("admin1234")
    db.session.add(admin)

    # ---------- Doctors ----------
    doctors = []
    for i, (name, specialty, fee) in enumerate(DOCTORS):
        first = name.split()[1].lower()
        doctor = Doctor(
            name=name,
            specialty=specialty,
            phone=random_phone(),
            email=f"{first}.{specialty.split()[0].lower()}@hospital.com",
            consultation_fee=fee,
            status="off" if i == 9 else "active",  # one doctor is off
            created_at=random_datetime(TODAY - timedelta(days=random.randint(200, 400))),
        )
        doctors.append(doctor)
    db.session.add_all(doctors)

    # ---------- Patients ----------
    patients = []
    for i in range(60):
        gender = random.choice(["Male", "Female"])
        first = random.choice(MALE_NAMES if gender == "Male" else FEMALE_NAMES)
        last = random.choice(LAST_NAMES)
        age = random.randint(1, 85)
        patient = Patient(
            name=f"{first} {last}",
            gender=gender,
            date_of_birth=TODAY - timedelta(days=age * 365 + random.randint(0, 364)),
            phone=random_phone(),
            email=f"{first.lower()}.{last.lower()}{i}@example.com",
            address=f"{random.randint(1, 120)} Street, {random.choice(AREAS)}, Cairo",
            blood_type=random.choices(BLOOD_TYPES, weights=BLOOD_WEIGHTS)[0],
            created_at=random_datetime(TODAY - timedelta(days=random.randint(0, 180))),
        )
        patients.append(patient)
    db.session.add_all(patients)
    db.session.commit()  # gives everyone an id

    # ---------- Appointments (no double-booking) ----------
    active_doctors = [d for d in doctors if d.status == "active"]
    booked = set()
    appointments = []
    current_time = datetime.now().time()
    attempts = 0

    while len(appointments) < 500 and attempts < 20000:
        attempts += 1
        day = TODAY + timedelta(days=random.randint(-150, 14))
        if day.weekday() == 4:  # Friday = day off
            continue

        doctor = random.choice(active_doctors)
        slot = random.choice(TIME_SLOTS)
        if (doctor.id, day, slot) in booked:
            continue

        eligible = [p for p in patients if p.created_at.date() <= day]
        if not eligible:
            continue
        patient = random.choice(eligible)

        if day < TODAY:
            status = random.choices(["completed", "cancelled", "no_show"], weights=[78, 12, 10])[0]
        elif day == TODAY:
            status = "completed" if slot < current_time else "scheduled"
        else:
            status = random.choices(["scheduled", "cancelled"], weights=[93, 7])[0]

        booked_on = max(day - timedelta(days=random.randint(1, 14)), patient.created_at.date())

        appointment = Appointment(
            patient=patient,
            doctor=doctor,
            date=day,
            time=slot,
            reason=random.choice(REASONS),
            status=status,
            created_at=random_datetime(booked_on),
        )
        booked.add((doctor.id, day, slot))
        appointments.append(appointment)

    db.session.add_all(appointments)
    db.session.commit()

        # ---------- Bills + prescriptions for completed appointments ----------
    bill_count, prescription_count = 0, 0

    for appt in appointments:
        if appt.status != "completed":
            continue

        doctor = appt.doctor

        # Bill (linked by id numbers → no warnings)
        amount = doctor.consultation_fee + random.choice([0, 0, 150, 300, 500])
        roll = random.random()
        if roll < 0.70:
            paid = amount
        elif roll < 0.85:
            paid = round(amount * random.choice([0.3, 0.5, 0.7]))
        else:
            paid = 0

        bill = Bill(
            patient_id=appt.patient_id,
            appointment_id=appt.id,
            amount=amount,
            paid_amount=paid,
            payment_method=random.choice(["Cash", "Card", "Insurance"]) if paid > 0 else None,
            created_at=datetime.combine(appt.date, appt.time),
        )
        bill.update_status()
        db.session.add(bill)
        bill_count += 1

        # Prescription (about 60% of visits)
        if random.random() < 0.6:
            prescription = Prescription(
                appointment_id=appt.id,
                patient_id=appt.patient_id,
                doctor_id=appt.doctor_id,
                diagnosis=random.choice(DIAGNOSES[doctor.specialty]),
                notes=random.choice(["Drink plenty of water.", "Rest for 2 days.",
                                     "Come back if symptoms continue.", None]),
                created_at=datetime.combine(appt.date, appt.time),
            )
            for med in random.sample(MEDICINES, k=random.randint(1, 3)):
                prescription.items.append(PrescriptionItem(
                    medicine=med[0], dosage=med[1], frequency=med[2], duration=med[3],
                ))
            db.session.add(prescription)
            prescription_count += 1

    db.session.commit()

    print("✅ Done!")
    print(f"   Users:         {User.query.count()}")
    print(f"   Doctors:       {Doctor.query.count()}")
    print(f"   Patients:      {Patient.query.count()}")
    print(f"   Appointments:  {Appointment.query.count()}")
    print(f"   Bills:         {Bill.query.count()}")
    print(f"   Prescriptions: {Prescription.query.count()}")
    print("\n🔐 Demo login →  admin@demo.com  /  admin1234")