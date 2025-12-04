"""
Bluesky Scraper for NYC Disease Surveillance
Monitors Bluesky posts for health-related content in NYC
"""

import json
import logging
import time
from datetime import datetime
from typing import List, Dict, Optional
from atproto import Client, models
from kafka import KafkaProducer


class BlueskyScraper:
    """
    Scrapes Bluesky posts for disease surveillance keywords
    """

    # Health-related keywords for NYC disease surveillance
    HEALTH_KEYWORDS = [
        "sick", "illness", "flu", "covid", "fever", "cough", "symptom",
        "disease", "outbreak", "virus", "infection", "contagious",
        "respiratory", "gastrointestinal", "nausea", "vomiting", "diarrhea",
        "sore throat", "headache", "body aches", "fatigue", "emergency room",
        "urgent care", "doctor", "hospital", "clinic", "test positive"
    ]

    # NYC location keywords
    NYC_KEYWORDS = [
        "nyc", "new york city", "manhattan", "brooklyn", "queens",
        "bronx", "staten island", "new york", "ny"
    ]

    def __init__(self,
                 bluesky_handle: Optional[str] = None,
                 bluesky_password: Optional[str] = None,
                 kafka_bootstrap_servers: Optional[List[str]] = None,
                 kafka_topic: str = "social-media",
                 enable_kafka: bool = False,
                 output_file: Optional[str] = None):
        """
        Initialize Bluesky scraper

        Args:
            bluesky_handle: Bluesky username/handle (optional for anonymous access)
            bluesky_password: Bluesky password (optional for anonymous access)
            kafka_bootstrap_servers: List of Kafka broker addresses
            kafka_topic: Kafka topic to publish to
            enable_kafka: Whether to send data to Kafka
            output_file: Optional JSON file to save posts
        """
        self.client = Client()
        self.enable_kafka = enable_kafka
        self.output_file = output_file
        self.kafka_topic = kafka_topic
        self.authenticated = False

        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger(__name__)

        # Setup Kafka producer if enabled
        # self.producer = None
        # if enable_kafka and kafka_bootstrap_servers:
        #     try:
        #         self.producer = KafkaProducer(
        #             bootstrap_servers=kafka_bootstrap_servers,
        #             value_serializer=lambda v: json.dumps(v).encode('utf-8'),
        #             key_serializer=lambda k: k.encode('utf-8') if k else None
        #         )
        #         self.logger.info(f"Kafka producer connected to {kafka_bootstrap_servers}")
        #     except Exception as e:
        #         self.logger.error(f"Failed to connect to Kafka: {e}")
        #         self.producer = None

        # Cache for seen posts (deduplication)
        self.seen_posts = set()

        # Login if credentials provided
        if bluesky_handle and bluesky_password:
            try:
                self.client.login(bluesky_handle, bluesky_password)
                self.authenticated = True
                self.logger.info(f"Successfully authenticated as {bluesky_handle}")
            except Exception as e:
                self.logger.warning(f"Failed to authenticate: {e}")
                self.logger.info("Continuing without authentication (limited functionality)")

    def _contains_health_keywords(self, text: str) -> bool:
        """Check if text contains health-related keywords"""
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in self.HEALTH_KEYWORDS)

    def _contains_nyc_keywords(self, text: str) -> bool:
        """Check if text contains NYC location keywords"""
        text_lower = text.lower()
        return any(keyword in text_lower for keyword in self.NYC_KEYWORDS)

    def _is_relevant_post(self, text: str) -> bool:
        """Determine if a post is relevant for disease surveillance"""
        return self._contains_health_keywords(text) and self._contains_nyc_keywords(text)

    def _extract_post_data(self, post) -> Dict:
        """
        Extract relevant data from a Bluesky post

        Args:
            post: Bluesky post object

        Returns:
            Dictionary with extracted post data
        """
        try:
            # Extract basic post information
            post_data = {
                "platform": "bluesky",
                "post_id": post.uri,
                "author": post.author.handle if hasattr(post, 'author') else None,
                "author_did": post.author.did if hasattr(post, 'author') else None,
                "text": post.record.text if hasattr(post.record, 'text') else "",
                "created_at": post.record.created_at if hasattr(post.record, 'created_at') else None,
                "scraped_at": datetime.utcnow().isoformat(),
                "reply_count": post.reply_count if hasattr(post, 'reply_count') else 0,
                "repost_count": post.repost_count if hasattr(post, 'repost_count') else 0,
                "like_count": post.like_count if hasattr(post, 'like_count') else 0,
                "language": post.record.langs[0] if hasattr(post.record, 'langs') and post.record.langs else None,
            }

            # Extract hashtags if present
            if hasattr(post.record, 'facets') and post.record.facets:
                hashtags = []
                for facet in post.record.facets:
                    for feature in facet.features:
                        if hasattr(feature, 'tag'):
                            hashtags.append(feature.tag)
                post_data["hashtags"] = hashtags

            return post_data

        except Exception as e:
            self.logger.error(f"Error extracting post data: {e}")
            return None

    def _send_to_kafka(self, post_data: Dict):
        """Send post data to Kafka topic"""
        if self.producer:
            try:
                self.producer.send(
                    self.kafka_topic,
                    key=post_data.get('post_id'),
                    value=post_data
                )
                self.logger.debug(f"Sent post {post_data['post_id']} to Kafka")
            except Exception as e:
                self.logger.error(f"Failed to send to Kafka: {e}")

    def _save_to_file(self, posts: List[Dict]):
        """Save all posts to JSON file as an array"""
        if self.output_file:
            try:
                # Read existing posts if file exists
                existing_posts = []
                if os.path.exists(self.output_file):
                    try:
                        with open(self.output_file, 'r') as f:
                            existing_posts = json.load(f)
                    except (json.JSONDecodeError, FileNotFoundError):
                        existing_posts = []

                # Combine existing and new posts
                all_posts = existing_posts + posts

                # Write all posts as JSON array
                with open(self.output_file, 'w') as f:
                    json.dump(all_posts, f, indent=2)

            except Exception as e:
                self.logger.error(f"Failed to write to file: {e}")

    def search_posts(self, query: str, limit: int = 100) -> List[Dict]:
        """
        Search Bluesky posts by query

        Args:
            query: Search query string
            limit: Maximum number of posts to retrieve

        Returns:
            List of relevant post data dictionaries
        """
        relevant_posts = []

        try:
            self.logger.info(f"Searching Bluesky for: '{query}'")

            # Search posts using the AT Protocol
            response = self.client.app.bsky.feed.search_posts(
                params={"q": query, "limit": limit}
            )

            if response and response.posts:
                self.logger.info(f"Found {len(response.posts)} posts")

                for post in response.posts:
                    # Skip if already seen
                    if post.uri in self.seen_posts:
                        continue

                    # Extract text
                    text = post.record.text if hasattr(post.record, 'text') else ""

                    # Check relevance
                    if self._is_relevant_post(text):
                        post_data = self._extract_post_data(post)

                        if post_data:
                            relevant_posts.append(post_data)
                            self.seen_posts.add(post.uri)

                            # Send to Kafka if enabled
                            if self.enable_kafka:
                                self._send_to_kafka(post_data)

                            self.logger.info(f"Relevant post found: {post.uri}")

            self.logger.info(f"Collected {len(relevant_posts)} relevant posts")

            # Save all posts to file after collection
            if self.output_file and relevant_posts:
                self._save_to_file(relevant_posts)

        except Exception as e:
            self.logger.error(f"Error searching posts: {e}")

        return relevant_posts

    def stream_health_posts(self, interval: int = 300, max_iterations: Optional[int] = None):
        """
        Continuously stream health-related posts from Bluesky

        Args:
            interval: Time in seconds between searches (default: 5 minutes)
            max_iterations: Maximum number of iterations (None = infinite)
        """
        iteration = 0

        self.logger.info("Starting Bluesky health post streaming...")

        try:
            while max_iterations is None or iteration < max_iterations:
                # Search with health + NYC keywords
                for health_keyword in ["sick NYC", "flu NYC", "covid NYC", "illness NYC"]:
                    try:
                        self.search_posts(query=health_keyword, limit=25)
                        time.sleep(2)  # Rate limiting
                    except Exception as e:
                        self.logger.error(f"Error in search iteration: {e}")
                        time.sleep(10)

                iteration += 1
                self.logger.info(f"Completed iteration {iteration}. Sleeping for {interval} seconds...")
                time.sleep(interval)

        except KeyboardInterrupt:
            self.logger.info("Streaming stopped by user")
        finally:
            self.close()

    def close(self):
        """Clean up resources"""
        if self.producer:
            self.logger.info("Flushing and closing Kafka producer...")
            self.producer.flush()
            self.producer.close()


if __name__ == "__main__":
    # Example usage - standalone mode (no Kafka)
    scraper = BlueskyScraper(
        enable_kafka=False,
        output_file="bluesky_health_posts.jsonl"
    )

    # Run a single search
    posts = scraper.search_posts("sick NYC", limit=50)
    print(f"\nCollected {len(posts)} relevant posts")

    # Or run continuous streaming (uncomment to use)
    # scraper.stream_health_posts(interval=300, max_iterations=5)
