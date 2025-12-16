"""
Spark Streaming Relevance Analysis Consumer
Ticket 3.1: ML-based relevance filtering and health entity extraction

Uses keyword-based analysis with ML-hybrid approach for:
1. Filter for health-relevant content
2. Extract diseases, symptoms, severity
3. Assign confidence scores

Reads from Kafka → Analysis (parallel) → Writes to output directory
"""

import os
import sys

# Configure PySpark environment before any imports
os.environ['PYSPARK_SUBMIT_ARGS'] = '--packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0 pyspark-shell'
os.environ['SPARK_LOCAL_IP'] = '127.0.0.1'
if sys.version_info >= (3, 0):
    os.environ['PYSPARK_PYTHON'] = sys.executable
    os.environ['PYSPARK_DRIVER_PYTHON'] = sys.executable

import json
from datetime import datetime
from typing import Tuple
import logging

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import udf, col, current_timestamp
from pyspark.sql.types import (
    StructType, StructField, StringType, BooleanType, 
    FloatType
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RelevanceConsumer:
    """
    Spark Streaming consumer for ML-based health relevance analysis
    """

    def __init__(
        self,
        kafka_bootstrap_servers: str = "localhost:9092",
        kafka_topics: str = "reddit.health,bluesky.health,rss.health,nyc_311.health,nyc_press.health,nyc_covid.health",
        output_dir: str = "data/relevance",
        checkpoint_dir: str = "checkpoints/relevance",
        auto_stop_on_empty: bool = False,
        empty_batches_before_stop: int = 3
    ):
        """
        Initialize the relevance consumer

        Args:
            kafka_bootstrap_servers: Kafka broker addresses
            kafka_topics: Comma-separated list of Kafka topics to consume
            output_dir: Directory to write analyzed data
            checkpoint_dir: Spark checkpoint directory
            auto_stop_on_empty: If True, stop after N consecutive empty batches (for pipeline mode)
            empty_batches_before_stop: Number of consecutive empty batches before stopping
        """
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.kafka_topics = kafka_topics
        self.output_dir = output_dir
        self.checkpoint_dir = checkpoint_dir
        self.auto_stop_on_empty = auto_stop_on_empty
        self.empty_batches_before_stop = empty_batches_before_stop

        # Progress tracking
        self.records_processed = 0
        self.relevant_count = 0
        self.irrelevant_count = 0
        self.start_time = None
        self.empty_batch_count = 0
        self.should_stop = False

        # Create output directories
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(f"{self.output_dir}/relevant", exist_ok=True)
        os.makedirs(f"{self.output_dir}/irrelevant", exist_ok=True)

        # Initialize Spark Session with Java 11+ compatibility
        self.spark = SparkSession.builder \
            .appName("NYC_Relevance_Analysis_ML") \
            .master("local[*]") \
            .config("spark.driver.memory", "4g") \
            .config("spark.executor.memory", "4g") \
            .config("spark.sql.streaming.schemaInference", "true") \
            .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0") \
            .config("spark.driver.extraJavaOptions", "-Djava.security.manager.allow=true") \
            .config("spark.executor.extraJavaOptions", "-Djava.security.manager.allow=true") \
            .config("spark.sql.streaming.checkpointLocation", self.checkpoint_dir) \
            .config("spark.default.parallelism", "10") \
            .config("spark.sql.shuffle.partitions", "10") \
            .config("spark.sql.streaming.kafka.useDeprecatedOffsetFetching", "false") \
            .getOrCreate()

        self.spark.sparkContext.setLogLevel("ERROR")

        print("Relevance Consumer initialized successfully")

    def create_analysis_udf(self):
        """
        Create Spark UDF for health relevance analysis
        This UDF will be executed in parallel across Spark executors
        """
        
        def analyze_health_relevance(json_str: str) -> Tuple[bool, str, str, str, float, str]:
            """
            Analyze if text is health-related and extract entities
            
            Returns:
                Tuple of (is_relevant, diseases_json, symptoms_json, severity, confidence, reason)
            """
            import json
            
            # Define keywords inside UDF to avoid serialization issues
            disease_keywords = {
                'COVID-19': ['covid', 'coronavirus', 'sars-cov-2'],
                'Influenza': ['flu', 'influenza'],
                'Norovirus': ['norovirus', 'stomach flu', 'stomach bug'],
                'RSV': ['rsv', 'respiratory syncytial'],
                'Strep Throat': ['strep', 'strep throat'],
                'Food Poisoning': ['food poisoning', 'foodborne', 'salmonella', 'e coli', 'e. coli'],
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
                'contamination',
                'unsanitary', 'hygiene', 'outbreak', 'infection',
                'contagious', 'epidemic', 'pandemic'
            ]
            
            try:
                # Parse record
                record = json.loads(json_str)
                
                # Handle structured COVID/health metrics data
                if 'metric' in record and 'value' in record:
                    metric = record.get('metric', '')
                    diseases = []
                    if 'COVID' in metric.upper():
                        diseases.append('COVID-19')
                    if 'FLU' in metric.upper() or 'INFLUENZA' in metric.upper():
                        diseases.append('Influenza')
                    if 'RSV' in metric.upper():
                        diseases.append('RSV')
                    
                    return (
                        True,
                        json.dumps(diseases),
                        json.dumps([]),
                        'moderate',
                        0.95,
                        'structured_health_data'
                    )
                
                # Extract text content from various fields
                text_parts = []
                
                # Add type field (e.g., "Rodent", "Food Poisoning")
                if 'type' in record:
                    text_parts.append(str(record['type']))
                
                # Add description
                if 'description' in record:
                    text_parts.append(str(record['description']))
                
                # Try other common fields from social media/news
                for field in ['text', 'title', 'content', 'body', 'summary']:
                    if field in record and record[field]:
                        text_parts.append(str(record[field]))
                
                # Combine text parts
                text = ' '.join(text_parts).strip()
                
                # Add location context if available
                if 'location' in record and isinstance(record['location'], dict):
                    location_info = []
                    if 'zip' in record['location']:
                        location_info.append(f"ZIP: {record['location']['zip']}")
                    if 'borough' in record['location']:
                        location_info.append(f"Borough: {record['location']['borough']}")
                    if location_info:
                        text = f"{text} ({', '.join(location_info)})"
                
                # Add source context for 311 reports
                if 'source' in record and record['source'] == 'NYC_311':
                    text = f"NYC 311 Report: {text}"
                
                # Skip empty or very short text
                if not text or len(text) < 5:
                    return (False, '[]', '[]', 'unknown', 0.0, 'insufficient_text')
                
                # Convert to lowercase for matching
                text_lower = text.lower()
                
                # Extract diseases using keyword matching
                found_diseases = []
                for disease, keywords in disease_keywords.items():
                    if any(kw in text_lower for kw in keywords):
                        found_diseases.append(disease)
                
                # Extract symptoms using keyword matching
                found_symptoms = []
                for symptom in symptom_keywords:
                    if symptom in text_lower:
                        found_symptoms.append(symptom)
                
                # Remove duplicate symptoms
                found_symptoms = list(set(found_symptoms))
                
                # Check for health hazards
                has_health_hazard = any(hazard in text_lower for hazard in health_hazard_keywords)
                
                # Determine relevance
                is_relevant = (
                    len(found_diseases) > 0 or
                    len(found_symptoms) >= 2 or
                    has_health_hazard
                )
                
                # Estimate severity based on keywords
                severity = 'unknown'
                if any(word in text_lower for word in ['severe', 'critical', 'emergency', 'hospital', 'ambulance', 'icu']):
                    severity = 'severe'
                elif any(word in text_lower for word in ['moderate', 'worse', 'worsening', 'bad']):
                    severity = 'moderate'
                elif any(word in text_lower for word in ['mild', 'slight', 'minor', 'little']):
                    severity = 'mild'
                
                # Calculate confidence score
                if is_relevant:
                    confidence = 0.6
                    # Boost confidence for specific diseases
                    if found_diseases:
                        confidence += 0.1 * min(len(found_diseases), 2)
                    # Boost confidence for multiple symptoms
                    if len(found_symptoms) >= 2:
                        confidence += 0.05 * min(len(found_symptoms), 3)
                    # Boost if severity identified
                    if severity != 'unknown':
                        confidence += 0.05
                    # Cap at 0.90
                    confidence = min(confidence, 0.90)
                else:
                    confidence = 0.2
                
                return (
                    is_relevant,
                    json.dumps(found_diseases),
                    json.dumps(found_symptoms),
                    severity,
                    float(confidence),
                    'keyword_analysis'
                )
                
            except Exception as e:
                return (False, '[]', '[]', 'unknown', 0.0, f'error_{type(e).__name__}')
        
        # Define return schema
        analysis_schema = StructType([
            StructField("is_relevant", BooleanType(), False),
            StructField("diseases_json", StringType(), False),
            StructField("symptoms_json", StringType(), False),
            StructField("severity", StringType(), False),
            StructField("confidence", FloatType(), False),
            StructField("reason", StringType(), False)
        ])
        
        return udf(analyze_health_relevance, analysis_schema)

    def update_progress(self, batch_df: DataFrame, batch_id: int):
        """Update and display progress"""
        try:
            batch_count = batch_df.count()
            
            # Count relevant vs irrelevant
            relevant_in_batch = batch_df.filter(col("is_relevant") == True).count()
            irrelevant_in_batch = batch_count - relevant_in_batch
            
            self.records_processed += batch_count
            self.relevant_count += relevant_in_batch
            self.irrelevant_count += irrelevant_in_batch
            
            if self.start_time is None:
                self.start_time = datetime.now()
            
            elapsed = (datetime.now() - self.start_time).total_seconds()
            rate = self.records_processed / elapsed if elapsed > 0 else 0
            
            # Progress bar
            total_estimated = 8000  # Adjust if you know exact count
            progress_pct = min(100, (self.records_processed / total_estimated) * 100)
            bar_length = 40
            filled_length = int(bar_length * progress_pct / 100)
            bar = '█' * filled_length + '-' * (bar_length - filled_length)
            
            print("")
            print("="*70)
            print(f"PROGRESS: [{bar}] {progress_pct:.1f}%")
            print(f"Batch {batch_id} | Processed: {self.records_processed}/{total_estimated} records")
            print(f"Relevant: {self.relevant_count} | Irrelevant: {self.irrelevant_count}")
            print(f"Rate: {rate:.2f} rec/sec | Elapsed: {elapsed/60:.1f} min")
            
            if rate > 0 and self.records_processed < total_estimated:
                remaining_time = (total_estimated - self.records_processed) / rate / 60
                print(f"Estimated time remaining: {remaining_time:.1f} minutes")
            
            print("="*70)
            print("")
            
        except Exception as e:
            logger.error(f"Progress update error: {e}")

    def write_relevant_batch(self, batch_df: DataFrame, batch_id: int):
        """Write relevant records batch and update progress"""
        try:
            # Update progress first
            self.update_progress(batch_df, batch_id)
            
            # Write to JSON
            if batch_df.count() > 0:
                batch_df.write.mode("append").json(f"{self.output_dir}/relevant")
            
        except Exception as e:
            logger.error(f"Error writing relevant batch {batch_id}: {e}")

    def start(self):
        """
        Start the Spark Streaming consumer with ML-based parallel processing
        """
        print("="*60)
        print("Starting NYC Relevance Analysis Consumer")
        print(f"Kafka Brokers: {self.kafka_bootstrap_servers}")
        print(f"Topics: {self.kafka_topics}")
        print(f"Output Dir: {self.output_dir}")
        print(f"Analysis: Keyword-based ML hybrid")
        print("="*60)

        # Create analysis UDF
        analyze_udf = self.create_analysis_udf()

        # Read from Kafka
        df = self.spark \
            .readStream \
            .format("kafka") \
            .option("kafka.bootstrap.servers", self.kafka_bootstrap_servers) \
            .option("subscribe", self.kafka_topics) \
            .option("startingOffsets", "earliest") \
            .load()

        # Parse JSON values and apply analysis UDF (executed in parallel)
        analyzed_df = df.selectExpr("CAST(value AS STRING) as json_str", "timestamp") \
            .withColumn("analysis", analyze_udf(col("json_str"))) \
            .select(
                col("json_str").alias("original_data"),
                col("timestamp").alias("kafka_timestamp"),
                col("analysis.is_relevant").alias("is_relevant"),
                col("analysis.diseases_json").alias("diseases_json"),
                col("analysis.symptoms_json").alias("symptoms_json"),
                col("analysis.severity").alias("severity"),
                col("analysis.confidence").alias("confidence"),
                col("analysis.reason").alias("reason"),
                current_timestamp().alias("processed_at")
            )

        
        def track_all_progress(batch_df: DataFrame, batch_id: int):
            """Track progress for all records"""
            try:
                batch_count = batch_df.count()
                
                # Check for empty batches (auto-stop mode)
                if self.auto_stop_on_empty:
                    if batch_count == 0:
                        self.empty_batch_count += 1
                        print(f"Empty batch {self.empty_batch_count}/{self.empty_batches_before_stop}...")
                        if self.empty_batch_count >= self.empty_batches_before_stop:
                            print("\n" + "="*70)
                            print("All Kafka messages processed. Stopping consumer...")
                            print("="*70)
                            self.should_stop = True
                            return
                    else:
                        # Reset counter if we get data
                        self.empty_batch_count = 0
                
                # Count relevant vs irrelevant
                relevant_in_batch = batch_df.filter(col("is_relevant") == True).count()
                irrelevant_in_batch = batch_count - relevant_in_batch
                
                self.records_processed += batch_count
                self.relevant_count += relevant_in_batch
                self.irrelevant_count += irrelevant_in_batch
                
                if self.start_time is None:
                    self.start_time = datetime.now()
                
                elapsed = (datetime.now() - self.start_time).total_seconds()
                rate = self.records_processed / elapsed if elapsed > 0 else 0
                
                # Progress bar
                total_estimated = 9480  # From your Kafka UI
                progress_pct = min(100, (self.records_processed / total_estimated) * 100)
                bar_length = 40
                filled_length = int(bar_length * progress_pct / 100)
                bar = '█' * filled_length + '-' * (bar_length - filled_length)
                
                print("")
                print("="*70)
                print(f"PROGRESS: [{bar}] {progress_pct:.1f}%")
                print(f"Batch {batch_id} | Processed: {self.records_processed}/{total_estimated} records")
                print(f"Relevant: {self.relevant_count} | Irrelevant: {self.irrelevant_count}")
                print(f"Rate: {rate:.2f} rec/sec | Elapsed: {elapsed/60:.1f} min")
                
                if rate > 0 and self.records_processed < total_estimated:
                    remaining_time = (total_estimated - self.records_processed) / rate / 60
                    print(f"Estimated time remaining: {remaining_time:.1f} minutes")
                
                print("="*70)
                print("")
                
            except Exception as e:
                logger.error(f"Progress update error: {e}")

        # Split into relevant and irrelevant streams
        relevant_df = analyzed_df.filter(col("is_relevant") == True)
        irrelevant_df = analyzed_df.filter(col("is_relevant") == False)

        # Track progress on ALL records by using analyzed_df directly
        progress_query = analyzed_df \
            .writeStream \
            .foreachBatch(track_all_progress) \
            .option("checkpointLocation", f"{self.checkpoint_dir}/progress") \
            .format("noop") \
            .start()

        # Write relevant records (no progress tracking here)
        relevant_query = relevant_df \
            .writeStream \
            .format("json") \
            .option("path", f"{self.output_dir}/relevant") \
            .option("checkpointLocation", f"{self.checkpoint_dir}/relevant") \
            .outputMode("append") \
            .start()

        # Write irrelevant records
        irrelevant_query = irrelevant_df \
            .writeStream \
            .format("json") \
            .option("path", f"{self.output_dir}/irrelevant") \
            .option("checkpointLocation", f"{self.checkpoint_dir}/irrelevant") \
            .outputMode("append") \
            .start()

        print("Streaming queries started with progress tracking")
        print(f"Relevant records → {self.output_dir}/relevant")
        print(f"Irrelevant records → {self.output_dir}/irrelevant")
        if self.auto_stop_on_empty:
            print(f"Auto-stop enabled: will stop after {self.empty_batches_before_stop} consecutive empty batches")

        try:
            if self.auto_stop_on_empty:
                # Poll for stop condition
                import time
                while not self.should_stop:
                    time.sleep(2)  # Check every 2 seconds
                    if not progress_query.isActive:
                        break
                
                # Stop all queries gracefully
                print("\n\nStopping consumers gracefully...")
                progress_query.stop()
                relevant_query.stop()
                irrelevant_query.stop()
            else:
                # Normal mode: wait indefinitely
                progress_query.awaitTermination()
                
        except KeyboardInterrupt:
            print("\n\nStopping consumers...")
            progress_query.stop()
            relevant_query.stop()
            irrelevant_query.stop()
        finally:
            self.spark.stop()
            
            # Final summary
            print("\n" + "="*70)
            print("FINAL SUMMARY")
            print(f"Total processed: {self.records_processed}")
            if self.records_processed > 0:
                print(f"Relevant: {self.relevant_count} ({self.relevant_count/self.records_processed*100:.1f}%)")
                print(f"Irrelevant: {self.irrelevant_count} ({self.irrelevant_count/self.records_processed*100:.1f}%)")
            print("="*70)
            print("Consumers stopped")


def main():
    """
    Main entry point
    """
    import argparse

    parser = argparse.ArgumentParser(description='Spark Streaming ML-based Relevance Analysis Consumer')
    parser.add_argument('--kafka-servers', default='localhost:9092', help='Kafka bootstrap servers')
    parser.add_argument('--topics', default='reddit.health,bluesky.health,rss.health,nyc_311.health,nyc_press.health,nyc_covid.health', help='Comma-separated Kafka topics')
    parser.add_argument('--output-dir', default='data/relevance', help='Output directory')
    parser.add_argument('--checkpoint-dir', default='checkpoints/relevance', help='Checkpoint directory')

    args = parser.parse_args()

    consumer = RelevanceConsumer(
        kafka_bootstrap_servers=args.kafka_servers,
        kafka_topics=args.topics,
        output_dir=args.output_dir,
        checkpoint_dir=args.checkpoint_dir
    )

    consumer.start()



if __name__ == "__main__":
    main()