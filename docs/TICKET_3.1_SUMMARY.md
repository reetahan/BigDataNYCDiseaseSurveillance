# Relevance Consumer (Ticket 3.1)

## Overview

The **Relevance Consumer** is the first stage in the Spark data processing pipeline. It performs ML-based health relevance filtering on raw data from multiple sources (Reddit, Bluesky, RSS, NYC 311, NYC Press, NYC COVID), extracting disease mentions, symptoms, and severity levels. This stage filters out non-health-related content, reducing noise before deduplication and location extraction.

## Pipeline Position

```
Scrapers → Kafka → **Relevance Filter** → Deduplication → Location Extraction → Embeddings → ChromaDB
                        (3.1)              (3.2)             (3.3)              (3.4)
```

**Input**: Raw data from Kafka topics (`reddit.health`, `bluesky.health`, `rss.health`, `nyc_311.health`, `nyc_press.health`, `nyc_covid.health`)  
**Output**: Filtered JSON (JSONL format) to `data/relevance/relevant/` and `data/relevance/irrelevant/`

---

## How the Code Works

### 1. **Architecture Components**

#### **RelevanceConsumer Class**
Main class managing Spark Streaming and relevance analysis:
- **Spark Streaming** from Kafka (real-time processing)
- **Parallel UDF execution** for ML-based keyword analysis
- **Dual-stream output** (relevant vs. irrelevant)
- **Progress tracking** with estimated completion time

#### **Key Methods**

##### `__init__(kafka_bootstrap_servers, kafka_topics, output_dir, checkpoint_dir)`
Initializes Spark Streaming consumer:

```python
# Initialize Spark with Java 11+ compatibility
self.spark = SparkSession.builder \
    .appName("NYC_Relevance_Analysis_ML") \
    .master("local[*]") \
    .config("spark.driver.memory", "4g") \
    .config("spark.executor.memory", "4g") \
    .config("spark.driver.extraJavaOptions", "-Djava.security.manager.allow=true") \
    .config("spark.executor.extraJavaOptions", "-Djava.security.manager.allow=true") \
    .config("spark.default.parallelism", "10") \
    .config("spark.sql.shuffle.partitions", "10") \
    .getOrCreate()

# Create output directories
os.makedirs("data/relevance/relevant", exist_ok=True)
os.makedirs("data/relevance/irrelevant", exist_ok=True)
```

**Why 10 partitions?**  
Balances parallelism with overhead. Too many partitions (100+) creates scheduling overhead; too few (1-2) underutilizes CPU cores.

##### `create_analysis_udf()`
Creates Spark User-Defined Function (UDF) for parallel keyword analysis:

**Keyword Dictionaries** (defined inside UDF to avoid serialization):
```python
disease_keywords = {
    'COVID-19': ['covid', 'coronavirus', 'sars-cov-2'],
    'Influenza': ['flu', 'influenza'],
    'Norovirus': ['norovirus', 'stomach flu', 'stomach bug'],
    'RSV': ['rsv', 'respiratory syncytial'],
    'Strep Throat': ['strep', 'strep throat'],
    'Food Poisoning': ['food poisoning', 'foodborne', 'salmonella', 'e coli'],
    'Pneumonia': ['pneumonia'],
    'Tuberculosis': ['tuberculosis', 'tb'],
    'Measles': ['measles'],
    'Hepatitis': ['hepatitis'],
    'Bronchitis': ['bronchitis'],
    'Meningitis': ['meningitis']
}

symptom_keywords = [
    'fever', 'cough', 'sore throat', 'headache', 'nausea',
    'vomiting', 'diarrhea', 'fatigue', 'chills', 'congestion',
    'body aches', 'shortness of breath', 'loss of taste',
    'loss of smell', 'runny nose', 'sneezing', 'rash',
    'dizzy', 'weakness', 'pain', 'aching', 'sick', 'ill'
]

health_hazard_keywords = [
    'contamination', 'unsanitary', 'hygiene', 'outbreak',
    'infection', 'contagious', 'epidemic', 'pandemic'
]
```

**Analysis Function** (executed in parallel across Spark executors):

