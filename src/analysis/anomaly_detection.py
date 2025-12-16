
import os
import pandas as pd
from sqlalchemy import create_engine

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "anomalies.csv")
os.makedirs(OUTPUT_DIR, exist_ok=True)

engine = create_engine("postgresql+psycopg2://postgres:postgres@localhost:5432/nyc_disease_surveillance")

query = """
SELECT
  time_bucket('1 day', timestamp) AS day,
  borough,
  unnest(diseases) AS disease,
  COUNT(*) AS cnt
FROM disease_events
WHERE borough IS NOT NULL
GROUP BY day, borough, disease
ORDER BY day;
"""

df = pd.read_sql(query, engine)
print(f"Loaded DataFrame shape: {df.shape}")

if df.empty:
  print("No rows returned from query (df is empty). Writing empty anomalies.csv anyway.")
  try:
    pd.DataFrame(columns=df.columns.tolist() + ["mean","std","z_score"]).to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote empty: {OUTPUT_PATH}")
  except Exception as e:
    print(f"Exception writing empty anomalies.csv: {e}")
else:
  # Sort by borough, disease, and day to ensure proper rolling window
  df = df.sort_values(['borough', 'disease', 'day']).reset_index(drop=True)
  
  # Calculate expanding mean and std for each borough-disease combination
  df["mean"] = df.groupby(["borough","disease"])["cnt"].transform(
      lambda x: x.shift(1).expanding(min_periods=1).mean()
  )
  df["std"] = df.groupby(["borough","disease"])["cnt"].transform(
      lambda x: x.shift(1).expanding(min_periods=1).std()
  )
  
  # Calculate z-score, handling edge cases
  # When std is 0 or NaN, use percentage change instead
  df["z_score"] = (df["cnt"] - df["mean"]) / df["std"]
  
  # For cases where std=0 (no variance), use percentage change as proxy
  # If count increases by more than 100%, flag as anomaly
  pct_change = ((df["cnt"] - df["mean"]) / df["mean"]).abs()
  df.loc[df["std"] == 0, "z_score"] = pct_change.where(pct_change > 1.0, 0)
  
  # Fill NaN z-scores (first occurrence) with 0
  df["z_score"] = df["z_score"].fillna(0)
  
  # Save ALL records (not just anomalies) so dashboard can show proper percentage
  print(f"\nSample of processed data:")
  print(df[['day', 'borough', 'disease', 'cnt', 'mean', 'std', 'z_score']].head(15))
  
  # Count anomalies for logging (z-score > 1.5)
  anomalies = df[(df["mean"].notna()) & (df["z_score"] > 1.5)]
  print(f"\nAnomalies found: {anomalies.shape[0]} out of {len(df)} records ({anomalies.shape[0]/len(df)*100:.1f}%)")
  
  try:
    df.to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote all records to: {OUTPUT_PATH}")
  except Exception as e:
    print(f"Exception writing anomalies.csv: {e}")
  
  print("\nTop anomalies detected:")
  print(anomalies[['day', 'borough', 'disease', 'cnt', 'mean', 'std', 'z_score']].head(20))

  print(df.sample(10))
