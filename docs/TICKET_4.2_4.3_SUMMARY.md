# TimescaleDB Integration for NYC Disease Surveillance

## Overview
PostgreSQL with TimescaleDB extension for time-series analysis and SQL querying of processed disease surveillance data. Loads location-enriched records from the Spark pipeline for temporal analysis, geospatial queries, and aggregations.

---

## 1. Database Schema

### Main Table: `disease_events`

**Purpose:** Hypertable (time-series optimized) storing all processed disease surveillance events

**Columns:**
```sql
CREATE TABLE disease_events (
    -- Identifiers (composite primary key for hypertable)
    id TEXT NOT NULL,                  -- Unique record ID (from source data)
    timestamp TIMESTAMPTZ NOT NULL,     -- Event timestamp (partitioning key)
    
    -- Source Information
    source TEXT NOT NULL,               -- Data source (reddit, bluesky, rss, etc.)
    text_content TEXT,                  -- Full text content
    
    -- Relevance Analysis (from Stage 3.1)
    is_relevant BOOLEAN,                -- Passed relevance filter
    diseases TEXT[],                    -- Detected diseases (array)
    symptoms TEXT[],                    -- Detected symptoms (array)
    severity TEXT,                      -- Severity level (mild, moderate, severe)
    confidence FLOAT,                   -- Relevance confidence score (0-1)
    
    -- Deduplication (from Stage 3.2)
    is_duplicate BOOLEAN,               -- Duplicate flag
    dedup_tier TEXT,                    -- Tier used (exact, fuzzy, semantic)
    similarity_score FLOAT,             -- Similarity score (0-1)
    
    -- Location Extraction (from Stage 3.3)
    borough TEXT,                       -- NYC borough (Brooklyn, Manhattan, etc.)
    neighborhood TEXT,                  -- NYC neighborhood
    latitude FLOAT,                     -- Latitude coordinate
    longitude FLOAT,                    -- Longitude coordinate
    location_source TEXT,               -- How location was determined
    extracted_locations TEXT[],         -- All extracted location entities
    
    -- Metadata
    author TEXT,                        -- Post/record author
    created_at TIMESTAMPTZ,            -- Original creation time
    processed_at TIMESTAMPTZ,          -- Pipeline processing time
    embedding_id TEXT,                  -- Reference to ChromaDB embedding
    
    -- Raw Data
    raw_data JSONB,                     -- Complete original record as JSON
    
    PRIMARY KEY (id, timestamp)
);
```

**Indexes:**
- `idx_disease_events_timestamp` - Time-based queries (DESC for recent-first)
- `idx_disease_events_borough` - Geospatial filtering by borough
- `idx_disease_events_neighborhood` - Geospatial filtering by neighborhood
- `idx_disease_events_severity` - Severity-based filtering
- `idx_disease_events_diseases` - GIN index for array contains queries
- `idx_disease_events_symptoms` - GIN index for array contains queries
- `idx_disease_events_is_relevant` - Partial index for relevant records only
- `idx_disease_events_is_duplicate` - Partial index for unique records only

---

### Materialized Views

#### `daily_disease_counts`
**Purpose:** Pre-aggregated daily disease counts by borough

```sql
CREATE MATERIALIZED VIEW daily_disease_counts AS
SELECT 
    time_bucket('1 day', timestamp) AS day,
    borough,
    unnest(diseases) AS disease,
    COUNT(*) AS count,
    AVG(confidence) AS avg_confidence
FROM disease_events
WHERE is_relevant = TRUE AND is_duplicate = FALSE
GROUP BY day, borough, disease
ORDER BY day DESC, count DESC;
```

**Use Case:** Fast dashboard queries for disease trends over time

---

#### `borough_severity_summary`
**Purpose:** Current severity distribution by borough

