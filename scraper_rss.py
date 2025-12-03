import feedparser
import json
import time
from datetime import datetime

# List of RSS feeds based on your project proposal
RSS_FEEDS = [
    "https://gothamist.com/feed/news", # Gothamist
    "https://nypost.com/metro/feed/",   # NY Post Metro
    "https://rss.nytimes.com/services/xml/rss/nyt/NYRegion.xml", # NYT New York Region
    # NY1 often requires specific scraping, but generic Spectrum News RSS might work if available.
    # For now, we stick to the accessible ones.
]

KEYWORDS = ["sick", "flu", "covid", "virus", "outbreak", "health", "hospital", "emergency", "poisoning"]

def fetch_rss_data():
    collected_articles = []
    
    for url in RSS_FEEDS:
        print(f"Fetching {url}...")
        try:
            feed = feedparser.parse(url)
            
            for entry in feed.entries:
                # Basic Keyword Filter (Optional at Layer 1, but good for relevance)
                # Combine title and summary for search
                content_text = (entry.title + " " + entry.get('summary', '')).lower()
                
                if any(keyword in content_text for keyword in KEYWORDS):
                    article = {
                        "source": feed.feed.get('title', 'Unknown Source'),
                        "title": entry.title,
                        "link": entry.link,
                        "published": entry.get('published', datetime.now().isoformat()),
                        "summary": entry.get('summary', ''),
                        "scraped_at": datetime.now().isoformat()
                    }
                    collected_articles.append(article)
                    
        except Exception as e:
            print(f"Error scraping {url}: {e}")

    return collected_articles

if __name__ == "__main__":
    # In production, this would be a loop or a cron job.
    # For Layer 1 delivery, we output to a JSON file.
    data = fetch_rss_data()
    
    filename = f"news_data_{int(time.time())}.json"
    with open(filename, 'w') as f:
        json.dump(data, f, indent=4)
        
    print(f"Scraped {len(data)} relevant articles. Saved to {filename}")