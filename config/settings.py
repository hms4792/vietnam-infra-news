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

# API Keys (from environment variables)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECIPIENTS = os.getenv("EMAIL_RECIPIENTS", "").split(",")

# News Sources (RSS Feeds)
RSS_FEEDS = {
    "VietnamPlus": "https://en.vietnamplus.vn/rss/news.rss",
    "VnExpress": "https://e.vnexpress.net/rss/news.rss",
    "Vietnam News": "https://vietnamnews.vn/rss/home.rss",
    "Tuoi Tre News": "https://tuoitrenews.vn/rss/home.rss",
}

# Sector Keywords (Improved)
SECTOR_KEYWORDS = {
    "Waste Water": {
        "primary": [
            "wastewater treatment plant", "sewage treatment plant",
            "wwtp", "wastewater treatment system", "sewerage system",
            "wastewater collection", "effluent treatment"
        ],
        "secondary": ["wastewater", "sewage", "effluent"]
    },
    "Water Supply": {
        "primary": [
            "water supply project", "water supply system",
            "clean water plant", "water treatment plant",
            "drinking water", "water supply infrastructure"
        ],
        "secondary": ["water supply", "clean water", "potable water"]
    },
    "Solid Waste": {
        "primary": [
            "waste-to-energy plant", "solid waste treatment",
            "landfill", "incineration plant", "recycling facility",
            "waste management"
        ],
        "secondary": ["solid waste", "waste treatment", "recycling"]
    },
    "Power": {
        "primary": [
            "power plant", "solar farm", "wind farm",
            "lng power", "thermal power", "hydropower plant"
        ],
        "secondary": ["electricity", "power generation"]
    },
    "Oil & Gas": {
        "primary": [
            "oil exploration", "gas field", "lng terminal",
            "refinery", "offshore drilling", "petroleum"
        ],
        "secondary": ["oil", "gas", "petroleum"]
    },
    "Industrial Parks": {
        "primary": [
            "industrial park", "industrial zone", "economic zone",
            "export processing zone"
        ],
        "secondary": ["fdi", "factory"]
    },
    "Smart City": {
        "primary": [
            "smart city project", "urban development",
            "digital transformation"
        ],
        "secondary": ["urban area"]
    },
    "Transport": {
        "primary": [
            "railway project", "metro construction", "airport",
            "highway", "expressway", "port development"
        ],
        "secondary": ["transport"]
    },
    "Construction": {
        "primary": [
            "construction project", "real estate", "housing project"
        ],
        "secondary": ["construction", "building"]
    }
}

# URL Blacklist Patterns
URL_BLACKLIST_PATTERNS = [
    # Category/Tag pages
    r'/category/', r'/tag/', r'/tags/', r'/categories/',
    r'/cooperation-investment$', r'/investment$', r'/business$',
    
    # Static pages
    r'/about', r'/contact', r'/policy', r'/law', r'/regulation',
    r'/investment-policy', r'/investment-incentive',
    r'/investment-climate', r'/doing-business',
    r'/investment-attraction',
    
    # Other
    r'/search', r'/archive', r'/page/', r'/expertise/',
]

# News Article Patterns
URL_NEWS_PATTERNS = [
    r'/\d{4}/\d{1,2}/',  # /2025/01/
    r'/news/', r'/article/', r'/post/', r'/story/',
    r'/tin-tuc/', r'/bai-viet/',
    r'-post\d+\.html?$',  # -post112164.html
    r'-\d{7,}\.html?$',   # article-1234567.html
    r'/\d{6,}\.html?$',   # /123456.html
    r'\.vnp$',            # .vnp
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

# Logging
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