```sql
CREATE MATERIALIZED VIEW borough_severity_summary AS
SELECT 
    borough,
    severity,
    COUNT(*) AS count,
    MAX(timestamp) AS last_event
FROM disease_events
WHERE is_relevant = TRUE AND is_duplicate = FALSE
GROUP BY borough, severity
ORDER BY borough, severity;
```

**Use Case:** Real-time severity heatmap visualization

---

## 2. How It Works

### Data Flow
```
Spark Pipeline (Stage 3.3)
    ↓
data/locations/*.json (location-enriched records)
    ↓
TimescaleDB Loader (psql_db_client.py)
    ↓
PostgreSQL + TimescaleDB (disease_events hypertable)
    ↓
SQL Queries / Materialized Views / Analytics
```

### Key Features

**1. Hypertable Partitioning**
- Automatically partitions data by `timestamp` into chunks
- Optimizes time-series queries (recent data retrieved faster)
- Enables efficient data retention policies

**2. Composite Primary Key**
- `(id, timestamp)` ensures uniqueness across time
- Required for TimescaleDB hypertables
- Handles duplicate IDs at different times

**3. Array Columns**
- `diseases` and `symptoms` stored as PostgreSQL arrays
- Enables multi-disease records (e.g., "COVID-19 and Influenza")
- Use `@>` operator for contains queries: `WHERE diseases @> ARRAY['COVID-19']`

**4. JSONB Storage**
- Full original record preserved in `raw_data`
- Allows schema flexibility for different source types
- Supports JSON querying: `raw_data->>'field_name'`

**5. Materialized Views**
- Pre-computed aggregations for fast dashboards
- Refresh manually or on schedule
- Trade-off: slightly stale data for fast queries

---

## 3. Running Locally

### Prerequisites
- Docker & Docker Compose
- Python 3.12+ with virtual environment
- Completed Spark pipeline (data in `src/data/locations/`)

### Step-by-Step Setup

#### 1. Start TimescaleDB Container
```bash
cd /path/to/BigDataNYCDiseaseSurveillance

# Start only TimescaleDB
docker-compose up -d timescaledb

# Verify it's running
docker ps | grep timescaledb
```

#### 2. Install Python Dependencies
```bash
# Activate your virtual environment
source ~/Classes/CSGY6513/bigdata/bin/activate

# Install psycopg2 (PostgreSQL adapter)
pip install psycopg2-binary
```

#### 3. Initialize Database Schema
```bash
cd src

# Create tables, hypertable, indexes, and views
python database/psql_db_client.py --init-schema
```

**Expected Output:**
```
✓ Connected to TimescaleDB
Creating schema...
✓ Created hypertable for disease_events
✓ Schema created successfully
```

#### 4. Load Processed Data
```bash
# Load from locations directory (full enriched data)
python database/psql_db_client.py --data-dir data/locations --refresh-views
```

**Expected Output:**
```
Loading from directory: data/locations
Found 1 files
✓ Loaded 12681 records
Total records loaded: 12681

TimescaleDB Statistics
Total Records: 12681
Relevant Records: 12681
Unique Records: 12681
Records by Borough:
  Brooklyn: 90
  Manhattan: 84
  ...
```

#### 5. Verify Data Loaded
```bash
# Connect to database
docker exec -it timescaledb psql -U postgres -d nyc_disease_surveillance

# Run sample queries
\dt                                    # List tables
SELECT COUNT(*) FROM disease_events;   # Count records
\q                                     # Exit
```

---

### Alternative Data Sources

**Load from different pipeline stages:**

```bash
# From relevance-filtered data (earliest stage)
python database/psql_db_client.py --data-dir data/relevance/relevant

# From deduplicated data (unique records only)
python database/psql_db_client.py --data-dir data/deduplicated

# From locations (RECOMMENDED - full enrichment)
python database/psql_db_client.py --data-dir data/locations
```

**Note:** Don't load from `data/embeddings/` - that's for ChromaDB (different format)

---

## 4. Usage Examples

