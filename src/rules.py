import os
import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Build database connection string
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_HOST = "localhost"
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL)

def evaluate_agronomic_rules(station_id="STN_001"):
    """
    Queries recent telemetry from PostgreSQL and evaluates land condition rules
    for livestock turnout and sowing readiness.
    """
    # Fetch the last 72 hours of observation data for the station
    query = f"""
        SELECT timestamp, air_temp_c, soil_temp_c, soil_moisture_pct, precipitation_mm, wind_speed_ms
        FROM weather_observations
        WHERE station_id = '{station_id}'
        ORDER BY timestamp DESC
        LIMIT 72;
    """
    
    df = pd.read_sql(query, engine)
    
    if df.empty:
        print(f"No observation data found for station {station_id}. Run ingest.py first.")
        return None

    # Sort chronologically for rolling calculations
    df = df.sort_values("timestamp").reset_index(drop=True)

    # --- Rule 1: Livestock Turnout Suitability ---
    recent_rain_48h = df['precipitation_mm'].tail(48).sum()
    latest_soil_moisture = df['soil_moisture_pct'].iloc[-1]

    turnout_safe = True
    turnout_reasons = []

    # Threshold: Soil moisture > 75% or 48h rain > 15mm risks severe poaching
    if latest_soil_moisture > 75.0:
        turnout_safe = False
        turnout_reasons.append(f"Soil moisture is high ({latest_soil_moisture:.1f}% > 75%). Risk of soil compaction.")
    
    if recent_rain_48h > 15.0:
        turnout_safe = False
        turnout_reasons.append(f"Recent 48h rainfall is heavy ({recent_rain_48h:.1f} mm > 15mm). Ground is saturated.")

    turnout_status = "GREEN - Suitable for Turnout" if turnout_safe else "RED - Unsuitable (Risk of Poaching)"

    # --- Rule 2: Sowing Readiness Windows ---
    recent_soil_temp = df['soil_temp_c'].tail(48).mean()
    recent_rain_24h = df['precipitation_mm'].tail(24).sum()

    sowing_safe = True
    sowing_reasons = []

    # Threshold: Soil temperature needs to average >= 6.0°C over 48h for reliable germination
    if pd.isna(recent_soil_temp) or recent_soil_temp < 6.0:
        sowing_safe = False
        sowing_reasons.append(f"Soil temperature is too low (48h avg: {recent_soil_temp:.1f}°C < 6.0°C threshold).")

    if recent_rain_24h > 5.0:
        sowing_safe = False
        sowing_reasons.append(f"Recent 24h rainfall ({recent_rain_24h:.1f} mm) creates unfavorable seedbed conditions for machinery.")

    sowing_status = "GREEN - Sowing Window Open" if sowing_safe else "RED - Sowing Conditions Unfavorable"

    # --- Print Report ---
    print(f"\n{'='*55}")
    print(f" AGRONOMIC DECISION REPORT: {station_id}")
    print(f"{'='*55}")
    print(f"Evaluation Timestamp: {df['timestamp'].iloc[-1]}")
    
    print(f"\n[Livestock Turnout]: {turnout_status}")
    if turnout_safe:
        print("  ✓ Soil moisture and recent precipitation are within safe grazing thresholds.")
    for r in turnout_reasons:
        print(f"  ✗ {r}")

    print(f"\n[Sowing Readiness]: {sowing_status}")
    if sowing_safe:
        print("  ✓ Soil temperature and field dryness support germination and machinery access.")
    for r in sowing_reasons:
        print(f"  ✗ {r}")
    print(f"{'='*55}\n")

    return {
        "station_id": station_id,
        "turnout_status": turnout_status,
        "sowing_status": sowing_status
    }

if __name__ == "__main__":
    evaluate_agronomic_rules()