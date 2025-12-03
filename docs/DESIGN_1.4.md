# Ticket 1.4: Design Considerations & Challenges

## 1. Configuration Management
Moved all static configuration (Dataset IDs, Domains) to `config.py` to keep the logic code clean and modular. Secrets (API Tokens) continue to be handled via Environment Variables.

## 2. Query Strategy
**Constraint:** The 311 dataset contains millions of records (noise complaints, parking, etc.) which are irrelevant to disease surveillance.
**Solution:** We use Server-Side Filtering (SoQL) to request ONLY health-related rows.
**Comprehensive List:** We filter for:
*   Vectors: Rodents, Pests
*   Sanitation: Dirty Conditions, Sewage, Mold
*   Direct Health: Food Poisoning, Air Quality

## 3. Data Latency
**Challenge:** NYC 311 data often lags by 24-48 hours for non-emergency tickets.
**Choice:** The scraper defaults to a **7-day lookback window**. This ensures we capture late-arriving data. The Spark Layer (Ticket 3.x) handles deduplication of overlapping records.