# NYC Disease Surveillance - Chained Data Pipeline

## Overview

This is a multi-stage Spark Streaming pipeline that processes disease surveillance data from multiple sources through four sequential consumers:

```
Kafka → 3.1 Relevance → 3.2 Deduplication → 3.3 Location → 3.4 Embeddings → Vector DB
```

## Pipeline Stages

### Stage 1: Relevance Analysis (Ticket 3.1)
**Consumer:** `relevance_consumer.py`
**Input:** Kafka topics (reddit, bluesky, rss, nyc_311, nyc_press, nyc_covid)
**Output:** `data/relevance/relevant/` (relevant records) & `data/relevance/irrelevant/`

**What it does:**
- Filters for health-relevant content using keyword analysis
- Extracts diseases, symptoms, and severity levels
- Assigns confidence scores
- Only relevant records proceed to next stage

**Fields added:**
- `is_relevant` (boolean)
- `diseases_json` (JSON list)
- `symptoms_json` (JSON list)
- `severity` (low/medium/high/unknown)
- `confidence` (0.0-1.0)
- `reason` (keyword_analysis)

---

### Stage 2: Deduplication (Ticket 3.2)
**Consumer:** `deduplication_consumer.py`
**Input:** `data/relevance/relevant/` (files from Stage 1)
**Output:** `data/deduplicated/unique_*.json` & `data/deduplicated/duplicates_*.json`

**What it does:**
- 3-Tier deduplication strategy:
  - **Tier 1:** Exact hash matching (~0ms)
  - **Tier 2:** Fuzzy TF-IDF matching (~5ms, 90% threshold)
  - **Tier 3:** Semantic embeddings (~100ms, 85% threshold)
- Separates unique and duplicate records

**Fields added:**
- `is_duplicate` (boolean)
- `dedup_tier` (unique/exact_hash/fuzzy_tfidf/semantic_embedding)
- `similarity_score` (0.0-1.0)
- `batch_id` (int)
- `processed_at` (timestamp)

---

### Stage 3: Location Extraction (Ticket 3.3)
**Consumer:** `location_consumer.py`
**Input:** `data/deduplicated/unique_*.json` (unique records from Stage 2)
**Output:** `data/locations/locations_batch_*.json`

**What it does:**
- Extracts locations from text using spaCy NER
- Maps coordinates (lat/lon) to NYC neighborhoods
- Normalizes location names (aliases, landmarks)
- Enriches with borough and neighborhood data

**Fields added:**
- `location_extraction` (nested object):
  - `extracted_locations` (list)
  - `normalized_locations` (list)
  - `neighborhood` (string or null)
  - `borough` (string or null)
  - `location_source` (coordinates/text_extraction)

---

### Stage 4: Embedding Generation (Ticket 3.4)
**Consumer:** `embedding_consumer.py`
**Input:** `data/locations/locations_batch_*.json` (location-enriched from Stage 3)
**Output:** `data/embeddings/embeddings_batch_*.json`

**What it does:**
- Creates rich text representations combining:
  - Original text content
  - Extracted diseases and symptoms
  - Location information (neighborhood, borough)
  - Severity level
- Generates 384-dimensional vector embeddings using sentence-transformers
- Outputs vector DB-ready format for Pinecone, Weaviate, ChromaDB, etc.

**Output format:**
- `id` (unique identifier)
- `vector` (384-dim embedding array)
- `text` (rich text used for embedding)
- `metadata` (diseases, symptoms, location, severity, confidence, etc.)
- `original_record` (complete original record)
- `embedding_model` (all-MiniLM-L6-v2)
- `embedding_dim` (384)
- `created_at` (timestamp)

---

## Usage

### Option 1: Run Full Chained Pipeline

Run all four stages sequentially:

```bash
cd src
python run_chained_pipeline.py
```

This will:
1. Read from Kafka → Relevance analysis
2. Read relevance output → Deduplication
3. Read unique records → Location extraction
4. Read location-enriched records → Embedding generation

### Option 2: Run Individual Consumers

#### Relevance Consumer (Kafka → Files)
```bash
python run_relevance_consumer.py
```

#### Deduplication Consumer (Files → Files)
```bash
python run_deduplication_consumer.py \
  --input-source file \
  --input-path data/relevance/relevant/
```

#### Location Consumer (Files → Files)
```bash
python run_location_consumer.py \
  --input-source file \
  --input-path "data/deduplicated/unique_*.json"
```

#### Embedding Consumer (Files → Files)
```bash
python run_embedding_consumer.py \
  --input-source file \
  --input-path data/locations/
```

### Option 3: Skip Certain Stages

