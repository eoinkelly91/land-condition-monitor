import os
import requests
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy import text
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Build database connection string
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_HOST = "localhost"
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL)

from sqlalchemy import text

def seed_stations():
    """Ensures multiple diverse monitoring stations exist without crashing on duplicates."""
    stations_data = [
        ("STN_001", "Home Farm - River Paddock (Heavy Clay)", 53.2707, -8.9054, 30.0, "Galway"),
        ("STN_002", "Hill Field - North Pasture (Free-Draining)", 53.3500, -8.5500, 75.0, "Roscommon"),
        ("STN_003", "Valley Tillage Plot (Loam)", 53.1500, -7.9000, 45.0, "Offaly")
    ]
    
    with engine.begin() as conn:
        for station in stations_data:
            conn.execute(
                text("""
                    INSERT INTO stations (station_id, station_name, latitude, longitude, elevation_m, region)
                    VALUES (:station_id, :station_name, :latitude, :longitude, :elevation_m, :region)
                    ON CONFLICT (station_id) DO NOTHING;
                """),
                {
                    "station_id": station[0],
                    "station_name": station[1],
                    "latitude": station[2],
                    "longitude": station[3],
                    "elevation_m": station[4],
                    "region": station[5]
                }
            )
    print("✓ Station network seeded successfully.")

def fetch_and_store_weather():
    """Queries Open-Meteo API for all registered stations and stores observations."""
    # Fetch all active stations from the database
    stations_df = pd.read_sql("SELECT station_id, latitude, longitude, station_name FROM stations;", engine)
    
    if stations_df.empty:
        print("No stations found. Seeding stations first...")
        seed_stations()
        stations_df = pd.read_sql("SELECT station_id, latitude, longitude, station_name FROM stations;", engine)

    for _, station in stations_df.iterrows():
        station_id = station['station_id']
        lat = station['latitude']
        lon = station['longitude']
        name = station['station_name']
        
        print(f"\nFetching weather data for: {name} ({station_id})...")
        
        # Open-Meteo API Endpoint with hourly weather and soil variables
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}"
            f"&hourly=temperature_2m,relative_humidity_2m,precipitation,"
            f"soil_temperature_0cm,soil_moisture_0_to_1cm,wind_speed_10m,shortwave_radiation"
            f"&past_days=7"
        )
        
        response = requests.get(url)
        if response.status_code != 200:
            print(f"  ✗ Failed to fetch data for {station_id}: HTTP {response.status_code}")
            continue
            
        data = response.json()
        hourly = data.get("hourly", {})
        
        if not hourly:
            print(f"  ✗ No hourly data returned for {station_id}.")
            continue
            
        # Build DataFrame
        df = pd.DataFrame({
            'station_id': station_id,
            'timestamp': pd.to_datetime(hourly['time']),
            'air_temp_c': hourly.get('temperature_2m'),
            'soil_temp_c': hourly.get('soil_temperature_0cm'),
            'soil_moisture_pct': [m * 100 if m is not None else None for m in hourly.get('soil_moisture_0_to_1cm', [])],
            'precipitation_mm': hourly.get('precipitation'),
            'wind_speed_ms': hourly.get('wind_speed_10m'),
            'solar_radiation_wm2': hourly.get('shortwave_radiation')
        })
        
        # Drop rows where timestamp is null
        df = df.dropna(subset=['timestamp'])
        
        # Upsert / Append to PostgreSQL database
        # Using 'append' with a primary key constraint or replacing existing records cleanly
        try:
            df.to_sql('weather_observations', engine, if_exists='append', index=False, method='multi')
            print(f"  ✓ Successfully stored {len(df)} observation records for {station_id}.")
        except Exception as e:
            print(f"  ℹ Note on insertion (likely duplicates skipped): {e}")

if __name__ == "__main__":
    seed_stations()
    fetch_and_store_weather()