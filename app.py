from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import uuid
import threading

import re
from flask import jsonify

from datetime import datetime

app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-secret-key"
app.config["DATABASE"] = os.path.join("instance", "petcare.db")
app.config["UPLOAD_FOLDER"] = os.path.join("static", "pet_photos")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ------------- EMAIL HELPER (Feature 10: Notifications) -------------

import os
import base64
from email.message import EmailMessage

def send_email(to_email, subject, body):
    """
    Sends a real email via Gmail API using OAuth Desktop credentials.

    Required files in your project folder:
      - credentials.json  (downloaded from Google Cloud -> OAuth client)
      - token.json        (auto-created on first successful auth)

    Required pip installs:
      pip install --upgrade google-api-python-client google-auth google-auth-oauthlib
    """
    if not to_email:
        return

    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from google.auth.transport.requests import Request

        SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

        creds = None
        token_path = "token.json"
        creds_path = "credentials.json"

        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)

        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(creds_path):
                    raise FileNotFoundError(
                        "credentials.json not found. Download the OAuth client JSON and save it as credentials.json"
                    )

                # This opens the browser ON THE MACHINE running Flask (your laptop)
                flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
                creds = flow.run_local_server(port=0)

            with open(token_path, "w", encoding="utf-8") as token:
                token.write(creds.to_json())

        service = build("gmail", "v1", credentials=creds)

        msg = EmailMessage()
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)

        encoded_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        send_body = {"raw": encoded_message}

        service.users().messages().send(userId="me", body=send_body).execute()

        print("\n" + "=" * 60)
        print("REAL EMAIL SENT (Gmail API)")
        print(f"To      : {to_email}")
        print(f"Subject : {subject}")
        print("=" * 60 + "\n")

    except Exception as e:
        # Fallback so your app never crashes during demo
        print("\n" + "=" * 60)
        print("EMAIL FAILED - FALLING BACK TO CONSOLE PRINT")
        print(f"Reason  : {e}")
        print(f"To      : {to_email}")
        print(f"Subject : {subject}")
        print("-" * 60)
        print(body)
        print("=" * 60 + "\n")
def send_email_async(to_email, subject, body):
    # non-blocking email send (prevents loading delay)
    threading.Thread(
        target=send_email,
        args=(to_email, subject, body),
        daemon=True
    ).start()


EMAIL_SIGNATURE = "Regards,\nPet Care & Vet-Connect"

def _pretty_status(status: str) -> str:
    if not status:
        return "Unknown"
    # "reschedule_pending" -> "Reschedule Pending"
    return status.strip().replace("_", " ").title()

def _pretty_datetime(dt_str: str) -> str:
    """
    dt_str expected format: 'YYYY-MM-DD HH:MM'
    Returns: 'Dec 11, 2025 at 02:30 PM'
    """
    if not dt_str:
        return "N/A"
    try:
        dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        return dt.strftime("%b %d, %Y at %I:%M %p")
    except Exception:
        return dt_str

def _fetch_email_context(conn, appt_id: int):
    """
    Gets owner email + details needed for email.
    Returns dict or None.
    """
    row = conn.execute("""
        SELECT
            a.id,
            a.status,
            a.appointment_date,
            o.email AS owner_email,
            o.name  AS owner_name,
            p.name  AS pet_name,
            d.name  AS doctor_name,
            c.name  AS clinic_name
        FROM appointments a
        JOIN pets p    ON a.pet_id = p.id
        JOIN owners o  ON p.owner_id = o.id
        JOIN doctors d ON a.doctor_id = d.id
        JOIN clinics c ON d.clinic_id = c.id
        WHERE a.id = ?
    """, (appt_id,)).fetchone()
    return dict(row) if row else None

def send_owner_status_email(owner_email: str, owner_name: str, clinic_name: str,
                            doctor_name: str, pet_name: str, appt_dt: str, status: str):
    pretty_status = _pretty_status(status)
    pretty_dt = _pretty_datetime(appt_dt)

    subject = f"Appointment Update: {pretty_status}"
    body = f"""Hello {owner_name or "there"},

This is an update regarding your appointment.

Clinic: {clinic_name}
Doctor: {doctor_name}
Pet: {pet_name}
Time: {pretty_dt}
Status: {pretty_status}

If you have any questions, please contact the clinic directly.

Regards,
Pet Care & Vet-Connect
"""

    # IMPORTANT: send in background so approve/cancel doesn't "hang"
    threading.Thread(
        target=send_email,
        args=(owner_email, subject, body),
        daemon=True
    ).start()



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


