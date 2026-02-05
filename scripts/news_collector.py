#!/usr/bin/env python3
"""
Vietnam Infrastructure News Collector
Fixed version with expanded sector keywords and robust RSS parsing
"""

import os
import sys
import json
import re
import sqlite3
import hashlib
import logging
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
import html
import xml.etree.ElementTree as ET

import requests
import feedparser
from bs4 import BeautifulSoup

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURATION
# ============================================================

# Database path
DB_PATH = os.environ.get('DB_PATH', 'data/vietnam_infrastructure_news.db')

# Hours to look back for news
HOURS_BACK = int(os.environ.get('HOURS_BACK', 24))

# RSS Feeds - Vietnam English news sources
RSS_FEEDS = {
    "VnExpress English": "https://e.vnexpress.net/rss/news.rss",
    "VnExpress Business": "https://e.vnexpress.net/rss/business.rss",
    "VietnamPlus EN": "https://en.vietnamplus.vn/rss/news.rss",
    "VietnamPlus Business": "https://en.vietnamplus.vn/rss/business.rss",
    "Vietnam News": "https://vietnamnews.vn/rss/home.rss",
    "Tuoi Tre English": "https://tuoitrenews.vn/rss/news.rss",
    "The Investor": "https://theinvestor.vn/rss/news.rss",
    "Vietnam Investment Review": "https://vir.com.vn/rss/news.rss",
    "Hanoi Times": "https://hanoitimes.vn/rss/news.rss",
    "VietnamNet EN": "https://vietnamnet.vn/en/rss/home.rss",
    "Saigon GP Daily": "https://en.sggp.org.vn/rss/news.rss",
}

# ============================================================
# EXPANDED SECTOR KEYWORDS - More inclusive matching
# ============================================================

SECTOR_KEYWORDS = {
    "Waste Water": {
        "primary": [
            "wastewater", "waste water", "sewage", "water treatment",
            "drainage", "water supply", "clean water", "tap water",
            "water infrastructure", "water project", "water plant",
            "water system", "water network", "sanitation"
        ],
        "secondary": [
            "water", "treatment plant", "purification", "effluent",
            "sludge", "pumping station", "reservoir"
        ]
    },
    "Solid Waste": {
        "primary": [
            "solid waste", "garbage", "trash", "landfill", "waste management",
            "recycling", "incineration", "waste-to-energy", "wte",
            "municipal waste", "hazardous waste", "waste collection"
        ],
        "secondary": [
            "waste", "disposal", "rubbish", "compost", "plastic waste"
        ]
    },
    "Power": {
        "primary": [
            "power plant", "electricity", "power generation", "thermal power",
            "coal power", "gas power", "hydropower", "hydro power",
            "wind power", "wind farm", "solar power", "solar farm",
            "renewable energy", "clean energy", "green energy",
            "power grid", "transmission line", "substation",
            "lng", "liquefied natural gas", "energy transition",
            "offshore wind", "floating solar", "battery storage",
            "power capacity", "megawatt", "gigawatt", "mw", "gw"
        ],
        "secondary": [
            "energy", "power", "electric", "turbine", "generator",
            "evn", "vietnam electricity", "petrovietnam"
        ]
    },
    "Oil & Gas": {
        "primary": [
            "oil and gas", "oil & gas", "petroleum", "refinery",
            "oil field", "gas field", "offshore oil", "pipeline",
            "petrochemical", "natural gas", "crude oil", "exploration",
            "drilling", "upstream", "downstream", "midstream"
        ],
        "secondary": [
            "pvn", "petrovietnam", "binh son", "nghi son", "dung quat"
        ]
    },
    "Industrial Parks": {
        "primary": [
            "industrial park", "industrial zone", "industrial complex",
            "economic zone", "export processing", "free trade zone",
            "manufacturing hub", "tech park", "hi-tech park",
            "industrial estate", "industrial cluster", "special economic"
        ],
        "secondary": [
            "industrial", "factory", "manufacturing", "warehouse",
            "logistics park", "industrial land"
        ]
    },
    "Smart City": {
        "primary": [
            "smart city", "smart urban", "digital city", "intelligent transport",
            "smart traffic", "smart grid", "iot", "5g network",
            "digital transformation", "e-government", "smart building",
            "ai camera", "surveillance system", "traffic management"
        ],
        "secondary": [
            "smart", "digital", "automated", "intelligent"
        ]
    },
    "Urban Development": {
        "primary": [
            "urban development", "urban planning", "city planning",
            "metro", "subway", "rail", "railway", "high-speed rail",
            "expressway", "highway", "motorway", "freeway",
            "bridge", "tunnel", "airport", "seaport", "port",
            "infrastructure investment", "infrastructure project",
            "public transport", "bus rapid transit", "brt",
            "new urban area", "township", "satellite city"
        ],
        "secondary": [
            "infrastructure", "construction", "road", "transport",
            "transit", "development project", "investment project",
            "billion", "trillion", "vnd", "usd"
        ]
    }
}

