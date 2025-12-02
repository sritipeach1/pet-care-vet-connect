from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os

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


@app.route("/logout")
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
        dashboard_type = "Pet Owner Dashboard (later: pet profile, appointments, history)"
    elif role == "clinic":
        dashboard_type = "Vet Clinic Dashboard (later: schedule, bookings, pet records)"
    elif role == "admin":
        dashboard_type = "Admin Dashboard (later: approve clinics, monitor system)"
    else:
        dashboard_type = "Unknown role"

    return render_template("dashboard.html", dashboard_type=dashboard_type)


if __name__ == "__main__":
    app.run(debug=True)
