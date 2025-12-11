# Spark Streaming Deduplication Consumer

**Ticket 3.2**: LLM/NLP-based deduplication filter for NYC Disease Surveillance

## Overview

A Spark Streaming consumer that reads health data from multiple Kafka topics and applies intelligent deduplication using a 3-tier strategy combining hash-based, fuzzy matching, and semantic similarity approaches.

## Architecture

```
Kafka Topics → Spark Streaming → 3-Tier Deduplication → Output Directory
```

### 3-Tier Deduplication Strategy

1. **Tier 1: Exact Hash Match (Fast)**
   - Uses SHA-256 hashing for exact duplicate detection
   - ~0ms per record
   - Catches identical posts

2. **Tier 2: Fuzzy Matching (Medium)**
   - TF-IDF based similarity (scikit-learn)
   - ~1-5ms per record
   - Catches near-duplicates with minor text variations
   - Default threshold: 90% similarity

3. **Tier 3: Semantic Similarity (Accurate)**
   - Sentence embeddings using `all-MiniLM-L6-v2` model
   - ~50-200ms per record (batching helps)
   - Catches semantically similar posts (e.g., "flu in Brooklyn" vs "Brooklyn flu outbreak")
   - Default threshold: 85% similarity

## Features

- ✅ **Multi-source deduplication** - Works across Reddit, Bluesky, RSS, 311, etc.
- ✅ **Real-time processing** - Spark Streaming with micro-batches
- ✅ **Local ML model** - No API costs, runs entirely on your infrastructure
- ✅ **Deployment ready** - Works on local, cloud, or Docker
- ✅ **Configurable thresholds** - Tune similarity thresholds via CLI or env vars
- ✅ **Memory efficient** - Limited caches prevent memory issues
- ✅ **Audit trail** - Saves both unique and duplicate records

## Installation

### Prerequisites

- Python 3.11+
- Apache Kafka running (via Docker Compose)
- Virtual environment activated

### Install Dependencies

```bash
pip install -r requirements.txt
```

This will install:
- `pyspark` - Spark Streaming framework
- `sentence-transformers` - Embedding models
- `scikit-learn` - TF-IDF and cosine similarity
- `numpy` - Numerical operations

## Configuration

### Environment Variables

Add to your `.env` file:

```env
# Deduplication Consumer Settings
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_TOPICS=reddit,bluesky,rss,nyc_311,nyc_press,nyc_covid

# Output Settings
DEDUP_OUTPUT_DIR=data/deduplicated
DEDUP_CHECKPOINT_DIR=checkpoints/deduplication

# Thresholds
SIMILARITY_THRESHOLD=0.85  # Semantic similarity (0-1)
FUZZY_THRESHOLD=0.90       # Fuzzy matching (0-1)

# Model Settings
EMBEDDING_MODEL=all-MiniLM-L6-v2
MAX_TEXT_CACHE=1000
MAX_EMBEDDING_CACHE=500
```

## Usage

### Basic Usage

```bash
python run_deduplication_consumer.py
```

### Custom Topics

```bash
python run_deduplication_consumer.py --topics reddit,bluesky
```

### Adjust Thresholds

```bash
# More aggressive deduplication (lower threshold = more duplicates detected)
python run_deduplication_consumer.py --similarity-threshold 0.80

# Less aggressive (higher threshold = fewer duplicates detected)
python run_deduplication_consumer.py --similarity-threshold 0.90
```

### All Options

```bash
python run_deduplication_consumer.py \
  --kafka-servers localhost:9092 \
  --topics reddit,bluesky,rss \
  --output-dir data/deduplicated \
  --checkpoint-dir checkpoints/dedup \
  --similarity-threshold 0.85 \
  --fuzzy-threshold 0.90
```

## Output Format

The consumer writes two types of files:

### 1. Unique Records

File: `data/deduplicated/unique_batch_<id>_<timestamp>.json`

```json
[
  {
    "post_id": "abc123",
    "source": "reddit",
    "text": "Feeling sick with flu in Brooklyn...",
    "timestamp": "2025-12-04T12:00:00",
    "is_duplicate": false,
    "dedup_tier": "unique",
    "similarity_score": 0.0,
    "batch_id": 1,
    "processed_at": "2025-12-04T12:05:00"
  }
]
```

### 2. Duplicate Records (Audit Trail)

File: `data/deduplicated/duplicates_batch_<id>_<timestamp>.json`

```json
[
  {
    "post_id": "xyz789",
    "source": "bluesky",
    "text": "Brooklyn flu outbreak reported...",
    "timestamp": "2025-12-04T12:01:00",
    "is_duplicate": true,
    "dedup_tier": "semantic_embedding",
    "similarity_score": 0.87,
    "batch_id": 1,
    "processed_at": "2025-12-04T12:05:00"
  }
]
```

### Deduplication Tiers

- `exact_hash` - Exact duplicate (Tier 1)
- `fuzzy_tfidf` - Fuzzy match (Tier 2)
- `semantic_embedding` - Semantic similarity (Tier 3)
- `unique` - Not a duplicate
- `skipped` - Text too short or empty

## How It Works

### Data Flow

1. **Consume from Kafka**
   - Reads from multiple topics (reddit, bluesky, rss, etc.)
   - Processes in micro-batches

2. **Extract Text**
   - Normalizes different data schemas
   - Extracts text from various fields (text, description, title, etc.)

3. **Apply 3-Tier Deduplication**
   ```python
   # Tier 1: Hash check (instant)
   if hash(text) in seen_hashes:
       return "duplicate"

   # Tier 2: TF-IDF similarity
   if tfidf_similarity(text, recent_texts) > 0.90:
       return "duplicate"

   # Tier 3: Semantic embeddings
   if cosine_similarity(embedding, recent_embeddings) > 0.85:
       return "duplicate"

   return "unique"
   ```

