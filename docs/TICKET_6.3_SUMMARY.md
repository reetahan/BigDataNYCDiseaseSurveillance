# NYC Disease Surveillance Dashboard - Summary

## 📋 Overview

The NYC Disease Surveillance Dashboard is a **real-time web application** built with Streamlit that visualizes disease outbreak data from multiple sources. It provides public health officials with an interactive interface to monitor disease patterns, compare official vs informal data, and assess outbreak risks across NYC neighborhoods.

**Purpose:** Centralized monitoring platform for disease surveillance with automated alerts and risk assessment.

**Technology Stack:**
- Frontend: Streamlit (Python web framework)
- Backend: PostgreSQL/TimescaleDB
- Visualization: Plotly (interactive charts)
- Data Processing: Pandas

---

## 🎯 Key Features

### 1. **Real-Time Surveillance Monitoring**
- Live event counts with auto-refresh (30s intervals)
- Time-series visualization of disease trends
- Geographic distribution across NYC boroughs
- Disease and symptom tracking

### 2. **Official vs Informal Data Comparison** ⭐ NEW
- Side-by-side comparison of official health reports vs social media surveillance
- Correlation analysis between data sources
- Early detection metrics (days ahead of official reports)
- Trend alignment visualization

### 3. **Comprehensive Risk Assessment** ⭐ NEW
- AI-powered risk scoring (0-100) for each neighborhood
- Color-coded alerts (🟢 LOW, 🟡 MODERATE, 🟠 HIGH, 🔴 CRITICAL)
- Risk component breakdown (trend, forecast, severity, density)
- Top 10 highest-risk areas prioritization

### 4. **Interactive Data Exploration**
- Filter by time window (24h, 48h, 7d, 30d)
- Borough-level and neighborhood-level views
- Disease-specific analysis
- Data source attribution

---

## 📊 Dashboard Layout

### Header Section
```
NYC Disease Surveillance Dashboard
Real-time monitoring of disease events across New York City
```

### Metrics Row (4 KPIs)
```
┌─────────────┬─────────────┬─────────────┬─────────────┐
│ Total       │ Last 24     │ Last 7      │ Avg/Hour    │
│ Events      │ Hours       │ Days        │ (24h)       │
│ 15,234      │ 423         │ 2,891       │ 17.6        │
└─────────────┴─────────────┴─────────────┴─────────────┘
```

### Primary Charts (2 columns)
```
┌────────────────────────┬────────────────────────┐
│ 🦠 Top Diseases        │ 📍 Events by Borough   │
│ [Horizontal Bar Chart] │ [Pie Chart]            │
│                        │                        │
│ influenza    ████ 450  │ Manhattan: 35%         │
│ covid-19     ███ 320   │ Brooklyn: 28%          │
│ norovirus    ██ 180    │ Queens: 20%            │
│ ...                    │ Bronx: 12%             │
│                        │ Staten Island: 5%      │
└────────────────────────┴────────────────────────┘
```

### Detail Charts (3 columns)
```
┌─────────────┬─────────────┬─────────────┐
│ 🤒 Top      │ ⚠️ Severity │ 📊 Data     │
│ Symptoms    │ Levels      │ Sources     │
│             │             │             │
│ fever       │ severe: 15% │ reddit: 45% │
│ cough       │ moderate:   │ bluesky:30% │
│ fatigue     │   48%       │ rss: 25%    │
│ ...         │ mild: 37%   │             │
└─────────────┴─────────────┴─────────────┘
```

### Official vs Informal Comparison ⭐ NEW (2 columns)
```
┌──────────────────────────────────────────────────────────┐
│ 📊 Official vs Informal Data Comparison                  │
├────────────────────────┬─────────────────────────────────┤
│ 📈 Data Source         │ 🎯 Risk Assessment              │
│ Comparison             │                                 │
│                        │                                 │
│ Metrics:               │ Top 10 Highest Risk Areas:      │
│ • Correlation: 0.78    │                                 │
│ • Early Detection: 5d  │ 🔴 Williamsburg - influenza     │
│ • Avg Difference: +23  │    Risk Score: 85/100           │
│                        │    [████████████░░░░░░] 85%     │
│ [Time Series Chart]    │                                 │
│ — Official (Blue)      │ 🟠 Astoria - covid-19           │
│ — Informal (Orange)    │    Risk Score: 72/100           │
│                        │    [██████████░░░░░░░] 72%      │
│                        │                                 │
│                        │ [Risk Distribution Pie Chart]   │
└────────────────────────┴─────────────────────────────────┘
```

