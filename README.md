# BigDataNYCDiseaseSurveillance

Repository for Fall 2025 Big Data Final Project: NYC Disease Outbreak Surveillance

## Team Members
- Devak Somaraj (ds8095)
- Steven Granaturov (sg8002)
- Reetahan Mukhopadhyay (rm6609)
- Adhyayan Verma (av4159)
- Zubair Ali (zl5749)

## Project Overview

NYC Disease Outbreak Surveillance provides hyperlocal disease monitoring for New York City by integrating unofficial data sources with official public health reports to support early outbreak detection at the neighborhood level.

## Quick Start

### Setup

1. Clone the repository and create virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. Configure environment:
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

### Layer 1: Data Ingestion (Scrapers)

# Ticket 1.1: Reddit Scraper

## Overview
This module implements a scraper to scrape health-related posts from r/nyc and r/AskNYC


#### Bluesky Social Media Scraper (Ticket 1.2)

Scrapes Bluesky for health-related posts mentioning NYC.

**Status:** ✅ Complete

**Quick Run:**
```bash
python run_bluesky_scraper.py --mode single --query "sick NYC" --limit 50
```

**Documentation:** See [scrapers/bluesky/README.md](scrapers/bluesky/README.md)

# Ticket 1.3: Local News RSS Scraper

## Overview
This module implements a scraper for Local NYC News RSS feeds (Gothamist, NY Post, NYT Region) to ingest health-related news articles into our pipeline.


# Ticket 1.4: NYC Open Data & 311 Scraper

## Overview
This module ingests environmental health indicators (Rodent sightings, Sanitation issues, Food Poisoning complaints) from the NYC 311 Service Requests API via the Socrata Open Data standard.

## Project Structure

```
BigDataNYCDiseaseSurveillance/
├── scrapers/
│   └── bluesky/           # Bluesky social media scraper
│       ├── scraper.py     # Main scraper implementation
│       ├── config.py      # Configuration management
│       └── README.md      # Detailed documentation
├── data/                  # Output data directory
├── venv/                  # Python virtual environment
├── requirements.txt       # Python dependencies
├── .env.example          # Environment variables template
└── run_bluesky_scraper.py # Main runner script
```

## Architecture

The system consists of 5 layers:

1. **Data Ingestion** - Web scrapers (Reddit, Bluesky, News, NYC Open Data, Health PDFs)
2. **Streaming Layer** - Apache Kafka message broker
3. **Processing** - Spark Streaming + LLM (GPT-4) integration
4. **Storage** - S3 (raw), PostgreSQL/TimescaleDB (time-series), ChromaDB (embeddings)
5. **Analytics** - Anomaly detection, spatial clustering, Plotly dashboard

## Development Status

### Layer 1: Data Ingestion
- [x] Ticket 1.2: Bluesky Scraper (Steven) - **COMPLETE**
- [x] Ticket 1.1: Reddit Scraper (Adhyayan)
- [x] Ticket 1.3: Local News RSS Feeds (Devak)
- [x] Ticket 1.4: NYC Open Data & 311 API (Devak) **COMPLETE**
- [x] Ticket 1.5: Health Department PDF Scraping (Reetahan)
