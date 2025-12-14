
# Embedding Consumer (Ticket 3.4)

## Overview

The **Embedding Consumer** is the final stage in the Spark data processing pipeline. It transforms location-enriched disease surveillance data into dense vector embeddings suitable for semantic search in ChromaDB. This enables natural language queries like "respiratory illness outbreak in Brooklyn" to find relevant surveillance data through vector similarity.

## Pipeline Position

```
Scrapers → Kafka → Relevance Filter → Deduplication → Location Extraction → **Embeddings** → ChromaDB
                    (3.1)              (3.2)             (3.3)              (3.4)
```

**Input**: Location-enriched JSON from `data/locations/` (output of Location Consumer)  
**Output**: Vector embeddings in ChromaDB-ready format to `data/embeddings/`

---

## How the Code Works

### 1. **Architecture Components**

#### **EmbeddingConsumer Class**
Main class that handles:
- **Spark initialization** (4GB memory, local mode)
- **Sentence-Transformers model loading** (`all-MiniLM-L6-v2` by default)
- **Batch processing** of location-enriched records
- **Output writing** with summaries

#### **Key Methods**

##### `create_embedding_text(record: Dict) -> str`
Constructs rich text representation for embedding by combining:
- Original text content (title, description, text)
- Extracted diseases: `"Diseases: COVID-19, Influenza"`
- Extracted symptoms: `"Symptoms: fever, cough, fatigue"`
- Location info: `"Location: Williamsburg, Brooklyn"`
- Severity level: `"Severity: high"`

**Example Output:**
```
"Person reported severe respiratory symptoms at local clinic. Diseases: COVID-19, RSV. 
Symptoms: fever, cough, shortness of breath. Location: Williamsburg, Brooklyn. Severity: high"
```

##### `create_embedding(record: Dict) -> Dict`
Transforms a single record into a vector document:

1. **Generate rich text** using `create_embedding_text()`
2. **Encode to vector** using Sentence-Transformers (384-dimensional)
3. **Generate unique ID** with fallback strategy:
   - Try `post_id` or `id` from record
   - Parse `original_data` JSON for source-specific IDs (`unique_key`, `complaint_number`)
   - **Fallback to UUID** if no ID found (prevents duplicates)
4. **Extract metadata** for ChromaDB filtering (diseases, symptoms, location, severity)
5. **Package as vector document** with all metadata

**Output Schema:**
```json
{
  "id": "uuid-or-source-id",
  "vector": [0.123, -0.456, 0.789, ...],  // 384 floats
  "text": "rich embedding text...",
  "metadata": {
    "source": "reddit",
    "timestamp": "2025-12-13T10:30:00",
    "diseases": ["COVID-19", "RSV"],
    "symptoms": ["fever", "cough"],
    "severity": "high",
    "neighborhood": "Williamsburg",
    "borough": "Brooklyn",
    "location_source": "ner_extraction"
  },
  "embedding_model": "all-MiniLM-L6-v2",
  "embedding_dim": 384,
  "created_at": "2025-12-14T10:37:00Z"
}
```

##### `process_batch(records: List[Dict], batch_id: int)`
Processes all records in a batch:
- Iterates through each record
- Calls `create_embedding()` with error handling
- Writes successful embeddings to output file
- Logs statistics (total processed, successful embeddings)

##### `read_from_files()`
Reads location-enriched JSON files:
- Supports both **JSON arrays** and **JSONL** (newline-delimited)
- Handles multiple files via glob pattern
- Returns flattened list of all records

### 2. **Execution Flow**

```
START
  ↓
Initialize Spark Session (4GB memory, local mode)
  ↓
Load Sentence-Transformers Model (all-MiniLM-L6-v2)
  ↓
Read all JSON files from input directory
  ↓
FOR each record:
  ├─ Create rich text (text + metadata)
  ├─ Generate 384-dim embedding vector
  ├─ Extract/generate unique ID
  ├─ Package metadata for ChromaDB
  └─ Add to batch
  ↓
Write embeddings to output JSON file
  ↓
Write summary statistics
  ↓
Stop Spark Session
```

