DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    phone TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('owner', 'clinic', 'admin')),
    clinic_name TEXT,
    clinic_location TEXT,
    clinic_license TEXT,
    is_verified INTEGER NOT NULL DEFAULT 0  -- for clinics, for later modules
);