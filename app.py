import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine
import os
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

# Page configuration
st.set_page_config(
    page_title="Land Condition Monitor",
    page_icon="🌾",
    layout="wide"
)

st.title("🌾 Land Condition Monitor")
st.markdown("AgTech Regional Decision-Support Platform for Livestock Turnout & Sowing Readiness")

# --- Sidebar Controls ---
st.sidebar.header("Configuration")

# Fetch available stations from database
try:
    stations_df = pd.read_sql("SELECT station_id, station_name, region FROM stations;", engine)
except Exception as e:
    st.error(f"Could not connect to database. Ensure Docker container is running. Error: {e}")
    st.stop()

if stations_df.empty:
    st.warning("No stations found in database. Please run `python src/ingest.py` first.")
    st.stop()

selected_station_name = st.sidebar.selectbox(
    "Select Monitoring Station",
    stations_df['station_name']
)

selected_station_id = stations_df.loc[
    stations_df['station_name'] == selected_station_name, 'station_id'
].values[0]

# --- Fetch Station Observations ---
@st.cache_data(ttl=600)
def load_data(station_id):
    query = f"""
        SELECT timestamp, air_temp_c, soil_temp_c, soil_moisture_pct, precipitation_mm, wind_speed_ms, solar_radiation_wm2
        FROM weather_observations
        WHERE station_id = '{station_id}'
        ORDER BY timestamp ASC;
    """
    return pd.read_sql(query, engine)

df = load_data(selected_station_id)

if df.empty:
    st.warning(f"No observation data available for {selected_station_name}.")
    st.stop()

# --- Rule Engine Logic for UI ---
latest_soil_moisture = df['soil_moisture_pct'].iloc[-1]
recent_rain_48h = df['precipitation_mm'].tail(48).sum()
recent_soil_temp = df['soil_temp_c'].tail(48).mean()
recent_rain_24h = df['precipitation_mm'].tail(24).sum()

turnout_safe = latest_soil_moisture <= 75.0 and recent_rain_48h <= 15.0
sowing_safe = recent_soil_temp >= 6.0 and recent_rain_24h <= 5.0

# --- Status Display ---
st.subheader("Operational Decision Status")
col1, col2 = st.columns(2)

with col1:
    if turnout_safe:
        st.success("**Livestock Turnout:** GREEN - Suitable for Turnout")
    else:
        st.error("**Livestock Turnout:** RED - Unsuitable (Risk of Poaching)")

with col2:
    if sowing_safe:
        st.success("**Sowing Readiness:** GREEN - Sowing Window Open")
    else:
        st.error("**Sowing Readiness:** RED - Conditions Unfavorable")

st.markdown("---")

# --- Interactive Time-Series Charts ---
st.subheader("Telemetry & Soil Conditions (Last 7 Days)")

# Soil Moisture Chart
fig_moisture = px.line(df, x='timestamp', y='soil_moisture_pct', title="Soil Moisture Content (%)")
fig_moisture.update_layout(
    yaxis=dict(range=[0, 100]),
    yaxis_title="Soil Moisture Percentage",
    xaxis_title="Timestamp"
)
st.plotly_chart(fig_moisture, use_container_width=True)

col3, col4 = st.columns(2)

with col3:
    # Temperature Chart
    fig_temp = px.line(df, x='timestamp', y=['air_temp_c', 'soil_temp_c'], title="Air vs. Soil Temperature (°C)")
    fig_temp.update_layout(
        yaxis_title="Temperature (°C)",
        xaxis_title="Timestamp"
    )
    st.plotly_chart(fig_temp, use_container_width=True)

with col4:
    # Precipitation Chart
    fig_rain = px.bar(df, x='timestamp', y='precipitation_mm', title="Precipitation / Rainfall (mm)")
    fig_rain.update_layout(
        yaxis_title="Precipitation (mm)",
        xaxis_title="Timestamp"
    )
    st.plotly_chart(fig_rain, use_container_width=True)