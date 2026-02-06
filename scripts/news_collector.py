#!/usr/bin/env python3
"""
Vietnam Infrastructure News Collector
Version 3.0 - Fixed logging issues and expanded keywords
"""

import os
import sys
import json
import re
import sqlite3
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse
import html

import requests
import feedparser
from bs4 import BeautifulSoup

# ============================================================
# CONFIGURATION
# ============================================================

DB_PATH = os.environ.get('DB_PATH', 'data/vietnam_infrastructure_news.db')
HOURS_BACK = int(os.environ.get('HOURS_BACK', 24))

# ============================================================
# VIETNAM PROVINCES - For location extraction
# ============================================================

PROVINCE_KEYWORDS = {
    # Major cities
    "Ho Chi Minh City": ["ho chi minh", "hcmc", "saigon", "sai gon", "hồ chí minh"],
    "Hanoi": ["hanoi", "ha noi", "hà nội"],
    "Da Nang": ["da nang", "đà nẵng", "danang"],
    "Hai Phong": ["hai phong", "hải phòng", "haiphong"],
    "Can Tho": ["can tho", "cần thơ", "cantho"],
    
    # Southern provinces
    "Binh Duong": ["binh duong", "bình dương"],
    "Dong Nai": ["dong nai", "đồng nai"],
    "Ba Ria - Vung Tau": ["ba ria", "vung tau", "vũng tàu", "bà rịa"],
    "Long An": ["long an"],
    "Tay Ninh": ["tay ninh", "tây ninh"],
    "Binh Phuoc": ["binh phuoc", "bình phước"],
    
    # Northern provinces
    "Quang Ninh": ["quang ninh", "quảng ninh", "ha long", "hạ long"],
    "Bac Ninh": ["bac ninh", "bắc ninh"],
    "Hai Duong": ["hai duong", "hải dương"],
    "Hung Yen": ["hung yen", "hưng yên"],
    "Vinh Phuc": ["vinh phuc", "vĩnh phúc"],
    "Thai Nguyen": ["thai nguyen", "thái nguyên"],
    "Bac Giang": ["bac giang", "bắc giang"],
    
    # Central provinces
    "Thanh Hoa": ["thanh hoa", "thanh hoá"],
    "Nghe An": ["nghe an", "nghệ an"],
    "Ha Tinh": ["ha tinh", "hà tĩnh"],
    "Quang Binh": ["quang binh", "quảng bình"],
    "Quang Tri": ["quang tri", "quảng trị"],
    "Thua Thien Hue": ["thua thien hue", "huế", "hue"],
    "Quang Nam": ["quang nam", "quảng nam"],
    "Quang Ngai": ["quang ngai", "quảng ngãi"],
    "Binh Dinh": ["binh dinh", "bình định"],
    "Phu Yen": ["phu yen", "phú yên"],
    "Khanh Hoa": ["khanh hoa", "khánh hòa", "nha trang"],
    "Ninh Thuan": ["ninh thuan", "ninh thuận"],
    "Binh Thuan": ["binh thuan", "bình thuận", "phan thiet"],
    
    # Highland provinces
    "Lam Dong": ["lam dong", "lâm đồng", "da lat", "đà lạt"],
    "Dak Lak": ["dak lak", "đắk lắk", "buon ma thuot"],
    "Gia Lai": ["gia lai"],
    "Kon Tum": ["kon tum"],
    
    # Mekong Delta
    "Tien Giang": ["tien giang", "tiền giang"],
    "Ben Tre": ["ben tre", "bến tre"],
    "Vinh Long": ["vinh long", "vĩnh long"],
    "Tra Vinh": ["tra vinh", "trà vinh"],
    "Dong Thap": ["dong thap", "đồng tháp"],
    "An Giang": ["an giang"],
    "Kien Giang": ["kien giang", "kiên giang", "phu quoc", "phú quốc"],
    "Hau Giang": ["hau giang", "hậu giang"],
    "Soc Trang": ["soc trang", "sóc trăng"],
    "Bac Lieu": ["bac lieu", "bạc liêu"],
    "Ca Mau": ["ca mau", "cà mau"],
    
    # Special projects
    "Long Thanh": ["long thanh", "long thành"],  # Airport project
}

# ============================================================
# RSS FEEDS - Verified working URLs
# ============================================================

RSS_FEEDS = {
    "VnExpress English": "https://e.vnexpress.net/rss/news.rss",
    "VnExpress Business": "https://e.vnexpress.net/rss/business.rss",
    "Vietnam News Economy": "https://vietnamnews.vn/rss/economy.rss",
    "Vietnam News Politics": "https://vietnamnews.vn/rss/politics-laws.rss",
    "Vietnam News Society": "https://vietnamnews.vn/rss/society.rss",
    "Vietnam News Environment": "https://vietnamnews.vn/rss/environment.rss",
    "Vietnam News Industries": "https://vietnamnews.vn/rss/industries.rss",
}

# ============================================================
# SECTOR KEYWORDS - Expanded for better matching
# ============================================================

