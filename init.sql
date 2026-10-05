CREATE TABLE IF NOT EXISTS parkings (
    name VARCHAR(255) PRIMARY KEY,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    address TEXT,
    manager VARCHAR(255),
    category VARCHAR(100),
    total_spots INT
);

-- Columns added after the first release; ALTER keeps existing databases in sync.
ALTER TABLE parkings
    ADD COLUMN IF NOT EXISTS start_date TEXT,
    ADD COLUMN IF NOT EXISTS opening_hours JSONB,
    ADD COLUMN IF NOT EXISTS tariffs JSONB,
    ADD COLUMN IF NOT EXISTS levels INT,
    ADD COLUMN IF NOT EXISTS total_places JSONB,
    ADD COLUMN IF NOT EXISTS dimensions JSONB,
    ADD COLUMN IF NOT EXISTS accepted_payment_method TEXT,
    ADD COLUMN IF NOT EXISTS allowed_vehicle_type TEXT,
    ADD COLUMN IF NOT EXISTS additional_security TEXT,
    ADD COLUMN IF NOT EXISTS manager_email TEXT,
    ADD COLUMN IF NOT EXISTS manager_telephone TEXT,
    ADD COLUMN IF NOT EXISTS operator_telephone TEXT;

CREATE TABLE IF NOT EXISTS parking_occupancy_logs (
    id BIGSERIAL PRIMARY KEY,
    parking_name VARCHAR(255) REFERENCES parkings(name),
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    free_public INT,
    free_disabled INT,
    free_electric INT,
    total_free INT,
    raw_payload JSONB
);

CREATE INDEX IF NOT EXISTS idx_occupancy_name_time 
ON parking_occupancy_logs (parking_name, recorded_at);