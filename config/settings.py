# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News Pipeline - Settings
Configuration for news collection, AI processing, and notifications
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

RSS_FEEDS = {
    # === TIER 1: Major English News Sources ===
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
    
    # === TIER 4: Energy Focus ===
    "Vietnam Energy": "https://vietnamenergy.vn/rss/home.rss",
}

# ============================================================
# SECTOR KEYWORDS - STRICT INFRASTRUCTURE ONLY
# ============================================================
# Each sector has:
# - required: At least one must match (prevents irrelevant articles)
# - boost: Additional keywords that increase confidence
# - exclude: Keywords that disqualify the article

SECTOR_KEYWORDS = {
    "Waste Water": {
        "required": [
            "wastewater treatment", "sewage treatment", "wwtp",
            "wastewater plant", "sewage plant", "sewerage",
            "xử lý nước thải", "nhà máy xử lý nước thải",
            "nước thải sinh hoạt", "nước thải công nghiệp"
        ],
        "boost": [
            "effluent", "drainage system", "sludge", "biological treatment",
            "thoát nước", "bùn thải"
        ],
        "exclude": [],
        "area": "Environment"
    },
    "Solid Waste": {
        "required": [
            "waste-to-energy", "solid waste treatment", "landfill",
            "waste management plant", "incineration plant", "recycling facility",
            "garbage treatment", "municipal waste", "hazardous waste treatment",
            "xử lý rác thải", "đốt rác", "bãi rác", "chất thải rắn",
            "nhà máy xử lý chất thải"
        ],
        "boost": [
            "recycling", "composting", "waste collection",
            "tái chế", "phân loại rác"
        ],
        "exclude": [],
        "area": "Environment"
    },
    "Water Supply/Drainage": {
        "required": [
            "water supply plant", "water treatment plant", "clean water project",
            "drinking water", "water supply system", "water infrastructure",
            "nhà máy nước", "cấp nước sạch", "hệ thống cấp nước",
            "nước sinh hoạt", "nhà máy nước sạch"
        ],
        "boost": [
            "potable water", "water distribution", "reservoir",
            "hồ chứa nước"
        ],
        "exclude": [],
        "area": "Environment"
    },
    "Power": {
        "required": [
            "power plant", "solar farm", "wind farm", "solar power project",
            "wind power project", "thermal power plant", "hydropower plant",
            "lng power plant", "gas turbine", "power generation",
            "nhà máy điện", "điện mặt trời", "điện gió", "thủy điện",
            "nhiệt điện", "năng lượng tái tạo"
        ],
        "boost": [
            "megawatt", "MW", "electricity generation", "grid connection",
            "công suất"
        ],
        "exclude": ["power outage", "power cut", "blackout"],
        "area": "Energy Develop."
    },
    "Oil & Gas": {
        "required": [
            "oil exploration", "gas field development", "lng terminal",
            "oil refinery", "petroleum project", "offshore drilling",
            "gas pipeline", "petrochemical plant",
            "dầu khí", "mỏ dầu", "mỏ khí", "nhà máy lọc dầu",
            "khai thác dầu"
        ],
        "boost": [
            "crude oil", "natural gas", "petroleum",
            "đường ống dẫn khí"
        ],
        "exclude": ["gas price", "oil price", "fuel price"],
        "area": "Energy Develop."
    },
    "Industrial Parks": {
        "required": [
            "industrial park development", "industrial zone construction",
            "economic zone project", "export processing zone",
            "industrial park infrastructure", "industrial estate",
            "khu công nghiệp", "khu chế xuất", "khu kinh tế"
        ],
        "boost": [
            "fdi", "foreign investment", "manufacturing hub",
            "đầu tư nước ngoài"
        ],
        "exclude": [],
        "area": "Urban Develop."
    },
    "Smart City": {
        "required": [
            "smart city project", "smart city development",
            "digital city", "smart urban",
            "thành phố thông minh", "đô thị thông minh"
        ],
        "boost": [
            "iot infrastructure", "digital transformation",
            "urban technology"
        ],
        "exclude": [],
        "area": "Urban Develop."
    },
    "Transport": {
        "required": [
            "railway construction", "metro project", "airport construction",
            "highway construction", "expressway project", "port development",
            "bridge construction", "tunnel project",
            "xây dựng đường sắt", "dự án metro", "xây dựng sân bay",
            "đường cao tốc", "cảng biển"
        ],
        "boost": [
            "logistics hub", "transport infrastructure",
            "giao thông"
        ],
        "exclude": ["traffic accident", "traffic jam", "flight delay"],
        "area": "Urban Develop."
    }
}

# ============================================================
# ARTICLE EXCLUSION KEYWORDS
# Skip articles containing these (case-insensitive)
# ============================================================

EXCLUSION_KEYWORDS = [
    # Sports
    "football", "soccer", "basketball", "volleyball", "tennis",
    "olympic", "sea games", "world cup", "championship", "tournament",
    "match result", "score", "goal", "player", "coach", "team won",
    "u23", "u21", "u19", "national team", "đội tuyển",
    "bóng đá", "cầu thủ", "huấn luyện viên",
    
    # Entertainment
    "celebrity", "movie", "film", "actress", "actor", "singer",
    "concert", "festival", "entertainment", "showbiz",
    "ca sĩ", "diễn viên", "phim",
    
    # Weather/Disasters (unless infrastructure related)
    "weather forecast", "typhoon warning", "storm warning",
    "earthquake", "flood warning", "hurricane",
    "dự báo thời tiết", "bão",
    
    # Crime/Politics
    "murder", "robbery", "arrest", "corruption scandal",
    "election result", "political party",
    
    # General news
    "covid", "pandemic", "vaccine", "quarantine",
    "stock market", "exchange rate", "inflation rate",
    "tourist arrival", "hotel booking",
    
    # Irrelevant
    "recipe", "cooking", "fashion", "beauty",
    "dating", "marriage", "divorce"
]

# ============================================================
# URL PATTERNS
# ============================================================

URL_BLACKLIST_PATTERNS = [
    r'/category/', r'/tag/', r'/tags/', r'/categories/',
    r'/about', r'/contact', r'/policy',
    r'/search', r'/archive', r'/page/',
    r'/rss', r'/feed', r'/sitemap',
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
COLLECTION_HOURS_BACK = 48
MAX_ARTICLES_PER_SOURCE = 30
REQUEST_DELAY = 2

# Logging
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
