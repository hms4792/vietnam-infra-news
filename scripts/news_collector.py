#!/usr/bin/env python3
"""
Vietnam Infrastructure News Collector
Version 4.0 - Expanded RSS sources with auto-discovery
"""

import os
import sys
import json
import re
import sqlite3
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse, urljoin
import html
import concurrent.futures
import time

import requests
import feedparser
from bs4 import BeautifulSoup

# ============================================================
# CONFIGURATION
# ============================================================

DB_PATH = os.environ.get('DB_PATH', 'data/vietnam_infrastructure_news.db')
HOURS_BACK = int(os.environ.get('HOURS_BACK', 24))
EXCEL_PATH = os.environ.get('EXCEL_PATH', 'data/database/Vietnam_Infra_News_Database_Final.xlsx')

# RSS Discovery settings
RSS_DISCOVERY_TIMEOUT = 5  # seconds per request
RSS_DISCOVERY_MAX_WORKERS = 10  # parallel requests
ENABLE_RSS_DISCOVERY = os.environ.get('ENABLE_RSS_DISCOVERY', 'false').lower() == 'true'

# Language filter settings
# 'english' = only English articles
# 'vietnamese' = only Vietnamese articles  
# 'all' = both English and Vietnamese
LANGUAGE_FILTER = os.environ.get('LANGUAGE_FILTER', 'english').lower()

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
    # ============================================================
    # ENGLISH NEWS SOURCES
    # ============================================================
    # VnExpress English
    "VnExpress English - News": "https://e.vnexpress.net/rss/news.rss",
    "VnExpress English - Business": "https://e.vnexpress.net/rss/business.rss",
    
    # Vietnam News
    "Vietnam News - Economy": "https://vietnamnews.vn/rss/economy.rss",
    "Vietnam News - Politics": "https://vietnamnews.vn/rss/politics-laws.rss",
    "Vietnam News - Society": "https://vietnamnews.vn/rss/society.rss",
    "Vietnam News - Environment": "https://vietnamnews.vn/rss/environment.rss",
    
    # VietnamPlus English
    "VietnamPlus English": "https://en.vietnamplus.vn/rss/news.rss",
    
    # Hanoi Times
    "Hanoi Times": "https://hanoitimes.vn/rss/news.rss",
    
    # VietnamNet English
    "VietnamNet English": "https://vietnamnet.vn/en/rss/home.rss",
    
    # The Investor
    "The Investor": "https://theinvestor.vn/rss.html",
    
    # VIR - Vietnam Investment Review
    "VIR": "https://vir.com.vn/rss/all.rss",
    
    # Tuoi Tre News (English)
    "Tuoi Tre News": "https://tuoitrenews.vn/rss/all.rss",
    
    # SGGP News English
    "SGGP News English": "https://en.sggp.org.vn/rss/home.rss",
    
    # VOV World
    "VOV World": "https://vovworld.vn/en-US/rss/all.rss",
    
    # ============================================================
    # VIETNAMESE NEWS SOURCES (Major outlets)
    # ============================================================
    # VnExpress Vietnamese
    "VnExpress - Tin mới": "https://vnexpress.net/rss/tin-moi-nhat.rss",
    "VnExpress - Kinh doanh": "https://vnexpress.net/rss/kinh-doanh.rss",
    "VnExpress - Thời sự": "https://vnexpress.net/rss/thoi-su.rss",
    
    # Tuoi Tre
    "Tuoi Tre - Tin mới": "https://tuoitre.vn/rss/tin-moi-nhat.rss",
    "Tuoi Tre - Kinh doanh": "https://tuoitre.vn/rss/kinh-doanh.rss",
    
    # Thanh Nien
    "Thanh Nien - Home": "https://thanhnien.vn/rss/home.rss",
    "Thanh Nien - Kinh te": "https://thanhnien.vn/rss/kinh-te.rss",
    
    # VietnamPlus Vietnamese
    "VietnamPlus - Kinh te": "https://www.vietnamplus.vn/rss/kinhte.rss",
    "VietnamPlus - Xa hoi": "https://www.vietnamplus.vn/rss/xahoi.rss",
    
    # VietnamNet Vietnamese
    "VietnamNet - Kinh doanh": "https://vietnamnet.vn/rss/kinh-doanh.rss",
    "VietnamNet - Thoi su": "https://vietnamnet.vn/rss/thoi-su.rss",
    
    # Dan Tri
    "Dan Tri - Kinh doanh": "https://dantri.com.vn/rss/kinh-doanh.rss",
    "Dan Tri - Xa hoi": "https://dantri.com.vn/rss/xa-hoi.rss",
    
    # CafeF (Finance/Business)
    "CafeF - Home": "https://cafef.vn/rss/home.rss",
    
    # CafeBiz
    "CafeBiz - Home": "https://cafebiz.vn/rss/home.rss",
    
    # VnEconomy
    "VnEconomy - Home": "https://vneconomy.vn/rss/home.rss",
    
    # Bao Dau Tu (Investment)
    "Bao Dau Tu": "https://baodautu.vn/rss/home.rss",
    
    # ============================================================
    # SPECIALIZED SOURCES (Energy, Environment, Construction)
    # ============================================================
    # Nang Luong Vietnam (Energy)
    "Nang Luong VN": "https://nangluongvietnam.vn/rss/home.rss",
    
    # Bao Xay Dung (Construction)
    "Bao Xay Dung": "https://baoxaydung.com.vn/rss/home.rss",
    
    # Bao Tai Nguyen Moi Truong (Environment)
    "Bao TN Moi Truong": "https://baotainguyenmoitruong.vn/rss/home.rss",
    
    # Kinh Te Moi Truong (Economic Environment)
    "Kinh Te Moi Truong": "https://kinhtemoitruong.vn/rss/home.rss",
    
    # ============================================================
    # REGIONAL SOURCES
    # ============================================================
    # Ho Chi Minh City
    "SGGP": "https://www.sggp.org.vn/rss/home.rss",
    
    # Hanoi
    "Hanoi Moi": "https://hanoimoi.vn/rss/home.rss",
    
    # Da Nang
    "Bao Da Nang": "https://baodanang.vn/rss/home.rss",
    
    # Dong Nai
    "Bao Dong Nai": "https://baodongnai.com.vn/rss/home.rss",
    
    # Binh Duong
    "Bao Binh Duong": "https://baobinhduong.vn/rss/home.rss",
    
    # Quang Ninh
    "Bao Quang Ninh": "https://baoquangninh.vn/rss/home.rss",
}

