-- Enable TimescaleDB extension if desired later, standard PostgreSQL used here for portability
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Drop tables if resetting environment during development
DROP TABLE IF EXISTS weather_observations;
DROP TABLE IF EXISTS stations;

-- 1. Stations Table (Metadata)
CREATE TABLE stations (
    station_id VARCHAR(50) PRIMARY KEY,
    station_name VARCHAR(100) NOT NULL,
    latitude DECIMAL(9, 6) NOT NULL,
    longitude DECIMAL(9, 6) NOT NULL,
    elevation_m DECIMAL(6, 2),
    region VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Weather Observations Table (Time-Series Data)
CREATE TABLE weather_observations (
    observation_id SERIAL,
    station_id VARCHAR(50) REFERENCES stations(station_id) ON DELETE CASCADE,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    air_temp_c DECIMAL(4, 1),
    soil_temp_c DECIMAL(4, 1),
    soil_moisture_pct DECIMAL(5, 2),
    precipitation_mm DECIMAL(6, 2),
    wind_speed_ms DECIMAL(5, 2),
    solar_radiation_wm2 DECIMAL(6, 2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT pk_observation PRIMARY KEY (station_id, timestamp)
);

-- Create an index on timestamp for fast time-range filtering in Streamlit
CREATE INDEX idx_obs_timestamp ON weather_observations(timestamp);
CREATE INDEX idx_obs_station_time ON weather_observations(station_id, timestamp DESC);