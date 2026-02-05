#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News Pipeline - Settings
"""

import os
from pathlib import Path

# === PATHS ===
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "outputs"
TEMPLATE_DIR = BASE_DIR / "templates"

# === API KEYS ===
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# === EMAIL ===
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_RECIPIENTS = os.getenv("EMAIL_RECIPIENTS", "")
EMAIL_SUBJECT = "🇻🇳 Vietnam Infrastructure News Daily"
EMAIL_FROM_NAME = "Vietnam Infra News"
EMAIL_SMTP_SERVER = "smtp.gmail.com"
EMAIL_SMTP_PORT = 587

# === TELEGRAM ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# === SLACK ===
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")

# === KAKAO ===
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "")
KAKAO_REFRESH_TOKEN = os.getenv("KAKAO_REFRESH_TOKEN", "")

# === DASHBOARD ===
DASHBOARD_URL = "https://hms4792.github.io/vietnam-infra-news/"

# === RSS FEEDS ===
# 일반 뉴스 (영어)
RSS_FEEDS = {
    # 주요 영어 뉴스
    "VnExpress English": "https://e.vnexpress.net/rss/news.rss",
    "VnExpress Business": "https://e.vnexpress.net/rss/business.rss",
    "VietnamPlus": "https://en.vietnamplus.vn/rss/news.rss",
    "VietnamPlus Business": "https://en.vietnamplus.vn/rss/business.rss",
    "Vietnam News": "https://vietnamnews.vn/rss/home.rss",
    "Tuoi Tre News": "https://tuoitrenews.vn/rss/news.rss",
    "The Investor": "https://theinvestor.vn/rss/news.rss",
    "Vietnam Investment Review": "https://vir.com.vn/rss/news.rss",
    "Hanoi Times": "https://hanoitimes.vn/rss/news.rss",
    "VietnamNet": "https://vietnamnet.vn/en/rss/home.rss",
    "Saigon GP Daily": "https://en.sggp.org.vn/rss/news.rss",
    
    # 베트남어 뉴스 (인프라 관련)
    "VnExpress Kinh Doanh": "https://vnexpress.net/rss/kinh-doanh.rss",
    "VnExpress Thoi Su": "https://vnexpress.net/rss/thoi-su.rss",
    "Tuoi Tre": "https://tuoitre.vn/rss/tin-moi-nhat.rss",
    "Dau Tu Online": "https://baodautu.vn/rss/home.rss",
    "Nhan Dan": "https://nhandan.vn/rss/kinhte.rss",
}

# === SECTOR CLASSIFICATION ===
SECTOR_KEYWORDS = {
    "Waste Water": {
        "keywords": [
            # English
            "wastewater", "waste water", "sewage", "sewerage", "effluent",
            "wastewater treatment", "sewage treatment", "wwtp", "stp",
            "drainage system", "stormwater", "water pollution",
            # Vietnamese
            "nước thải", "xử lý nước thải", "thoát nước", "ô nhiễm nước"
        ],
        "area": "Environment",
        "priority": 1
    },
    "Solid Waste": {
        "keywords": [
            # English
            "solid waste", "waste management", "garbage", "landfill", "incinerat",
            "waste-to-energy", "wte", "recycling", "composting",
            "hazardous waste", "medical waste", "e-waste", "plastic waste",
            "waste collection", "garbage collection", "municipal waste",
            # Vietnamese
            "rác thải", "chất thải rắn", "bãi rác", "đốt rác", "xử lý rác",
            "tái chế", "chất thải nguy hại"
        ],
        "area": "Environment",
        "priority": 2
    },
    "Water Supply/Drainage": {
        "keywords": [
            # English
            "water supply", "water treatment", "drinking water", "potable water",
            "water plant", "reservoir", "water distribution", "water pipeline",
            "desalination", "water network", "clean water", "tap water",
            "water infrastructure", "water project",
            # Vietnamese
            "cấp nước", "nhà máy nước", "nước sạch", "hồ chứa", "đường ống nước"
        ],
        "area": "Environment",
        "priority": 3
    },
    "Power": {
        "keywords": [
            # English
            "power plant", "electricity", "solar power", "solar energy", "solar farm",
            "wind power", "wind farm", "wind energy", "offshore wind",
            "hydropower", "hydro power", "thermal power", "coal power",
            "renewable energy", "photovoltaic", "pv project",
            "power grid", "transmission line", "substation", "megawatt",
            "energy storage", "battery storage", "lng power", "gas turbine",
            "energy project", "power project", "electricity generation",
            # Vietnamese
            "nhà máy điện", "điện mặt trời", "điện gió", "thủy điện",
            "năng lượng tái tạo", "lưới điện", "trạm biến áp"
        ],
        "area": "Energy Develop.",
        "priority": 4
    },
    "Oil & Gas": {
        "keywords": [
            # English
            "oil and gas", "oil & gas", "petroleum", "lng terminal", "lng project",
            "refinery", "petrochemical", "offshore drilling", "gas pipeline",
            "natural gas", "crude oil", "oil exploration", "gas field",
            "oil project", "gas project",
            # Vietnamese
            "dầu khí", "khí đốt", "lọc dầu", "nhà máy lọc dầu",
            "petrovietnam", "pvn", "binh son", "nghi son"
        ],
        "area": "Energy Develop.",
        "priority": 5
    },
    "Industrial Parks": {
        "keywords": [
            # English
            "industrial park", "industrial zone", "economic zone", "export processing zone",
            "manufacturing zone", "industrial estate", "industrial complex",
            "industrial cluster", "factory construction", "industrial land",
            "fdi investment", "fdi project", "foreign investment",
            # Vietnamese
            "khu công nghiệp", "kcn", "khu chế xuất", "khu kinh tế",
            "cụm công nghiệp", "nhà máy"
        ],
        "area": "Urban Develop.",
        "priority": 6
    },
    "Smart City": {
        "keywords": [
            # English
            "smart city", "urban development", "city planning", "smart infrastructure",
            "urban infrastructure", "metro line", "subway", "urban rail",
            "infrastructure project", "public transport", "transport infrastructure",
            # Vietnamese
            "đô thị thông minh", "quy hoạch đô thị", "phát triển đô thị",
            "metro", "tàu điện ngầm"
        ],
        "area": "Urban Develop.",
        "priority": 7
    }
}

# === EXCLUSION KEYWORDS ===
EXCLUSION_KEYWORDS = [
    # Sports
    "football", "soccer", "basketball", "tennis", "golf tournament",
    "u23", "u-23", "sea games", "olympic", "world cup", "championship",
    "coach", "player", "match score", "victory", "defeat", "league",
    "bóng đá", "đội tuyển", "huấn luyện viên", "cầu thủ", "trận đấu",
    
    # Entertainment
    "celebrity", "singer", "actor", "actress", "movie", "film festival",
    "concert", "album", "k-pop", "drama", "tv show", "entertainment",
    
    # Natural disasters (not infrastructure)
    "earthquake death", "landslide death", "flood death", "tsunami",
    "typhoon death", "hurricane death", "tornado", "volcanic eruption",
    "death toll", "missing persons", "rescue operation", "disaster relief",
    
    # Weather (non-infrastructure)
    "weather forecast", "temperature today", "rain expected",
    "ice storm", "hurricane warning", "typhoon warning", "cold front",
    
    # Stock/Finance (not infrastructure)
    "stock market", "stock price", "share price", "trading volume",
    "stock exchange", "market cap", "investor sentiment",
    
    # General news
    "tourist arrivals", "tourism revenue",
    "covid", "pandemic", "vaccine", "infection rate",
    "election", "vote", "political party", "parliament",
    "murder", "arrest", "crime", "prison", "court ruling",
    "recipe", "cooking", "restaurant review", "food festival"
]

# === AI PROMPTS ===
SUMMARIZATION_PROMPT_TEMPLATE = """Summarize this Vietnam infrastructure news in {language}:

Title: {title}
Sector: {sector}
Content: {content}

Write a 2-3 sentence summary focusing on the infrastructure project details."""

TRANSLATION_PROMPT_TEMPLATE = """Translate to {language}. Return ONLY the translation:

{text}"""