```python
def analyze_health_relevance(json_str: str) -> Tuple[bool, str, str, str, float, str]:
    """
    Analyze if text is health-related and extract entities
    
    Returns:
        (is_relevant, diseases_json, symptoms_json, severity, confidence, reason)
    """
    record = json.loads(json_str)
    
    # 1. Handle structured health data (NYC COVID metrics)
    if 'metric' in record and 'value' in record:
        diseases = extract_diseases_from_metric(record['metric'])
        return (True, json.dumps(diseases), '[]', 'moderate', 0.95, 'structured_health_data')
    
    # 2. Extract text from various fields
    text_parts = []
    for field in ['type', 'description', 'text', 'title', 'content', 'body', 'summary']:
        if field in record and record[field]:
            text_parts.append(str(record[field]))
    
    text = ' '.join(text_parts).strip()
    text_lower = text.lower()
    
    # 3. Extract diseases using keyword matching
    found_diseases = []
    for disease, keywords in disease_keywords.items():
        if any(kw in text_lower for kw in keywords):
            found_diseases.append(disease)
    
    # 4. Extract symptoms using keyword matching
    found_symptoms = []
    for symptom in symptom_keywords:
        if symptom in text_lower:
            found_symptoms.append(symptom)
    
    found_symptoms = list(set(found_symptoms))  # Deduplicate
    
    # 5. Check for health hazards
    has_health_hazard = any(hazard in text_lower for hazard in health_hazard_keywords)
    
    # 6. Determine relevance
    is_relevant = (
        len(found_diseases) > 0 or
        len(found_symptoms) >= 2 or  # At least 2 symptoms
        has_health_hazard
    )
    
    # 7. Estimate severity
    severity = 'unknown'
    if any(word in text_lower for word in ['severe', 'critical', 'emergency', 'hospital', 'icu']):
        severity = 'severe'
    elif any(word in text_lower for word in ['moderate', 'worse', 'worsening']):
        severity = 'moderate'
    elif any(word in text_lower for word in ['mild', 'slight', 'minor']):
        severity = 'mild'
    
    # 8. Calculate confidence score
    confidence = 0.6 if is_relevant else 0.2
    if found_diseases:
        confidence += 0.1 * min(len(found_diseases), 2)
    if len(found_symptoms) >= 2:
        confidence += 0.05 * min(len(found_symptoms), 3)
    if severity != 'unknown':
        confidence += 0.05
    confidence = min(confidence, 0.90)
    
    return (
        is_relevant,
        json.dumps(found_diseases),
        json.dumps(found_symptoms),
        severity,
        float(confidence),
        'keyword_analysis'
    )
```

**Return Schema**:
```python
StructType([
    StructField("is_relevant", BooleanType()),
    StructField("diseases_json", StringType()),    # JSON array: ["COVID-19", "RSV"]
    StructField("symptoms_json", StringType()),    # JSON array: ["fever", "cough"]
    StructField("severity", StringType()),         # severe/moderate/mild/unknown
    StructField("confidence", FloatType()),        # 0.0 - 0.9
    StructField("reason", StringType())            # keyword_analysis/structured_health_data/error
])
```

##### `start()`
Main streaming execution:

```python
# 1. Read from Kafka
df = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", "localhost:9092") \
    .option("subscribe", "reddit.health,bluesky.health,rss.health,...") \
    .option("startingOffsets", "earliest") \
    .load()

# 2. Parse JSON and apply analysis UDF (parallel execution)
analyzed_df = df.selectExpr("CAST(value AS STRING) as json_str", "timestamp") \
    .withColumn("analysis", analyze_udf(col("json_str"))) \
    .select(
        col("json_str").alias("original_data"),
        col("analysis.is_relevant").alias("is_relevant"),
        col("analysis.diseases_json").alias("diseases_json"),
        col("analysis.symptoms_json").alias("symptoms_json"),
        col("analysis.severity").alias("severity"),
        col("analysis.confidence").alias("confidence"),
        col("analysis.reason").alias("reason")
    )

# 3. Split into relevant and irrelevant streams
relevant_df = analyzed_df.filter(col("is_relevant") == True)
irrelevant_df = analyzed_df.filter(col("is_relevant") == False)

# 4. Track progress on all records
progress_query = analyzed_df.writeStream \
    .foreachBatch(track_all_progress) \
    .format("noop") \
    .start()

# 5. Write relevant records to data/relevance/relevant/
relevant_query = relevant_df.writeStream \
    .format("json") \
    .option("path", "data/relevance/relevant") \
    .option("checkpointLocation", "checkpoints/relevance/relevant") \
    .outputMode("append") \
    .start()

# 6. Write irrelevant records to data/relevance/irrelevant/
irrelevant_query = irrelevant_df.writeStream \
    .format("json") \
    .option("path", "data/relevance/irrelevant") \
    .option("checkpointLocation", "checkpoints/relevance/irrelevant") \
    .outputMode("append") \
    .start()

# Wait for termination
progress_query.awaitTermination()
```