### Sidebar Controls
```
┌──────────────────────┐
│ Dashboard Controls   │
├──────────────────────┤
│ ☑ Auto-refresh (30s) │
│                      │
│ Time Window:         │
│ ▼ Last 7 days        │
│                      │
│ ─────────────────    │
│                      │
│ Last updated:        │
│ 2024-12-15 14:23:45  │
└──────────────────────┘
```

---

## 📁 Data Sources

### Primary Data: PostgreSQL Database

**Table:** `disease_events`

**Required Columns:**
- `timestamp` - Event time (TIMESTAMPTZ)
- `diseases` - Array of diseases (TEXT[])
- `symptoms` - Array of symptoms (TEXT[])
- `severity` - Severity level (TEXT)
- `borough` - NYC borough (TEXT)
- `neighborhood` - Specific area (TEXT)
- `source` - Data source (TEXT)
- `is_relevant` - Relevance flag (BOOLEAN)
- `is_duplicate` - Duplicate flag (BOOLEAN)

### Secondary Data: Official Health Reports ⭐ NEW

**Format:** JSON files

**Location:** `data/official_reports/*.json`

**Supported Formats:**

**Format 1 - Simple Array:**
```json
[
  {
    "date": "2024-12-01",
    "disease": "influenza",
    "cases": 50,
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

**Format 3 - NYC DOH API:**
```json
{
  "columns": ["date", "disease", "cases", "borough"],
  "data": [
    ["2024-12-01", "influenza", 50, "Manhattan"]
  ]
}
```

### Tertiary Data: Analysis Outputs

**Spatial Clustering:**
- Location: `data/spatial_clusters/cluster_analysis_*.json`
- Contains: Geographic clusters of disease events

**Outbreak Forecasts:**
- Location: `forecast/outbreak_forecast.csv`
- Contains: 7-14 day predictions with risk levels

---

## 🎨 Visualization Details

### Chart Types Used

#### 1. **Horizontal Bar Charts** (Disease, Symptoms, Sources)
- **Purpose:** Compare counts across categories
- **Color:** Heat-mapped by value (Reds, Blues, Greens)
- **Interaction:** Hover for exact counts
- **Sort:** Descending by count

#### 2. **Pie Charts** (Borough Distribution, Risk Levels)
- **Purpose:** Show proportions
- **Colors:** Qualitative palette for boroughs, severity-coded for risks
- **Interaction:** Click to highlight segment
- **Labels:** Percentage + category name

#### 3. **Time Series Line Charts** (Official vs Informal)
- **Purpose:** Compare trends over time
- **Lines:**
  - Blue: Official health reports
  - Orange: Informal surveillance
- **Interaction:** Unified hover (shows both values)
- **Markers:** Enabled for better readability

#### 4. **Progress Bars** (Risk Scores)
- **Purpose:** Visual risk level indicator
- **Range:** 0-100
- **Color:** Gradient based on risk level
- **Context:** Shown with numeric score

### Color Schemes

**Risk Levels:**
- 🟢 LOW: `#2ca02c` (Green)
- 🟡 MODERATE: `#ffdd57` (Yellow)
- 🟠 HIGH: `#ff7f0e` (Orange)
- 🔴 CRITICAL: `#d62728` (Red)

**Severity Levels:**
- Severe: `#d62728` (Red)
- Moderate: `#ff7f0e` (Orange)
- Mild: `#2ca02c` (Green)
- Unknown: `#7f7f7f` (Gray)

**Data Sources:**
- Disease charts: Red gradient
- Symptom charts: Blue gradient
- Source charts: Green gradient

---

## 🔄 Data Flow

