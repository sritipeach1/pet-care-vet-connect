from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import uuid
import re


from datetime import datetime

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-secret-key"   
app.config["DATABASE"] = os.path.join("instance", "petcare.db")



def get_db():
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    if not os.path.exists("instance"):
        os.makedirs("instance")

    conn = get_db()
    
    with open("schema.sql", "r") as f:
        conn.executescript(f.read())
    conn.commit()

    admin_email = "admin@petcare.com"
    admin = conn.execute(
        "SELECT * FROM users WHERE email = ?", (admin_email,)
    ).fetchone()

    if not admin:
        password_hash = generate_password_hash("admin123")  # admin password
        conn.execute(
            """
            INSERT INTO users
            (name, email, phone, password_hash, role,
             clinic_name, clinic_location, clinic_license, is_verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("System Admin", admin_email, None, password_hash, "admin",
             None, None, None, 1),
        )
        conn.commit()

    conn.close()
def get_or_create_owner_for_current_user():
    """Return the owners row for the logged-in owner.
       If it doesn't exist yet, create it from the users table."""
    user_id = session.get("user_id")
    if not user_id:
        return None

    conn = get_db()
    cur = conn.cursor()

    owner = cur.execute(
        "SELECT * FROM owners WHERE user_id = ?", (user_id,)
    ).fetchone()

    if not owner:
        
        user = cur.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()

        if not user:
            conn.close()
            return None

        cur.execute(
            """
            INSERT INTO owners (user_id, name, email, location, password)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user["id"], user["name"], user["email"], "", ""),
        )
        conn.commit()

        owner = cur.execute(
            "SELECT * FROM owners WHERE user_id = ?", (user_id,)
        ).fetchone()

    conn.close()
    return owner
def get_or_create_clinic_for_current_user():
    """Return the clinics row for the logged-in clinic user.
       If it doesn't exist yet, create it from the users table."""
    user_id = session.get("user_id")
    if not user_id:
        return None

    conn = get_db()
    cur = conn.cursor()

    clinic = cur.execute(
        "SELECT * FROM clinics WHERE user_id = ?", (user_id,)
    ).fetchone()

    if not clinic:
        user = cur.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()

        if not user or user["role"] != "clinic":
            conn.close()
            return None

        cur.execute(
            """
            INSERT INTO clinics (user_id, name, license_number, email, contact_number, location)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                user["clinic_name"] or user["name"],
                user["clinic_license"] or "",
                user["email"],
                user["phone"] or "",
                user["clinic_location"] or "",
            ),
        )
        conn.commit()

        clinic = cur.execute(
            "SELECT * FROM clinics WHERE user_id = ?", (user_id,)
        ).fetchone()

    conn.close()
    return clinic


def build_weekly_schedule_from_form(form):
    days = [
        ("Saturday", "sat"),
        ("Sunday", "sun"),
        ("Monday", "mon"),
        ("Tuesday", "tue"),
        ("Wednesday", "wed"),
        ("Thursday", "thu"),
        ("Friday", "fri"),
    ]

    parts = []
    for label, key in days:
        if form.get(f"{key}_enabled"):
            start = form.get(f"{key}_start")
            end = form.get(f"{key}_end")
            if start and end:
                parts.append(f"{label} {start} - {end}")
    return "; ".join(parts)


def parse_schedule_to_fields(schedule_text):
    fields = {
        "sat_start": "", "sat_end": "",
        "sun_start": "", "sun_end": "",
        "mon_start": "", "mon_end": "",
        "tue_start": "", "tue_end": "",
        "wed_start": "", "wed_end": "",
        "thu_start": "", "thu_end": "",
        "fri_start": "", "fri_end": "",
    }

    if not schedule_text:
        return fields

    day_map = {
        "Saturday": "sat",
        "Sunday": "sun",
        "Monday": "mon",
        "Tuesday": "tue",
        "Wednesday": "wed",
        "Thursday": "thu",
        "Friday": "fri",
    }

    parts = schedule_text.split(";")
    for part in parts:
        part = part.strip()
        if not part:
            continue

        try:
            day_name, times = part.split(" ", 1)
        except ValueError:
            continue

        key = day_map.get(day_name)
        if not key or " - " not in times:
            continue

        start, end = [t.strip() for t in times.split(" - ", 1)]
        fields[f"{key}_start"] = start
        fields[f"{key}_end"] = end

    return fields



# create DB file if it doesn't exist yet
if not os.path.exists(app.config["DATABASE"]):
    init_db()



@app.route("/")
def index():
 
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    # figure out which type based on ?role=owner or ?role=clinic
    default_role = request.args.get("role", "owner")
    if default_role not in ("owner", "clinic"):
        default_role = "owner"

    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        phone = request.form["phone"]
        password = request.form["password"]

        # role comes from hidden field, but we still trust only "owner"/"clinic"
        role = request.form.get("role", default_role)
        if role not in ("owner", "clinic"):
            role = "owner"

        # only clinics have these extra fields
        clinic_name = request.form.get("clinic_name") if role == "clinic" else None
        clinic_location = request.form.get("clinic_location") if role == "clinic" else None
        clinic_license = request.form.get("clinic_license") if role == "clinic" else None

        password_hash = generate_password_hash(password)

        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO users
                (name, email, phone, password_hash, role,
                 clinic_name, clinic_location, clinic_license, is_verified)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    email,
                    phone,
                    password_hash,
                    role,
                    clinic_name,
                    clinic_location,
                    clinic_license,
                    0 if role == "clinic" else 1,  # clinics pending, owners active
                ),
            )
            conn.commit()
            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Email already registered.", "danger")
        finally:
            conn.close()

    return render_template("register.html", default_role=default_role)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        conn.close()

        if user and check_password_hash(user["password_hash"], password):
            # block unverified clinics
            if user["role"] == "clinic" and not user["is_verified"]:
                flash("Your clinic account is pending admin verification.", "warning")
                return redirect(url_for("login"))

            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["role"] = user["role"]

            flash("Login successful!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid email or password.", "danger")

    return render_template("login.html")


@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))



@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    role = session.get("role")

    if role == "owner":
    
        return redirect(url_for("owner_dashboard"))
    elif role == "clinic":
        return redirect(url_for("clinic_dashboard"))
    
    elif role == "admin":
        return redirect(url_for("admin_dashboard"))
    else:
        dashboard_type = "Unknown role"
        return render_template("dashboard.html", dashboard_type=dashboard_type)

# --- ADMIN MODULE (Feature 3) ---

@app.route('/admin_dashboard')
def admin_dashboard():
    # 1. Security Check
    if 'user_id' not in session or session.get('role') != 'admin':
        flash("Access Denied: Admins only.", "danger")
        return redirect(url_for('login')) 
    
    conn = get_db()
    
    # 2. Fetch lists for all 3 categories
    # Pending (is_verified = 0)
    pending = conn.execute('SELECT * FROM users WHERE role=? AND is_verified=?', ('clinic', 0)).fetchall()
    
    # Approved (is_verified = 1)
    approved = conn.execute('SELECT * FROM users WHERE role=? AND is_verified=?', ('clinic', 1)).fetchall()
    
    # Rejected (is_verified = 2)
    rejected = conn.execute('SELECT * FROM users WHERE role=? AND is_verified=?', ('clinic', 2)).fetchall()
    
    conn.close()
    
    # 3. Render template with ALL lists
    return render_template('admin_dashboard.html', 
                           pending=pending, 
                           approved=approved, 
                           rejected=rejected,
                           wide_mode=True)

@app.route('/approve_clinic/<int:user_id>')
def approve_clinic(user_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    conn = get_db()
    # Update is_verified to 1
    conn.execute('UPDATE users SET is_verified = 1 WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    flash("Clinic Approved Successfully!")
    return redirect(url_for('admin_dashboard'))

@app.route('/reject_clinic/<int:user_id>')
def reject_clinic(user_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
        
    conn = get_db()
    # CHANGE: Update status to 2 (Rejected) instead of DELETE
    # 0 = Pending, 1 = Approved, 2 = Rejected
    conn.execute('UPDATE users SET is_verified = 2 WHERE id = ?', (user_id,)) 
    conn.commit()
    conn.close()
    
    flash("Clinic application marked as Rejected.", "warning")
    return redirect(url_for('admin_dashboard'))

# Faria: Owner Dashboard & Pets 

@app.route("/owner/dashboard")
def owner_dashboard():
    if "user_id" not in session or session.get("role") != "owner":
        return redirect(url_for("login"))

    owner = get_or_create_owner_for_current_user()
    if not owner:
        flash("Owner profile not found.", "danger")
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    pets = cur.execute(
        "SELECT * FROM pets WHERE owner_id = ?", (owner["id"],)
    ).fetchall()
    conn.close()

  
    tab = request.args.get("tab", "owner")
    return render_template("owner_dashboard.html", owner=owner, pets=pets, tab=tab)


@app.route("/owner/pets/add", methods=["GET", "POST"])
def add_pet_form():
    if "user_id" not in session or session.get("role") != "owner":
        return redirect(url_for("login"))

    owner = get_or_create_owner_for_current_user()
    if not owner:
        flash("Owner profile not found.", "danger")
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form.get("name")
        age = request.form.get("age")
        animal_type = request.form.get("animal_type")
        breed = request.form.get("breed")
        gender = request.form.get("gender")
        vaccination_status = request.form.get("vaccination_status")

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO pets (owner_id, name, age, animal_type, breed, gender, vaccination_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (owner["id"], name, age, animal_type, breed, gender, vaccination_status),
        )
        conn.commit()
        conn.close()

        return redirect(url_for("owner_dashboard", tab="pets"))

    return render_template("add_pet.html")


@app.route("/owner/pets/<int:pet_id>/edit", methods=["GET", "POST"])
def edit_pet_form(pet_id):
    if "user_id" not in session or session.get("role") != "owner":
        return redirect(url_for("login"))

    owner = get_or_create_owner_for_current_user()
    if not owner:
        flash("Owner profile not found.", "danger")
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    pet = cur.execute(
        "SELECT * FROM pets WHERE id = ? AND owner_id = ?",
        (pet_id, owner["id"]),
    ).fetchone()

    if not pet:
        conn.close()
        flash("Pet not found.", "warning")
        return redirect(url_for("owner_dashboard", tab="pets"))

    if request.method == "POST":
        name = request.form.get("name")
        age = request.form.get("age")
        animal_type = request.form.get("animal_type")
        breed = request.form.get("breed")
        gender = request.form.get("gender")
        vaccination_status = request.form.get("vaccination_status")

        cur.execute(
            """
            UPDATE pets
            SET name = ?, age = ?, animal_type = ?, breed = ?, gender = ?, vaccination_status = ?
            WHERE id = ? AND owner_id = ?
            """,
            (name, age, animal_type, breed, gender, vaccination_status, pet_id, owner["id"]),
        )
        conn.commit()
        conn.close()

        return redirect(url_for("owner_dashboard", tab="pets"))

    conn.close()
    return render_template("edit_pet.html", pet=pet)


@app.route("/owner/pets/<int:pet_id>/delete", methods=["POST"])
def delete_pet_from_dashboard(pet_id):
    if "user_id" not in session or session.get("role") != "owner":
        return redirect(url_for("login"))

    owner = get_or_create_owner_for_current_user()
    if not owner:
        flash("Owner profile not found.", "danger")
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM pets WHERE id = ? AND owner_id = ?",
        (pet_id, owner["id"]),
    )
    conn.commit()
    conn.close()

    return redirect(url_for("owner_dashboard", tab="pets"))


@app.route("/owner/profile/edit", methods=["GET", "POST"])
def edit_owner_profile():
    if "user_id" not in session or session.get("role") != "owner":
        return redirect(url_for("login"))

    owner = get_or_create_owner_for_current_user()
    if not owner:
        flash("Owner profile not found.", "danger")
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        location = request.form["location"]
        password = request.form["password"]

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE owners
            SET name = ?, email = ?, location = ?, password = ?
            WHERE id = ?
            """,
            (name, email, location, password, owner["id"]),
        )
        conn.commit()
        conn.close()

        flash("Profile updated successfully.", "success")
        return redirect(url_for("owner_dashboard", tab="owner"))

    return render_template("edit_owner_profile.html", owner=owner)

# Faria: Clinic Dashboard & Doctors 

@app.route("/clinic/dashboard")
def clinic_dashboard():
    if "user_id" not in session or session.get("role") != "clinic":
        return redirect(url_for("login"))

    clinic = get_or_create_clinic_for_current_user()
    if not clinic:
        flash("Clinic profile not found.", "danger")
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    doctors = cur.execute(
        "SELECT * FROM doctors WHERE clinic_id = ?",
        (clinic["id"],),
    ).fetchall()
    conn.close()

    tab = request.args.get("tab", "doctors")
    return render_template("clinic_dashboard.html", clinic=clinic, doctors=doctors, tab=tab)


@app.route("/clinic/doctors/add", methods=["GET", "POST"])
def add_doctor_form():
    if "user_id" not in session or session.get("role") != "clinic":
        return redirect(url_for("login"))

    clinic = get_or_create_clinic_for_current_user()
    if not clinic:
        flash("Clinic profile not found.", "danger")
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        base_fee = request.form["base_fee"]
        qualifications = request.form["qualifications"]

        weekly_schedule = build_weekly_schedule_from_form(request.form)

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO doctors (clinic_id, name, email, base_fee, qualifications, rating, weekly_schedule)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (clinic["id"], name, email, base_fee, qualifications, 0, weekly_schedule),
        )
        conn.commit()
        conn.close()

        return redirect(url_for("clinic_dashboard", tab="doctors"))

    return render_template("add_doctor.html")


@app.route("/clinic/doctors/<int:doctor_id>/edit", methods=["GET", "POST"])
def edit_doctor_form(doctor_id):
    if "user_id" not in session or session.get("role") != "clinic":
        return redirect(url_for("login"))

    clinic = get_or_create_clinic_for_current_user()
    if not clinic:
        flash("Clinic profile not found.", "danger")
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    doctor = cur.execute(
        "SELECT * FROM doctors WHERE id = ? AND clinic_id = ?",
        (doctor_id, clinic["id"]),
    ).fetchone()

    if not doctor:
        conn.close()
        flash("Doctor not found.", "warning")
        return redirect(url_for("clinic_dashboard", tab="doctors"))

    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        base_fee = request.form["base_fee"]
        qualifications = request.form["qualifications"]

        old_schedule = doctor["weekly_schedule"] or ""
        new_schedule = build_weekly_schedule_from_form(request.form)
        final_schedule = new_schedule if new_schedule else old_schedule

        cur.execute(
            """
            UPDATE doctors
            SET name = ?, email = ?, base_fee = ?, qualifications = ?, weekly_schedule = ?
            WHERE id = ? AND clinic_id = ?
            """,
            (name, email, base_fee, qualifications, final_schedule, doctor_id, clinic["id"]),
        )
        conn.commit()
        conn.close()

        return redirect(url_for("clinic_dashboard", tab="doctors"))

    schedule_fields = parse_schedule_to_fields(doctor["weekly_schedule"] or "")
    conn.close()

    return render_template("edit_doctor.html", doctor=doctor, schedule=schedule_fields)


@app.route("/clinic/doctors/<int:doctor_id>/delete", methods=["POST"])
def delete_doctor_from_dashboard(doctor_id):
    if "user_id" not in session or session.get("role") != "clinic":
        return redirect(url_for("login"))

    clinic = get_or_create_clinic_for_current_user()
    if not clinic:
        flash("Clinic profile not found.", "danger")
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM doctors WHERE id = ? AND clinic_id = ?",
        (doctor_id, clinic["id"]),
    )
    conn.commit()
    conn.close()

    return redirect(url_for("clinic_dashboard", tab="doctors"))