### Connecting to Database

**Via psql (command line):**
```bash
docker exec -it timescaledb psql -U postgres -d nyc_disease_surveillance
```

**Via Python:**
```python
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    database='nyc_disease_surveillance',
    user='postgres',
    password='postgres'
)
cursor = conn.cursor()
```

**Via GUI (DBeaver, pgAdmin, TablePlus):**
- Host: `localhost`
- Port: `5432`
- Database: `nyc_disease_surveillance`
- User: `postgres`
- Password: `postgres`

---

### Sample SQL Queries

**1. Disease counts by borough:**
```sql
SELECT 
    borough,
    unnest(diseases) AS disease,
    COUNT(*) AS cases
FROM disease_events
WHERE borough IS NOT NULL
GROUP BY borough, disease
ORDER BY cases DESC;
```

**2. Recent severe cases in Brooklyn:**
```sql
SELECT 
    timestamp,
    diseases,
    symptoms,
    text_content
FROM disease_events
WHERE borough = 'Brooklyn'
  AND severity = 'severe'
ORDER BY timestamp DESC
LIMIT 10;
```

**3. COVID-19 trend over last 7 days:**
```sql
SELECT 
    time_bucket('1 day', timestamp) AS day,
    COUNT(*) AS covid_mentions
FROM disease_events
WHERE diseases @> ARRAY['COVID-19']
  AND timestamp > NOW() - INTERVAL '7 days'
GROUP BY day
ORDER BY day DESC;
```

**4. Multi-disease events:**
```sql
SELECT 
    diseases,
    borough,
    COUNT(*) AS count
FROM disease_events
WHERE array_length(diseases, 1) > 1  -- More than one disease
GROUP BY diseases, borough
ORDER BY count DESC;
```

**5. Query raw JSON data:**
```sql
SELECT 
    id,
    raw_data->>'subreddit' AS subreddit,
    raw_data->>'author' AS author
FROM disease_events
WHERE source = 'reddit'
LIMIT 5;
```

**6. Use materialized views:**
```sql
-- Fast pre-aggregated query
SELECT * FROM daily_disease_counts
WHERE day > NOW() - INTERVAL '30 days'
  AND borough = 'Manhattan'
ORDER BY day DESC;

-- Refresh views after loading new data
REFRESH MATERIALIZED VIEW daily_disease_counts;
REFRESH MATERIALIZED VIEW borough_severity_summary;
```

---

## 5. Considerations & Best Practices

### Performance

**1. Query Optimization**
- Always filter by `timestamp` first for time-series queries
- Use `@>` for array containment, not `= ANY(array)`
- Index on frequently queried columns (already done for borough, severity, etc.)
- Use `EXPLAIN ANALYZE` to debug slow queries

**2. Hypertable Benefits**
- Recent data retrieved faster (partitioned by time)
- Old data can be compressed or dropped automatically
- Continuous aggregates for real-time dashboards

**3. Materialized View Trade-offs**
- **Pros:** Very fast queries (pre-computed)
- **Cons:** Slightly stale data until refresh
- **Solution:** Refresh on schedule or after data loads

---

### Data Quality

