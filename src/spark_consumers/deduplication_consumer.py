"""
Spark Streaming Deduplication Consumer
Ticket 3.2: LLM/NLP-based deduplication filter

3-Tier Deduplication Strategy:
1. Exact Match (hash-based) - Fast
2. Fuzzy Matching (TF-IDF) - Medium
3. Semantic Similarity (embeddings) - Slow but accurate

Reads from Kafka → Deduplicates → Writes to output directory
"""

import os
import sys

# Configure PySpark environment before any imports
os.environ['PYSPARK_SUBMIT_ARGS'] = '--packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0 --conf spark.driver.extraJavaOptions=-Djava.security.manager.allow=true --conf spark.executor.extraJavaOptions=-Djava.security.manager.allow=true pyspark-shell'
os.environ['SPARK_LOCAL_IP'] = '127.0.0.1'
if sys.version_info >= (3, 0):
    os.environ['PYSPARK_PYTHON'] = sys.executable
    os.environ['PYSPARK_DRIVER_PYTHON'] = sys.executable

import json
import hashlib
from datetime import datetime
from typing import List, Dict, Set
import logging

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import col, from_json, udf, struct, to_json
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, ArrayType, FloatType

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DeduplicationConsumer:
    """
    Spark Streaming consumer with 3-tier deduplication
    """

    def __init__(
        self,
        input_source: str = "kafka",
        input_path: str = None,
        kafka_bootstrap_servers: str = "localhost:9092",
        kafka_topics: str = "reddit.health,bluesky.health,rss.health,nyc_311.health,nyc_press.health,nyc_covid.health",
        output_dir: str = "data/deduplicated",
        checkpoint_dir: str = "checkpoints/deduplication",
        similarity_threshold: float = 0.85,
        fuzzy_threshold: float = 0.90
    ):
        """
        Initialize the deduplication consumer

        Args:
            input_source: "kafka" or "file" - where to read data from
            input_path: Path to input files (for file mode, e.g., "data/relevance/relevant/")
            kafka_bootstrap_servers: Kafka broker addresses
            kafka_topics: Comma-separated list of Kafka topics to consume
            output_dir: Directory to write deduplicated data
            checkpoint_dir: Spark checkpoint directory
            similarity_threshold: Cosine similarity threshold for semantic deduplication (0-1)
            fuzzy_threshold: TF-IDF similarity threshold for fuzzy matching (0-1)
        """
        self.input_source = input_source
        self.input_path = input_path
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.kafka_topics = kafka_topics
        self.output_dir = output_dir
        self.checkpoint_dir = checkpoint_dir
        self.similarity_threshold = similarity_threshold
        self.fuzzy_threshold = fuzzy_threshold

        # Create output directory
        os.makedirs(self.output_dir, exist_ok=True)

        # Initialize Spark Session with Java 11+ compatibility
        self.spark = SparkSession.builder \
            .appName("NYC_Disease_Deduplication") \
            .master("local[*]") \
            .config("spark.driver.memory", "4g") \
            .config("spark.executor.memory", "4g") \
            .config("spark.sql.streaming.schemaInference", "true") \
            .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0") \
            .config("spark.driver.extraJavaOptions", "-Djava.security.manager.allow=true") \
            .config("spark.executor.extraJavaOptions", "-Djava.security.manager.allow=true") \
            .config("spark.sql.streaming.checkpointLocation", self.checkpoint_dir) \
            .getOrCreate()

        self.spark.sparkContext.setLogLevel("WARN")

        # Initialize ML models (loaded once, shared across workers)
        logger.info("Loading sentence transformer model...")
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        logger.info("Model loaded successfully")

        # In-memory caches for deduplication
        self.seen_hashes: Set[str] = set()
        self.text_cache: List[str] = []
        self.embedding_cache: List[np.ndarray] = []

    def extract_text_content(self, record: Dict) -> str:
        """
        Extract text content from different data sources

        Args:
            record: Data record from Kafka

        Returns:
            Extracted text content
        """
        # Try different text fields based on source
        text_fields = ['text', 'description', 'title', 'content', 'body']

        for field in text_fields:
            if field in record and record[field]:
                return str(record[field])

        # Fallback: combine available text fields
        text_parts = []
        if 'title' in record:
            text_parts.append(str(record['title']))
        if 'text' in record:
            text_parts.append(str(record['text']))

        return ' '.join(text_parts) if text_parts else ""

    def compute_hash(self, text: str) -> str:
        """
        Compute SHA-256 hash of text (Tier 1: Exact Match)

        Args:
            text: Input text

        Returns:
            SHA-256 hash string
        """
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    def is_exact_duplicate(self, text: str) -> bool:
        """
        Check for exact duplicate using hash (Tier 1)

        Args:
            text: Input text

        Returns:
            True if exact duplicate found
        """
        text_hash = self.compute_hash(text)

        if text_hash in self.seen_hashes:
            return True

        self.seen_hashes.add(text_hash)
        return False

    def fuzzy_similarity(self, text: str, existing_texts: List[str]) -> float:
        """
        Compute TF-IDF based fuzzy similarity (Tier 2)

        Args:
            text: New text to check
            existing_texts: List of existing texts

        Returns:
            Maximum similarity score (0-1)
        """
        if not existing_texts:
            return 0.0

        try:
            vectorizer = TfidfVectorizer(min_df=1, stop_words='english')
            all_texts = existing_texts + [text]
            tfidf_matrix = vectorizer.fit_transform(all_texts)

            # Compute similarity of new text with all existing texts
            new_text_vector = tfidf_matrix[-1]
            existing_vectors = tfidf_matrix[:-1]

            similarities = cosine_similarity(new_text_vector, existing_vectors)[0]
            return float(np.max(similarities)) if len(similarities) > 0 else 0.0

        except Exception as e:
            logger.warning(f"Fuzzy similarity computation failed: {e}")
            return 0.0

    def semantic_similarity(self, text: str, existing_embeddings: List[np.ndarray]) -> float:
        """
        Compute semantic similarity using embeddings (Tier 3)

        Args:
            text: New text to check
            existing_embeddings: List of existing embeddings

        Returns:
            Maximum similarity score (0-1)
        """
        if not existing_embeddings:
            return 0.0

        try:
            # Generate embedding for new text
            new_embedding = self.embedding_model.encode([text])[0]

            # Compute cosine similarity with all existing embeddings
            similarities = cosine_similarity([new_embedding], existing_embeddings)[0]
            return float(np.max(similarities))

        except Exception as e:
            logger.warning(f"Semantic similarity computation failed: {e}")
            return 0.0

    def deduplicate_record(self, record: Dict) -> Dict:
        """
        Apply 3-tier deduplication to a single record

        Args:
            record: Input data record

        Returns:
            Record with deduplication metadata
        """
        text = self.extract_text_content(record)

        # Skip empty text
        if not text or len(text.strip()) < 10:
            record['is_duplicate'] = False
            record['dedup_tier'] = 'skipped'
            record['similarity_score'] = 0.0
            return record

        # Tier 1: Exact Hash Match (fastest)
        if self.is_exact_duplicate(text):
            logger.debug(f"Tier 1 duplicate detected: {text[:50]}...")
            record['is_duplicate'] = True
            record['dedup_tier'] = 'exact_hash'
            record['similarity_score'] = 1.0
            return record

        # Tier 2: Fuzzy Match (medium speed)
        fuzzy_score = self.fuzzy_similarity(text, self.text_cache[-100:])  # Check last 100 texts
        if fuzzy_score >= self.fuzzy_threshold:
            logger.debug(f"Tier 2 duplicate detected (score: {fuzzy_score}): {text[:50]}...")
            record['is_duplicate'] = True
            record['dedup_tier'] = 'fuzzy_tfidf'
            record['similarity_score'] = float(fuzzy_score)
            return record

        # Tier 3: Semantic Similarity (slowest but most accurate)
        semantic_score = self.semantic_similarity(text, self.embedding_cache[-50:])  # Check last 50
        if semantic_score >= self.similarity_threshold:
            logger.debug(f"Tier 3 duplicate detected (score: {semantic_score}): {text[:50]}...")
            record['is_duplicate'] = True
            record['dedup_tier'] = 'semantic_embedding'
            record['similarity_score'] = float(semantic_score)
            return record

        # Not a duplicate - add to caches
        record['is_duplicate'] = False
        record['dedup_tier'] = 'unique'
        record['similarity_score'] = 0.0

        # Update caches
        self.text_cache.append(text)
        try:
            embedding = self.embedding_model.encode([text])[0]
            self.embedding_cache.append(embedding)
        except Exception as e:
            logger.warning(f"Failed to generate embedding: {e}")

        # Limit cache sizes to prevent memory issues
        if len(self.text_cache) > 1000:
            self.text_cache = self.text_cache[-1000:]
        if len(self.embedding_cache) > 500:
            self.embedding_cache = self.embedding_cache[-500:]

        return record

    def process_batch(self, records: List[Dict], batch_id: int):
        """
        Process a micro-batch of records

        Args:
            records: List of record dictionaries
            batch_id: Batch ID
        """
        logger.info(f"Processing batch {batch_id} with {len(records)} records")

        # Apply deduplication to each record
        processed_records = []
        unique_count = 0
        duplicate_count = 0

        for record in records:
            try:
                dedup_record = self.deduplicate_record(record)
                dedup_record['batch_id'] = batch_id
                dedup_record['processed_at'] = datetime.utcnow().isoformat()

                processed_records.append(dedup_record)

                if dedup_record['is_duplicate']:
                    duplicate_count += 1
                else:
                    unique_count += 1

            except Exception as e:
                logger.error(f"Error processing record: {e}")
                continue

        logger.info(f"Batch {batch_id}: {unique_count} unique, {duplicate_count} duplicates")

        # Write results to output directory
        if processed_records:
            self.write_output(processed_records, batch_id)

    def write_output(self, records: List[Dict], batch_id: int):
        """
        Write deduplicated records to output directory

        Args:
            records: List of processed records
            batch_id: Batch ID
        """
        # Separate unique and duplicate records
        unique_records = [r for r in records if not r['is_duplicate']]
        duplicate_records = [r for r in records if r['is_duplicate']]

        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')

        # Write unique records
        if unique_records:
            unique_file = os.path.join(
                self.output_dir,
                f"unique_batch_{batch_id}_{timestamp}.json"
            )
            with open(unique_file, 'w') as f:
                json.dump(unique_records, f, indent=2)
            logger.info(f"Wrote {len(unique_records)} unique records to {unique_file}")

        # Write duplicate records (for audit/analysis)
        if duplicate_records:
            dup_file = os.path.join(
                self.output_dir,
                f"duplicates_batch_{batch_id}_{timestamp}.json"
            )
            with open(dup_file, 'w') as f:
                json.dump(duplicate_records, f, indent=2)
            logger.info(f"Wrote {len(duplicate_records)} duplicate records to {dup_file}")

    def read_from_files(self):
        """
        Read JSON records from file system (batch mode)
        """
        import glob

        logger.info(f"Reading files from: {self.input_path}")

        # Find all JSON files in the input path
        if os.path.isdir(self.input_path):
            file_pattern = os.path.join(self.input_path, "*.json")
        else:
            file_pattern = self.input_path

        json_files = glob.glob(file_pattern)
        logger.info(f"Found {len(json_files)} JSON files")

        all_records = []
        for file_path in json_files:
            try:
                with open(file_path, 'r') as f:
                    content = f.read().strip()
                    if not content:
                        continue
                    
                    # Try to parse as regular JSON first
                    try:
                        data = json.loads(content)
                        if isinstance(data, list):
                            all_records.extend(data)
                        else:
                            all_records.append(data)
                    except json.JSONDecodeError:
                        # If that fails, try JSONL (newline-delimited JSON)
                        lines = content.split('\n')
                        for line in lines:
                            line = line.strip()
                            if line:
                                try:
                                    all_records.append(json.loads(line))
                                except json.JSONDecodeError:
                                    pass
            except Exception as e:
                logger.warning(f"Failed to read {file_path}: {e}")

        logger.info(f"Loaded {len(all_records)} total records")
        return all_records

    def start(self):
        """
        Start the deduplication consumer (streaming or batch mode)
        """
        logger.info("="*60)
        logger.info("Starting NYC Disease Deduplication Consumer")
        logger.info(f"Input Source: {self.input_source}")
        if self.input_source == "kafka":
            logger.info(f"Kafka Brokers: {self.kafka_bootstrap_servers}")
            logger.info(f"Topics: {self.kafka_topics}")
        else:
            logger.info(f"Input Path: {self.input_path}")
        logger.info(f"Output Dir: {self.output_dir}")
        logger.info(f"Similarity Threshold: {self.similarity_threshold}")
        logger.info(f"Fuzzy Threshold: {self.fuzzy_threshold}")
        logger.info("="*60)

        if self.input_source == "file":
            # Batch processing mode
            records = self.read_from_files()
            if records:
                self.process_batch(records, batch_id=0)
            logger.info("File processing completed")
            self.spark.stop()
            return

        # Streaming mode (Kafka)
        # Read from Kafka
        df = self.spark \
            .readStream \
            .format("kafka") \
            .option("kafka.bootstrap.servers", self.kafka_bootstrap_servers) \
            .option("subscribe", self.kafka_topics) \
            .option("startingOffsets", "earliest") \
            .load()

        # Parse JSON values from Kafka
        # Assume all messages are JSON with at least these fields
        value_df = df.selectExpr("CAST(value AS STRING) as json_str", "timestamp")

        # Parse JSON (flexible schema)
        from pyspark.sql.functions import from_json, schema_of_json

        # Use foreachBatch to process with Python logic
        query = value_df \
            .writeStream \
            .foreachBatch(lambda batch_df, batch_id: self.process_batch_wrapper(batch_df, batch_id)) \
            .option("checkpointLocation", self.checkpoint_dir) \
            .start()

        logger.info("Streaming query started. Press Ctrl+C to stop.")

        try:
            query.awaitTermination()
        except KeyboardInterrupt:
            logger.info("Stopping consumer...")
            query.stop()
            self.spark.stop()
            logger.info("Consumer stopped")

    def process_batch_wrapper(self, batch_df: DataFrame, batch_id: int):
        """
        Wrapper to parse JSON and call process_batch

        Args:
            batch_df: Raw Spark DataFrame from Kafka
            batch_id: Batch ID
        """
        try:
            # Parse JSON strings
            json_records = []
            for row in batch_df.collect():
                try:
                    record = json.loads(row['json_str'])
                    json_records.append(record)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON: {e}")
                    continue

            if not json_records:
                logger.info(f"Batch {batch_id}: No valid records")
                return

            # Process directly as Python dicts (no DataFrame conversion needed)
            self.process_batch(json_records, batch_id)

        except Exception as e:
            logger.error(f"Error in batch {batch_id}: {e}")
            import traceback
            traceback.print_exc()