```bash
# Skip relevance (use existing data)
python run_chained_pipeline.py --skip-relevance

# Only run location extraction and embeddings
python run_chained_pipeline.py --skip-relevance --skip-dedupe

# Only run embeddings
python run_chained_pipeline.py --skip-relevance --skip-dedupe --skip-location
```

---

## Configuration

### Kafka Mode vs File Mode

Each consumer (3.2 and 3.3) supports two input modes:

**Kafka Mode (default for 3.1):**
```bash
python run_deduplication_consumer.py \
  --input-source kafka \
  --topics reddit,bluesky,rss
```

**File Mode (for chaining):**
```bash
python run_deduplication_consumer.py \
  --input-source file \
  --input-path data/relevance/relevant/
```

### Tuning Parameters

**Deduplication Thresholds:**
```bash
python run_deduplication_consumer.py \
  --similarity-threshold 0.85 \  # Semantic similarity (0-1)
  --fuzzy-threshold 0.90         # TF-IDF fuzzy matching (0-1)
```

**spaCy Model (Location Extraction):**
```bash
python run_location_consumer.py \
  --spacy-model en_core_web_md  # More accurate (larger model)
```

**Embedding Model (Embedding Generation):**
```bash
python run_embedding_consumer.py \
  --embedding-model all-MiniLM-L6-v2 \  # Fast, 384-dim (default)
  --embedding-dim 384

# Or use a larger model:
python run_embedding_consumer.py \
  --embedding-model all-mpnet-base-v2 \  # More accurate, 768-dim
  --embedding-dim 768
```

---

## Data Flow Example

### Input (Kafka Message):
```json
{
  "post_id": "abc123",
  "source": "reddit",
  "text": "Flu outbreak in Williamsburg. Multiple people sick this week.",
  "timestamp": "2025-12-11T10:00:00"
}
```

### After Stage 1 (Relevance):
```json
{
  "post_id": "abc123",
  "source": "reddit",
  "text": "Flu outbreak in Williamsburg...",
  "is_relevant": true,
  "diseases_json": "[\"influenza\", \"flu\"]",
  "symptoms_json": "[\"sick\"]",
  "severity": "medium",
  "confidence": 0.92
}
```

### After Stage 2 (Deduplication):
```json
{
  "post_id": "abc123",
  "source": "reddit",
  "text": "Flu outbreak in Williamsburg...",
  "is_relevant": true,
  "diseases_json": "[\"influenza\", \"flu\"]",
  "is_duplicate": false,
  "dedup_tier": "unique",
  "similarity_score": 0.0
}
```

### After Stage 3 (Location):
```json
{
  "post_id": "abc123",
  "source": "reddit",
  "text": "Flu outbreak in Williamsburg...",
  "is_relevant": true,
  "diseases_json": "[\"influenza\", \"flu\"]",
  "is_duplicate": false,
  "dedup_tier": "unique",
  "location_extraction": {
    "extracted_locations": ["Williamsburg"],
    "normalized_locations": ["Williamsburg"],
    "neighborhood": "Williamsburg",
    "borough": "Brooklyn",
    "location_source": "text_extraction"
  }
}
```

### After Stage 4 (Embeddings):
```json
{
  "id": "abc123",
  "vector": [0.100, -0.080, 0.097, ..., 0.042],
  "text": "Flu outbreak in Williamsburg. Multiple people sick this week. Diseases: influenza, flu. Location: Williamsburg, Brooklyn. Severity: medium",
  "metadata": {
    "source": "reddit",
    "timestamp": "2025-12-11T10:00:00",
    "diseases": ["influenza", "flu"],
    "symptoms": ["sick"],
    "severity": "medium",
    "confidence": 0.92,
    "neighborhood": "Williamsburg",
    "borough": "Brooklyn",
    "location_source": "text_extraction",
    "is_duplicate": false,
    "dedup_tier": "unique"
  },
  "original_record": { ... },
  "embedding_model": "all-MiniLM-L6-v2",
  "embedding_dim": 384,
  "created_at": "2025-12-12T00:13:45.858380"
}
```

---

## Output Directory Structure

```
data/
├── relevance/
│   ├── relevant/                    # Relevant records → sent to Stage 2
│   └── irrelevant/                  # Filtered out (not disease-related)
├── deduplicated/
│   ├── unique_batch_*.json          # Unique records → sent to Stage 3
│   └── duplicates_batch_*.json      # Duplicates (for audit)
├── locations/
│   └── locations_batch_*.json       # Location-enriched → sent to Stage 4
└── embeddings/
    ├── embeddings_batch_*.json      # Vector DB-ready embeddings (FINAL OUTPUT)
    └── embedding_summary_batch_*.json  # Summary statistics
```

---

## Performance

### Throughput Estimates