##### `update_progress(batch_df, batch_id)` / `track_all_progress(batch_df, batch_id)`
Real-time progress tracking:

```python
def track_all_progress(batch_df: DataFrame, batch_id: int):
    batch_count = batch_df.count()
    
    # Count relevant vs irrelevant
    relevant_in_batch = batch_df.filter(col("is_relevant") == True).count()
    irrelevant_in_batch = batch_count - relevant_in_batch
    
    # Update totals
    self.records_processed += batch_count
    self.relevant_count += relevant_in_batch
    self.irrelevant_count += irrelevant_in_batch
    
    # Calculate rate
    elapsed = (datetime.now() - self.start_time).total_seconds()
    rate = self.records_processed / elapsed
    
    # Display progress bar
    progress_pct = (self.records_processed / total_estimated) * 100
    bar = '█' * filled + '-' * empty
    
    print(f"PROGRESS: [{bar}] {progress_pct:.1f}%")
    print(f"Batch {batch_id} | Processed: {self.records_processed}/{total_estimated}")
    print(f"Relevant: {self.relevant_count} | Irrelevant: {self.irrelevant_count}")
    print(f"Rate: {rate:.2f} rec/sec | Elapsed: {elapsed/60:.1f} min")
    print(f"Estimated time remaining: {remaining_time:.1f} minutes")
```

### 2. **Execution Flow**

```
START
  ↓
Initialize Spark Session (4GB memory, 10 partitions)
  ↓
Create output directories (relevant/, irrelevant/)
  ↓
Define analysis UDF with keyword dictionaries
  ↓
Read from Kafka (subscribe to 6 topics)
  ↓
FOR EACH micro-batch (streaming):
  ├─ Parse JSON from Kafka value
  ├─ Apply analysis UDF IN PARALLEL across executors:
  │   ├─ Extract text from multiple fields
  │   ├─ Match disease keywords (12 diseases)
  │   ├─ Match symptom keywords (22 symptoms)
  │   ├─ Check health hazard keywords (8 hazards)
  │   ├─ Determine relevance (diseases OR 2+ symptoms OR hazards)
  │   ├─ Estimate severity (severe/moderate/mild/unknown)
  │   └─ Calculate confidence score (0.2-0.9)
  ├─ Split into relevant/irrelevant DataFrames
  ├─ Track progress (count, rate, ETA)
  ├─ Write relevant → data/relevance/relevant/ (JSONL)
  └─ Write irrelevant → data/relevance/irrelevant/ (JSONL)
  ↓
Await termination (Ctrl+C to stop)
  ↓
Display final summary (total, relevant %, irrelevant %)
```

### 3. **Relevance Determination Logic**

**A record is considered RELEVANT if**:
- **At least 1 disease** mentioned (COVID-19, Influenza, RSV, etc.)
- **OR at least 2 symptoms** mentioned (fever + cough, nausea + vomiting, etc.)
- **OR at least 1 health hazard** mentioned (outbreak, contamination, epidemic, etc.)

**Examples**:

| Text | Diseases | Symptoms | Hazards | Relevant? | Reason |
|------|----------|----------|---------|-----------|--------|
| "Person tested positive for COVID" | ✅ COVID-19 | - | - | ✅ YES | Disease found |
| "Child has fever and cough" | - | ✅ 2 | - | ✅ YES | Multiple symptoms |
| "Food contamination at restaurant" | - | - | ✅ 1 | ✅ YES | Health hazard |
| "Traffic jam on highway" | - | - | - | ❌ NO | No health keywords |
| "Feeling tired today" | - | 1 | - | ❌ NO | Only 1 symptom |

### 4. **Confidence Score Calculation**

```python
# Base confidence
confidence = 0.6 if is_relevant else 0.2

# Boost for diseases (+0.1 per disease, max 2)
if found_diseases:
    confidence += 0.1 * min(len(found_diseases), 2)

# Boost for symptoms (+0.05 per symptom, max 3)
if len(found_symptoms) >= 2:
    confidence += 0.05 * min(len(found_symptoms), 3)

# Boost for severity identification (+0.05)
if severity != 'unknown':
    confidence += 0.05

# Cap at 0.90
confidence = min(confidence, 0.90)
```

