#!/usr/bin/env python3
"""
Chained Pipeline Runner
Runs all four consumers in sequence: Relevance → Deduplication → Location → Embeddings

Pipeline Flow:
1. Relevance Consumer (3.1): Kafka → data/relevance/relevant/
2. Deduplication Consumer (3.2): data/relevance/relevant/ → data/deduplicated/
3. Location Consumer (3.3): data/deduplicated/unique_*.json → data/locations/
4. Embedding Consumer (3.4): data/locations/ → data/embeddings/

Usage:
    python run_chained_pipeline.py
    python run_chained_pipeline.py --skip-relevance  # Start from dedupe
    python run_chained_pipeline.py --skip-relevance --skip-dedupe  # Start from location
    python run_chained_pipeline.py --skip-relevance --skip-dedupe --skip-location  # Only embeddings
"""

import sys
import os
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Load .env
repo_root = Path(__file__).parent.parent
env_path = repo_root / '.env'
load_dotenv(dotenv_path=env_path)

# Add spark_consumers to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'spark_consumers'))

from relevance_consumer import RelevanceConsumer
from deduplication_consumer import DeduplicationConsumer
from location_consumer import LocationConsumer
from embedding_consumer import EmbeddingConsumer


def print_banner(step_num, step_name, description):
    """Print a fancy banner for each pipeline step"""
    print("\n" + "="*80)
    print(f" STEP {step_num}: {step_name}")
    print(f" {description}")
    print("="*80 + "\n")