# Vietnam location keywords for relevance check
VIETNAM_KEYWORDS = [
    "vietnam", "vietnamese", "hanoi", "ho chi minh", "hcmc", "saigon",
    "da nang", "danang", "hai phong", "haiphong", "can tho", "cantho",
    "binh duong", "dong nai", "ba ria", "vung tau", "quang ninh",
    "hai duong", "bac ninh", "vinh phuc", "hung yen", "long an",
    "binh dinh", "khanh hoa", "lam dong", "phu quoc", "mekong",
    "red river", "evn", "petrovietnam", "pvn", "vingroup", "vietjet"
]

# Non-Vietnam countries to filter out
NON_VIETNAM_COUNTRIES = [
    "singapore", "malaysia", "thailand", "indonesia", "philippines",
    "cambodia", "laos", "myanmar", "china", "japan", "korea", "india",
    "taiwan", "hong kong", "australia", "russia", "uk ", "u.k.", "u.s.",
    "usa", "america", "europe", "africa"
]

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def clean_html(text):
    """Remove HTML tags and decode entities"""
    if not text:
        return ""
    soup = BeautifulSoup(text, 'html.parser')
    return html.unescape(soup.get_text(separator=' ', strip=True))


def generate_url_hash(url):
    """Generate MD5 hash of URL for duplicate detection"""
    return hashlib.md5(url.encode()).hexdigest()


def is_english_title(title):
    """Check if title is primarily English"""
    if not title:
        return False
    # Count ASCII letters vs non-ASCII
    ascii_letters = sum(1 for c in title if c.isascii() and c.isalpha())
    non_ascii = sum(1 for c in title if not c.isascii())
    total_letters = ascii_letters + non_ascii
    if total_letters == 0:
        return False
    return (ascii_letters / total_letters) > 0.7


def is_vietnam_related(title, summary=""):
    """Check if article is related to Vietnam"""
    text = f"{title} {summary}".lower()
    
    # Check for Vietnam keywords
    has_vietnam = any(kw in text for kw in VIETNAM_KEYWORDS)
    
    # Check for non-Vietnam country focus
    has_other_country = False
    for country in NON_VIETNAM_COUNTRIES:
        if country in text:
            # Make sure Vietnam is also mentioned prominently
            vietnam_count = text.count("vietnam")
            country_count = text.count(country)
            if country_count > vietnam_count:
                has_other_country = True
                break
    
    return has_vietnam and not has_other_country


def classify_sector(title, summary=""):
    """Classify article into infrastructure sector"""
    text = f"{title} {summary}".lower()
    
    matches = []
    
    for sector, keywords in SECTOR_KEYWORDS.items():
        score = 0
        # Primary keywords - strong match
        for kw in keywords["primary"]:
            if kw in text:
                score += 2
        # Secondary keywords - weak match
        for kw in keywords.get("secondary", []):
            if kw in text:
                score += 1
        
        if score > 0:
            matches.append((sector, score))
    
    if matches:
        # Return sector with highest score
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[0][0]
    
    return None