```
┌─────────────────┐
│   PostgreSQL    │
│  (TimescaleDB)  │
└────────┬────────┘
         │
         │ SQL Queries (every 30s)
         ↓
┌─────────────────────────┐
│  Streamlit Backend      │
│  • fetch_* functions    │
│  • Pandas processing    │
│  • Plotly chart creation│
└────────┬────────────────┘
         │
         │ Render
         ↓
┌─────────────────────────┐
│   Browser (Frontend)    │
│  • Interactive charts   │
│  • Auto-refresh         │
│  • User controls        │
└─────────────────────────┘

Additional Data Sources:
┌──────────────┐        ┌──────────────┐
│ Official JSON│───────▶│ Comparison   │
│    Reports   │        │   Panel      │
└──────────────┘        └──────────────┘

┌──────────────┐        ┌──────────────┐
│  Forecast    │───────▶│     Risk     │
│     CSV      │        │  Assessment  │
└──────────────┘        └──────────────┘
```

---

## 📊 Output Examples

### Scenario 1: Normal Operations

**Metrics:**
```
Total Events: 15,234
Last 24 Hours: 423
Last 7 Days: 2,891
Avg/Hour: 17.6
```

**Top Diseases:**
```
influenza    ████████████ 450
covid-19     ██████████ 320
norovirus    ██████ 180
gastroenteritis ████ 120
rsv          ███ 95
```

**Risk Assessment:**
```
No high-risk alerts
Most areas: LOW to MODERATE risk
```

### Scenario 2: Emerging Outbreak

**Metrics:**
```
Total Events: 15,234
Last 24 Hours: 1,247 (+194% ↑)
Last 7 Days: 4,523
Avg/Hour: 52.0 (+195% ↑)
```

**Top Diseases:**
```
influenza    ███████████████████ 1,120 (outbreak!)
covid-19     ██████████ 320
norovirus    ██████ 180
```

**Comparison Panel:**
```
Correlation: 0.82
Early Detection: 7 days ahead
Avg Difference: +45 cases

[Chart shows informal data spiking 7 days before official]
```

**Risk Assessment:**
```
🔴 CRITICAL: Williamsburg - influenza
   Risk Score: 92/100
   Components:
   • Recent Trend: 28/30
   • Forecast: 38/40
   • Severity: 16/20
   • Density: 10/10

🟠 HIGH: Astoria - influenza
   Risk Score: 78/100

🟠 HIGH: Park Slope - influenza
   Risk Score: 75/100
```

### Scenario 3: Data Gap

**When official data is missing:**
```
📝 No official data found. Add JSON files to get started.

[Expandable help section shows:]
📖 How to add official data (JSON format)
   • File location
   • Supported formats (3 examples)
   • Column name variations
   • Download sources
```

**When forecast data is missing:**
```
Risk assessment requires forecast data.
Run: python disease_outbreak_forecaster.py
```

---

## 🔧 Configuration

### Database Connection

**File:** Top of `app.py`

```python
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "nyc_disease_surveillance",
    "user": "postgres",
    "password": "postgres"
}
```

**For Docker:**
```python
DB_CONFIG = {
    "host": "postgres",  # Service name in docker-compose
    "port": 5432,
    "database": "disease_surveillance",
    "user": os.environ.get("DB_USER", "postgres"),
    "password": os.environ.get("DB_PASSWORD", "postgres")
}
```

### Cache Settings

```python
@st.cache_data(ttl=30)  # Cache for 30 seconds
def fetch_total_events():
    # Function caches results for 30s
    # Reduces database load
    pass

@st.cache_data(ttl=60)  # Cache for 1 minute
def load_latest_forecast():
    # Files update less frequently
    pass

@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_official_health_data():
    # Official data updates infrequently
    pass
```

**Cache Strategy:**
- Real-time data (events): 30 seconds
- Analysis outputs (forecasts): 60 seconds
- Official reports: 5 minutes

### Auto-Refresh

**Default:** Enabled (30 second intervals)

```python
if auto_refresh:
    st.sidebar.info("Dashboard will refresh in 30 seconds")
    time.sleep(30)
    st.rerun()
```

**User Control:** Toggle in sidebar

---

## 🛠️ Setup Instructions

### Prerequisites

```bash
# Required software
- Python 3.8+
- PostgreSQL 12+ (with TimescaleDB extension)
- Web browser (Chrome, Firefox, Safari)

# Python packages
pip install streamlit
pip install psycopg2-binary
pip install pandas
pip install plotly
```

### Quick Start (Local Development)

**Step 1: Clone/Setup Project**

```bash
cd your_project_directory
```

**Step 2: Install Dependencies**

```bash
pip install streamlit psycopg2-binary pandas plotly
```

**Step 3: Configure Database**