@app.route("/clinic/profile/edit", methods=["GET", "POST"])
def edit_clinic_profile():
    if "user_id" not in session or session.get("role") != "clinic":
        return redirect(url_for("login"))

    clinic = get_or_create_clinic_for_current_user()
    if not clinic:
        flash("Clinic profile not found.", "danger")
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        name = request.form["name"]
        license_number = request.form["license_number"]
        email = request.form["email"]
        contact_number = request.form["contact_number"]
        location = request.form["location"]

        cur.execute(
            """
            UPDATE clinics
            SET name = ?, license_number = ?, email = ?, contact_number = ?, location = ?
            WHERE id = ?
            """,
            (name, license_number, email, contact_number, location, clinic["id"]),
        )
        conn.commit()
        conn.close()

        return redirect(url_for("clinic_dashboard", tab="profile"))

   
    clinic = cur.execute(
        "SELECT * FROM clinics WHERE id = ?",
        (clinic["id"],),
    ).fetchone()
    conn.close()

    return render_template("edit_clinic_profile.html", clinic=clinic)


@app.route('/admin/view_list/<status>')
def admin_view_list(status):
    # 1. Security Check
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))

    # 2. Convert word "approved" to number 1, etc.
    status_map = {'pending': 0, 'approved': 1, 'rejected': 2}
    if status not in status_map:
        flash("Invalid list type", "danger")
        return redirect(url_for('admin_dashboard'))
    
    ver_code = status_map[status]

    # 3. Pagination Logic
    page = request.args.get('page', 1, type=int) 
    per_page = 5                                 
    offset = (page - 1) * per_page               
    
    conn = get_db()
    
    # Fetch users for this page
    users = conn.execute(
        'SELECT * FROM users WHERE role="clinic" AND is_verified=? LIMIT ? OFFSET ?',
        (ver_code, per_page, offset)
    ).fetchall()
    
    # Count TOTAL users for buttons
    total_users = conn.execute(
        'SELECT COUNT(*) FROM users WHERE role="clinic" AND is_verified=?',
        (ver_code,)
    ).fetchone()[0]
    conn.close()
    
    # Calculate total pages
    total_pages = (total_users + per_page - 1) // per_page
    
    return render_template('admin_list_view.html', 
                           users=users, 
                           status=status, 
                           page=page, 
                           total_pages=total_pages)


