# Spatial Clustering Analysis (Ticket 5.3)

## Overview

The **Spatial Clustering Analyzer** uses Spark and machine learning algorithms to identify geographic hotspots and spatial patterns in disease surveillance data. It combines structured data from TimescaleDB with semantic embeddings from ChromaDB to find clusters of disease outbreaks across NYC boroughs and neighborhoods.

## Key Features

✅ **DBSCAN clustering** - Density-based spatial clustering for identifying outbreak hotspots  
✅ **K-Means clustering** - Partition-based clustering for fixed-number regional analysis  
✅ **Multi-database integration** - Combines TimescaleDB (structured) + ChromaDB (semantic)  
✅ **Semantic coherence scoring** - Measures how semantically similar documents are within clusters  
✅ **Borough & neighborhood analysis** - Maps clusters to NYC geographic regions  
✅ **Disease & symptom distribution** - Analyzes what diseases/symptoms appear in each cluster  
✅ **Temporal analysis** - Tracks time range of cluster activity  
✅ **Spark-powered** - Scalable data loading via JDBC from PostgreSQL  

---

## How the Code Works

### 1. **Architecture**

```
┌─────────────┐         ┌──────────────┐
│ TimescaleDB │         │   ChromaDB   │
│  (Postgres) │         │   (Vectors)  │
└──────┬──────┘         └───────┬──────┘
       │                        │
       │ JDBC                   │ Python API
       │                        │
       ▼                        ▼
   ┌────────────────────────────────┐
   │   SpatialClusteringAnalyzer    │
   │  ┌──────────────────────────┐  │
   │  │   Spark DataFrame        │  │
   │  │   (disease events)       │  │
   │  └────────┬─────────────────┘  │
   │           │                     │
   │           ▼                     │
   │  ┌──────────────────────────┐  │
   │  │  Prepare Spatial Features│  │
   │  │  (lat/lon from borough)  │  │
   │  └────────┬─────────────────┘  │
   │           │                     │
   │           ▼                     │
   │  ┌──────────────────────────┐  │
   │  │  DBSCAN or K-Means       │  │
   │  │  (scikit-learn)          │  │
   │  └────────┬─────────────────┘  │
   │           │                     │
   │           ▼                     │
   │  ┌──────────────────────────┐  │
   │  │  Analyze Clusters        │  │
   │  │  (diseases, symptoms,    │  │
   │  │   boroughs, time range)  │  │
   │  └────────┬─────────────────┘  │
   │           │                     │
   │           ▼                     │
   │  ┌──────────────────────────┐  │
   │  │  Semantic Enrichment     │  │
   │  │  (cosine similarity)     │  │
   │  └────────┬─────────────────┘  │
   │           │                     │
   │           ▼                     │
   │  ┌──────────────────────────┐  │
   │  │  Save Results            │  │
   │  │  (JSON + TXT reports)    │  │
   │  └──────────────────────────┘  │
   └────────────────────────────────┘
```

### 2. **Key Classes and Methods**

#### **SpatialClusteringAnalyzer Class**

**`__init__()`** - Initialize connections:
- Spark Session with JDBC PostgreSQL driver
- TimescaleDB connection configuration
- ChromaDB PersistentClient
- Borough coordinate mapping

**`load_data_from_timescaledb()`** - Load via Spark JDBC:
```python
# SQL query with filters
query = """
    SELECT id, timestamp, borough, neighborhood, diseases, symptoms, severity
    FROM disease_events
    WHERE timestamp >= '2025-09-15'  # time_window_days filter
      AND borough IN ('Brooklyn', 'Manhattan')  # borough_filter
      AND borough IS NOT NULL  # Only records with location
"""

# Load via JDBC into Spark DataFrame
df = spark.read.format("jdbc") \
    .option("url", "jdbc:postgresql://localhost:5432/nyc_disease_surveillance") \
    .option("query", query) \
    .option("user", "postgres") \
    .load()
```

