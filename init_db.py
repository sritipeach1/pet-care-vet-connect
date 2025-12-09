import sqlite3
import os
from werkzeug.security import generate_password_hash

# 1. Setup Paths
db_folder = "instance"
if not os.path.exists(db_folder):
    os.makedirs(db_folder)
db_path = os.path.join(db_folder, "petcare.db")

# 2. Delete Old DB (The "Clean Slate" for setup only)
if os.path.exists(db_path):
    os.remove(db_path)
    print(f"Deleted old database at {db_path}")

# 3. Connect and Build Tables
conn = sqlite3.connect(db_path)
with open("schema.sql", "r") as f:
    conn.executescript(f.read())
print("Tables created successfully.")

cur = conn.cursor()

# A. Create ADMIN
admin_pass = generate_password_hash("admin123")
cur.execute("""
    INSERT INTO users (name, email, password_hash, role, is_verified) 
    VALUES (?, ?, ?, ?, ?)
""", ("System Admin", "admin@petconnect.com", admin_pass, "admin", 1))

# B. Create a VERIFIED CLINIC (For Analytics Demo)
clinic_pass = generate_password_hash("1234")
cur.execute("""
    INSERT INTO users (name, email, phone, password_hash, role, clinic_name, clinic_location, clinic_license, is_verified) 
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
""", ("Happy Pets Manager", "clinic@test.com", "01700000000", clinic_pass, "clinic", "Happy Pets Clinic", "Dhaka", "LIC-101", 1))

# Get Clinic ID
clinic_user_id = cur.lastrowid
# Create Clinic Profile Entry
cur.execute("INSERT INTO clinics (user_id, name, license_number, email, contact_number, location) VALUES (?, ?, ?, ?, ?, ?)",
            (clinic_user_id, "Happy Pets Clinic", "LIC-101", "clinic@test.com", "01700000000", "Dhaka"))
clinic_id = cur.lastrowid

# C. Create DOCTORS for that Clinic
cur.execute("INSERT INTO doctors (clinic_id, name, email, base_fee, qualifications, weekly_schedule) VALUES (?, ?, ?, ?, ?, ?)",
            (clinic_id, "Dr. Rahim", "rahim@vet.com", 500.0, "MBBS, DVM", "Sun 10:00 - 18:00"))
doc1_id = cur.lastrowid

cur.execute("INSERT INTO doctors (clinic_id, name, email, base_fee, qualifications, weekly_schedule) VALUES (?, ?, ?, ?, ?, ?)",
            (clinic_id, "Dr. Karim", "karim@vet.com", 800.0, "PhD Veterinary", "Mon 12:00 - 20:00"))
doc2_id = cur.lastrowid

# D. Create a PENDING CLINIC (To show Admin Approval)
pending_pass = generate_password_hash("1234")
cur.execute("""
    INSERT INTO users (name, email, password_hash, role, clinic_name, clinic_location, clinic_license, is_verified) 
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""", ("Pending User", "pending@test.com", pending_pass, "clinic", "New Vet Center", "Chittagong", "LIC-999", 0))

# E. Create an OWNER (To show Pet Dashboard)
owner_pass = generate_password_hash("1234")
cur.execute("""
    INSERT INTO users (name, email, password_hash, role, is_verified) 
    VALUES (?, ?, ?, ?, ?)
""", ("Faria Owner", "owner@test.com", owner_pass, "owner", 1))
owner_user_id = cur.lastrowid

# Create Owner Profile
cur.execute("INSERT INTO owners (user_id, name, email) VALUES (?, ?, ?)", (owner_user_id, "Faria Owner", "owner@test.com"))
owner_id = cur.lastrowid

# Add a Pet
cur.execute("""
    INSERT INTO pets (owner_id, name, age, animal_type, breed, gender, vaccination_status) 
    VALUES (?, ?, ?, ?, ?, ?, ?)
""", (owner_id, "Mimi", "2 years", "Cat", "Persian", "Female", "Fully Vaccinated"))
pet_id = cur.lastrowid

# F. Create APPOINTMENTS (To show Analytics Reports)
# 1. Completed Appointment (Earns money)
cur.execute("INSERT INTO appointments (pet_id, doctor_id, appointment_date, status, rating) VALUES (?, ?, '2025-10-01', 'completed', 5)", (pet_id, doc1_id))
# 2. Another Completed
cur.execute("INSERT INTO appointments (pet_id, doctor_id, appointment_date, status, rating) VALUES (?, ?, '2025-10-02', 'completed', 4)", (pet_id, doc1_id))
# 3. Pending Appointment
cur.execute("INSERT INTO appointments (pet_id, doctor_id, appointment_date, status, rating) VALUES (?, ?, '2025-12-10', 'pending', NULL)", (pet_id, doc2_id))

conn.commit()
conn.close()


print("Login Credentials for Presentation:")

