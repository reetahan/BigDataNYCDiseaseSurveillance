#!/usr/bin/env python3
"""
Runner script for Spark Streaming Relevance Analysis Consumer
Ticket 3.1: LLM-based relevance filtering and health entity extraction

Usage:
    python run_relevance_consumer.py
    python run_relevance_consumer.py --topics reddit,bluesky
    python run_relevance_consumer.py --batch-size 20
"""

import sys
import os
from pathlib import Path

# Load .env BEFORE any other imports
from dotenv import load_dotenv
repo_root = Path(__file__).parent.parent  # Go up to repo root from src/
env_path = repo_root / '.env'
load_dotenv(dotenv_path=env_path)

# Add spark_consumers to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'spark_consumers'))

from relevance_consumer import main

if __name__ == "__main__":
    print("\n" + "="*70)
    print(" NYC Disease Surveillance - Relevance Analysis Consumer")
    print(" Ticket 3.1: Spark Streaming with LLM-based Health Filtering")
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