**`prepare_spatial_features()`** - Convert to coordinates:
```python
# Map borough names to approximate coordinates
borough_coords = {
    "Manhattan": (40.7831, -73.9712),
    "Brooklyn": (40.6782, -73.9442),
    "Queens": (40.7282, -73.7949),
    "Bronx": (40.8448, -73.8648),
    "Staten Island": (40.5795, -74.1502)
}

# Add jitter for neighborhood variation (prevents identical coordinates)
lat = borough_lat + random.uniform(-0.02, 0.02)  # ~2km variation
lon = borough_lon + random.uniform(-0.02, 0.02)
```

**Why jitter?**  
Without it, all Brooklyn records have identical coordinates (40.6782, -73.9442), making clustering impossible. Jitter adds realistic neighborhood-level variation (~2km radius).

**`dbscan_clustering()`** - Density-based clustering:
```python
from sklearn.cluster import DBSCAN

# Convert km to degrees (1 degree ≈ 111 km)
eps_degrees = eps_km / 111.0  # e.g., 2km → 0.018 degrees

# Run DBSCAN
dbscan = DBSCAN(eps=eps_degrees, min_samples=5)
cluster_labels = dbscan.fit_predict(coords)

# Labels: 0, 1, 2, ... = cluster IDs, -1 = noise
```

**How DBSCAN works**:
1. For each point, find all neighbors within `eps` distance
2. If ≥ `min_samples` neighbors, mark as core point and create cluster
3. Expand cluster by adding neighbors of neighbors
4. Points with < `min_samples` neighbors = noise (-1)

**Advantages**:
- Finds arbitrary-shaped clusters (not just circular)
- Automatically determines number of clusters
- Identifies outliers (noise points)

**`kmeans_clustering()`** - Partition-based clustering:
```python
from sklearn.cluster import KMeans

# Standardize coordinates (important for K-Means)
scaler = StandardScaler()
coords_scaled = scaler.fit_transform(coords)

# Run K-Means
kmeans = KMeans(n_clusters=5, random_state=42)
cluster_labels = kmeans.fit_predict(coords_scaled)

# Get cluster centers
centers = scaler.inverse_transform(kmeans.cluster_centers_)
```

**How K-Means works**:
1. Randomly initialize K cluster centers
2. Assign each point to nearest center
3. Recompute centers as mean of assigned points
4. Repeat until convergence

**Advantages**:
- Fast and deterministic
- Fixed number of clusters (good for regional analysis)
- Finds cluster centroids

**`analyze_clusters()`** - Extract cluster characteristics:
```python
for cluster_id in unique_clusters:
    cluster_data = df[df['cluster_id'] == cluster_id]
    
    analysis = {
        'size': len(cluster_data),
        'centroid': (mean_lat, mean_lon),
        'boroughs': borough_counts,  # {'Brooklyn': 45, 'Manhattan': 23}
        'neighborhoods': neighborhood_counts,
        'diseases': disease_counts,  # {'COVID-19': 30, 'Influenza': 15}
        'symptoms': symptom_counts,  # {'fever': 40, 'cough': 35}
        'severity': severity_counts,  # {'high': 10, 'medium': 25}
        'time_range': (min_timestamp, max_timestamp),
        'avg_confidence': mean(confidence_scores)
    }
```

**`enrich_with_semantic_similarity()`** - ChromaDB integration:
```python
# Get embeddings for cluster members
cluster_ids = ['id1', 'id2', 'id3', ...]
results = chroma_collection.get(ids=cluster_ids, include=['embeddings'])

# Calculate pairwise cosine similarities
embeddings = np.array(results['embeddings'])
similarities = 1 - cdist(embeddings, embeddings, metric='cosine')

# Average similarity (exclude diagonal)
avg_similarity = similarities[mask].mean()

# Semantic coherence: high (>0.7), medium (0.5-0.7), low (<0.5)
```

**Why semantic similarity?**  
Spatial proximity doesn't guarantee topical similarity. A spatially tight cluster might contain unrelated diseases. Semantic similarity confirms if cluster members discuss similar health topics.

**`save_results()`** - Output three files:
1. **Cluster assignments** (JSON): Record-level data with cluster labels
2. **Cluster analysis** (JSON): Aggregate statistics per cluster
3. **Cluster summary** (TXT): Human-readable report

---

## How to Run

### **Prerequisites**

