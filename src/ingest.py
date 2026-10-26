import os
import requests
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Build database connection string from environment variables
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_HOST = "localhost"
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL)

def ingest_station_data():
    # 1. Define a sample monitoring station (e.g., regional test station)
    station_id = "STN_001"
    station_name = "Galway Agricultural Test Site"
    latitude = 53.2707
    longitude = -9.0568
    elevation_m = 25.0
    region = "Connacht"

    # Insert or update station metadata
    station_df = pd.DataFrame([{
        "station_id": station_id,
        "station_name": station_name,
        "latitude": latitude,
        "longitude": longitude,
        "elevation_m": elevation_m,
        "region": region
    }])
    
    # Write station metadata to PostgreSQL (upsert behavior using pandas to_sql)
    station_df.to_sql("stations", engine, if_exists="append", index=False, method="multi")
    print(f"Station {station_id} metadata successfully registered.")

    # 2. Fetch live weather & soil data from Open-Meteo API
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": [
            "temperature_2m",
            "soil_temperature_0cm",
            "soil_moisture_0_to_7cm",
            "precipitation",
            "wind_speed_10m",
            "shortwave_radiation"
        ],
        "past_days": 1,
        "forecast_days": 2
    }

    print("Fetching weather and soil telemetry from Open-Meteo...")
    response = requests.get(url, params=params)
    
    if response.status_code != 200:
        print(f"Failed to fetch data: {response.status_code} - {response.text}")
        return

    data = response.json()
    hourly = data["hourly"]

    # 3. Parse JSON parallel arrays into a structured Pandas DataFrame
    obs_df = pd.DataFrame({
        "station_id": station_id,
        "timestamp": pd.to_datetime(hourly["time"]),
        "air_temp_c": hourly["temperature_2m"],
        "soil_temp_c": hourly["soil_temperature_0cm"],
        "soil_moisture_pct": [m * 100 if m is not None else None for m in hourly["soil_moisture_0_to_7cm"]], # Convert volumetric ratio to percentage
        "precipitation_mm": hourly["precipitation"],
        "wind_speed_ms": [w / 3.6 if w is not None else None for w in hourly["wind_speed_10m"]], # Convert km/h to m/s
        "solar_radiation_wm2": hourly["shortwave_radiation"]
    })

    # Drop rows with missing critical timestamps
    obs_df = obs_df.dropna(subset=["timestamp"])

    # 4. Load observations into PostgreSQL
    try:
        # Using 'append' with conflict handling or raw insert depending on primary key constraints
        obs_df.to_sql("weather_observations", engine, if_exists="append", index=False, method="multi")
        print(f"Successfully loaded {len(obs_df)} observation records into PostgreSQL!")
    except Exception as e:
        print(f"Error loading observations into database (likely duplicate primary keys from existing data): {e}")

if __name__ == "__main__":
    ingest_station_data()