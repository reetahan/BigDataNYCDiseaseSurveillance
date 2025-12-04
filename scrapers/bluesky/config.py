"""
Configuration settings for Bluesky scraper
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from project root
project_root = Path(__file__).parent.parent.parent
load_dotenv(project_root / '.env')


class Config:
    """Configuration for Bluesky scraper"""

    # Bluesky authentication
    BLUESKY_HANDLE = os.getenv('BLUESKY_HANDLE')
    BLUESKY_PASSWORD = os.getenv('BLUESKY_PASSWORD')

    # Kafka settings
    KAFKA_BOOTSTRAP_SERVERS = os.getenv(
        'KAFKA_BOOTSTRAP_SERVERS',
        'localhost:9092'
    ).split(',')
    KAFKA_TOPIC = os.getenv('KAFKA_TOPIC', 'social-media')
    ENABLE_KAFKA = os.getenv('ENABLE_KAFKA', 'false').lower() == 'true'

    # Scraper settings
    SCRAPE_INTERVAL = int(os.getenv('SCRAPE_INTERVAL', '300'))  # seconds
    MAX_POSTS_PER_SEARCH = int(os.getenv('MAX_POSTS_PER_SEARCH', '100'))
    OUTPUT_FILE = os.getenv('OUTPUT_FILE', 'data/bluesky_posts.json')

    # Health keywords (can be extended via environment)
    CUSTOM_HEALTH_KEYWORDS = os.getenv('CUSTOM_HEALTH_KEYWORDS', '').split(',')
    CUSTOM_NYC_KEYWORDS = os.getenv('CUSTOM_NYC_KEYWORDS', '').split(',')

    # Rate limiting
    RATE_LIMIT_DELAY = int(os.getenv('RATE_LIMIT_DELAY', '2'))  # seconds between requests

    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
