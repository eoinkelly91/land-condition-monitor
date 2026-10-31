import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine
import os
import datetime
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

# --- Fetch Station Observations & Forecasts ---
@st.cache_data(ttl=600)
def load_data(station_id):
    query = f"""
        SELECT timestamp, air_temp_c, soil_temp_c, soil_moisture_pct, precipitation_mm, wind_speed_ms, solar_radiation_wm2, is_forecast
        FROM weather_observations
        WHERE station_id = '{station_id}'
        ORDER BY timestamp ASC;
    """
    return pd.read_sql(query, engine)

df = load_data(selected_station_id)

if df.empty:
    st.warning(f"No observation data available for {selected_station_name}.")
    st.stop()

# Split into historical observations and future forecasts
df_history = df[df['is_forecast'] == False]
df_forecast = df[df['is_forecast'] == True]

# --- Soil-Aware Rule Engine Logic for UI (Volumetric Water Content %) ---
# Use latest available historical reading for current status
latest_df = df_history if not df_history.empty else df
latest_soil_moisture = latest_df['soil_moisture_pct'].iloc[-1] if not latest_df.empty else 0.0
recent_rain_48h = latest_df['precipitation_mm'].tail(48).sum() if not latest_df.empty else 0.0
recent_soil_temp = latest_df['soil_temp_c'].tail(48).mean() if not latest_df.empty else 0.0
recent_rain_24h = latest_df['precipitation_mm'].tail(24).sum() if not latest_df.empty else 0.0

# Dynamic thresholds based on station soil type and VWC limits
if "Heavy Clay" in selected_station_name:
    moisture_limit = 32.0
    rain_limit_48h = 10.0
    soil_temp_limit = 7.0
elif "Free-Draining" in selected_station_name:
    moisture_limit = 40.0
    rain_limit_48h = 20.0
    soil_temp_limit = 5.5
else:
    moisture_limit = 35.0
    rain_limit_48h = 15.0
    soil_temp_limit = 6.0

turnout_safe = latest_soil_moisture <= moisture_limit and recent_rain_48h <= rain_limit_48h

# Sowing seasonal calendar gate (Spring: Mar-Apr, Autumn: Sep)
current_month = datetime.datetime.now().month
is_valid_sowing_season = current_month in [3, 4, 9]
sowing_safe = (
    is_valid_sowing_season and 
    recent_soil_temp >= soil_temp_limit and 
    recent_rain_24h <= 5.0
)

# --- 48-Hour Forecast Outlook Check ---
forecast_48h = df_forecast.head(48) if not df_forecast.empty else pd.DataFrame()
rain_forecast_48h = forecast_48h['precipitation_mm'].sum() if not forecast_48h.empty else 0.0
soil_moisture_forecast_peak = forecast_48h['soil_moisture_pct'].max() if not forecast_48h.empty else latest_soil_moisture

forecast_risk_elevated = soil_moisture_forecast_peak > moisture_limit or rain_forecast_48h > rain_limit_48h

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
        st.error("**Sowing Readiness:** RED - Conditions Unfavorable (Seasonal / Soil)")

# --- Forecast Outlook Banner ---
st.subheader("🔮 48-Hour Proactive Risk Outlook")
if forecast_risk_elevated:
    st.warning(f"**Weather Warning:** Predicted rain ({rain_forecast_48h:.1f}mm) or rising soil moisture (Peak: {soil_moisture_forecast_peak:.1f}%) expected over the next 48 hours. Monitor paddock conditions closely.")
else:
    st.info(f"**Stable Outlook:** Next 48 hours look stable. Expected rainfall: {rain_forecast_48h:.1f}mm. No immediate weather-driven restrictions triggered.")

# --- Transparency & Metric Inspection ---
with st.expander("🔍 View Decision Rule Metrics & Thresholds"):
    m_col1, m_col2 = st.columns(2)
    with m_col1:
        st.markdown(f"**Station:** {selected_station_name}")
        st.markdown(r"**Current Soil Moisture:** " + f"{latest_soil_moisture:.1f}% (Limit: $\le$ {moisture_limit}%)")
        st.markdown(r"**48h Historical Rain:** " + f"{recent_rain_48h:.1f} mm (Limit: $\le$ {rain_limit_48h} mm)")
    with m_col2:
        st.markdown(r"**48h Avg Soil Temp:** " + f"{recent_soil_temp:.1f}°C (Limit: $\ge$ {soil_temp_limit}°C)")
        st.markdown(f"**48h Forecast Rain Outlook:** {rain_forecast_48h:.1f} mm")

# --- Interactive Time-Series Charts ---
st.subheader("Telemetry & 7-Day Forecast Trends")

# Soil Moisture Chart
fig_moisture = px.line(df, x='timestamp', y='soil_moisture_pct', title="Soil Moisture Content (%) — History & Forecast")
fig_moisture.update_layout(
    yaxis=dict(range=[0, 100]),
    yaxis_title="Soil Moisture Percentage",
    xaxis_title="Timestamp"
)
st.plotly_chart(fig_moisture, use_container_width=True)

col3, col4 = st.columns(2)

with col3:
    fig_temp = px.line(df, x='timestamp', y=['air_temp_c', 'soil_temp_c'], title="Air vs. Soil Temperature (°C)")
    fig_temp.update_layout(
        yaxis_title="Temperature (°C)",
        xaxis_title="Timestamp"
    )
    st.plotly_chart(fig_temp, use_container_width=True)

with col4:
    fig_rain = px.bar(df, x='timestamp', y='precipitation_mm', title="Precipitation / Rainfall (mm)")
    fig_rain.update_layout(
        yaxis_title="Precipitation (mm)",
        xaxis_title="Timestamp"
    )
    st.plotly_chart(fig_rain, use_container_width=True)