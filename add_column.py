import sqlite3

conn = sqlite3.connect("instance/petcare.db")
cur = conn.cursor()
cur.execute("ALTER TABLE pets ADD COLUMN photo_filename TEXT;")
conn.commit()
conn.close()

print("Column added successfully!")
