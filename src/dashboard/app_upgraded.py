"""
NYC Disease Surveillance Dashboard
Real-time monitoring of disease events from TimescaleDB and analysis outputs

Loads data from:
- TimescaleDB: Raw disease events
- Spatial Clustering: Geographic cluster analysis (data/spatial_clusters/)
- Anomaly Detection: Statistical anomaly alerts (data/anomalies.csv)
- Outbreak Forecasting: Predictions and risk alerts (data/forecast/outbreak_forecast.csv)

Run with: streamlit run src/dashboard/app_upgraded.py
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
    page_icon="",
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

# ============================================================================
# EXISTING FUNCTIONS (UNCHANGED)
# ============================================================================

@st.cache_data(ttl=30)
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
def fetch_disease_distribution(hours=168):
    """Get disease type distribution"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        query = f"""
            SELECT
                unnest(diseases) as disease,
                COUNT(*) as count
            FROM disease_events
            WHERE diseases IS NOT NULL AND array_length(diseases, 1) > 0
              AND timestamp >= NOW() - INTERVAL '{hours} hours'
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
def fetch_borough_distribution(hours=168):
    """Get events by borough"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        query = f"""
            SELECT
                borough,
                COUNT(*) as count
            FROM disease_events
            WHERE borough IS NOT NULL
              AND timestamp >= NOW() - INTERVAL '{hours} hours'
            GROUP BY borough
            ORDER BY count DESC;
        """
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=30)
def fetch_severity_distribution(hours=168):
    """Get events by severity level
    
    Severity levels determined by relevance_consumer.py keyword matching:
    - severe: hospital, emergency, icu, critical, ambulance
    - moderate: worse, worsening, bad
    - mild: slight, minor, little
    - unknown: no severity keywords found
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        query = f"""
            SELECT
                severity,
                COUNT(*) as count
            FROM disease_events
            WHERE timestamp >= NOW() - INTERVAL '{hours} hours'
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
def fetch_time_series(hours=168):
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
def fetch_top_symptoms(hours=168):
    """Get most common symptoms"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        query = f"""
            SELECT
                unnest(symptoms) as symptom,
                COUNT(*) as count
            FROM disease_events
            WHERE symptoms IS NOT NULL AND array_length(symptoms, 1) > 0
              AND timestamp >= NOW() - INTERVAL '{hours} hours'
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
def fetch_source_distribution(hours=168):
    """Get events by data source"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        query = f"""
            SELECT
                CASE
                    WHEN source = 'unknown' THEN '⚠️ Unknown Source'
                    ELSE source
                END as source,
                COUNT(*) as count
            FROM disease_events
            WHERE timestamp >= NOW() - INTERVAL '{hours} hours'
            GROUP BY source
            ORDER BY count DESC;
        """
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=60)
def load_latest_spatial_clusters():
    """Load latest spatial clustering analysis"""
    try:
        cluster_dir = "data/spatial_clusters"
        analysis_files = glob.glob(f"{cluster_dir}/cluster_analysis_*.json")

        if not analysis_files:
            return None

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
        forecast_file = "data/forecast/outbreak_forecast.csv"

        if not os.path.exists(forecast_file):
            return None

        forecast_df = pd.read_csv(forecast_file)
        forecast_df['forecast_date'] = pd.to_datetime(forecast_df['forecast_date'])

        return forecast_df
    except Exception as e:
        st.warning(f"Could not load forecast data: {e}")
        return None

@st.cache_data(ttl=60)
def load_anomaly_detection():
    """Load anomaly detection results"""
    try:
        anomaly_file = "data/anomalies.csv"

        if not os.path.exists(anomaly_file):
            return None

        anomaly_df = pd.read_csv(anomaly_file)
        
        # Rename columns to match expected format
        if 'day' in anomaly_df.columns:
            anomaly_df['date'] = pd.to_datetime(anomaly_df['day'])
        if 'cnt' in anomaly_df.columns:
            anomaly_df['case_count'] = anomaly_df['cnt']
        
        # Mark anomalies (z_score > 1.5)
        if 'z_score' in anomaly_df.columns:
            anomaly_df['is_anomaly'] = anomaly_df['z_score'].abs() > 1.5

        return anomaly_df
    except Exception as e:
        st.warning(f"Could not load anomaly data: {e}")
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

# ============================================================================
# NEW FUNCTIONS: Official vs Informal Data Comparison
# ============================================================================

@st.cache_data(ttl=300)
def load_official_health_data():
    """
    Load official NYC health department data from JSON files

    Priority order:
    1. JSON file: data/official_reports/nyc_doh_reports.json
    2. Multiple JSON files: data/official_reports/*.json
    3. Database table: official_health_reports
    4. Mock data for demonstration

    Supported JSON formats:
    Format 1 - Array of records:
    [
        {"date": "2024-12-01", "disease": "influenza", "cases": 50, "borough": "Manhattan"},
        ...
    ]

    Format 2 - Nested structure:
    {
        "data": [
            {"report_date": "2024-12-01", "illness_type": "influenza", "count": 50, "location": "Manhattan"},
            ...
        ]
    }

    Format 3 - NYC DOH API format:
    {
        "meta": {...},
        "data": [
            ["2024-12-01", "influenza", "50", "Manhattan"],
            ...
        ],
        "columns": ["date", "disease", "cases", "borough"]
    }
    """
    try:
        # Try loading single JSON file
        official_file = "data/nyc_311/nyc_doh_reports.json"

        if os.path.exists(official_file):
            with open(official_file, 'r') as f:
                data = json.load(f)

            df = parse_official_json(data)
            if df is not None and not df.empty:
                return df

        # Try loading multiple JSON files
        json_files = glob.glob("data/nyc_311/*.json")
        if json_files:
            all_data = []
            for json_file in json_files:
                try:
                    with open(json_file, 'r') as f:
                        data = json.load(f)
                    parsed = parse_official_json(data)
                    if parsed is not None:
                        all_data.append(parsed)
                except Exception as e:
                    st.warning(f"Could not parse {json_file}: {e}")
                    continue

            if all_data:
                df = pd.concat(all_data, ignore_index=True)
                df = df.drop_duplicates(subset=['date', 'disease', 'borough'])
                df = df.sort_values('date')
                return df

        # Generate mock data for demonstration
        dates = pd.date_range(end=datetime.now(), periods=30, freq='D')
        mock_data = pd.DataFrame({
            'date': dates,
            'disease': ['influenza'] * 30,
            'reported_cases': [50 + i*2.5 for i in range(30)],
            'borough': ['Manhattan'] * 30
        })
        return mock_data

    except Exception as e:
        st.warning(f"Could not load official health data: {e}")
        return None

def parse_official_json(data):
    """
    Parse various JSON formats from official health reports

    Args:
        data: Parsed JSON data (dict or list)

    Returns:
        DataFrame with columns: date, disease, reported_cases, borough
    """
    try:
        # Format 1: Direct array of objects
        if isinstance(data, list):
            df = pd.DataFrame(data)
            df = standardize_official_columns(df)
            return df

        # Format 2: Nested under 'data' key
        if isinstance(data, dict):
            # Check for common nested structures
            if 'data' in data:
                records = data['data']

                # NYC DOH API format with separate columns definition
                if 'columns' in data and isinstance(records, list) and records and isinstance(records[0], list):
                    columns = data['columns']
                    df = pd.DataFrame(records, columns=columns)
                    df = standardize_official_columns(df)
                    return df

                # Standard nested format
                elif isinstance(records, list):
                    df = pd.DataFrame(records)
                    df = standardize_official_columns(df)
                    return df

            # Direct dictionary format (single record)
            else:
                df = pd.DataFrame([data])
                df = standardize_official_columns(df)
                return df

        return None

    except Exception as e:
        st.warning(f"Error parsing JSON: {e}")
        return None

def standardize_official_columns(df):
    """
    Standardize column names from various official data formats

    Maps common variations to standard names:
    - date, report_date, Date -> date
    - disease, illness, illness_type, disease_name -> disease
    - cases, count, reported_cases, case_count -> reported_cases
    - borough, location, area, neighborhood -> borough
    """
    if df is None or df.empty:
        return df

    # Column name mappings
    date_cols = ['date', 'report_date', 'Date', 'reported_date', 'event_date']
    disease_cols = ['disease', 'illness', 'illness_type', 'disease_name', 'diagnosis']
    cases_cols = ['cases', 'count', 'reported_cases', 'case_count', 'num_cases']
    borough_cols = ['borough', 'location', 'area', 'neighborhood', 'region']

    # Find and rename columns
    col_mapping = {}

    for col in df.columns:
        if col in date_cols:
            col_mapping[col] = 'date'
        elif col in disease_cols:
            col_mapping[col] = 'disease'
        elif col in cases_cols:
            col_mapping[col] = 'reported_cases'
        elif col in borough_cols:
            col_mapping[col] = 'borough'

    # Apply renaming
    df = df.rename(columns=col_mapping)

    # Ensure required columns exist
    required_cols = ['date', 'disease', 'reported_cases']
    if not all(col in df.columns for col in required_cols):
        # Try NYC 311 specific fallbacks
        if 'Complaint Type' in df.columns:
            df['disease'] = df['Complaint Type']
        if 'Created Date' in df.columns:
            df['date'] = df['Created Date']
        if 'reported_cases' not in df.columns:
            df['reported_cases'] = 1  # Each 311 complaint is one case
        
        # Final check
        if not all(col in df.columns for col in required_cols):
            return None

    # Convert data types
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df['reported_cases'] = pd.to_numeric(df['reported_cases'], errors='coerce')

    # Standardize disease names (lowercase)
    df['disease'] = df['disease'].str.lower().str.strip()

    # Add borough if missing
    if 'borough' not in df.columns:
        if 'Borough' in df.columns:
            df['borough'] = df['Borough']
        else:
            df['borough'] = 'Unknown'

    # Remove rows with invalid data
    df = df.dropna(subset=['date', 'disease', 'reported_cases'])

    return df[['date', 'disease', 'reported_cases', 'borough']]

@st.cache_data(ttl=30)
def fetch_informal_disease_counts(days_back=None):
    """Get aggregated disease counts from our surveillance system
    
    Args:
        days_back: Number of days to look back (None = all data)
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        
        # Build query with or without time filter
        if days_back:
            query = f"""
                SELECT
                    DATE(timestamp) as date,
                    unnest(diseases) as disease,
                    COUNT(*) as informal_cases
                FROM disease_events
                WHERE timestamp >= NOW() - INTERVAL '{days_back} days'
                    AND diseases IS NOT NULL
                    AND array_length(diseases, 1) > 0
                GROUP BY DATE(timestamp), disease
                ORDER BY date, disease;
            """
        else:
            query = """
                SELECT
                    DATE(timestamp) as date,
                    unnest(diseases) as disease,
                    COUNT(*) as informal_cases
                FROM disease_events
                WHERE diseases IS NOT NULL
                    AND array_length(diseases, 1) > 0
                GROUP BY DATE(timestamp), disease
                ORDER BY date, disease;
            """
        
        df = pd.read_sql(query, conn)
        conn.close()
        df['date'] = pd.to_datetime(df['date'])
        
        # Normalize disease names to lowercase for comparison with official data
        if 'disease' in df.columns:
            df['disease'] = df['disease'].str.lower().str.strip()
        
        return df
    except Exception as e:
        return pd.DataFrame()

def compare_official_vs_informal(official_df, informal_df):
    """
    Compare official and informal surveillance data
    Returns: merged_df, metrics_dict
    """
    if official_df is None or official_df.empty or informal_df.empty:
        return None, None

    # Ensure date columns are date-only (no time component)
    official_df = official_df.copy()
    informal_df = informal_df.copy()
    official_df['date'] = pd.to_datetime(official_df['date']).dt.date
    informal_df['date'] = pd.to_datetime(informal_df['date']).dt.date
    
    # Aggregate by date and disease (consolidate multiple timestamps per day)
    official_agg = official_df.groupby(['date', 'disease'], as_index=False)['reported_cases'].sum()
    informal_agg = informal_df.groupby(['date', 'disease'], as_index=False)['informal_cases'].sum()

    # Merge datasets
    merged = pd.merge(
        official_agg,
        informal_agg,
        on=['date', 'disease'],
        how='outer'
    ).fillna(0)

    # Calculate comparison metrics
    merged['difference'] = merged['informal_cases'] - merged['reported_cases']
    merged['percent_difference'] = (
        (merged['informal_cases'] - merged['reported_cases'])
        / merged['reported_cases'].replace(0, 1) * 100
    )

    # Calculate correlation
    if len(merged) > 5:
        correlation = merged[['reported_cases', 'informal_cases']].corr().iloc[0, 1]
    else:
        correlation = None

    # Calculate early detection capability
    early_days = calculate_early_detection(merged)

    metrics = {
        'correlation': correlation,
        'avg_informal': merged['informal_cases'].mean(),
        'avg_official': merged['reported_cases'].mean(),
        'early_detection_days': early_days
    }

    return merged, metrics

def calculate_early_detection(merged_df):
    """Calculate days of early detection advantage"""
    try:
        # Find first spike in informal data (>150% of mean)
        informal_threshold = merged_df['informal_cases'].mean() * 1.5
        informal_spike = merged_df[merged_df['informal_cases'] > informal_threshold]

        if informal_spike.empty:
            return 0

        # Find first spike in official data
        official_threshold = merged_df['reported_cases'].mean() * 1.5
        official_spike = merged_df[merged_df['reported_cases'] > official_threshold]

        if official_spike.empty:
            return 0

        # Calculate day difference
        days_early = (official_spike['date'].min() - informal_spike['date'].min()).days
        return max(0, days_early)
    except:
        return 0

# ============================================================================
# NEW FUNCTIONS: Risk Assessment
# ============================================================================

def calculate_risk_score(neighborhood, disease, forecast_df, informal_df):
    """
    Calculate comprehensive risk score (0-100)

    Components:
    - Recent trend: 30 points
    - Forecast prediction: 40 points
    - Historical severity: 20 points
    - Population density: 10 points
    """
    risk_score = 0
    components = {}

    try:
        # Component 1: Recent trend (30 points)
        if not informal_df.empty:
            disease_data = informal_df[informal_df['disease'] == disease]
            if not disease_data.empty:
                recent_7d = disease_data.tail(7)['informal_cases'].sum()
                historical_avg = disease_data['informal_cases'].mean() * 7

                if historical_avg > 0:
                    trend_ratio = recent_7d / historical_avg
                    trend_score = min(30, trend_ratio * 15)
                else:
                    trend_score = 0
            else:
                trend_score = 0

            risk_score += trend_score
            components['recent_trend'] = trend_score

        # Component 2: Forecast prediction (40 points)
        if forecast_df is not None and not forecast_df.empty:
            forecast_match = forecast_df[
                (forecast_df['neighborhood'] == neighborhood) &
                (forecast_df['disease'] == disease)
            ]

            if not forecast_match.empty:
                risk_level = forecast_match['risk_level'].iloc[0]
                risk_map = {'LOW': 10, 'MODERATE': 20, 'HIGH': 35, 'CRITICAL': 40}
                forecast_score = risk_map.get(risk_level, 0)
            else:
                forecast_score = 0

            risk_score += forecast_score
            components['forecast'] = forecast_score

        # Component 3: Historical severity (20 points)
        severity_score = 10  # Default moderate
        risk_score += severity_score
        components['severity'] = severity_score

        # Component 4: Population density (10 points)
        density_map = {
            'Manhattan': 10, 'Brooklyn': 7, 'Queens': 7,
            'Bronx': 5, 'Staten Island': 3
        }
        density_score = density_map.get(neighborhood, 5)
        risk_score += density_score
        components['density'] = density_score

    except Exception as e:
        st.warning(f"Error calculating risk score: {e}")

    return min(100, risk_score), components

def generate_risk_assessment():
    """Generate comprehensive risk assessment for all areas"""
    try:
        forecast_df = load_latest_forecast()
        informal_df = fetch_informal_disease_counts(days_back=None)

        if forecast_df is None or informal_df.empty:
            return None

        # Get unique combinations
        combinations = forecast_df[['neighborhood', 'disease']].drop_duplicates()

        risk_assessments = []

        for _, row in combinations.iterrows():
            neighborhood = row['neighborhood']
            disease = row['disease']

            risk_score, components = calculate_risk_score(
                neighborhood, disease, forecast_df, informal_df
            )

            # Classify risk level
            if risk_score >= 75:
                risk_level, color = 'CRITICAL', '🔴'
            elif risk_score >= 60:
                risk_level, color = 'HIGH', '🟠'
            elif risk_score >= 40:
                risk_level, color = 'MODERATE', '🟡'
            else:
                risk_level, color = 'LOW', '🟢'

            risk_assessments.append({
                'neighborhood': neighborhood,
                'disease': disease,
                'risk_score': risk_score,
                'risk_level': risk_level,
                'color': color,
                'components': components
            })

        risk_df = pd.DataFrame(risk_assessments).sort_values('risk_score', ascending=False)
        return risk_df

    except Exception as e:
        st.warning(f"Could not generate risk assessment: {e}")
        return None

# ============================================================================
# UI RENDERING FUNCTIONS
# ============================================================================

def render_metrics_row():
    """Render top-level metrics"""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        total = fetch_total_events()
        st.metric("Total Events", f"{total:,}")

    with col2:
        recent_24h = fetch_recent_events(24)
        st.metric("Last 24 Hours", f"{recent_24h:,}")

    with col3:
        recent_7d = fetch_recent_events(168)
        st.metric("Last 7 Days", f"{recent_7d:,}")

    with col4:
        avg_per_hour = recent_24h / 24 if recent_24h > 0 else 0
        st.metric("Avg/Hour (24h)", f"{avg_per_hour:.1f}")

def render_disease_borough_charts(time_window=168):
    """Render disease and borough distribution charts"""
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🦠 Top Diseases")
        disease_df = fetch_disease_distribution(time_window)
        if not disease_df.empty:
            fig = px.bar(
                disease_df, x='count', y='disease', orientation='h',
                color='count', color_continuous_scale='Reds'
            )
            fig.update_layout(showlegend=False, height=400)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No disease data available")

    with col2:
        st.subheader("📍 Events by Borough")
        borough_df = fetch_borough_distribution(time_window)
        if not borough_df.empty:
            fig = px.pie(
                borough_df, values='count', names='borough',
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No borough data available")

def render_details_charts(time_window=168):
    """Render symptoms, severity, and source charts"""
    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("🤒 Top Symptoms")
        symptom_df = fetch_top_symptoms(time_window)
        if not symptom_df.empty:
            fig = px.bar(
                symptom_df, x='count', y='symptom', orientation='h',
                color='count', color_continuous_scale='Blues'
            )
            fig.update_layout(showlegend=False, height=350)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No symptom data available")

    with col2:
        st.subheader("⚠️ Severity Levels")
        severity_df = fetch_severity_distribution(time_window)
        if not severity_df.empty:
            color_map = {
                'severe': '#d62728', 'moderate': '#ff7f0e',
                'mild': '#2ca02c', 'unknown': '#7f7f7f'
            }
            fig = px.bar(
                severity_df, x='severity', y='count',
                color='severity', color_discrete_map=color_map
            )
            fig.update_layout(showlegend=False, height=350)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No severity data available")

    with col3:
        st.subheader("📊 Data Sources")
        source_df = fetch_source_distribution(time_window)
        if not source_df.empty:
            fig = px.bar(
                source_df, x='count', y='source', orientation='h',
                color='count', color_continuous_scale='Greens'
            )
            fig.update_layout(showlegend=False, height=350)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No source data available")

def render_comparison_section():
    """Render official vs informal data comparison"""
    st.header("📊 Official vs Informal Data Comparison")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📈 Data Source Comparison")

        official_df = load_official_health_data()
        informal_df = fetch_informal_disease_counts(days_back=None)

        if official_df is not None and not informal_df.empty:
            merged_df, metrics = compare_official_vs_informal(official_df, informal_df)

            if merged_df is not None and metrics:
                # Display metrics
                m1, m2, m3 = st.columns(3)

                with m1:
                    corr = metrics.get('correlation', 0)
                    if corr:
                        st.metric("Correlation", f"{corr:.2f}")

                with m2:
                    early = metrics.get('early_detection_days', 0)
                    st.metric("Early Detection", f"{early} days")

                with m3:
                    avg_diff = metrics['avg_informal'] - metrics['avg_official']
                    st.metric("Avg Difference", f"{avg_diff:.1f}")

                # Show data source info
                st.caption(f"📁 Loaded {len(official_df)} official records")

                # Comparison chart
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=merged_df['date'], y=merged_df['reported_cases'],
                    mode='lines+markers', name='Official Reports (NYC DOH)',
                    line=dict(color='#1f77b4', width=2)
                ))
                fig.add_trace(go.Scatter(
                    x=merged_df['date'], y=merged_df['informal_cases'],
                    mode='lines+markers', name='Informal Surveillance (Our System)',
                    line=dict(color='#ff7f0e', width=2)
                ))
                fig.update_layout(
                    title='Official vs Informal Case Counts',
                    xaxis_title='Date', yaxis_title='Cases',
                    hovermode='x unified', height=400
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("📝 No official data found. Add JSON files to get started.")

            with st.expander("📖 How to add official data (JSON format)"):
                st.markdown("""
                ### JSON File Location
                Place your JSON files in: `data/official_reports/`

                ### Supported JSON Formats

                **Format 1 - Simple Array:**
                ```json
                [
                    {
                        "date": "2024-12-01",
                        "disease": "influenza",
                        "cases": 50,
                        "borough": "Manhattan"
                    },
                    {
                        "date": "2024-12-02",
                        "disease": "influenza",
                        "cases": 55,
                        "borough": "Manhattan"
                    }
                ]
                ```

                **Format 2 - Nested Structure:**
                ```json
                {
                    "data": [
                        {
                            "report_date": "2024-12-01",
                            "illness_type": "influenza",
                            "count": 50,
                            "location": "Manhattan"
                        }
                    ]
                }
                ```

                **Format 3 - NYC DOH API Format:**
                ```json
                {
                    "columns": ["date", "disease", "cases", "borough"],
                    "data": [
                        ["2024-12-01", "influenza", 50, "Manhattan"],
                        ["2024-12-02", "influenza", 55, "Manhattan"]
                    ]
                }
                ```

                ### Column Name Variations (Auto-detected)
                - **Date**: date, report_date, Date, reported_date
                - **Disease**: disease, illness, illness_type, diagnosis
                - **Cases**: cases, count, reported_cases, case_count
                - **Borough**: borough, location, area, neighborhood

                ### Example: NYC DOH Data
                Download from: https://data.cityofnewyork.us/Health/
                """)

    with col2:
        st.subheader("🎯 Risk Assessment")

        risk_df = generate_risk_assessment()

        if risk_df is not None and not risk_df.empty:
            st.markdown("**Top 10 Highest Risk Areas**")

            for _, row in risk_df.head(10).iterrows():
                col_a, col_b, col_c = st.columns([1, 3, 2])

                with col_a:
                    st.markdown(f"## {row['color']}")

                with col_b:
                    st.markdown(f"**{row['neighborhood']}** - {row['disease']}")
                    st.caption(f"Risk: {row['risk_level']}")

                with col_c:
                    st.metric("Score", f"{row['risk_score']:.0f}/100")

                st.progress(row['risk_score'] / 100)
                st.markdown("---")

            # Risk distribution
            risk_counts = risk_df['risk_level'].value_counts()
            fig = px.pie(
                values=risk_counts.values, names=risk_counts.index,
                color=risk_counts.index,
                color_discrete_map={
                    'CRITICAL': '#d62728', 'HIGH': '#ff7f0e',
                    'MODERATE': '#ffdd57', 'LOW': '#2ca02c'
                }
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Risk assessment requires forecast data")

# ============================================================================
# RENDER FUNCTIONS: Spatial Clustering
# ============================================================================

def render_spatial_clustering_section():
    """Render spatial clustering analysis tab"""
    st.header("🗺️ Spatial Clustering Analysis")
    st.markdown("DBSCAN-based geographic clustering of disease events")

    cluster_data = load_latest_spatial_clusters()

    if cluster_data is None:
        st.info("No spatial clustering data available. Run: `python src/analysis/spatial_clustering.py`")
        return

    summary = get_cluster_summary(cluster_data)

    # Metadata row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Clusters", summary['num_clusters'])
    with col2:
        st.metric("Records Analyzed", f"{summary['total_records']:,}")
    with col3:
        st.metric("Algorithm", summary['algorithm'])
    with col4:
        st.metric("Analysis Time", summary['timestamp'][:10])

    st.markdown("---")

    # Cluster details
    if summary['cluster_details']:
        st.subheader("Cluster Breakdown")

        # Sort by size
        clusters_sorted = sorted(summary['cluster_details'], key=lambda x: x['size'], reverse=True)

        for cluster in clusters_sorted[:10]:  # Top 10 clusters
            with st.expander(f"Cluster {cluster['cluster_id']} - {cluster['size']} events", expanded=False):
                c1, c2, c3 = st.columns(3)

                with c1:
                    st.markdown(f"**Size:** {cluster['size']}")
                    st.markdown(f"**Top Disease:** {cluster['top_disease']}")

                with c2:
                    st.markdown("**Boroughs:**")
                    for borough, count in cluster['boroughs'].items():
                        st.markdown(f"- {borough}: {count}")

                with c3:
                    if cluster['centroid_lat'] and cluster['centroid_lon']:
                        st.markdown(f"**Centroid:**")
                        st.markdown(f"Lat: {cluster['centroid_lat']:.4f}")
                        st.markdown(f"Lon: {cluster['centroid_lon']:.4f}")

        # Cluster size distribution
        cluster_sizes = [c['size'] for c in clusters_sorted]
        fig = px.bar(
            x=[f"Cluster {c['cluster_id']}" for c in clusters_sorted[:15]],
            y=cluster_sizes[:15],
            title="Top 15 Clusters by Size",
            labels={'x': 'Cluster ID', 'y': 'Number of Events'}
        )
        fig.update_layout(showlegend=False, height=400)
        st.plotly_chart(fig, use_container_width=True)

# ============================================================================
# RENDER FUNCTIONS: Anomaly Detection
# ============================================================================

def render_anomaly_detection_section():
    """Render anomaly detection analysis tab"""
    st.header("⚠️ Anomaly Detection")
    st.markdown("Statistical anomaly detection using expanding window z-scores")

    anomaly_df = load_anomaly_detection()

    if anomaly_df is None:
        st.info("No anomaly data available. Run: `python src/analysis/anomaly_detection.py`")
        return

    # Filter for significant anomalies
    significant_anomalies = anomaly_df[anomaly_df['is_anomaly'] == True]

    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Records", len(anomaly_df))
    with col2:
        st.metric("Anomalies Detected", len(significant_anomalies))
    with col3:
        pct = (len(significant_anomalies) / len(anomaly_df) * 100) if len(anomaly_df) > 0 else 0
        st.metric("Anomaly Rate", f"{pct:.1f}%")
    with col4:
        if 'z_score' in anomaly_df.columns:
            max_z = anomaly_df['z_score'].abs().max()
            st.metric("Max Z-Score", f"{max_z:.2f}")

    st.markdown("---")

    # Recent anomalies table
    if not significant_anomalies.empty:
        st.subheader("Recent Anomalies")

        # Sort by date descending
        recent = significant_anomalies.sort_values('date', ascending=False).head(20)

        display_cols = ['date', 'borough', 'disease', 'case_count', 'z_score']
        display_cols = [col for col in display_cols if col in recent.columns]

        st.dataframe(
            recent[display_cols],
            use_container_width=True,
            hide_index=True
        )

        # Time series with anomalies
        st.subheader("Case Trends with Anomalies")

        # Borough filter
        available_boroughs = anomaly_df['borough'].unique() if 'borough' in anomaly_df.columns else []
        selected_borough = st.selectbox("Select Borough", options=['All'] + list(available_boroughs))

        plot_df = anomaly_df if selected_borough == 'All' else anomaly_df[anomaly_df['borough'] == selected_borough]

        if 'date' in plot_df.columns and 'case_count' in plot_df.columns:
            fig = go.Figure()

            # Normal cases
            normal = plot_df[plot_df['is_anomaly'] == False]
            fig.add_trace(go.Scatter(
                x=normal['date'],
                y=normal['case_count'],
                mode='lines+markers',
                name='Normal',
                line=dict(color='#2ca02c', width=2),
                marker=dict(size=6)
            ))

            # Anomalies
            anomalies = plot_df[plot_df['is_anomaly'] == True]
            fig.add_trace(go.Scatter(
                x=anomalies['date'],
                y=anomalies['case_count'],
                mode='markers',
                name='Anomaly',
                marker=dict(color='#d62728', size=12, symbol='x')
            ))

            fig.update_layout(
                title=f"Disease Case Trends - {selected_borough}",
                xaxis_title='Date',
                yaxis_title='Case Count',
                hovermode='x unified',
                height=500
            )
            st.plotly_chart(fig, use_container_width=True)

# ============================================================================
# RENDER FUNCTIONS: Outbreak Forecasting
# ============================================================================

def render_outbreak_forecasting_section():
    """Render outbreak forecasting analysis tab"""
    st.header("📈 Outbreak Forecasting")
    st.markdown("Prophet-based time-series predictions for disease outbreaks")

    forecast_df = load_latest_forecast()

    if forecast_df is None or len(forecast_df) == 0:
        st.warning("⚠️ Forecast CSV is empty. This may be due to:")
        st.markdown("""
        - **Insufficient data**: Prophet requires at least 14 days of historical data per neighborhood/disease
        - **Sparse data**: `min_cases=3` threshold not met for most combinations
        - **Recent analysis**: No outbreak patterns detected yet
        
        **To generate forecasts:**
        ```bash
        python src/analysis/disease_outbreak_forecaster.py
        ```
        
        The forecaster will only predict for neighborhood/disease pairs with sufficient historical data.
        """)
        return

    summary = get_forecast_summary(forecast_df)

    # Metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Predictions", summary['total_predictions'])
    with col2:
        st.metric("High Risk Alerts", summary['high_risk_count'])
    with col3:
        st.metric("Diseases", summary['diseases_forecasted'])
    with col4:
        st.metric("Forecast Horizon", f"{summary['forecast_horizon']} days")

    st.markdown("---")

    # High risk alerts
    if summary['high_risk_alerts']:
        st.subheader("🚨 High Risk Alerts")

        for alert in summary['high_risk_alerts'][:10]:
            with st.expander(f"{alert['neighborhood']} - {alert['disease']} ({alert['risk_level']})", expanded=False):
                c1, c2, c3 = st.columns(3)

                with c1:
                    st.metric("Predicted Cases", f"{alert['predicted_cases']:.1f}")
                with c2:
                    st.metric("Risk Level", alert['risk_level'])
                with c3:
                    st.metric("Forecast Date", str(alert['forecast_date'])[:10])

    st.markdown("---")

    # Forecast visualization
    st.subheader("Forecast Predictions")

    # Filters
    col1, col2 = st.columns(2)
    with col1:
        available_diseases = forecast_df['disease'].unique()
        selected_disease = st.selectbox("Select Disease", options=available_diseases)

    with col2:
        available_neighborhoods = forecast_df['neighborhood'].unique()
        selected_neighborhood = st.selectbox("Select Neighborhood", options=available_neighborhoods)

    # Filter data
    plot_df = forecast_df[
        (forecast_df['disease'] == selected_disease) &
        (forecast_df['neighborhood'] == selected_neighborhood)
    ]

    if not plot_df.empty:
        fig = go.Figure()

        # Predicted cases
        fig.add_trace(go.Scatter(
            x=plot_df['forecast_date'],
            y=plot_df['predicted_cases'],
            mode='lines+markers',
            name='Predicted Cases',
            line=dict(color='#1f77b4', width=3)
        ))

        # Confidence intervals if available
        if 'lower_bound' in plot_df.columns and 'upper_bound' in plot_df.columns:
            fig.add_trace(go.Scatter(
                x=plot_df['forecast_date'],
                y=plot_df['upper_bound'],
                mode='lines',
                name='Upper Bound',
                line=dict(width=0),
                showlegend=False
            ))
            fig.add_trace(go.Scatter(
                x=plot_df['forecast_date'],
                y=plot_df['lower_bound'],
                mode='lines',
                name='Lower Bound',
                line=dict(width=0),
                fill='tonexty',
                fillcolor='rgba(31, 119, 180, 0.2)',
                showlegend=True
            ))

        fig.update_layout(
            title=f"{selected_disease.title()} Forecast - {selected_neighborhood}",
            xaxis_title='Date',
            yaxis_title='Predicted Cases',
            hovermode='x unified',
            height=500
        )
        st.plotly_chart(fig, use_container_width=True)

        # Risk level distribution
        risk_counts = plot_df['risk_level'].value_counts()
        fig2 = px.bar(
            x=risk_counts.index,
            y=risk_counts.values,
            title="Risk Level Distribution",
            labels={'x': 'Risk Level', 'y': 'Count'},
            color=risk_counts.index,
            color_discrete_map={
                'CRITICAL': '#d62728',
                'HIGH': '#ff7f0e',
                'MODERATE': '#ffdd57',
                'LOW': '#2ca02c'
            }
        )
        fig2.update_layout(showlegend=False, height=300)
        st.plotly_chart(fig2, use_container_width=True)

# ============================================================================
# MAIN DASHBOARD
# ============================================================================

def main():
    st.title("🏙️ NYC Disease Surveillance Dashboard")
    st.markdown("Real-time monitoring of disease events across New York City")

    # Sidebar
    st.sidebar.header("⚙️ Dashboard Controls")
    auto_refresh = st.sidebar.checkbox("Auto-refresh (30s)", value=False)
    time_window = st.sidebar.selectbox(
        "Time Window",
        options=[24, 48, 168, 720],
        format_func=lambda x: f"Last {x} hours" if x < 168 else f"Last {x//24} days",
        index=2
    )
    st.sidebar.markdown("---")
    st.sidebar.markdown(f"**Last updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Tab navigation
    tabs = st.tabs([
        "📊 Overview",
        "🗺️ Spatial Clustering",
        "⚠️ Anomaly Detection",
        "📈 Outbreak Forecasting",
        "🔍 Data Comparison"
    ])

    try:
        # Tab 1: Overview (existing dashboard)
        with tabs[0]:
            render_metrics_row()
            st.markdown("---")
            render_disease_borough_charts(time_window)
            render_details_charts(time_window)

        # Tab 2: Spatial Clustering
        with tabs[1]:
            render_spatial_clustering_section()

        # Tab 3: Anomaly Detection
        with tabs[2]:
            render_anomaly_detection_section()

        # Tab 4: Outbreak Forecasting
        with tabs[3]:
            render_outbreak_forecasting_section()

        # Tab 5: Data Comparison
        with tabs[4]:
            render_comparison_section()

    except psycopg2.OperationalError as e:
        st.error("❌ Cannot connect to TimescaleDB")
        st.info("Start database: `docker compose up -d timescaledb`")
    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
        st.exception(e)

    # Auto-refresh
    if auto_refresh:
        st.sidebar.info("Refreshing in 30 seconds...")
        time.sleep(30)
        st.rerun()

if __name__ == "__main__":
    main()