def get_appointment_context(appt_id):
    """
    Returns one row with:
    - owner_name, owner_email
    - clinic_name, clinic_email
    - doctor_name, pet_name
    - appointment_date, status
    """
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            a.id,
            a.appointment_date,
            a.status,
            o.name   AS owner_name,
            o.email  AS owner_email,
            c.name   AS clinic_name,
            c.email  AS clinic_email,
            d.name   AS doctor_name,
            p.name   AS pet_name
        FROM appointments a
        JOIN pets p    ON a.pet_id = p.id
        JOIN owners o  ON p.owner_id = o.id
        JOIN doctors d ON a.doctor_id = d.id
        JOIN clinics c ON d.clinic_id = c.id
        WHERE a.id = ?
        """,
        (appt_id,),
    )
    row = cur.fetchone()
    conn.close()
    return row


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
    pending = conn.execute('SELECT * FROM users WHERE role=? AND is_verified=?',
                           ('clinic', 0)).fetchall()

    # Approved (is_verified = 1)
    approved = conn.execute('SELECT * FROM users WHERE role=? AND is_verified=?',
                            ('clinic', 1)).fetchall()

    # Rejected (is_verified = 2)
    rejected = conn.execute('SELECT * FROM users WHERE role=? AND is_verified=?',
                            ('clinic', 2)).fetchall()

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

        photo_file = request.files.get("photo")
        photo_filename = None

        if photo_file and photo_file.filename and allowed_file(photo_file.filename):
            os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
            ext = photo_file.filename.rsplit(".", 1)[1].lower()
            photo_filename = f"{uuid.uuid4().hex}.{ext}"
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], photo_filename)
            photo_file.save(save_path)

        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO pets (owner_id, name, age, animal_type, breed, gender, vaccination_status, photo_filename)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (owner["id"], name, age, animal_type, breed, gender, vaccination_status, photo_filename),
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

        photo_file = request.files.get("photo")
        photo_filename = pet["photo_filename"]  # keep old one by default

        if photo_file and photo_file.filename and allowed_file(photo_file.filename):
            os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
            ext = photo_file.filename.rsplit(".", 1)[1].lower()
            new_filename = f"{uuid.uuid4().hex}.{ext}"
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], new_filename)
            photo_file.save(save_path)
            photo_filename = new_filename

        cur.execute(
            """
            UPDATE pets
            SET name = ?, age = ?, animal_type = ?, breed = ?, gender = ?, vaccination_status = ?, photo_filename = ?
            WHERE id = ? AND owner_id = ?
            """,
            (name, age, animal_type, breed, gender, vaccination_status, photo_filename, pet_id, owner["id"]),
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


from werkzeug.security import generate_password_hash, check_password_hash  # noqa: E402


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

        # Optional password fields
        current_password = request.form.get("current_password", "").strip()
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        conn = get_db()
        cur = conn.cursor()

        # Update basic profile info 
        cur.execute(
            """
            UPDATE owners
            SET name = ?, email = ?, location = ?
            WHERE id = ?
            """,
            (name, email, location, owner["id"]),
        )

        # Handle optional password change
        if current_password or new_password or confirm_password:
            if not current_password or not new_password or not confirm_password:
                conn.close()
                flash("To change password, fill current password and both new password fields.", "warning")
                return redirect(url_for("edit_owner_profile"))

            if new_password != confirm_password:
                conn.close()
                flash("New password and confirmation do not match.", "warning")
                return redirect(url_for("edit_owner_profile"))

            user = cur.execute(
                "SELECT * FROM users WHERE id = ?",
                (owner["user_id"],)
            ).fetchone()

            if not user or not check_password_hash(user["password_hash"], current_password):
                conn.close()
                flash("Current password is incorrect.", "danger")
                return redirect(url_for("edit_owner_profile"))

  
            new_hash = generate_password_hash(new_password)
            cur.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (new_hash, owner["user_id"])
            )

            # update plain password column in owners 
            cur.execute(
                "UPDATE owners SET password = ? WHERE id = ?",
                (new_password, owner["id"])
            )

        conn.commit()
        conn.close()

        flash("Profile updated successfully.", "success")
        return redirect(url_for("owner_dashboard", tab="owner"))

    return render_template("edit_owner_profile.html", owner=owner)


@app.route("/owner/appointment/<int:appt_id>/accept_reschedule", methods=["POST"])
def owner_accept_reschedule(appt_id):
    """
    Owner accepts the new time proposed by the clinic.
    We mark the appointment as approved again.
    """
    # Must be logged in as owner
    guard = _require_owner()
    if guard:
        return guard

    conn = _get_conn()
    cur = conn.cursor()

    # Ensure this appointment belongs to the logged in owner
    owner = _get_owner_for_current_user(conn)
    if not owner:
        conn.close()
        flash("Owner profile not found.", "danger")
        return redirect(url_for("owner_dashboard"))

    cur.execute(
        """
        SELECT a.*
        FROM appointments a
        JOIN pets p ON a.pet_id = p.id
        JOIN owners o ON p.owner_id = o.id
        WHERE a.id = ? AND o.id = ?
        """,
        (appt_id, owner["id"]),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        flash("Appointment not found for your account.", "warning")
        return redirect(url_for("owner_appointments"))

    # Update status to approved (new time confirmed)
    conn.execute(
        "UPDATE appointments SET status = 'approved' WHERE id = ?",
        (appt_id,),
    )
    conn.commit()
    conn.close()

    # notify clinic that owner accepted
    appt = get_appointment_context(appt_id)
    if appt:
        subject = "PetConnect: Owner Accepted Rescheduled Appointment"
        body = (
            f"Hello {appt['clinic_name']},\n\n"
            f"The pet owner has accepted the new time for this appointment.\n\n"
            f"Owner  : {appt['owner_name']}\n"
            f"Pet    : {appt['pet_name']}\n"
            f"Doctor : {appt['doctor_name']}\n"
            f"When   : {appt['appointment_date']}\n"
            f"Status : Approved\n\n"
            "– PetConnect"
        )
        send_email_async(appt["clinic_email"], subject, body)

    flash("New time confirmed.", "success")
    return redirect(url_for("owner_appointments"))


@app.route("/owner/appointment/<int:appt_id>/decline_reschedule", methods=["POST"])
def owner_decline_reschedule(appt_id):
    """
    Owner declines the new time. We mark the appointment as owner_cancelled.
    """
    #Must be logged in as owner
    guard = _require_owner()
    if guard:
        return guard

    conn = _get_conn()
    cur = conn.cursor()

    #Ensure this appointment belongs to the logged-in owner
    owner = _get_owner_for_current_user(conn)
    if not owner:
        conn.close()
        flash("Owner profile not found.", "danger")
        return redirect(url_for("owner_dashboard"))

    cur.execute(
        """
        SELECT a.*
        FROM appointments a
        JOIN pets p ON a.pet_id = p.id
        JOIN owners o ON p.owner_id = o.id
        WHERE a.id = ? AND o.id = ?
        """,
        (appt_id, owner["id"]),
    )
    row = cur.fetchone()
    if not row:
        conn.close()
        flash("Appointment not found for your account.", "warning")
        return redirect(url_for("owner_appointments"))

    #Update status to owner_cancelled
    conn.execute(
        "UPDATE appointments SET status = 'owner_cancelled' WHERE id = ?",
        (appt_id,),
    )
    conn.commit()
    conn.close()

    #notify clinic that owner cancelled 
    appt = get_appointment_context(appt_id)
    if appt:
        subject = "PetConnect: Rescheduled Appointment Declined by Owner"
        body = (
            f"Hello {appt['clinic_name']},\n\n"
            f"The pet owner has declined the proposed new time. "
            f"The appointment is now cancelled by the owner.\n\n"
            f"Owner  : {appt['owner_name']}\n"
            f"Pet    : {appt['pet_name']}\n"
            f"Doctor : {appt['doctor_name']}\n"
            f"When   : {appt['appointment_date']}\n"
            f"Status : Cancelled\n\n"
            "– PetConnect"
        )
        send_email(appt["clinic_email"], subject, body)

    flash("Rescheduled time declined. Appointment cancelled.", "info")
    return redirect(url_for("owner_appointments"))


@app.route("/clinic/dashboard")
def clinic_dashboard():
    if "user_id" not in session or session.get("role") != "clinic":
        return redirect(url_for("login"))

    clinic = get_or_create_clinic_for_current_user()
    if not clinic:
        flash("Clinic profile not found.", "danger")
        return redirect(url_for("login"))

    tab = request.args.get("tab", "doctors")

    conn = get_db()
    cur = conn.cursor()

    # Always load doctors (left-side list)
    doctors = cur.execute(
        "SELECT * FROM doctors WHERE clinic_id = ? ORDER BY name",
        (clinic["id"],),
    ).fetchall()

    # Only load requests if we are on the Appointments tab
    appointments_requests = []
    if tab == "appointments":
        appointments_requests = cur.execute(
            """
            SELECT
                a.id,
                a.appointment_date,
                a.status,
                p.name               AS pet_name,
                p.age                AS age,
                p.age                AS pet_age,
                p.animal_type        AS animal_type,
                p.animal_type        AS pet_animal_type,
                p.breed              AS breed,
                p.breed              AS pet_breed,
                p.gender             AS gender,
                p.gender             AS pet_gender,
                p.vaccination_status AS vaccination_status,
                p.vaccination_status AS pet_vaccination_status,
                o.name               AS owner_name,
                d.name               AS doctor_name
            FROM appointments a
            JOIN pets    p ON a.pet_id   = p.id
            JOIN owners  o ON p.owner_id = o.id
            JOIN doctors d ON a.doctor_id = d.id
            WHERE d.clinic_id = ?
              AND a.status IN ('pending', 'reschedule_pending')
            ORDER BY a.appointment_date ASC
            """,
            (clinic["id"],),
        ).fetchall()

    conn.close()

    return render_template(
        "clinic_dashboard.html",
        clinic=clinic,
        doctors=doctors,
        tab=tab,
        appointments_requests=appointments_requests,   # used in Manage Appointments tab
    )

@app.route("/clinic/doctor/<int:doctor_id>/appointments")
def clinic_doctor_appointments(doctor_id):
    # Must be clinic user
    if "user_id" not in session or session.get("role") != "clinic":
        return redirect(url_for("login"))

    clinic = get_or_create_clinic_for_current_user()
    if not clinic:
        flash("Clinic profile not found.", "danger")
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    # Make sure this doctor belongs to this clinic
    cur.execute(
        "SELECT * FROM doctors WHERE id = ? AND clinic_id = ?",
        (doctor_id, clinic["id"]),
    )
    doctor = cur.fetchone()
    if not doctor:
        conn.close()
        flash("Doctor not found for this clinic.", "danger")
        return redirect(url_for("clinic_dashboard", tab="appointments"))

    # Optional search by pet name
    q = (request.args.get("q") or "").strip()
    params = [doctor_id]
    where_extra = ""
    if q:
        where_extra = " AND LOWER(p.name) LIKE ?"
        params.append(f"%{q.lower()}%")

    cur.execute(
        f"""
        SELECT
            a.id,
            a.appointment_date,
            a.status,
            a.rating,
            p.name               AS pet_name,
            p.age                AS age,
            p.age                AS pet_age,
            p.animal_type        AS animal_type,
            p.animal_type        AS pet_animal_type,
            p.breed              AS breed,
            p.breed              AS pet_breed,
            p.gender             AS gender,
            p.gender             AS pet_gender,
            p.vaccination_status AS vaccination_status,
            p.vaccination_status AS pet_vaccination_status,
            o.name               AS owner_name,
            d.name               AS doctor_name
        FROM appointments a
        JOIN pets    p ON a.pet_id   = p.id
        JOIN owners  o ON p.owner_id = o.id
        JOIN doctors d ON a.doctor_id = d.id
        WHERE a.doctor_id = ?
          {where_extra}
        ORDER BY a.appointment_date ASC
        """,
        params,
    )

    rows = cur.fetchall()
    conn.close()

    # Split into sections for tabs/cards
    requests = []
    upcoming = []
    completed = []
    cancelled = []

    for r in rows:
        status = (r["status"] or "").lower()

        if status in ("pending", "reschedule_pending"):
            requests.append(r)          # still not decided
        elif status in ("approved",):
            upcoming.append(r)         # approved future visits
        elif status in ("completed", "done"):
            completed.append(r)        # finished ones
        elif status in ("clinic_cancelled", "owner_cancelled", "cancelled", "canceled"):
            cancelled.append(r)        # any kind of cancel

    return render_template(
        "clinic_doctor_appointments.html",
        clinic=clinic,
        doctor=doctor,
        q=q,
        requests=requests,
        upcoming=upcoming,
        completed=completed,
        cancelled=cancelled,
    )

@app.route("/clinic/appointment/<int:appt_id>/<action>", methods=["POST"])
def clinic_appointment_action(appt_id, action):
    if "user_id" not in session or session.get("role") != "clinic":
        return redirect(url_for("login"))

    clinic = get_or_create_clinic_for_current_user()
    if not clinic:
        flash("Clinic profile not found.", "danger")
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    # Ensure appointment belongs to this clinic
    cur.execute(
        """
        SELECT a.id, a.status, d.clinic_id
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        WHERE a.id = ?
        """,
        (appt_id,),
    )
    row = cur.fetchone()

    if not row or row["clinic_id"] != clinic["id"]:
        conn.close()
        flash("Appointment not found for this clinic.", "warning")
        return redirect(url_for("clinic_dashboard", tab="appointments"))

    new_status = None

    if action == "approve":
        new_status = "approved"
        cur.execute("UPDATE appointments SET status = ? WHERE id = ?", (new_status, appt_id))
        flash("Appointment approved.", "success")

    elif action == "cancel":
        new_status = "clinic_cancelled"
        cur.execute("UPDATE appointments SET status = ? WHERE id = ?", (new_status, appt_id))
        flash("Appointment cancelled.", "info")

    else:
        conn.close()
        flash("Invalid action.", "warning")
        return redirect(url_for("clinic_dashboard", tab="appointments"))

    conn.commit()

    # Email owner 
    ctx = _fetch_email_context(conn, appt_id)
    if ctx and ctx.get("owner_email"):
        send_owner_status_email(
            owner_email=ctx["owner_email"],
            owner_name=ctx.get("owner_name"),
            clinic_name=ctx.get("clinic_name"),
            doctor_name=ctx.get("doctor_name"),
            pet_name=ctx.get("pet_name"),
            appt_dt=ctx.get("appointment_date"),
            status=new_status,
        )

    conn.close()
    return redirect(url_for("clinic_dashboard", tab="appointments"))



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


@app.route("/clinic/appointments")
def clinic_appointments():
    if "user_id" not in session or session.get("role") != "clinic":
        return redirect(url_for("login"))

    clinic = get_or_create_clinic_for_current_user()
    conn = get_db()
    cur = conn.cursor()

    rows = cur.execute(
        """
        SELECT
            a.*,
            d.name               AS doctor_name,
            p.name               AS pet_name,
            p.animal_type        AS animal_type,
            p.animal_type        AS pet_animal,
            p.animal_type        AS pet_animal_type,
            p.breed              AS breed,
            p.breed              AS pet_breed,
            p.gender             AS gender,
            p.gender             AS pet_gender,
            p.age                AS age,
            p.age                AS pet_age,
            p.vaccination_status AS vaccination_status,
            p.vaccination_status AS pet_vaccination,
            p.vaccination_status AS pet_vaccination_status,
            o.name               AS owner_name
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        JOIN pets    p ON a.pet_id   = p.id
        JOIN owners  o ON p.owner_id = o.id
        WHERE d.clinic_id = ?
        ORDER BY a.appointment_date ASC
        """,
        (clinic["id"],),
    ).fetchall()

    conn.close()

    return render_template(
        "clinic_dashboard.html",
        clinic=clinic,
        appointments=rows,
        tab="appointments"
    )




@app.route("/clinic/appointment/<int:appt_id>/reschedule", methods=["GET", "POST"])
def reschedule_appointment(appt_id):
    if "user_id" not in session or session.get("role") != "clinic":
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT
            a.*,
            d.id   AS doctor_id,
            d.name AS doctor_name,
            p.name AS pet_name,
            o.name AS owner_name
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        JOIN pets p    ON a.pet_id   = p.id
        JOIN owners o  ON p.owner_id = o.id
        WHERE a.id = ?
        """,
        (appt_id,),
    )
    appt = cur.fetchone()

    if not appt:
        conn.close()
        flash("Appointment not found.", "danger")
        return redirect(url_for("clinic_dashboard", tab="appointments"))

    if request.method == "POST":
        new_date = request.form.get("new_date")
        new_time = request.form.get("new_time")

        if not new_date or not new_time:
            flash("Please choose both date and time.", "warning")
            conn.close()
            return redirect(url_for("reschedule_appointment", appt_id=appt_id))

        try:
            dt = datetime.strptime(f"{new_date} {new_time}", "%Y-%m-%d %H:%M")
        except ValueError:
            flash("Invalid date or time format.", "warning")
            conn.close()
            return redirect(url_for("reschedule_appointment", appt_id=appt_id))

        new_dt_str = dt.strftime("%Y-%m-%d %H:%M")

        cur.execute(
            "UPDATE appointments SET appointment_date = ?, status = 'reschedule_pending' WHERE id = ?",
            (new_dt_str, appt_id),
        )
        conn.commit()

        ctx = _fetch_email_context(conn, appt_id)
        if ctx and ctx.get("owner_email"):
            send_owner_status_email(
                owner_email=ctx["owner_email"],
                owner_name=ctx.get("owner_name"),
                clinic_name=ctx.get("clinic_name"),
                doctor_name=ctx.get("doctor_name"),
                pet_name=ctx.get("pet_name"),
                appt_dt=new_dt_str,
                status="reschedule_pending",
            )

        conn.close()
        flash("New time proposed. Waiting for owner confirmation.", "info")
        return redirect(url_for("clinic_dashboard", tab="appointments"))


    selected_date = request.args.get("date")  # optional
    available_slots = []

    if selected_date:
        available_slots = _doctor_slots_for_date(conn, appt["doctor_id"], selected_date)

    conn.close()
    return render_template(
        "reschedule_form.html",
        appointment=appt,
        selected_date=selected_date,
        available_slots=available_slots,
    )


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

        current_password = request.form.get("current_password", "").strip()
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        #Update basic clinic profile 
        cur.execute(
            """
            UPDATE clinics
            SET name = ?, license_number = ?, email = ?, contact_number = ?, location = ?
            WHERE id = ?
            """,
            (name, license_number, email, contact_number, location, clinic["id"]),
        )

        # pass change
        if current_password or new_password or confirm_password:
            if not current_password or not new_password or not confirm_password:
                conn.close()
                flash("To change password, fill current password and both new password fields.", "warning")
                return redirect(url_for("edit_clinic_profile"))

            if new_password != confirm_password:
                conn.close()
                flash("New password and confirmation do not match.", "warning")
                return redirect(url_for("edit_clinic_profile"))

            user = cur.execute(
                "SELECT * FROM users WHERE id = ?",
                (clinic["user_id"],)
            ).fetchone()

            if not user or not check_password_hash(user["password_hash"], current_password):
                conn.close()
                flash("Current password is incorrect.", "danger")
                return redirect(url_for("edit_clinic_profile"))

            new_hash = generate_password_hash(new_password)
            cur.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (new_hash, clinic["user_id"])
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
    total_appointments = conn.execute('''
        SELECT COUNT(*)
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        WHERE d.clinic_id = ? AND a.status = 'completed'
    ''', (clinic['id'],)).fetchone()[0]

    # --- 2: ESTIMATED REVENUE ---
    revenue = conn.execute('''
        SELECT SUM(d.base_fee)
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        WHERE d.clinic_id = ? AND a.status = 'completed'
    ''', (clinic['id'],)).fetchone()[0]

    total_revenue = round(revenue, 2) if revenue else 0.0

    # --- 3: AVERAGE RATING ---
    avg_rating = conn.execute('''
        SELECT AVG(a.rating)
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        WHERE d.clinic_id = ? AND a.rating IS NOT NULL
    ''', (clinic['id'],)).fetchone()[0]

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
        conn.execute("INSERT INTO appointments (pet_id, doctor_id, appointment_date, status, rating) "
                     "VALUES (1, ?, '2025-12-01', 'completed', 5)", (doctor['id'],))
        conn.execute("INSERT INTO appointments (pet_id, doctor_id, appointment_date, status, rating) "
                     "VALUES (1, ?, '2025-12-02', 'completed', 4)", (doctor['id'],))
        conn.execute("INSERT INTO appointments (pet_id, doctor_id, appointment_date, status, rating) "
                     "VALUES (1, ?, '2025-12-05', 'pending', NULL)", (doctor['id'],))

        conn.commit()
        flash("Test data generated! Check your reports now.", "success")
    else:
        flash("Please add a doctor first.", "warning")

    conn.close()
    return redirect(url_for('clinic_reports'))


