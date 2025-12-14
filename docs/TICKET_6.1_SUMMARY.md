# NYC Disease Surveillance Dashboard

Real-time dashboard for monitoring disease events across New York City.

## Features

### Real-Time Metrics
- **Total Events**: Overall count of disease events in database
- **Last 24 Hours**: Recent activity
- **Last 7 Days**: Weekly trend
- **Average per Hour**: Rate of incoming events

### Visualizations
1. **Top Diseases**: Bar chart of most reported diseases (COVID-19, Influenza, etc.)
2. **Events by Borough**: Geographic distribution across NYC boroughs
3. **Event Timeline**: Time-series graph showing disease trends
4. **Top Symptoms**: Most commonly reported symptoms
5. **Severity Levels**: Distribution of mild/moderate/severe cases
6. **Data Sources**: Breakdown by source (Reddit, Bluesky, 311, etc.)

## Running the Dashboard

### Prerequisites
```bash
# Install dependencies
pip install streamlit plotly psycopg2-binary

# Ensure TimescaleDB is running
docker compose up -d timescaledb
```

### Start Dashboard
```bash
streamlit run src/dashboard/app.py
```

Dashboard will open at `http://localhost:8501`

### Configuration
- **Auto-refresh**: Enable 30-second auto-refresh in sidebar
- **Time Window**: Select data range (1 day, 2 days, 7 days, 30 days)
- **Database Connection**: Configured for localhost TimescaleDB (port 5432)

## Dashboard Components

### Data Caching
- All queries cached for 30 seconds using `@st.cache_data(ttl=30)`
- Reduces database load while maintaining near-real-time updates

### Database Queries
The dashboard queries TimescaleDB for:
- Total event counts
- Time-bucketed aggregations (hourly)
- Disease/symptom/borough distributions
- Severity level breakdowns
- Source statistics

### Auto-Refresh
When enabled, dashboard automatically refreshes every 30 seconds to show latest data.

## Architecture

```
Dashboard (Streamlit)
    ↓
TimescaleDB (PostgreSQL)
    ↑
Pipeline (Spark Consumers)
    ↑
Kafka Topics
    ↑
Scrapers (Reddit, Bluesky, 311, etc.)
```

## Future Enhancements (Optional)

- **Interactive Map**: Plotly/Folium map showing spatial clusters
- **Semantic Search**: ChromaDB integration for text search
- **Alert System**: Notifications for outbreak detection
- **Comparative Analysis**: Compare boroughs/diseases side-by-side
- **Export Data**: Download filtered datasets as CSV/JSON
- **User Authentication**: Secure access control
- **Mobile Responsive**: Optimized mobile layout

## Troubleshooting

### Cannot Connect to Database
```
Error: Cannot connect to TimescaleDB
Solution: docker compose up -d timescaledb
```

### No Data Showing
```
Issue: Empty charts
Solution: Run pipeline to populate database
  python src/run_chained_pipeline.py
```

### Port Already in Use
```
Error: Port 8501 is already in use
Solution: streamlit run src/dashboard/app.py --server.port 8502
```

## Technology Stack

- **Streamlit**: Web framework for data apps
- **Plotly**: Interactive visualizations
- **psycopg2**: PostgreSQL database adapter
- **Pandas**: Data manipulation
- **TimescaleDB**: Time-series database backend