### 3. **ID Generation Strategy** (Critical for ChromaDB)

ChromaDB requires **unique IDs**. The consumer uses a multi-tier fallback:

```python
# Tier 1: Use existing IDs from upstream
record_id = record.get('post_id') or record.get('id')

# Tier 2: Parse original_data for source-specific IDs
if not record_id and 'original_data' exists:
    Parse JSON and try: id, post_id, unique_key, complaint_number

# Tier 3: Generate UUID (guaranteed unique)
if not record_id:
    record_id = str(uuid.uuid4())
```

**Why UUID Fallback?**  
Location consumer output often lacks top-level IDs, and MD5 hashing can create duplicates if timestamps are identical. UUID guarantees uniqueness.

---

## How to Run

### **Command Line Interface**

```bash
python src/spark_consumers/embedding_consumer.py \
    --input-path src/data/locations \
    --output-dir src/data/embeddings \
    --checkpoint-dir src/checkpoints/embeddings \
    --embedding-model all-MiniLM-L6-v2 \
    --embedding-dim 384
```

### **Via Pipeline Runner**

```bash
# Full pipeline (includes embeddings)
python run_project.py

# Or run chained pipeline
python src/run_chained_pipeline.py
```

### **Programmatic Usage**

```python
from src.spark_consumers.embedding_consumer import EmbeddingConsumer

consumer = EmbeddingConsumer(
    input_source='file',
    input_path='src/data/locations/',
    output_dir='src/data/embeddings',
    checkpoint_dir='src/checkpoints/embeddings',
    embedding_model='all-MiniLM-L6-v2',
    embedding_dim=384
)

consumer.start()
```

---

## Expected Output

### **File Structure**

```
src/data/embeddings/
├── embeddings_batch_0_20251214_103700.json     # Vector documents (ChromaDB ready)
└── embedding_summary_batch_0_20251214_103700.json  # Statistics
```

### **Embeddings File** (`embeddings_batch_*.json`)

JSON array of vector documents:
```json
[
  {
    "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "vector": [0.123, -0.456, 0.789, ...],  // 384 floats
    "text": "Person with flu symptoms in Brooklyn clinic. Diseases: Influenza. Symptoms: fever, cough. Location: Williamsburg, Brooklyn. Severity: medium",
    "metadata": {
      "source": "reddit",
      "timestamp": "2025-12-13T10:30:00",
      "diseases": ["Influenza"],
      "symptoms": ["fever", "cough"],
      "severity": "medium",
      "neighborhood": "Williamsburg",
      "borough": "Brooklyn",
      "confidence": 0.87
    },
    "embedding_model": "all-MiniLM-L6-v2",
    "embedding_dim": 384,
    "created_at": "2025-12-14T10:37:00Z"
  },
  ...
]
```

### **Summary File** (`embedding_summary_batch_*.json`)

Processing statistics:
```json
{
  "batch_id": 0,
  "total_embeddings": 12681,
  "embedding_model": "all-MiniLM-L6-v2",
  "embedding_dim": 384,
  "created_at": "2025-12-14T10:37:00Z",
  "sample_metadata": {
    "diseases": ["COVID-19", "Influenza", "RSV", "Food Poisoning"],
    "boroughs": ["Brooklyn", "Manhattan", "Queens", "Bronx", "Staten Island"],
    "severity_levels": ["low", "medium", "high"]
  }
}
```

### **Typical Processing Statistics**

```
Input: 12,681 location-enriched records
Output: 12,681 vector embeddings
Processing time: ~1-2 minutes (depends on model loading)
File size: ~50-100MB (depending on text length)
```

---

## Technical Considerations

### **1. ID Uniqueness (Critical Bug Fix)**

**Problem**: Original implementation used MD5 hash of `embedding_text + timestamp`, causing duplicates when:
- Multiple records had identical text
- Timestamps were missing or identical
- ChromaDB rejected: `"Expected IDs to be unique, found 66 duplicated IDs"`