# -- FEATURE 6: ANALYTICS REPORTS (Rayan) --

@app.route('/clinic/reports')
def clinic_reports():
    # 1. Security Check
    if "user_id" not in session or session.get("role") != "clinic":
        return redirect(url_for("login"))

    clinic = get_or_create_clinic_for_current_user()
    if not clinic:
        return redirect(url_for("login"))

    conn = get_db()
    
    # --- 1: TOTAL COMPLETED APPOINTMENTS ---
    # We count appointments where status is 'completed' for ANY doctor in this clinic
    total_appointments = conn.execute('''
        SELECT COUNT(*) 
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        WHERE d.clinic_id = ? AND a.status = 'completed'
    ''', (clinic['id'],)).fetchone()[0]

    # --- 2: ESTIMATED REVENUE ---
    # Sum of base_fee for all completed appointments
    revenue = conn.execute('''
        SELECT SUM(d.base_fee) 
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        WHERE d.clinic_id = ? AND a.status = 'completed'
    ''', (clinic['id'],)).fetchone()[0]
    
    # If revenue is None (no appointments), make it 0
    total_revenue = round(revenue, 2) if revenue else 0.0

    # --- 3: AVERAGE RATING ---
    # Average of the 'rating' column for this clinic's doctors
    avg_rating = conn.execute('''
        SELECT AVG(a.rating) 
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        WHERE d.clinic_id = ? AND a.rating IS NOT NULL
    ''', (clinic['id'],)).fetchone()[0]

    # If no ratings yet, make it 0
    average_rating = round(avg_rating, 1) if avg_rating else 0.0

    conn.close()

    return render_template('clinic_reports.html', 
                           clinic=clinic,
                           total_appointments=total_appointments,
                           total_revenue=total_revenue,
                           average_rating=average_rating)

