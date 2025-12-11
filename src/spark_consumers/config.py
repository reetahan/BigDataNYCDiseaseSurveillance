"""
Configuration for Spark Streaming Deduplication Consumer
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from project root
project_root = Path(__file__).parent.parent
load_dotenv(project_root / '.env')


class DeduplicationConfig:
    """Configuration settings for deduplication consumer"""

    # Kafka settings
    KAFKA_BOOTSTRAP_SERVERS = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
    KAFKA_TOPICS = os.getenv('KAFKA_TOPICS', 'reddit,bluesky,rss,nyc_311,nyc_press,nyc_covid')

    # Output settings
    OUTPUT_DIR = os.getenv('DEDUP_OUTPUT_DIR', 'data/deduplicated')
    CHECKPOINT_DIR = os.getenv('DEDUP_CHECKPOINT_DIR', 'checkpoints/deduplication')

    # Deduplication thresholds
    SIMILARITY_THRESHOLD = float(os.getenv('SIMILARITY_THRESHOLD', '0.85'))  # Semantic similarity
    FUZZY_THRESHOLD = float(os.getenv('FUZZY_THRESHOLD', '0.90'))  # Fuzzy matching

    # Model settings
    EMBEDDING_MODEL = os.getenv('EMBEDDING_MODEL', 'all-MiniLM-L6-v2')

    # Cache limits (prevent memory issues)
    MAX_TEXT_CACHE = int(os.getenv('MAX_TEXT_CACHE', '1000'))
    MAX_EMBEDDING_CACHE = int(os.getenv('MAX_EMBEDDING_CACHE', '500'))

    # Processing settings
    BATCH_SIZE = int(os.getenv('DEDUP_BATCH_SIZE', '100'))
    MIN_TEXT_LENGTH = int(os.getenv('MIN_TEXT_LENGTH', '10'))
