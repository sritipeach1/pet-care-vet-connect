-- Drop tables for a clean re-init
DROP TABLE IF EXISTS pets;
DROP TABLE IF EXISTS owners;
DROP TABLE IF EXISTS doctors;
DROP TABLE IF EXISTS clinics;
DROP TABLE IF EXISTS users;

-- Main users table: shared by owners, clinics, admin
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
    is_verified INTEGER NOT NULL DEFAULT 0  -- 1 = verified clinic, 0 = pending
);

-- Extra profile for owners (your owner dashboard)
CREATE TABLE owners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    location TEXT NOT NULL DEFAULT '',
    password TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Pets for each owner
CREATE TABLE pets (
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

-- Clinic profile table for clinic users
CREATE TABLE clinics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE,
    name TEXT NOT NULL,
    license_number TEXT NOT NULL,
    email TEXT NOT NULL,
    contact_number TEXT NOT NULL,
    location TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Doctors belonging to a clinic
CREATE TABLE doctors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clinic_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    base_fee REAL NOT NULL,
    qualifications TEXT NOT NULL,
    rating REAL DEFAULT 0,
    weekly_schedule TEXT NOT NULL,
    FOREIGN KEY (clinic_id) REFERENCES clinics(id)
);
-- Appointments (for bookings and analytics)
CREATE TABLE appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pet_id INTEGER NOT NULL,
    doctor_id INTEGER NOT NULL,
    appointment_date DATETIME NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    rating INTEGER,        -- 1 to 5              
    FOREIGN KEY (pet_id) REFERENCES pets(id),
    FOREIGN KEY (doctor_id) REFERENCES doctors(id)
);