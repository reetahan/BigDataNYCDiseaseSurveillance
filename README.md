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

3. Start all Docker containers (Kafka, Kafka UI, TimescaleDB):
   ```bash
   docker-compose up -d
   ```
   Wait a few seconds for all services to be ready.

4. Run the project:
   ```bash
   python run_project.py
   ```
   This will run the whole project in one shot (may need to wait for certain consumers to finish).
   You may also run the scrapers individually, the Spark consumers or individually or via the run_chained_project.py,
   and set up the Postgres/Timescale DB via the psql_db_client.py options and ChromaDB via the chromadb_client.py,
   then run the individual Spark analysis scripts in the analysis folder, and you can run the dashboard app in the
   dashboard folder as 
   ```bash
   streamlit run app_upgraded.py
   ```

   