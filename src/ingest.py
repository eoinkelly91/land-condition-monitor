import os
import requests
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine, text
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

def init_db():
    """Ensures database tables and constraints are up to date."""
    with engine.begin() as conn:
        # Create stations table if not exists
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS stations (
                station_id VARCHAR(50) PRIMARY KEY,
                station_name VARCHAR(150),
                latitude FLOAT,
                longitude FLOAT,
                elevation_m FLOAT,
                region VARCHAR(100)
            );
        """))
        
        # Create weather_observations table if not exists
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS weather_observations (
                station_id VARCHAR(50),
                timestamp TIMESTAMP,
                air_temp_c FLOAT,
                soil_temp_c FLOAT,
                soil_moisture_pct FLOAT,
                precipitation_mm FLOAT,
                wind_speed_ms FLOAT,
                solar_radiation_wm2 FLOAT,
                is_forecast BOOLEAN DEFAULT FALSE,
                PRIMARY KEY (station_id, timestamp)
            );
        """))
        
        # Add is_forecast column if upgrading an existing table
        conn.execute(text("""
            ALTER TABLE weather_observations 
            ADD COLUMN IF NOT EXISTS is_forecast BOOLEAN DEFAULT FALSE;
        """))

def seed_stations():
    """Ensures multiple diverse monitoring stations exist."""
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
                    "station_id": station[0], "station_name": station[1],
                    "latitude": station[2], "longitude": station[3],
                    "elevation_m": station[4], "region": station[5]
                }
            )
    print("✓ Station network verified.")

def fetch_and_store_weather():
    """Queries Open-Meteo API for historical and 7-day forecast data for all stations."""
    stations_df = pd.read_sql("SELECT station_id, latitude, longitude, station_name FROM stations;", engine)
    
    now = datetime.now()

    for _, station in stations_df.iterrows():
        station_id = station['station_id']
        lat = station['latitude']
        lon = station['longitude']
        name = station['station_name']
        
        print(f"\nFetching historical & forecast telemetry for: {name} ({station_id})...")
        
        # Open-Meteo API Endpoint including both past_days and forecast_days
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}"
            f"&hourly=temperature_2m,relative_humidity_2m,precipitation,"
            f"soil_temperature_0cm,soil_moisture_0_to_1cm,wind_speed_10m,shortwave_radiation"
            f"&past_days=7&forecast_days=7"
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
            
        timestamps = pd.to_datetime(hourly['time'])
        
        # Build DataFrame and tag whether each row is a forecast (> current time)
        df = pd.DataFrame({
            'station_id': station_id,
            'timestamp': timestamps,
            'air_temp_c': hourly.get('temperature_2m'),
            'soil_temp_c': hourly.get('soil_temperature_0cm'),
            'soil_moisture_pct': [m * 100 if m is not None else None for m in hourly.get('soil_moisture_0_to_1cm', [])],
            'precipitation_mm': hourly.get('precipitation'),
            'wind_speed_ms': hourly.get('wind_speed_10m'),
            'solar_radiation_wm2': hourly.get('shortwave_radiation'),
            'is_forecast': [t > pd.Timestamp(now) for t in timestamps]
        })
        
        df = df.dropna(subset=['timestamp'])
        
        # Upsert into PostgreSQL (updates forecasts and observations cleanly on conflict)
        with engine.begin() as conn:
            for _, row in df.iterrows():
                conn.execute(
                    text("""
                        INSERT INTO weather_observations 
                        (station_id, timestamp, air_temp_c, soil_temp_c, soil_moisture_pct, precipitation_mm, wind_speed_ms, solar_radiation_wm2, is_forecast)
                        VALUES (:station_id, :timestamp, :air_temp_c, :soil_temp_c, :soil_moisture_pct, :precipitation_mm, :wind_speed_ms, :solar_radiation_wm2, :is_forecast)
                        ON CONFLICT (station_id, timestamp) 
                        DO UPDATE SET 
                            air_temp_c = EXCLUDED.air_temp_c,
                            soil_temp_c = EXCLUDED.soil_temp_c,
                            soil_moisture_pct = EXCLUDED.soil_moisture_pct,
                            precipitation_mm = EXCLUDED.precipitation_mm,
                            wind_speed_ms = EXCLUDED.wind_speed_ms,
                            solar_radiation_wm2 = EXCLUDED.solar_radiation_wm2,
                            is_forecast = EXCLUDED.is_forecast;
                    """),
                    {
                        "station_id": row['station_id'],
                        "timestamp": row['timestamp'],
                        "air_temp_c": row['air_temp_c'],
                        "soil_temp_c": row['soil_temp_c'],
                        "soil_moisture_pct": row['soil_moisture_pct'],
                        "precipitation_mm": row['precipitation_mm'],
                        "wind_speed_ms": row['wind_speed_ms'],
                        "solar_radiation_wm2": row['solar_radiation_wm2'],
                        "is_forecast": row['is_forecast']
                    }
                )
        print(f"  ✓ Successfully stored {len(df)} records (Historical & Forecast) for {station_id}.")

if __name__ == "__main__":
    init_db()
    seed_stations()
    fetch_and_store_weather()