```bash
# Install dependencies
pip install pyspark psycopg2-binary scikit-learn numpy pandas scipy chromadb

# Ensure TimescaleDB is running
docker compose up timescaledb

# Ensure data is loaded
python src/database/psql_db_client.py --embeddings-dir src/data/locations
python src/database/chromadb_client.py --embeddings-dir src/data/embeddings
```

### **Basic Usage**

#### **DBSCAN Clustering** (recommended for outbreak detection):
```bash
python src/spatial_clustering.py \
    --algorithm dbscan \
    --eps-km 2.0 \
    --min-samples 5 \
    --time-window 90
```

#### **K-Means Clustering** (regional analysis):
```bash
python src/spatial_clustering.py \
    --algorithm kmeans \
    --k 5 \
    --time-window 90
```

### **Advanced Filtering**

#### **Filter by disease**:
```bash
python src/spatial_clustering.py \
    --algorithm dbscan \
    --disease COVID-19 Influenza RSV \
    --time-window 30
```

#### **Filter by borough**:
```bash
python src/spatial_clustering.py \
    --algorithm dbscan \
    --borough Brooklyn Manhattan \
    --eps-km 1.5
```

#### **All historical data** (no time filter):
```bash
python src/spatial_clustering.py \
    --algorithm dbscan \
    --time-window 0  # 0 = all data
```

### **Full Parameter List**

```bash
python src/spatial_clustering.py \
    --algorithm dbscan                 # dbscan or kmeans
    --time-window 90                   # Days (0 = all data)
    --disease COVID-19 Influenza       # Filter diseases
    --borough Brooklyn Queens          # Filter boroughs
    --eps-km 2.0                       # DBSCAN: cluster radius (km)
    --min-samples 5                    # DBSCAN: min cluster size
    --k 5                              # K-Means: number of clusters
    --postgres-host localhost          # Database host
    --postgres-port 5432               # Database port
    --chromadb-path data/chromadb      # ChromaDB location
    --output-dir data/spatial_clusters # Output directory
```

### **Programmatic Usage**

```python
from src.spatial_clustering import SpatialClusteringAnalyzer

# Initialize
analyzer = SpatialClusteringAnalyzer(
    postgres_host='localhost',
    chromadb_path='data/chromadb',
    output_dir='data/spatial_clusters'
)

# Run DBSCAN analysis
analyzer.run_analysis(
    algorithm='dbscan',
    time_window_days=90,
    disease_filter=['COVID-19', 'Influenza'],
    borough_filter=['Brooklyn', 'Manhattan'],
    eps_km=2.0,
    min_samples=5
)

# Run K-Means analysis
analyzer.run_analysis(
    algorithm='kmeans',
    time_window_days=30,
    n_clusters=5
)

# Cleanup
analyzer.stop()
```

---

## Expected Output

### **Console Output**

