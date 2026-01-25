# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News Pipeline - Settings
Configuration for news collection, AI processing, and notifications
Updated with all news sources from database analysis
"""

import os
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
LOG_DIR = PROJECT_ROOT / "logs"
TEMPLATE_DIR = PROJECT_ROOT / "templates"

# Database
DATABASE_PATH = DATA_DIR / "vietnam_infrastructure_news.db"
EXCEL_DB_PATH = DATA_DIR / "database" / "Vietnam_Infra_News_Database_Final.xlsx"

# API Keys (from environment variables)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECIPIENTS = os.getenv("EMAIL_RECIPIENTS", "").split(",")

# Telegram (optional)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Slack (optional)
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# Kakao (optional)
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY")
KAKAO_REFRESH_TOKEN = os.getenv("KAKAO_REFRESH_TOKEN")

# Email SMTP Settings
EMAIL_SMTP_SERVER = "smtp.gmail.com"
EMAIL_SMTP_PORT = 587

# ============================================================
# NEWS SOURCES - Based on Database Analysis (232 domains, 2000+ articles)
# ============================================================

# Primary RSS Feeds (English sources - highest priority)
RSS_FEEDS = {
    # === TIER 1: Major English News Sources (Most articles in DB) ===
    "Vietnam News": "https://vietnamnews.vn/rss/home.rss",
    "VnExpress English": "https://e.vnexpress.net/rss/news.rss",
    "VietnamPlus English": "https://en.vietnamplus.vn/rss/news.rss",
    "Tuoi Tre News": "https://tuoitrenews.vn/rss/home.rss",
    
    # === TIER 2: Investment & Business Focus ===
    "The Investor": "https://theinvestor.vn/rss/home.rss",
    "Vietnam Investment Review": "https://vir.com.vn/rss/home.rss",
    "Hanoi Times": "https://hanoitimes.vn/rss/home.rss",
    "The Saigon Times": "https://english.thesaigontimes.vn/rss/home.rss",
    
    # === TIER 3: Regional & Specialized ===
    "VietnamNet English": "https://vietnamnet.vn/en/rss/home.rss",
    "Saigon GP News": "https://en.sggp.org.vn/rss/home.rss",
    
    # === TIER 4: Energy & Environment Focus ===
    "Vietnam Energy": "https://vietnamenergy.vn/rss/home.rss",
}

# Alternative/Backup RSS URLs (if primary fails)
RSS_FEEDS_BACKUP = {
    "Vietnam News Alt": "https://vietnamnews.vn/rss/economy.rss",
    "VnExpress Business": "https://e.vnexpress.net/rss/business.rss",
    "VietnamPlus Business": "https://en.vietnamplus.vn/rss/business.rss",
}

# Direct scraping sources (no RSS, need HTML scraping)
SCRAPE_SOURCES = {
    "Da Nang News": {
        "base_url": "https://baodanang.vn",
        "news_path": "/english/",
        "articles_in_db": 104
    },
    "Bao Dau Tu": {
        "base_url": "https://baodautu.vn", 
        "news_path": "/",
        "articles_in_db": 42
    },
    "VEN Cong Thuong": {
        "base_url": "https://ven.congthuong.vn",
        "news_path": "/",
        "articles_in_db": 31
    },
    "Bao Tai Nguyen Moi Truong": {
        "base_url": "https://baotainguyenmoitruong.vn",
        "news_path": "/",
        "articles_in_db": 26
    },
    "Dong Nai News": {
        "base_url": "https://baodongnai.com.vn",
        "news_path": "/",
        "articles_in_db": 29
    },
    "Binh Duong News": {
        "base_url": "https://baobinhduong.vn",
        "news_path": "/",
        "articles_in_db": 21
    },
}

# ============================================================
# SOURCE STATUS LOG (for reference)
# ============================================================
# This documents the status of each source for troubleshooting

NEWS_SOURCES_STATUS = """
=== NEWS SOURCES STATUS LOG ===
Last Updated: 2026-01-24

TIER 1 - Primary English Sources (RSS Available):
✓ vietnamnews.vn (291 articles) - RSS: /rss/home.rss
✓ e.vnexpress.net (142 articles) - RSS: /rss/news.rss
✓ en.vietnamplus.vn (132 articles) - RSS: /rss/news.rss
✓ tuoitrenews.vn (59 articles) - RSS: /rss/home.rss

TIER 2 - Investment Focus (RSS May Vary):
○ theinvestor.vn (171 articles) - RSS: /rss/home.rss (check availability)
○ vir.com.vn (95 articles) - RSS: /rss/home.rss (check availability)
○ hanoitimes.vn (62 articles) - RSS: /rss/home.rss (check availability)
○ english.thesaigontimes.vn (26 articles) - RSS: /rss/home.rss (check availability)

TIER 3 - Regional Sources (May need scraping):
○ baodanang.vn (104 articles) - No RSS confirmed, scrape needed
○ vietnamenergy.vn (69 articles) - Check RSS availability
○ vietnamnet.vn (50 articles) - RSS: /en/rss/home.rss
○ en.sggp.org.vn (48 articles) - Check RSS availability

TIER 4 - Vietnamese Language Sources:
○ baodautu.vn (42 articles) - Vietnamese, scrape needed
○ ven.congthuong.vn (31 articles) - Vietnamese, scrape needed
○ baotainguyenmoitruong.vn (26 articles) - Vietnamese, scrape needed

