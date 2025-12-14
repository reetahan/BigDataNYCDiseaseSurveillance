# ChromaDB Loading Process (Ticket 4.3)

## Overview

The **ChromaDB Client** loads vector embeddings from the Embedding Consumer into ChromaDB for semantic search. It enables natural language queries like "respiratory illness in Brooklyn" to find relevant disease surveillance data through vector similarity matching.

## Pipeline Position

```
Embedding Consumer → JSON files → **ChromaDB Loader** → ChromaDB (Vector DB)
  (src/spark_consumers/    (data/embeddings/)    (this script)         (data/chromadb/)
   embedding_consumer.py)
```

**Input**: Embedding JSON files from `data/embeddings/embeddings_batch_*.json`  
**Output**: Populated ChromaDB vector database at `data/chromadb/`

---

## How the Code Works

### 1. **Architecture Components**

#### **ChromaDBClient Class**
Main class managing the ChromaDB connection and operations:
- **PersistentClient initialization** - creates/connects to local ChromaDB instance
- **Collection management** - get or create collection with metadata
- **Bulk loading** - reads embedding JSON files and inserts into ChromaDB
- **Query interface** - semantic search with metadata filtering

#### **Key Methods**

##### `__init__(persist_directory, collection_name)`
Initializes ChromaDB connection:

```python
# Creates directory if doesn't exist
os.makedirs("data/chromadb", exist_ok=True)

# Initialize persistent client (disk-based storage)
self.client = chromadb.PersistentClient(path=persist_directory)

# Get or create collection
self.collection = self.client.get_or_create_collection(
    name="nyc_disease_surveillance",
    metadata={"description": "NYC Disease Surveillance Embeddings"}
)
```

**Why PersistentClient?**
- Data persists across restarts (unlike in-memory client)
- Stores vectors in SQLite database at `data/chromadb/chroma.sqlite3`
- No external database server required (unlike pgvector)

##### `load_embeddings_from_file(embeddings_file: str) -> int`
Loads a single embedding JSON file:

**Step-by-Step Process:**

1. **Read JSON file**:
```python
with open(embeddings_file, 'r') as f:
    embeddings_data = json.load(f)  # List of embedding documents
```

2. **Parse and transform each document**:
```python
for doc in embeddings_data:
    ids.append(doc['id'])                    # Unique identifier
    embeddings.append(doc['vector'])         # 384-dim float array
    documents.append(doc['text'])            # Rich text representation
```

3. **Flatten metadata** (ChromaDB requirements):
```python
metadata = doc['metadata'].copy()

# Convert lists to comma-separated strings
if 'diseases' in metadata and isinstance(metadata['diseases'], list):
    metadata['diseases'] = ','.join(metadata['diseases'])
    # ["COVID-19", "RSV"] → "COVID-19,RSV"

if 'symptoms' in metadata and isinstance(metadata['symptoms'], list):
    metadata['symptoms'] = ','.join(metadata['symptoms'])
    # ["fever", "cough"] → "fever,cough"

# Add embedding generation metadata
metadata['embedding_model'] = doc['embedding_model']
metadata['embedding_dim'] = doc['embedding_dim']
metadata['created_at'] = doc['created_at']

# Remove None values (ChromaDB rejects them)
metadata = {k: v for k, v in metadata.items() if v is not None}
```

**Why Flatten Lists?**  
ChromaDB metadata only supports scalar types (strings, numbers, booleans). Lists must be converted to comma-separated strings for filtering.

4. **Bulk insert into ChromaDB**:
```python
self.collection.add(
    ids=ids,                  # ["uuid1", "uuid2", ...]
    embeddings=embeddings,    # [[0.1, -0.2, ...], [0.3, 0.4, ...]]
    metadatas=metadatas,      # [{"disease": "COVID", ...}, ...]
    documents=documents       # ["text1", "text2", ...]
)
```

**Returns**: Number of documents loaded

