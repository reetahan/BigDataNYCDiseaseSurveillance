"""
Disease Outbreak Forecasting System
Uses PySpark to process data from PostgreSQL and Prophet/statsmodels for forecasting
"""
import os
import sys
# Configure PySpark environment before any imports
os.environ['PYSPARK_SUBMIT_ARGS'] = '--packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0 --conf spark.driver.extraJavaOptions=-Djava.security.manager.allow=true --conf spark.executor.extraJavaOptions=-Djava.security.manager.allow=true pyspark-shell'
os.environ['SPARK_LOCAL_IP'] = '127.0.0.1'
if sys.version_info >= (3, 0):
    os.environ['PYSPARK_PYTHON'] = sys.executable
    os.environ['PYSPARK_DRIVER_PYTHON'] = sys.executable

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, count, window, date_trunc, to_date,
    explode, concat_ws, avg, sum as spark_sum,
    lag, lead, stddev, collect_list, struct, pandas_udf, PandasUDFType
)
from pyspark.sql.window import Window
from pyspark.sql.types import *
import pandas as pd
from prophet import Prophet
from statsmodels.tsa.statespace.sarimax import SARIMAX
from statsmodels.tsa.holtwinters import ExponentialSmoothing
import numpy as np
from datetime import datetime, timedelta
import warnings
import platform

warnings.filterwarnings('ignore')

# --- SPARK-CENTRIC CHANGE 1: DEFINE OUTPUT SCHEMA ---
# Spark needs to know what the UDF returns before it runs
FORECAST_OUTPUT_SCHEMA = StructType([
    StructField("neighborhood", StringType(), True),
    StructField("disease", StringType(), True),
    StructField("date", TimestampType(), True),
    StructField("predicted_cases", DoubleType(), True),
    StructField("lower_bound", DoubleType(), True),
    StructField("upper_bound", DoubleType(), True),
    StructField("risk_level", StringType(), True),
    StructField("zscore", DoubleType(), True),
    StructField("method", StringType(), True),
    StructField("historical_mean", DoubleType(), True),
    StructField("historical_std", DoubleType(), True)
])

# --- SPARK-CENTRIC CHANGE 2: MOVE HELPER FUNCTIONS OUTSIDE CLASS ---
# These must be standalone functions so Spark can serialize them to worker nodes.

def forecast_prophet(neighborhood_data, forecast_days=14):
    """Standalone Prophet forecaster for Spark UDF"""
    if len(neighborhood_data) < 14:
        return None

    prophet_df = neighborhood_data[['date', 'case_count']].copy()
    prophet_df.columns = ['ds', 'y']
    prophet_df['ds'] = pd.to_datetime(prophet_df['ds'])

    model = Prophet(
        changepoint_prior_scale=0.05,
        seasonality_prior_scale=10,
        daily_seasonality=True,
        weekly_seasonality=True,
        yearly_seasonality=False
    )

    try:
        model.fit(prophet_df)
        future = model.make_future_dataframe(periods=forecast_days)
        forecast = model.predict(future)

        # Extract forecast for future dates only
        last_date = prophet_df['ds'].max()
        forecast_future = forecast[forecast['ds'] > last_date][['ds', 'yhat', 'yhat_lower', 'yhat_upper']].copy()
        forecast_future.columns = ['date', 'predicted_cases', 'lower_bound', 'upper_bound']

        forecast_future['predicted_cases'] = forecast_future['predicted_cases'].clip(lower=0)
        forecast_future['lower_bound'] = forecast_future['lower_bound'].clip(lower=0)
        forecast_future['upper_bound'] = forecast_future['upper_bound'].clip(lower=0)
        return forecast_future

    except Exception as e:
        return None

def forecast_sarima(neighborhood_data, forecast_days=14):
    """Standalone SARIMA forecaster for Spark UDF"""
    if len(neighborhood_data) < 30:
        return None

    try:
        ts_data = neighborhood_data.set_index('date')['case_count']

        # Simple SARIMA config
        model = SARIMAX(
            ts_data,
            order=(1, 1, 1),
            seasonal_order=(1, 1, 1, 7),
            enforce_stationarity=False,
            enforce_invertibility=False
        )

        fitted_model = model.fit(disp=False)
        forecast = fitted_model.forecast(steps=forecast_days)
        forecast_result = fitted_model.get_forecast(steps=forecast_days)
        ci = forecast_result.conf_int()

        last_date = ts_data.index[-1]
        future_dates = pd.date_range(start=last_date + timedelta(days=1), periods=forecast_days)

        result = pd.DataFrame({
            'date': future_dates,
            'predicted_cases': forecast.values.clip(min=0),
            'lower_bound': ci.iloc[:, 0].values.clip(min=0),
            'upper_bound': ci.iloc[:, 1].values.clip(min=0)
        })
        return result

    except Exception as e:
        return None