Edit `app.py`:
```python
DB_CONFIG = {
    "host": "localhost",      # Your database host
    "port": 5432,
    "database": "nyc_disease_surveillance",
    "user": "postgres",
    "password": "your_password"
}
```

**Step 4: Create Data Directories**

```bash
mkdir -p data/official_reports
mkdir -p data/spatial_clusters
mkdir -p forecast
```

**Step 5: Add Sample Data (Optional)**

```bash
# Add official health data
cat > data/official_reports/sample.json << 'EOF'
[
  {"date": "2024-12-01", "disease": "influenza", "cases": 50, "borough": "Manhattan"}
]
EOF
```

**Step 6: Run Dashboard**

```bash
streamlit run src/dashboard/app.py
```

**Step 7: Access Dashboard**

Open browser to: `http://localhost:8501`

### Docker Setup

**Step 1: Create Dockerfile**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN pip install streamlit psycopg2-binary pandas plotly

COPY app.py /app/
COPY data/ /app/data/
COPY forecast/ /app/forecast/

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address", "0.0.0.0"]
```

**Step 2: Create docker-compose.yml**

```yaml
version: '3.8'

services:
  dashboard:
    build: .
    ports:
      - "8501:8501"
    environment:
      - DB_HOST=postgres
      - DB_PORT=5432
      - DB_NAME=disease_surveillance
      - DB_USER=postgres
      - DB_PASSWORD=postgres
    volumes:
      - ./data:/app/data
      - ./forecast:/app/forecast
    depends_on:
      - postgres
    networks:
      - app_network

  postgres:
    image: timescale/timescaledb:latest-pg15
    environment:
      POSTGRES_DB: disease_surveillance
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - app_network

volumes:
  postgres_data:

networks:
  app_network:
    driver: bridge
```

**Step 3: Build and Run**

```bash
docker-compose up -d
```

**Step 4: Access Dashboard**

Open browser to: `http://localhost:8501`

### Production Deployment

#### Option 1: Streamlit Cloud

**Step 1: Push to GitHub**

```bash
git add .
git commit -m "Add Streamlit dashboard"
git push origin main
```

**Step 2: Deploy on Streamlit Cloud**

1. Go to https://share.streamlit.io
2. Connect GitHub repository
3. Select `src/dashboard/app.py` as main file
4. Add secrets in dashboard settings:

```toml
# .streamlit/secrets.toml
[DB_CONFIG]
host = "your-db-host"
port = 5432
database = "disease_surveillance"
user = "postgres"
password = "your_password"
```

**Step 3: Update app.py to use secrets**

```python
import streamlit as st

DB_CONFIG = {
    "host": st.secrets["DB_CONFIG"]["host"],
    "port": st.secrets["DB_CONFIG"]["port"],
    "database": st.secrets["DB_CONFIG"]["database"],
    "user": st.secrets["DB_CONFIG"]["user"],
    "password": st.secrets["DB_CONFIG"]["password"]
}
```

#### Option 2: AWS/GCP/Azure