##### `load_embeddings_from_directory(embeddings_dir: str) -> int`
Batch loads all embedding files:

```python
# Find all embedding files (not summaries)
file_pattern = os.path.join(embeddings_dir, "embeddings_batch_*.json")
embedding_files = glob.glob(file_pattern)

total_loaded = 0
for file_path in embedding_files:
    try:
        count = self.load_embeddings_from_file(file_path)
        total_loaded += count
    except Exception as e:
        logger.error(f"Failed to load {file_path}: {e}")
        # Continue loading other files even if one fails
```

**Returns**: Total documents loaded across all files

##### `query(query_texts, n_results, where, where_document) -> Dict`
Performs semantic search:

```python
results = self.collection.query(
    query_texts=["respiratory illness in Brooklyn"],
    n_results=10,
    where={"borough": "Brooklyn"},           # Metadata filter
    where_document={"$contains": "COVID"}    # Document content filter
)
```

**How It Works:**
1. ChromaDB encodes query text using same embedding model
2. Computes cosine similarity between query vector and all stored vectors
3. Applies metadata filters (`where` clause)
4. Returns top N most similar documents with distances

**Returns**:
```python
{
    'ids': [['id1', 'id2', ...]],
    'documents': [['text1', 'text2', ...]],
    'metadatas': [[{meta1}, {meta2}, ...]],
    'distances': [[0.234, 0.456, ...]]  # Lower = more similar
}
```

##### `search_by_disease(query_text, disease, n_results) -> Dict`
Disease-specific search:

```python
results = self.collection.query(
    query_texts=[query_text],
    n_results=n_results,
    where_document={"$contains": disease}  # Filter for disease mentions
)
```

**Use Case**: "Find all COVID-19 outbreaks"

##### `search_by_location(query_text, borough, neighborhood, n_results) -> Dict`
Location-filtered search:

```python
where_filter = {}
if borough:
    where_filter['borough'] = borough
if neighborhood:
    where_filter['neighborhood'] = neighborhood

results = self.collection.query(
    query_texts=[query_text],
    where=where_filter
)
```

**Use Case**: "Find disease outbreaks in Williamsburg, Brooklyn"

##### `search_by_severity(query_text, severity, n_results) -> Dict`
Severity-filtered search:

```python
results = self.collection.query(
    query_texts=[query_text],
    where={"severity": severity}  # low/medium/high
)
```

**Use Case**: "Find high-severity outbreaks"

##### `get_statistics() -> Dict`
Retrieves collection statistics:

```python
count = self.collection.count()  # Total documents

# Sample first 100 documents
sample = self.collection.get(limit=min(100, count))

# Analyze metadata
for meta in sample['metadatas']:
    unique_diseases.update(meta['diseases'].split(','))
    unique_boroughs.add(meta['borough'])
    severity_counts[meta['severity']] += 1
```

**Returns**:
```python
{
    "total_documents": 12681,
    "collection_name": "nyc_disease_surveillance",
    "persist_directory": "data/chromadb",
    "sample_diseases": ["COVID-19", "Influenza", "RSV", ...],
    "sample_boroughs": ["Brooklyn", "Manhattan", "Queens", ...],
    "severity_distribution": {"high": 45, "medium": 32, "low": 23}
}
```

##### `clear_collection()`
Resets the collection:

```python
# Delete existing collection
self.client.delete_collection(name=self.collection_name)

# Recreate empty collection
self.collection = self.client.get_or_create_collection(
    name=self.collection_name,
    metadata={"description": "NYC Disease Surveillance Embeddings"}
)
```

**When to Use**: Regenerating embeddings with different model/parameters

### 2. **Execution Flow**