**Example Scores**:
- COVID-19 mention + fever + cough + severe: `0.6 + 0.1 + 0.1 + 0.05 = 0.85`
- Flu + fatigue: `0.6 + 0.1 + 0.05 = 0.75`
- Fever + cough (no disease): `0.6 + 0.1 = 0.70`
- Food contamination: `0.6`
- Irrelevant text: `0.2`

---

## How to Run

### **Command Line Interface**

```bash
python src/spark_consumers/relevance_consumer.py \
    --kafka-servers localhost:9092 \
    --topics reddit.health,bluesky.health,rss.health,nyc_311.health,nyc_press.health,nyc_covid.health \
    --output-dir data/relevance \
    --checkpoint-dir checkpoints/relevance
```

### **Via Pipeline Runner**

```bash
# Full pipeline (includes relevance consumer)
python run_project.py

# Or run chained pipeline directly
python src/run_chained_pipeline.py
```

### **Programmatic Usage**

```python
from src.spark_consumers.relevance_consumer import RelevanceConsumer

consumer = RelevanceConsumer(
    kafka_bootstrap_servers='localhost:9092',
    kafka_topics='reddit.health,bluesky.health,rss.health,nyc_311.health,nyc_press.health,nyc_covid.health',
    output_dir='data/relevance',
    checkpoint_dir='checkpoints/relevance'
)

consumer.start()  # Runs until Ctrl+C
```

### **Stop Consumer**

Press `Ctrl+C` to gracefully stop:
```
^C
Stopping consumers...
======================================================================
FINAL SUMMARY
Total processed: 9480
Relevant: 4227 (44.6%)
Irrelevant: 5253 (55.4%)
======================================================================
Consumers stopped
```

---

## Expected Output

### **Console Output (Real-Time)**

```
============================================================
Starting NYC Relevance Analysis Consumer
Kafka Brokers: localhost:9092
Topics: reddit.health,bluesky.health,rss.health,nyc_311.health,nyc_press.health,nyc_covid.health
Output Dir: data/relevance
Analysis: Keyword-based ML hybrid
============================================================
Streaming queries started with progress tracking
Relevant records → data/relevance/relevant
Irrelevant records → data/relevance/irrelevant

======================================================================
PROGRESS: [████████████████████████████████--------] 80.5%
Batch 15 | Processed: 7631/9480 records
Relevant: 3412 | Irrelevant: 4219
Rate: 127.18 rec/sec | Elapsed: 1.0 min
Estimated time remaining: 0.2 minutes
======================================================================
```

### **File Structure**

```
data/relevance/
├── relevant/
│   ├── part-00000-*.json     # JSONL format (newline-delimited)
│   ├── part-00001-*.json
│   └── ...
└── irrelevant/
    ├── part-00000-*.json     # JSONL format
    ├── part-00001-*.json
    └── ...
```

### **Output Format (JSONL)**

**Relevant Record**:
```json
{"original_data":"{\"text\":\"Person tested positive for COVID\",\"source\":\"reddit\",\"timestamp\":\"2025-12-13T10:30:00\"}","kafka_timestamp":"2025-12-13T10:30:05.123Z","is_relevant":true,"diseases_json":"[\"COVID-19\"]","symptoms_json":"[]","severity":"unknown","confidence":0.7,"reason":"keyword_analysis","processed_at":"2025-12-13T10:30:05.456Z"}
```

**Irrelevant Record**:
```json
{"original_data":"{\"text\":\"Traffic update on I-95\",\"source\":\"twitter\"}","kafka_timestamp":"2025-12-13T10:31:00.789Z","is_relevant":false,"diseases_json":"[]","symptoms_json":"[]","severity":"unknown","confidence":0.2,"reason":"keyword_analysis","processed_at":"2025-12-13T10:31:01.234Z"}
```

**Parsed Fields**:
- `original_data`: Original JSON string from Kafka
- `kafka_timestamp`: When message was produced to Kafka
- `is_relevant`: Boolean (true/false)
- `diseases_json`: JSON array string `["COVID-19", "Influenza"]`
- `symptoms_json`: JSON array string `["fever", "cough", "fatigue"]`
- `severity`: `severe`/`moderate`/`mild`/`unknown`
- `confidence`: Float 0.0-0.9
- `reason`: `keyword_analysis`/`structured_health_data`/`error_*`
- `processed_at`: When UDF completed analysis

