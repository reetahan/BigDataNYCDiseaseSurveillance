"""
Spark Streaming Relevance Analysis Consumer
Ticket 3.1: LLM-based relevance filtering and health entity extraction

Uses Qwen 2.5 7B via Ollama (local inference) with Spark UDFs for parallelism:
1. Filter for health-relevant content
2. Extract diseases, symptoms, severity
3. Assign confidence scores

Reads from Kafka → LLM Analysis (parallel) → Writes to output directory
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
import re
import requests
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import logging

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import udf, col, current_timestamp, lit
from pyspark.sql.types import (
    StructType, StructField, StringType, BooleanType, 
    ArrayType, FloatType, IntegerType
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RelevanceConsumer:
    """
    Spark Streaming consumer for LLM-based health relevance analysis
    """

    def __init__(
        self,
        kafka_bootstrap_servers: str = "localhost:9092",
        kafka_topics: str = "reddit.health,bluesky.health,rss.health,nyc_311.health,nyc_press.health,nyc_covid.health",
        output_dir: str = "data/relevance",
        checkpoint_dir: str = "checkpoints/relevance",
        ollama_url: str = "http://localhost:11434",
        ollama_model: str = "qwen2.5:7b"
    ):
        """
        Initialize the relevance consumer

        Args:
            kafka_bootstrap_servers: Kafka broker addresses
            kafka_topics: Comma-separated list of Kafka topics to consume
            output_dir: Directory to write analyzed data
            checkpoint_dir: Spark checkpoint directory
            ollama_url: Ollama API endpoint
            ollama_model: Ollama model name
        """
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.kafka_topics = kafka_topics
        self.output_dir = output_dir
        self.checkpoint_dir = checkpoint_dir
        self.ollama_url = ollama_url
        self.ollama_model = ollama_model

        # Create output directories
        os.makedirs(self.output_dir, exist_ok=True)
        os.makedirs(f"{self.output_dir}/relevant", exist_ok=True)
        os.makedirs(f"{self.output_dir}/irrelevant", exist_ok=True)

        # Initialize Spark Session with Java 11+ compatibility
        self.spark = SparkSession.builder \
            .appName("NYC_Relevance_Analysis") \
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
            .getOrCreate()

        self.spark.sparkContext.setLogLevel("WARN")

        # Test Ollama connection
        logger.info(f"Testing Ollama connection at {self.ollama_url}...")
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models = [m['name'] for m in response.json().get('models', [])]
                logger.info(f"Ollama connected. Available models: {models}")
                if self.ollama_model not in models:
                    logger.warning(f"Model '{self.ollama_model}' not found. Run: ollama pull {self.ollama_model}")
            else:
                logger.warning(f"Ollama returned status {response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Cannot connect to Ollama at {self.ollama_url}. Make sure 'OLLAMA_NUM_PARALLEL=10 ollama serve' is running.")
            raise ValueError(f"Ollama connection failed: {e}")

        logger.info(f"Ollama client initialized successfully with model: {self.ollama_model}")

    def create_analysis_udf(self):
        """
        Create Spark UDF for health relevance analysis
        This UDF will be executed in parallel across Spark executors
        """
        ollama_url = self.ollama_url
        ollama_model = self.ollama_model
        def analyze_health_relevance(json_str: str) -> Tuple[bool, str, str, str, float, str]:
            """Analyze if text is health-related and extract entities"""
            try:
                # Parse record
                record = json.loads(json_str)
                
                # Handle structured COVID/health metrics data
                if 'metric' in record and 'value' in record:
                    # This is time-series health data - mark as relevant
                    metric = record.get('metric', '')
                    submetric = record.get('submetric', '')
                    value = record.get('value', '')
                    date = record.get('date', '')
                    
                    # Extract disease from metric name
                    diseases = []
                    if 'COVID' in metric.upper():
                        diseases.append('COVID-19')
                    if 'FLU' in metric.upper() or 'INFLUENZA' in metric.upper():
                        diseases.append('Influenza')
                    if 'RSV' in metric.upper():
                        diseases.append('RSV')
                    
                    # This is structured health data - always relevant
                    return (
                        True,
                        json.dumps(diseases),
                        json.dumps([]),  # No symptoms in time-series data
                        'moderate',  # Default severity for surveillance data
                        0.95,  # High confidence - this is official health data
                        'structured_health_data'
                    )
                
                # Handle text-based records (social media, 311, news)
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
                
                # Add location context if available (important for 311 data)
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
                
                # Truncate long text
                text = text[:2000]
                
                # Create prompt with better context
                prompt = f"""Text: "{text}"

        Task: Determine if this NYC report/post is health-related (diseases, symptoms, environmental health hazards like rodents, food safety issues).

        Output ONLY valid JSON with no additional text:
        {{"is_relevant": true, "diseases": ["disease_name"], "symptoms": ["symptom"], "severity": "mild"}}

        JSON:"""
                
                # Call Ollama
                response = requests.post(
                    f"{ollama_url}/api/generate",
                    json={
                        "model": ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {
                            "temperature": 0.1,
                            "num_predict": 150
                        }
                    },
                    timeout=30
                )
                
                if response.status_code != 200:
                    return (False, '[]', '[]', 'unknown', 0.0, f'api_error_{response.status_code}')
                
                # Parse response
                result = response.json()
                content = result.get('response', '').strip()
                
                # Extract JSON from response
                json_match = re.search(r'\{.*?\}', content, re.DOTALL)
                if json_match:
                    json_str_response = json_match.group(0)
                    parsed = json.loads(json_str_response)
                    
                    is_relevant = parsed.get('is_relevant', False)
                    diseases = parsed.get('diseases', [])
                    symptoms = parsed.get('symptoms', [])
                    severity = parsed.get('severity', 'unknown')
                    
                    # Calculate confidence
                    if is_relevant:
                        confidence = 0.7 + (0.1 * min(len(diseases), 2)) + (0.05 * min(len(symptoms), 2))
                        if severity != 'unknown':
                            confidence += 0.05
                        confidence = min(confidence, 0.95)
                    else:
                        confidence = 0.1
                    
                    return (
                        is_relevant,
                        json.dumps(diseases),
                        json.dumps(symptoms),
                        severity,
                        float(confidence),
                        'success'
                    )
                
                return (False, '[]', '[]', 'unknown', 0.0, 'parse_error')
                
            except requests.exceptions.Timeout:
                return (False, '[]', '[]', 'unknown', 0.0, 'timeout')
            except json.JSONDecodeError as e:
                return (False, '[]', '[]', 'unknown', 0.0, 'json_decode_error')
            except Exception as e:
                return (False, '[]', '[]', 'unknown', 0.0, f'error_{type(e).__name__}')
                    
                            
                
                
            except requests.exceptions.Timeout:
                return (False, '[]', '[]', 'unknown', 0.0, 'timeout')
            except json.JSONDecodeError as e:
                return (False, '[]', '[]', 'unknown', 0.0, 'json_decode_error')
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

    def start(self):
        """
        Start the Spark Streaming consumer with UDF-based parallel processing
        """
        logger.info("="*60)
        logger.info("Starting NYC Relevance Analysis Consumer (Parallel UDF)")
        logger.info(f"Kafka Brokers: {self.kafka_bootstrap_servers}")
        logger.info(f"Topics: {self.kafka_topics}")
        logger.info(f"Output Dir: {self.output_dir}")
        logger.info(f"Ollama Model: {self.ollama_model}")
        logger.info("="*60)

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

        # Split into relevant and irrelevant streams
        relevant_df = analyzed_df.filter(col("is_relevant") == True)
        irrelevant_df = analyzed_df.filter(col("is_relevant") == False)

        # Write relevant records
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

        logger.info("Streaming queries started. Press Ctrl+C to stop.")
        logger.info(f"Relevant records → {self.output_dir}/relevant")
        logger.info(f"Irrelevant records → {self.output_dir}/irrelevant")

        try:
            relevant_query.awaitTermination()
        except KeyboardInterrupt:
            logger.info("Stopping consumers...")
            relevant_query.stop()
            irrelevant_query.stop()
            self.spark.stop()
            logger.info("Consumers stopped")


def main():
    """
    Main entry point
    """
    import argparse

    parser = argparse.ArgumentParser(description='Spark Streaming Relevance Analysis Consumer (Parallel UDF)')
    parser.add_argument('--kafka-servers', default='localhost:9092', help='Kafka bootstrap servers')
    parser.add_argument('--topics', default='reddit.health,bluesky.health,rss.health,nyc_311.health,nyc_press.health,nyc_covid.health', help='Comma-separated Kafka topics')
    parser.add_argument('--output-dir', default='data/relevance', help='Output directory')
    parser.add_argument('--checkpoint-dir', default='checkpoints/relevance', help='Checkpoint directory')
    parser.add_argument('--ollama-url', default='http://localhost:11434', help='Ollama API URL')
    parser.add_argument('--ollama-model', default='qwen2.5:7b', help='Ollama model name')

    args = parser.parse_args()

    consumer = RelevanceConsumer(
        kafka_bootstrap_servers=args.kafka_servers,
        kafka_topics=args.topics,
        output_dir=args.output_dir,
        checkpoint_dir=args.checkpoint_dir,
        ollama_url=args.ollama_url,
        ollama_model=args.ollama_model
    )

    consumer.start()


if __name__ == "__main__":
    main()