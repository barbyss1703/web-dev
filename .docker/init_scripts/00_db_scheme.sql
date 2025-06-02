CREATE DATABASE flightproj;
\c flightproj;


CREATE TABLE IF NOT EXISTS flights (
    flight_id SERIAL PRIMARY KEY,
    total_seats INTEGER,
    available_seats INTEGER
);
CREATE TABLE IF NOT EXISTS reservations (
    booking_id TEXT PRIMARY KEY,
    flight_id INTEGER,
    seat_number TEXT
);
CREATE TABLE IF NOT EXISTS bookings (
    booking_id SERIAL PRIMARY KEY,
    flight_id INTEGER,
    user_id TEXT,
    seat_number TEXT,
    status TEXT
);
CREATE TABLE IF NOT EXISTS payments (
    payment_id SERIAL PRIMARY KEY,
    booking_id INTEGER,
    amount FLOAT,
    status TEXT
);

CREATE TABLE IF NOT EXISTS inbox (
    event_id TEXT PRIMARY KEY,
    event_type TEXT,
    payload JSONB
);

CREATE TABLE IF NOT EXISTS outbox (
    event_id TEXT PRIMARY KEY,
    event_type TEXT,
    payload JSONB
);