SECTOR_KEYWORDS = {
    "Waste Water": {
        "primary": [
            "wastewater", "waste water", "sewage", "water treatment",
            "drainage", "water supply", "clean water", "tap water",
            "water infrastructure", "water project", "water plant",
            "water system", "sanitation", "water network",
            "water utility", "drinking water", "groundwater"
        ]
    },
    "Solid Waste": {
        "primary": [
            "solid waste", "garbage", "trash", "landfill", "waste management",
            "recycling", "incineration", "waste-to-energy", "wte",
            "municipal waste", "hazardous waste", "waste collection",
            "waste treatment", "waste disposal"
        ]
    },
    "Power": {
        "primary": [
            "power plant", "power station", "electricity", "power generation",
            "thermal power", "coal power", "gas power", "gas turbine",
            "hydropower", "hydro power", "hydroelectric",
            "wind power", "wind farm", "wind energy", "offshore wind",
            "solar power", "solar farm", "solar energy", "photovoltaic",
            "renewable energy", "clean energy", "green energy",
            "power grid", "transmission line", "substation", "transformer",
            "lng terminal", "lng plant", "liquefied natural gas",
            "battery storage", "energy storage", "energy transition",
            "power capacity", "megawatt", "gigawatt", "mw capacity", "gw capacity",
            "evn", "vietnam electricity", "power project"
        ]
    },
    "Oil & Gas": {
        "primary": [
            "oil and gas", "oil & gas", "petroleum", "refinery",
            "oil field", "gas field", "offshore oil", "offshore gas",
            "pipeline", "gas pipeline", "oil pipeline",
            "petrochemical", "natural gas", "crude oil",
            "exploration", "drilling", "upstream", "downstream",
            "petrovietnam", "pvn", "binh son", "nghi son", "dung quat"
        ]
    },
    "Industrial Parks": {
        "primary": [
            "industrial park", "industrial zone", "industrial complex",
            "economic zone", "export processing", "free trade zone",
            "manufacturing hub", "tech park", "hi-tech park", "high-tech park",
            "industrial estate", "industrial cluster", "special economic zone",
            "industrial land", "factory zone", "industrial area"
        ]
    },
    "Smart City": {
        "primary": [
            "smart city", "smart urban", "digital city",
            "intelligent transport", "smart traffic", "traffic management",
            "smart grid", "smart meter", "smart building",
            "iot infrastructure", "5g infrastructure", "5g network",
            "digital transformation", "e-government",
            "surveillance system", "cctv", "ai camera"
        ]
    },
    "Urban Development": {
        "primary": [
            # Rail/Metro
            "metro", "metro line", "subway", "urban rail", "light rail",
            "railway", "high-speed rail", "high speed rail", "rail project",
            # Roads
            "expressway", "highway", "motorway", "freeway",
            "ring road", "bypass", "overpass", "flyover", "interchange",
            "road project", "road construction",
            # Bridges/Tunnels
            "bridge", "tunnel", "viaduct",
            # Airports/Ports
            "airport", "terminal", "runway",
            "seaport", "port", "container terminal", "logistics hub",
            "long thanh",
            # Urban projects
            "urban development", "city planning", "urban planning",
            "new urban area", "township", "satellite city",
            "public transport", "bus rapid transit", "brt",
            # Infrastructure general
            "infrastructure investment", "infrastructure project",
            "infrastructure development", "construction project",
            "billion usd", "billion dollar", "trillion vnd"
        ]
    }
}

# Keywords that EXCLUDE articles
EXCLUDE_KEYWORDS = [
    "arrest", "jail", "prison", "sentenced", "trafficking", "smuggling",
    "fraud", "corruption", "murder", "killed", "death", "crime", "drug",
    "gold price", "gold prices", "stock market", "forex", "exchange rate",
    "export jump", "export rise", "import", "seafood export", "agricultural export",
    "fire kills", "accident", "tourist", "tourism", "hotel", "resort",
    "education", "university", "school", "student", "scholarship",
    "sports", "football", "soccer", "tennis", "basketball",
    "party congress", "politburo", "state visit"
]

# Vietnam keywords
VIETNAM_KEYWORDS = [
    "vietnam", "vietnamese", "hanoi", "ho chi minh", "hcmc", "saigon",
    "da nang", "hai phong", "can tho", "binh duong", "dong nai",
    "ba ria", "vung tau", "quang ninh", "bac ninh", "long an",
    "mekong", "evn", "petrovietnam", "vingroup", "vietjet"
]