def main():
    """
    Main entry point
    """
    import argparse

    parser = argparse.ArgumentParser(description='Spark Streaming Deduplication Consumer')
    parser.add_argument('--input-source', default='kafka', choices=['kafka', 'file'], help='Input source: kafka or file')
    parser.add_argument('--input-path', default=None, help='Path to input files (for file mode)')
    parser.add_argument('--kafka-servers', default='localhost:9092', help='Kafka bootstrap servers')
    parser.add_argument('--topics', default='reddit.health,bluesky.health,rss.health,nyc_311.health,nyc_press.health,nyc_covid.health', help='Comma-separated Kafka topics')
    parser.add_argument('--output-dir', default='data/deduplicated', help='Output directory')
    parser.add_argument('--checkpoint-dir', default='checkpoints/deduplication', help='Checkpoint directory')
    parser.add_argument('--similarity-threshold', type=float, default=0.85, help='Semantic similarity threshold (0-1)')
    parser.add_argument('--fuzzy-threshold', type=float, default=0.90, help='Fuzzy matching threshold (0-1)')

    args = parser.parse_args()

    consumer = DeduplicationConsumer(
        input_source=args.input_source,
        input_path=args.input_path,
        kafka_bootstrap_servers=args.kafka_servers,
        kafka_topics=args.topics,
        output_dir=args.output_dir,
        checkpoint_dir=args.checkpoint_dir,
        similarity_threshold=args.similarity_threshold,
        fuzzy_threshold=args.fuzzy_threshold
    )

    consumer.start()


if __name__ == "__main__":
    main()