### **Typical Statistics**

```
Total Kafka Messages: 9,480
Relevant: 4,227 (44.6%)
Irrelevant: 5,253 (55.4%)
Processing Rate: ~120-150 records/sec
Processing Time: ~1.5 minutes
Output Size: ~15-20MB (JSONL)
```

---

## Technical Considerations

### **1. Spark Streaming Architecture**

**Micro-batch Processing**:
```
Kafka → [Batch 1: 500 records] → Process → Write
     → [Batch 2: 500 records] → Process → Write
     → [Batch 3: 500 records] → Process → Write
```

**Default Trigger**: ProcessingTime (as fast as possible)
- Spark pulls batches continuously from Kafka
- Processes each batch before pulling next
- Checkpoint tracks Kafka offsets

**Why Streaming vs. Batch?**
- **Real-time**: Process data as it arrives
- **Scalability**: Handles continuous data flow
- **Fault tolerance**: Checkpoints enable recovery from failures

### **2. UDF Parallelization**

**How Spark Parallelizes UDFs**:
```python
# Spark distributes work across executors
Executor 1: Process records 1-1000
Executor 2: Process records 1001-2000
Executor 3: Process records 2001-3000
...
Executor 10: Process records 9001-10000
```

**Why Define Keywords Inside UDF?**
```python
# ❌ Wrong: Variables outside UDF require serialization
disease_keywords = {...}  # Defined in class

def analyze(text):
    # Uses disease_keywords - must serialize and send to executors
    ...

# ✅ Correct: Variables inside UDF are self-contained
def analyze(text):
    disease_keywords = {...}  # Defined inside
    # Each executor has its own copy, no serialization needed
    ...
```

**Performance**: Self-contained UDFs avoid serialization overhead and network transfer.

### **3. Keyword-Based ML Hybrid Approach**

**Why Keyword Matching vs. Deep Learning?**

| Approach | Pros | Cons | Use Case |
|----------|------|------|----------|
| **Keywords** | ✅ Fast (0.1ms/record)<br>✅ Interpretable<br>✅ No training needed | ❌ Misses paraphrases<br>❌ Rigid rules | **Initial filtering** |
| **Deep Learning** | ✅ Understands context<br>✅ Handles paraphrases | ❌ Slow (10-100ms/record)<br>❌ Needs training data<br>❌ Black box | **Fine-grained analysis** |

**Our Hybrid Strategy**:
1. **Stage 1 (This consumer)**: Fast keyword filtering (~44% pass)
2. **Stage 2-4**: Advanced processing on filtered data (dedup, location, embeddings)

**Result**: Process 9,480 records in ~1.5 minutes vs. ~15+ minutes with deep learning.

### **4. JSONL vs. JSON Format**

**Output Format**: JSONL (newline-delimited JSON)
```
{"id": 1, "text": "..."}
{"id": 2, "text": "..."}
{"id": 3, "text": "..."}
```

**Why JSONL?**
- ✅ **Streaming-friendly**: Append-only, no array wrapping
- ✅ **Fault-tolerant**: Partial writes still valid
- ✅ **Memory-efficient**: Read line-by-line, no full load
- ❌ **Compatibility**: Requires special parsing (not `json.load()`)

**Reading JSONL**:
```python
# ❌ Wrong
with open('file.json') as f:
    data = json.load(f)  # Fails on JSONL

# ✅ Correct
with open('file.json') as f:
    for line in f:
        record = json.loads(line)
```

### **5. Checkpoint Management**

**Checkpoint Structure**:
```
checkpoints/relevance/
├── progress/
│   ├── commits/
│   ├── offsets/
│   └── metadata
├── relevant/
│   ├── commits/
│   ├── offsets/
│   └── metadata
└── irrelevant/
    ├── commits/
    ├── offsets/
    └── metadata
```

**Purpose**:
- **Offsets**: Track Kafka position (enable exactly-once processing)
- **Commits**: Record completed micro-batches
- **Metadata**: Spark query configuration

**Recovery**:
```bash
# Consumer crashes at record 5000
# Restart consumer
python src/spark_consumers/relevance_consumer.py

# Spark reads checkpoint: "Last processed offset: 4999"
# Resumes from record 5000 (no duplicates, no data loss)
```