# ---------------------------------------------------------
# MODULE 2 - Search & Appointment Booking (Sriti)
# ---------------------------------------------------------

import os as _os  # avoid clashing with above imports
import re as _re
import sqlite3 as _sqlite3
from datetime import datetime as _dt2, timedelta
from flask import jsonify as _jsonify

DB_PATH = _os.path.join("instance", "petcare.db")


def _get_conn():
    """Simple helper JUST for these routes."""
    conn = _sqlite3.connect(DB_PATH)
    conn.row_factory = _sqlite3.Row
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


# -------------------------- Search --------------------------

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



DAY_TOKENS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _expand_half_hours(start_str: str, end_str: str):
    """Return ['HH:MM', ...] every 30 min from start (inclusive) to end (exclusive)."""
    start = _dt2.strptime(start_str, "%H:%M")
    end = _dt2.strptime(end_str, "%H:%M")
    out = []
    t = start
    while t < end:
        out.append(t.strftime("%H:%M"))
        t += timedelta(minutes=30)
    return out


def _parse_weekly_schedule_by_day(weekly_schedule: str):
    """
    Parse a free-text weekly schedule into a dict:
      {'mon': [('12:00','20:00'), ('09:00','11:00')], 'tue': [...], ...}
    """
    if not weekly_schedule:
        return {}

    text = weekly_schedule.lower() + " __END__"

    positions = []
    for d in DAY_TOKENS:
        for m in _re.finditer(rf"\b{d}\w*\b", text):  
            positions.append((m.start(), d))
    positions.sort()

    chunks = []
    for i, (pos, day) in enumerate(positions):
        end_pos = positions[i + 1][0] if i + 1 < len(positions) else text.index(" __END__")
        chunks.append((day, text[pos:end_pos]))

    out = {d: [] for d in DAY_TOKENS}
    for day, chunk in chunks:
        times = _re.findall(r"(\d{2}:\d{2})", chunk)
        for i in range(0, len(times), 2):
            if i + 1 < len(times):
                out[day].append((times[i], times[i + 1]))

    return {d: ranges for d, ranges in out.items() if ranges}