**1. NULL Handling**
- Borough/neighborhood often NULL (location extraction isn't perfect)
- Filter with `WHERE borough IS NOT NULL` for location-based queries
- `diseases` and `symptoms` can be empty arrays `{}`

**2. Duplicate Prevention**
- Composite key `(id, timestamp)` allows same ID at different times
- `is_duplicate` field already set by deduplication pipeline
- Filter duplicates: `WHERE is_duplicate = FALSE`

**3. Data Validation**
- Check `confidence` scores (0-1 range)
- Verify `severity` values (mild, moderate, severe)
- Validate `timestamp` vs `created_at` vs `processed_at`

---

### Scaling Considerations

**1. Data Volume**
- Current: 12,681 records (~270 with locations)
- TimescaleDB handles millions of rows efficiently
- Consider partitioning by month for very large datasets

**2. Retention Policies**
```sql
-- Auto-drop data older than 1 year (optional)
SELECT add_retention_policy('disease_events', INTERVAL '1 year');
```

**3. Continuous Aggregates**
```sql
-- Real-time materialized views (auto-refresh)
CREATE MATERIALIZED VIEW hourly_counts
WITH (timescaledb.continuous) AS
SELECT 
    time_bucket('1 hour', timestamp) AS hour,
    borough,
    COUNT(*)
FROM disease_events
GROUP BY hour, borough;
```

**4. Compression**
```sql
-- Compress old data (saves 90%+ space)
ALTER TABLE disease_events SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'borough'
);

SELECT add_compression_policy('disease_events', INTERVAL '7 days');
```

---

### Security

**1. Production Deployment**
- Change default password: `postgres/postgres`
- Use environment variables for credentials
- Enable SSL connections
- Restrict network access (firewall, VPC)

**2. Access Control**
```sql
-- Create read-only user for dashboards
CREATE USER readonly_user WITH PASSWORD 'secure_password';
GRANT SELECT ON disease_events TO readonly_user;
```

---

### Maintenance

**1. Regular Tasks**
```bash
# Refresh materialized views (weekly or after data loads)
python database/psql_db_client.py --refresh-views

# Vacuum and analyze (monthly)
docker exec -it timescaledb psql -U postgres -d nyc_disease_surveillance \
    -c "VACUUM ANALYZE disease_events;"

# Check database size
docker exec -it timescaledb psql -U postgres -d nyc_disease_surveillance \
    -c "SELECT pg_size_pretty(pg_database_size('nyc_disease_surveillance'));"
```

**2. Backup & Restore**
```bash
# Backup
docker exec -t timescaledb pg_dump -U postgres nyc_disease_surveillance \
    > backup_$(date +%Y%m%d).sql

# Restore
cat backup_20251213.sql | docker exec -i timescaledb \
    psql -U postgres -d nyc_disease_surveillance
```

---

### Integration with Other Components

**1. ChromaDB (Vector Search)**
- TimescaleDB: Structured queries, time-series, geospatial
- ChromaDB: Semantic similarity search
- Use `embedding_id` to link records between both

**2. Visualization**
- Connect Grafana, Metabase, or Tableau to TimescaleDB
- Use materialized views for real-time dashboards
- Query REST API via PostgREST (optional)

**3. Pipeline Integration**
- Run loader after Stage 3.3 (location enrichment)
- Add to `run_project.py` for automatic loading
- Monitor for new files in `data/locations/`

---

## Troubleshooting

**Issue:** "relation does not exist"
```bash
# Solution: Initialize schema
python database/psql_db_client.py --init-schema
```

**Issue:** "null value violates not-null constraint"
```bash
# Solution: ID extraction failed, fixed in latest version
# Regenerate location data or manually set IDs
```

**Issue:** "no such file or directory: data/locations"
```bash
# Solution: Run from src/ directory
cd src
python database/psql_db_client.py
```

**Issue:** Container not running
```bash
# Solution: Start TimescaleDB
docker-compose up -d timescaledb

# Check logs
docker logs timescaledb
```

**Issue:** Slow queries
```sql
-- Solution: Check query plan
EXPLAIN ANALYZE SELECT ...;

-- Ensure timestamp filter present
WHERE timestamp > NOW() - INTERVAL '30 days'
```

---

## Summary

✅ **TimescaleDB Setup Complete**
- Hypertable optimized for time-series queries
- 12,681 records loaded with full enrichment
- Materialized views for fast aggregations
- Ready for SQL analytics and visualization

✅ **Next Steps**
- Build dashboards (Grafana, Streamlit, etc.)
- Set up scheduled data loads
- Add continuous aggregates for real-time views
- Integrate with ChromaDB for hybrid search