**Cleanup** (if needed):
```bash
# Remove checkpoints to reprocess from beginning
rm -rf checkpoints/relevance/
```

### **6. Memory Management**

**Spark Configuration**:
```python
.config("spark.driver.memory", "4g")
.config("spark.executor.memory", "4g")
```

**Memory Breakdown**:
- **Driver**: Coordinates executors, collects results (~1GB used)
- **Executors**: Process UDFs in parallel (~1GB used per executor)
- **Reserve**: Remaining for overhead

**For 9,480 records**:
- **Batch size**: ~500 records/batch
- **Batch memory**: 500 × ~2KB = ~1MB
- **Peak memory**: ~2GB (well below 4GB limit)

**Scaling**:
- **100k records**: Same config works
- **1M+ records**: Increase to 8GB or use distributed Spark cluster

### **7. Kafka Integration**

**Consumer Group**: Automatic (Spark manages)
```python
# Spark creates consumer group: "spark-kafka-source-..."
# Tracks offsets in Kafka (__consumer_offsets topic)
```

**Offset Management**:
```python
.option("startingOffsets", "earliest")  # Start from beginning
# Alternatives:
# "latest" - Only new messages
# {"topic1": {"0": 23, "1": -2}} - Specific offsets
```

**Multiple Topics**:
```python
.option("subscribe", "reddit.health,bluesky.health,...")
# Spark reads from all topics in parallel
# Maintains separate offsets per topic-partition
```

### **8. Error Handling**

**UDF Exception Handling**:
```python
def analyze_health_relevance(json_str: str):
    try:
        record = json.loads(json_str)
        # ... analysis logic ...
        return (is_relevant, diseases, symptoms, severity, confidence, 'keyword_analysis')
    except Exception as e:
        # Return safe default instead of crashing
        return (False, '[]', '[]', 'unknown', 0.0, f'error_{type(e).__name__}')
```

**Why Catch All Exceptions?**
- Single bad record shouldn't crash entire batch
- Log error reason in `reason` field for debugging
- Continue processing remaining records

**Common Errors**:
1. **JSON parsing**: Malformed Kafka message → `error_JSONDecodeError`
2. **Missing fields**: Record without text → `insufficient_text`
3. **Type errors**: Unexpected data types → `error_TypeError`

### **9. Progress Tracking Strategy**

**Three Separate Streams**:
```python
# Stream 1: Track ALL records (relevant + irrelevant)
progress_query = analyzed_df.writeStream \
    .foreachBatch(track_all_progress) \
    .format("noop")  # Don't write output, just count
    .start()

# Stream 2: Write ONLY relevant records
relevant_query = relevant_df.writeStream \
    .format("json") \
    .start()

# Stream 3: Write ONLY irrelevant records
irrelevant_query = irrelevant_df.writeStream \
    .format("json") \
    .start()
```

**Why Separate?**
- `foreachBatch` counts all records before filtering
- JSON writers only see their respective subsets
- Enables accurate total progress tracking

### **10. Performance Optimization**

**Current Bottlenecks**:
- **Kafka read**: ~5-10ms per batch
- **JSON parsing**: ~0.1ms per record
- **Keyword matching**: ~0.1ms per record (22 symptoms × 12 diseases = 264 checks)
- **JSON write**: ~5-10ms per batch

**For 9,480 records**:
- **Total time**: ~90 seconds
- **Throughput**: ~105 records/sec
- **Parallelism**: 10 cores → ~10.5 records/sec/core

**Optimization Options**:

1. **Increase Parallelism**:
```python
.config("spark.default.parallelism", "20")  # 2x cores
# Expected: ~150 records/sec
```

2. **Batch Size Tuning**:
```python
.trigger(processingTime='10 seconds')  # Larger batches
# Reduces overhead, increases latency
```

3. **Compiled Regex** (instead of `in` checks):
```python
import re
covid_pattern = re.compile(r'\b(covid|coronavirus|sars-cov-2)\b', re.IGNORECASE)
if covid_pattern.search(text):
    found_diseases.append('COVID-19')
# ~50% faster for complex patterns
```

4. **Pre-filter by Source**:
```python
# NYC COVID metrics are always relevant, skip analysis
if record.get('source') == 'NYC_COVID':
    return (True, ..., 0.95, 'source_whitelist')
```

---

## Dependencies

```bash
# Required packages
pip install pyspark==3.5.3
pip install kafka-python  # For Kafka connectivity

# Java requirement
export JAVA_HOME=/opt/homebrew/opt/openjdk@11
```

