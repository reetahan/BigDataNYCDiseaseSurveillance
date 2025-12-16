#!/usr/bin/env python3
"""
NYC Disease Surveillance - Master Project Runner
One-click execution: Scrapers → Kafka → Pipeline → Databases → Analysis → Dashboard

This script runs the entire project from start to finish:
1. Start Docker (Kafka + TimescaleDB)
2. Run all scrapers (Reddit, Bluesky, RSS, NYC APIs)
3. Publish data to Kafka
4. Run chained pipeline (Relevance → Dedup → Location → Embeddings)
5. Load embeddings into ChromaDB
6. Load data into TimescaleDB
7. Run spatial clustering analysis (DBSCAN)
8. Run outbreak forecasting (time-series prediction)
9. Deploy real-time dashboard (Streamlit)

Usage:
    python run_project.py                        # Full run + prompt for dashboard
    python run_project.py --dashboard-only       # Just start dashboard
    python run_project.py --skip-scrapers        # Start from existing data
    python run_project.py --skip-analysis        # Skip clustering/forecasting
    python run_project.py --skip-dashboard       # Don't deploy dashboard
"""

import sys
import os
import subprocess
import time
import argparse
from pathlib import Path

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_banner(message, color=Colors.CYAN):
    """Print a colored banner"""
    print(f"\n{color}{'='*80}{Colors.END}")
    print(f"{color}{Colors.BOLD}{message:^80}{Colors.END}")
    print(f"{color}{'='*80}{Colors.END}\n")

