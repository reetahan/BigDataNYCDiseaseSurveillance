"""
TimescaleDB Client for NYC Disease Surveillance
Loads processed data from Spark consumers into PostgreSQL with TimescaleDB
for time-series analysis and querying
"""

import os
import json
import glob
from typing import List, Dict, Optional
import logging
from datetime import datetime
import psycopg2
from psycopg2.extras import execute_values
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TimescaleDBClient:
    """
    Client for loading disease surveillance data into TimescaleDB
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "nyc_disease_surveillance",
        user: str = "postgres",
        password: str = "postgres"
    ):
        """
        Initialize TimescaleDB client

        Args:
            host: Database host
            port: Database port
            database: Database name
            user: Database user
            password: Database password
        """
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.conn = None
        self.cursor = None

        logger.info(f"Connecting to TimescaleDB at {host}:{port}/{database}")

    def connect(self):
        """Establish database connection"""
        try:
            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password
            )
            self.cursor = self.conn.cursor()
            logger.info("✓ Connected to TimescaleDB")
        except psycopg2.OperationalError as e:
            logger.error(f"Failed to connect: {e}")
            logger.info("Attempting to create database...")
            self._create_database()

    def _create_database(self):
        """Create database if it doesn't exist"""
        try:
            # Connect to default postgres database
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database='postgres',
                user=self.user,
                password=self.password
            )
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cursor = conn.cursor()

            # Create database
            cursor.execute(f"CREATE DATABASE {self.database}")
            logger.info(f"✓ Created database: {self.database}")

            cursor.close()
            conn.close()

            # Reconnect to new database
            self.connect()

        except Exception as e:
            logger.error(f"Failed to create database: {e}")
            raise

    def create_schema(self):
        """Create TimescaleDB schema and hypertables"""
        logger.info("Creating schema...")

        # Enable TimescaleDB extension
        self.cursor.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;")

        # Create main disease_events table
        # NOTE: For TimescaleDB hypertable, timestamp must be part of primary key
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS disease_events (
                id TEXT NOT NULL,
                timestamp TIMESTAMPTZ NOT NULL,
                source TEXT NOT NULL,
                text_content TEXT,
                
                -- Relevance data
                is_relevant BOOLEAN,
                diseases TEXT[],
                symptoms TEXT[],
                severity TEXT,
                confidence FLOAT,
                
                -- Deduplication data
                is_duplicate BOOLEAN,
                dedup_tier TEXT,
                similarity_score FLOAT,
                
                -- Location data
                borough TEXT,
                neighborhood TEXT,
                latitude FLOAT,
                longitude FLOAT,
                location_source TEXT,
                extracted_locations TEXT[],
                
                -- Metadata
                author TEXT,
                created_at TIMESTAMPTZ,
                processed_at TIMESTAMPTZ,
                embedding_id TEXT,
                
                -- Raw data
                raw_data JSONB,
                
                -- Composite primary key including timestamp for hypertable
                PRIMARY KEY (id, timestamp)
            );
        """)

        # Convert to hypertable (time-series optimized)
        try:
            self.cursor.execute("""
                SELECT create_hypertable('disease_events', 'timestamp',
                    if_not_exists => TRUE,
                    migrate_data => TRUE
                );
            """)
            logger.info("✓ Created hypertable for disease_events")
        except Exception as e:
            logger.warning(f"Hypertable may already exist: {e}")
            self.conn.rollback()  # Rollback on error to continue

        # Create indexes for common queries
        self.cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_disease_events_timestamp 
                ON disease_events (timestamp DESC);
            
            CREATE INDEX IF NOT EXISTS idx_disease_events_borough 
                ON disease_events (borough);
            
            CREATE INDEX IF NOT EXISTS idx_disease_events_neighborhood 
                ON disease_events (neighborhood);
            
            CREATE INDEX IF NOT EXISTS idx_disease_events_severity 
                ON disease_events (severity);
            
            CREATE INDEX IF NOT EXISTS idx_disease_events_diseases 
                ON disease_events USING GIN (diseases);
            
            CREATE INDEX IF NOT EXISTS idx_disease_events_symptoms 
                ON disease_events USING GIN (symptoms);
            
            CREATE INDEX IF NOT EXISTS idx_disease_events_is_relevant 
                ON disease_events (is_relevant) WHERE is_relevant = TRUE;
            
            CREATE INDEX IF NOT EXISTS idx_disease_events_is_duplicate 
                ON disease_events (is_duplicate) WHERE is_duplicate = FALSE;
        """)

        # Create aggregation views
        self.cursor.execute("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS daily_disease_counts AS
            SELECT 
                time_bucket('1 day', timestamp) AS day,
                borough,
                unnest(diseases) AS disease,
                COUNT(*) AS count,
                AVG(confidence) AS avg_confidence
            FROM disease_events
            WHERE is_relevant = TRUE AND is_duplicate = FALSE
            GROUP BY day, borough, disease
            ORDER BY day DESC, count DESC;
            
            CREATE INDEX IF NOT EXISTS idx_daily_counts_day 
                ON daily_disease_counts (day DESC);
        """)

        self.cursor.execute("""
            CREATE MATERIALIZED VIEW IF NOT EXISTS borough_severity_summary AS
            SELECT 
                borough,
                severity,
                COUNT(*) AS count,
                MAX(timestamp) AS last_event
            FROM disease_events
            WHERE is_relevant = TRUE AND is_duplicate = FALSE
            GROUP BY borough, severity
            ORDER BY borough, severity;
        """)

        self.conn.commit()
        logger.info("✓ Schema created successfully")

    def load_from_json_file(self, json_file: str) -> int:
        """
        Load processed data from a JSON file into TimescaleDB

        Args:
            json_file: Path to processed JSON file

        Returns:
            Number of records loaded
        """
        logger.info(f"Loading data from: {json_file}")

        with open(json_file, 'r') as f:
            data = json.load(f)

        records = []
        for item in data:
            # Extract source from original_data.source_file first
            source = 'unknown'
            original = None
            if 'original_data' in item:
                try:
                    if isinstance(item['original_data'], str):
                        original = json.loads(item['original_data'])
                    else:
                        original = item['original_data']
                    
                    # Extract source from source_file path (e.g., "reddit_posts.json" -> "reddit")
                    source_file = original.get('source_file', '')
                    if 'reddit' in source_file.lower():
                        source = 'reddit'
                    elif 'bluesky' in source_file.lower():
                        source = 'bluesky'
                    elif '311' in source_file:
                        source = 'nyc_311'
                    elif 'rss' in source_file.lower():
                        source = 'rss'
                    elif 'press' in source_file.lower():
                        source = 'nyc_press'
                    elif 'covid' in source_file.lower() or 'respiratory' in source_file.lower():
                        source = 'nyc_doh'
                except:
                    pass
            
            # Fallback to top-level source field
            if source == 'unknown':
                source = item.get('source', 'unknown')
            
            # Extract ID - try original_data first, then top-level fields
            record_id = None
            if original:
                record_id = original.get('post_id') or original.get('id') or original.get('message_id') or original.get('comment_id')
            
            # Fallback to top-level ID fields
            if not record_id:
                record_id = item.get('id') or item.get('post_id') or item.get('message_id')
            
            # If still no ID, generate one from timestamp + source
            if not record_id:
                import hashlib
                content = f"{source}_{item.get('processed_at', '')}_{item.get('text_content', '')[:100]}"
                record_id = hashlib.md5(content.encode()).hexdigest()
            
            # Extract timestamp - PRIORITIZE ORIGINAL EVENT TIME, not processing time
            # Try created_at/created_utc from original_data first
            timestamp = None
            if original:
                timestamp = (original.get('created_at') or 
                            original.get('created_utc') or 
                            original.get('timestamp') or 
                            original.get('scraped_at'))
            
            # Fallback to top-level created_at, then processed_at as last resort
            if not timestamp:
                timestamp = (item.get('created_at') or 
                            item.get('created_utc') or 
                            item.get('timestamp') or 
                            item.get('scraped_at') or 
                            item.get('processed_at') or 
                            datetime.now().isoformat())
            
            # Parse diseases and symptoms from JSON strings if needed
            diseases = item.get('diseases_json')
            if isinstance(diseases, str):
                try:
                    diseases = json.loads(diseases)
                except:
                    diseases = []
            
            symptoms = item.get('symptoms_json')
            if isinstance(symptoms, str):
                try:
                    symptoms = json.loads(symptoms)
                except:
                    symptoms = []

            # Extract location data
            location = item.get('location_extraction', {})
            if isinstance(location, str):
                try:
                    location = json.loads(location)
                except:
                    location = {}

            # Prepare record
            record = (
                record_id,
                timestamp,
                source,  # Now properly extracted from source_file
                item.get('text') or item.get('text_content'),
                
                # Relevance
                item.get('is_relevant'),
                diseases,
                symptoms,
                item.get('severity'),
                item.get('confidence'),
                
                # Deduplication
                item.get('is_duplicate'),
                item.get('dedup_tier'),
                item.get('similarity_score'),
                
                # Location
                location.get('borough'),
                location.get('neighborhood'),
                location.get('latitude'),
                location.get('longitude'),
                location.get('location_source'),
                location.get('extracted_locations', []),
                
                # Metadata
                item.get('author'),
                item.get('created_at') or item.get('created_utc'),
                item.get('processed_at'),
                item.get('embedding_id'),
                
                # Raw data
                json.dumps(item)
            )
            records.append(record)

        # Deduplicate records by (id, timestamp) - keep last occurrence
        seen = {}
        for record in records:
            key = (record[0], record[1])  # (id, timestamp)
            seen[key] = record
        
        unique_records = list(seen.values())
        
        if len(records) != len(unique_records):
            logger.warning(f"Removed {len(records) - len(unique_records)} duplicate (id, timestamp) pairs from batch")
        
        records = unique_records

        # Bulk insert
        insert_query = """
            INSERT INTO disease_events (
                id, timestamp, source, text_content,
                is_relevant, diseases, symptoms, severity, confidence,
                is_duplicate, dedup_tier, similarity_score,
                borough, neighborhood, latitude, longitude, location_source, extracted_locations,
                author, created_at, processed_at, embedding_id,
                raw_data
            ) VALUES %s
            ON CONFLICT (id, timestamp) DO UPDATE SET
                source = EXCLUDED.source,
                text_content = EXCLUDED.text_content,
                is_relevant = EXCLUDED.is_relevant,
                diseases = EXCLUDED.diseases,
                symptoms = EXCLUDED.symptoms,
                severity = EXCLUDED.severity,
                confidence = EXCLUDED.confidence,
                is_duplicate = EXCLUDED.is_duplicate,
                dedup_tier = EXCLUDED.dedup_tier,
                similarity_score = EXCLUDED.similarity_score,
                borough = EXCLUDED.borough,
                neighborhood = EXCLUDED.neighborhood,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude,
                location_source = EXCLUDED.location_source,
                extracted_locations = EXCLUDED.extracted_locations,
                author = EXCLUDED.author,
                created_at = EXCLUDED.created_at,
                processed_at = EXCLUDED.processed_at,
                embedding_id = EXCLUDED.embedding_id,
                raw_data = EXCLUDED.raw_data
        """

        execute_values(self.cursor, insert_query, records)
        self.conn.commit()

        logger.info(f"✓ Loaded {len(records)} records")
        return len(records)

    def load_from_directory(self, directory: str, pattern: str = "*.json") -> int:
        """
        Load all JSON files from a directory

        Args:
            directory: Directory containing JSON files
            pattern: File pattern to match

        Returns:
            Total number of records loaded
        """
        logger.info(f"Loading from directory: {directory}")

        file_pattern = os.path.join(directory, pattern)
        json_files = glob.glob(file_pattern)

        logger.info(f"Found {len(json_files)} files")

        total_loaded = 0
        for json_file in json_files:
            try:
                count = self.load_from_json_file(json_file)
                total_loaded += count
            except Exception as e:
                logger.error(f"Failed to load {json_file}: {e}")

        logger.info(f"Total records loaded: {total_loaded}")
        return total_loaded

    def refresh_materialized_views(self):
        """Refresh materialized views"""
        logger.info("Refreshing materialized views...")
        
        self.cursor.execute("REFRESH MATERIALIZED VIEW daily_disease_counts;")
        self.cursor.execute("REFRESH MATERIALIZED VIEW borough_severity_summary;")
        
        self.conn.commit()
        logger.info("✓ Materialized views refreshed")

    def get_statistics(self) -> Dict:
        """Get database statistics"""
        stats = {}

        # Total records
        self.cursor.execute("SELECT COUNT(*) FROM disease_events;")
        stats['total_records'] = self.cursor.fetchone()[0]

        # Relevant records
        self.cursor.execute("SELECT COUNT(*) FROM disease_events WHERE is_relevant = TRUE;")
        stats['relevant_records'] = self.cursor.fetchone()[0]

        # Unique records (non-duplicates)
        self.cursor.execute("SELECT COUNT(*) FROM disease_events WHERE is_duplicate = FALSE;")
        stats['unique_records'] = self.cursor.fetchone()[0]

        # Records by borough
        self.cursor.execute("""
            SELECT borough, COUNT(*) 
            FROM disease_events 
            WHERE borough IS NOT NULL 
            GROUP BY borough 
            ORDER BY COUNT(*) DESC;
        """)
        stats['by_borough'] = dict(self.cursor.fetchall())

        # Top diseases
        self.cursor.execute("""
            SELECT unnest(diseases) AS disease, COUNT(*) 
            FROM disease_events 
            WHERE diseases IS NOT NULL 
            GROUP BY disease 
            ORDER BY COUNT(*) DESC 
            LIMIT 10;
        """)
        stats['top_diseases'] = dict(self.cursor.fetchall())

        # Date range
        self.cursor.execute("""
            SELECT MIN(timestamp), MAX(timestamp) 
            FROM disease_events;
        """)
        min_date, max_date = self.cursor.fetchone()
        stats['date_range'] = {
            'earliest': str(min_date) if min_date else None,
            'latest': str(max_date) if max_date else None
        }

        return stats

    def close(self):
        """Close database connection"""
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()
        logger.info("Database connection closed")


def main():
    """Main entry point for loading data into TimescaleDB"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Load processed data into TimescaleDB',
        epilog="""
Pipeline stages:
  1. data/relevance/relevant/  - Relevance-filtered records
  2. data/deduplicated/        - Deduplicated unique records  
  3. data/locations/           - Location-enriched records 
  4. data/embeddings/          - Vector embeddings (different format)

Load from data/locations/ for the most complete processed data.
        """
    )
    parser.add_argument('--host', default='localhost', help='Database host')
    parser.add_argument('--port', type=int, default=5432, help='Database port')
    parser.add_argument('--database', default='nyc_disease_surveillance', help='Database name')
    parser.add_argument('--user', default='postgres', help='Database user')
    parser.add_argument('--password', default='postgres', help='Database password')
    
    parser.add_argument('--data-dir', default='data/locations',
                        help='Directory containing processed data (default: locations with full enrichment)')
    parser.add_argument('--init-schema', action='store_true',
                        help='Initialize database schema')
    parser.add_argument('--refresh-views', action='store_true',
                        help='Refresh materialized views after loading')

    args = parser.parse_args()

    # Initialize client
    client = TimescaleDBClient(
        host=args.host,
        port=args.port,
        database=args.database,
        user=args.user,
        password=args.password
    )

    try:
        client.connect()

        # Initialize schema if requested
        if args.init_schema:
            client.create_schema()

        # Load data
        logger.info("="*60)
        logger.info("Loading Data into TimescaleDB")
        logger.info("="*60)

        total_loaded = client.load_from_directory(args.data_dir)

        # Refresh views if requested
        if args.refresh_views:
            client.refresh_materialized_views()

        # Print statistics
        stats = client.get_statistics()
        logger.info("\n" + "="*60)
        logger.info("TimescaleDB Statistics")
        logger.info("="*60)
        logger.info(f"Total Records: {stats['total_records']}")
        logger.info(f"Relevant Records: {stats['relevant_records']}")
        logger.info(f"Unique Records: {stats['unique_records']}")
        
        if stats['date_range']['earliest']:
            logger.info(f"Date Range: {stats['date_range']['earliest']} to {stats['date_range']['latest']}")
        
        if stats['by_borough']:
            logger.info("\nRecords by Borough:")
            for borough, count in stats['by_borough'].items():
                logger.info(f"  {borough}: {count}")
        
        if stats['top_diseases']:
            logger.info("\nTop Diseases:")
            for disease, count in list(stats['top_diseases'].items())[:5]:
                logger.info(f"  {disease}: {count}")

        logger.info("\n✓ TimescaleDB loading completed successfully!")

    except Exception as e:
        logger.error(f"Error: {e}")
        raise
    finally:
        client.close()


if __name__ == "__main__":
    main()