```
START
  ↓
Parse CLI arguments (--embeddings-dir, --persist-dir, --clear, --query)
  ↓
Initialize ChromaDBClient
  ├─ Create persist directory (data/chromadb/)
  ├─ Initialize PersistentClient
  └─ Get/create collection (nyc_disease_surveillance)
  ↓
[Optional] Clear existing collection (if --clear flag)
  ↓
Load embeddings from directory:
  ├─ Find all embeddings_batch_*.json files
  ├─ FOR each file:
  │   ├─ Read JSON array
  │   ├─ Parse ids, vectors, documents, metadata
  │   ├─ Flatten metadata (lists → comma-separated strings)
  │   ├─ Remove None values
  │   └─ Bulk insert: collection.add(...)
  └─ Log total loaded
  ↓
Get statistics:
  ├─ Count total documents
  ├─ Sample 100 documents
  └─ Analyze diseases, locations, severity
  ↓
[Optional] Run test query (if --query provided)
  ├─ Encode query text to vector
  ├─ Compute cosine similarity
  └─ Return top N results with metadata
  ↓
END (data persisted to data/chromadb/)
```

### 3. **Data Transformation Example**

**Input** (from `embeddings_batch_0.json`):
```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "vector": [0.123, -0.456, 0.789, ..., 0.234],
  "text": "Person with flu symptoms. Diseases: Influenza. Location: Brooklyn.",
  "metadata": {
    "source": "reddit",
    "timestamp": "2025-12-13T10:30:00",
    "diseases": ["Influenza"],
    "symptoms": ["fever", "cough"],
    "severity": "medium",
    "borough": "Brooklyn",
    "neighborhood": "Williamsburg"
  },
  "embedding_model": "all-MiniLM-L6-v2",
  "embedding_dim": 384,
  "created_at": "2025-12-14T10:37:00Z"
}
```

**Transformed for ChromaDB**:
```python
# Add to collection with:
ids = ["a1b2c3d4-e5f6-7890-abcd-ef1234567890"]
embeddings = [[0.123, -0.456, 0.789, ..., 0.234]]
documents = ["Person with flu symptoms. Diseases: Influenza. Location: Brooklyn."]
metadatas = [{
    "source": "reddit",
    "timestamp": "2025-12-13T10:30:00",
    "diseases": "Influenza",           # List → String
    "symptoms": "fever,cough",         # List → String
    "severity": "medium",
    "borough": "Brooklyn",
    "neighborhood": "Williamsburg",
    "embedding_model": "all-MiniLM-L6-v2",
    "embedding_dim": 384,
    "created_at": "2025-12-14T10:37:00Z"
}]
```

**Stored in ChromaDB** (`data/chromadb/chroma.sqlite3`):
- Vectors indexed for fast similarity search (HNSW algorithm)
- Metadata stored for filtering
- Document text stored for retrieval

---

## How to Run

### **Command Line Interface**

#### Basic Loading:
```bash
python src/database/chromadb_client.py \
    --embeddings-dir src/data/embeddings \
    --persist-dir data/chromadb \
    --collection nyc_disease_surveillance
```

#### Clear and Reload:
```bash
python src/database/chromadb_client.py \
    --embeddings-dir src/data/embeddings \
    --clear  # Delete existing data first
```

#### Load with Test Query:
```bash
python src/database/chromadb_client.py \
    --embeddings-dir src/data/embeddings \
    --query "respiratory illness outbreak in Brooklyn" \
    --clear
```

### **Via Pipeline Runner**

In `run_project.py`, Step 5 loads ChromaDB:

```python
def load_chromadb():
    """Load embeddings into ChromaDB"""
    return run_command(
        'python src/database/chromadb_client.py --embeddings-dir src/data/embeddings --clear',
        "Loading ChromaDB",
        timeout=120
    )

# Called after chained pipeline completes
load_chromadb()
```

### **Programmatic Usage**

