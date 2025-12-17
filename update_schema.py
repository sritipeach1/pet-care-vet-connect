import sqlite3
import os

# Connect to the database
conn = sqlite3.connect("instance/petcare.db")
cur = conn.cursor()

try:
    # Add the columns
    cur.execute("ALTER TABLE owners ADD COLUMN is_premium INTEGER DEFAULT 0")
    cur.execute("ALTER TABLE owners ADD COLUMN subscription_expiry TEXT")
    cur.execute("ALTER TABLE owners ADD COLUMN reward_points INTEGER DEFAULT 0")
    print("Columns added successfully.")
except Exception as e:
    print(f"Skipped column addition (might already exist): {e}")

# Create the table
cur.execute("""
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    trx_id TEXT NOT NULL,
    payment_method TEXT DEFAULT 'bKash',
    payment_date TEXT NOT NULL,
    status TEXT DEFAULT 'completed',
    FOREIGN KEY (owner_id) REFERENCES owners (id)
)
""")
print("Payments table check/creation done.")

conn.commit()
conn.close()