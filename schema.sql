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
-- Extra tables for Faria's Owner Dashboard & Pets
CREATE TABLE IF NOT EXISTS owners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    location TEXT NOT NULL,
    password TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS pets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    age TEXT NOT NULL,
    animal_type TEXT NOT NULL,
    breed TEXT NOT NULL,
    gender TEXT NOT NULL,
    vaccination_status TEXT NOT NULL,
    FOREIGN KEY (owner_id) REFERENCES owners(id)
);