def detect_outbreak_risk(forecast_df, historical_mean, historical_std):
    """Standalone risk classifier"""
    if forecast_df is None or len(forecast_df) == 0:
        return None

    forecast_df = forecast_df.copy()
    # Avoid division by zero
    safe_std = historical_std if historical_std > 0 else 1.0
    forecast_df['zscore'] = (forecast_df['predicted_cases'] - historical_mean) / safe_std

    def classify_risk(zscore):
        if zscore > 2.5: return 'CRITICAL'
        elif zscore > 1.5: return 'HIGH'
        elif zscore > 0.5: return 'MODERATE'
        else: return 'LOW'

    forecast_df['risk_level'] = forecast_df['zscore'].apply(classify_risk)
    return forecast_df

# --- SPARK-CENTRIC CHANGE 3: THE WORKER LOGIC ---
def forecast_worker_logic(pdf):
    """
    This function runs on the worker node.
    Input: Pandas DataFrame for ONE neighborhood/disease
    Output: Pandas DataFrame with forecast
    """
    neighborhood = pdf['neighborhood'].iloc[0]
    disease = pdf['disease'].iloc[0]

    # Sort and prep
    pdf['date'] = pd.to_datetime(pdf['date'])
    pdf = pdf.sort_values('date')

    total_cases = pdf['case_count'].sum()
    if total_cases < 10:
        return pd.DataFrame(columns=FORECAST_OUTPUT_SCHEMA.names)

    hist_mean = pdf['case_count'].mean()
    hist_std = pdf['case_count'].std()

    # Try Prophet
    forecast = forecast_prophet(pdf, 14)
    method = 'Prophet'

    # Try SARIMA fallback
    if forecast is None and len(pdf) >= 30:
        forecast = forecast_sarima(pdf, 14)
        method = 'SARIMA'

    if forecast is not None:
        forecast = detect_outbreak_risk(forecast, hist_mean, hist_std)

        # Fill in metadata columns required by Schema
        forecast['neighborhood'] = neighborhood
        forecast['disease'] = disease
        forecast['method'] = method
        forecast['historical_mean'] = hist_mean
        forecast['historical_std'] = hist_std

        # Ensure column order matches schema exactly
        return forecast[FORECAST_OUTPUT_SCHEMA.names]

    if forecast is not None:
        # ... existing logic ...

        # ADD THIS BLOCK TO FORCE TYPES
        forecast['predicted_cases'] = forecast['predicted_cases'].astype(float)
        forecast['lower_bound'] = forecast['lower_bound'].astype(float)
        forecast['upper_bound'] = forecast['upper_bound'].astype(float)
        forecast['zscore'] = forecast['zscore'].astype(float)
        forecast['historical_mean'] = forecast['historical_mean'].astype(float)
        forecast['historical_std'] = forecast['historical_std'].astype(float)

        return forecast[FORECAST_OUTPUT_SCHEMA.names]

    return pd.DataFrame(columns=FORECAST_OUTPUT_SCHEMA.names)