# --- HELPER: GENERATE DUMMY DATA (For Testing Only) ---
@app.route('/generate_test_data')
def generate_test_data():
    # This route quickly adds fake appointments so you can test the report
    if "user_id" not in session or session.get("role") != "clinic":
        return redirect(url_for("login"))
        
    clinic = get_or_create_clinic_for_current_user()
    conn = get_db()
    
    # Find a doctor in this clinic
    doctor = conn.execute("SELECT id FROM doctors WHERE clinic_id=?", (clinic['id'],)).fetchone()
    
    # If we have a doctor, create fake finished appointments
    if doctor:
        # 1. Completed appt (Earns money, 5 stars)
        conn.execute("INSERT INTO appointments (pet_id, doctor_id, appointment_date, status, rating) VALUES (1, ?, '2025-12-01', 'completed', 5)", (doctor['id'],))
        # 2. Completed appt (Earns money, 4 stars)
        conn.execute("INSERT INTO appointments (pet_id, doctor_id, appointment_date, status, rating) VALUES (1, ?, '2025-12-02', 'completed', 4)", (doctor['id'],))
        # 3. Pending appt (Does NOT earn money yet)
        conn.execute("INSERT INTO appointments (pet_id, doctor_id, appointment_date, status, rating) VALUES (1, ?, '2025-12-05', 'pending', NULL)", (doctor['id'],))
        
        conn.commit()
        flash("Test data generated! Check your reports now.", "success")
    else:
        flash("Please add a doctor first.", "warning")
        
    conn.close()
    return redirect(url_for('clinic_reports'))


