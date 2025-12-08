# Ticket 4.1: S3 Data Archival Pipeline - COMPLETE ✅

**Assignee:** Devak Somaraj (ds8095)
**Status:** Complete
**Date Completed:** December 7, 2025

## Summary
Implemented the "Cold Path" data archival layer. This universal uploader ensures reproducibility by capturing raw output from all scrapers (Reddit, Bluesky, 311, News) and securing it in AWS S3 storage before real-time processing begins. This creates an immutable "Source of Truth" backup.

## Deliverables

### Core Implementation
1.  **Universal Uploader** ([s3_uploader.py](s3_uploader.py))
    - Recursive directory scanning (`os.walk`) to support any folder structure.
    - Source-agnostic design (supports JSON, JSONL, CSV).
    - "Mock Mode" (Dry Run) logic for cost-free testing.
    - Automated file lifecycle management (Move-to-Processed).

2.  **Environment Template** ([.env.example](.env.example))
    - Template for AWS credentials to ensure teammates configure their environment correctly without leaking secrets.

### Infrastructure
1.  **Dependencies** ([requirements.txt](requirements.txt))
    - `boto3`: AWS SDK for Python.
    - `botocore`: Exception handling for AWS connections.
    - `python-dotenv`: Environment variable management.

2.  **Storage Architecture**
    - **Source:** Local `data/` directory.
    - **Destination:** AWS S3 Bucket (e.g., `nyc-disease-surveillance-raw/`).
    - **Archive:** Local `data_processed/` directory.

## Technical Highlights

### 1. Mock vs. Live Execution (Cost Control)
**Feature:** The script automatically detects the presence of valid AWS credentials.
- **If Keys Missing:** Defaults to **Dry Run Mode**. Logs actions (`[Mock] Would upload...`) but makes no network calls.
- **If Keys Present:** Switches to **Live Mode** and performs actual S3 uploads.
**Benefit:** Allows the entire team to verify the logic locally without needing an AWS account or incurring cloud costs.

### 2. Idempotency & Data Lifecycle
**Challenge:** Scrapers run continuously. Uploading the same files repeatedly wastes bandwidth and storage costs.
**Solution:** The "Move-to-Processed" pattern.
- Step 1: Upload `data/file.json` to S3.
- Step 2: On success, move `data/file.json` to `data_processed/file.json`.
- Step 3: Next run finds `data/` empty (or only containing new files).

### 3. Recursive Scanning
The script is not hardcoded for specific scrapers. It simply walks the `data/` tree.
- If a new scraper (e.g., `tiktok_scraper`) is added and saves to `data/tiktok/`, this script handles it automatically without code changes.

## Output Format (S3 Structure)

The S3 bucket mirrors the local directory structure:

```text
s3://bucket-name/
└── raw/
    ├── nyc_311/
    │   └── 311_data_1764834.json
    ├── reddit/
    │   └── posts_1764834.json
    └── rss/
        └── news_1764834.json
```

## Usage Examples
### Dry Run (Default)
```bash
# Ensure AWS keys are unset
python s3_uploader.py
# Output: "MODE: DRY RUN... Found 5 files..."
```
### Live Upload
```bash
# Set keys in .env
python s3_uploader.py
# Output: "MODE: LIVE... Uploading..."
```
### Integration Points
- **Upstream:** Consumes data from all Layer 1 scrapers.
- **Downstream:** S3 Bucket acts as the Data Lake for batch analytics (Layer 5) or historical replay.

## Testing & Validation
- ✅ Verified recursive scanning on nested directories.
- ✅ Tested "Dry Run" logic to ensure no crashes when keys are missing.
- ✅ Live Test: Verified successful upload to personal AWS S3 bucket and file movement to data_processed/.

## Files Created
- s3_uploader.py
- .env.example
- .gitignore (Updated)
- TICKET_4.1_SUMMARY.md
