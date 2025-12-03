import json
import os
import time
from sodapy import Socrata
from datetime import datetime, timedelta
import config


# LOOKBACK WINDOW:
# Set to 7 days because NYC Open Data often has a 1-3 day lag 
# for non-emergency 311 data to appear in the public API.
LOOKBACK_DAYS = 7 

def fetch_311_data():
    """
    Fetches 311 complaints related to health hazards (Rodents, Sanitation, Food Poisoning)
    from the NYC Open Data API.
    """
    print(f"--- Starting 311 Scraper ---")
    print(f"Target: {config.DOMAIN}")
    
    if config.APP_TOKEN:
        print("Auth Status: Authenticated (High Throughput)")
        client = Socrata(config.DOMAIN, config.APP_TOKEN)
    else:
        print("Auth Status: Anonymous (Throttled)")
        client = Socrata(config.DOMAIN, None)

    # Calculate time window
    lookback_date = (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime('%Y-%m-%dT%H:%M:%S')
    print(f"Querying data from: {lookback_date} to present")

    # --- SoQL QUERY ---
    # Server-side filtering to reduce bandwidth and processing time.
    where_query = (
        f"created_date > '{lookback_date}' AND "
        "(complaint_type LIKE '%Rodent%' OR "
        "complaint_type LIKE '%Sanitation%' OR "
        "complaint_type LIKE '%Food Poisoning%' OR "
        "complaint_type LIKE '%Dirty Conditions%' OR "
        "complaint_type LIKE '%Pest%' OR "
        "complaint_type LIKE '%Mold%' OR "
        "complaint_type LIKE '%Sewage%' OR "
        "complaint_type LIKE '%Air Quality%')"
    )

    try:
        # Limit set to 5000 to capture a full week of data if needed
        results = client.get(config.DATASET_ID_311, where=where_query, limit=5000, order="created_date DESC")
        
        # Transformation: Standardize data for Layer 2 (Kafka)
        formatted_results = []
        for r in results:
            record = {
                "source": "NYC_311",
                "id": r.get("unique_key"),
                "timestamp": r.get("created_date"),
                "type": r.get("complaint_type"),
                "description": r.get("descriptor"),
                "location": {
                    "zip": r.get("incident_zip"),
                    "lat": r.get("latitude"),
                    "lon": r.get("longitude")
                },
                "status": r.get("status"),
                "scraped_at": datetime.now().isoformat()
            }
            formatted_results.append(record)
            
        return formatted_results

    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        return []

if __name__ == "__main__":
    data = fetch_311_data()
    
    if data:
        filename = f"311_data_{int(time.time())}.json"
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4)
            
        print(f"SUCCESS: Fetched {len(data)} records.")
        print(f"Data dump saved to: {filename}")
    else:
        print("WARNING: No records found. Check API status or Lookback Window.")