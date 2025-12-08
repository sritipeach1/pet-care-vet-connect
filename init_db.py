import sqlite3
import os
from werkzeug.security import generate_password_hash # Import the hashing tool

# 1. Correct Path (inside instance folder)
db_folder = "instance"
if not os.path.exists(db_folder):
    os.makedirs(db_folder)

db_path = os.path.join(db_folder, "petcare.db")
connection = sqlite3.connect(db_path)

with open('schema.sql') as f:
    connection.executescript(f.read())

cur = connection.cursor()

# 2. Correct Password Hashing
# We must encrypt 'admin123' so app.py can read it
admin_pass = generate_password_hash('admin123')
clinic_pass = generate_password_hash('1234')

# Create Default Admin
print("Creating Admin...")
cur.execute("INSERT INTO users (name, email, password_hash, role, is_verified) VALUES (?, ?, ?, ?, ?)",
            ('Super Admin', 'admin@petcare.com', admin_pass, 'admin', 1)
            )

# Create Dummy Pending Clinic
print("Creating Test Clinic...")
cur.execute("INSERT INTO users (name, email, password_hash, role, clinic_name, clinic_location, clinic_license, is_verified) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ('Test Clinic Owner', 'clinic@test.com', clinic_pass, 'clinic', 'Happy Pets Clinic', 'Dhaka', 'LIC-999', 0)
            )

connection.commit()
connection.close()
print(f"Database initialized successfully at {db_path}!")