class DiseaseOutbreakForecaster:
    """
    Forecasts disease outbreaks by neighborhood using historical data
    """

    def __init__(self, postgres_config):
        """
        Initialize Spark session and database connection
        """
        # --- YOUR ORIGINAL WINDOWS LOGIC (PRESERVED) ---
        if platform.system() == 'Windows':
            if 'HADOOP_HOME' not in os.environ:
                # Try common locations
                possible_homes = [
                    os.path.join(os.path.expanduser("~"), "hadoop"),
                    r"C:\hadoop",
                    os.path.join(os.environ.get('USERPROFILE', ''), 'hadoop')
                ]

                for hadoop_home in possible_homes:
                    winutils = os.path.join(hadoop_home, 'bin', 'winutils.exe')
                    if os.path.exists(winutils):
                        os.environ['HADOOP_HOME'] = hadoop_home
                        os.environ['PATH'] += os.pathsep + os.path.join(hadoop_home, 'bin')
                        print(f"Set HADOOP_HOME to: {hadoop_home}")
                        break
                else:
                    print("WARNING: HADOOP_HOME not set! Spark will likely fail on Windows.")
                    print("Please download winutils.exe and place it in C:\\hadoop\\bin")

        # Find PostgreSQL JDBC driver (Your original logic)
        import glob
        possible_paths = [
            "postgresql-*.jar",
            "../postgresql-*.jar",
            "../../postgresql-*.jar",
            os.path.join(os.getcwd(), "postgresql-*.jar"),
            os.path.join(os.path.dirname(__file__), "postgresql-*.jar"),
        ]

        jdbc_jar = None
        for pattern in possible_paths:
            matches = glob.glob(pattern)
            if matches:
                jdbc_jar = os.path.abspath(matches[0])
                break

        if not jdbc_jar:
             # Fallback if not found locally, though usually better to pass via submit
             jdbc_jar = "postgresql-42.6.0.jar"

        self.spark = SparkSession.builder \
            .appName("DiseaseOutbreakForecasting") \
            .master("local[2]") \
            .config("spark.jars", jdbc_jar) \
            .config("spark.sql.adaptive.enabled", "true") \
            .config("spark.sql.execution.arrow.pyspark.enabled", "false") \
            .config("spark.driver.extraClassPath", jdbc_jar) \
            .getOrCreate()

        self.postgres_config = postgres_config
        self.jdbc_url = f"jdbc:postgresql://{postgres_config['host']}:{postgres_config['port']}/{postgres_config['database']}"

    def load_disease_data(self, start_date=None, end_date=None):
        """Load disease events from PostgreSQL into Spark DataFrame"""
        query = """
        (SELECT
            id, timestamp, source, text_content,
            is_relevant, diseases, symptoms, severity, confidence,
            is_duplicate, borough, neighborhood,
            latitude, longitude, location_source,
            author, created_at, processed_at
        FROM disease_events
        WHERE is_relevant = true
        AND is_duplicate = false
        AND borough IS NOT NULL
        AND neighborhood IS NOT NULL
        """
        if start_date: query += f" AND timestamp >= '{start_date}'"
        if end_date: query += f" AND timestamp <= '{end_date}'"
        query += ") as disease_data"

        return self.spark.read \
            .format("jdbc") \
            .option("url", self.jdbc_url) \
            .option("dbtable", query) \
            .option("user", self.postgres_config['user']) \
            .option("password", self.postgres_config['password']) \
            .option("driver", "org.postgresql.Driver") \
            .load()

    def aggregate_by_neighborhood_daily(self, df):
        """Aggregate disease events by neighborhood and day"""
        df_exploded = df.select(
            col("timestamp"),
            col("borough"),
            col("neighborhood"),
            col("severity"),
            explode(col("diseases")).alias("disease")
        )
        return df_exploded.groupBy(
            date_trunc("day", col("timestamp")).alias("date"),
            col("borough"),
            col("neighborhood"),
            col("disease")
        ).agg(
            count("*").alias("case_count"),
            spark_sum(col("severity").cast("string").isin(["severe"]).cast("int")).alias("severe_cases")
        )

    def create_time_series_features(self, df):
        """Create lag features (Preserved from original code)"""
        window_spec = Window.partitionBy("neighborhood", "disease").orderBy("date")
        df_featured = df.withColumn("lag_1", lag("case_count", 1).over(window_spec)) \
                       .withColumn("lag_7", lag("case_count", 7).over(window_spec)) \
                       .withColumn("lag_14", lag("case_count", 14).over(window_spec))

        rolling_window = Window.partitionBy("neighborhood", "disease").orderBy("date").rowsBetween(-6, 0)
        df_featured = df_featured.withColumn("rolling_avg_7d", avg("case_count").over(rolling_window)) \
                                 .withColumn("rolling_std_7d", stddev("case_count").over(rolling_window))
        return df_featured

    def forecast_all_neighborhoods(self, forecast_days=14, min_cases=10):
            """
            Generate forecasts for all neighborhoods (Driver-Side Loop Version)
            Stable on Windows.
            """
            # 1. Load Data using Spark (This is fast and fine)
            print("Loading data from database...")
            df = self.load_disease_data()

            # 2. Aggregate using Spark (Also fast and fine)
            print("Aggregating daily stats...")
            daily_df = self.aggregate_by_neighborhood_daily(df)

            # 3. CRITICAL CHANGE: Bring data to Driver to avoid Windows Worker Crash
            # We convert to Pandas HERE, before forecasting
            print("Collecting data for forecasting...")
            all_data_pd = daily_df.toPandas()

            # Ensure dates are datetime objects
            all_data_pd['date'] = pd.to_datetime(all_data_pd['date'])

            # 4. Run Forecasting Loop Locally
            print(f"Starting forecasting for {len(all_data_pd)} records...")
            forecasts = {}

            # Group by neighborhood and disease using Pandas
            grouped = all_data_pd.groupby(['neighborhood', 'disease'])

            total_groups = len(grouped)
            processed = 0

            for (neighborhood, disease), group in grouped:
                processed += 1
                if processed % 10 == 0:
                    print(f"Processing {processed}/{total_groups}...")

                # reuse your existing logic, but call it directly
                # We treat the group exactly like the worker did

                # --- Logic from previous forecast_worker_logic ---
                group = group.sort_values('date')
                total_cases = group['case_count'].sum()

                if total_cases < min_cases:
                    continue

                hist_mean = group['case_count'].mean()
                hist_std = group['case_count'].std()

                # Try Prophet
                forecast = forecast_prophet(group, forecast_days)
                method = 'Prophet'

                # Try SARIMA fallback
                if forecast is None and len(group) >= 30:
                    forecast = forecast_sarima(group, forecast_days)
                    method = 'SARIMA'

                if forecast is not None:
                    forecast = detect_outbreak_risk(forecast, hist_mean, hist_std)

                    # Store in dictionary (Format matching your report generator)
                    forecasts[(neighborhood, disease)] = {
                        'forecast': forecast,
                        'method': method,
                        'historical_mean': hist_mean,
                        'historical_std': hist_std,
                        'total_historical_cases': total_cases
                    }

            return forecasts

    def generate_outbreak_report(self, forecasts, output_file=r'forecast\outbreak_forecast.csv'):
        """Generate comprehensive outbreak forecast report (Preserved)"""
        report_data = []

        for (neighborhood, disease), forecast_info in forecasts.items():
            forecast = forecast_info['forecast']
            for _, row in forecast.iterrows():
                report_data.append({
                    'neighborhood': neighborhood,
                    'disease': disease,
                    'forecast_date': row['date'],
                    'predicted_cases': row['predicted_cases'],
                    'lower_bound': row['lower_bound'],
                    'upper_bound': row['upper_bound'],
                    'risk_level': row['risk_level'],
                    'zscore': row['zscore'],
                    'method': forecast_info['method'],
                    'historical_mean': forecast_info['historical_mean'],
                    'historical_std': forecast_info['historical_std']
                })

        report_df = pd.DataFrame(report_data)
        # Ensure directory exists
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        report_df.to_csv(output_file, index=False)
        print(f"\nForecast report saved to {output_file}")
        return report_df

    def get_high_risk_alerts(self, forecasts, risk_threshold='HIGH'):
        """Filter and return high-risk outbreak alerts (Preserved)"""
        risk_levels = {'MODERATE': 1, 'HIGH': 2, 'CRITICAL': 3}
        threshold_value = risk_levels.get(risk_threshold, 2)

        alerts = []
        for (neighborhood, disease), forecast_info in forecasts.items():
            forecast = forecast_info['forecast']
            high_risk_days = forecast[
                forecast['risk_level'].map(lambda x: risk_levels.get(x, 0)) >= threshold_value
            ]

            if len(high_risk_days) > 0:
                alerts.append({
                    'neighborhood': neighborhood,
                    'disease': disease,
                    'risk_days': len(high_risk_days),
                    'max_risk': high_risk_days['risk_level'].iloc[0],
                    'max_predicted_cases': high_risk_days['predicted_cases'].max(),
                    'alert_date': high_risk_days['date'].iloc[0],
                    'historical_mean': forecast_info['historical_mean']
                })

        if not alerts:
            return pd.DataFrame()
        return pd.DataFrame(alerts).sort_values('max_predicted_cases', ascending=False)

    def close(self):
        """Clean up Spark session"""
        self.spark.stop()