```
2025-12-14 10:30:00 - __main__ - INFO - ======================================================================
2025-12-14 10:30:00 - __main__ - INFO - Starting Spatial Clustering Analysis
2025-12-14 10:30:00 - __main__ - INFO - Algorithm: DBSCAN
2025-12-14 10:30:00 - __main__ - INFO - ======================================================================
2025-12-14 10:30:01 - __main__ - INFO - Initializing Spark Session...
2025-12-14 10:30:05 - __main__ - INFO - Connecting to ChromaDB at: data/chromadb
2025-12-14 10:30:05 - __main__ - INFO - ChromaDB collection 'nyc_disease_surveillance' loaded: 12681 documents
2025-12-14 10:30:05 - __main__ - INFO - Spatial Clustering Analyzer initialized successfully
2025-12-14 10:30:05 - __main__ - INFO - Loading data from TimescaleDB...
2025-12-14 10:30:07 - __main__ - INFO - Loaded 270 records from TimescaleDB
2025-12-14 10:30:07 - __main__ - INFO - Preparing spatial features...
2025-12-14 10:30:07 - __main__ - INFO - Prepared 270 records with spatial features
2025-12-14 10:30:07 - __main__ - INFO - Running DBSCAN clustering (eps=2.0km, min_samples=5)...
2025-12-14 10:30:07 - __main__ - INFO - DBSCAN found 8 clusters, 12 noise points
2025-12-14 10:30:07 - __main__ - INFO - Analyzing clusters (cluster_id)...
2025-12-14 10:30:08 - __main__ - INFO - Analyzed 8 clusters
2025-12-14 10:30:08 - __main__ - INFO - Enriching clusters with semantic similarity...
2025-12-14 10:30:12 - __main__ - INFO - Computed semantic similarity for 8 clusters
2025-12-14 10:30:12 - __main__ - INFO - Saved cluster assignments to data/spatial_clusters/cluster_assignments_dbscan_20251214_103012.json
2025-12-14 10:30:12 - __main__ - INFO - Saved cluster analysis to data/spatial_clusters/cluster_analysis_dbscan_20251214_103012.json
2025-12-14 10:30:12 - __main__ - INFO - Saved cluster summary to data/spatial_clusters/cluster_summary_dbscan_20251214_103012.txt
2025-12-14 10:30:12 - __main__ - INFO - 
======================================================================
2025-12-14 10:30:12 - __main__ - INFO - CLUSTERING SUMMARY
2025-12-14 10:30:12 - __main__ - INFO - ======================================================================
2025-12-14 10:30:12 - __main__ - INFO - Algorithm: DBSCAN
2025-12-14 10:30:12 - __main__ - INFO - Total records: 270
2025-12-14 10:30:12 - __main__ - INFO - Number of clusters: 8
2025-12-14 10:30:12 - __main__ - INFO - Results saved to: data/spatial_clusters/
2025-12-14 10:30:12 - __main__ - INFO - ======================================================================
```

### **Output Files**

```
data/spatial_clusters/
├── cluster_assignments_dbscan_20251214_103012.json
├── cluster_analysis_dbscan_20251214_103012.json
└── cluster_summary_dbscan_20251214_103012.txt
```

### **1. Cluster Assignments JSON**

Record-level data with cluster labels:

```json
[
  {
    "id": "a1b2c3d4-...",
    "timestamp": "2025-11-15T10:30:00",
    "borough": "Brooklyn",
    "neighborhood": "Williamsburg",
    "lat": 40.6795,
    "lon": -73.9520,
    "diseases": ["COVID-19", "Influenza"],
    "symptoms": ["fever", "cough", "fatigue"],
    "severity": "medium",
    "cluster_id": 0
  },
  {
    "id": "e5f6g7h8-...",
    "timestamp": "2025-11-16T14:20:00",
    "borough": "Brooklyn",
    "neighborhood": "Park Slope",
    "lat": 40.6730,
    "lon": -73.9765,
    "diseases": ["COVID-19"],
    "symptoms": ["fever", "shortness of breath"],
    "severity": "high",
    "cluster_id": 0
  },
  ...
]
```

### **2. Cluster Analysis JSON**

Aggregate statistics per cluster:

```json
{
  "metadata": {
    "algorithm": "dbscan",
    "timestamp": "20251214_103012",
    "total_records": 270,
    "num_clusters": 8
  },
  "clusters": {
    "0": {
      "size": 45,
      "centroid": {"lat": 40.6782, "lon": -73.9442},
      "boroughs": {"Brooklyn": 45},
      "neighborhoods": {
        "Williamsburg": 12,
        "Park Slope": 10,
        "Bushwick": 8,
        "Bedford-Stuyvesant": 7,
        "Crown Heights": 8
      },
      "diseases": {
        "COVID-19": 30,
        "Influenza": 12,
        "RSV": 8
      },
      "symptoms": {
        "fever": 40,
        "cough": 35,
        "fatigue": 25,
        "shortness of breath": 15
      },
      "severity": {
        "high": 10,
        "medium": 25,
        "low": 10
      },
      "time_range": {
        "start": "2025-11-01T08:00:00",
        "end": "2025-12-10T18:30:00"
      },
      "avg_confidence": 0.78
    },
    "1": {
      "size": 38,
      "centroid": {"lat": 40.7831, "lon": -73.9712},
      "boroughs": {"Manhattan": 38},
      ...
    }
  },
  "semantic_scores": {
    "0": {
      "avg_cosine_similarity": 0.72,
      "semantic_coherence": "high",
      "sample_size": 45
    },
    "1": {
      "avg_cosine_similarity": 0.68,
      "semantic_coherence": "medium",
      "sample_size": 38
    }
  }
}
```

