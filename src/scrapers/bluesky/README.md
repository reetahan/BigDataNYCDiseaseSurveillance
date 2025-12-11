# Bluesky Scraper for NYC Disease Surveillance

A Python scraper that monitors Bluesky posts for health-related content in NYC.

## What is Bluesky?

Bluesky is a decentralized social media platform (similar to Twitter/X) built on the AT Protocol. It's open, has a free API, and hosts a large health/medical community that migrated from Twitter. Perfect for monitoring public health discussions.

## Quick Start

### 1. Setup (from project root)
```bash
source venv/bin/activate
cp .env.example .env
# Edit .env with credentials (already configured: nyudatascraper.bsky.social)
```

### 2. Run a Test
```bash
python run_bluesky_scraper.py --mode single --query "sick NYC" --limit 50
```

### 3. Start Continuous Monitoring
```bash
python run_bluesky_scraper.py --mode stream --interval 300
```

## How It Works

1. **Searches Bluesky** for posts using health keywords (sick, flu, covid, fever, etc.)
2. **Filters by location** - must mention NYC/boroughs
3. **Extracts data** - author, text, timestamp, engagement metrics
4. **Saves to file** - JSON Lines format in `data/bluesky_posts.jsonl`
5. **Optional Kafka** - can stream to Kafka topic for real-time processing

## Command Options

```bash
--mode {single,stream}   # single search or continuous monitoring
--query TEXT            # search keywords (default: "sick NYC")
--limit INT             # max posts per search (default: 100)
--interval INT          # seconds between searches (default: 300)
--output PATH           # output file path
--kafka                 # enable Kafka producer
```

## Output Format

Each post is saved as JSON:
```json
{
  "platform": "bluesky",
  "post_id": "at://...",
  "author": "username.bsky.social",
  "text": "Post content...",
  "created_at": "2025-11-24T00:19:44Z",
  "scraped_at": "2025-11-24T03:49:37Z",
  "reply_count": 0,
  "repost_count": 0,
  "like_count": 5,
  "language": "en"
}
```

## Monitored Keywords

**Health:** sick, illness, flu, covid, fever, cough, symptom, disease, outbreak, virus, infection, respiratory, gastrointestinal, nausea, vomiting, diarrhea, sore throat, headache, body aches, fatigue, emergency room, urgent care, doctor, hospital, clinic, test positive

**Location:** nyc, new york city, manhattan, brooklyn, queens, bronx, staten island, new york, ny

Posts must contain **both** a health keyword AND a location keyword.

## Configuration (.env)

```env
BLUESKY_HANDLE=nyudatascraper.bsky.social
BLUESKY_PASSWORD=5cez-kqvh-drwz-b42d

KAFKA_BOOTSTRAP_SERVERS=localhost:9092
KAFKA_TOPIC=social-media
ENABLE_KAFKA=false

SCRAPE_INTERVAL=300
MAX_POSTS_PER_SEARCH=100
OUTPUT_FILE=data/bluesky_posts.jsonl
```

## Examples

```bash
# Search for COVID mentions
python run_bluesky_scraper.py --mode single --query "covid NYC" --limit 100

# Monitor flu activity every 10 minutes
python run_bluesky_scraper.py --mode stream --interval 600

# Stream to Kafka
python run_bluesky_scraper.py --mode stream --kafka
```

## Troubleshooting

**Authentication Error (401):**
- Verify credentials in `.env`
- Use full handle: `name.bsky.social`
- Use app password, not account password

**No Posts Found:**
- Try broader search terms
- Posts need both health AND NYC keywords
- Bluesky's search has limited history

**Rate Limits:**
- Built-in 2-second delay between requests
- 3000 requests per 5 minutes allowed

## Integration

Feeds into NYC Disease Surveillance pipeline:
```
Bluesky API → This Scraper → Kafka → Spark Streaming → GPT-4 → Database
```

## Project Structure

```
scrapers/bluesky/
├── scraper.py      # Main BlueskyScraper class
├── config.py       # Configuration management
└── README.md       # This file
```

## Why Bluesky Over Twitter/X?

- **Free API** (Twitter charges $100/month minimum)
- **Open access** to public posts
- **Active health community** (MedTwitter migrated here)
- **No paywalls** or enterprise pricing required
- **Official Python library** (`atproto`)

---

For detailed setup instructions, see [SETUP_GUIDE.md](../../SETUP_GUIDE.md) in project root.
