#!/usr/bin/env python3
"""
Load embeddings into ChromaDB
Wrapper script for chromadb_client
"""

import sys
import os

# Add vector_db to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'database'))

from chromadb_client import main

if __name__ == "__main__":
    main()