| Stage | Mode | Records/sec | Bottleneck |
|-------|------|-------------|------------|
| 1. Relevance | Streaming | 50-100 | Keyword matching |
| 2. Dedupe | Batch | 10-50 | Semantic embeddings |
| 3. Location | Batch | 5-20 | spaCy NER |
| 4. Embeddings | Batch | 20-40 | Sentence transformers |

**Full Pipeline:** ~5-20 records/sec (limited by slowest stage: Location)

### Optimization Tips

1. **Use smaller models:**
   - Dedup: Keep `all-MiniLM-L6-v2` (fast)
   - Location: Use `en_core_web_sm` (not md/lg)
   - Embeddings: Use `all-MiniLM-L6-v2` (384-dim, fast) instead of mpnet-base-v2 (768-dim, slow)

2. **Increase Spark resources:**
   ```bash
   --conf spark.driver.memory=8g
   --conf spark.executor.memory=8g
   ```

3. **Process only unique data:**
   - Chain stages so duplicates/irrelevant records are filtered early

---

## Prerequisites

### 1. Kafka Running
```bash
docker-compose up -d kafka
```

### 2. Python Dependencies
```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

### 3. Data Available
For file mode, ensure previous stage completed:
```bash
ls data/relevance/relevant/  # For Stage 2
ls data/deduplicated/        # For Stage 3
```

---

## Troubleshooting

### "No files found" Error

**Stage 2 (Dedupe):**
```bash
# Verify relevance data exists
ls data/relevance/relevant/

# If empty, run Stage 1 first
python run_relevance_consumer.py
```

**Stage 3 (Location):**
```bash
# Verify dedupe data exists
ls data/deduplicated/unique_*.json

# If empty, run Stage 2 first
python run_deduplication_consumer.py --input-source file --input-path data/relevance/relevant/
```

### Java Security Manager Error

Already fixed in code with:
```python
.config("spark.driver.extraJavaOptions", "-Djava.security.manager.allow=true")
```

### spaCy Model Not Found

```bash
python -m spacy download en_core_web_sm
```

---

## Testing the Pipeline

### 1. Test with Sample Data

```bash
# Run full pipeline with existing Kafka data
python run_chained_pipeline.py
```

### 2. Test Individual Stages

```bash
# Stage 1
python run_relevance_consumer.py

# Wait for data, then test Stage 2
python run_deduplication_consumer.py --input-source file --input-path data/relevance/relevant/

# Test Stage 3
python run_location_consumer.py --input-source file --input-path "data/deduplicated/unique_*.json"
```

### 3. Verify Output

```bash
# Check relevance output
ls -lh data/relevance/relevant/
cat data/relevance/relevant/*.json | python -m json.tool | head -50

# Check dedupe output
ls -lh data/deduplicated/unique_*.json
cat data/deduplicated/unique_*.json | python -m json.tool | head -50

# Check location output
ls -lh data/locations/
cat data/locations/*.json | python -m json.tool | head -50

# Check embeddings output
ls -lh data/embeddings/
cat data/embeddings/embedding_summary_*.json | python -m json.tool
```

---

## Architecture Diagram

```
┌─────────────┐
│   Kafka     │  reddit, bluesky, rss, nyc_311, nyc_press, nyc_covid
└──────┬──────┘
       │
       ▼
┌─────────────────────────┐
│ Stage 1: Relevance      │  Filter + Extract health entities
│ Input: Kafka stream     │
│ Output: Files           │  ✓ is_relevant, diseases, symptoms
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────────┐
│ Stage 2: Deduplication  │  3-Tier deduplication
│ Input: Files            │
│ Output: Files           │  ✓ is_duplicate, dedup_tier
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────────┐
│ Stage 3: Location       │  NER + Neighborhood mapping
│ Input: Files            │
│ Output: Files           │  ✓ location_extraction
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────────┐
│ Stage 4: Embeddings     │  Generate vector embeddings
│ Input: Files            │
│ Output: Files           │  ✓ vector, metadata (384-dim)
└──────┬──────────────────┘
       │
       ▼
┌─────────────────────────┐
│ Vector Database         │  Pinecone, Weaviate, ChromaDB, etc.
│ data/embeddings/        │  Ready for semantic search & analysis
└─────────────────────────┘
```

---

## Next Steps

The pipeline output (`data/embeddings/`) can now be used for:
- **Vector Database Integration:** Import embeddings into Pinecone, Weaviate, ChromaDB, etc.
- **Semantic Search:** Query disease outbreaks by symptoms, location, or natural language
- **Downstream Analysis:** Visualization dashboards and reporting
- **Disease Hotspot Detection:** Cluster analysis and geographic heatmaps
- **Temporal Trend Analysis:** Track disease spread over time
- **Similarity Detection:** Find similar outbreak patterns across neighborhoods
