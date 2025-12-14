# Disease Outbreak Forecasting - Testing Guide (Summary)

A concise guide for setting up, testing, and running the Disease Outbreak Forecasting system.  
Covers software prerequisites, Python dependencies, PostgreSQL setup, testing procedures, troubleshooting, and performance benchmarks.

---

## 1. Prerequisites Setup

### 1.1 Install Required Software

**PostgreSQL Installation:**

- **macOS**
```bash
brew install postgresql@15
brew services start postgresql@15
```

- **Ubuntu/Debian**
```bash
sudo apt-get update
sudo apt-get install postgresql postgresql-contrib
```
* **Windows**: Download from [postgresql.org](https://www.postgresql.org/download/)

### 1.2 Install Python Dependencies

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install --upgrade pip
pip install numpy==1.26.4 pandas==2.1.4 pyarrow==14.0.1 scipy>=1.11.0
pip install pyspark==3.5.0 prophet statsmodels psycopg2-binary pytest plotly
```

**Download JDBC Driver**

```bash
wget https://jdbc.postgresql.org/download/postgresql-42.6.0.jar
```

### 1.3 Setup PostgreSQL Database

```bash
# Start PostgreSQL
brew services start postgresql@15  # macOS
sudo systemctl start postgresql    # Linux

# Create test user and database
psql -U postgres -c "CREATE USER test_user WITH PASSWORD 'test_password';"
psql -U postgres -c "CREATE DATABASE disease_test_db OWNER test_user;"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE disease_test_db TO test_user;"
```

---

## 2. Testing Approach 

| Level | Description                                              | Duration  |
| ----- | -------------------------------------------------------- | --------- |
| 1     | Integration Test - end-to-end test with DB & forecasting | 10-15 min |

### 2.1 Full Integration Test

1. **Verify Database Connection**

```bash
psql -U test_user -d disease_test_db -c "SELECT version();"
```

2. **Create Test Files**

   * `disease_outbreak_forecaster.py` (main code)
   * `postgresql-42.6.0.jar` (JDBC driver)


3. **Configure Test Parameters** in `disease_outbreak_forecaster.py`:

```python
test_config = {
    'host': 'localhost',
    'port': '5432',
    'database': 'disease_test_db',
    'user': 'test_user',
    'password': 'test_password'
}
```

4. **Run Full Integration Test**

```bash
python disease_outbreak_forecaster.py
```

5. **Monitor Progress**

* Steps: setup DB → load DB → run forecasting → validate results
* Output includes forecasts and high-risk alerts

6. **Verify Output Files**

```bash
ls -lh test_outbreak_forecast.csv
head test_outbreak_forecast.csv
```

* Columns: neighborhood, disease, forecast_date, predicted_cases, lower_bound, upper_bound, risk_level, zscore, method

---

## 3. Troubleshooting Common Issues

| Issue                        | Solution                                                                     |
| ---------------------------- | ---------------------------------------------------------------------------- |
| JDBC path not found          | download driver manually                              |
| JDBC Driver Not Found        | Ensure `.config("spark.jars", "/full/path/to/postgresql-42.6.0.jar")` is set |
| PostgreSQL Connection Failed | Check service status, verify credentials, update `pg_hba.conf`               |
| PyArrow Warning              | Install compatible versions: `pip install pandas==2.1.4 pyarrow==14.0.1`     |
| Prophet Install Fails        | Install build tools or use `conda install -c conda-forge prophet`            |
| Memory Error in Spark        | Increase memory: `.config("spark.driver.memory", "4g")`                      |
| No Forecasts Generated       | Debug with print statements, verify DB contents                              |

---

## 4. Performance Benchmarks

* Mock data generation (3000 records): ~2 sec
* DB loading: ~5 sec
* Spark loading: ~10 sec
* Forecasting (15 neighborhood-disease pairs): ~30–60 sec
* Total integration test: ~2–3 min

**If slower:** adjust Spark memory, DB indexes, `forecast_days` or `min_cases`.

---

## 5. Next Steps

* Scale up: test with larger datasets (10K+ records)
* Tune Prophet hyperparameters
* Add monitoring/alerts for high-risk forecasts
* Schedule daily jobs with cron/Airflow
* Visualize results in dashboards

---

## 6. Getting Help

* Verify prerequisites and error messages
* Run each test level separately
* Check PostgreSQL logs: `tail -f /usr/local/var/log/postgres.log`
* Review Spark logs for JDBC issues


```
