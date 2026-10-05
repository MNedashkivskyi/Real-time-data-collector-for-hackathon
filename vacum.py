import os
import json
import time
import requests
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import Json
from datetime import datetime

load_dotenv()

# Database connection settings
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "parking_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgres")
DB_PORT = os.getenv("DB_PORT", "5432")

# Warsaw Open Data API configuration
API_URL = os.getenv(
    "WARSAW_API_URL", 
    "https://dane.um.warszawa.pl/api/action/get_m_parkingi_wolne_miejsca"
)
API_TOKEN = (os.getenv("WARSAW_API_TOKEN") or os.getenv("WARSAW_API_KEY") or os.getenv("API_TOKEN") or "").strip(' "\'')

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "init.sql")

def to_int(value, default=0):
    """Convert a spot count to int, falling back to a default for missing or malformed values."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def to_text(value):
    """Store a descriptive field as text, serializing it if the API sends a list or object instead."""
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)

def to_json(value):
    """Wrap a structured field for a JSONB column, keeping missing values as NULL."""
    return Json(value) if value is not None else None

def to_float(value):
    """Convert a coordinate to float, treating missing or malformed values as NULL."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def get_db_connection():
    """Establish and maintain a resilient database connection with auto-retry."""
    while True:
        try:
            return psycopg2.connect(
                host=DB_HOST,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
                port=DB_PORT
            )
        except psycopg2.OperationalError as e:
            print(f"[{datetime.now()}] Database connection error, retrying in 3 seconds: {e}")
            time.sleep(3)

def ensure_schema():
    """Create tables and indexes if they do not exist yet (init.sql is idempotent)."""
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema_sql = f.read()

    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(schema_sql)
        conn.commit()
        print(f"[{datetime.now()}] Database schema is ready.")
    finally:
        conn.close()

def fetch_parking_data():
    """Fetch live parking occupancy data from the Warsaw Open Data API."""
    headers = {}
    if API_TOKEN:
        headers["Authorization"] = API_TOKEN
    try:
        response = requests.post(API_URL, headers=headers, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        print(f"[{datetime.now()}] Error fetching parking data: {e}")
        return None

def save_data(data):
    """Parse API response and persist parking registry and occupancy logs into PostgreSQL."""
    if not data:
        print(f"[{datetime.now()}] No data to save.")
        return

    # 1. Check known primary keys (or accept a bare top-level list)
    parkings_list = None
    if isinstance(data, list):
        parkings_list = data
    elif isinstance(data, dict):
        parkings_list = data.get("Parkings") or data.get("carParks")

        # 2. Dynamic fallback: extract the first non-empty list found in the payload
        if not parkings_list:
            for val in data.values():
                if isinstance(val, list) and len(val) > 0:
                    parkings_list = val
                    break

    # 3. Abort gracefully if no list structure matches, showing what the API actually returned
    if not parkings_list:
        print(f"[{datetime.now()}] No parking list found in response: {str(data)[:500]}")
        return

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        saved = 0
        skipped = 0
        for item in parkings_list:
            name = item.get("name") if isinstance(item, dict) else None
            if not name:
                skipped += 1
                continue

            # Isolate each record so one malformed entry does not discard the whole batch
            cur.execute("SAVEPOINT parking_item")
            try:
                # Parse coordinates and descriptive metadata
                lat = to_float(item.get("latitude"))
                lon = to_float(item.get("longitude"))
                address = item.get("adress") or ""
                manager = item.get("manager") or ""
                category = item.get("parkingCategory") or ""

                # Calculate total parking capacity across all levels
                total_spots = 0
                for lvl in item.get("total_places") or []:
                    total_spots += to_int(lvl.get("standard")) + to_int(lvl.get("disabled")) + to_int(lvl.get("electric"))

                # Insert or update static parking facility record
                cur.execute("""
                    INSERT INTO parkings (
                        name, latitude, longitude, address, manager, category, total_spots,
                        start_date, opening_hours, tariffs, levels, total_places, dimensions,
                        accepted_payment_method, allowed_vehicle_type, additional_security,
                        manager_email, manager_telephone, operator_telephone
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (name) DO UPDATE 
                    SET latitude = EXCLUDED.latitude,
                        longitude = EXCLUDED.longitude,
                        address = EXCLUDED.address,
                        manager = EXCLUDED.manager,
                        category = EXCLUDED.category,
                        total_spots = EXCLUDED.total_spots,
                        start_date = EXCLUDED.start_date,
                        opening_hours = EXCLUDED.opening_hours,
                        tariffs = EXCLUDED.tariffs,
                        levels = EXCLUDED.levels,
                        total_places = EXCLUDED.total_places,
                        dimensions = EXCLUDED.dimensions,
                        accepted_payment_method = EXCLUDED.accepted_payment_method,
                        allowed_vehicle_type = EXCLUDED.allowed_vehicle_type,
                        additional_security = EXCLUDED.additional_security,
                        manager_email = EXCLUDED.manager_email,
                        manager_telephone = EXCLUDED.manager_telephone,
                        operator_telephone = EXCLUDED.operator_telephone;
                """, (
                    name, lat, lon, address, manager, category, total_spots,
                    to_text(item.get("start_date")),
                    to_json(item.get("opening_hours")),
                    to_json(item.get("tariffs")),
                    to_int(item.get("levels"), None),
                    to_json(item.get("total_places")),
                    to_json(item.get("dimensions")),
                    to_text(item.get("acceptedPaymentMethod")),
                    to_text(item.get("allowedVehicleType")),
                    to_text(item.get("additionalSecurity")),
                    to_text(item.get("managerEmail")),
                    to_text(item.get("managerTelephone")),
                    to_text(item.get("operatorTelephone")),
                ))

                # Parse available spot metrics with safe fallback to zero
                free_info = item.get("free_places_total") or {}
                free_public = to_int(free_info.get("public"))
                free_disabled = to_int(free_info.get("disabled"))
                free_electric = to_int(free_info.get("electric"))
                total_free = free_public + free_disabled + free_electric

                # Append time-series occupancy measurement
                cur.execute("""
                    INSERT INTO parking_occupancy_logs 
                    (parking_name, free_public, free_disabled, free_electric, total_free, raw_payload)
                    VALUES (%s, %s, %s, %s, %s, %s);
                """, (name, free_public, free_disabled, free_electric, total_free, Json(item)))

                cur.execute("RELEASE SAVEPOINT parking_item")
                saved += 1
            except Exception as e:
                cur.execute("ROLLBACK TO SAVEPOINT parking_item")
                skipped += 1
                print(f"[{datetime.now()}] Skipping parking '{name}': {e}")

        conn.commit()
        print(f"[{datetime.now()}] Saved {saved} parking entries to the database ({skipped} skipped).")
    except Exception as e:
        conn.rollback()
        print(f"[{datetime.now()}] Error saving data to the database: {e}")
    finally:
        cur.close()
        conn.close()

def fetch_and_save():
    """Single fetch and storage cycle."""
    payload = fetch_parking_data()
    if payload:
        save_data(payload)

def main():
    """Main execution loop polling the API every 5 minutes."""
    print(f"[{datetime.now()}] Starting parking data fetcher...")
    ensure_schema()
    while True:
        try:
            fetch_and_save()
        except Exception as e:
            print(f"[{datetime.now()}] Unexpected error in fetch cycle: {e}")
        time.sleep(300)

if __name__ == "__main__":
    main()