```python
from src.database.chromadb_client import ChromaDBClient

# Initialize client
client = ChromaDBClient(
    persist_directory='data/chromadb',
    collection_name='nyc_disease_surveillance'
)

# Clear existing data (optional)
client.clear_collection()

# Load embeddings
total = client.load_embeddings_from_directory('src/data/embeddings')
print(f"Loaded {total} documents")

# Get statistics
stats = client.get_statistics()
print(f"Total: {stats['total_documents']}")
print(f"Diseases: {stats['sample_diseases']}")

# Query
results = client.query(
    query_texts=["flu outbreak in Queens"],
    n_results=5
)

# Disease-specific search
results = client.search_by_disease(
    query_text="respiratory illness",
    disease="COVID-19",
    n_results=10
)

# Location-filtered search
results = client.search_by_location(
    query_text="disease outbreak",
    borough="Brooklyn",
    neighborhood="Williamsburg",
    n_results=10
)
```

---

## Expected Output

### **Console Output**

```
2025-12-14 10:37:00,123 - __main__ - INFO - Initializing ChromaDB at: data/chromadb
2025-12-14 10:37:00,456 - __main__ - INFO - Connected to collection: nyc_disease_surveillance
2025-12-14 10:37:00,457 - __main__ - INFO - Current collection size: 0 documents
2025-12-14 10:37:00,458 - __main__ - WARNING - Clearing collection: nyc_disease_surveillance
2025-12-14 10:37:00,459 - __main__ - INFO - Collection cleared
2025-12-14 10:37:00,460 - __main__ - INFO - ============================================================
2025-12-14 10:37:00,460 - __main__ - INFO - Loading Embeddings into ChromaDB
2025-12-14 10:37:00,460 - __main__ - INFO - ============================================================
2025-12-14 10:37:00,461 - __main__ - INFO - Loading embeddings from directory: src/data/embeddings
2025-12-14 10:37:00,462 - __main__ - INFO - Found 2 embedding files
2025-12-14 10:37:00,463 - __main__ - INFO - Loading embeddings from: src/data/embeddings/embeddings_batch_0_20251213_174759.json
2025-12-14 10:37:12,345 - __main__ - INFO - Added 6340 documents to ChromaDB
2025-12-14 10:37:12,346 - __main__ - INFO - Loading embeddings from: src/data/embeddings/embeddings_batch_0_20251213_175218.json
2025-12-14 10:37:24,567 - __main__ - INFO - Added 6341 documents to ChromaDB
2025-12-14 10:37:24,568 - __main__ - INFO - Total documents loaded: 12681
2025-12-14 10:37:24,569 - __main__ - INFO - Collection size: 12681
2025-12-14 10:37:24,570 - __main__ - INFO - 
============================================================
2025-12-14 10:37:24,570 - __main__ - INFO - ChromaDB Statistics
2025-12-14 10:37:24,570 - __main__ - INFO - ============================================================
2025-12-14 10:37:24,571 - __main__ - INFO - Total Documents: 12681
2025-12-14 10:37:24,571 - __main__ - INFO - Collection: nyc_disease_surveillance
2025-12-14 10:37:24,572 - __main__ - INFO - Diseases (sample): COVID-19, Influenza, RSV, Food Poisoning, Tuberculosis, Measles, Norovirus, Hepatitis, Legionnaires
2025-12-14 10:37:24,572 - __main__ - INFO - Boroughs: Brooklyn, Manhattan, Queens, Bronx, Staten Island
2025-12-14 10:37:24,573 - __main__ - INFO - Severity Distribution: {'high': 23, 'medium': 42, 'low': 35}
```

### **With Test Query** (--query flag)

