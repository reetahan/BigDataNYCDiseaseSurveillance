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
import argparse
import os

# Import the other scripts
import kafka_publisher


def run_complete_pipeline(local_mode=False):
    """Run the complete Health → Kafka pipeline"""
    print("\n" + "#"*60)
    print(f"# UNIFIED HEALTH DATA PIPELINE {'(LOCAL MODE)' if local_mode else ''}")
    print("# ALL Scrapers → JSON → Kafka")
    print("#"*60)
    print(f"# Started at: {datetime.now()}")
    print("#"*60 + "\n")


    try:
        # Setup environment for scrapers
        env = os.environ.copy()
        if local_mode:
            env['LOCAL_MODE'] = '1'
        
        # STEP 1: Scrape All Health Data
        print("\nSTEP 1: Scraping Reddit and saving to JSON...")
        subprocess.run([sys.executable, "scrapers/redditscraper.py"], capture_output=False, text=True, check=True, env=env)

        print("\nSTEP 1: Scraping Bluesky and saving to JSON...")
        subprocess.run([sys.executable, "scrapers/run_bluesky_scraper.py"], capture_output=False, text=True, check=True, env=env)

        print("\nSTEP 1: Scraping 311 and saving to JSON...")
        subprocess.run([sys.executable, "scrapers/scraper_311.py"], capture_output=False, text=True, check=True, env=env)

        print("\nSTEP 1: Scraping rss and saving to JSON...")
        subprocess.run([sys.executable, "scrapers/scraper_rss.py"], capture_output=False, text=True, check=True, env=env)

        print("\nSTEP 1: Scraping nyc_health and saving to JSON...")
        subprocess.run([sys.executable, "scrapers/nyc_health_press_release_scraper.py"], capture_output=False, text=True, check=True, env=env)

        print("\nSTEP 1: Scraping nyc_covid and saving to JSON...")
        subprocess.run([sys.executable, "scrapers/nyc_covid_rsv_flu_official_scraper.py"], capture_output=False, text=True, check=True, env=env)

        # STEP 2: Publish ALL JSON files to Kafka
        print("\nSTEP 2: Publishing ALL JSON files to Kafka...")
        kafka_results = kafka_publisher.publish_to_kafka()

        # STEP 3: Run Spark Consumers (optional - can be run separately)
        print("\n" + "#"*60)
        print("# STEP 3: SPARK STREAMING CONSUMERS")
        print("#"*60)
        print("\nNote: Consumers run indefinitely. Press Ctrl+C to stop.")
        print("You can also run them separately:")
        print("  python run_deduplication_consumer.py")
        print("  python run_location_consumer.py")
        
        run_consumers = input("\nRun Spark consumers now? (y/n): ").lower().strip() == 'y'
        
        if run_consumers:
            print("\nStarting Spark consumers in background...")
            print("(Press Ctrl+C to stop all consumers)\n")
            
            # Run consumers as subprocesses
            dedup_process = subprocess.Popen(
                [sys.executable, "run_deduplication_consumer.py"],
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            
            location_process = subprocess.Popen(
                [sys.executable, "run_location_consumer.py"],
                cwd=os.path.dirname(os.path.abspath(__file__))
            )
            
            print(f"✓ Deduplication consumer started (PID: {dedup_process.pid})")
            print(f"✓ Location consumer started (PID: {location_process.pid})")
            print("\nPress Ctrl+C to stop all consumers...\n")
            
            try:
                # Wait for both processes
                dedup_process.wait()
                location_process.wait()
            except KeyboardInterrupt:
                print("\n\nStopping consumers...")
                dedup_process.terminate()
                location_process.terminate()
                dedup_process.wait()
                location_process.wait()
                print("Consumers stopped.")

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
    parser = argparse.ArgumentParser(description='Run the health data pipeline')
    parser.add_argument('--local', action='store_true', help='Run in local mode (no file saving or Kafka publishing)')
    args = parser.parse_args()
    
    success = run_complete_pipeline(local_mode=args.local)
    sys.exit(0 if success else 1)