4. **Write Results**
   - Unique records → Main output
   - Duplicates → Audit trail

### Example Deduplication Cases

**Exact Match (Tier 1):**
```
Post 1: "Flu outbreak in Brooklyn"
Post 2: "Flu outbreak in Brooklyn"
Result: Duplicate (100% match)
```

**Fuzzy Match (Tier 2):**
```
Post 1: "Flu outbreak in Brooklyn"
Post 2: "Flu outbreak in Brooklyn!"
Result: Duplicate (99% TF-IDF similarity)
```

**Semantic Match (Tier 3):**
```
Post 1: "Flu outbreak in Brooklyn"
Post 2: "Brooklyn experiencing influenza cases"
Result: Duplicate (87% semantic similarity)
```

## Performance

### Speed

- **Tier 1 (Hash)**: ~0.001ms per record
- **Tier 2 (TF-IDF)**: ~5ms per record
- **Tier 3 (Embeddings)**: ~100ms per record
- **Overall**: ~10-50 records/second (depends on cache hits)

### Memory Usage

- **Base**: ~512MB (embedding model)
- **Per batch**: ~50-100MB (caches)
- **Total**: ~1GB recommended

### Scalability

- Works on single machine or Spark cluster
- Can process 100K+ records/day on modest hardware
- Cache limits prevent memory issues

## Troubleshooting

### Issue: "Connection refused to Kafka"

**Solution:**
```bash
# Check if Kafka is running
docker ps | grep kafka

# Start Kafka if needed
docker compose up -d kafka
```

### Issue: "Model download failed"

**Solution:**
```bash
# Pre-download the model
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

### Issue: "Out of memory"

**Solution:**
- Reduce cache sizes in config
- Increase heap size: `export SPARK_DRIVER_MEMORY=2g`
- Process smaller batches

### Issue: "Too many/few duplicates detected"

**Solution:**
- Adjust thresholds:
  - Lower threshold (0.75-0.80) = more aggressive deduplication
  - Higher threshold (0.90-0.95) = less aggressive deduplication

## Monitoring

### Check Output

```bash
# View unique records
ls -lh data/deduplicated/unique_*

# Count unique records
cat data/deduplicated/unique_* | python -m json.tool | grep -c "post_id"

# View duplicate stats
cat data/deduplicated/duplicates_* | python -m json.tool | grep "dedup_tier"
```

### Logs

The consumer logs:
- Records processed per batch
- Unique vs duplicate counts
- Deduplication tier statistics

## Integration

### Next Steps (Downstream Processing)

The deduplicated data can be:
1. **Loaded into HDFS** for big data processing
2. **Inserted into PostgreSQL/TimescaleDB** for time-series analysis
3. **Indexed in ChromaDB** for vector search
4. **Fed to LLM** for symptom extraction (Layer 3)

### Example: Load to HDFS

```bash
# Copy deduplicated files to HDFS
hdfs dfs -put data/deduplicated/unique_* /disease_surveillance/deduplicated/
```

## Deployment

### Docker Deployment

Add to `docker-compose.yml`:

```yaml
dedup-consumer:
  build: .
  command: python run_deduplication_consumer.py
  environment:
    - KAFKA_BOOTSTRAP_SERVERS=kafka:29092
  depends_on:
    - kafka
  volumes:
    - ./data:/app/data
```

### Cloud Deployment

Works on:
- AWS EC2 with Kafka (MSK)
- GCP Compute Engine with Kafka
- Azure VMs with Kafka

## Testing

### Test with Sample Data

```bash
# Publish test data to Kafka
python -c "
from kafka import KafkaProducer
import json

producer = KafkaProducer(
    bootstrap_servers='localhost:9092',
    value_serializer=lambda v: json.dumps(v).encode('utf-8')
)

# Test post
post = {
    'post_id': 'test_001',
    'source': 'test',
    'text': 'Feeling sick with flu in Brooklyn',
    'timestamp': '2025-12-04T12:00:00'
}

producer.send('reddit', post)
producer.flush()
print('Test post sent')
"

# Run consumer
python run_deduplication_consumer.py --topics reddit
```

## Architecture Diagram

```
┌─────────────────────────────────────────────────┐
│           Kafka Topics                          │
│  (reddit, bluesky, rss, 311, press, covid)     │
└────────────────┬────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────┐
│      Spark Streaming Consumer                   │
│                                                  │
│  ┌──────────────────────────────────────────┐  │
│  │  Tier 1: Hash Deduplication              │  │
│  │  (SHA-256, instant)                      │  │
│  └──────────────┬───────────────────────────┘  │
│                 │ Not duplicate                 │
│                 ▼                                │
│  ┌──────────────────────────────────────────┐  │
│  │  Tier 2: Fuzzy Matching                  │  │
│  │  (TF-IDF, ~5ms)                          │  │
│  └──────────────┬───────────────────────────┘  │
│                 │ Not duplicate                 │
│                 ▼                                │
│  ┌──────────────────────────────────────────┐  │
│  │  Tier 3: Semantic Similarity             │  │
│  │  (Embeddings, ~100ms)                    │  │
│  └──────────────┬───────────────────────────┘  │
└─────────────────┼────────────────────────────────┘
                  │
          ┌───────┴───────┐
          │               │
          ▼               ▼
     Unique Records   Duplicate Records
     (main output)    (audit trail)
```

## Support

For issues or questions:
1. Check logs in console output
2. Verify Kafka is running
3. Check output directory permissions
4. Review similarity thresholds

---

**Implementation Status**: ✅ Complete
**Author**: Steven Granaturov (sg8002)
**Date**: December 2025
**Ticket**: 3.2 - Spark Streaming Deduplication Consumer
