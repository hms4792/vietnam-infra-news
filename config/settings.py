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
RSS_FEEDS = {
    "Vietnam News": "https://vietnamnews.vn/rss/home.rss",
    "VnExpress English": "https://e.vnexpress.net/rss/news.rss",
    "VietnamPlus": "https://en.vietnamplus.vn/rss/news.rss",
    "Tuoi Tre News": "https://tuoitrenews.vn/rss/news.rss",
    "The Investor": "https://theinvestor.vn/rss/news.rss",
    "Vietnam Investment Review": "https://vir.com.vn/rss/news.rss",
    "Hanoi Times": "https://hanoitimes.vn/rss/news.rss",
    "Saigon Times": "https://english.thesaigontimes.vn/rss/news.rss",
    "VietnamNet": "https://vietnamnet.vn/en/rss/home.rss",
    "Saigon GP Daily": "https://en.sggp.org.vn/rss/news.rss",
    "Vietnam Energy": "https://nangluongvietnam.vn/rss/news.rss",
}

# === SECTOR CLASSIFICATION ===
SECTOR_KEYWORDS = {
    "Waste Water": {
        "keywords": [
            "wastewater", "waste water", "sewage", "sewerage", "effluent",
            "wastewater treatment", "sewage treatment", "wwtp", "stp",
            "nước thải", "xử lý nước thải", "drainage", "stormwater", "thoát nước"
        ],
        "area": "Environment",
        "priority": 1
    },
    "Solid Waste": {
        "keywords": [
            "solid waste", "waste management", "garbage", "landfill", "incinerat",
            "waste-to-energy", "wte", "recycling plant", "composting",
            "rác thải", "chất thải rắn", "bãi rác", "đốt rác", "xử lý rác",
            "hazardous waste", "medical waste", "e-waste"
        ],
        "area": "Environment",
        "priority": 2
    },
    "Water Supply/Drainage": {
        "keywords": [
            "water supply", "water treatment", "drinking water", "potable water",
            "water plant", "reservoir", "pipeline", "water distribution",
            "cấp nước", "nhà máy nước", "nước sạch", "hồ chứa",
            "desalination", "water network"
        ],
        "area": "Environment",
        "priority": 3
    },
    "Power": {
        "keywords": [
            "power plant", "electricity", "solar", "wind farm", "hydropower",
            "thermal power", "renewable energy", "photovoltaic", "pv",
            "nhà máy điện", "điện mặt trời", "điện gió", "thủy điện",
            "grid", "transmission line", "substation", "megawatt", "mw",
            "energy storage", "battery storage", "lng power"
        ],
        "area": "Energy Develop.",
        "priority": 4
    },
    "Oil & Gas": {
        "keywords": [
            "oil", "gas", "petroleum", "lng", "refinery", "petrochemical",
            "offshore", "drilling", "terminal",
            "dầu khí", "khí đốt", "lọc dầu", "nhà máy lọc dầu",
            "petrovietnam", "pvn", "binh son refining"
        ],
        "area": "Energy Develop.",
        "priority": 5
    },
    "Industrial Parks": {
        "keywords": [
            "industrial park", "industrial zone", "economic zone", "export processing",
            "manufacturing zone", "factory", "industrial estate",
            "khu công nghiệp", "kcn", "khu chế xuất", "khu kinh tế"
        ],
        "area": "Urban Develop.",
        "priority": 6
    },
    "Smart City": {
        "keywords": [
            "smart city", "urban development", "city planning", "smart infrastructure",
            "đô thị thông minh", "quy hoạch đô thị", "phát triển đô thị"
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
    "coach", "player", "match", "score", "goal", "victory", "defeat",
    "bóng đá", "đội tuyển", "huấn luyện viên", "cầu thủ", "trận đấu",
    
    # Entertainment
    "celebrity", "singer", "actor", "actress", "movie", "film festival",
    "concert", "album", "k-pop", "drama", "tv show",
    
    # Weather (non-infrastructure)
    "weather forecast", "temperature today", "rain expected",
    "ice storm", "hurricane", "typhoon warning",
    
    # General news
    "stock market", "stock price", "tourist arrivals",
    "covid", "pandemic", "vaccine",
    "election", "vote", "political party",
    "murder", "arrest", "crime", "prison",
    "recipe", "cooking", "restaurant review"
]

# === AI PROMPTS ===
SUMMARIZATION_PROMPT_TEMPLATE = """Summarize this Vietnam infrastructure news in {language}:

Title: {title}
Sector: {sector}
Content: {content}

Write a 2-3 sentence summary focusing on the infrastructure project details."""

TRANSLATION_PROMPT_TEMPLATE = """Translate to {language}. Return ONLY the translation:

{text}"""
