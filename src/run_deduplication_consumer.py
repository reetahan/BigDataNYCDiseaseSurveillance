#!/usr/bin/env python3
"""
Runner script for Spark Streaming Deduplication Consumer
Ticket 3.2: LLM/NLP-based deduplication filter

Usage:
    python run_deduplication_consumer.py
    python run_deduplication_consumer.py --topics reddit,bluesky
    python run_deduplication_consumer.py --similarity-threshold 0.80
"""

import sys
import os

# Add spark_consumers to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'spark_consumers'))

from deduplication_consumer import main

if __name__ == "__main__":
    print("\n" + "="*70)
    print(" NYC Disease Surveillance - Deduplication Consumer")
    print(" Ticket 3.2: Spark Streaming with LLM-based Deduplication")
    print("="*70 + "\n")

    try:
        main()
    except KeyboardInterrupt:
        print("\n\nConsumer stopped by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
