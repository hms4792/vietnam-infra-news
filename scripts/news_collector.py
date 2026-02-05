#!/usr/bin/env python3
"""
Vietnam Infrastructure News Collector
Version 2.0 - Updated RSS feeds and improved sector classification
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

import requests
import feedparser
from bs4 import BeautifulSoup

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(Y-%m-%d %H:%M:%S - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ============================================================
# CONFIGURATION
# ============================================================

# Database path - matches workflow expectation
DB_PATH = os.environ.get('DB_PATH', 'data/vietnam_infrastructure_news.db')

# Hours to look back for news
HOURS_BACK = int(os.environ.get('HOURS_BACK', 24))

# ============================================================
# UPDATED RSS FEEDS - Verified working URLs (Feb 2026)
# ============================================================

RSS_FEEDS = {
    # VnExpress - Working
    "VnExpress English": "https://e.vnexpress.net/rss/news.rss",
    "VnExpress Business": "https://e.vnexpress.net/rss/business.rss",
    
    # Vietnam News (VNA) - Updated URLs
    "Vietnam News Economy": "https://vietnamnews.vn/rss/economy.rss",
    "Vietnam News Politics": "https://vietnamnews.vn/rss/politics-laws.rss",
    "Vietnam News Society": "https://vietnamnews.vn/rss/society.rss",
    "Vietnam News Environment": "https://vietnamnews.vn/rss/environment.rss",
    "Vietnam News Industries": "https://vietnamnews.vn/rss/industries.rss",
    
    # DTiNews (Dan Tri International)
    "DTiNews": "https://dtinews.vn/rss/home.rss",
    
    # VNA English
    "VNA English": "https://en.vnanet.vn/rss/home.rss",
    
    # Bizhub (VNA Business)
    "Bizhub VNA": "https://bnews.vn/rss/home.rss",
}

# ============================================================
# STRICT INFRASTRUCTURE SECTOR KEYWORDS
# Only true infrastructure projects - no general news
# ============================================================

SECTOR_KEYWORDS = {
    "Waste Water": {
        "primary": [
            "wastewater", "waste water", "sewage", "water treatment",
            "drainage", "water supply", "clean water", "tap water",
            "water infrastructure", "water project", "water plant",
            "water system", "sanitation", "water network"
        ],
        "secondary": [
            "treatment plant", "purification", "effluent", "sludge",
            "pumping station", "reservoir", "water utility"
        ]
    },
    "Solid Waste": {
        "primary": [
            "solid waste", "garbage", "trash", "landfill", "waste management",
            "recycling", "incineration", "waste-to-energy", "wte",
            "municipal waste", "hazardous waste", "waste collection",
            "waste treatment"
        ],
        "secondary": [
            "disposal", "rubbish", "compost", "plastic waste", "waste plant"
        ]
    },
    "Power": {
        "primary": [
            "power plant", "power station", "electricity generation",
            "thermal power", "coal power", "gas power", "gas turbine",
            "hydropower", "hydro power", "hydroelectric",
            "wind power", "wind farm", "wind energy", "offshore wind",
            "solar power", "solar farm", "solar energy", "photovoltaic",
            "renewable energy", "clean energy", "green energy",
            "power grid", "transmission line", "substation", "transformer",
            "lng terminal", "lng plant", "liquefied natural gas",
            "battery storage", "energy storage",
            "power capacity", "megawatt", "gigawatt"
        ],
        "secondary": [
            "evn", "vietnam electricity", "power project", "energy project"
        ]
    },
    "Oil & Gas": {
        "primary": [
            "oil and gas", "oil & gas", "petroleum", "refinery",
            "oil field", "gas field", "offshore oil", "offshore gas",
            "pipeline", "gas pipeline", "oil pipeline",
            "petrochemical", "natural gas", "crude oil",
            "exploration", "drilling", "upstream", "downstream"
        ],
        "secondary": [
            "petrovietnam", "pvn", "binh son refinery", "nghi son", "dung quat"
        ]
    },
    "Industrial Parks": {
        "primary": [
            "industrial park", "industrial zone", "industrial complex",
            "economic zone", "export processing zone", "free trade zone",
            "manufacturing hub", "tech park", "hi-tech park", "high-tech park",
            "industrial estate", "industrial cluster", "special economic zone"
        ],
        "secondary": [
            "industrial land", "factory zone", "manufacturing zone"
        ]
    },
    "Smart City": {
        "primary": [
            "smart city", "smart urban", "digital city",
            "intelligent transport", "smart traffic", "traffic management system",
            "smart grid", "smart meter",
            "iot infrastructure", "5g infrastructure", "5g network",
            "digital transformation infrastructure",
            "smart building", "building automation",
            "surveillance system", "cctv system", "ai camera"
        ],
        "secondary": [
            "smart infrastructure", "digital infrastructure"
        ]
    },
    "Urban Development": {
        "primary": [
            # Rail/Metro
            "metro line", "metro project", "subway", "urban rail",
            "light rail", "railway project", "high-speed rail", "high speed rail",
            "rail line", "train station",
            # Roads
            "expressway", "highway", "motorway", "freeway",
            "ring road", "bypass", "overpass", "flyover", "interchange",
            # Bridges/Tunnels
            "bridge project", "bridge construction", "tunnel project",
            # Airports/Ports
            "airport project", "airport expansion", "airport terminal",
            "seaport", "port project", "port expansion", "container terminal",
            "long thanh airport",
            # Urban projects
            "urban development project", "city planning project",
            "new urban area", "township project", "satellite city",
            "public transport", "bus rapid transit", "brt"
        ],
        "secondary": [
            "infrastructure investment", "infrastructure project",
            "construction project", "development project"
        ]
    }
}

# Keywords that EXCLUDE articles (not infrastructure)
EXCLUDE_KEYWORDS = [
    # Crime/Legal
    "arrest", "jail", "prison", "sentenced", "trafficking", "smuggling",
    "fraud", "corruption", "bribery", "murder", "killed", "death",
    "crime", "criminal", "police bust", "drug",
    # Trade/Commerce (not infrastructure)
    "export", "import", "trade", "tariff", "customs",
    "agricultural", "seafood", "rice", "coffee", "fruit",
    # Finance (not infrastructure)
    "gold price", "stock", "forex", "exchange rate", "dollar",
    "bonus", "salary", "wage",
    # General news
    "fire", "accident", "flood", "storm", "earthquake",
    "covid", "pandemic", "virus", "disease",
    "tourism", "tourist", "travel", "hotel", "resort",
    "education", "university", "school", "student",
    "sports", "football", "soccer", "tennis",
    # Politics (general)
    "party congress", "politburo", "party chief", "state visit"
]

# Vietnam location keywords for relevance check
VIETNAM_KEYWORDS = [
    "vietnam", "vietnamese", "hanoi", "ho chi minh", "hcmc", "saigon",
    "da nang", "danang", "hai phong", "haiphong", "can tho", "cantho",
    "binh duong", "dong nai", "ba ria", "vung tau", "quang ninh",
    "hai duong", "bac ninh", "vinh phuc", "hung yen", "long an",
    "binh dinh", "khanh hoa", "lam dong", "phu quoc", "mekong",
    "red river", "evn", "petrovietnam", "pvn", "vingroup"
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
            vietnam_count = text.count("vietnam")
            country_count = text.count(country)
            if country_count > vietnam_count:
                has_other_country = True
                break
    
    return has_vietnam and not has_other_country


def should_exclude(title, summary=""):
    """Check if article should be excluded based on keywords"""
    text = f"{title} {summary}".lower()
    
    for keyword in EXCLUDE_KEYWORDS:
        if keyword in text:
            return True
    
    return False


def classify_sector(title, summary=""):
    """Classify article into infrastructure sector - STRICT matching"""
    text = f"{title} {summary}".lower()
    
    # First check exclusions
    if should_exclude(title, summary):
        return None
    
    matches = []
    
    for sector, keywords in SECTOR_KEYWORDS.items():
        score = 0
        matched_keywords = []
        
        # Primary keywords - strong match (must have at least one)
        for kw in keywords["primary"]:
            if kw in text:
                score += 3
                matched_keywords.append(kw)
        
        # Secondary keywords - weak match
        for kw in keywords.get("secondary", []):
            if kw in text:
                score += 1
                matched_keywords.append(kw)
        
        # Only count if we have at least one PRIMARY keyword match
        primary_match = any(kw in text for kw in keywords["primary"])
        if primary_match and score > 0:
            matches.append((sector, score, matched_keywords))
    
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
    
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str)
    except:
        pass
    
    return None


def fetch_rss_robust(url, timeout=30):
    """Fetch RSS with robust error handling"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        content = response.text
        
        # Clean content
        content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', content)
        content = content.replace('&nbsp;', ' ')
        
        feed = feedparser.parse(content)
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
    total_excluded = 0
    
    for source_name, feed_url in RSS_FEEDS.items():
        logger.info(f"\n{'='*50}")
        logger.info(f"📰 {source_name}")
        logger.info(f"   URL: {feed_url}")
        
        feed = fetch_rss_robust(feed_url)
        
        if feed.bozo and not feed.entries:
            if hasattr(feed, 'bozo_exception'):
                logger.warning(f"   ⚠️ Feed parsing issue: {feed.bozo_exception}")
            logger.info(f"   Found 0 entries")
            continue
        
        entries = feed.entries
        logger.info(f"   Found {len(entries)} entries")
        total_entries += len(entries)
        
        source_collected = 0
        source_skipped = 0
        source_no_match = 0
        source_excluded = 0
        
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
            
            # Check exclusions first
            if should_exclude(title, summary):
                logger.info(f"    ✗ Excluded (not infra): {title[:50]}...")
                source_excluded += 1
                total_excluded += 1
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
        
        logger.info(f"   Summary: found={len(entries)}, collected={source_collected}, excluded={source_excluded}, no_match={source_no_match}")
    
    conn.close()
    
    # Print summary
    logger.info(f"\n{'='*60}")
    logger.info("COLLECTION SUMMARY")
    logger.info(f"{'='*60}")
    logger.info(f"Total RSS entries: {total_entries}")
    logger.info(f"Recent entries (within {hours_back}h): {total_recent}")
    logger.info(f"Excluded (not infra): {total_excluded}")
    logger.info(f"No sector match: {total_no_match}")
    logger.info(f"Collected (infra): {total_collected}")
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
