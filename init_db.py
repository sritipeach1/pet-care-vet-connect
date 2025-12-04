import sqlite3

connection = sqlite3.connect('petcare.db')

with open('schema.sql') as f:
    connection.executescript(f.read())

cur = connection.cursor()

# Create a default Admin user so you can log in
# Note: In a real app, password should be hashed, but for testing we'll use plain text if your login allows it, 
# or you can use the hash format your team uses. 
# Assuming simple text for now based on your skill level:
cur.execute("INSERT INTO users (name, email, password_hash, role, is_verified) VALUES (?, ?, ?, ?, ?)",
            ('Super Admin', 'admin@petcare.com', 'admin123', 'admin', 1)
            )

# Create a Dummy Pending Clinic for you to test approving
cur.execute("INSERT INTO users (name, email, password_hash, role, clinic_name, clinic_location, clinic_license, is_verified) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ('Test Clinic Owner', 'clinic@test.com', '1234', 'clinic', 'Happy Pets Clinic', 'Dhaka', 'LIC-999', 0)
            )

connection.commit()
connection.close()
print("Database initialized successfully with the Team Schema!")