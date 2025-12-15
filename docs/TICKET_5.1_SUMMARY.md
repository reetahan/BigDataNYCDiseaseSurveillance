# Ticket 5.1 – Time-Series Anomaly Detection

## Objective
Detect abnormal spikes in disease mentions across NYC boroughs using
time-series analysis.

## Data Source
Processed disease surveillance data stored in TimescaleDB
(`disease_events` hypertable).

## Method
We aggregate daily counts of disease mentions per borough and disease.
A rolling Z-score method is applied:

- Rolling window: 7 days
- Mean and standard deviation computed per (borough, disease)
- An anomaly is flagged when:
  
  count > mean + 3 × standard deviation

This method is lightweight, interpretable, and well-suited for public
health monitoring.

## Implementation
- SQL aggregation using TimescaleDB `time_bucket`
- Pandas used for rolling statistics
- Output saved to `data/anomalies.csv`

## Example Output
Due to limited local data volume, no strong anomalies were detected.
The pipeline correctly handles sparse data and produces valid results.

## Limitations
- Requires sufficient historical data for stable statistics
- Does not account for seasonality or long-term trends
- Designed as a rule-based baseline, not a predictive model

## Future Work
- Add seasonal baselines
- Incorporate Isolation Forest for multivariate anomalies
- Visualize anomalies in dashboards