def parse_date(date_str):
    """Parse various date formats"""
    if not date_str:
        return None
    
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    
    # Try feedparser's date parser
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str)
    except:
        pass
    
    return None


def fetch_rss_robust(url, timeout=30):
    """Fetch RSS with robust error handling for malformed feeds"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        content = response.text
        
        # Try standard feedparser first
        feed = feedparser.parse(content)
        if feed.entries:
            return feed
        
        # If feedparser fails, try cleaning the XML
        # Remove invalid characters
        content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', content)
        
        # Fix common XML issues
        content = content.replace('&nbsp;', ' ')
        content = content.replace('&amp;amp;', '&amp;')
        
        # Try parsing again
        feed = feedparser.parse(content)
        if feed.entries:
            return feed
        
        # Last resort: extract items manually with regex
        items = []
        item_pattern = re.compile(r'<item>(.*?)</item>', re.DOTALL | re.IGNORECASE)
        title_pattern = re.compile(r'<title[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', re.DOTALL | re.IGNORECASE)
        link_pattern = re.compile(r'<link[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>', re.DOTALL | re.IGNORECASE)
        desc_pattern = re.compile(r'<description[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>', re.DOTALL | re.IGNORECASE)
        date_pattern = re.compile(r'<pubDate[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</pubDate>', re.DOTALL | re.IGNORECASE)
        
        for item_match in item_pattern.finditer(content):
            item_content = item_match.group(1)
            
            title_match = title_pattern.search(item_content)
            link_match = link_pattern.search(item_content)
            desc_match = desc_pattern.search(item_content)
            date_match = date_pattern.search(item_content)
            
            if title_match and link_match:
                item = {
                    'title': clean_html(title_match.group(1).strip()),
                    'link': link_match.group(1).strip(),
                    'summary': clean_html(desc_match.group(1).strip()) if desc_match else '',
                    'published': date_match.group(1).strip() if date_match else '',
                }
                items.append(type('Entry', (), item)())
        
        if items:
            return type('Feed', (), {'entries': items, 'bozo': False})()
        
        return feed
        
    except Exception as e:
        logger.warning(f"   Error fetching {url}: {e}")
        return type('Feed', (), {'entries': [], 'bozo': True, 'bozo_exception': str(e)})()


# ============================================================
# DATABASE FUNCTIONS
# ============================================================

def init_database(db_path):
    """Initialize SQLite database"""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url_hash TEXT UNIQUE,
            url TEXT,
            title TEXT,
            title_vi TEXT,
            title_ko TEXT,
            summary TEXT,
            summary_vi TEXT,
            summary_ko TEXT,
            source TEXT,
            sector TEXT,
            area TEXT,
            province TEXT,
            published_date TEXT,
            collected_date TEXT,
            processed INTEGER DEFAULT 0
        )
    ''')
    
    conn.commit()
    return conn


def get_existing_urls(conn):
    """Get set of existing URL hashes"""
    cursor = conn.cursor()
    cursor.execute("SELECT url_hash FROM articles")
    return {row[0] for row in cursor.fetchall()}


def save_article(conn, article):
    """Save article to database"""
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            INSERT INTO articles (
                url_hash, url, title, summary, source, sector, area,
                province, published_date, collected_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            article['url_hash'],
            article['url'],
            article['title'],
            article.get('summary', ''),
            article['source'],
            article['sector'],
            article.get('area', 'Environment'),
            article.get('province', 'Vietnam'),
            article.get('published_date', ''),
            datetime.now().isoformat()
        ))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


# ============================================================
# MAIN COLLECTION FUNCTION
# ============================================================

def collect_news(hours_back=24):
    """Collect news from all RSS feeds"""
    
    # Initialize database
    conn = init_database(DB_PATH)
    existing_urls = get_existing_urls(conn)
    logger.info(f"Loaded {len(existing_urls)} existing URLs")
    
    # Calculate cutoff time
    cutoff_time = datetime.now() - timedelta(hours=hours_back)
    logger.info(f"Collecting news from last {hours_back} hours")
    logger.info(f"Cutoff time: {cutoff_time.strftime('%Y-%m-%d %H:%M')}")
    
    total_collected = 0
    total_entries = 0
    total_recent = 0
    total_no_match = 0
    
    for source_name, feed_url in RSS_FEEDS.items():
        logger.info(f"\n{'='*50}")
        logger.info(f"📰 {source_name}")
        logger.info(f"   URL: {feed_url}")
        
        # Fetch feed
        feed = fetch_rss_robust(feed_url)
        
        if feed.bozo and not feed.entries:
            if hasattr(feed, 'bozo_exception'):
                logger.warning(f"   ⚠️ Feed parsing issue: {feed.bozo_exception}")
            logger.info(f"   Found 0 entries")
            logger.info(f"   Summary: found=0, collected=0, skipped=0, no_match=0")
            continue
        
        entries = feed.entries
        logger.info(f"   Found {len(entries)} entries")
        total_entries += len(entries)
        
        source_collected = 0
        source_skipped = 0
        source_no_match = 0
        
        for entry in entries:
            title = getattr(entry, 'title', '')
            if not title:
                continue
            
            title = clean_html(title)
            link = getattr(entry, 'link', '')
            summary = clean_html(getattr(entry, 'summary', getattr(entry, 'description', '')))
            published = getattr(entry, 'published', getattr(entry, 'pubDate', ''))
            
            # Skip non-English
            if not is_english_title(title):
                logger.info(f"   ✗ Non-English title skipped: {title[:60]}...")
                continue
            
            logger.info(f"   Checking: {title[:70]}...")
            
            # Check if already collected
            url_hash = generate_url_hash(link)
            if url_hash in existing_urls:
                source_skipped += 1
                continue
            
            # Parse date and check recency
            pub_date = parse_date(published)
            if pub_date:
                # Make timezone-naive for comparison
                if pub_date.tzinfo:
                    pub_date = pub_date.replace(tzinfo=None)
                if pub_date < cutoff_time:
                    continue
                total_recent += 1
            
            # Check Vietnam relevance
            if not is_vietnam_related(title, summary):
                logger.info(f"    ✗ Not Vietnam: {title[:50]}...")
                source_no_match += 1
                total_no_match += 1
                continue
            
            # Classify sector
            sector = classify_sector(title, summary)
            if not sector:
                logger.info(f"    ✗ No sector match: {title[:50]}...")
                source_no_match += 1
                total_no_match += 1
                continue
            
            # Determine area
            area = "Environment" if sector in ["Waste Water", "Solid Waste"] else \
                   "Energy" if sector in ["Power", "Oil & Gas"] else "Urban Development"
            
            # Save article
            article = {
                'url_hash': url_hash,
                'url': link,
                'title': title,
                'summary': summary[:1000] if summary else '',
                'source': source_name,
                'sector': sector,
                'area': area,
                'published_date': pub_date.isoformat() if pub_date else ''
            }
            
            if save_article(conn, article):
                existing_urls.add(url_hash)
                source_collected += 1
                total_collected += 1
                logger.info(f"    ✓ Saved [{sector}]: {title[:50]}...")
        
        logger.info(f"   Summary: found={len(entries)}, collected={source_collected}, skipped={source_skipped}, no_match={source_no_match}")
    
    conn.close()
    
    # Print summary
    logger.info(f"\n{'='*60}")
    logger.info("COLLECTION SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"Total RSS entries: {total_entries}")
    logger.info(f"Recent entries (within {hours_back}h): {total_recent}")
    logger.info(f"Collected (infra): {total_collected}")
    logger.info(f"No sector match: {total_no_match}")
    logger.info(f"{'='*60}")
    
    return total_collected


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("VIETNAM INFRASTRUCTURE NEWS COLLECTOR")
    print("=" * 60)
    print()
    
    collected = collect_news(HOURS_BACK)
    
    print()
    print("=" * 50)
    print(f"TOTAL COLLECTED: {collected}")
    print()
    print(f"Total: {collected} articles collected")