# Common RSS URL patterns to try for auto-discovery
RSS_URL_PATTERNS = [
    "/rss",
    "/rss.xml",
    "/feed",
    "/feed.xml",
    "/feed/rss",
    "/rss/home.rss",
    "/rss/all.rss",
    "/rss/news.rss",
    "/rss/tin-moi-nhat.rss",
    "/en/rss/home.rss",
]

# ============================================================
# RSS AUTO-DISCOVERY FUNCTIONS
# ============================================================

def discover_rss_from_html(base_url, timeout=5):
    """
    Discover RSS feed URLs from a website's HTML.
    Looks for <link rel="alternate" type="application/rss+xml"> tags.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(base_url, headers=headers, timeout=timeout)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find RSS/Atom link tags
        rss_links = []
        for link in soup.find_all('link', rel='alternate'):
            link_type = link.get('type', '')
            if 'rss' in link_type or 'atom' in link_type or 'xml' in link_type:
                href = link.get('href', '')
                if href:
                    # Convert relative URL to absolute
                    full_url = urljoin(base_url, href)
                    rss_links.append(full_url)
        
        return rss_links
    except Exception as e:
        return []


def try_rss_patterns(base_url, timeout=5):
    """
    Try common RSS URL patterns for a given website.
    Returns list of working RSS URLs.
    """
    working_feeds = []
    
    # Normalize base URL
    if not base_url.startswith('http'):
        base_url = 'https://' + base_url
    
    parsed = urlparse(base_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    
    for pattern in RSS_URL_PATTERNS:
        rss_url = base + pattern
        try:
            response = requests.get(rss_url, timeout=timeout, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            if response.status_code == 200:
                # Verify it's actually RSS/XML
                content_type = response.headers.get('content-type', '').lower()
                content_start = response.text[:500].lower()
                
                if ('xml' in content_type or 'rss' in content_type or 
                    '<rss' in content_start or '<feed' in content_start or
                    '<?xml' in content_start):
                    
                    # Try parsing to verify
                    feed = feedparser.parse(response.content)
                    if feed.entries:
                        working_feeds.append({
                            'url': rss_url,
                            'title': feed.feed.get('title', ''),
                            'entries': len(feed.entries)
                        })
        except:
            continue
    
    return working_feeds


def discover_rss_for_site(site_info):
    """
    Discover RSS feeds for a single site.
    Returns dict with domain and discovered feeds.
    """
    domain = site_info.get('domain', '')
    url = site_info.get('url', '')
    
    if not url:
        return {'domain': domain, 'feeds': [], 'error': 'No URL'}
    
    discovered = []
    
    # Method 1: Look for RSS links in HTML
    html_feeds = discover_rss_from_html(url)
    for feed_url in html_feeds:
        discovered.append({'url': feed_url, 'method': 'html_link'})
    
    # Method 2: Try common patterns
    if not discovered:
        pattern_feeds = try_rss_patterns(url)
        for feed in pattern_feeds:
            discovered.append({
                'url': feed['url'],
                'title': feed.get('title', ''),
                'entries': feed.get('entries', 0),
                'method': 'pattern'
            })
    
    return {
        'domain': domain,
        'url': url,
        'feeds': discovered
    }


def load_sources_from_excel():
    """
    Load source sites from Excel Source sheet.
    Returns list of site info dicts.
    """
    try:
        import openpyxl
        
        if not os.path.exists(EXCEL_PATH):
            log(f"Excel file not found: {EXCEL_PATH}")
            return []
        
        wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True)
        
        # Find Source sheet
        source_sheet = None
        for name in wb.sheetnames:
            if name.lower() in ['source', 'sources', 'rss_sources']:
                source_sheet = wb[name]
                break
        
        if not source_sheet:
            log("Source sheet not found in Excel")
            return []
        
        sites = []
        headers = [cell.value for cell in source_sheet[1]]
        
        # Find column indices
        domain_col = None
        url_col = None
        status_col = None
        type_col = None
        
        for i, h in enumerate(headers):
            if h:
                h_lower = h.lower()
                if 'domain' in h_lower:
                    domain_col = i
                elif 'url' in h_lower:
                    url_col = i
                elif 'status' in h_lower:
                    status_col = i
                elif 'type' in h_lower:
                    type_col = i
        
        if url_col is None:
            log("URL column not found in Source sheet")
            return []
        
        for row in source_sheet.iter_rows(min_row=2, values_only=True):
            url = row[url_col] if url_col is not None and url_col < len(row) else None
            if not url or not isinstance(url, str):
                continue
            
            # Skip inaccessible sites
            status = row[status_col] if status_col is not None and status_col < len(row) else 'Accessible'
            if status and 'inaccessible' in str(status).lower():
                continue
            
            # Skip sites with spaces in URL (invalid)
            if ' ' in url:
                continue
            
            sites.append({
                'domain': row[domain_col] if domain_col is not None and domain_col < len(row) else '',
                'url': url,
                'type': row[type_col] if type_col is not None and type_col < len(row) else 'Media/News',
                'status': status
            })
        
        wb.close()
        return sites
        
    except Exception as e:
        log(f"Error loading sources from Excel: {e}")
        return []


def discover_all_rss_feeds(max_sites=50):
    """
    Discover RSS feeds from Source sheet sites.
    Uses parallel processing for efficiency.
    Returns dict of discovered feeds.
    """
    sites = load_sources_from_excel()
    
    if not sites:
        log("No sites loaded from Excel")
        return {}
    
    # Limit number of sites to check
    sites = sites[:max_sites]
    log(f"Discovering RSS feeds for {len(sites)} sites...")
    
    discovered_feeds = {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=RSS_DISCOVERY_MAX_WORKERS) as executor:
        future_to_site = {
            executor.submit(discover_rss_for_site, site): site 
            for site in sites
        }
        
        for future in concurrent.futures.as_completed(future_to_site):
            try:
                result = future.result()
                domain = result.get('domain', 'unknown')
                feeds = result.get('feeds', [])
                
                if feeds:
                    discovered_feeds[domain] = feeds
                    log(f"  Found {len(feeds)} RSS feed(s) for {domain}")
            except Exception as e:
                continue
    
    log(f"Total: Discovered RSS feeds for {len(discovered_feeds)} sites")
    return discovered_feeds


def get_all_rss_feeds():
    """
    Get all RSS feeds: hardcoded + discovered from Source sheet.
    Returns dict of name -> URL.
    """
    all_feeds = dict(RSS_FEEDS)  # Start with hardcoded feeds
    
    # Optionally discover additional feeds
    if ENABLE_RSS_DISCOVERY:
        log("RSS discovery enabled - scanning Source sheet sites...")
        discovered = discover_all_rss_feeds(max_sites=100)
        
        for domain, feeds in discovered.items():
            for i, feed in enumerate(feeds):
                feed_url = feed.get('url', '')
                if feed_url and feed_url not in all_feeds.values():
                    name = f"{domain}" if i == 0 else f"{domain} ({i+1})"
                    all_feeds[name] = feed_url
    
    return all_feeds

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
    """Check if title is primarily English"""
    if not title:
        return False
    ascii_letters = sum(1 for c in title if c.isascii() and c.isalpha())
    non_ascii = sum(1 for c in title if not c.isascii())
    total = ascii_letters + non_ascii
    if total == 0:
        return False
    return (ascii_letters / total) > 0.7


def is_vietnamese_title(title):
    """Check if title is primarily Vietnamese"""
    if not title:
        return False
    # Vietnamese uses Latin alphabet with diacritics
    # Check for Vietnamese-specific characters
    vietnamese_chars = set('àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ')
    has_vietnamese = any(c in vietnamese_chars for c in title)
    return has_vietnamese


def passes_language_filter(title):
    """Check if title passes the configured language filter"""
    if LANGUAGE_FILTER == 'all':
        return True
    elif LANGUAGE_FILTER == 'vietnamese':
        return is_vietnamese_title(title) or not is_english_title(title)
    else:  # 'english' (default)
        return is_english_title(title)


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
    collected_articles = []  # 수집된 기사 목록
    collection_stats = {}    # RSS 소스별 통계
    
    # Get all RSS feeds (hardcoded + discovered)
    all_feeds = get_all_rss_feeds()
    log(f"Total RSS feeds to check: {len(all_feeds)}")
    
    for source_name, feed_url in all_feeds.items():
        print("")
        print("=" * 50)
        log(f"Source: {source_name}")
        log(f"URL: {feed_url}")
        
        # Initialize stats for this source
        collection_stats[source_name] = {
            'url': feed_url,
            'status': 'Unknown',
            'last_check': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'entries_found': 0,
            'collected': 0,
            'error': ''
        }
        
        feed = fetch_rss(feed_url)
        
        if feed.bozo and not feed.entries:
            log("Feed error or empty")
            collection_stats[source_name]['status'] = 'Failed'
            collection_stats[source_name]['error'] = 'Feed error or empty response'
            continue
        
        entries = feed.entries
        log(f"Found {len(entries)} entries")
        total_entries += len(entries)
        
        collection_stats[source_name]['entries_found'] = len(entries)
        collection_stats[source_name]['status'] = 'Success'
        
        source_collected = 0
        
        for entry in entries:
            title = getattr(entry, 'title', '')
            if not title:
                continue
            
            title = clean_html(title)
            link = getattr(entry, 'link', '')
            summary = clean_html(getattr(entry, 'summary', getattr(entry, 'description', '')))
            published = getattr(entry, 'published', getattr(entry, 'pubDate', ''))
            
            if not passes_language_filter(title):
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
                collected_articles.append(article)  # 리스트에 추가
                log(f"  SAVED [{sector}] [{province}]: {title[:50]}...")
        
        # Update stats for this source
        collection_stats[source_name]['collected'] = source_collected
        log(f"Collected from {source_name}: {source_collected}")
    
    conn.close()
    
    print("")
    print("=" * 60)
    print("COLLECTION SUMMARY")
    print("=" * 60)
    print(f"Total RSS entries: {total_entries}")
    print(f"Total collected: {total_collected}")
    print("=" * 60)
    
    return total_collected, collected_articles, collection_stats


# ============================================================
# EXCEL UPDATE FUNCTION
# ============================================================

def update_excel_database(articles, collection_stats=None):
    """Add new articles to the Excel database and update reporting sheets"""
    try:
        import openpyxl
        from openpyxl.utils import get_column_letter
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        import shutil
    except ImportError:
        log("openpyxl not installed - skipping Excel update")
        return False
    
    EXCEL_PATH = Path("data/database/Vietnam_Infra_News_Database_Final.xlsx")
    
    if not EXCEL_PATH.exists():
        log(f"Excel file not found: {EXCEL_PATH}")
        return False
    
    log(f"Updating Excel database...")
    
    # ============================================================
    # SAFETY CHECK: Verify existing data before modification
    # ============================================================
    try:
        wb_check = openpyxl.load_workbook(EXCEL_PATH, read_only=True)
        ws_check = wb_check.active
        existing_count = sum(1 for row in ws_check.iter_rows(min_row=2, values_only=True) if any(row))
        wb_check.close()
        log(f"✓ Safety check: {existing_count} existing articles found")
        
        if existing_count < 100:
            log(f"⚠️ WARNING: Only {existing_count} articles found. Expected 2000+")
            log(f"⚠️ Skipping update to prevent data loss")
            return False
    except Exception as e:
        log(f"Safety check failed: {e}")
        return False
    
    # ============================================================
    # CREATE BACKUP before modification
    # ============================================================
    backup_path = EXCEL_PATH.with_suffix('.xlsx.backup')
    try:
        shutil.copy2(EXCEL_PATH, backup_path)
        log(f"✓ Backup created: {backup_path}")
    except Exception as e:
        log(f"Backup failed: {e}")
    
    try:
        # Load workbook
        wb = openpyxl.load_workbook(EXCEL_PATH)
        
        # ============================================================
        # 1. Update main articles sheet
        # ============================================================
        ws = wb.active
        last_row = ws.max_row
        
        # Get existing URLs to avoid duplicates
        existing_urls = set()
        url_col = None
        
        for col in range(1, ws.max_column + 1):
            header = ws.cell(row=1, column=col).value
            if header and "link" in str(header).lower():
                url_col = col
                break
        
        if url_col:
            for row in range(2, last_row + 1):
                url = ws.cell(row=row, column=url_col).value
                if url:
                    existing_urls.add(url)
        
        col_map = {
            'area': 1,
            'sector': 2,
            'province': 3,
            'title': 4,
            'date': 5,
            'source': 6,
            'url': 7,
            'summary': 8
        }
        
        added_count = 0
        for article in articles:
            if article.get('url') in existing_urls:
                continue
            
            new_row = last_row + 1 + added_count
            
            ws.cell(row=new_row, column=col_map['area'], value=article.get('area', 'Environment'))
            ws.cell(row=new_row, column=col_map['sector'], value=article.get('sector', ''))
            ws.cell(row=new_row, column=col_map['province'], value=article.get('province', 'Vietnam'))
            ws.cell(row=new_row, column=col_map['title'], value=article.get('title', ''))
            
            date_str = article.get('published_date', '')
            if date_str:
                date_str = date_str[:10]
            ws.cell(row=new_row, column=col_map['date'], value=date_str)
            
            ws.cell(row=new_row, column=col_map['source'], value=article.get('source', ''))
            ws.cell(row=new_row, column=col_map['url'], value=article.get('url', ''))
            ws.cell(row=new_row, column=col_map['summary'], value=article.get('summary', '')[:500])
            
            added_count += 1
            existing_urls.add(article.get('url'))
        
        log(f"✓ Added {added_count} new articles to main sheet")
        
        # ============================================================
        # 2. Update/Create RSS_Sources sheet
        # ============================================================
        if "RSS_Sources" in wb.sheetnames:
            ws_rss = wb["RSS_Sources"]
            wb.remove(ws_rss)
        
        ws_rss = wb.create_sheet("RSS_Sources")
        
        # Headers
        rss_headers = ["Source Name", "URL", "Status", "Last Check", "Entries Found", "Articles Collected", "Error Message"]
        header_fill = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF")
        
        for col, header in enumerate(rss_headers, 1):
            cell = ws_rss.cell(row=1, column=col, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")
        
        # Data from collection_stats
        if collection_stats:
            for row, (source, stats) in enumerate(collection_stats.items(), 2):
                ws_rss.cell(row=row, column=1, value=source)
                ws_rss.cell(row=row, column=2, value=stats.get('url', ''))
                ws_rss.cell(row=row, column=3, value=stats.get('status', 'Unknown'))
                ws_rss.cell(row=row, column=4, value=stats.get('last_check', ''))
                ws_rss.cell(row=row, column=5, value=stats.get('entries_found', 0))
                ws_rss.cell(row=row, column=6, value=stats.get('collected', 0))
                ws_rss.cell(row=row, column=7, value=stats.get('error', ''))
                
                # Color coding
                status = stats.get('status', '')
                if status == 'Success':
                    ws_rss.cell(row=row, column=3).fill = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")
                elif status == 'Failed':
                    ws_rss.cell(row=row, column=3).fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
        
        # Adjust column widths
        ws_rss.column_dimensions['A'].width = 25
        ws_rss.column_dimensions['B'].width = 45
        ws_rss.column_dimensions['C'].width = 12
        ws_rss.column_dimensions['D'].width = 20
        ws_rss.column_dimensions['E'].width = 15
        ws_rss.column_dimensions['F'].width = 18
        ws_rss.column_dimensions['G'].width = 40
        
        log("✓ Updated RSS_Sources sheet")
        
        # ============================================================
        # 3. Update/Create Keywords sheet
        # ============================================================
        if "Keywords" in wb.sheetnames:
            ws_kw = wb["Keywords"]
            wb.remove(ws_kw)
        
        ws_kw = wb.create_sheet("Keywords")
        
        # Headers
        kw_headers = ["Business Sector", "Area", "Keywords"]
        for col, header in enumerate(kw_headers, 1):
            cell = ws_kw.cell(row=1, column=col, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")
        
        # Sector to Area mapping
        sector_area = {
            "Waste Water": "Environment",
            "Solid Waste": "Environment",
            "Power": "Energy",
            "Oil & Gas": "Energy",
            "Industrial Parks": "Urban Development",
            "Smart City": "Urban Development",
            "Urban Development": "Urban Development"
        }
        
        row = 2
        for sector, keywords_dict in SECTOR_KEYWORDS.items():
            keywords = keywords_dict.get("primary", [])
            ws_kw.cell(row=row, column=1, value=sector)
            ws_kw.cell(row=row, column=2, value=sector_area.get(sector, "Other"))
            ws_kw.cell(row=row, column=3, value=", ".join(keywords))
            row += 1
        
        ws_kw.column_dimensions['A'].width = 20
        ws_kw.column_dimensions['B'].width = 18
        ws_kw.column_dimensions['C'].width = 100
        
        log("✓ Updated Keywords sheet")
        
        # ============================================================
        # 4. Update/Create Collection_Log sheet
        # ============================================================
        if "Collection_Log" not in wb.sheetnames:
            ws_log = wb.create_sheet("Collection_Log")
            log_headers = ["Date", "Time", "Hours Back", "RSS Entries", "Articles Collected", "New Added", "Total DB"]
            for col, header in enumerate(log_headers, 1):
                cell = ws_log.cell(row=1, column=col, value=header)
                cell.fill = header_fill
                cell.font = header_font
        else:
            ws_log = wb["Collection_Log"]
        
        # Add new log entry
        log_row = ws_log.max_row + 1
        now = datetime.now()
        
        total_entries = sum(s.get('entries_found', 0) for s in collection_stats.values()) if collection_stats else 0
        total_collected = sum(s.get('collected', 0) for s in collection_stats.values()) if collection_stats else len(articles)
        
        ws_log.cell(row=log_row, column=1, value=now.strftime("%Y-%m-%d"))
        ws_log.cell(row=log_row, column=2, value=now.strftime("%H:%M:%S"))
        ws_log.cell(row=log_row, column=3, value=HOURS_BACK)
        ws_log.cell(row=log_row, column=4, value=total_entries)
        ws_log.cell(row=log_row, column=5, value=total_collected)
        ws_log.cell(row=log_row, column=6, value=added_count)
        ws_log.cell(row=log_row, column=7, value=last_row - 1 + added_count)
        
        ws_log.column_dimensions['A'].width = 12
        ws_log.column_dimensions['B'].width = 10
        ws_log.column_dimensions['C'].width = 12
        ws_log.column_dimensions['D'].width = 12
        ws_log.column_dimensions['E'].width = 18
        ws_log.column_dimensions['F'].width = 12
        ws_log.column_dimensions['G'].width = 12
        
        log("✓ Updated Collection_Log sheet")
        
        # ============================================================
        # 5. Update/Create Keywords_History sheet
        # ============================================================
        if "Keywords_History" in wb.sheetnames:
            ws_hist = wb["Keywords_History"]
            wb.remove(ws_hist)
        
        ws_hist = wb.create_sheet("Keywords_History")
        
        # Headers
        hist_headers = ["Area", "Business Sector", "Province", "Date", "Title", "Source", "Link"]
        for col, header in enumerate(hist_headers, 1):
            cell = ws_hist.cell(row=1, column=col, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")
        
        # Load ALL articles from main sheet for history
        # Use 'ws' which is the main data sheet (not wb.active which might point to another sheet)
        all_articles = []
        ws_main = ws  # Use the same worksheet reference from step 1
        
        # Re-calculate max_row to include newly added articles
        current_max_row = last_row + added_count
        
        for row_idx in range(2, current_max_row + 1):
            area = ws_main.cell(row=row_idx, column=1).value or ""
            sector = ws_main.cell(row=row_idx, column=2).value or ""
            province = ws_main.cell(row=row_idx, column=3).value or "Vietnam"
            title = ws_main.cell(row=row_idx, column=4).value or ""
            date = ws_main.cell(row=row_idx, column=5).value or ""
            source = ws_main.cell(row=row_idx, column=6).value or ""
            link = ws_main.cell(row=row_idx, column=7).value or ""
            
            if title:  # Skip empty rows
                # Convert date to string if needed
                if hasattr(date, 'strftime'):
                    date = date.strftime("%Y-%m-%d")
                else:
                    date = str(date)[:10] if date else ""
                
                all_articles.append({
                    'area': area,
                    'sector': sector,
                    'province': province,
                    'title': title,
                    'date': date,
                    'source': source,
                    'link': link
                })
        
        # Define sort order for Areas
        area_order = {"Environment": 1, "Energy": 2, "Urban Development": 3}
        
        # Define sort order for Sectors within each Area
        sector_order = {
            # Environment
            "Waste Water": 1, "Solid Waste": 2, "Water Supply/Drainage": 3,
            # Energy
            "Power": 4, "Oil & Gas": 5,
            # Urban Development
            "Industrial Parks": 6, "Smart City": 7, "Urban Development": 8, "Transport": 9
        }
        
        # Secondary sort: within same grouping, newest date first
        from itertools import groupby
        
        # Sort articles:
        # 1. Area (Environment → Energy → Urban Development)
        # 2. Sector
        # 3. Province (specific provinces first, "Vietnam" last)
        # 4. Date (newest first - 2026 → 2025 → ... → 2019)
        
        sorted_articles = []
        
        # First, group by area, sector, province
        all_articles.sort(key=lambda x: (
            area_order.get(x.get('area', ''), 99),
            sector_order.get(x.get('sector', ''), 99),
            1 if x.get('province') == "Vietnam" else 0,
            x.get('province', '')
        ))
        
        for key, group in groupby(all_articles, key=lambda x: (
            x.get('area', ''),
            x.get('sector', ''),
            x.get('province', '')
        )):
            group_list = list(group)
            # Sort by date DESCENDING (newest first: 2026 → 2025 → ... → 2019)
            group_list.sort(key=lambda x: x.get('date', '') or "0000-00-00", reverse=True)
            sorted_articles.extend(group_list)
        
        log(f"  - Total articles for history: {len(sorted_articles)}")
        log(f"  - Date range: {min(a.get('date', '9999') for a in sorted_articles if a.get('date'))} ~ {max(a.get('date', '0000') for a in sorted_articles if a.get('date'))}")
        
        # Write to sheet
        current_area = None
        current_sector = None
        current_province = None
        row_idx = 2
        
        # Color fills for areas
        area_fills = {
            "Environment": PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid"),  # Green
            "Energy": PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid"),       # Yellow
            "Urban Development": PatternFill(start_color="E0E7FF", end_color="E0E7FF", fill_type="solid")  # Purple
        }
        
        # Year highlight for recent articles (2026)
        year_2026_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")  # Light red
        
        for article in sorted_articles:
            area = article.get('area', '')
            sector = article.get('sector', '')
            province = article.get('province', '')
            date = article.get('date', '')
            
            # Add separator row when Area or Sector changes
            if area != current_area or sector != current_sector:
                if current_area is not None:  # Not first row
                    row_idx += 1  # Empty row as separator
                
                current_area = area
                current_sector = sector
                current_province = None
            
            # Write article data
            ws_hist.cell(row=row_idx, column=1, value=area)
            ws_hist.cell(row=row_idx, column=2, value=sector)
            ws_hist.cell(row=row_idx, column=3, value=province)
            ws_hist.cell(row=row_idx, column=4, value=date)
            ws_hist.cell(row=row_idx, column=5, value=article.get('title', ''))
            ws_hist.cell(row=row_idx, column=6, value=article.get('source', ''))
            ws_hist.cell(row=row_idx, column=7, value=article.get('link', ''))
            
            # Apply area color
            area_fill = area_fills.get(area)
            if area_fill:
                ws_hist.cell(row=row_idx, column=1).fill = area_fill
                ws_hist.cell(row=row_idx, column=2).fill = area_fill
            
            # Highlight 2026 articles (newest)
            if date and date.startswith('2026'):
                ws_hist.cell(row=row_idx, column=4).fill = year_2026_fill
                ws_hist.cell(row=row_idx, column=4).font = Font(bold=True)
            
            row_idx += 1
        
        # Adjust column widths
        ws_hist.column_dimensions['A'].width = 18
        ws_hist.column_dimensions['B'].width = 20
        ws_hist.column_dimensions['C'].width = 20
        ws_hist.column_dimensions['D'].width = 12
        ws_hist.column_dimensions['E'].width = 60
        ws_hist.column_dimensions['F'].width = 20
        ws_hist.column_dimensions['G'].width = 50
        
        # Freeze header row
        ws_hist.freeze_panes = 'A2'
        
        # Count articles by year
        year_counts = {}
        for article in sorted_articles:
            year = article.get('date', '')[:4] if article.get('date') else 'Unknown'
            year_counts[year] = year_counts.get(year, 0) + 1
        
        log(f"✓ Updated Keywords_History sheet ({len(sorted_articles)} articles)")
        log(f"  - Articles by year: {dict(sorted(year_counts.items(), reverse=True))}")
        
        # ============================================================
        # 6. Update/Create Summary sheet (at the END, not beginning)
        # ============================================================
        if "Summary" in wb.sheetnames:
            ws_sum = wb["Summary"]
            wb.remove(ws_sum)
        
        ws_sum = wb.create_sheet("Summary")  # Create at end (no index = append)
        
        # Title
        ws_sum.merge_cells('A1:D1')
        title_cell = ws_sum.cell(row=1, column=1, value="Vietnam Infrastructure News Database - Summary Report")
        title_cell.font = Font(bold=True, size=14, color="0F766E")
        title_cell.alignment = Alignment(horizontal="center")
        
        # Last updated
        ws_sum.cell(row=2, column=1, value=f"Last Updated: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Statistics
        ws_sum.cell(row=4, column=1, value="📊 Database Statistics")
        ws_sum.cell(row=4, column=1).font = Font(bold=True, size=12)
        
        total_articles = last_row - 1 + added_count
        ws_sum.cell(row=5, column=1, value="Total Articles:")
        ws_sum.cell(row=5, column=2, value=total_articles)
        
        ws_sum.cell(row=6, column=1, value="New This Session:")
        ws_sum.cell(row=6, column=2, value=added_count)
        
        # RSS Sources summary
        ws_sum.cell(row=8, column=1, value="📡 RSS Sources")
        ws_sum.cell(row=8, column=1).font = Font(bold=True, size=12)
        
        if collection_stats:
            success_count = sum(1 for s in collection_stats.values() if s.get('status') == 'Success')
            failed_count = sum(1 for s in collection_stats.values() if s.get('status') == 'Failed')
            
            ws_sum.cell(row=9, column=1, value="Active Sources:")
            ws_sum.cell(row=9, column=2, value=success_count)
            ws_sum.cell(row=10, column=1, value="Failed Sources:")
            ws_sum.cell(row=10, column=2, value=failed_count)
        
        # Sector summary
        ws_sum.cell(row=12, column=1, value="🏭 Sectors Monitored")
        ws_sum.cell(row=12, column=1).font = Font(bold=True, size=12)
        
        row = 13
        for sector in SECTOR_KEYWORDS.keys():
            ws_sum.cell(row=row, column=1, value=f"  • {sector}")
            row += 1
        
        ws_sum.column_dimensions['A'].width = 25
        ws_sum.column_dimensions['B'].width = 15
        
        log("✓ Updated Summary sheet")
        
        # Save workbook
        wb.save(EXCEL_PATH)
        wb.close()
        
        log(f"✓ Excel database saved: {total_articles} total articles")
        return True
        
    except Exception as e:
        log(f"Error updating Excel: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Vietnam Infrastructure News Collector')
    parser.add_argument('--hours-back', type=int, default=HOURS_BACK, 
                        help='Hours to look back for news')
    args = parser.parse_args()
    
    # Update global HOURS_BACK for Excel logging
    HOURS_BACK = args.hours_back
    
    print("=" * 60)
    print("VIETNAM INFRASTRUCTURE NEWS COLLECTOR")
    print("=" * 60)
    print("")
    
    # Collect news
    collected_count, collected_articles, collection_stats = collect_news(args.hours_back)
    
    # Update Excel database with stats
    print("")
    print("=" * 60)
    print("UPDATING EXCEL DATABASE")
    print("=" * 60)
    
    update_excel_database(collected_articles, collection_stats)
    
    # Print RSS source summary
    print("")
    print("=" * 60)
    print("RSS SOURCE STATUS")
    print("=" * 60)
    for source, stats in collection_stats.items():
        status_icon = "✓" if stats['status'] == 'Success' else "✗"
        print(f"  {status_icon} {source}: {stats['entries_found']} entries, {stats['collected']} collected")
        if stats['error']:
            print(f"      Error: {stats['error']}")
    
    print("")
    print("=" * 50)
    print(f"TOTAL COLLECTED: {collected_count}")
    print("")
    print(f"Total: {collected_count} articles collected")
