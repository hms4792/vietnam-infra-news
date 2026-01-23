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
<details>
<summary>👉 클릭하여 코드 보기 (길어서 접음)</summary>
```python
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
```
</details>

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

SUMMARY_PROMPT_TEMPLATE = """Analyze this Vietnam infrastructure news article and provide a structured summary.

Title: {title}
Content: {content}
Source: {source}
Date: {date}

Please respond in JSON format with:
{{
    "title_ko": "Korean translation of the title",
    "title_en": "English translation/original of the title", 
    "title_vi": "Vietnamese translation of the title",
    "summary_ko": "2-3 sentence summary in Korean",
    "summary_en": "2-3 sentence summary in English",
    "summary_vi": "2-3 sentence summary in Vietnamese",
    "area": "Environment or Energy Develop. or Urban Develop.",
    "sector": "Waste Water or Solid Waste or Water Supply/Drainage or Power or Oil & Gas or Industrial Parks or Smart City",
    "entities": ["list of key organizations, companies, government bodies mentioned"],
    "project_value": "investment amount if mentioned, otherwise empty string"
}}

Important classification rules:
- If article mentions oil, gas, petroleum, refinery, LNG terminal -> sector: "Oil & Gas", area: "Energy Develop."
- If article mentions wastewater, sewage, water treatment -> sector: "Waste Water", area: "Environment"
- If article mentions solid waste, landfill, recycling -> sector: "Solid Waste", area: "Environment"
- If article mentions power plant, solar, wind, electricity -> sector: "Power", area: "Energy Develop."
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

# URL 블랙리스트 패턴
URL_BLACKLIST_PATTERNS = [
    # 카테고리/태그 페이지
    r'/category/', r'/tag/', r'/tags/', r'/categories/',
    r'/cooperation-investment$', r'/investment$', r'/business$',
    
    # 정적 페이지
    r'/about', r'/contact', r'/policy', r'/law', r'/regulation',
    r'/investment-policy', r'/investment-incentive',
    r'/investment-climate', r'/doing-business',
    r'/investment-attraction',
    
    # 기타
    r'/search', r'/archive', r'/page/', r'/expertise/',
]

# 뉴스 기사 패턴
URL_NEWS_PATTERNS = [
    r'/\d{4}/\d{1,2}/',  # /2025/01/
    r'/news/', r'/article/', r'/post/', r'/story/',
    r'/tin-tuc/', r'/bai-viet/',
    r'-post\d+\.html?$',  # -post112164.html
    r'-\d{7,}\.html?$',   # article-1234567.html
    r'/\d{6,}\.html?$',   # /123456.html
    r'\.vnp$',            # .vnp
]