def _doctor_slots_for_date(conn, doctor_id: int, date_str: str):
    """
    Return 30-min available start times (['HH:MM', ...]) for a given doctor on a given date.
    Filters by the doctor's weekly_schedule AND removes already-booked or rescheduled times.
    """
    cur = conn.cursor()

    cur.execute("SELECT weekly_schedule FROM doctors WHERE id = ?", (doctor_id,))
    row = cur.fetchone()
    if not row:
        return []

    weekly = (row["weekly_schedule"] or "")
    schedule_by_day = _parse_weekly_schedule_by_day(weekly)

    try:
        dt = _dt2.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return []

    weekday = dt.strftime("%a").lower()[:3]  

    if weekday not in schedule_by_day:
        return []

    slots = []
    for start, end in schedule_by_day[weekday]:
        slots.extend(_expand_half_hours(start, end))

    if not slots:
        return []

    cur.execute(
        """
        SELECT appointment_date
        FROM appointments
        WHERE doctor_id = ?
          AND appointment_date LIKE ?
          AND status IN (
            'pending',
            'approved',
            'completed',
            'rescheduled',
            'reschedule_pending'
          )
        """,
        (doctor_id, f"{date_str}%"),
    )

    taken = set()
    for r in cur.fetchall():
        try:
            t = _dt2.strptime(r["appointment_date"], "%Y-%m-%d %H:%M").strftime("%H:%M")
            taken.add(t)
        except Exception:
            pass

    # Return only slots NOT taken
    return [s for s in slots if s not in taken]



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

    # Clinic info + average rating
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

    # Owner + pets 
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

    return render_template(
        "owner_clinic_detail.html",
        clinic=clinic,
        doctors=doctors,
        pets=pets,
        doctor_slots={}, 
    )