def run_pipeline(skip_relevance=False, skip_dedupe=False, skip_location=False, skip_embeddings=False):
    """
    Run the complete chained pipeline

    Args:
        skip_relevance: Skip relevance analysis (start from existing data)
        skip_dedupe: Skip deduplication (start from existing dedupe data)
        skip_location: Skip location extraction
        skip_embeddings: Skip embedding generation
    """
    print("\n" + "🚀 "*20)
    print(" "*15 + "NYC DISEASE SURVEILLANCE - CHAINED PIPELINE")
    print("🚀 "*20 + "\n")

    # Step 1: Relevance Analysis (3.1)
    if not skip_relevance:
        print_banner(1, "RELEVANCE ANALYSIS",
                     "Filter for health-relevant content, extract diseases & symptoms")

        relevance_consumer = RelevanceConsumer(
            kafka_bootstrap_servers="localhost:9092",
            kafka_topics="reddit.health,bluesky.health,rss.health,nyc_311.health,nyc_press.health,nyc_covid.health",
            output_dir="data/relevance",
            checkpoint_dir="checkpoints/relevance",
            auto_stop_on_empty=True,  # Auto-stop when Kafka queue is empty (pipeline mode)
            empty_batches_before_stop=3  # Stop after 3 consecutive empty batches
        )

        print("Starting Relevance Consumer...")
        print("Reading from Kafka topics: reddit.health, bluesky.health, rss.health, nyc_311.health, nyc_press.health, nyc_covid.health")
        print("Output: data/relevance/relevant/")
        print("Mode: Auto-stop when all messages processed\n")

        try:
            relevance_consumer.start()
            print("\n✓ Relevance analysis completed")
        except KeyboardInterrupt:
            print("\n✓ Relevance analysis completed (interrupted by user)")
        except Exception as e:
            print(f"\n✗ Relevance analysis failed: {e}")
            return False
    else:
        print_banner(1, "RELEVANCE ANALYSIS (SKIPPED)",
                     "Using existing data from data/relevance/relevant/")

    # Step 2: Deduplication (3.2)
    if not skip_dedupe:
        print_banner(2, "DEDUPLICATION",
                     "Remove duplicate records using 3-tier strategy (hash, fuzzy, semantic)")

        dedupe_consumer = DeduplicationConsumer(
            input_source="file",
            input_path="data/relevance/relevant/",
            output_dir="data/deduplicated",
            checkpoint_dir="checkpoints/deduplication",
            similarity_threshold=0.85,
            fuzzy_threshold=0.90
        )

        print("Starting Deduplication Consumer...")
        print("Reading from: data/relevance/relevant/")
        print("Output: data/deduplicated/unique_*.json\n")

        try:
            dedupe_consumer.start()
            print("\n✓ Deduplication completed")
        except Exception as e:
            print(f"\n✗ Deduplication failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    else:
        print_banner(2, "DEDUPLICATION (SKIPPED)",
                     "Using existing data from data/deduplicated/")

    # Step 3: Location Extraction (3.3)
    if not skip_location:
        print_banner(3, "LOCATION EXTRACTION",
                     "Extract locations and assign to NYC neighborhoods")

        location_consumer = LocationConsumer(
            input_source="file",
            input_path="data/deduplicated/unique_*.json",
            output_dir="data/locations",
            checkpoint_dir="checkpoints/locations",
            spacy_model="en_core_web_sm"
        )

        print("Starting Location Consumer...")
        print("Reading from: data/deduplicated/unique_*.json")
        print("Output: data/locations/\n")

        try:
            location_consumer.start()
            print("\n✓ Location extraction completed")
        except Exception as e:
            print(f"\n✗ Location extraction failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    else:
        print_banner(3, "LOCATION EXTRACTION (SKIPPED)",
                     "Skipping location extraction")

    # Step 4: Embedding Generation (3.4)
    if not skip_embeddings:
        print_banner(4, "EMBEDDING GENERATION",
                     "Create vector embeddings for vector database")

        embedding_consumer = EmbeddingConsumer(
            input_source="file",
            input_path="data/locations/",
            output_dir="data/embeddings",
            checkpoint_dir="checkpoints/embeddings",
            embedding_model="all-MiniLM-L6-v2",
            embedding_dim=384
        )

        print("Starting Embedding Consumer...")
        print("Reading from: data/locations/")
        print("Output: data/embeddings/\n")

        try:
            embedding_consumer.start()
            print("\n✓ Embedding generation completed")
        except Exception as e:
            print(f"\n✗ Embedding generation failed: {e}")
            import traceback
            traceback.print_exc()
            return False
    else:
        print_banner(4, "EMBEDDING GENERATION (SKIPPED)",
                     "Skipping embedding generation")

    # Pipeline complete
    print("\n" + "🎉 "*20)
    print(" "*20 + "PIPELINE COMPLETED SUCCESSFULLY!")
    print("🎉 "*20 + "\n")

    print("Output Summary:")
    print("  1. Relevance analysis: data/relevance/relevant/")
    print("  2. Deduplicated data: data/deduplicated/unique_*.json")
    print("  3. Location-enriched: data/locations/")
    print("  4. Vector embeddings: data/embeddings/\n")

    return True


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Run chained pipeline: Relevance → Dedupe → Location → Embeddings',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run full pipeline (Kafka → Relevance → Dedupe → Location → Embeddings)
  python run_chained_pipeline.py

  # Start from deduplication (use existing relevance data)
  python run_chained_pipeline.py --skip-relevance

  # Only run location and embeddings
  python run_chained_pipeline.py --skip-relevance --skip-dedupe

  # Only run embeddings
  python run_chained_pipeline.py --skip-relevance --skip-dedupe --skip-location
        """
    )

    parser.add_argument('--skip-relevance', action='store_true',
                        help='Skip relevance analysis (use existing data)')
    parser.add_argument('--skip-dedupe', action='store_true',
                        help='Skip deduplication (use existing data)')
    parser.add_argument('--skip-location', action='store_true',
                        help='Skip location extraction')
    parser.add_argument('--skip-embeddings', action='store_true',
                        help='Skip embedding generation')

    args = parser.parse_args()

    # Validate flags
    if args.skip_relevance and args.skip_dedupe and args.skip_location and args.skip_embeddings:
        print("ERROR: Cannot skip all steps!")
        sys.exit(1)

    try:
        success = run_pipeline(
            skip_relevance=args.skip_relevance,
            skip_dedupe=args.skip_dedupe,
            skip_location=args.skip_location,
            skip_embeddings=args.skip_embeddings
        )

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n\nPipeline interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\nPipeline failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
