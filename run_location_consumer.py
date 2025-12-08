#!/usr/bin/env python3
"""
Runner script for Location Extraction Consumer
Ticket 3.3: Extract locations and assign to NYC neighborhoods
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from spark_consumers.location_consumer import main

if __name__ == "__main__":
    main()
