#!/usr/bin/env python3
"""
Runner script for Embedding Consumer (Ticket 3.4)
Generates vector embeddings from location-enriched data
"""

import sys
import os

# Add spark_consumers to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'spark_consumers'))

from embedding_consumer import main

if __name__ == "__main__":
    main()
