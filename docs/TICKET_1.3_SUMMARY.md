# Ticket 1.3: Local News RSS Scraper - COMPLETE ✅

**Assignee:** Devak Somaraj (ds8095)
**Status:** Complete
**Date Completed:** November 26, 2025

## Summary
Successfully implemented a standardized ingestion tool for local NYC news outlets (Gothamist, NY Post, NYT). The scraper aggregates health-related news summaries to serve as the "Curated News" input signal for the surveillance pipeline, acting as a counterbalance to informal social media signals.

## Deliverables

### Core Implementation
1.  **RSS Scraper** ([scrapers/scraper_rss.py](scrapers/scraper_rss.py))
    - Universal XML parsing using `feedparser`.
    - Normalization of diverse RSS standards (Atom vs. RSS 2.0).
    - Hard-coded source list of reliable local NYC outlets.
    - JSON output generation with standardized timestamps.

2.  **Configuration**
    - List of targeted feeds (`RSS_FEEDS`) defined in-script for simplicity.
    - Keyword list (`sick`, `flu`, `virus`, etc.) serves as the primary relevance filter.

### Documentation
1.  **Usage Guide**
    - Included in the main `README.md` under Layer 1 instructions.
    - Setup instructions for `feedparser` dependencies.

### Infrastructure
1.  **Dependencies** ([requirements.txt](requirements.txt))
    - `feedparser==6.0.10`: Handles the complexities of XML parsing.
    - Standard libraries: `json`, `datetime`, `time`.

2.  **Data Directory** (`data/rss/`)
    - Output location for scraped JSON files.
    - Files named by timestamp for uniqueness.

## Technical Highlights

### Design Choices
1.  **Library Strategy (`feedparser`)**
    - *Why:* Raw XML scraping is brittle because every news site structures their feed differently.
    - *Benefit:* `feedparser` abstracts these differences, providing a unified Python dictionary interface regardless of whether the source is NYT or a local blog.

2.  **Ingestion-Level Filtering**
    - *Why:* News feeds contain sports, politics, and entertainment.
    - *Mechanism:* A strict keyword filter checks both the `title` and `summary` fields. Only articles containing health keywords pass through.
    - *Benefit:* Reduces noise entering the Kafka pipeline by ~90%, saving processing costs in Layer 3.

3.  **Summary vs. Full Text**
    - *Constraint:* RSS feeds legally and technically only provide summaries.
    - *Solution:* We ingest the summary for immediate relevance checks but capture the `link` URL. Layer 3 (Spark) can use this URL to fetch the full HTML content if the LLM determines the summary is insufficient.

## Output Format

Each article is saved as a JSON object within a batch file:

```json
[
    {
        "source": "Gothamist",
        "title": "Flu Cases Rise in Brooklyn",
        "link": "https://gothamist.com/news/health/flu-rise-2025",
        "published": "2025-11-23T14:30:00",
        "summary": "Health officials warn of early flu season across the borough...",
        "scraped_at": "2025-11-23T15:00:00"
    }
]
```

## Usage Examples
**Quick Test**:
```bash 
python scraper_rss.py
```
Output: Scraped 5 relevant articles. Saved to data/rss/rss_data_1764834.json

## Integration Check
Verify output file creation in data/rss/.

## Integration Points
1. **Input**: Public RSS URLs from NYC news outlets.
2. **Output**: JSON files in data/rss/.
3. **Next Stage**: S3 Archival (Ticket 4.1) and Kafka Producer (Ticket 2.1).

## Testing & Validation
- ✅ Validated against NYT Region (XML) and Gothamist (RSS) feeds.
- ✅ Confirmed keyword filtering excludes non-health news.
- ✅ Verified JSON structure compatibility with Spark schemas.

## Known Limitations
1. **Refresh Rate**: News feeds update slowly. Running this more than once per hour is redundant.
2. **Content Depth**: Analysis is limited to the ~50 word summary provided by the feed.

## Future Enhancements
1. **Full-Text Crawler**: Add a secondary step to visit the link and scrape the full HTML body.
2. **Source Expansion**: Add generic Google News RSS feeds for broader coverage.