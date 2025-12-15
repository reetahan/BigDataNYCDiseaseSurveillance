
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
  df["mean"] = df.groupby(["borough","disease"])["cnt"].transform(lambda x: x.rolling(7, min_periods=3).mean())
  df["std"]  = df.groupby(["borough","disease"])["cnt"].transform(lambda x: x.rolling(7, min_periods=3).std())
  df["z_score"] = (df["cnt"] - df["mean"]) / df["std"]
  anomalies = df[(df["std"].notna()) & (df["std"] != 0) & (df["z_score"] > 1.5)]
  print(f"Anomalies found: {anomalies.shape[0]}")
  try:
    anomalies.to_csv(OUTPUT_PATH, index=False)
    print(f"Wrote: {OUTPUT_PATH}")
  except Exception as e:
    print(f"Exception writing anomalies.csv: {e}")
  print("Anomalies detected:")
  print(anomalies)
