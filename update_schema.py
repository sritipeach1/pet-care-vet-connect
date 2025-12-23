import sqlite3

DB_PATH = "instance/petcare.db"

def add_column_if_missing(cur, table, column_def):
    col_name = column_def.split()[0]
    cur.execute(f"PRAGMA table_info({table})")
    existing_cols = [row[1] for row in cur.fetchall()]
    if col_name not in existing_cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
        print(f"✅ Added column: {col_name}")
    else:
        print(f"⚠️ Column already exists: {col_name}")


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # ✅ Add missing review columns in appointments
    add_column_if_missing(cur, "appointments", "review_text TEXT")
    add_column_if_missing(cur, "appointments", "clinic_rating INTEGER")
    add_column_if_missing(cur, "appointments", "clinic_review_text TEXT")
    add_column_if_missing(cur, "appointments", "reviewed_at TEXT")

    conn.commit()
    conn.close()
    print("✅ Schema updated successfully!")

if __name__ == "__main__":
    main()
