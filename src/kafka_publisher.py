"""
kafka_publisher.py (FOLDER-BASED)
Publishes ALL JSON files from folders to Kafka topics
- Scans entire folders for JSON files
- Automatically processes all .json files
- Creates topics based on folder/file structure
"""

import json
from datetime import datetime
from kafka import KafkaProducer, KafkaAdminClient
from kafka.admin import NewTopic
from kafka.errors import TopicAlreadyExistsError
import os
import glob
import hashlib
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class FolderBasedKafkaPublisher:
    """
    Kafka publisher that processes entire folders of JSON files
    Tracks published files to avoid duplicates
    """

    def __init__(self, bootstrap_servers='localhost:9092', tracking_file='data/.kafka_published_files.json'):
        self.bootstrap_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', bootstrap_servers)
        self.tracking_file = tracking_file

        # Load tracking data (which files have been published)
        self.published_files = self.load_tracking_data()

        # Connect to Kafka
        self.producer = KafkaProducer(
            bootstrap_servers=self.bootstrap_servers.split(','),
            value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None
        )

        self.admin_client = KafkaAdminClient(
            bootstrap_servers=self.bootstrap_servers.split(','),
            client_id='folder_publisher_admin'
        )

        print(f"✓ Connected to Kafka: {self.bootstrap_servers}")
        print(f"✓ Tracking file: {self.tracking_file}\n")

    def load_tracking_data(self):
        """Load tracking data of published files"""
        if os.path.exists(self.tracking_file):
            try:
                with open(self.tracking_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_tracking_data(self):
        """Save tracking data of published files"""
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.tracking_file), exist_ok=True)

        with open(self.tracking_file, 'w') as f:
            json.dump(self.published_files, f, indent=2)

    def get_file_hash(self, filepath):
        """Get hash of file content to detect changes"""
        hash_md5 = hashlib.md5()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def is_file_already_published(self, filepath, skip_check=False):
        """
        Check if file has already been published

        Args:
            filepath: Path to file
            skip_check: If True, always publish (ignores tracking)

        Returns:
            (already_published, changed)
            already_published: True if file was published before
            changed: True if file content has changed since last publish
        """
        if skip_check:
            return False, False

        filepath = os.path.abspath(filepath)

        if filepath not in self.published_files:
            return False, False

        # File was published before - check if it changed
        old_hash = self.published_files[filepath].get('hash')
        current_hash = self.get_file_hash(filepath)

        if old_hash != current_hash:
            return True, True  # Published before, but changed

        return True, False  # Published before, no changes

    def mark_file_as_published(self, filepath, topic_name, record_count):
        """Mark a file as published in tracking data"""
        filepath = os.path.abspath(filepath)

        self.published_files[filepath] = {
            'topic': topic_name,
            'published_at': datetime.now().isoformat(),
            'record_count': record_count,
            'hash': self.get_file_hash(filepath)
        }

    def create_topic(self, topic_name, num_partitions=3, replication_factor=1):
        """Create a Kafka topic"""
        try:
            topic = NewTopic(
                name=topic_name,
                num_partitions=num_partitions,
                replication_factor=replication_factor
            )
            self.admin_client.create_topics([topic])
            print(f"✓ Created topic: {topic_name} ({num_partitions} partitions)")
        except TopicAlreadyExistsError:
            print(f"⚠ Topic already exists: {topic_name}")
        except Exception as e:
            print(f"✗ Error creating topic {topic_name}: {e}")

    def load_json_data(self, filepath):
        """Load data from JSON file"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Handle different JSON structures
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                # Try common keys that contain arrays
                for key in ['data', 'results', 'items', 'records', 'posts', 'tweets', 'articles']:
                    if key in data and isinstance(data[key], list):
                        return data[key]
                # If no array found, return the dict as single item
                return [data]
            else:
                return [data]

        except Exception as e:
            print(f"✗ Error reading {filepath}: {e}")
            return []

    def find_json_files(self, folder_path, recursive=True):
        """
        Find all JSON files in a folder

        Args:
            folder_path: Path to folder
            recursive: If True, search subfolders too

        Returns:
            List of JSON file paths
        """
        if not os.path.exists(folder_path):
            print(f"⚠ Folder not found: {folder_path}")
            return []

        if recursive:
            pattern = os.path.join(folder_path, '**', '*.json')
            json_files = glob.glob(pattern, recursive=True)
        else:
            pattern = os.path.join(folder_path, '*.json')
            json_files = glob.glob(pattern)

        return sorted(json_files)

    def generate_topic_name(self, filepath, base_topic=None):
        return base_topic


    def publish_json_file(self, json_file, topic_name, key_field=None, num_partitions=3, skip_if_published=True):
        """
        Publish a JSON file to Kafka

        Args:
            json_file: Path to JSON file
            topic_name: Kafka topic name
            key_field: Field to use as message key (optional)
            num_partitions: Number of partitions for the topic
            skip_if_published: If True, skip files already published (unless changed)

        Returns:
            Number of messages published
        """
        # Check if already published
        already_published, changed = self.is_file_already_published(json_file, skip_check=not skip_if_published)

        if already_published and not changed:
            print(f"  ⏭️  SKIPPED (already published): {os.path.basename(json_file)}")
            return 0

        if already_published and changed:
            print(f"  🔄 CHANGED (republishing): {os.path.basename(json_file)}")

        # Create topic
        self.create_topic(topic_name, num_partitions=num_partitions)

        # Load data
        records = self.load_json_data(json_file)

        if not records:
            return 0

        # Publish each record
        count = 0
        for record in records:
            # Add metadata
            if isinstance(record, dict):
                record['published_to_kafka_at'] = datetime.now().isoformat()
                record['source_file'] = os.path.basename(json_file)
                record['source_path'] = json_file

            # Determine message key
            key = None
            if key_field and isinstance(record, dict) and key_field in record:
                key = str(record[key_field])
            elif isinstance(record, dict):
                # Try common ID fields
                for id_field in ['id', '_id', 'post_id', 'comment_id', 'tweet_id',
                                'article_id', 'record_id', 'user_id', 'message_id']:
                    if id_field in record:
                        key = str(record[id_field])
                        break

            # Publish to Kafka
            self.producer.send(topic_name, key=key, value=record)
            count += 1

        self.producer.flush()

        # Mark file as published
        if count > 0:
            self.mark_file_as_published(json_file, topic_name, count)

        return count

    def publish_folder(self, folder_config):
        """
        Publish all JSON files from a folder

        Args:
            folder_config: Dict with folder configuration
                {
                    'folder': 'data/reddit',
                    'base_topic': 'reddit.health',     # optional
                    'key_field': 'post_id',            # optional
                    'partitions': 3,                   # optional
                    'recursive': True,                 # optional
                    'skip_if_published': True          # optional - skip already published files
                }

        Returns:
            Dictionary with results per file
        """
        folder_path = folder_config.get('folder')
        base_topic = folder_config.get('base_topic', None)
        key_field = folder_config.get('key_field', None)
        partitions = folder_config.get('partitions', 3)
        recursive = folder_config.get('recursive', True)
        skip_if_published = folder_config.get('skip_if_published', True)

        print(f"\n{'='*60}")
        print(f"Processing folder: {folder_path}")
        print(f"{'='*60}")

        # Find all JSON files
        json_files = self.find_json_files(folder_path, recursive=recursive)

        if not json_files:
            print(f"⚠ No JSON files found in {folder_path}")
            return {}

        print(f"Found {len(json_files)} JSON files\n")

        results = {}
        total_records = 0
        skipped_count = 0

        for json_file in json_files:
            # Generate topic name
            topic_name = self.generate_topic_name(json_file, base_topic)

            print(f"Processing: {json_file}")
            print(f"  → Topic: {topic_name}")

            # Publish file
            count = self.publish_json_file(
                json_file=json_file,
                topic_name=topic_name,
                key_field=key_field,
                num_partitions=partitions,
                skip_if_published=skip_if_published
            )

            if count > 0:
                print(f"  ✓ Published: {count} records\n")
                results[topic_name] = results.get(topic_name, 0) + count
                total_records += count
            elif count == 0:
                skipped_count += 1
                # Skip message already printed in publish_json_file
                print()

        print(f"{'='*60}")
        print(f"Folder complete: {total_records} records published, {skipped_count} files skipped")
        print(f"{'='*60}\n")

        # Save tracking data
        self.save_tracking_data()

        return results

    def publish_all_folders(self, folders_config):
        """
        Publish all JSON files from multiple folders

        Args:
            folders_config: List of folder configurations

        Returns:
            Dictionary with results per topic
        """

        all_results = {}

        for folder_config in folders_config:
            folder_results = self.publish_folder(folder_config)

            # Merge results
            for topic, count in folder_results.items():
                all_results[topic] = all_results.get(topic, 0) + count


        print("\n" + "#"*60)
        print("# PUBLISHING COMPLETE")
        print("#"*60)
        for topic, count in sorted(all_results.items()):
            print(f"  {topic}: {count} records")
        print(f"\nTotal: {sum(all_results.values())} records")
        print("#"*60 + "\n")

        return all_results


    def close(self):
        """Close Kafka connections and save tracking data"""
        self.save_tracking_data()
        self.producer.close()
        self.admin_client.close()
        print("\n✓ Kafka connections closed")
        print(f"✓ Published files tracked in: {self.tracking_file}")

    def reset_tracking(self):
        """Reset tracking data - republish all files next time"""
        self.published_files = {}
        self.save_tracking_data()
        print(f"✓ Tracking data reset. All files will be republished next run.")

    def show_tracking_status(self):
        """Show which files have been published"""
        print(f"\n{'='*60}")
        print(f"PUBLISHED FILES TRACKING STATUS")
        print(f"{'='*60}\n")

        if not self.published_files:
            print("No files tracked yet.\n")
            return

        print(f"Total files published: {len(self.published_files)}\n")

        for filepath, info in sorted(self.published_files.items()):
            print(f"File: {filepath}")
            print(f"  Topic: {info['topic']}")
            print(f"  Published: {info['published_at']}")
            print(f"  Records: {info['record_count']}")
            print(f"  Hash: {info['hash'][:16]}...")
            print()


# ==============================================================
# CONFIGURATION - EDIT THIS SECTION FOR YOUR DATA FOLDERS
# ==============================================================

def get_folders_config():
    """
    Configure your data folders here

    Each folder can contain multiple JSON files
    All files will be automatically discovered and published
    """

    folders = [
        # ===== REDDIT DATA =====
        {
            'folder': 'data/reddit',             # Folder path
            'base_topic': 'reddit.health',       # Base topic name
            'key_field': 'post_id',              # Field to use as key (tries comment_id too)
            'partitions': 3,                     # Number of partitions
            'recursive': False,                  # Don't search subfolders
            'skip_if_published': True            # Skip already published files
        },

        # ===== nyc_covid DATA =====
         {
             'folder': 'data/nyc_covid',
             'base_topic': 'nyc_covid.health',
             'key_field': 'date',
             'partitions': 3,
             'recursive': False,                  # Search subfolders
             'skip_if_published': True
         },

        # ===== nyc_press DATA =====
        {
            'folder': 'data/nyc_press',
            'base_topic': 'nyc_press.health',
            'key_field': 'scraped_at',
            'partitions': 3,
            'recursive': False,  # Search subfolders
            'skip_if_published': True
        },

        # ===== Bluesky DATA =====
        {
            'folder': 'data/bluesky',
            'base_topic': 'bluesky.health',
            'key_field': 'post_id',
            'partitions': 3,
            'recursive': False,  # Search subfolders
            'skip_if_published': True
        },

        # ===== 311 DATA =====
        {
            'folder': 'data/nyc_311',
            'base_topic': 'nyc_311.health',
            'key_field': 'id',
            'partitions': 3,
            'recursive': False,  # Search subfolders
            'skip_if_published': True
        },

        # ===== rss DATA =====
        {
            'folder': 'data/rss',
            'base_topic': 'rss.health',
            'key_field': 'id',
            'partitions': 3,
            'recursive': False,  # Search subfolders
            'skip_if_published': True
        },

        # ===== NEWS DATA =====
        # {
        #     'folder': 'data/news',
        #     'base_topic': 'news.health',
        #     'key_field': 'article_id',
        #     'partitions': 3,
        #     'recursive': True
        # },

        # ===== CDC DATA =====
        # {
        #     'folder': 'data/cdc',
        #     'base_topic': 'cdc.health',
        #     'key_field': 'report_id',
        #     'partitions': 2,
        #     'recursive': False
        # },

        # ===== ALL OTHER JSON FILES =====
        # {
        #     'folder': 'data/scraped',
        #     'base_topic': 'health.data',       # Generic topic
        #     'key_field': None,                 # Auto-detect ID field
        #     'partitions': 3,
        #     'recursive': True                  # Process all subfolders
        # },
    ]

    return folders


# ==============================================================
# MAIN EXECUTION
# ==============================================================

def publish_to_kafka():
    """
    Main function to publish all configured folders to Kafka
    This is called by run_pipeline.py
    """
    publisher = FolderBasedKafkaPublisher()
    folders_config = get_folders_config()
    results = publisher.publish_all_folders(folders_config)
    publisher.close()

    # Return results in expected format for run_pipeline.py
    return {
        'posts': results.get('reddit.health.posts', 0),
        'comments': results.get('reddit.health.comments', 0),
        'all_topics': results
    }


if __name__ == "__main__":
    print("\n" + "#"*60)
    print("# FOLDER-BASED KAFKA PUBLISHER")
    print("# Publishes ALL JSON files from configured folders")
    print("#"*60 + "\n")

    results = publish_to_kafka()

    print(f"\n✓ Done! Published to {len(results['all_topics'])} topics")
    print(f"✓ View your data at: http://localhost:8090")