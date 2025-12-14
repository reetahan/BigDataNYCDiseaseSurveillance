"""
NYC Disease Surveillance Dashboard
Real-time monitoring of disease events from TimescaleDB and analysis outputs

Loads data from:
- TimescaleDB: Raw disease events
- Spatial Clustering: Geographic cluster analysis (data/spatial_clusters/)
- Outbreak Forecasting: Predictions and risk alerts (forecast/)

Run with: streamlit run src/dashboard/app.py
"""

import streamlit as st
import psycopg2
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time
import json
import glob
import os

# Page configuration
st.set_page_config(
    page_title="NYC Disease Surveillance",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Database connection configuration
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "nyc_disease_surveillance",
    "user": "postgres",
    "password": "postgres"
}

# Data fetching functions - each creates its own connection
@st.cache_data(ttl=30)  # Cache for 30 seconds
def fetch_total_events():
    """Get total number of disease events"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        query = "SELECT COUNT(*) as total FROM disease_events;"
        df = pd.read_sql(query, conn)
        conn.close()
        return df['total'].iloc[0] if not df.empty else 0
    except Exception as e:
        st.error(f"Error fetching total events: {e}")
        return 0

@st.cache_data(ttl=30)
def fetch_recent_events(hours=24):
    """Get events from last N hours"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        query = f"""
            SELECT COUNT(*) as count
            FROM disease_events
            WHERE timestamp >= NOW() - INTERVAL '{hours} hours';
        """
        df = pd.read_sql(query, conn)
        conn.close()
        return df['count'].iloc[0] if not df.empty else 0
    except Exception as e:
        return 0

@st.cache_data(ttl=30)
def fetch_disease_distribution():
    """Get disease type distribution"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        query = """
            SELECT 
                unnest(diseases) as disease,
                COUNT(*) as count
            FROM disease_events
            WHERE diseases IS NOT NULL AND array_length(diseases, 1) > 0
            GROUP BY disease
            ORDER BY count DESC
            LIMIT 10;
        """
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=30)
def fetch_borough_distribution():
    """Get events by borough"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        query = """
            SELECT 
                borough,
                COUNT(*) as count
            FROM disease_events
            WHERE borough IS NOT NULL
            GROUP BY borough
            ORDER BY count DESC;
        """
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=30)
def fetch_severity_distribution():
    """Get events by severity level"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        query = """
            SELECT 
                severity,
                COUNT(*) as count
            FROM disease_events
            GROUP BY severity
            ORDER BY 
                CASE severity
                    WHEN 'severe' THEN 1
                    WHEN 'moderate' THEN 2
                    WHEN 'mild' THEN 3
                    ELSE 4
                END;
        """
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=30)
def fetch_time_series(hours=168):  # 7 days default
    """Get time series data"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        query = f"""
            SELECT 
                time_bucket('1 hour', timestamp) as hour,
                COUNT(*) as count
            FROM disease_events
            WHERE timestamp >= NOW() - INTERVAL '{hours} hours'
            GROUP BY hour
            ORDER BY hour;
        """
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=30)
def fetch_top_symptoms():
    """Get most common symptoms"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        query = """
            SELECT 
                unnest(symptoms) as symptom,
                COUNT(*) as count
            FROM disease_events
            WHERE symptoms IS NOT NULL AND array_length(symptoms, 1) > 0
            GROUP BY symptom
            ORDER BY count DESC
            LIMIT 10;
        """
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=30)
def fetch_source_distribution():
    """Get events by data source"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        query = """
            SELECT 
                source,
                COUNT(*) as count
            FROM disease_events
            GROUP BY source
            ORDER BY count DESC;
        """
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception as e:
        return pd.DataFrame()

# Analysis output loading functions
@st.cache_data(ttl=60)  # Cache for 1 minute (analysis files update less frequently)
def load_latest_spatial_clusters():
    """Load latest spatial clustering analysis"""
    try:
        cluster_dir = "data/spatial_clusters"
        analysis_files = glob.glob(f"{cluster_dir}/cluster_analysis_*.json")
        
        if not analysis_files:
            return None
        
        # Get most recent file
        latest_file = max(analysis_files, key=os.path.getmtime)
        
        with open(latest_file, 'r') as f:
            cluster_data = json.load(f)
        
        return cluster_data
    except Exception as e:
        st.warning(f"Could not load spatial clustering data: {e}")
        return None

@st.cache_data(ttl=60)
def load_latest_forecast():
    """Load latest outbreak forecast"""
    try:
        forecast_file = "forecast/outbreak_forecast.csv"
        
        if not os.path.exists(forecast_file):
            return None
        
        forecast_df = pd.read_csv(forecast_file)
        forecast_df['forecast_date'] = pd.to_datetime(forecast_df['forecast_date'])
        
        return forecast_df
    except Exception as e:
        st.warning(f"Could not load forecast data: {e}")
        return None

@st.cache_data(ttl=60)
def get_cluster_summary(cluster_data):
    """Extract summary statistics from cluster analysis"""
    if not cluster_data:
        return None
    
    metadata = cluster_data.get('metadata', {})
    clusters = cluster_data.get('clusters', {})
    
    summary = {
        'algorithm': metadata.get('algorithm', 'N/A'),
        'total_records': metadata.get('total_records', 0),
        'num_clusters': metadata.get('num_clusters', 0),
        'timestamp': metadata.get('timestamp', 'N/A'),
        'cluster_details': []
    }
    
    for cluster_id, details in clusters.items():
        summary['cluster_details'].append({
            'cluster_id': cluster_id,
            'size': details.get('size', 0),
            'boroughs': details.get('boroughs', {}),
            'top_disease': max(details.get('diseases', {}).items(), key=lambda x: x[1])[0] if details.get('diseases') else 'None',
            'centroid_lat': details.get('centroid', {}).get('lat'),
            'centroid_lon': details.get('centroid', {}).get('lon'),
        })
    
    return summary

@st.cache_data(ttl=60)
def get_forecast_summary(forecast_df):
    """Extract summary statistics from forecast data"""
    if forecast_df is None or forecast_df.empty:
        return None
    
    # Get high-risk predictions
    high_risk = forecast_df[forecast_df['risk_level'].isin(['HIGH', 'CRITICAL'])]
    
    summary = {
        'total_predictions': len(forecast_df),
        'high_risk_count': len(high_risk),
        'diseases_forecasted': forecast_df['disease'].nunique(),
        'neighborhoods_covered': forecast_df['neighborhood'].nunique(),
        'forecast_horizon': (forecast_df['forecast_date'].max() - forecast_df['forecast_date'].min()).days,
        'high_risk_alerts': high_risk[['neighborhood', 'disease', 'forecast_date', 'risk_level', 'predicted_cases']].to_dict('records')[:10]
    }
    
    return summary

# Main dashboard
def main():
    # Header
    st.title("NYC Disease Surveillance Dashboard")
    st.markdown("Real-time monitoring of disease events across New York City")
    
    # Sidebar controls
    st.sidebar.header("Dashboard Controls")
    auto_refresh = st.sidebar.checkbox("Auto-refresh (30s)", value=True)
    time_window = st.sidebar.selectbox(
        "Time Window",
        options=[24, 48, 168, 720],  # 1 day, 2 days, 7 days, 30 days
        format_func=lambda x: f"Last {x} hours" if x < 168 else f"Last {x//24} days",
        index=2  # Default to 7 days
    )
    
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**Last updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Try to fetch data
    try:
        # Load analysis outputs
        cluster_data = load_latest_spatial_clusters()
        forecast_df = load_latest_forecast()
        cluster_summary = get_cluster_summary(cluster_data)
        forecast_summary = get_forecast_summary(forecast_df)
        
        # Top metrics row
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_events = fetch_total_events()
            st.metric("Total Events", f"{total_events:,}")
        
        with col2:
            recent_24h = fetch_recent_events(24)
            st.metric("Last 24 Hours", f"{recent_24h:,}")
        
        with col3:
            recent_7d = fetch_recent_events(168)
            st.metric("Last 7 Days", f"{recent_7d:,}")
        
        with col4:
            avg_per_hour = recent_24h / 24 if recent_24h > 0 else 0
            st.metric("Avg/Hour (24h)", f"{avg_per_hour:.1f}")
        
        st.markdown("---")
        
        # Disease and Borough distribution
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🦠 Top Diseases")
            disease_df = fetch_disease_distribution()
            if not disease_df.empty:
                fig = px.bar(
                    disease_df,
                    x='count',
                    y='disease',
                    orientation='h',
                    color='count',
                    color_continuous_scale='Reds',
                    labels={'count': 'Number of Events', 'disease': 'Disease'}
                )
                fig.update_layout(showlegend=False, height=400)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No disease data available")
        
        with col2:
            st.subheader("📍 Events by Borough")
            borough_df = fetch_borough_distribution()
            if not borough_df.empty:
                fig = px.pie(
                    borough_df,
                    values='count',
                    names='borough',
                    color_discrete_sequence=px.colors.qualitative.Set3
                )
                fig.update_layout(height=400)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No borough data available")
        
        # Bottom row: Symptoms, Severity, Source
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.subheader("🤒 Top Symptoms")
            symptom_df = fetch_top_symptoms()
            if not symptom_df.empty:
                fig = px.bar(
                    symptom_df,
                    x='count',
                    y='symptom',
                    orientation='h',
                    color='count',
                    color_continuous_scale='Blues'
                )
                fig.update_layout(showlegend=False, height=350)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No symptom data available")
        
        with col2:
            st.subheader("⚠️ Severity Levels")
            severity_df = fetch_severity_distribution()
            if not severity_df.empty:
                # Color mapping for severity
                color_map = {
                    'severe': '#d62728',
                    'moderate': '#ff7f0e',
                    'mild': '#2ca02c',
                    'unknown': '#7f7f7f'
                }
                fig = px.bar(
                    severity_df,
                    x='severity',
                    y='count',
                    color='severity',
                    color_discrete_map=color_map
                )
                fig.update_layout(showlegend=False, height=350)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No severity data available")
        
        with col3:
            st.subheader("📊 Data Sources")
            source_df = fetch_source_distribution()
            if not source_df.empty:
                fig = px.bar(
                    source_df,
                    x='count',
                    y='source',
                    orientation='h',
                    color='count',
                    color_continuous_scale='Greens'
                )
                fig.update_layout(showlegend=False, height=350)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No source data available")
        
    except psycopg2.OperationalError as e:
        st.error("❌ Cannot connect to TimescaleDB. Make sure the database is running.")
        st.code(str(e))
        st.info("Start the database with: `docker compose up -d timescaledb`")
    except Exception as e:
        st.error(f"❌ Error loading dashboard: {str(e)}")
        st.code(str(e))
    
    # Auto-refresh at the very end, after all content is rendered
    if auto_refresh:
        st.sidebar.info("Dashboard will refresh in 30 seconds")
        time.sleep(30)
        st.rerun()

if __name__ == "__main__":
    main()
