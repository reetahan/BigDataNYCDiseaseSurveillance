import os

# NYC Open Data Configuration
DOMAIN = "data.cityofnewyork.us"
DATASET_ID_311 = "erm2-nwe9"
APP_TOKEN = os.getenv("NYC_APP_TOKEN")

# Scraper Settings
# Lookback window in days (increased to 7 to handle reporting lag)
LOOKBACK_DAYS = 7