@app.route("/owner/doctor/<int:doctor_id>/slots")
def owner_doctor_slots(doctor_id):
    """
    JSON API: ?date=YYYY-MM-DD  ->  ["09:00","09:30",...]
    Only for logged-in owners.
    """
    guard = _require_owner()
    if guard:
        return guard

    date_str = (request.args.get("date") or "").strip()
    if not date_str:
        return _jsonify([])

    conn = _get_conn()
    try:
        slots = _doctor_slots_for_date(conn, doctor_id, date_str)
        return _jsonify(slots)
    finally:
        conn.close()


# Booking 

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
        dt = _dt2.strptime(f"{date} {time_str}", "%Y-%m-%d %H:%M")
    except ValueError:
        flash("Please pick a valid date and time.", "warning")
        return redirect(url_for("owner_clinic_detail", clinic_id=clinic_id))

    appointment_dt = dt.strftime("%Y-%m-%d %H:%M")
    weekday_short = dt.strftime("%a").lower()  # 'mon', 'tue', ...

    conn = get_db()
    cur = conn.cursor()

    # 1) Check doctor's weekly availability (day of week)
    cur.execute("SELECT weekly_schedule FROM doctors WHERE id = ?", (doctor_id,))
    doctor_row = cur.fetchone()
    if not doctor_row:
        conn.close()
        flash("Doctor not found.", "danger")
        return redirect(url_for("owner_clinic_detail", clinic_id=clinic_id))

    weekly_schedule = (doctor_row["weekly_schedule"] or "").lower()

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

    #  2) Verify pet belongs to this owner 
    cur.execute(
        "SELECT 1 FROM pets WHERE id = ? AND owner_id = ?",
        (pet_id, owner["id"])
    )
    if not cur.fetchone():
        conn.close()
        flash("Invalid pet selected.", "danger")
        return redirect(url_for("owner_clinic_detail", clinic_id=clinic_id))

    # 3) Prevent double booking of same slot
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

    # 4) Insert appointment 
    cur.execute(
        """
        INSERT INTO appointments (pet_id, doctor_id, appointment_date, status)
        VALUES (?, ?, ?, 'pending')
        """,
        (pet_id, doctor_id, appointment_dt),
    )
    appt_id = cur.lastrowid
    conn.commit()
    conn.close()
    # 5) Send emails 
    appt = get_appointment_context(appt_id)
    if appt:
        pretty_status = _pretty_status(appt["status"] or "pending")
        pretty_dt = _pretty_datetime(appt["appointment_date"])

        owner_subject = f"Appointment Update: {pretty_status}"
        owner_body = (
            f"Hello {appt['owner_name'] or 'there'},\n\n"
            f"Your appointment request has been placed successfully.\n\n"
            f"Clinic: {appt['clinic_name']}\n"
            f"Doctor: {appt['doctor_name']}\n"
            f"Pet: {appt['pet_name']}\n"
            f"Time: {pretty_dt}\n"
            f"Status: {pretty_status}\n\n"
            f"You will receive another update when the clinic approves, cancels, or reschedules this appointment.\n\n"
            f"{EMAIL_SIGNATURE}\n"
        )
        send_email_async(appt["owner_email"], owner_subject, owner_body)

        clinic_subject = f"New Appointment Request: {pretty_status}"
        clinic_body = (
            f"Hello {appt['clinic_name'] or 'there'},\n\n"
            f"A new appointment request has been made.\n\n"
            f"Owner: {appt['owner_name']}\n"
            f"Pet: {appt['pet_name']}\n"
            f"Doctor: {appt['doctor_name']}\n"
            f"Time: {pretty_dt}\n"
            f"Status: {pretty_status}\n\n"
            f"Please review this request from your clinic dashboard.\n\n"
            f"{EMAIL_SIGNATURE}\n"
        )
        send_email_async(appt["clinic_email"], clinic_subject, clinic_body)


    flash("Appointment booked! Waiting for clinic confirmation.", "success")
    return redirect(url_for("owner_appointments"))



