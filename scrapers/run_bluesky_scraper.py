#!/usr/bin/env python3
"""
Main runner script for Bluesky scraper
Usage:
    python run_bluesky_scraper.py --mode single --query "sick NYC"
    python run_bluesky_scraper.py --mode stream --interval 300
"""

import argparse
import sys
import os

# Add scrapers directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scrapers'))

from bluesky.scraper import BlueskyScraper
from bluesky.config import Config

def ensure_data_folder():
    """Create data folder if it doesn't exist"""
    os.makedirs('data/bluesky', exist_ok=True)

def main():
    ensure_data_folder()
    parser = argparse.ArgumentParser(description='Bluesky Health Surveillance Scraper')

    parser.add_argument(
        '--mode',
        choices=['single', 'stream'],
        default='single',
        help='Scraping mode: single search or continuous streaming'
    )

    parser.add_argument(
        '--query',
        type=str,
        default='sick NYC',
        help='Search query for single mode'
    )

    parser.add_argument(
        '--limit',
        type=int,
        default=Config.MAX_POSTS_PER_SEARCH,
        help='Maximum posts per search'
    )

    parser.add_argument(
        '--interval',
        type=int,
        default=Config.SCRAPE_INTERVAL,
        help='Time between searches in stream mode (seconds)'
    )

    parser.add_argument(
        '--iterations',
        type=int,
        default=None,
        help='Max iterations for stream mode (None = infinite)'
    )

    parser.add_argument(
        '--output',
        type=str,
        default=Config.OUTPUT_FILE,
        help='Output JSON file path'
    )

    parser.add_argument(
        '--kafka',
        action='store_true',
        help='Enable Kafka producer'
    )

    args = parser.parse_args()

    # Initialize scraper
    scraper = BlueskyScraper(
        bluesky_handle=Config.BLUESKY_HANDLE,
        bluesky_password=Config.BLUESKY_PASSWORD,
        kafka_bootstrap_servers=Config.KAFKA_BOOTSTRAP_SERVERS if args.kafka else None,
        kafka_topic=Config.KAFKA_TOPIC,
        enable_kafka=args.kafka or Config.ENABLE_KAFKA,
        output_file=args.output
    )

    print(f"🦋 Bluesky Health Surveillance Scraper")
    print(f"Mode: {args.mode}")
    print(f"Output: {args.output}")
    print(f"Kafka: {'Enabled' if args.kafka or Config.ENABLE_KAFKA else 'Disabled'}")
    print("-" * 60)

    try:
        if args.mode == 'single':
            # Single search mode
            print(f"Searching for: '{args.query}' (limit: {args.limit})")
            posts = scraper.search_posts(query=args.query, limit=args.limit)
            print(f"\nCollected {len(posts)} relevant posts")

            if posts:
                print("\nSample post:")
                print(f"  Author: {posts[0]['author']}")
                print(f"  Text: {posts[0]['text'][:100]}...")
                print(f"  Created: {posts[0]['created_at']}")

        elif args.mode == 'stream':
            # Continuous streaming mode
            print(f"Starting continuous streaming (interval: {args.interval}s)")
            if args.iterations:
                print(f"Max iterations: {args.iterations}")
            print("Press Ctrl+C to stop\n")

            scraper.stream_health_posts(
                interval=args.interval,
                max_iterations=args.iterations
            )

    except KeyboardInterrupt:
        print("\n\nScraper stopped by user")
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1
    finally:
        scraper.close()

    print("\n✅ Scraper finished successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())