# Example usage
if __name__ == "__main__":
    # Database configuration
    postgres_config = {
        'host': 'localhost',
        'port': '5432',
        'database': 'disease_test_db',
        'user': 'postgres',
        'password': 'your_password'
    }

    # Initialize forecaster
    forecaster = DiseaseOutbreakForecaster(postgres_config)

    try:
        # Generate 14-day forecasts for all neighborhoods
        print("Generating disease outbreak forecasts...")
        forecasts = forecaster.forecast_all_neighborhoods(
            forecast_days=14,
            min_cases=10
        )

        # Generate comprehensive report
        report = forecaster.generate_outbreak_report(forecasts)

        # Get high-risk alerts
        alerts = forecaster.get_high_risk_alerts(forecasts, risk_threshold='HIGH')

        print("\n" + "="*80)
        print("HIGH-RISK OUTBREAK ALERTS")
        print("="*80)
        if not alerts.empty:
            print(alerts.to_string(index=False))
        else:
            print("No high risk alerts found.")

        # Display summary statistics
        print("\n" + "="*80)
        print("FORECAST SUMMARY")
        print("="*80)
        if forecasts:
            print(f"Total neighborhoods forecasted: {len(set([k[0] for k in forecasts.keys()]))}")
            print(f"Total diseases tracked: {len(set([k[1] for k in forecasts.keys()]))}")
            print(f"High-risk alerts: {len(alerts)}")

    finally:
        forecaster.close()