```
2025-12-14 10:37:24,574 - __main__ - INFO - 
============================================================
2025-12-14 10:37:24,574 - __main__ - INFO - Test Query: 'respiratory illness outbreak in Brooklyn'
2025-12-14 10:37:24,574 - __main__ - INFO - ============================================================

2025-12-14 10:37:24,678 - __main__ - INFO - Result 1 (distance: 0.2345):
2025-12-14 10:37:24,678 - __main__ - INFO -   Text: Person with severe respiratory symptoms at local clinic. Diseases: COVID-19, RSV. Symptoms: fever, cough, shortness of breath. Location: Williamsburg, Brooklyn. Severity: high...
2025-12-14 10:37:24,679 - __main__ - INFO -   Disease: COVID-19,RSV
2025-12-14 10:37:24,679 - __main__ - INFO -   Location: Williamsburg, Brooklyn
2025-12-14 10:37:24,679 - __main__ - INFO -   Severity: high

2025-12-14 10:37:24,680 - __main__ - INFO - Result 2 (distance: 0.3456):
2025-12-14 10:37:24,680 - __main__ - INFO -   Text: Child with flu-like symptoms in Brooklyn school. Diseases: Influenza. Symptoms: fever, cough, fatigue. Location: Park Slope, Brooklyn. Severity: medium...
2025-12-14 10:37:24,680 - __main__ - INFO -   Disease: Influenza
2025-12-14 10:37:24,681 - __main__ - INFO -   Location: Park Slope, Brooklyn
2025-12-14 10:37:24,681 - __main__ - INFO -   Severity: medium

2025-12-14 10:37:24,682 - __main__ - INFO - 
✓ ChromaDB loading completed successfully!
```

### **File Structure After Loading**

```
data/chromadb/
├── chroma.sqlite3           # Main SQLite database (vectors + metadata)
└── c2dc7c0d-.../            # Collection-specific files (HNSW index, etc.)
    ├── data_level0.bin
    ├── header.bin
    └── length.bin
```

### **Typical Statistics**

```
Input: 2 embedding files (embeddings_batch_0_*.json)
Total Records: 12,681 disease surveillance documents
Vector Dimensions: 384 (per document)
Processing Time: ~25-30 seconds
ChromaDB Size: ~50-80MB (vectors + metadata + indices)
Diseases Detected: 15+ (COVID-19, Influenza, RSV, Food Poisoning, etc.)
Locations: 5 boroughs, 50+ neighborhoods
```

---

## Technical Considerations

### **1. ChromaDB Architecture**

**Storage Backend**:
- **SQLite database**: Stores vectors, metadata, documents
- **HNSW index**: Hierarchical Navigable Small World graph for fast similarity search
- **Persistent storage**: Data survives restarts (unlike in-memory mode)

**File Structure**:
```
data/chromadb/
├── chroma.sqlite3                    # Main database
└── <collection-uuid>/                # Per-collection files
    ├── data_level0.bin              # HNSW graph data
    ├── header.bin                   # Collection metadata
    └── length.bin                   # Vector length info
```

**Why ChromaDB vs. Alternatives?**

| Feature | ChromaDB | Pinecone | pgvector | FAISS |
|---------|----------|----------|----------|-------|
| **Self-hosted** | ✅ | ❌ (Cloud) | ✅ | ✅ |
| **Persistent** | ✅ | ✅ | ✅ | ⚠️ (Manual) |
| **Metadata filtering** | ✅ | ✅ | ⚠️ (Limited) | ❌ |
| **Python API** | ✅ Excellent | ✅ Good | ⚠️ SQL | ⚠️ Complex |
| **Setup complexity** | ✅ Low | ✅ Low | ⚠️ PostgreSQL | ⚠️ Manual |
| **Cost** | ✅ Free | ❌ Paid | ✅ Free | ✅ Free |

**Chosen for**: Easy local development, metadata filtering, persistence, Python-friendly API

### **2. Metadata Flattening (Critical)**

**Problem**: ChromaDB only supports scalar metadata values:
```python
# ❌ Not supported
metadata = {"diseases": ["COVID-19", "RSV"]}

# ✅ Must convert to string
metadata = {"diseases": "COVID-19,RSV"}
```

**Implementation**:
```python
if 'diseases' in metadata and isinstance(metadata['diseases'], list):
    metadata['diseases'] = ','.join(metadata['diseases'])
```

