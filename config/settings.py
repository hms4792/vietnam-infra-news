"""
Vietnam Infrastructure News Pipeline - Configuration Settings
"""
import os
from datetime import datetime
from pathlib import Path

# ============================================
# PATH CONFIGURATION
# ============================================
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "outputs"
TEMPLATE_DIR = BASE_DIR / "templates"

# ============================================
# API KEYS (from environment variables)
# ============================================
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
EMAIL_SMTP_SERVER = os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_RECIPIENTS = os.getenv("EMAIL_RECIPIENTS", "").split(",")

# Kakao Talk
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "")
KAKAO_REFRESH_TOKEN = os.getenv("KAKAO_REFRESH_TOKEN", "")
KAKAO_REDIRECT_URI = os.getenv("KAKAO_REDIRECT_URI", "http://localhost:8080/callback")

# ============================================
# NEWS SOURCES CONFIGURATION
# ============================================
NEWS_SOURCES = {
    "VnExpress": {
        "base_url": "https://vnexpress.net",
        "search_url": "https://timkiem.vnexpress.net/?q=",
        "rss_feeds": [
            "https://vnexpress.net/rss/kinh-doanh.rss",
            "https://vnexpress.net/rss/bat-dong-san.rss",
        ],
        "keywords": ["infrastructure", "wastewater", "solar", "wind power", "industrial park"]
    },
    "VietnamNews": {
        "base_url": "https://vietnamnews.vn",
        "search_url": "https://vietnamnews.vn/search?q=",
        "rss_feeds": [
            "https://vietnamnews.vn/rss/economy.rss",
            "https://vietnamnews.vn/rss/environment.rss",
        ],
        "keywords": ["infrastructure", "energy", "environment", "construction"]
    },
    "VnEconomy": {
        "base_url": "https://vneconomy.vn",
        "search_url": "https://vneconomy.vn/tim-kiem?q=",
        "rss_feeds": [],
        "keywords": ["ha tang", "nang luong", "moi truong"]
    },
    "TuoiTre": {
        "base_url": "https://tuoitre.vn",
        "search_url": "https://tuoitre.vn/tim-kiem.htm?keywords=",
        "rss_feeds": [
            "https://tuoitre.vn/rss/kinh-doanh.rss",
        ],
        "keywords": ["infrastructure", "energy", "industrial"]
    },
}

# ============================================
# SECTOR CLASSIFICATION
# ============================================
SECTOR_KEYWORDS = {
    "Environment": {
        "Waste Water": ["wastewater", "sewage", "water treatment", "nước thải", "xử lý nước"],
        "Solid Waste": ["solid waste", "landfill", "waste-to-energy", "rác thải", "chất thải rắn"],
        "Water Supply/Drainage": ["water supply", "drainage", "cấp nước", "thoát nước", "reservoir"]
    },
    "Energy Develop.": {
        "Power": ["solar", "wind", "power plant", "điện mặt trời", "điện gió", "nhà máy điện", "renewable"],
        "Oil & Gas": ["LNG", "gas pipeline", "oil", "petroleum", "dầu khí", "khí đốt"]
    },
    "Urban Develop.": {
        "Smart City": ["smart city", "digital", "IoT", "thành phố thông minh", "đô thị số"],
        "Industrial Parks": ["industrial park", "FDI", "khu công nghiệp", "đầu tư", "manufacturing"]
    }
}

# ============================================
# PROVINCES LIST
# ============================================
PROVINCES = [
    "Hanoi", "Ho Chi Minh City", "Da Nang", "Hai Phong", "Can Tho",
    "Binh Duong", "Dong Nai", "Hai Duong", "Binh Dinh", "Ba Ria-Vung Tau",
    "Quang Ninh", "Nghe An", "Long An", "Ninh Thuan", "Bac Ninh",
    "Thai Nguyen", "Thanh Hoa", "Khanh Hoa", "Lam Dong", "Tay Ninh",
    "Quang Nam", "Binh Thuan", "Phu Yen", "Vinh Phuc", "Bac Giang"
]

PROVINCE_ALIASES = {
    "HCM": "Ho Chi Minh City",
    "HCMC": "Ho Chi Minh City",
    "Saigon": "Ho Chi Minh City",
    "TP HCM": "Ho Chi Minh City",
    "Ha Noi": "Hanoi",
    "Da Nang": "Da Nang",
    "Danang": "Da Nang",
}

# ============================================
# AI SUMMARIZATION SETTINGS
# ============================================
AI_MODEL = "claude-sonnet-4-20250514"
AI_MAX_TOKENS = 1024
AI_TEMPERATURE = 0.3

SUMMARY_PROMPT_TEMPLATE = """
You are an expert analyst for Vietnam infrastructure news. 
Analyze the following news article and provide:
1. A concise summary in Korean (2-3 sentences)
2. A concise summary in English (2-3 sentences)
3. A concise summary in Vietnamese (2-3 sentences)
4. Key entities mentioned (companies, government bodies)
5. Estimated project value if mentioned
6. Classification: Area (Environment/Energy Develop./Urban Develop.) and Sector

Article Title: {title}
Article Content: {content}
Source: {source}
Date: {date}

Respond in JSON format:
{{
    "summary_ko": "...",
    "summary_en": "...",
    "summary_vi": "...",
    "entities": ["..."],
    "project_value": "...",
    "area": "...",
    "sector": "..."
}}
"""

# ============================================
# NOTIFICATION SETTINGS
# ============================================
NOTIFICATION_SCHEDULE = "08:00"  # Daily at 8 AM
NOTIFICATION_TIMEZONE = "Asia/Ho_Chi_Minh"

NOTIFICATION_TEMPLATE = {
    "ko": """
🇻🇳 베트남 인프라 뉴스 일일 브리핑
📅 {date}

📊 오늘의 요약:
• 총 수집 기사: {total_articles}건
• 환경 인프라: {env_count}건
• 에너지 개발: {energy_count}건
• 도시 개발: {urban_count}건

🔥 주요 뉴스:
{top_news}

🔗 대시보드: {dashboard_url}
""",
    "en": """
🇻🇳 Vietnam Infrastructure News Daily Briefing
📅 {date}

📊 Today's Summary:
• Total Articles: {total_articles}
• Environment: {env_count}
• Energy: {energy_count}
• Urban Development: {urban_count}

🔥 Top News:
{top_news}

🔗 Dashboard: {dashboard_url}
"""
}

# ============================================
# OUTPUT SETTINGS
# ============================================
OUTPUT_FORMATS = ["json", "csv", "xlsx", "html"]
DASHBOARD_FILENAME = "vietnam_dashboard.html"
DATABASE_FILENAME = "vietnam_infra_news_database.xlsx"

# ============================================
# SCHEDULING
# ============================================
COLLECTION_TIMES = ["06:00", "12:00", "18:00"]  # 3 times daily
REPORT_TIME = "08:00"  # Daily report time

# ============================================
# LOGGING
# ============================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_FILE = BASE_DIR / "logs" / "pipeline.log"
