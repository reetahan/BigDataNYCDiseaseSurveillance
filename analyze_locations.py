#!/usr/bin/env python3
"""
Quick analysis of location data in processed JSON files
"""
import json
from pathlib import Path
from collections import Counter

def analyze_location_files():
    location_dir = Path('data/locations')
    
    total_records = 0
    has_borough = 0
    has_neighborhood = 0
    has_lat_lon = 0
    has_any_location = 0
    
    sources = Counter()
    boroughs = Counter()
    neighborhoods = Counter()
    location_sources = Counter()
    
    print("Analyzing location files...")
    
    for json_file in location_dir.glob('*.json'):
        print(f"  Reading {json_file.name}...")
        with open(json_file, 'r') as f:
            data = json.load(f)
        
        for record in data:
            total_records += 1
            
            # Extract source
            source = 'unknown'
            if 'original_data' in record:
                try:
                    od = json.loads(record['original_data']) if isinstance(record['original_data'], str) else record['original_data']
                    source_file = od.get('source_file', '')
                    if 'reddit' in source_file.lower():
                        source = 'reddit'
                    elif 'bluesky' in source_file.lower():
                        source = 'bluesky'
                    elif '311' in source_file:
                        source = 'nyc_311'
                except:
                    pass
            sources[source] += 1
            
            # Extract location
            loc = record.get('location_extraction', {})
            if isinstance(loc, str):
                try:
                    loc = json.loads(loc)
                except:
                    loc = {}
            
            borough = loc.get('borough')
            neighborhood = loc.get('neighborhood')
            lat = loc.get('latitude')
            lon = loc.get('longitude')
            loc_source = loc.get('location_source')
            
            if borough:
                has_borough += 1
                boroughs[borough] += 1
            if neighborhood:
                has_neighborhood += 1
                neighborhoods[neighborhood] += 1
            if lat and lon:
                has_lat_lon += 1
            if loc_source:
                location_sources[loc_source] += 1
            if borough or neighborhood or (lat and lon):
                has_any_location += 1
    
    # Print summary
    print("\n" + "="*80)
    print("LOCATION DATA ANALYSIS")
    print("="*80)
    print(f"\nTotal records: {total_records:,}")
    print(f"Records with borough: {has_borough:,} ({100*has_borough/total_records:.2f}%)")
    print(f"Records with neighborhood: {has_neighborhood:,} ({100*has_neighborhood/total_records:.2f}%)")
    print(f"Records with coordinates: {has_lat_lon:,} ({100*has_lat_lon/total_records:.2f}%)")
    print(f"Records with ANY location: {has_any_location:,} ({100*has_any_location/total_records:.2f}%)")
    
    print("\n" + "-"*80)
    print("SOURCES")
    print("-"*80)
    for source, count in sources.most_common():
        print(f"  {source:20s}: {count:,} ({100*count/total_records:.2f}%)")
    
    if boroughs:
        print("\n" + "-"*80)
        print("TOP BOROUGHS")
        print("-"*80)
        for borough, count in boroughs.most_common(10):
            print(f"  {borough:20s}: {count:,}")
    
    if neighborhoods:
        print("\n" + "-"*80)
        print("TOP NEIGHBORHOODS")
        print("-"*80)
        for hood, count in neighborhoods.most_common(20):
            print(f"  {hood:20s}: {count:,}")
    
    if location_sources:
        print("\n" + "-"*80)
        print("LOCATION EXTRACTION METHODS")
        print("-"*80)
        for method, count in location_sources.most_common():
            print(f"  {method:20s}: {count:,}")

if __name__ == '__main__':
    analyze_location_files()