**Solution**: Three-tier ID fallback with UUID guarantee:
```python
# Try source IDs first
record_id = record.get('post_id') or record.get('id')

# Parse original_data for source-specific IDs
if not record_id and 'original_data':
    Try: id, post_id, unique_key, complaint_number

# Guarantee uniqueness with UUID
if not record_id:
    record_id = str(uuid.uuid4())
```

**Result**: Zero duplicate IDs, all records load successfully into ChromaDB

### **2. Embedding Model Selection**

**Default**: `all-MiniLM-L6-v2`
- **Dimensions**: 384 (smaller = faster queries, less storage)
- **Speed**: ~1000 sentences/second on CPU
- **Quality**: Good for semantic similarity, trained on 1B+ sentence pairs

**Alternatives**:
- `all-mpnet-base-v2` (768-dim): Better quality, slower
- `paraphrase-multilingual-MiniLM-L12-v2`: Multilingual support
- `msmarco-distilbert-base-v4`: Optimized for search/retrieval

**Trade-offs**:
- **Higher dimensions**: Better semantic understanding, more storage/slower queries
- **Lower dimensions**: Faster queries, less storage, slightly reduced quality

### **3. Memory Management**

**Spark Configuration**:
```python
.config("spark.driver.memory", "4g")
.config("spark.executor.memory", "4g")
```

**Why 4GB?**
- Sentence-Transformers model: ~100MB
- Batch processing: ~12k records × ~1KB each = ~12MB
- Embedding vectors: 12k × 384 floats × 4 bytes = ~18MB
- Safety margin for JSON parsing and Spark overhead

**Scaling Considerations**:
- For 100k+ records: Increase to 8GB
- For production: Use distributed Spark with multiple executors
- Monitor with: `htop` or Activity Monitor during processing

### **4. Rich Text Construction**

**Design Philosophy**: Create semantically meaningful text that captures:
- **Primary content**: Original post/complaint text
- **Disease context**: Extracted disease names
- **Symptom patterns**: Clinical indicators
- **Spatial context**: Neighborhood/borough
- **Severity signals**: Risk level

**Why Combine Metadata?**  
Pure text embeddings miss structured information. By injecting metadata into the text:
- Queries like "COVID-19 in Brooklyn" match disease + location
- Symptom-based queries work: "fever and cough outbreaks"
- Severity filtering: "severe respiratory illness"

**Example Transformation**:
```python
# Input record
{
  "text": "Went to clinic, tested positive",
  "diseases_json": '["COVID-19"]',
  "symptoms_json": '["fever", "cough"]',
  "location_extraction": {"neighborhood": "Williamsburg", "borough": "Brooklyn"}
}

# Output embedding text
"Went to clinic, tested positive. Diseases: COVID-19. Symptoms: fever, cough. 
Location: Williamsburg, Brooklyn"
```

### **5. JSON Format Handling**

**Input Flexibility**:
```python
# Supports JSON arrays
[{"id": "1", ...}, {"id": "2", ...}]

# Supports JSONL (newline-delimited)
{"id": "1", ...}
{"id": "2", ...}
```

**Why Both?**  
Different pipeline stages output different formats:
- Relevance consumer: JSONL (streaming)
- Location consumer: JSON arrays (batch)

### **6. Metadata Preservation**

**Full Record Storage**:
```json
{
  "id": "...",
  "vector": [...],
  "text": "...",
  "metadata": {/* filtered fields */},
  "original_record": {/* complete input record */}
}
```

**Why Store Original?**  
- Debugging: Trace back to source data
- Auditing: Verify extraction accuracy
- Re-processing: Regenerate embeddings without re-running pipeline

### **7. Batch vs. Streaming**

**Current**: Batch processing only (`input_source='file'`)

**Why Batch?**  
- Embeddings typically generated after deduplication is complete
- Model loading overhead makes streaming inefficient
- ChromaDB bulk loading is faster than incremental

**Future Streaming Support**:
```python
# Not yet implemented
consumer = EmbeddingConsumer(input_source='kafka', kafka_topics='embeddings.ready')
```

### **8. Output Format (ChromaDB Compatible)**