### **3. Cluster Summary TXT**

Human-readable report:

```
======================================================================
Spatial Clustering Analysis Summary - DBSCAN
Generated: 20251214_103012
======================================================================

Total Records: 270
Number of Clusters: 8

======================================================================
CLUSTER 0
======================================================================
Size: 45 records
Centroid: lat=40.6782, lon=-73.9442

Boroughs:
  - Brooklyn: 45

Top Neighborhoods:
  - Williamsburg: 12
  - Park Slope: 10
  - Bushwick: 8
  - Bedford-Stuyvesant: 7
  - Crown Heights: 8

Top Diseases:
  - COVID-19: 30
  - Influenza: 12
  - RSV: 8

Top Symptoms:
  - fever: 40
  - cough: 35
  - fatigue: 25
  - shortness of breath: 15
  - headache: 12

Severity Distribution:
  - high: 10
  - medium: 25
  - low: 10

Semantic Coherence: high (similarity: 0.720)

Time Range: 2025-11-01 08:00:00 to 2025-12-10 18:30:00

======================================================================
CLUSTER 1
======================================================================
...
```

---

## Technical Considerations

### **1. DBSCAN vs. K-Means Trade-offs**

| Feature | DBSCAN | K-Means |
|---------|--------|---------|
| **Cluster shape** | Arbitrary (follows density) | Circular/spherical |
| **Number of clusters** | Automatic | Must specify K |
| **Outlier detection** | ✅ Yes (noise points = -1) | ❌ No (all assigned) |
| **Deterministic** | ✅ Yes | ⚠️ Sensitive to init |
| **Scalability** | O(n log n) | O(nk) |
| **Parameters** | eps, min_samples | k |
| **Best for** | Irregular hotspots | Regional partitioning |

**When to use DBSCAN**:
- Detecting outbreak hotspots with unknown shape
- Identifying anomalous isolated cases
- Variable-density regions (dense Manhattan, sparse Staten Island)

**When to use K-Means**:
- Dividing city into K fixed regions
- Comparing across time periods (same K)
- Need cluster centroids for visualization

### **2. Coordinate Jitter Strategy**

**Problem**: Borough-only data means all Brooklyn records have identical (40.6782, -73.9442) coordinates.

**Solution**: Add random jitter within ~2km radius:
```python
lat = borough_lat + np.random.uniform(-0.02, 0.02)  # ±0.02° ≈ ±2.2km
lon = borough_lon + np.random.uniform(-0.02, 0.02)
```

**Why 2km?**  
NYC neighborhoods are typically 1-5km across. 2km jitter creates realistic within-borough variation without crossing borough boundaries.

**Seed**: `np.random.seed(42)` ensures reproducible jitter across runs.

### **3. Epsilon (eps) Parameter Tuning**

**DBSCAN's most critical parameter**: Maximum distance between cluster members.

**Guidelines**:
```python
eps_km = 2.0   # Good for neighborhood-level clusters (Williamsburg, Park Slope)
eps_km = 5.0   # Borough-level clusters (all of Brooklyn)
eps_km = 0.5   # Block-level clusters (specific street corners)
```

**Rule of thumb**: Set eps to average distance between nearby outbreak cases.

**Find optimal eps**:
```python
from sklearn.neighbors import NearestNeighbors

# Plot k-distance graph
k = min_samples
nbrs = NearestNeighbors(n_neighbors=k).fit(coords)
distances, indices = nbrs.kneighbors(coords)
distances = np.sort(distances[:, k-1], axis=0)

# Elbow point in plot → optimal eps
```

### **4. Minimum Samples Parameter**

**min_samples**: Minimum points to form a dense region (core point).

**Guidelines**:
```python
min_samples = 5   # Detect small clusters (5+ cases = outbreak)
min_samples = 10  # More significant outbreaks only
min_samples = 2   # Very sensitive (2 cases = cluster)
```