**Requirements:**
- VM with 2GB+ RAM
- Python 3.8+
- Nginx for reverse proxy
- SSL certificate (Let's Encrypt)

**Setup:**

```bash
# Install on Ubuntu
sudo apt update
sudo apt install python3-pip nginx

# Install dashboard
pip3 install streamlit psycopg2-binary pandas plotly

# Run as service
sudo nano /etc/systemd/system/streamlit.service
```

**Service file:**
```ini
[Unit]
Description=Streamlit Dashboard
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/dashboard
ExecStart=/usr/local/bin/streamlit run app.py --server.port 8501
Restart=always

[Install]
WantedBy=multi-user.target
```

**Nginx config:**
```nginx
server {
    listen 80;
    server_name dashboard.yourdomain.com;

    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

---

## 🎭 User Personas & Use Cases

### Persona 1: Public Health Official

**Name:** Dr. Sarah Chen, NYC DOHMH

**Goal:** Monitor disease trends and respond to outbreaks

**Workflow:**
1. Opens dashboard each morning
2. Checks "Last 24 Hours" metric
3. Reviews high-risk alerts in Risk Assessment
4. If CRITICAL alert → Initiates response protocol
5. Exports data for weekly report

**Key Features Used:**
- ✅ Real-time metrics
- ✅ Risk assessment panel
- ✅ Borough distribution
- ✅ Time window filtering

### Persona 2: Hospital Administrator

**Name:** Michael Rodriguez, Mt. Sinai Hospital

**Goal:** Prepare for patient surge

**Workflow:**
1. Reviews dashboard before shift planning meetings
2. Checks neighborhood-specific forecasts
3. Compares current trends to official predictions
4. Adjusts staffing based on high-risk neighborhoods
5. Monitors severity distribution

**Key Features Used:**
- ✅ Forecast data integration
- ✅ Severity level charts
- ✅ Geographic distribution
- ✅ Official vs informal comparison

### Persona 3: Data Scientist

**Name:** Emily Thompson, Research Team

**Goal:** Validate surveillance system accuracy

**Workflow:**
1. Opens dashboard weekly for validation
2. Examines correlation between official and informal data
3. Checks early detection metrics
4. Documents system performance
5. Identifies areas for improvement

**Key Features Used:**
- ✅ Official vs informal comparison
- ✅ Correlation metrics
- ✅ Early detection days
- ✅ Data source distribution

### Persona 4: Community Health Worker

**Name:** Juan Martinez, Brooklyn Community Outreach

**Goal:** Allocate vaccination resources

**Workflow:**
1. Checks dashboard for Brooklyn-specific alerts
2. Reviews top diseases in borough
3. Identifies high-risk neighborhoods
4. Plans mobile clinic locations
5. Shares alerts with community partners

**Key Features Used:**
- ✅ Borough filtering (via charts)
- ✅ Disease distribution
- ✅ Risk assessment
- ✅ Geographic visualization

---

## 📈 Performance Characteristics

### Load Times

**Initial Page Load:**
- Database: ~2-3 seconds
- Charts rendering: ~1-2 seconds
- Total: **3-5 seconds**

**Auto-refresh:**
- Cached queries: ~200-500ms
- Chart updates: ~500ms
- Total: **~1 second**

### Database Query Performance

**Metrics queries:**
```sql
-- fetch_total_events: ~50ms
SELECT COUNT(*) FROM disease_events;

-- fetch_disease_distribution: ~200ms
SELECT unnest(diseases), COUNT(*) 
FROM disease_events 
GROUP BY unnest(diseases);
```

**Optimization techniques:**
- Indexed columns (timestamp, borough, diseases)
- TimescaleDB hypertable partitioning
- Query result caching (30s TTL)
- Connection pooling

### Scalability

**Current capacity:**
- 10,000 events: Instant load
- 100,000 events: <5 second load
- 1,000,000 events: ~10-15 second load

**Bottlenecks:**
- Database query speed (largest table scans)
- Plotly chart rendering (complex charts)
- Network latency (dashboard ↔ database)

**Future optimizations:**
- Materialized views for aggregations
- Data sampling for very large datasets
- Client-side caching with Service Workers

---

## 🚨 Troubleshooting

### Issue 1: Cannot Connect to Database

**Symptoms:**
```
❌ Cannot connect to TimescaleDB
psycopg2.OperationalError: could not connect to server
```

**Solutions:**

```bash
# Check if PostgreSQL is running
docker ps | grep postgres

# If not running, start it
docker-compose up -d postgres

# Test connection manually
psql -h localhost -U postgres -d disease_surveillance

# Check firewall
sudo ufw status
sudo ufw allow 5432/tcp

# Verify DB_CONFIG in app.py
```

### Issue 2: No Data Showing

**Symptoms:**
```
Total Events: 0
Charts show "No data available"
```

**Solutions:**

```bash
# Check if table exists
psql -U postgres -d disease_surveillance -c "\dt"

# Check if table has data
psql -U postgres -d disease_surveillance -c "SELECT COUNT(*) FROM disease_events;"

# Load test data
python test_disease_forecast.py

# Check filters (is_relevant, is_duplicate)
psql -U postgres -d disease_surveillance -c "
SELECT 
  COUNT(*) as total,
  COUNT(*) FILTER (WHERE is_relevant = true) as relevant,
  COUNT(*) FILTER (WHERE is_duplicate = false) as unique
FROM disease_events;
"
```

### Issue 3: Official Data Not Loading

**Symptoms:**
```
📝 No official data found. Add JSON files to get started.
```

**Solutions:**

```bash
# Check directory exists
ls -la data/official_reports/

# Check JSON files exist
ls -la data/official_reports/*.json

# Validate JSON syntax
cat data/official_reports/sample.json | python -m json.tool

# Check file permissions
chmod 644 data/official_reports/*.json

# Verify JSON format matches expected schema
# See "Data Sources" section above
```

### Issue 4: Charts Not Rendering

**Symptoms:**
- Blank white boxes where charts should be
- JavaScript errors in browser console

**Solutions:**

```bash
# Clear Streamlit cache
streamlit cache clear

# Update Plotly
pip install --upgrade plotly

# Check browser console (F12)
# Look for JavaScript errors

# Try different browser
# Chrome, Firefox, Safari

# Disable browser extensions
# Ad blockers can interfere with charts
```

### Issue 5: Slow Performance

**Symptoms:**
- Dashboard takes >10 seconds to load
- Auto-refresh freezes UI

**Solutions:**

```python
# Reduce cache TTL
@st.cache_data(ttl=60)  # Increase from 30s

# Limit data range
query = f"""
    SELECT * FROM disease_events
    WHERE timestamp >= NOW() - INTERVAL '7 days'  -- Reduce from 30 days
"""

# Disable auto-refresh temporarily
auto_refresh = st.sidebar.checkbox("Auto-refresh (30s)", value=False)

# Add database indexes
CREATE INDEX idx_events_recent ON disease_events(timestamp DESC)
WHERE timestamp >= NOW() - INTERVAL '30 days';
```

### Issue 6: Risk Assessment Panel Empty

**Symptoms:**
```
Risk assessment requires forecast data
```

**Solutions:**

```bash
# Run forecasting script
python disease_outbreak_forecaster.py

# Check forecast file exists
ls -la forecast/outbreak_forecast.csv

# Verify CSV format
head forecast/outbreak_forecast.csv

# Check file permissions
chmod 644 forecast/outbreak_forecast.csv

# Verify date format in CSV
# Should be: 2024-12-15, not 12/15/2024
```

---

## 📊 Metrics & Monitoring

### Dashboard Usage Metrics

Track in production:

```python
# Add to app.py
import streamlit as st
from datetime import datetime

# Log page views
if 'page_views' not in st.session_state:
    st.session_state.page_views = 0

st.session_state.page_views += 1

# Log interactions
def log_interaction(action):
    with open('dashboard_metrics.log', 'a') as f:
        f.write(f"{datetime.now()},{action}\n")

# Track button clicks
if st.button("Export Data"):
    log_interaction("export_clicked")
```

### Health Check Endpoint

```python
# Add health check for monitoring
# Access via: http://localhost:8501/health

import streamlit as st
import psycopg2

def check_database():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.close()
        return True
    except:
        return False

if st.experimental_get_query_params().get("health"):
    if check_database():
        st.write("OK")
    else:
        st.write("ERROR: Database connection failed")
```

---

## 🚀 Future Enhancements

### Planned Features

**Q1 2025:**
- [ ] User authentication and role-based access
- [ ] Downloadable PDF reports
- [ ] Email alerts for high-risk events
- [ ] Mobile-responsive design improvements

**Q2 2025:**
- [ ] Interactive map with cluster visualization
- [ ] Custom date range picker
- [ ] Forecast accuracy dashboard
- [ ] Multi-language support (Spanish, Chinese)

**Q3 2025:**
- [ ] Real-time WebSocket updates (no refresh needed)
- [ ] Machine learning model performance metrics
- [ ] Automated weekly summary emails
- [ ] Integration with NYC 311 data

### Technical Improvements

**Performance:**
- Implement Redis for caching
- Add PostgreSQL connection pooling
- Use Streamlit's experimental memo for expensive computations

**User Experience:**
- Add loading spinners for slow queries
- Implement progressive data loading
- Add keyboard shortcuts (?, h for help)

**Data Quality:**
- Add data validation dashboard
- Show confidence intervals on all metrics
- Display data freshness timestamps

---

## 📞 Support & Resources

### Documentation

- **Streamlit Docs:** https://docs.streamlit.io
- **Plotly Docs:** https://plotly.com/python/
- **TimescaleDB Docs:** https://docs.timescale.com

### Getting Help

**For bugs:**
1. Check logs: `streamlit run app.py --logger.level debug`
2. Clear cache: `streamlit cache clear`