**Schema Alignment**:
```python
# ChromaDB expects
{
  "ids": ["id1", "id2", ...],
  "embeddings": [[vec1], [vec2], ...],
  "metadatas": [{"key": "val"}, ...],
  "documents": ["text1", "text2", ...]
}

# Our format transforms easily
chromadb.collection.add(
    ids=[doc['id'] for doc in embeddings],
    embeddings=[doc['vector'] for doc in embeddings],
    metadatas=[doc['metadata'] for doc in embeddings],
    documents=[doc['text'] for doc in embeddings]
)
```

### **9. Error Handling**

**Graceful Degradation**:
- Failed embeddings logged but don't stop batch
- JSON parsing errors caught per-record
- Model encoding errors isolated to single record

**Logging Strategy**:
```python
try:
    vector_doc = self.create_embedding(record)
    embedded_docs.append(vector_doc)
except Exception as e:
    logger.error(f"Error creating embedding: {e}")
    continue  # Skip this record, process rest
```

### **10. Performance Optimization**

**Current Bottlenecks**:
- Model loading: ~3-5 seconds (one-time cost)
- Embedding generation: ~0.5-1ms per record
- JSON I/O: ~0.1ms per record

**For 12,681 records**:
- Model loading: 5s
- Embedding: 12.681k × 1ms = ~13s
- I/O: 12.681k × 0.1ms = ~1.3s
- **Total**: ~20 seconds

**Optimization Options**:
1. **Batch encoding** (current): `model.encode([text1, text2, ...])`  
2. **GPU acceleration**: Use `device='cuda'` for 10x speedup
3. **Quantization**: Reduce precision (float16) for 50% storage reduction
4. **Async I/O**: Write embeddings asynchronously

---

## Dependencies

```bash
# Required packages
pip install pyspark==3.5.3
pip install sentence-transformers
pip install torch  # PyTorch backend for transformers
pip install numpy
```

**Java Requirement**: Java 11+ (for PySpark)
```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@11
```

---

## Integration with ChromaDB

After embeddings are generated, load into ChromaDB:

```bash
python src/vector_db/chromadb_client.py \
    --embeddings-dir src/data/embeddings \
    --persist-dir data/chromadb \
    --collection nyc_disease_surveillance \
    --clear  # Optional: clear existing data
```

**Query Example**:
```python
from src.vector_db.chromadb_client import ChromaDBClient

client = ChromaDBClient(persist_directory='data/chromadb')
results = client.query(
    query_texts=["respiratory illness outbreak in Brooklyn"],
    n_results=5
)

# Returns top 5 most similar documents with metadata
```

---

## Troubleshooting

### **Issue**: `ModuleNotFoundError: No module named 'sentence_transformers'`
**Solution**: 
```bash
pip install sentence-transformers torch
```

### **Issue**: `Expected IDs to be unique, found X duplicated IDs`
**Solution**: Updated code now uses UUID fallback. Delete old embeddings and regenerate:
```bash
rm -rf src/data/embeddings/*.json
python src/spark_consumers/embedding_consumer.py --input-path src/data/locations
```

### **Issue**: Out of memory errors
**Solution**: Reduce batch size or increase Spark memory:
```bash
# Increase Spark memory to 8GB
python src/spark_consumers/embedding_consumer.py  # Edit config in code
```

### **Issue**: Slow embedding generation
**Solution**: Use GPU acceleration or smaller model:
```bash
# Use CPU-optimized model
python src/spark_consumers/embedding_consumer.py --embedding-model all-MiniLM-L6-v2
```

---

## Summary

The Embedding Consumer transforms processed disease surveillance data into semantic vectors, enabling natural language search through ChromaDB. Key features:

✅ **Rich text construction** combining content + metadata  
✅ **UUID-based ID generation** guaranteeing uniqueness  
✅ **384-dimensional embeddings** balancing quality and speed  
✅ **ChromaDB-ready output** with full metadata preservation  
✅ **Robust error handling** with per-record isolation  
✅ **Batch processing** optimized for ~12k records in ~20 seconds  

This enables the final application layer to perform semantic queries like "flu outbreak in Queens" or "respiratory illness near schools in Manhattan" with vector similarity search.
