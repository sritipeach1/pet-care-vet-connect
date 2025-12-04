from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import uuid
from datetime import datetime

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-secret-key"   # change later if you want
app.config["DATABASE"] = os.path.join("instance", "petcare.db")


# ----------------- DB helpers -----------------

def get_db():
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    # make sure instance folder exists
    if not os.path.exists("instance"):
        os.makedirs("instance")

    conn = get_db()
    # run schema.sql to (re)create tables
    with open("schema.sql", "r") as f:
        conn.executescript(f.read())
    conn.commit()

    # seed a default admin if not exists
    admin_email = "admin@petconnect.com"
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
        # create profile from users table
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


# ----------------- Routes -----------------

@app.route("/")
def index():
    # for now, just go to login page
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
        # send owners to Faria's owner dashboard
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
        flash("Access Denied: Admins only.")
        return redirect(url_for('login')) 
    
    conn = get_db()
    
    # 2. Fetch pending clinics using the correct Schema columns
    # We look for role='clinic' and is_verified=0
    pending_clinics = conn.execute(
        'SELECT * FROM users WHERE role = ? AND is_verified = ?', 
        ('clinic', 0)
    ).fetchall()
    
    conn.close()
    
    # 3. Render the HTML template
    return render_template('admin_dashboard.html', clinics=pending_clinics, wide_mode=True)

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
    # Delete the user from the database
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    flash("Clinic Rejected.")
    return redirect(url_for('admin_dashboard'))

# ------------- Faria: Owner Dashboard & Pets -------------

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

    # tab=? in URL, default "owner"
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
# ------------- Clinic Dashboard & Doctors (Faria) -------------

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

    # GET – reload latest data
    clinic = cur.execute(
        "SELECT * FROM clinics WHERE id = ?",
        (clinic["id"],),
    ).fetchone()
    conn.close()

    return render_template("edit_clinic_profile.html", clinic=clinic)

if __name__ == "__main__":
    app.run(debug=True)
