# NYC Health Data Scrapers - Design Summary

## Scripts

1. **nyc_health_press_release_scraper.py** - Scrapes NYC DOHMH press releases
2. **nyc_covid_rsv_flu_official_scraper.py** - Gets COVID/Flu/RSV data from NYC GitHub

## Key Design Decisions

### Press Release Scraper

**Challenge:** Original scraper failed with "Could not find main content div" error.

**Root Cause:** Looking for non-existent `<div class="page-content">` container.

**Solution:** Parse actual HTML structure - press releases are in `<p>` tags with:
- `<strong>` containing date ("November 24, 2025")  
- `<a>` containing title and URL

**Implementation:**
- Iterate through all `<p>` tags on page
- Find those with both `<strong>` and `<a>` children
- Parse date with `strptime('%B %d, %Y')`
- Filter by disease keywords (outbreak, virus, infection, etc.)
- No complex DOM traversal needed

**Considerations:**
- Fragile to HTML structure changes (but current structure is stable)
- Date parsing assumes specific format
- Keyword filtering may miss novel disease names
- No full text extraction (only title/URL)

### Respiratory Data Scraper

**Challenge:** Dashboard at `nyc.gov/assets/doh/respiratory-illness-data/` loads data via React/JavaScript.

**Initial Approaches Rejected:**
1. Selenium scraping - too slow, brittle, overkill
2. API reverse engineering - requires network inspection
3. NYC Open Data Portal - dataset IDs kept changing

**Final Solution:** Found official NYC Health GitHub repo with raw CSV!
- URL: `https://raw.githubusercontent.com/nychealth/respiratory-illness-data/main/data/emergencyDeptData.csv`
- Updated regularly by NYC Health Department
- No authentication required

**Implementation:**
- Direct CSV download via pandas
- Structured data with columns: date, metric, submetric, value, display
- Includes COVID-19, Flu, RSV data by age/borough/time
- Simple filtering methods for date/disease/location

**Considerations:**
- Depends on NYC maintaining GitHub repo (reliable but not guaranteed)
- CSV structure could change (unlikely - public API)
- Data has ~7-day lag (matches official surveillance reporting)
- No historical data beyond what's in CSV (Sept 2025+)


## Validation Strategy

**For early detection claims:**
1. Get press release date (official announcement)
2. Get social media spike date from your pipeline
3. Calculate lead time: `press_release_date - social_spike_date`
4. Document cases where social signals preceded official announcements

**Expected lead time:** 5-7 days based on syndromic surveillance lag

## Error Handling

Both scripts use basic try/except with:
- Network timeouts (10 seconds)
- Empty result handling
- Graceful degradation (return empty list on failure)

**Production improvements needed:**
- Retry logic with exponential backoff
- Rate limiting (though unlikely needed for these sources)
- Logging instead of print statements
- Alerting on consecutive failures

## Performance

- **Press releases:** ~2 seconds (single HTTP request + parsing)
- **Respiratory data:** ~1 second (CSV download ~100KB)
- Both suitable for daily/hourly scheduling

## Maintenance Concerns

**High risk:**
- Press release HTML structure changes (happens ~1-2x/year for gov sites)
- GitHub repo discontinued (low probability - public resource)

**Medium risk:**
- Date format changes in press releases
- CSV schema changes (column renames, additions)

**Low risk:**
- URL changes (NYC maintains redirects)
- Data availability (official health dept commitment)

## Alternative Approaches Considered

1. **NYC EpiQuery API** (`a816-health.nyc.gov/hdi/epiquery`) - Requires network inspection to find endpoints
2. **NYC Open Data Portal SODA API** - Has COVID data (ID: rc75-m7u3) but flu/RSV datasets unclear
3. **Selenium for press releases** - Works but unnecessary overhead
4. **Weekly PDF scraping** - Mentioned in project plan but GitHub CSV is superior