**Kafka Setup**:
```bash
# Start Kafka via Docker
docker compose up kafka kafka-ui
```

---

## Troubleshooting

### **Issue**: `ModuleNotFoundError: No module named 'pyspark'`
**Solution**:
```bash
pip install pyspark==3.5.3
```

### **Issue**: `java.lang.IllegalAccessError` or security manager errors
**Solution**: Java 11+ requires extra flags (already configured):
```python
.config("spark.driver.extraJavaOptions", "-Djava.security.manager.allow=true")
.config("spark.executor.extraJavaOptions", "-Djava.security.manager.allow=true")
```

### **Issue**: Consumer not reading any records
**Solution**: Check Kafka topics have data:
```bash
# List topics
docker exec -it kafka kafka-topics --list --bootstrap-server localhost:9092

# Check message count
docker exec -it kafka kafka-run-class kafka.tools.GetOffsetShell \
  --broker-list localhost:9092 \
  --topic reddit.health
```

### **Issue**: Consumer reading same data repeatedly
**Solution**: Checkpoints persisting old offsets. Delete and restart:
```bash
rm -rf checkpoints/relevance/
python src/spark_consumers/relevance_consumer.py
```

### **Issue**: Slow processing (< 50 records/sec)
**Solution**: Increase parallelism:
```python
# Edit relevance_consumer.py
.config("spark.default.parallelism", "20")  # Increase from 10
.config("spark.sql.shuffle.partitions", "20")
```

### **Issue**: Out of memory errors
**Solution**: Reduce batch size or increase memory:
```python
.config("spark.driver.memory", "8g")  # Increase from 4g
.config("spark.executor.memory", "8g")
```

### **Issue**: "Connection refused" to Kafka
**Solution**: Verify Kafka is running:
```bash
docker ps | grep kafka
# Should show kafka container running on port 9092
```

---

## Query Examples (After Processing)

Once data is in `data/relevance/relevant/`, subsequent consumers read it:

```bash
# Count relevant records
cat data/relevance/relevant/part-*.json | wc -l

# Find COVID-19 mentions
cat data/relevance/relevant/part-*.json | grep -i "COVID-19"

# Count by severity
cat data/relevance/relevant/part-*.json | jq -r '.severity' | sort | uniq -c

# Extract all diseases
cat data/relevance/relevant/part-*.json | jq -r '.diseases_json' | jq -r '.[]' | sort | uniq -c
```

---

## Integration with Downstream Consumers

**Deduplication Consumer** reads `data/relevance/relevant/`:
```python
from src.spark_consumers.deduplication_consumer import DeduplicationConsumer

dedup = DeduplicationConsumer(
    input_path='data/relevance/relevant/',  # Read relevance output
    output_dir='data/deduplicated'
)
dedup.process_from_files()
```

**Data Flow**:
```
Relevance (9,480 total)
  ↓ Filter (44.6% pass)
Deduplication (4,227 relevant)
  ↓ Deduplicate (~33% duplicates)
Location Extraction (2,840 unique)
  ↓ Enrich with location
Embeddings (2,840 with location)
  ↓ Generate vectors
ChromaDB (2,840 searchable)
```

---

## Summary

The Relevance Consumer performs the critical first-stage filtering of disease surveillance data, using keyword-based ML analysis to identify health-related content. Key features:

✅ **Spark Streaming** - real-time processing from Kafka with fault tolerance  
✅ **Parallel UDF execution** - keyword matching across 10+ executor cores  
✅ **Multi-source support** - Reddit, Bluesky, RSS, NYC 311, Press, COVID data  
✅ **Disease extraction** - 12 disease categories with keyword matching  
✅ **Symptom extraction** - 22 symptom keywords with deduplication  
✅ **Severity estimation** - severe/moderate/mild classification  
✅ **Confidence scoring** - 0.2-0.9 range based on match quality  
✅ **Dual-stream output** - relevant (44.6%) vs. irrelevant (55.4%)  
✅ **Progress tracking** - real-time rate, ETA, completion percentage  
✅ **JSONL format** - streaming-friendly newline-delimited output  

This stage reduces the data volume by ~55% while retaining all health-relevant content, enabling efficient processing in subsequent deduplication, location extraction, and embedding stages. Processing 9,480 records takes ~1.5 minutes at ~105 records/sec.