**Why?**  
ChromaDB's underlying SQLite database stores metadata as simple types. List fields must be serialized.

**Query Implications**:
```python
# ❌ Can't filter exact list match
where={"diseases": ["COVID-19", "RSV"]}

# ✅ Use $contains for partial match
where_document={"$contains": "COVID-19"}

# ⚠️ String filter (matches "COVID-19,RSV" or "COVID-19" prefix)
where={"diseases": {"$like": "COVID-19%"}}
```

### **3. Duplicate ID Handling**

**Critical Error**: ChromaDB requires unique IDs
```
chromadb.errors.IDAlreadyExistsError: Expected IDs to be unique, found 66 duplicated IDs
```

**Root Cause**: Embedding consumer previously used MD5 hash of text+timestamp, creating duplicates.

**Solution**: UUID-based ID generation in embedding consumer:
```python
# Guaranteed unique
record_id = str(uuid.uuid4())
```

**Verification**:
```python
# Check for duplicates before loading
ids = [doc['id'] for doc in embeddings_data]
duplicates = [id for id in ids if ids.count(id) > 1]
if duplicates:
    raise ValueError(f"Duplicate IDs: {duplicates}")
```

### **4. Bulk vs. Incremental Loading**

**Current Approach**: Bulk loading
```python
# Load all documents at once
self.collection.add(
    ids=[...],           # All IDs
    embeddings=[...],    # All vectors
    metadatas=[...],     # All metadata
    documents=[...]      # All documents
)
```

**Advantages**:
- Faster: Single transaction, batch index update
- Atomic: All-or-nothing insertion
- Efficient: Optimized HNSW index construction

**Alternative**: Incremental
```python
# Add one at a time
for doc in embeddings_data:
    self.collection.add(
        ids=[doc['id']],
        embeddings=[doc['vector']],
        metadatas=[doc['metadata']],
        documents=[doc['text']]
    )
```

