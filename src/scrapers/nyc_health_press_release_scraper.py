#!/usr/bin/env python3
"""
NYC Health Press Release Scraper
"""

import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime, timedelta
import os

def scrape_press_releases(days_back=30):
    """Scrape NYC DOHMH press releases."""
    url = "https://www.nyc.gov/site/doh/about/press/recent-press-releases.page"
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching page: {e}")
        return []
    
    soup = BeautifulSoup(response.content, 'html.parser')
    paragraphs = soup.find_all('p')
    
    press_releases = []
    cutoff_date = datetime.now() - timedelta(days=days_back)
    
    for p in paragraphs:
        # Look for paragraphs with a <strong> date and an <a> link
        strong = p.find('strong')
        link = p.find('a', href=True)
        
        if not strong or not link:
            continue
        
        date_text = strong.get_text(strip=True)
        title = link.get_text(strip=True)
        href = link['href']
        
        try:
            press_date = datetime.strptime(date_text, '%B %d, %Y')
        except ValueError:
            continue
        
        # Filter by date
        if press_date < cutoff_date:
            continue
        
        # Build full URL
        if href.startswith('http'):
            full_url = href
        else:
            full_url = f"https://www.nyc.gov{href}"
        
        result = {
            'source': 'nyc_doh_press_release',
            'title': title,
            'date': press_date.isoformat(),
            'url': full_url,
            'scraped_at': datetime.now().isoformat()
        }
        
        press_releases.append(result)
    
    print(f"Collected {len(press_releases)} press releases from last {days_back} days")
    return press_releases

def fetch_article_text(url):
    """Fetch the full text content of a press release."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        
        content = None
        
        # Try common content containers
        for selector in [
            {'class': 'page-content'},
            {'class': 'content'},
            {'class': 'main-content'},
            {'id': 'content'}
        ]:
            content = soup.find('div', selector)
            if content:
                break
        
        # If still not found, look for article or main tags
        if not content:
            content = soup.find('article') or soup.find('main')
        
        if content:
            # Extract all paragraphs
            paragraphs = content.find_all('p')
            text = '\n\n'.join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
            return text
        
        return None
        
    except Exception as e:
        print(f"  Error fetching article: {e}")
        return None
    
def filter_disease_related(press_releases):
    """Filter for disease-related press releases."""
    
    keywords = [
        'outbreak', 'disease', 'illness', 'virus', 'infection',
        'COVID', 'flu', 'influenza', 'RSV', 'respiratory',
        'measles', 'tuberculosis', 'hepatitis', 'legionnaires',
        'west nile', 'norovirus', 'food poisoning', 'salmonella',
        'E. coli', 'meningitis', 'mpox', 'monkeypox', 'rabies',
        'surveillance', 'epidemic', 'pandemic', 'cluster',
        'gastrointestinal', 'stomach', 'fever', 'cases', 'vaccine',
        'immunization', 'testing', 'health alert', 'vaccinating'
    ]
    
    filtered = []
    for pr in press_releases:
        title_lower = pr['title'].lower()
        if any(kw.lower() in title_lower for kw in keywords):
            filtered.append(pr)
    
    print(f"Filtered to {len(filtered)} disease-related releases")
    return filtered


def main():
    """Main function."""
    print("NYC Health Press Release Scraper\n")
    
    press_releases = scrape_press_releases(days_back=30)
    
    if not press_releases:
        print("No press releases found!")
        return
    
    disease_releases = filter_disease_related(press_releases)

    for i, pr in enumerate(disease_releases, 1):
        print(f"  [{i}/{len(disease_releases)}] {pr['title'][:50]}...")
        pr['full_text'] = fetch_article_text(pr['url'])
    
    output_json = {
        'scraped_at': datetime.now().isoformat(),
        'total_releases': len(press_releases),
        'disease_related': len(disease_releases),
        'releases': disease_releases
    }

    output_dir = "data/nyc_press"
    os.makedirs(output_dir, exist_ok=True)
    filename = os.path.join(output_dir, f"nyc_press_releases_{datetime.now().strftime('%Y%m%d')}.json")
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(output_json, f, indent=2, ensure_ascii=False)
    print(f"Saved to {filename}")
    print(f"\nTotal: {len(press_releases)} releases, {len(disease_releases)} disease-related")
    
    if disease_releases:
        print("\nMost recent:")
        for pr in disease_releases[:5]:
            print(f"  {pr['date'][:10]}: {pr['title'][:60]}")


if __name__ == '__main__':
    main()