"""
reddit_scraper.py
Scrapes health-related posts from r/nyc and r/AskNYC
Saves data to JSON files in data/ folder
"""

import praw
import json
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import re

# Load credentials from .env file
load_dotenv()

# JSON file paths
POSTS_JSON = 'data/reddit/reddit_posts.json'
COMMENTS_JSON = 'data/reddit/reddit_comments.json'

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
def ensure_data_folder():
    """Create data folder if it doesn't exist"""
    os.makedirs('data/reddit', exist_ok=True)

def load_existing_data(filepath):
    """Load existing JSON data if file exists"""
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_json_data(data, filepath):
    """Save data to JSON file"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

def contains_health_keywords(text):
    """Check if text mentions health topics"""
    if not text:
        return False
    text_lower = text.lower()
    cleaned_line = re.sub(r'[^a-z0-9\s]', ' ', text_lower)
    words = cleaned_line.strip().split()
    return any(keyword in words for keyword in HEALTH_KEYWORDS)

def scrape_reddit(subreddits=['nyc', 'AskNYC', 'newyorkcity', 'Brooklyn', 'Queens', 'bronx', 'Manhattan', 'StatenIsland'], days_back=30, max_posts=100):
    """
    Scrape Reddit for health discussions

    Args:
        subreddits: List of subreddits to scrape
        days_back: How many days back to scrape
        max_posts: Maximum posts to check per subreddit
    """
    # Check for local mode
    local_mode = os.getenv('LOCAL_MODE') == '1'
    
    print("\n" + "="*60)
    print(f"STARTING REDDIT SCRAPER {'(LOCAL MODE)' if local_mode else ''}")
    print("="*60)
    
    # In local mode, just return existing data without scraping
    if local_mode:
        ensure_data_folder()
        all_posts = load_existing_data(POSTS_JSON)
        all_comments = load_existing_data(COMMENTS_JSON)
        
        print(f"\nLocal mode: Loaded {len(all_posts)} posts and {len(all_comments)} comments from files")
        print("="*60 + "\n")
        
        return {
            'posts': all_posts,
            'comments': all_comments,
            'new_posts': 0,
            'new_comments': 0,
            'total_posts': len(all_posts),
            'total_comments': len(all_comments)
        }

    # Ensure data folder exists
    ensure_data_folder()

    # Load existing data
    all_posts = load_existing_data(POSTS_JSON)
    all_comments = load_existing_data(COMMENTS_JSON)

    # Track existing IDs to avoid duplicates
    existing_post_ids = {post['post_id'] for post in all_posts}
    existing_comment_ids = {comment['comment_id'] for comment in all_comments}

    # Initialize Reddit API
    reddit = praw.Reddit(
        client_id=os.getenv('REDDIT_CLIENT_ID'),
        client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
        user_agent=os.getenv('REDDIT_USER_AGENT')
    )

    start_date = datetime.now() - timedelta(days=days_back)
    new_posts = 0
    new_comments = 0

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

                # Skip if already scraped
                if post.id in existing_post_ids:
                    continue

                # Create post object
                post_data = {
                    'post_id': post.id,
                    'subreddit': sub_name,
                    'title': post.title,
                    'author': str(post.author),
                    'created_utc': post_date.isoformat(),
                    'score': post.score,
                    'num_comments': post.num_comments,
                    'text': post.selftext,
                    'url': post.url,
                    'scraped_at': datetime.now().isoformat()
                }

                all_posts.append(post_data)
                existing_post_ids.add(post.id)
                posts_found += 1
                new_posts += 1

                # Get comments
                post.comments.replace_more(limit=0)
                for comment in post.comments.list()[:20]:  # Max 20 comments per post
                    if contains_health_keywords(comment.body):

                        # Skip if already scraped
                        if comment.id in existing_comment_ids:
                            continue

                        comment_data = {
                            'comment_id': comment.id,
                            'post_id': post.id,
                            'author': str(comment.author),
                            'created_utc': datetime.fromtimestamp(comment.created_utc).isoformat(),
                            'score': comment.score,
                            'text': comment.body,
                            'scraped_at': datetime.now().isoformat()
                        }

                        all_comments.append(comment_data)
                        existing_comment_ids.add(comment.id)
                        new_comments += 1

                if posts_found % 10 == 0 and posts_found > 0:
                    print(f"  Found {posts_found} new posts...")

        print(f"  ✓ r/{sub_name}: {posts_found} new posts")

    # Save to JSON files
    save_json_data(all_posts, POSTS_JSON)
    save_json_data(all_comments, COMMENTS_JSON)

    print("\n" + "="*60)
    print(f"SCRAPING COMPLETE")
    print(f"New Posts: {new_posts}")
    print(f"New Comments: {new_comments}")
    print(f"Total Posts: {len(all_posts)}")
    print(f"Total Comments: {len(all_comments)}")
    print(f"Posts saved to: {POSTS_JSON}")
    print(f"Comments saved to: {COMMENTS_JSON}")
    print("="*60 + "\n")

    return {
        'new_posts': new_posts,
        'new_comments': new_comments,
        'total_posts': len(all_posts),
        'total_comments': len(all_comments)
    }

if __name__ == "__main__":
    # Scrape Reddit
    results = scrape_reddit(
        subreddits=['nyc', 'AskNYC', 'newyorkcity', 'Brooklyn', 'Queens', 'bronx', 'Manhattan', 'StatenIsland'],
        days_back=300,      # Last 30 days
        max_posts=1000      # Check 100 recent posts per subreddit
    )

    print(f"\n✓ Done! Found {results['new_posts']} new posts and {results['new_comments']} new comments")
    print(f"✓ Total data: {results['total_posts']} posts, {results['total_comments']} comments")
    print(f"✓ Data saved to: {POSTS_JSON} and {COMMENTS_JSON}")