**Rule of thumb**: `min_samples ≈ 2 * dimensions` (here: 2D → min_samples ≈ 4-5)

**Trade-off**:
- **Low min_samples**: More clusters, more noise sensitivity
- **High min_samples**: Fewer clusters, miss small outbreaks

### **5. Semantic Similarity Computation**

**Cosine similarity** between embeddings:
```python
# For cluster with N documents
embeddings = [[e1], [e2], ..., [eN]]  # N × 384 matrices

# Compute N × N similarity matrix
similarities = 1 - cdist(embeddings, embeddings, metric='cosine')

# Average off-diagonal elements
avg_similarity = mean(similarities[i, j] for i != j)
```

**Interpretation**:
- **> 0.7**: High coherence - cluster discusses same topic
- **0.5-0.7**: Medium coherence - related but diverse topics
- **< 0.5**: Low coherence - spatially close but topically unrelated

**Why useful?**  
Identifies "false positive" clusters where cases are spatially clustered by chance but discuss unrelated diseases.

### **6. Spark JDBC Performance**

**Loading 270 records** from Postgres:
```python
df = spark.read.format("jdbc") \
    .option("url", "jdbc:postgresql://localhost:5432/nyc_disease_surveillance") \
    .option("query", sql_query) \
    .option("user", "postgres") \
    .load()
```

**Performance**: ~2-3 seconds for 270 records, ~10 seconds for 10k records

**Optimization for large datasets**:
```python
# Parallel partitioning by timestamp
.option("partitionColumn", "timestamp") \
.option("lowerBound", "2025-01-01") \
.option("upperBound", "2025-12-31") \
.option("numPartitions", "10")
```

### **7. Memory Requirements**

**For 270 records**:
- Spark DataFrame: ~1MB
- Pandas conversion: ~1MB
- Scikit-learn clustering: ~1MB
- ChromaDB embeddings: 270 × 384 floats × 4 bytes ≈ 0.4MB
- **Total**: ~5MB

**For 10,000 records**:
- Spark DataFrame: ~40MB
- Pandas conversion: ~40MB
- DBSCAN: ~800MB (distance matrix: 10k × 10k × 8 bytes)
- **Total**: ~1GB

**Recommendation**: Use 4GB Spark memory for up to 20k records.

### **8. Time Complexity**

| Operation | Complexity | Time (270 records) |
|-----------|------------|-------------------|
| Postgres JDBC load | O(n) | 2 seconds |
| Coordinate mapping | O(n) | < 0.1 seconds |
| DBSCAN | O(n log n) | 0.5 seconds |
| K-Means | O(nk iterations) | 0.3 seconds |
| Cluster analysis | O(n) | 0.2 seconds |
| Semantic similarity | O(n²) | 4 seconds |
| **Total** | **O(n²)** | **~7 seconds** |

**Bottleneck**: Semantic similarity (pairwise distance computation).

**Optimization**: Limit to 100 samples per cluster for large clusters.

### **9. Handling Missing Location Data**

**SQL filter**: `WHERE borough IS NOT NULL OR neighborhood IS NOT NULL`

**Effect**: Excludes ~95% of records without location data (only 270/12,681 have borough info).

**Future improvement**: Use geopy geocoding on text mentions:
```python
from geopy.geocoders import Nominatim

text = "outbreak near Times Square"
location = geolocator.geocode(f"{text}, New York City")
lat, lon = location.latitude, location.longitude
```

### **10. Temporal Clustering Extension**

**Current**: Spatial only (lat, lon)

**Future**: Spatio-temporal clustering (lat, lon, time):
```python
# Add time as third dimension (normalized to 0-1 scale)
time_normalized = (timestamp - min_time) / (max_time - min_time)

# Weighted distance
from sklearn.metrics import pairwise_distances

def spatiotemporal_distance(X):
    spatial = X[:, :2]  # lat, lon
    temporal = X[:, 2:]  # time
    
    spatial_dist = pairwise_distances(spatial) * 111  # degrees to km
    temporal_dist = pairwise_distances(temporal) * 30  # scale: 1 unit = 30 days
    
    return spatial_dist + 0.5 * temporal_dist  # Weight: space=1, time=0.5

dbscan = DBSCAN(eps=5.0, metric=spatiotemporal_distance)
```