**When to Use Incremental**:
- Streaming pipeline (real-time ingestion)
- Memory constraints (can't load full batch)
- Error recovery (resume from last processed document)

### **5. Query Performance**

**HNSW Index**: Approximate nearest neighbor search
- **Build time**: O(N log N) during insertion
- **Query time**: O(log N) per query
- **Accuracy**: 95%+ recall (configurable)

**For 12,681 documents**:
- **Insertion**: ~25 seconds (includes index building)
- **Query**: ~100-200ms per query
- **Memory**: ~50MB (vectors + index)

**Scaling Considerations**:
- **100k documents**: ~5 minutes load, ~200ms query
- **1M documents**: Consider sharding or distributed ChromaDB
- **10M+ documents**: Use production vector DB (Pinecone, Weaviate)

**Optimization Tips**:
```python
# Adjust HNSW parameters for speed/accuracy trade-off
collection = client.create_collection(
    name="fast_collection",
    metadata={
        "hnsw:construction_ef": 100,  # Lower = faster build, less accurate
        "hnsw:search_ef": 50,         # Lower = faster query, less accurate
        "hnsw:M": 16                  # Lower = less memory, less accurate
    }
)
```

### **6. Distance Metrics**

**Default**: Cosine similarity (L2-normalized dot product)
```python
# Distance range: 0.0 (identical) to 2.0 (opposite)
# Typical results: 0.2-0.8 for relevant matches
```

**Interpretation**:
- **< 0.3**: Highly similar (same disease, location, context)
- **0.3-0.5**: Moderately similar (related concepts)
- **0.5-0.8**: Weakly similar (tangentially related)
- **> 0.8**: Dissimilar (different topics)

**Alternative Metrics**:
```python
# L2 (Euclidean) distance
collection = client.create_collection(
    name="l2_collection",
    metadata={"hnsw:space": "l2"}
)

# Inner product (dot product without normalization)
collection = client.create_collection(
    name="ip_collection",
    metadata={"hnsw:space": "ip"}
)
```

### **7. Metadata Filtering Performance**

**Pre-filtering** (recommended):
```python
# Filter first, then search
results = client.query(
    query_texts=["outbreak"],
    where={"borough": "Brooklyn"},  # Narrows search space
    n_results=10
)
```

**Post-filtering** (slower):
```python
# Search all, filter results
results = client.query(query_texts=["outbreak"], n_results=100)
filtered = [r for r in results if r['metadata']['borough'] == 'Brooklyn'][:10]
```

**Performance Impact**:
- **Pre-filtering**: O(log N_filtered)
- **Post-filtering**: O(log N_total)

For 12,681 docs, filtering to Brooklyn (270 docs) speeds up queries by ~5x.

### **8. Error Handling Strategies**

**File-Level Errors**:
```python
for file_path in embedding_files:
    try:
        count = self.load_embeddings_from_file(file_path)
        total_loaded += count
    except Exception as e:
        logger.error(f"Failed to load {file_path}: {e}")
        # Continue with other files
```

**Document-Level Errors** (if implemented):
```python
for doc in embeddings_data:
    try:
        self.collection.add(ids=[doc['id']], ...)
    except chromadb.errors.IDAlreadyExistsError:
        logger.warning(f"Skipping duplicate ID: {doc['id']}")
    except Exception as e:
        logger.error(f"Failed to add doc {doc['id']}: {e}")
```

**Common Errors**:
1. **Duplicate IDs**: Fixed by UUID generation in embedding consumer
2. **None values in metadata**: Filtered out with `{k: v for k, v in meta.items() if v is not None}`
3. **List values in metadata**: Converted to comma-separated strings
4. **Missing vector dimensions**: Validate `len(vector) == 384`

### **9. Memory Management**

**Loading Process**:
```python
# 1. Read entire JSON file into memory
with open(embeddings_file, 'r') as f:
    embeddings_data = json.load(f)  # ~10-20MB per file

# 2. Parse into separate lists
ids = [...]          # ~1MB (12k strings)
embeddings = [...]   # ~18MB (12k × 384 floats × 4 bytes)
metadatas = [...]    # ~2MB (metadata dicts)
documents = [...]    # ~5MB (text strings)

# 3. Bulk insert (ChromaDB internal processing)
self.collection.add(...)  # Peak memory: ~50MB
```

**Total Memory Usage**: ~100MB peak during loading

**For Large Datasets**:
```python
# Chunked loading (not currently implemented)
def load_in_chunks(embeddings_data, chunk_size=1000):
    for i in range(0, len(embeddings_data), chunk_size):
        chunk = embeddings_data[i:i+chunk_size]
        self.collection.add(
            ids=[doc['id'] for doc in chunk],
            embeddings=[doc['vector'] for doc in chunk],
            ...
        )
```

### **10. Integration with TimescaleDB**

**Complementary Databases**:

| Use Case | Database |
|----------|----------|
| **Semantic search** ("flu outbreak in Brooklyn") | ChromaDB |
| **Structured queries** (COUNT, GROUP BY, time-series) | TimescaleDB |
| **Metadata filtering** (borough, disease, severity) | Both |
| **Time-series analysis** (trends over time) | TimescaleDB |
| **Similarity search** (find related outbreaks) | ChromaDB |

**Example Workflow**:
```python
# 1. Semantic search in ChromaDB
results = chroma_client.query(
    query_texts=["respiratory illness"],
    n_results=100
)

# 2. Extract IDs of relevant documents
relevant_ids = results['ids'][0]

# 3. Query TimescaleDB for time-series analysis
cursor.execute("""
    SELECT date_trunc('day', timestamp) as day,
           COUNT(*) as cases
    FROM disease_events
    WHERE id = ANY(%s)
    GROUP BY day
    ORDER BY day
""", (relevant_ids,))
```

---

## Dependencies

```bash
# Required packages
pip install chromadb
pip install sentence-transformers  # For query encoding (if needed)
```

**No External Services**:
- ChromaDB runs in-process (no server required)
- SQLite embedded database (included with Python)
- HNSW index built automatically

---

## Troubleshooting

### **Issue**: `ModuleNotFoundError: No module named 'chromadb'`
**Solution**:
```bash
pip install chromadb
```

### **Issue**: `Expected IDs to be unique, found X duplicated IDs`
**Solution**: Regenerate embeddings with UUID-based IDs:
```bash
rm -rf src/data/embeddings/*.json
python src/spark_consumers/embedding_consumer.py --input-path src/data/locations
python src/database/chromadb_client.py --embeddings-dir src/data/embeddings --clear
```

### **Issue**: `TypeError: Object of type ndarray is not JSON serializable`
**Solution**: Ensure vectors are converted to lists:
```python
embeddings.append(doc['vector'].tolist())  # If NumPy array
```

### **Issue**: Slow query performance
**Solution**: Reduce search space with metadata filtering:
```bash
# ❌ Slow (searches all 12k docs)
results = client.query(query_texts=["outbreak"], n_results=10)

# ✅ Fast (searches ~270 Brooklyn docs)
results = client.query(
    query_texts=["outbreak"],
    where={"borough": "Brooklyn"},
    n_results=10
)
```

### **Issue**: Collection not persisting across restarts
**Solution**: Verify using PersistentClient (not in-memory):
```python
# ✅ Correct
client = chromadb.PersistentClient(path="data/chromadb")

# ❌ Wrong (in-memory, data lost on restart)
client = chromadb.Client()
```

### **Issue**: Out of memory during loading
**Solution**: Implement chunked loading:
```python
# Load in batches of 1000 documents
for i in range(0, len(embeddings_data), 1000):
    chunk = embeddings_data[i:i+1000]
    self.collection.add(...)
```

---

## Query Examples

### **Basic Semantic Search**:
```python
results = client.query(
    query_texts=["respiratory illness outbreak"],
    n_results=5
)
```

### **Disease-Specific**:
```python
results = client.search_by_disease(
    query_text="outbreak in school",
    disease="COVID-19",
    n_results=10
)
```

### **Location-Filtered**:
```python
results = client.search_by_location(
    query_text="disease outbreak",
    borough="Brooklyn",
    neighborhood="Williamsburg",
    n_results=10
)
```

### **Severity-Filtered**:
```python
results = client.search_by_severity(
    query_text="respiratory illness",
    severity="high",
    n_results=10
)
```

### **Combined Filters**:
```python
results = client.query(
    query_texts=["flu outbreak in schools"],
    where={
        "borough": "Brooklyn",
        "severity": "high"
    },
    where_document={"$contains": "Influenza"},
    n_results=10
)
```

### **Time-Based Query** (using metadata timestamp):
```python
results = client.query(
    query_texts=["recent outbreak"],
    where={
        "timestamp": {"$gte": "2025-12-01T00:00:00"}
    },
    n_results=10
)
```

---

## Summary

The ChromaDB Loader transforms embedding JSON files into a queryable vector database, enabling semantic search over disease surveillance data. Key features:

✅ **PersistentClient** - disk-based storage that survives restarts  
✅ **Metadata flattening** - converts lists to comma-separated strings for ChromaDB compatibility  
✅ **Bulk loading** - efficient batch insertion with HNSW index building  
✅ **Rich query interface** - semantic search with disease/location/severity filtering  
✅ **Error resilience** - continues loading even if individual files fail  
✅ **Statistics tracking** - provides insights into loaded data distribution  
✅ **UUID-based IDs** - guarantees uniqueness (fixes duplicate ID bug)  

This enables the final application to perform natural language queries like "respiratory illness in Brooklyn schools" with sub-second response times across 12,681+ disease surveillance documents.