GOVERNMENT/OFFICIAL:
○ www9.monre.gov.vn (38 articles) - Ministry site, manual check
○ moitruongvadothi.vn (37 articles) - Environment & Urban

INTERNATIONAL:
○ offshore-energy.biz (19 articles) - International energy news

=== TOTAL FROM DATABASE ===
- 232 unique domains
- 2000+ total articles
- Top 15 sources account for ~70% of articles
"""

# ============================================================
# SECTOR KEYWORDS
# ============================================================

SECTOR_KEYWORDS = {
    "Waste Water": {
        "primary": [
            "wastewater treatment plant", "sewage treatment plant",
            "wwtp", "wastewater treatment system", "sewerage system",
            "wastewater collection", "effluent treatment",
            "xử lý nước thải", "nhà máy xử lý nước thải"
        ],
        "secondary": ["wastewater", "sewage", "effluent", "nước thải"]
    },
    "Water Supply/Drainage": {
        "primary": [
            "water supply project", "water supply system",
            "clean water plant", "water treatment plant",
            "drinking water", "water supply infrastructure",
            "cấp nước", "nhà máy nước sạch"
        ],
        "secondary": ["water supply", "clean water", "potable water", "nước sạch"]
    },
    "Solid Waste": {
        "primary": [
            "waste-to-energy plant", "solid waste treatment",
            "landfill", "incineration plant", "recycling facility",
            "waste management", "rác thải", "chất thải rắn"
        ],
        "secondary": ["solid waste", "waste treatment", "recycling", "garbage"]
    },
    "Power": {
        "primary": [
            "power plant", "solar farm", "wind farm",
            "lng power", "thermal power", "hydropower plant",
            "nhà máy điện", "điện mặt trời", "điện gió"
        ],
        "secondary": ["electricity", "power generation", "điện"]
    },
    "Oil & Gas": {
        "primary": [
            "oil exploration", "gas field", "lng terminal",
            "refinery", "offshore drilling", "petroleum",
            "dầu khí", "nhà máy lọc dầu"
        ],
        "secondary": ["oil", "gas", "petroleum", "lng"]
    },
    "Industrial Parks": {
        "primary": [
            "industrial park", "industrial zone", "economic zone",
            "export processing zone", "khu công nghiệp"
        ],
        "secondary": ["fdi", "factory", "manufacturing"]
    },
    "Smart City": {
        "primary": [
            "smart city project", "urban development",
            "digital transformation", "thành phố thông minh"
        ],
        "secondary": ["urban area", "city development"]
    },
    "Transport": {
        "primary": [
            "railway project", "metro construction", "airport",
            "highway", "expressway", "port development",
            "đường sắt", "sân bay", "cảng biển"
        ],
        "secondary": ["transport", "logistics"]
    },
    "Construction": {
        "primary": [
            "construction project", "real estate", "housing project",
            "xây dựng", "bất động sản"
        ],
        "secondary": ["construction", "building"]
    }
}

# URL Blacklist Patterns (skip these URLs)
URL_BLACKLIST_PATTERNS = [
    r'/category/', r'/tag/', r'/tags/', r'/categories/',
    r'/cooperation-investment$', r'/investment$', r'/business$',
    r'/about', r'/contact', r'/policy', r'/law', r'/regulation',
    r'/investment-policy', r'/investment-incentive',
    r'/investment-climate', r'/doing-business',
    r'/search', r'/archive', r'/page/', r'/expertise/',
    r'/rss', r'/feed', r'/sitemap',
]

# News Article URL Patterns (valid article URLs)
URL_NEWS_PATTERNS = [
    r'/\d{4}/\d{1,2}/',      # /2025/01/
    r'/news/', r'/article/', r'/post/', r'/story/',
    r'/tin-tuc/', r'/bai-viet/',
    r'-post\d+\.html?$',      # -post112164.html
    r'-\d{7,}\.html?$',       # article-1234567.html
    r'/\d{6,}\.html?$',       # /123456.html
    r'\.vnp$',                # .vnp
    r'-d\d+\.html$',          # -d12345.html
]

# AI Prompts
SUMMARIZATION_PROMPT_TEMPLATE = """
Summarize this Vietnamese infrastructure news article in {language}.

Article Title: {title}
Sector: {sector}
Content: {content}

Provide a concise 2-3 sentence summary focusing on:
- Project name and location
- Key stakeholders and investment amount
- Project status and timeline

Summary in {language}:
"""

TRANSLATION_PROMPT_TEMPLATE = """
Translate this Vietnamese news headline to English.
Keep it concise and professional.
Return ONLY the English translation, nothing else.

Vietnamese: {title}

English:
"""

# Email Settings
EMAIL_SUBJECT = "Vietnam Infrastructure News - Daily Report"
EMAIL_FROM_NAME = "Vietnam Infra News Bot"

# Dashboard Settings
DASHBOARD_TITLE = "Vietnam Infrastructure News Database"
DASHBOARD_SUBTITLE = "Real-time Infrastructure Project Tracking"

# Collection Settings
COLLECTION_HOURS_BACK = 48  # Collect articles from last 48 hours
MAX_ARTICLES_PER_SOURCE = 30  # Max articles to fetch per RSS source
REQUEST_DELAY = 2  # Seconds between requests

# Logging
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