---

## Use Cases

### **1. Outbreak Hotspot Detection**

**Scenario**: Health department needs to identify COVID-19 outbreak hotspots.

```bash
python src/spatial_clustering.py \
    --algorithm dbscan \
    --disease COVID-19 \
    --time-window 14 \
    --eps-km 1.5 \
    --min-samples 3
```

**Result**: Identifies neighborhoods with 3+ COVID cases within 1.5km in last 2 weeks.

### **2. Regional Health Planning**

**Scenario**: Divide NYC into 5 health districts for resource allocation.

```bash
python src/spatial_clustering.py \
    --algorithm kmeans \
    --k 5 \
    --time-window 90
```

**Result**: 5 clusters representing distinct health regions with their disease profiles.

### **3. Multi-Disease Analysis**

**Scenario**: Study respiratory disease patterns (COVID, flu, RSV).

```bash
python src/spatial_clustering.py \
    --algorithm dbscan \
    --disease COVID-19 Influenza RSV \
    --time-window 30 \
    --eps-km 2.0
```

**Result**: Clusters showing co-occurrence patterns of respiratory diseases.

### **4. Borough Comparison**

**Scenario**: Compare Brooklyn vs. Queens outbreak patterns.

```bash
# Brooklyn
python src/spatial_clustering.py --borough Brooklyn --time-window 60

# Queens
python src/spatial_clustering.py --borough Queens --time-window 60
```

**Result**: Separate analyses for comparing cluster characteristics.

---

## Troubleshooting

### **Issue**: "No data to cluster" error
**Cause**: No records match filters (time window, borough, disease).
**Solution**:
```bash
# Check data availability
docker exec -it timescaledb psql -U postgres -d nyc_disease_surveillance \
    -c "SELECT borough, COUNT(*) FROM disease_events WHERE borough IS NOT NULL GROUP BY borough;"

# Loosen filters
python src/spatial_clustering.py --time-window 0  # All data
```

### **Issue**: ChromaDB connection warning
**Cause**: ChromaDB not populated or path incorrect.
**Solution**:
```bash
# Load ChromaDB
python src/database/chromadb_client.py --embeddings-dir src/data/embeddings --clear

# Check path
ls data/chromadb/chroma.sqlite3
```

### **Issue**: "DBSCAN found 0 clusters"
**Cause**: `eps` too small or `min_samples` too large.
**Solution**:
```bash
# Increase eps
python src/spatial_clustering.py --eps-km 5.0

# Decrease min_samples
python src/spatial_clustering.py --min-samples 3
```

### **Issue**: All records in one K-Means cluster
**Cause**: K too small for data distribution.
**Solution**:
```bash
python src/spatial_clustering.py --algorithm kmeans --k 10  # Increase K
```

### **Issue**: PostgreSQL JDBC driver error
**Cause**: Driver not downloaded by Spark.
**Solution**:
```bash
# Download manually
wget https://jdbc.postgresql.org/download/postgresql-42.7.1.jar -P ~/spark/jars/

# Or install via pip (already in PYSPARK_SUBMIT_ARGS)
pip install pyspark --upgrade
```

---

## Summary

The Spatial Clustering Analyzer identifies geographic disease outbreak patterns by:

✅ **Loading** structured data from TimescaleDB via Spark JDBC  
✅ **Enriching** with semantic embeddings from ChromaDB  
✅ **Clustering** using DBSCAN (hotspot detection) or K-Means (regional analysis)  
✅ **Analyzing** disease/symptom distribution, severity, and temporal patterns per cluster  
✅ **Scoring** semantic coherence to validate topical similarity within clusters  
✅ **Outputting** JSON (machine-readable) and TXT (human-readable) reports  

This enables public health officials to:
- **Detect** emerging outbreak hotspots in real-time
- **Allocate** resources to high-burden regions
- **Compare** disease patterns across boroughs and time periods
- **Validate** spatial clusters with semantic similarity (avoid false positives)

Typical analysis of 270 records takes ~7 seconds and produces 3 output files with detailed cluster characteristics.