NON_VIETNAM_COUNTRIES = [
    "singapore", "malaysia", "thailand", "indonesia", "philippines",
    "cambodia", "laos", "myanmar", "china", "japan", "korea", "india",
    "taiwan", "hong kong", "australia", "russia", "uk ", "usa", "america"
]


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def log(message):
    """Simple print-based logging to avoid format issues"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"{timestamp} - {message}")


def clean_html(text):
    if not text:
        return ""
    soup = BeautifulSoup(text, 'html.parser')
    return html.unescape(soup.get_text(separator=' ', strip=True))


def generate_url_hash(url):
    return hashlib.md5(url.encode()).hexdigest()


def extract_province(title, summary=""):
    """Extract province/city from article title and summary"""
    text = f"{title} {summary}".lower()
    
    # Check each province
    for province, keywords in PROVINCE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                return province
    
    return "Vietnam"  # Default if no specific location found


def is_english_title(title):
    if not title:
        return False
    ascii_letters = sum(1 for c in title if c.isascii() and c.isalpha())
    non_ascii = sum(1 for c in title if not c.isascii())
    total = ascii_letters + non_ascii
    if total == 0:
        return False
    return (ascii_letters / total) > 0.7


def is_vietnam_related(title, summary=""):
    text = f"{title} {summary}".lower()
    has_vietnam = any(kw in text for kw in VIETNAM_KEYWORDS)
    
    for country in NON_VIETNAM_COUNTRIES:
        if country in text:
            if text.count("vietnam") < text.count(country):
                return False
    
    return has_vietnam


def should_exclude(title, summary=""):
    text = f"{title} {summary}".lower()
    for keyword in EXCLUDE_KEYWORDS:
        if keyword in text:
            return True
    return False


def classify_sector(title, summary=""):
    text = f"{title} {summary}".lower()
    
    if should_exclude(title, summary):
        return None
    
    best_match = None
    best_score = 0
    
    for sector, keywords in SECTOR_KEYWORDS.items():
        score = 0
        for kw in keywords["primary"]:
            if kw in text:
                score += 1
        
        if score > best_score:
            best_score = score
            best_match = sector
    
    return best_match if best_score > 0 else None


def parse_date(date_str):
    if not date_str:
        return None
    
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
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


def fetch_rss(url, timeout=30):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        content = response.text
        content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', content)
        return feedparser.parse(content)
    except Exception as e:
        log(f"   Error fetching {url}: {e}")
        return type('Feed', (), {'entries': [], 'bozo': True})()


# ============================================================
# DATABASE FUNCTIONS
# ============================================================

def init_database(db_path):
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
    cursor = conn.cursor()
    cursor.execute("SELECT url_hash FROM articles")
    return {row[0] for row in cursor.fetchall()}


def save_article(conn, article):
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
    conn = init_database(DB_PATH)
    existing_urls = get_existing_urls(conn)
    log(f"Loaded {len(existing_urls)} existing URLs")
    
    cutoff_time = datetime.now() - timedelta(hours=hours_back)
    log(f"Collecting news from last {hours_back} hours")
    log(f"Cutoff time: {cutoff_time.strftime('%Y-%m-%d %H:%M')}")
    
    total_collected = 0
    total_entries = 0
    
    for source_name, feed_url in RSS_FEEDS.items():
        print("")
        print("=" * 50)
        log(f"Source: {source_name}")
        log(f"URL: {feed_url}")
        
        feed = fetch_rss(feed_url)
        
        if feed.bozo and not feed.entries:
            log("Feed error or empty")
            continue
        
        entries = feed.entries
        log(f"Found {len(entries)} entries")
        total_entries += len(entries)
        
        source_collected = 0
        
        for entry in entries:
            title = getattr(entry, 'title', '')
            if not title:
                continue
            
            title = clean_html(title)
            link = getattr(entry, 'link', '')
            summary = clean_html(getattr(entry, 'summary', getattr(entry, 'description', '')))
            published = getattr(entry, 'published', getattr(entry, 'pubDate', ''))
            
            if not is_english_title(title):
                continue
            
            url_hash = generate_url_hash(link)
            if url_hash in existing_urls:
                continue
            
            pub_date = parse_date(published)
            if pub_date:
                if pub_date.tzinfo:
                    pub_date = pub_date.replace(tzinfo=None)
                if pub_date < cutoff_time:
                    continue
            
            if not is_vietnam_related(title, summary):
                continue
            
            sector = classify_sector(title, summary)
            if not sector:
                continue
            
            area = "Environment" if sector in ["Waste Water", "Solid Waste"] else \
                   "Energy" if sector in ["Power", "Oil & Gas"] else "Urban Development"
            
            # Extract province from title/summary
            province = extract_province(title, summary)
            
            article = {
                'url_hash': url_hash,
                'url': link,
                'title': title,
                'summary': summary[:1000] if summary else '',
                'source': source_name,
                'sector': sector,
                'area': area,
                'province': province,
                'published_date': pub_date.isoformat() if pub_date else ''
            }
            
            if save_article(conn, article):
                existing_urls.add(url_hash)
                source_collected += 1
                total_collected += 1
                log(f"  SAVED [{sector}] [{province}]: {title[:50]}...")
        
        log(f"Collected from {source_name}: {source_collected}")
    
    conn.close()
    
    print("")
    print("=" * 60)
    print("COLLECTION SUMMARY")
    print("=" * 60)
    print(f"Total RSS entries: {total_entries}")
    print(f"Total collected: {total_collected}")
    print("=" * 60)
    
    return total_collected


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("VIETNAM INFRASTRUCTURE NEWS COLLECTOR")
    print("=" * 60)
    print("")
    
    collected = collect_news(HOURS_BACK)
    
    print("")
    print("=" * 50)
    print(f"TOTAL COLLECTED: {collected}")
    print("")
    print(f"Total: {collected} articles collected")
