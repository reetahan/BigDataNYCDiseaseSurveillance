"""
Spark Streaming Location Extraction Consumer
Ticket 3.3: Identify locations and assign to NYC neighborhoods

Extracts location information from text and existing coordinates:
1. For records with lat/lon: Map coordinates to neighborhoods
2. For text content: Use NER to extract location mentions
3. Normalize and enrich with NYC neighborhood data

Reads from Kafka → Extracts locations → Writes enriched data
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
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import logging

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import col, from_json, udf, struct, to_json
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, ArrayType, FloatType

import spacy
from spark_consumers.nyc_neighborhoods import (
    get_borough_from_zip,
    get_neighborhood_from_coords,
    get_neighborhood_from_zip,
    normalize_location_name,
    ALL_NEIGHBORHOODS,
    NYC_BOROUGHS
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class LocationConsumer:
    """
    Spark Streaming consumer for location extraction and neighborhood assignment
    """

    def __init__(
        self,
        kafka_bootstrap_servers: str = "localhost:9092",
        kafka_topics: str = "reddit.health,bluesky.health,rss.health,nyc_311.health,nyc_press.health,nyc_covid.health",
        output_dir: str = "data/locations",
        checkpoint_dir: str = "checkpoints/locations",
        spacy_model: str = "en_core_web_sm"
    ):
        """
        Initialize Location Consumer

        Args:
            kafka_bootstrap_servers: Kafka broker addresses
            kafka_topics: Comma-separated list of topics to consume
            output_dir: Directory to write enriched location data
            checkpoint_dir: Spark checkpoint directory
            spacy_model: spaCy model name for NER
        """
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.kafka_topics = kafka_topics
        self.output_dir = output_dir
        self.checkpoint_dir = checkpoint_dir
        self.spacy_model_name = spacy_model

        # Create output directory
        os.makedirs(self.output_dir, exist_ok=True)

        # Initialize Spark Session with Java 11+ compatibility
        self.spark = SparkSession.builder \
            .appName("NYC_Location_Extraction") \
            .master("local[*]") \
            .config("spark.driver.memory", "4g") \
            .config("spark.executor.memory", "4g") \
            .config("spark.sql.streaming.schemaInference", "true") \
            .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0") \
            .config("spark.driver.extraJavaOptions", "-Djava.security.manager.allow=true") \
            .config("spark.executor.extraJavaOptions", "-Djava.security.manager.allow=true") \
            .config("spark.sql.streaming.checkpointLocation", self.checkpoint_dir) \
            .getOrCreate()

        # Load spaCy model
        logger.info(f"Loading spaCy model: {self.spacy_model_name}")
        try:
            self.nlp = spacy.load(self.spacy_model_name)
        except OSError:
            logger.warning(f"spaCy model '{self.spacy_model_name}' not found. Attempting to download...")
            import subprocess
            subprocess.run(["python", "-m", "spacy", "download", self.spacy_model_name])
            self.nlp = spacy.load(self.spacy_model_name)
        logger.info("spaCy model loaded successfully")

    def extract_text_content(self, record: Dict) -> str:
        """Extract text content from various record types"""
        # Try different text fields based on source
        text_fields = ['text', 'description', 'title', 'summary', 'body', 'content']

        text_parts = []
        for field in text_fields:
            if field in record and record[field]:
                text_parts.append(str(record[field]))

        return ' '.join(text_parts).strip()

    def extract_locations_from_text(self, text: str) -> List[str]:
        """
        Extract location entities from text using spaCy NER

        Args:
            text: Input text

        Returns:
            List of location strings found in text
        """
        if not text or len(text) < 3:
            return []

        # Limit text length for performance
        text = text[:5000]

        doc = self.nlp(text)

        locations = []
        for ent in doc.ents:
            if ent.label_ in ["GPE", "LOC", "FAC"]:  # Geopolitical entity, Location, Facility
                locations.append(ent.text)

        return locations

    def extract_location_from_coords(self, record: Dict) -> Optional[Tuple[str, str]]:
        """
        Extract neighborhood and borough from lat/lon coordinates

        Args:
            record: Record with potential location data

        Returns:
            Tuple of (neighborhood, borough) or None
        """
        # Check if record has location object (NYC 311 format)
        if 'location' in record and isinstance(record['location'], dict):
            lat = record['location'].get('lat')
            lon = record['location'].get('lon')
            zip_code = record['location'].get('zip')

            if lat and lon:
                try:
                    neighborhood = get_neighborhood_from_coords(float(lat), float(lon))
                    borough = None

                    # Try to get borough from zip first
                    if zip_code:
                        borough = get_borough_from_zip(zip_code)

                    # If no neighborhood found, try zip
                    if not neighborhood and zip_code:
                        neighborhood = get_neighborhood_from_zip(zip_code)

                    return neighborhood, borough
                except (ValueError, TypeError):
                    pass

        # Check for top-level lat/lon fields
        if 'lat' in record and 'lon' in record:
            try:
                lat = float(record['lat'])
                lon = float(record['lon'])
                neighborhood = get_neighborhood_from_coords(lat, lon)
                borough = None

                if 'zip' in record or 'zipcode' in record:
                    zip_code = record.get('zip') or record.get('zipcode')
                    borough = get_borough_from_zip(zip_code)

                return neighborhood, borough
            except (ValueError, TypeError):
                pass

        return None, None

    def enrich_with_location(self, record: Dict) -> Dict:
        """
        Enrich record with location information

        Args:
            record: Input record

        Returns:
            Record enriched with location metadata
        """
        location_data = {
            "extracted_locations": [],
            "neighborhood": None,
            "borough": None,
            "location_source": None,
            "normalized_locations": []
        }

        # Step 1: Try to get location from coordinates
        neighborhood, borough = self.extract_location_from_coords(record)

        if neighborhood or borough:
            location_data["neighborhood"] = neighborhood
            location_data["borough"] = borough
            location_data["location_source"] = "coordinates"

        # Step 2: Extract locations from text
        text = self.extract_text_content(record)
        if text:
            raw_locations = self.extract_locations_from_text(text)
            location_data["extracted_locations"] = raw_locations

            # Normalize extracted locations
            normalized = []
            for loc in raw_locations:
                normalized_loc = normalize_location_name(loc)
                if normalized_loc:
                    normalized.append(normalized_loc)

                    # If we don't have a neighborhood yet, use first normalized location
                    if not location_data["neighborhood"]:
                        # Check if it's a neighborhood
                        if normalized_loc in ALL_NEIGHBORHOODS:
                            location_data["neighborhood"] = normalized_loc
                            location_data["location_source"] = "text_extraction"

                        # Check if it's a borough
                        elif normalized_loc in NYC_BOROUGHS:
                            location_data["borough"] = normalized_loc
                            location_data["location_source"] = "text_extraction"

            location_data["normalized_locations"] = list(set(normalized))  # Remove duplicates

        # Step 3: Try to infer borough from neighborhood if missing
        if location_data["neighborhood"] and not location_data["borough"]:
            for borough, borough_info in NYC_BOROUGHS.items():
                # Check if neighborhood is in this borough's neighborhoods
                if location_data["neighborhood"] in ALL_NEIGHBORHOODS:
                    # This is a simplified check - would need more detailed mapping
                    # For now, check zip codes
                    neighborhood_data = ALL_NEIGHBORHOODS[location_data["neighborhood"]]
                    if "zips" in neighborhood_data and neighborhood_data["zips"]:
                        test_zip = neighborhood_data["zips"][0]
                        inferred_borough = get_borough_from_zip(test_zip)
                        if inferred_borough:
                            location_data["borough"] = inferred_borough
                            break

        # Merge location data into record
        record["location_extraction"] = location_data

        return record

    def process_batch(self, records: List[Dict], batch_id: int):
        """
        Process a micro-batch of records

        Args:
            records: List of record dictionaries
            batch_id: Batch ID
        """
        logger.info(f"Processing batch {batch_id} with {len(records)} records")

        # Enrich records with location data
        enriched_records = []

        for record in records:
            try:
                enriched_record = self.enrich_with_location(record)
                enriched_record['batch_id'] = batch_id
                enriched_record['processed_at'] = datetime.utcnow().isoformat()
                enriched_records.append(enriched_record)
            except Exception as e:
                logger.error(f"Error processing record: {e}")
                continue

        # Log statistics
        with_neighborhood = sum(1 for r in enriched_records if r["location_extraction"]["neighborhood"])
        with_borough = sum(1 for r in enriched_records if r["location_extraction"]["borough"])

        logger.info(f"Batch {batch_id}: {with_neighborhood} with neighborhood, {with_borough} with borough")

        # Write results to output directory
        if enriched_records:
            self.write_output(enriched_records, batch_id)

    def write_output(self, records: List[Dict], batch_id: int):
        """
        Write enriched records to output directory

        Args:
            records: Enriched records
            batch_id: Batch ID
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        output_file = f"{self.output_dir}/locations_batch_{batch_id}_{timestamp}.json"

        with open(output_file, 'w') as f:
            json.dump(records, f, indent=2)

        logger.info(f"Wrote {len(records)} records to {output_file}")

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

            # Process directly as Python dicts
            self.process_batch(json_records, batch_id)

        except Exception as e:
            logger.error(f"Error in batch {batch_id}: {e}")
            import traceback
            traceback.print_exc()

    def start(self):
        """
        Start the streaming consumer
        """
        logger.info("="*60)
        logger.info("Starting NYC Location Extraction Consumer")
        logger.info(f"Kafka Brokers: {self.kafka_bootstrap_servers}")
        logger.info(f"Topics: {self.kafka_topics}")
        logger.info(f"Output Dir: {self.output_dir}")
        logger.info("="*60)

        # Read from Kafka
        df = self.spark \
            .readStream \
            .format("kafka") \
            .option("kafka.bootstrap.servers", self.kafka_bootstrap_servers) \
            .option("subscribe", self.kafka_topics) \
            .option("startingOffsets", "latest") \
            .load()

        # Parse JSON values from Kafka
        value_df = df.selectExpr("CAST(value AS STRING) as json_str", "timestamp")

        # Write stream with foreachBatch
        query = value_df \
            .writeStream \
            .foreachBatch(self.process_batch_wrapper) \
            .outputMode("append") \
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


def main():
    """
    Main entry point
    """
    import argparse

    parser = argparse.ArgumentParser(description='Spark Streaming Location Extraction Consumer')
    parser.add_argument('--kafka-servers', default='localhost:9092',
                        help='Kafka bootstrap servers (default: localhost:9092)')
    parser.add_argument('--topics', default='reddit.health,bluesky.health,rss.health,nyc_311.health,nyc_press.health,nyc_covid.health',
                        help='Comma-separated list of Kafka topics')
    parser.add_argument('--output-dir', default='data/locations',
                        help='Output directory for enriched data')
    parser.add_argument('--checkpoint-dir', default='checkpoints/locations',
                        help='Checkpoint directory for Spark')
    parser.add_argument('--spacy-model', default='en_core_web_sm',
                        help='spaCy model name for NER')

    args = parser.parse_args()

    consumer = LocationConsumer(
        kafka_bootstrap_servers=args.kafka_servers,
        kafka_topics=args.topics,
        output_dir=args.output_dir,
        checkpoint_dir=args.checkpoint_dir,
        spacy_model=args.spacy_model
    )

    consumer.start()


if __name__ == "__main__":
    main()