@app.route("/owner/appointments")
def owner_appointments():
    """
    Show all appointments for the logged-in owner.
    Reschedule-pending ones are shown at the top of 'Upcoming'.
    """

    guard = _require_owner()
    if guard:
        return guard

    conn = get_db()
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
            d.name               AS doctor_name,
            c.name               AS clinic_name,
            c.location           AS clinic_location,
            p.name               AS pet_name,
            p.animal_type        AS pet_animal_type,
            p.breed              AS pet_breed,
            p.gender             AS pet_gender,
            p.age                AS pet_age,
            p.vaccination_status AS pet_vaccination_status
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

    upcoming, completed, cancelled = [], [], []

    for r in rows:
        status = (r["status"] or "").lower()

        if status in ("completed", "done"):
            completed.append(r)
        elif status in ("cancelled", "canceled", "owner_cancelled", "clinic_cancelled"):
            cancelled.append(r)
        else:
            upcoming.append(r)

    def upcoming_sort_key(a):
        st = (a["status"] or "").lower()
        priority = 0 if st == "reschedule_pending" else 1
        return (priority, a["appointment_date"])

    upcoming = sorted(upcoming, key=upcoming_sort_key)

    return render_template(
        "owner_appointments.html",
        upcoming=upcoming,
        completed=completed,
        cancelled=cancelled,
    )



if __name__ == "__main__":
    app.run(debug=True)
