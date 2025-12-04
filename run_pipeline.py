"""
run_pipeline.py
Main script - Runs the complete pipeline:
1. Scrapes ALL health data
2. Saves to JSON files
3. Publishes ALL JSON files to Kafka (Reddit + any other sources)
"""

from datetime import datetime
import sys
import subprocess
import sys

# Import the other scripts
import kafka_publisher


def run_complete_pipeline():
    """Run the complete Health → Kafka pipeline"""
    print("\n" + "#"*60)
    print("# UNIFIED HEALTH DATA PIPELINE")
    print("# ALL Scrapers → JSON → Kafka")
    print("#"*60)
    print(f"# Started at: {datetime.now()}")
    print("#"*60 + "\n")


    try:
        # STEP 1: Scrape All Health Data
        print("\nSTEP 1: Scraping Reddit and saving to JSON...")
        scrape_red = subprocess.run([sys.executable, "scrapers/redditscraper.py"], capture_output=False, text=True, check=True)

        print("\nSTEP 1: Scraping Bluesky and saving to JSON...")
        scrape_blue = subprocess.run([sys.executable, "scrapers/run_bluesky_scraper.py"], capture_output=False, text=True, check=True)

        print("\nSTEP 1: Scraping 311 and saving to JSON...")
        scrape_311 = subprocess.run([sys.executable, "scrapers/scraper_311.py"], capture_output=False, text=True, check=True)

        print("\nSTEP 1: Scraping rss and saving to JSON...")
        scrape_rss = subprocess.run([sys.executable, "scrapers/scraper_rss.py"], capture_output=False, text=True, check=True)

        print("\nSTEP 1: Scraping nyc_health and saving to JSON...")
        scrape_nyc_health = subprocess.run([sys.executable, "scrapers/nyc_health_press_release_scraper.py"], capture_output=False, text=True, check=True)

        print("\nSTEP 1: Scraping nyc_covid and saving to JSON...")
        scrape_nyc_covid = subprocess.run([sys.executable, "scrapers/nyc_covid_rsv_flu_official_scraper.py"], capture_output=False, text=True, check=True)

        # STEP 2: Publish ALL JSON files to Kafka (Reddit + other sources)
        print("\nSTEP 2: Publishing ALL JSON files to Kafka...")
        kafka_results = kafka_publisher.publish_to_kafka()

        # Summary
        print("\n" + "#"*60)
        print("# PIPELINE COMPLETE ✓")
        print("#"*60)
        print(f"#")
        print(f"# SCRAPING RESULTS:")
        print(f"# ALL DATA SCRAPED IN data FOLDER")
        print(f"#")
        print(f"# KAFKA PUBLISHING RESULTS:")

        for topic, count in kafka_results['all_topics'].items():
            print(f"#   {topic}: {count} records")

        print(f"#")
        print(f"# Finished at: {datetime.now()}")
        print("#"*60)
        print(f"\n✓ View your data in Kafka UI: http://localhost:8090")
        print(f"✓ JSON files in: /data folder\n")

        return True

    except Exception as e:
        print("\n" + "!"*60)
        print(f"ERROR: {e}")
        print("!"*60 + "\n")

        print("Troubleshooting:")
        print("1. Check if Kafka is running: docker ps")
        print("2. Check your .env file has correct credentials")
        print("3. Make sure you installed: pip install praw kafka-python python-dotenv")

        import traceback
        traceback.print_exc()

        return False

if __name__ == "__main__":
    success = run_complete_pipeline()
    sys.exit(0 if success else 1)