# ---------------------------------------------------------
# MODULE 2 - Search & Appointment Booking (Sriti)
# ---------------------------------------------------------

DB_PATH = os.path.join("instance", "petcare.db")


def _get_conn():
    """Simple helper JUST for these routes."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _require_owner():
    """Redirect to login if not logged in as pet owner."""
    if not session.get("user_id") or session.get("role") != "owner":
        flash("Please log in as a pet owner to access this page.", "warning")
        return redirect(url_for("login"))
    return None


def _get_owner_for_current_user(conn):
    """
    Look up the row in owners table for the currently logged-in user.
    users.id -> owners.user_id
    """
    user_id = session.get("user_id")
    if not user_id:
        return None
    cur = conn.cursor()
    cur.execute("SELECT * FROM owners WHERE user_id = ?", (user_id,))
    return cur.fetchone()


@app.route("/owner/search")
def owner_search():
    """
    Search clinics by name, location, rating.
    Uses clinics + doctors + users.is_verified.
    """
    guard = _require_owner()
    if guard:
        return guard

    q = (request.args.get("q") or "").strip()
    location_filter = (request.args.get("location") or "").strip()
    rating_filter = (request.args.get("rating") or "").strip()

    conn = _get_conn()
    cur = conn.cursor()

    # Locations list from clinics table
    cur.execute("SELECT DISTINCT location FROM clinics ORDER BY location")
    locations = [row["location"] for row in cur.fetchall() if row["location"]]

    # Base query: only clinics whose user is verified
    sql = """
        SELECT
            c.*,
            u.clinic_location,
            COALESCE(AVG(d.rating), 0) AS clinic_rating,
            COUNT(d.id)                AS doctor_count
        FROM clinics c
        JOIN users u   ON c.user_id = u.id
        LEFT JOIN doctors d ON d.clinic_id = c.id
        WHERE u.is_verified = 1
    """
    params = []

    # Free-text search on name or location (case-insensitive)
    if q:
        sql += " AND (LOWER(c.name) LIKE ? OR LOWER(c.location) LIKE ?)"
        like_q = f"%{q.lower()}%"
        params.extend([like_q, like_q])

    # Exact location filter, if chosen
    if location_filter and location_filter.lower() != "all":
        sql += " AND c.location = ?"
        params.append(location_filter)

    sql += " GROUP BY c.id ORDER BY c.name"

    cur.execute(sql, params)
    clinics = cur.fetchall()
    conn.close()

    # Rating filter (using computed clinic_rating)
    def passes_rating(c):
        if not rating_filter or rating_filter == "all":
            return True
        rating = c["clinic_rating"] or 0
        if rating_filter == "4.5plus":
            return rating >= 4.5
        if rating_filter == "4plus":
            return rating >= 4.0
        if rating_filter == "3plus":
            return rating >= 3.0
        return True

    clinics = [c for c in clinics if passes_rating(c)]

    return render_template(
        "owner_search.html",
        clinics=clinics,
        locations=locations,
        q=q,
        location_filter=location_filter,
        rating_filter=rating_filter,
    )

def _extract_time_slots(weekly_schedule: str):
    """
    Turn a weekly_schedule string into a list of time slots.

    Examples of weekly_schedule formats this can handle:
      "Mon 12:00 - 20:00"
      "Sunday:09:00-11:00,14:00-16:00"
      "Tue 09:00-10:00; Wed 14:00-16:00"

    It looks for all HH:MM times and pairs them:
      [09:00,11:00,14:00,16:00] -> (09:00-11:00), (14:00-16:00)
    """
    if not weekly_schedule:
        return []

    times = re.findall(r"(\d{2}:\d{2})", weekly_schedule)
    slots = []
    for i in range(0, len(times), 2):
        if i + 1 < len(times):
            start = times[i]
            end = times[i + 1]
            slots.append(
                {
                    "start": start,                # value we submit to backend
                    "label": f"{start} - {end}",   # text shown on the button
                }
            )
    return slots
@app.route("/owner/clinic/<int:clinic_id>")
def owner_clinic_detail(clinic_id):
    """
    Show single clinic details + doctors + booking form.
    """
    guard = _require_owner()
    if guard:
        return guard

    conn = _get_conn()
    cur = conn.cursor()

    # Get clinic
    cur.execute(
        """
        SELECT
            c.*,
            COALESCE(AVG(d.rating), 0) AS clinic_rating
        FROM clinics c
        LEFT JOIN doctors d ON d.clinic_id = c.id
        WHERE c.id = ?
        GROUP BY c.id
        """,
        (clinic_id,),
    )
    clinic = cur.fetchone()

    if not clinic:
        conn.close()
        flash("Clinic not found.", "danger")
        return redirect(url_for("owner_search"))

    # Doctors in this clinic
    cur.execute(
        """
        SELECT *
        FROM doctors
        WHERE clinic_id = ?
        ORDER BY name
        """,
        (clinic_id,),
    )
    doctors = cur.fetchall()

    # Owner + pets (via owners.user_id)
    owner = _get_owner_for_current_user(conn)
    if not owner:
        conn.close()
        flash("Owner profile not found.", "danger")
        return redirect(url_for("owner_dashboard"))

    cur.execute(
        """
        SELECT *
        FROM pets
        WHERE owner_id = ?
        ORDER BY name
        """,
        (owner["id"],),
    )
    pets = cur.fetchall()

    conn.close()

    # Build a dict: doctor_id -> list of slots
    doctor_slots = {}
    for d in doctors:
        doctor_slots[d["id"]] = _extract_time_slots(d["weekly_schedule"] or "")


    return render_template(
        "owner_clinic_detail.html",
        clinic=clinic,
        doctors=doctors,
        pets=pets,
        doctor_slots=doctor_slots,
    )


@app.route("/owner/book/<int:clinic_id>/<int:doctor_id>", methods=["POST"])
def book_appointment(clinic_id, doctor_id):
    """Book an appointment for a pet with a doctor."""
    # Must be logged in as owner
    if "user_id" not in session or session.get("role") != "owner":
        flash("Please log in as a pet owner to book an appointment.", "warning")
        return redirect(url_for("login"))

    owner = get_or_create_owner_for_current_user()
    if not owner:
        flash("Owner profile not found.", "danger")
        return redirect(url_for("login"))

    # Form values
    pet_id = request.form.get("pet_id")
    date = request.form.get("date")
    time_str = request.form.get("time")

    if not pet_id or not date or not time_str:
        flash("Please select pet, date, and time.", "warning")
        return redirect(url_for("owner_clinic_detail", clinic_id=clinic_id))

    # Parse to datetime so we can check weekday etc.
    try:
        dt = datetime.strptime(f"{date} {time_str}", "%Y-%m-%d %H:%M")
    except ValueError:
        flash("Please pick a valid date and time.", "warning")
        return redirect(url_for("owner_clinic_detail", clinic_id=clinic_id))

    appointment_dt = dt.strftime("%Y-%m-%d %H:%M")   # string stored in DB
    weekday_short = dt.strftime("%a").lower()        # 'mon', 'tue', ...

    conn = get_db()
    cur = conn.cursor()

    # -------- 1) Check doctor's weekly availability (day of week) --------
    cur.execute("SELECT weekly_schedule FROM doctors WHERE id = ?", (doctor_id,))
    doctor_row = cur.fetchone()
    if not doctor_row:
        conn.close()
        flash("Doctor not found.", "danger")
        return redirect(url_for("owner_clinic_detail", clinic_id=clinic_id))

    weekly_schedule = (doctor_row["weekly_schedule"] or "").lower()

    # We just check if the 3-letter day code is mentioned in the schedule text.
    # Example: weekly_schedule = "Mon 12:00-20:00, Wed 10:00-18:00"
    # dt.strftime("%a") = "Mon" -> "mon" is in weekly_schedule.
    day_code = {
        "mon": "mon",
        "tue": "tue",
        "wed": "wed",
        "thu": "thu",
        "fri": "fri",
        "sat": "sat",
        "sun": "sun",
    }[weekday_short]

    if day_code not in weekly_schedule:
        conn.close()
        flash("This doctor is not available on that day. Please choose another date.", "warning")
        return redirect(url_for("owner_clinic_detail", clinic_id=clinic_id))

    # -------- 2) Check that the pet actually belongs to this owner --------
    cur.execute(
        "SELECT 1 FROM pets WHERE id = ? AND owner_id = ?",
        (pet_id, owner["id"]),
    )
    if not cur.fetchone():
        conn.close()
        flash("Invalid pet selected.", "danger")
        return redirect(url_for("owner_clinic_detail", clinic_id=clinic_id))

    # -------- 3) Check for an existing appointment with same slot --------
    cur.execute(
        """
        SELECT id
        FROM appointments
        WHERE doctor_id = ?
          AND appointment_date = ?
          AND status IN ('pending', 'completed', 'approved')
        """,
        (doctor_id, appointment_dt),
    )
    if cur.fetchone():
        conn.close()
        flash("Slot is filled, choose another timing.", "danger")
        return redirect(url_for("owner_clinic_detail", clinic_id=clinic_id))

    # -------- 4) Insert new appointment --------
    cur.execute(
        """
        INSERT INTO appointments (pet_id, doctor_id, appointment_date, status)
        VALUES (?, ?, ?, 'pending')
        """,
        (pet_id, doctor_id, appointment_dt),
    )
    conn.commit()
    conn.close()

    flash("Appointment booked! Waiting for clinic confirmation.", "success")
    return redirect(url_for("owner_appointments"))

@app.route("/owner/appointments")
def owner_appointments():
    """
    Show all appointments for the logged-in owner.
    appointments joins pets -> owners -> doctors -> clinics.
    """
    guard = _require_owner()
    if guard:
        return guard

    conn = _get_conn()
    cur = conn.cursor()

    owner = _get_owner_for_current_user(conn)
    if not owner:
        conn.close()
        flash("Owner profile not found.", "danger")
        return redirect(url_for("owner_dashboard"))

    cur.execute(
        """
        SELECT
            a.*,
            d.name AS doctor_name,
            c.name AS clinic_name,
            c.location AS clinic_location,
            p.name AS pet_name
        FROM appointments a
        JOIN pets    p ON a.pet_id   = p.id
        JOIN owners  o ON p.owner_id = o.id
        JOIN doctors d ON a.doctor_id = d.id
        JOIN clinics c ON d.clinic_id = c.id
        WHERE o.id = ?
        ORDER BY a.appointment_date DESC
        """,
        (owner["id"],),
    )
    rows = cur.fetchall()
    conn.close()

    upcoming = []
    completed = []
    cancelled = []

    for r in rows:
        status = (r["status"] or "").lower()
        if status in ("completed", "done"):
            completed.append(r)
        elif status in ("cancelled", "canceled", "owner_cancelled", "clinic_cancelled"):
            cancelled.append(r)
        else:
            upcoming.append(r)

    return render_template(
        "owner_appointments.html",
        upcoming=upcoming,
        completed=completed,
        cancelled=cancelled,
    )




if __name__ == "__main__":
    app.run(debug=True)
