"""
reddit_scraper.py
Scrapes health-related posts from r/nyc and r/AskNYC
Saves data to SQLite database: reddit_health.db
python pipeline.py --mode once --days 365
"""

import praw
import sqlite3
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

# Load credentials from .env file
load_dotenv()

# Health keywords to search for
HEALTH_KEYWORDS = [
    'fever', 'cough', 'sore throat', 'headache', 'nausea',
            'vomiting', 'diarrhea', 'fatigue', 'chills', 'body aches',
            'congestion', 'runny nose', 'shortness of breath', 'chest pain',
            'stomach pain', 'rash', 'dizzy', 'weak', 'sick', 'ill',
            'flu', 'cold', 'covid', 'virus', 'infection', 'symptoms',
            'doctor', 'urgent care', 'emergency room', 'hospital',
            'feeling sick', 'not feeling well', 'under the weather'
]


def init_database():
    """Create database tables"""
    conn = sqlite3.connect('reddit_health.db')
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS posts (
            post_id TEXT PRIMARY KEY,
            subreddit TEXT,
            title TEXT,
            author TEXT,
            created_utc TIMESTAMP,
            score INTEGER,
            num_comments INTEGER,
            text TEXT,
            url TEXT,
            scraped_at TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            comment_id TEXT PRIMARY KEY,
            post_id TEXT,
            author TEXT,
            created_utc TIMESTAMP,
            score INTEGER,
            text TEXT,
            scraped_at TIMESTAMP
        )
    ''')

    conn.commit()
    conn.close()
    print("✓ Database initialized: reddit_health.db")


def contains_health_keywords(text):
    """Check if text mentions health topics"""
    if not text:
        return False
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in HEALTH_KEYWORDS)


def scrape_reddit(subreddits=['nyc', 'AskNYC'], days_back=30, max_posts=100):
    """
    Scrape Reddit for health discussions

    Args:
        subreddits: List of subreddits to scrape
        days_back: How many days back to scrape
        max_posts: Maximum posts to check per subreddit
    """
    print("\n" + "=" * 60)
    print("STARTING REDDIT SCRAPER")
    print("=" * 60)

    # Initialize Reddit API
    reddit = praw.Reddit(
        client_id=os.getenv('REDDIT_CLIENT_ID'),
        client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
        user_agent=os.getenv('REDDIT_USER_AGENT')
    )

    conn = sqlite3.connect('reddit_health.db')
    cursor = conn.cursor()

    start_date = datetime.now() - timedelta(days=days_back)
    total_posts = 0
    total_comments = 0

    for sub_name in subreddits:
        print(f"\nScraping r/{sub_name}...")
        subreddit = reddit.subreddit(sub_name)
        posts_found = 0

        # Get recent posts
        for post in subreddit.new(limit=max_posts):
            post_date = datetime.fromtimestamp(post.created_utc)

            if post_date < start_date:
                continue

            # Check if post is about health
            if contains_health_keywords(post.title) or contains_health_keywords(post.selftext):

                # Save post
                cursor.execute('''
                    INSERT OR REPLACE INTO posts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    post.id, sub_name, post.title, str(post.author),
                    post_date, post.score, post.num_comments,
                    post.selftext, post.url, datetime.now()
                ))

                posts_found += 1

                # Get comments
                post.comments.replace_more(limit=0)
                for comment in post.comments.list()[:20]:  # Max 20 comments per post
                    if contains_health_keywords(comment.body):
                        cursor.execute('''
                            INSERT OR REPLACE INTO comments VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            comment.id, post.id, str(comment.author),
                            datetime.fromtimestamp(comment.created_utc),
                            comment.score, comment.body, datetime.now()
                        ))
                        total_comments += 1

                if posts_found % 10 == 0:
                    print(f"  Found {posts_found} posts...")

        total_posts += posts_found
        print(f"  ✓ r/{sub_name}: {posts_found} posts")

    conn.commit()
    conn.close()

    print("\n" + "=" * 60)
    print(f"SCRAPING COMPLETE")
    print(f"Total Posts: {total_posts}")
    print(f"Total Comments: {total_comments}")
    print(f"Database: reddit_health.db")
    print("=" * 60 + "\n")

    return {'posts': total_posts, 'comments': total_comments}


if __name__ == "__main__":
    # Initialize database
    init_database()

    # Scrape Reddit
    results = scrape_reddit(
        subreddits=['nyc', 'AskNYC'],
        days_back=30,  # Last 30 days
        max_posts=100  # Check 100 recent posts per subreddit
    )

    print(f"\n✓ Done! Found {results['posts']} posts and {results['comments']} comments")
    print(f"✓ Data saved to: reddit_health.db")