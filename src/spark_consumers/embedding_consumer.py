"""
Spark Streaming Embedding Consumer
Ticket 3.4: Create embeddings for vector database storage

Creates dense vector embeddings from fully processed data (3.1 → 3.2 → 3.3):
1. Combines text content with extracted metadata (diseases, symptoms, location)
2. Generates embeddings using sentence-transformers
3. Outputs in vector DB-ready format

Reads from location consumer output → Creates embeddings → Writes vector DB format
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
from datetime import datetime
from typing import List, Dict, Optional
import logging
import hashlib

from pyspark.sql import SparkSession, DataFrame
import numpy as np
from sentence_transformers import SentenceTransformer

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EmbeddingConsumer:
    """
    Consumer for creating vector embeddings from processed disease surveillance data
    """

    def __init__(
        self,
        input_source: str = "file",
        input_path: str = "data/locations/",
        output_dir: str = "data/embeddings",
        checkpoint_dir: str = "checkpoints/embeddings",
        embedding_model: str = "all-MiniLM-L6-v2",
        embedding_dim: int = 384
    ):
        """
        Initialize Embedding Consumer

        Args:
            input_source: "kafka" or "file" (typically file for this stage)
            input_path: Path to location-enriched data
            output_dir: Output directory for embeddings
            checkpoint_dir: Spark checkpoint directory
            embedding_model: Sentence transformer model name
            embedding_dim: Embedding dimension (384 for MiniLM, 768 for base models)
        """
        self.input_source = input_source
        self.input_path = input_path
        self.output_dir = output_dir
        self.checkpoint_dir = checkpoint_dir
        self.embedding_model_name = embedding_model
        self.embedding_dim = embedding_dim

        # Create output directory
        os.makedirs(self.output_dir, exist_ok=True)

        # Initialize Spark Session
        self.spark = SparkSession.builder \
            .appName("NYC_Disease_Embeddings") \
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

        # Load embedding model
        logger.info(f"Loading embedding model: {self.embedding_model_name}")
        self.embedding_model = SentenceTransformer(self.embedding_model_name)
        logger.info(f"Model loaded (dimension: {self.embedding_dim})")

    def create_embedding_text(self, record: Dict) -> str:
        """
        Create rich text representation for embedding

        Combines:
        - Original text content
        - Extracted diseases and symptoms
        - Location information
        - Severity level

        Args:
            record: Processed record with all metadata

        Returns:
            Rich text string for embedding
        """
        parts = []

        # Main text content
        text = record.get('text') or record.get('description') or record.get('title') or ''
        if text:
            parts.append(text)

        # Diseases
        diseases_json = record.get('diseases_json', '[]')
        try:
            diseases = json.loads(diseases_json) if isinstance(diseases_json, str) else diseases_json
            if diseases:
                parts.append(f"Diseases: {', '.join(diseases)}")
        except:
            pass

        # Symptoms
        symptoms_json = record.get('symptoms_json', '[]')
        try:
            symptoms = json.loads(symptoms_json) if isinstance(symptoms_json, str) else symptoms_json
            if symptoms:
                parts.append(f"Symptoms: {', '.join(symptoms)}")
        except:
            pass

        # Location
        loc_extract = record.get('location_extraction', {})
        if loc_extract:
            neighborhood = loc_extract.get('neighborhood')
            borough = loc_extract.get('borough')
            if neighborhood:
                parts.append(f"Location: {neighborhood}, {borough}" if borough else f"Location: {neighborhood}")
            elif borough:
                parts.append(f"Location: {borough}")

        # Severity
        severity = record.get('severity')
        if severity and severity != 'unknown':
            parts.append(f"Severity: {severity}")

        return '. '.join(parts)

    def create_embedding(self, record: Dict) -> Dict:
        """
        Create embedding for a single record

        Args:
            record: Input record

        Returns:
            Record with embedding and vector DB metadata
        """
        # Create rich text for embedding
        embedding_text = self.create_embedding_text(record)

        # Generate embedding
        embedding_vector = self.embedding_model.encode(embedding_text)

        # Create unique ID (for vector DB)
        record_id = record.get('post_id') or record.get('id') or hashlib.md5(
            (embedding_text + str(record.get('timestamp', ''))).encode()
        ).hexdigest()

        # Extract metadata for vector DB filtering
        diseases = []
        symptoms = []
        try:
            diseases_json = record.get('diseases_json', '[]')
            diseases = json.loads(diseases_json) if isinstance(diseases_json, str) else diseases_json
        except:
            pass

        try:
            symptoms_json = record.get('symptoms_json', '[]')
            symptoms = json.loads(symptoms_json) if isinstance(symptoms_json, str) else symptoms_json
        except:
            pass

        loc_extract = record.get('location_extraction', {})

        # Create vector DB document
        vector_doc = {
            # Vector DB fields
            "id": record_id,
            "vector": embedding_vector.tolist(),  # Convert numpy array to list
            "text": embedding_text,

            # Metadata for filtering/retrieval
            "metadata": {
                "source": record.get('source'),
                "timestamp": record.get('timestamp'),
                "diseases": diseases,
                "symptoms": symptoms,
                "severity": record.get('severity'),
                "confidence": record.get('confidence'),
                "neighborhood": loc_extract.get('neighborhood'),
                "borough": loc_extract.get('borough'),
                "location_source": loc_extract.get('location_source'),
                "is_duplicate": record.get('is_duplicate', False),
                "dedup_tier": record.get('dedup_tier'),
            },

            # Full original record (for reference)
            "original_record": record,

            # Processing metadata
            "embedding_model": self.embedding_model_name,
            "embedding_dim": self.embedding_dim,
            "created_at": datetime.utcnow().isoformat()
        }

        return vector_doc

    def process_batch(self, records: List[Dict], batch_id: int):
        """
        Process batch of records and create embeddings

        Args:
            records: List of location-enriched records
            batch_id: Batch ID
        """
        logger.info(f"Processing batch {batch_id} with {len(records)} records")

        embedded_docs = []

        for record in records:
            try:
                vector_doc = self.create_embedding(record)
                embedded_docs.append(vector_doc)
            except Exception as e:
                logger.error(f"Error creating embedding: {e}")
                continue

        logger.info(f"Created {len(embedded_docs)} embeddings")

        # Write output
        if embedded_docs:
            self.write_output(embedded_docs, batch_id)

    def write_output(self, vector_docs: List[Dict], batch_id: int):
        """
        Write embeddings to output directory

        Args:
            vector_docs: List of vector documents
            batch_id: Batch ID
        """
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        output_file = f"{self.output_dir}/embeddings_batch_{batch_id}_{timestamp}.json"

        with open(output_file, 'w') as f:
            json.dump(vector_docs, f, indent=2)

        logger.info(f"Wrote {len(vector_docs)} embeddings to {output_file}")

        # Also write a summary
        summary_file = f"{self.output_dir}/embedding_summary_batch_{batch_id}_{timestamp}.json"
        summary = {
            "batch_id": batch_id,
            "total_embeddings": len(vector_docs),
            "embedding_model": self.embedding_model_name,
            "embedding_dim": self.embedding_dim,
            "created_at": datetime.utcnow().isoformat(),
            "sample_metadata": {
                "diseases": list(set([d for doc in vector_docs for d in doc['metadata'].get('diseases', [])])),
                "boroughs": list(set([doc['metadata'].get('borough') for doc in vector_docs if doc['metadata'].get('borough')])),
                "severity_levels": list(set([doc['metadata'].get('severity') for doc in vector_docs if doc['metadata'].get('severity')]))
            }
        }

        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2)

        logger.info(f"Wrote summary to {summary_file}")

    def read_from_files(self):
        """Read JSON records from file system"""
        import glob

        logger.info(f"Reading files from: {self.input_path}")

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
        """Start the embedding consumer"""
        logger.info("="*60)
        logger.info("Starting NYC Disease Embedding Consumer")
        logger.info(f"Input Source: {self.input_source}")
        logger.info(f"Input Path: {self.input_path}")
        logger.info(f"Output Dir: {self.output_dir}")
        logger.info(f"Embedding Model: {self.embedding_model_name}")
        logger.info(f"Embedding Dimension: {self.embedding_dim}")
        logger.info("="*60)

        if self.input_source == "file":
            # Batch processing mode
            records = self.read_from_files()
            if records:
                self.process_batch(records, batch_id=0)
            logger.info("Embedding generation completed")
            self.spark.stop()
            return

        # Streaming mode not implemented for this stage (typically batch)
        logger.error("Streaming mode not implemented for embedding consumer")
        self.spark.stop()


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Embedding Consumer for Vector DB')
    parser.add_argument('--input-source', default='file', choices=['file'], help='Input source (file only)')
    parser.add_argument('--input-path', default='data/locations/', help='Path to location-enriched data')
    parser.add_argument('--output-dir', default='data/embeddings', help='Output directory')
    parser.add_argument('--checkpoint-dir', default='checkpoints/embeddings', help='Checkpoint directory')
    parser.add_argument('--embedding-model', default='all-MiniLM-L6-v2', help='Sentence transformer model')
    parser.add_argument('--embedding-dim', type=int, default=384, help='Embedding dimension')

    args = parser.parse_args()

    consumer = EmbeddingConsumer(
        input_source=args.input_source,
        input_path=args.input_path,
        output_dir=args.output_dir,
        checkpoint_dir=args.checkpoint_dir,
        embedding_model=args.embedding_model,
        embedding_dim=args.embedding_dim
    )

    consumer.start()


if __name__ == "__main__":
    main()