def print_step(step_num, title, description):
    """Print step information"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}[STEP {step_num}] {title}{Colors.END}")
    print(f"{Colors.CYAN}{description}{Colors.END}\n")

def run_command(cmd, description, cwd=None, timeout=None):
    """Run a shell command and handle errors"""
    print(f"{Colors.YELLOW}▶ {description}...{Colors.END}")
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            timeout=timeout,
            capture_output=False,
            text=True
        )
        if result.returncode == 0:
            print(f"{Colors.GREEN}✓ {description} completed{Colors.END}")
            return True
        else:
            print(f"{Colors.RED}✗ {description} failed with code {result.returncode}{Colors.END}")
            return False
    except subprocess.TimeoutExpired:
        print(f"{Colors.RED}✗ {description} timed out{Colors.END}")
        return False
    except Exception as e:
        print(f"{Colors.RED}✗ {description} failed: {e}{Colors.END}")
        return False

def check_docker():
    """Check if Docker is running"""
    print_step(0, "DOCKER CHECK", "Verifying Docker is running")
    result = subprocess.run(
        "docker info",
        shell=True,
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        print(f"{Colors.GREEN}✓ Docker is running{Colors.END}")
        return True
    else:
        print(f"{Colors.RED}✗ Docker is not running. Please start Docker first.{Colors.END}")
        return False

def start_kafka():
    """Start Kafka using docker-compose"""
    print_step(1, "KAFKA STARTUP", "Starting Kafka and Zookeeper")

    # Check if already running
    result = subprocess.run(
        "docker-compose ps | grep kafka",
        shell=True,
        capture_output=True,
        text=True
    )

    if "Up" in result.stdout:
        print(f"{Colors.GREEN}✓ Kafka is already running{Colors.END}")
        return True

    # Start Kafka
    success = run_command(
        "docker-compose up -d kafka zookeeper",
        "Starting Kafka containers"
    )

    if success:
        print(f"{Colors.YELLOW}⏳ Waiting 15 seconds for Kafka to initialize...{Colors.END}")
        time.sleep(15)
        print(f"{Colors.GREEN}✓ Kafka is ready{Colors.END}")

    return success

def run_scrapers(use_local=False):
    """Run all data scrapers"""
    print_step(2, "DATA COLLECTION", "Running all scrapers (Reddit, Bluesky, RSS, NYC APIs)")
    
    if use_local:
        # Check if Reddit data exists locally
        reddit_data = list(Path('data/reddit').glob('*.json')) if Path('data/reddit').exists() else []
        bluesky_data = list(Path('data/bluesky').glob('*.json')) if Path('data/bluesky').exists() else []
        
        if not reddit_data and not bluesky_data:
            print(f"{Colors.RED}✗ No local Reddit or Bluesky data found in data/reddit/ or data/bluesky/{Colors.END}")
            print(f"{Colors.RED}  Run without --use-local to scrape fresh data{Colors.END}")
            return False
        
        if reddit_data:
            print(f"{Colors.GREEN}✓ Using local Reddit data: {len(reddit_data)} file(s) in data/reddit/{Colors.END}")
        if bluesky_data:
            print(f"{Colors.GREEN}✓ Using local Bluesky data: {len(bluesky_data)} file(s) in data/bluesky/{Colors.END}")

    scrapers = [
        ("python src/scrapers/redditscraper.py", "Reddit scraper"),
        ("python src/scrapers/run_bluesky_scraper.py", "Bluesky scraper"),
        ("python src/scrapers/scraper_rss.py", "RSS scraper"),
        ("python src/scrapers/scraper_311.py", "NYC 311 scraper"),
        ("python src/scrapers/nyc_health_press_release_scraper.py", "NYC Press scraper"),
        ("python src/scrapers/nyc_covid_rsv_flu_official_scraper.py", "NYC COVID scraper"),
    ]

    all_success = True
    for cmd, desc in scrapers:
        # Skip Reddit and Bluesky scrapers if using local data
        if use_local and ("reddit" in cmd or "bluesky" in cmd):
            print(f"{Colors.CYAN}▶ {desc} (skipped - using local data)...{Colors.END}")
            print(f"{Colors.GREEN}✓ {desc} skipped{Colors.END}")
            continue
            
        success = run_command(cmd, desc, timeout=120)
        if not success:
            print(f"{Colors.YELLOW}⚠ {desc} failed, but continuing...{Colors.END}")
            all_success = False

    return all_success

def publish_to_kafka():
    """Publish scraped data to Kafka"""
    print_step(3, "KAFKA PUBLISHING", "Publishing scraped data to Kafka topics")

    return run_command(
        "python src/kafka_publisher.py",
        "Publishing to Kafka",
        timeout=300
    )

def run_pipeline(skip_relevance=False):
    """Run the complete 4-stage pipeline"""
    if skip_relevance:
        print_step(4, "DATA PIPELINE (3.2-3.4)", "Deduplication → Location → Embeddings (using existing relevance data)")
    else:
        print_step(4, "DATA PIPELINE (3.1-3.4)", "Relevance → Deduplication → Location → Embeddings")

    # Set Java environment for Spark (use existing JAVA_HOME or try to find it)
    java_home = os.environ.get('JAVA_HOME')

    # If JAVA_HOME not set, try to find Java on macOS
    if not java_home and sys.platform == 'darwin':
        result = subprocess.run(
            '/usr/libexec/java_home',
            shell=True,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            java_home = result.stdout.strip()

    # Build environment variables
    if java_home:
        env_vars = (
            f'export JAVA_HOME="{java_home}" && '
            'export PATH="$JAVA_HOME/bin:$PATH" && '
            'export _JAVA_OPTIONS="-Djava.security.manager.allow=true" && '
        )
    else:
        # Just set Java options, rely on system Java
        env_vars = 'export _JAVA_OPTIONS="-Djava.security.manager.allow=true" && '

    skip_flag = "--skip-relevance" if skip_relevance else ""
    return run_command(
        f'{env_vars}python src/run_chained_pipeline.py {skip_flag}',
        "Running chained pipeline",
        timeout=600
    )

def load_chromadb():
    """Load embeddings into ChromaDB"""
    print_step(5, "CHROMADB LOADING", "Loading embeddings into vector database")

    return run_command(
        'python src/load_chromadb.py --embeddings-dir data/embeddings --clear',
        "Loading ChromaDB",
        timeout=120
    )

def start_timescaledb():
    """Start TimescaleDB using docker-compose"""
    print_step(6, "TIMESCALEDB STARTUP", "Starting TimescaleDB for time-series analysis")

    # Check if already running
    result = subprocess.run(
        "docker-compose ps | grep timescaledb",
        shell=True,
        capture_output=True,
        text=True
    )

    if "Up" in result.stdout:
        print(f"{Colors.GREEN}✓ TimescaleDB is already running{Colors.END}")
        return True

    # Start TimescaleDB
    success = run_command(
        "docker-compose up -d timescaledb",
        "Starting TimescaleDB container"
    )

    if success:
        print(f"{Colors.YELLOW}⏳ Waiting 10 seconds for TimescaleDB to initialize...{Colors.END}")
        time.sleep(10)
        print(f"{Colors.GREEN}✓ TimescaleDB is ready{Colors.END}")

    return success

def load_timescaledb():
    """Load data into TimescaleDB"""
    print_step(7, "TIMESCALEDB LOADING", "Loading enriched data into TimescaleDB")

    return run_command(
        'python src/database/psql_db_client.py --input-dir src/data/embeddings',
        "Loading TimescaleDB",
        timeout=300
    )

def run_spatial_clustering():
    """Run spatial clustering analysis"""
    print_step(8, "SPATIAL CLUSTERING", "Analyzing geographic disease hotspots with DBSCAN")

    return run_command(
        'python src/spatial_clustering.py --algorithm dbscan --eps-km 2.0 --min-samples 3',
        "Running spatial clustering",
        timeout=180
    )

def run_outbreak_forecasting():
    """Run disease outbreak forecasting"""
    print_step(9, "OUTBREAK FORECASTING", "Generating 14-day disease outbreak forecasts")

    return run_command(
        'python src/disease_outbreak_forecaster.py',
        "Running outbreak forecasting",
        timeout=180
    )

def deploy_dashboard():
    """Deploy Streamlit dashboard"""
    print_step(10, "DASHBOARD DEPLOYMENT", "Starting real-time surveillance dashboard")

    print(f"{Colors.CYAN}🌐 Dashboard URL: http://localhost:8501{Colors.END}")
    print(f"{Colors.YELLOW}⚠ Dashboard will run in foreground. Press Ctrl+C to stop.{Colors.END}")
    print(f"{Colors.YELLOW}⚠ To run in background, use: streamlit run src/dashboard/app.py &{Colors.END}\n")

    # Run dashboard in foreground (will block)
    return run_command(
        'streamlit run src/dashboard/app.py',
        "Starting Streamlit dashboard",
        timeout=None  # No timeout for dashboard
    )

def print_summary():
    """Print final summary"""
    print_banner("PROJECT RUN COMPLETED!", Colors.GREEN)

    print(f"{Colors.BOLD}📊 Output Summary:{Colors.END}")
    print(f"  1. Scraped data:         {Colors.CYAN}data/scraped/{Colors.END}")
    print(f"  2. Kafka topics:         {Colors.CYAN}reddit, bluesky, rss, nyc_311, nyc_press, nyc_covid{Colors.END}")
    print(f"  3. Relevant records:     {Colors.CYAN}data/relevance/relevant/{Colors.END}")
    print(f"  4. Unique records:       {Colors.CYAN}data/deduplicated/unique_*.json{Colors.END}")
    print(f"  5. Location-enriched:    {Colors.CYAN}src/data/locations/{Colors.END}")
    print(f"  6. Vector embeddings:    {Colors.CYAN}src/data/embeddings/{Colors.END}")
    print(f"  7. ChromaDB:             {Colors.CYAN}data/chromadb/{Colors.END}")
    print(f"  8. TimescaleDB:          {Colors.CYAN}localhost:5432/nyc_disease_surveillance{Colors.END}")
    print(f"  9. Spatial clusters:     {Colors.CYAN}data/spatial_clusters/{Colors.END}")
    print(f" 10. Outbreak forecasts:   {Colors.CYAN}data/forecast/{Colors.END}")
    print(f" 11. Dashboard:            {Colors.CYAN}http://localhost:8501{Colors.END}")

    print(f"\n{Colors.BOLD}🔍 Query ChromaDB:{Colors.END}")
    print(f"  {Colors.CYAN}python src/load_chromadb.py --query \"flu outbreak in Brooklyn\"{Colors.END}")

    print(f"\n{Colors.BOLD}🗄️ Query TimescaleDB:{Colors.END}")
    print(f"  {Colors.CYAN}docker exec -it timescaledb psql -U postgres -d nyc_disease_surveillance{Colors.END}")

    print(f"\n{Colors.BOLD}📈 View Analysis Results:{Colors.END}")
    print(f"  {Colors.CYAN}cat data/spatial_clusters/cluster_analysis_*.json | python -m json.tool{Colors.END}")
    print(f"  {Colors.CYAN}cat data/forecast/outbreak_forecast.csv{Colors.END}")

    print(f"\n{Colors.BOLD}🌐 Access Dashboard:{Colors.END}")
    print(f"  {Colors.CYAN}Open http://localhost:8501 in your browser{Colors.END}")
    print()

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='NYC Disease Surveillance - Master Project Runner',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run everything from scratch (will prompt for dashboard at end)
  python run_project.py

  # Use existing Reddit and Bluesky data (data/reddit/*.json, data/bluesky/*.json)
  python run_project.py --use-local

  # Skip scrapers (use existing data)
  python run_project.py --skip-scrapers

  # Skip databases (ChromaDB + TimescaleDB)
  python run_project.py --skip-chromadb --skip-timescaledb

  # Skip analysis (spatial clustering + forecasting)
  python run_project.py --skip-analysis

  # Run full pipeline but don't deploy dashboard
  python run_project.py --skip-dashboard

  # Just start the dashboard (assumes data already processed)
  python run_project.py --dashboard-only
        """
    )

    parser.add_argument('--use-local', action='store_true',
                        help='Use existing Reddit and Bluesky data from data/reddit/ and data/bluesky/ instead of scraping')
    parser.add_argument('--skip-scrapers', action='store_true',
                        help='Skip data scraping (use existing data)')
    parser.add_argument('--skip-publishing', action='store_true',
                        help='Skip Kafka publishing (use existing Kafka topics)')
    parser.add_argument('--skip-chromadb', action='store_true',
                        help='Skip ChromaDB loading')
    parser.add_argument('--skip-timescaledb', action='store_true',
                        help='Skip TimescaleDB loading')
    parser.add_argument('--skip-analysis', action='store_true',
                        help='Skip spatial clustering and forecasting analysis')
    parser.add_argument('--skip-dashboard', action='store_true',
                        help='Skip dashboard deployment')
    parser.add_argument('--skip-kafka-start', action='store_true',
                        help='Skip Kafka startup (assume already running)')
    parser.add_argument('--dashboard-only', action='store_true',
                        help='Only deploy dashboard (skip all other steps)')

    args = parser.parse_args()

    print_banner("NYC DISEASE SURVEILLANCE - MASTER PROJECT RUNNER", Colors.HEADER)

    start_time = time.time()

    # Dashboard-only mode
    if args.dashboard_only:
        print_step(0, "DASHBOARD-ONLY MODE", "Skipping all processing steps")
        deploy_dashboard()
        return

    # Step 0: Check Docker
    if not check_docker():
        print(f"\n{Colors.RED}❌ FAILED: Docker is not running{Colors.END}")
        sys.exit(1)

    # Step 1: Start Kafka
    if not args.skip_kafka_start:
        if not start_kafka():
            print(f"\n{Colors.RED}❌ FAILED: Could not start Kafka{Colors.END}")
            sys.exit(1)
    else:
        print_step(1, "KAFKA STARTUP (SKIPPED)", "Using existing Kafka instance")

    # Step 2: Run scrapers
    if not args.skip_scrapers:
        if not run_scrapers(use_local=args.use_local):
            if args.use_local:
                print(f"\n{Colors.RED}❌ FAILED: No local data found{Colors.END}")
                sys.exit(1)
            else:
                print(f"\n{Colors.YELLOW}⚠ WARNING: Some scrapers failed, but continuing...{Colors.END}")
    else:
        print_step(2, "DATA COLLECTION (SKIPPED)", "Using existing scraped data")

    # Step 3: Publish to Kafka
    if not args.skip_publishing:
        if not publish_to_kafka():
            print(f"\n{Colors.YELLOW}⚠ WARNING: Kafka publishing failed, but continuing...{Colors.END}")
    else:
        print_step(3, "KAFKA PUBLISHING (SKIPPED)", "Using existing Kafka topics")

    # Step 4: Run pipeline
    # Skip relevance stage if we're skipping publishing (no Kafka topics)
    if not run_pipeline(skip_relevance=args.skip_publishing):
        print(f"\n{Colors.RED}❌ FAILED: Pipeline execution failed{Colors.END}")
        sys.exit(1)

    # Step 5: Load ChromaDB
    if not args.skip_chromadb:
        if not load_chromadb():
            print(f"\n{Colors.YELLOW}⚠ WARNING: ChromaDB loading failed{Colors.END}")
    else:
        print_step(5, "CHROMADB LOADING (SKIPPED)", "Skipping vector database loading")

    # Step 6: Start TimescaleDB
    if not args.skip_timescaledb:
        if not start_timescaledb():
            print(f"\n{Colors.RED}❌ FAILED: Could not start TimescaleDB{Colors.END}")
            print(f"{Colors.YELLOW}⚠ Continuing without TimescaleDB...{Colors.END}")
    else:
        print_step(6, "TIMESCALEDB STARTUP (SKIPPED)", "Using existing TimescaleDB instance")

    # Step 7: Load TimescaleDB
    if not args.skip_timescaledb:
        if not load_timescaledb():
            print(f"\n{Colors.YELLOW}⚠ WARNING: TimescaleDB loading failed{Colors.END}")
    else:
        print_step(7, "TIMESCALEDB LOADING (SKIPPED)", "Skipping TimescaleDB data loading")

    # Step 8: Run Spatial Clustering
    if not args.skip_analysis:
        if not run_spatial_clustering():
            print(f"\n{Colors.YELLOW}⚠ WARNING: Spatial clustering failed{Colors.END}")
    else:
        print_step(8, "SPATIAL CLUSTERING (SKIPPED)", "Skipping spatial analysis")

    # Step 9: Run Outbreak Forecasting
    if not args.skip_analysis:
        if not run_outbreak_forecasting():
            print(f"\n{Colors.YELLOW}⚠ WARNING: Outbreak forecasting failed{Colors.END}")
    else:
        print_step(9, "OUTBREAK FORECASTING (SKIPPED)", "Skipping forecasting analysis")

    # Summary
    elapsed = time.time() - start_time
    print_summary()
    print(f"{Colors.BOLD}⏱ Total execution time: {elapsed:.1f} seconds{Colors.END}\n")

    # Step 10: Deploy Dashboard (if not skipped)
    if not args.skip_dashboard:
        print(f"\n{Colors.BOLD}{Colors.CYAN}Press Enter to deploy dashboard, or Ctrl+C to exit...{Colors.END}")
        try:
            input()
            deploy_dashboard()
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}Dashboard deployment skipped{Colors.END}")
    else:
        print_step(10, "DASHBOARD (SKIPPED)", "Skipping dashboard deployment")
        print(f"\n{Colors.CYAN}To start dashboard manually:{Colors.END}")
        print(f"  {Colors.CYAN}streamlit run src/dashboard/app.py{Colors.END}\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}⚠ Project run interrupted by user{Colors.END}")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n{Colors.RED}❌ Unexpected error: {e}{Colors.END}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
