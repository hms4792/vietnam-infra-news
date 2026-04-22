# -*- coding: utf-8 -*-
"""
news_collector.py
베트남 인프라 뉴스 수집기 — RSS + NewsData.io + GNews

변경사항 (이번 수정):
  ① RSS_FEEDS에서 영구 폐쇄 소스 6개 완전 제거:
     - theinvestor.vn/feed      (404 폐쇄)
     - vir.com.vn/rss/news.aspx (410 Gone)
     - constructionvietnam.net  (폐쇄)
     - monre.gov.vn/rss         (봇 차단)
     - ictvietnam.vn/feed       (봇 차단)
     - moitruong.com.vn/feed    (봇 차단)
  ② 위 사이트들은 specialist_crawler.py (Jina.ai fallback 포함)가 담당

영구 제약:
  - 번역: Google Translate (MyMemory → deep-translator fallback)
  - Anthropic API: GitHub Actions 연결 오류 → 절대 금지
  - date fallback: article.get('date') or article.get('published_date')
  - NewsData.io: /api/1/latest, country=vn, language=en/vi, q 파라미터만
    (domain, from_date, category+domain → 422 오류, 절대 금지)
  - 전문미디어 크롤링: specialist_crawler.py 위임 (weekly_backfill.yml)
"""

import os
import re
import sys
import time
import sqlite3
import hashlib
import logging
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ── 경로 ─────────────────────────────────────────────────
ROOT_DIR   = Path(__file__).parent.parent
DB_PATH    = str(ROOT_DIR / 'data' / 'vietnam_infra_news.db')
EXCEL_PATH = str(ROOT_DIR / 'data' / 'database' / 'Vietnam_Infra_News_Database_Final.xlsx')

# ── 로깅 ─────────────────────────────────────────────────
logging.basicConfig(
    level   = logging.INFO,
    format  = '%(asctime)s - %(message)s',
    datefmt = '%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger(__name__)

def log(msg): logger.info(msg)

# ── 수집 설정 ────────────────────────────────────────────
HOURS_BACK             = int(os.environ.get('HOURS_BACK', 24))
LANGUAGE_FILTER        = True
MIN_CLASSIFY_THRESHOLD = 1
GNEWS_API_KEY          = os.environ.get('GNEWS_API_KEY', '')
ENABLE_GNEWS           = bool(GNEWS_API_KEY)

# ── 섹터 분류 키워드 ──────────────────────────────────────
SECTOR_KEYWORDS = {
    'Waste Water': [
        'wastewater', 'sewage', 'wwtp', 'nước thải', 'thoát nước',
        'wastewater treatment', 'effluent', 'water treatment plant',
        'hệ thống thoát nước', 'xử lý nước thải',
    ],
    'Water Supply/Drainage': [
        'water supply', 'clean water', 'drinking water', 'cấp nước',
        'nước sạch', 'drainage', 'water pipe', 'water network',
        'đường ống nước', 'hệ thống cấp nước',
    ],
    'Solid Waste': [
        'solid waste', 'waste management', 'rác thải', 'chất thải',
        'landfill', 'recycling', 'waste-to-energy', 'tái chế',
        'xử lý chất thải', 'bãi rác', 'đốt rác',
    ],
    'Power': [
        'electricity', 'power plant', 'renewable energy', 'solar',
        'wind power', 'pdp8', 'evn', 'nuclear power', 'power grid',
        'điện', 'năng lượng tái tạo', 'điện gió', 'điện mặt trời',
        'quy hoạch điện', 'lưới điện', 'nhà máy điện',
    ],
    'Oil & Gas': [
        'lng', 'petroleum', 'petrovietnam', 'oil', 'gas pipeline',
        'offshore', 'dầu khí', 'khí thiên nhiên', 'đường ống khí',
        'pvn', 'pv gas', 'lng terminal',
    ],
    'Industrial Parks': [
        'industrial park', 'industrial zone', 'khu công nghiệp',
        'vsip', 'fdi', 'eco-industrial', 'khu kinh tế',
        'khu chế xuất', 'factory', 'manufacturing',
    ],
    'Smart City': [
        'smart city', 'metro', 'digital infrastructure', 'iot',
        'thành phố thông minh', 'chuyển đổi số', 'e-government',
        'đường sắt đô thị', 'tuyến metro', 'digital',
    ],
    'Transport': [
        'expressway', 'highway', 'airport', 'port', 'railway',
        'cao tốc', 'cảng biển', 'sân bay', 'giao thông',
        'north-south', 'metro line', 'long thanh',
    ],
    'Environment': [
        'environment', 'emission', 'carbon', 'esg', 'sustainability',
        'môi trường', 'khí thải', 'phát thải', 'ô nhiễm',
        'mekong', 'ecosystem', 'climate',
    ],
}

# 섹터 우선순위 (Environment > Energy > Urban)
SECTOR_PRIORITY = [
    'Waste Water', 'Water Supply/Drainage', 'Solid Waste', 'Environment',
    'Power', 'Oil & Gas',
    'Industrial Parks', 'Smart City', 'Transport',
]

# ── Province 키워드 ────────────────────────────────────
PROVINCE_KEYWORDS = {
    'Hanoi'              : ['hanoi', 'ha noi', 'hà nội'],
    'Ho Chi Minh City'   : ['ho chi minh', 'hcmc', 'saigon', 'sài gòn', 'tp.hcm'],
    'Da Nang'            : ['da nang', 'đà nẵng', 'danang'],
    'Hai Phong'          : ['hai phong', 'hải phòng'],
    'Can Tho'            : ['can tho', 'cần thơ'],
    'Binh Duong'         : ['binh duong', 'bình dương'],
    'Dong Nai'           : ['dong nai', 'đồng nai'],
    'Ba Ria-Vung Tau'    : ['vung tau', 'vũng tàu', 'ba ria', 'bà rịa'],
    'Quang Ninh'         : ['quang ninh', 'quảng ninh', 'ha long', 'hạ long'],
    'Long An'            : ['long an'],
    'Nghe An'            : ['nghe an', 'nghệ an'],
    'Khanh Hoa'          : ['khanh hoa', 'khánh hòa', 'nha trang'],
    'Quang Nam'          : ['quang nam', 'quảng nam'],
    'Binh Dinh'          : ['binh dinh', 'bình định'],
    'Thua Thien Hue'     : ['hue', 'huế', 'thua thien'],
    'Lam Dong'           : ['lam dong', 'lâm đồng', 'da lat', 'đà lạt'],
    'Bac Ninh'           : ['bac ninh', 'bắc ninh'],
    'Hung Yen'           : ['hung yen', 'hưng yên'],
    'National Level'     : ['vietnam', 'viet nam', 'việt nam', 'national', 'toàn quốc'],
}

# ════════════════════════════════════════════════════════
# RSS 피드 목록 (검증된 정상 소스만, 2026-04-07 기준)
#
# ❌ 영구 폐쇄 — 아래 소스 절대 재추가 금지:
#   theinvestor.vn/feed     → 404
#   vir.com.vn/rss          → 410 Gone
#   constructionvietnam.net → 폐쇄
#   monre.gov.vn/rss        → 봇 차단
#   ictvietnam.vn/feed      → 봇 차단
#   moitruong.com.vn/feed   → 봇 차단
#   vea.gov.vn              → 봇 차단
#   mic.gov.vn/rss          → 봇 차단
#   smartcity.mobi          → 폐쇄
#   baotintuc.vn            → 봇 차단
#   hanoimoi.vn             → 봇 차단
# ════════════════════════════════════════════════════════
RSS_FEEDS = {
    # ── 검증 완료 (2026-04-07) ───────────────────────────
    'Hanoi Times'        : 'https://hanoitimes.vn/rss/home.rss',
    'PV Tech'            : 'https://pv-tech.org/feed/',
    'Energy Monitor'     : 'https://energymonitor.ai/rss',
    'Nikkei Asia'        : 'https://asia.nikkei.com/rss/feed/nar',
    'Moitruong Net'      : 'https://moitruong.net.vn/rss/home.rss',
    'Vietnamnet Tech'    : 'https://vietnamnet.vn/rss/cong-nghe.rss',

    # ── 추가 베트남 미디어 ────────────────────────────────
    'VietnamPlus'        : 'https://www.vietnamplus.vn/rss/kinhte-311.rss',
    'Bao Xay Dung'       : 'https://baoxaydung.com.vn/rss/home.rss',
    'Tuoi Tre'           : 'https://tuoitre.vn/rss/tin-moi-nhat.rss',
    'VnExpress Kinh Doanh': 'https://vnexpress.net/rss/kinh-doanh.rss',
    'Dantri Kinh Te'     : 'https://dantri.com.vn/rss/kinh-doanh.rss',
    'Thanh Nien Kinh Te' : 'https://thanhnien.vn/rss/kinh-te.rss',
    'SGGP English'       : 'https://en.sggp.org.vn/rss/home.rss',
    'Bao Tai Nguyen'     : 'https://baotainguyenmoitruong.vn/rss/tin-tuc.rss',

    # ── 환경/에너지 전문 ─────────────────────────────────
    'Offshore Energy'    : 'https://offshore-energy.biz/feed/',
    'Solar Quarter'      : 'https://solarquarter.com/feed/',
    'Vietnam Energy'     : 'https://vietnamenergy.vn/rss/home.rss',
    'Nhan Dan English'   : 'https://en.nhandan.vn/rss/home.rss',
}

# ── NewsData.io 설정 ────────────────────────────────────
# 중요: /api/1/latest 엔드포인트만
# 허용 파라미터: country=vn + language=en/vi + q
# 금지: domain, from_date, category+domain → 422 오류
NEWSDATA_ENDPOINT = 'https://newsdata.io/api/1/latest'

NEWSDATA_QUERIES = [
    # 환경 인프라
    {'q': 'Vietnam wastewater treatment infrastructure',  'language': 'en'},
    {'q': 'Vietnam water supply drainage',                'language': 'en'},
    {'q': 'Vietnam solid waste recycling',                'language': 'en'},
    # 에너지
    {'q': 'Vietnam renewable energy solar wind power PDP8', 'language': 'en'},
    {'q': 'Vietnam LNG gas pipeline petroleum',           'language': 'en'},
    {'q': 'Vietnam EVN electricity grid nuclear',         'language': 'en'},
    # 도시/산업
    {'q': 'Vietnam industrial park FDI investment',       'language': 'en'},
    {'q': 'Vietnam smart city metro digital infrastructure', 'language': 'en'},
    {'q': 'Vietnam expressway airport port transport',    'language': 'en'},
    # 베트남어
    {'q': 'nước thải xử lý môi trường hạ tầng',           'language': 'vi'},
    {'q': 'năng lượng tái tạo điện mặt trời gió PDP8',    'language': 'vi'},
    {'q': 'khu công nghiệp đầu tư FDI',                   'language': 'vi'},
]

# 전문미디어 NewsData 보완 쿼리 (domain 파라미터 없이 q에 포함)
NEWSDATA_SPECIALIST_QUERIES = [
    {'source': 'The Investor',             'domain': 'theinvestor.vn',
     'q': 'infrastructure OR "industrial park" OR wastewater OR "power plant" OR "oil gas"',
     'language': 'en'},
    {'source': 'Vietnam Investment Review','domain': 'vir.com.vn',
     'q': 'investment OR energy OR infrastructure OR industrial OR environment',
     'language': 'en'},
    {'source': 'Nhan Dan',                 'domain': 'en.nhandan.vn',
     'q': 'Vietnam infrastructure energy environment investment',
     'language': 'en'},
]

# GNews 쿼리 (GNEWS_API_KEY 있을 때)
GNEWS_QUERY       = 'Vietnam infrastructure energy environment'
GNEWS_ENV_QUERY   = 'Vietnam wastewater water supply solid waste'
GNEWS_NORTH_QUERY = 'Vietnam industrial park smart city transport'


# ════════════════════════════════════════════════════════
# 유틸리티
# ════════════════════════════════════════════════════════
def generate_url_hash(url: str) -> str:
    return hashlib.md5(url.strip().encode()).hexdigest()


def clean_html(text: str) -> str:
    if not text:
        return ''
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def is_english_text(text: str) -> bool:
    if not text:
        return False
    ascii_count = sum(1 for c in text if ord(c) < 128)
    return ascii_count / max(len(text), 1) > 0.8


def is_vietnamese_text(text: str) -> bool:
    vi_chars = 'àáảãạăắặằẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ'
    return any(c in vi_chars for c in text.lower())


def passes_language_filter(text: str) -> bool:
    """영문 또는 베트남어 기사만 통과"""
    if not LANGUAGE_FILTER:
        return True
    return is_english_text(text) or is_vietnamese_text(text)


def is_vietnam_related(text: str) -> bool:
    """베트남 관련 기사 여부"""
    vn_kws = ['vietnam', 'viet nam', 'việt nam', 'hanoi', 'ho chi minh',
              'hcmc', 'mekong', 'evn', 'petrovietnam', 'vnm', 'vn']
    text_lower = text.lower()
    return any(kw in text_lower for kw in vn_kws)


def should_exclude(title: str, summary: str = '') -> bool:
    """제외 패턴"""
    exclude_patterns = [
        r'^\[pdf\]', r'^\[video\]', r'^\[infographic\]',
        r'week in review', r'daily briefing',
        r'advertisement', r'sponsored',
    ]
    text = (title + ' ' + summary).lower()
    return any(re.search(p, text) for p in exclude_patterns)


def extract_province(text: str) -> str:
    """본문에서 Province 추출"""
    text_lower = text.lower()
    for prov, kws in PROVINCE_KEYWORDS.items():
        if any(kw in text_lower for kw in kws):
            return prov
    return 'National Level'


def classify_sector(title: str, summary: str = '') -> str:
    """
    섹터 분류 — 우선순위 기반
    환경 인프라 > 에너지 > 도시개발
    """
    text = (title + ' ' + summary).lower()
    for sector in SECTOR_PRIORITY:
        kws = SECTOR_KEYWORDS.get(sector, [])
        if any(kw in text for kw in kws):
            return sector
    return 'Environment'


def area_fill(sector: str) -> str:
    """섹터 → Area (BACKEND_DATA 구조 준수)"""
    env_s    = {'Waste Water', 'Water Supply/Drainage', 'Solid Waste', 'Environment'}
    energy_s = {'Power', 'Oil & Gas'}
    if sector in env_s:    return 'Environment'
    if sector in energy_s: return 'Energy Develop.'
    return 'Urban Develop.'


def parse_date(date_str: str) -> Optional[datetime]:
    """다양한 날짜 형식 파싱"""
    if not date_str:
        return None
    fmts = [
        '%a, %d %b %Y %H:%M:%S %z', '%a, %d %b %Y %H:%M:%S %Z',
        '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%d %H:%M:%S', '%Y-%m-%d',
        '%d/%m/%Y', '%B %d, %Y', '%b %d, %Y',
    ]
    for fmt in fmts:
        try:
            dt = datetime.strptime(date_str.strip()[:len(fmt)+5], fmt)
            return dt.replace(tzinfo=None)
        except (ValueError, TypeError):
            continue
    return None


# ════════════════════════════════════════════════════════
# 번역 (Google Translate — MyMemory + deep-translator)
# Anthropic API 절대 금지
# ════════════════════════════════════════════════════════
def translate_text(text: str, target: str = 'ko') -> str:
    """
    번역 메인 함수
    1차: MyMemory API (무료)
    2차: deep-translator (Google Translate 백엔드)
    """
    if not text or len(text.strip()) < 3:
        return text

    # 1차: MyMemory
    try:
        params = urllib.parse.urlencode({
            'q': text[:400], 'langpair': f'en|{target}'
        })
        url = f'https://api.mymemory.translated.net/get?{params}'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as r:
            import json
            data = json.loads(r.read())
            result = data.get('responseData', {}).get('translatedText', '')
            if result and 'MYMEMORY WARNING' not in result and result != text:
                return result.strip()
    except Exception:
        pass

    time.sleep(0.5)

    # 2차: deep-translator
    try:
        from deep_translator import GoogleTranslator
        result = GoogleTranslator(source='auto', target=target).translate(text[:400])
        if result and result != text:
            return result.strip()
    except Exception:
        pass

    return text


def translate_articles(articles: list[dict]) -> list[dict]:
    """기사 목록 3개국어 번역"""
    for a in articles:
        title = a.get('title', '') or a.get('title_en', '')
        summary = a.get('summary', '') or a.get('sum_en', '')

        if not a.get('title_ko'):
            a['title_ko'] = translate_text(title, 'ko')
            time.sleep(0.3)
        if not a.get('title_vi'):
            a['title_vi'] = translate_text(title, 'vi')
            time.sleep(0.3)
        if not a.get('sum_ko') and summary:
            a['sum_ko'] = translate_text(summary[:300], 'ko')
            time.sleep(0.3)
        if not a.get('sum_vi') and summary:
            a['sum_vi'] = translate_text(summary[:300], 'vi')
            time.sleep(0.3)
    return articles


# ════════════════════════════════════════════════════════
# DB 초기화
# ════════════════════════════════════════════════════════
def init_database() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            url_hash   TEXT UNIQUE,
            title      TEXT,
            url        TEXT,
            date       TEXT,
            source     TEXT,
            src_type   TEXT DEFAULT "NewsData.io",
            sector     TEXT,
            province   TEXT,
            summary    TEXT,
            title_ko   TEXT,
            title_vi   TEXT,
            sum_ko     TEXT,
            sum_vi     TEXT,
            created_at TEXT DEFAULT (datetime("now"))
        )
    ''')
    conn.commit()
    return conn


def get_existing_hashes(conn: sqlite3.Connection) -> set:
    rows = conn.execute('SELECT url_hash FROM articles').fetchall()
    return {r[0] for r in rows}


def save_article(conn: sqlite3.Connection, article: dict) -> bool:
    url_hash = generate_url_hash(article.get('url', ''))
    try:
        conn.execute(
            '''INSERT OR IGNORE INTO articles
               (url_hash, title, url, date, source, src_type,
                sector, province, summary, title_ko, title_vi, sum_ko, sum_vi)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (url_hash,
             article.get('title_en', '') or article.get('title', ''),
             article.get('url', ''),
             article.get('date', '') or article.get('published_date', ''),
             article.get('source', ''),
             article.get('src_type', 'NewsData.io'),
             article.get('sector', ''),
             article.get('province', ''),
             article.get('sum_en', '') or article.get('summary', ''),
             article.get('title_ko', ''),
             article.get('title_vi', ''),
             article.get('sum_ko', ''),
             article.get('sum_vi', ''))
        )
        conn.commit()
        return True
    except sqlite3.Error:
        return False


# ════════════════════════════════════════════════════════
# RSS 수집
# ════════════════════════════════════════════════════════
def fetch_rss(url: str, source_name: str, cutoff: datetime,
              existing: set) -> list[dict]:
    """RSS 피드 수집"""
    articles = []

    try:
        if HAS_FEEDPARSER:
            feed = feedparser.parse(url)
            entries = feed.entries
        else:
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/rss+xml'}
            )
            with urllib.request.urlopen(req, timeout=20) as r:
                content = r.read()
            import xml.etree.ElementTree as ET
            root = ET.fromstring(content)
            entries = []  # 간단한 fallback

        for entry in entries:
            # 날짜 파싱
            pub_raw = getattr(entry, 'published', '') or getattr(entry, 'updated', '')
            pub_dt  = parse_date(pub_raw)
            if pub_dt and pub_dt < cutoff:
                continue

            title = clean_html(getattr(entry, 'title', '') or '')
            url_a = getattr(entry, 'link', '') or ''
            summ  = clean_html(
                getattr(entry, 'summary', '') or
                getattr(entry, 'description', '') or ''
            )[:500]

            if not title or len(title) < 10:
                continue
            if should_exclude(title, summ):
                continue
            if not is_vietnam_related(title + ' ' + summ):
                continue

            url_hash = generate_url_hash(url_a)
            if url_hash in existing:
                continue

            date_str = pub_dt.strftime('%Y-%m-%d') if pub_dt else datetime.now().strftime('%Y-%m-%d')
            sector   = classify_sector(title, summ)
            province = extract_province(title + ' ' + summ)

            articles.append({
                'title_en'      : title,
                'title'         : title,
                'source'        : source_name,
                'src_type'      : 'RSS',
                'date'          : date_str,
                'published_date': date_str,
                'province'      : province,
                'plan'          : '',
                'sector'        : sector,
                'area'          : area_fill(sector),
                'sum_en'        : summ,
                'summary'       : summ,
                'url'           : url_a,
                'title_ko'      : '',
                'title_vi'      : '',
                'sum_ko'        : '',
                'sum_vi'        : '',
                'grade'         : '',
            })
            existing.add(url_hash)

    except Exception as e:
        log(f"  RSS 오류 [{source_name}]: {e}")

    return articles


# ════════════════════════════════════════════════════════
# NewsData.io 수집
# ════════════════════════════════════════════════════════
def _call_newsdata(params: dict, api_key: str) -> list[dict]:
    """
    NewsData.io API 호출
    - 엔드포인트: /api/1/latest (고정)
    - 422 발생 시 category 파라미터 제거 후 재시도
    """
    params['apikey'] = api_key
    url = NEWSDATA_ENDPOINT + '?' + urllib.parse.urlencode(params)

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as r:
            import json
            return json.loads(r.read()).get('results', [])
    except urllib.error.HTTPError as e:
        if e.code == 422:
            # 422: category 파라미터 제거 후 재시도
            params.pop('category', None)
            url2 = NEWSDATA_ENDPOINT + '?' + urllib.parse.urlencode(params)
            try:
                req2 = urllib.request.Request(url2, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req2, timeout=15) as r2:
                    import json
                    return json.loads(r2.read()).get('results', [])
            except Exception:
                return []
        return []
    except Exception as e:
        log(f"  NewsData.io 오류: {e}")
        return []


def _parse_result(item: dict, source_override: str = '') -> dict:
    """NewsData.io 응답 아이템 → 기사 dict 변환"""
    title = item.get('title', '').strip()
    url_a = item.get('link', '').strip()

    # source: 빈 문자열 처리 (or 연산자 사용 — dict.get() default는 빈문자열 통과)
    raw_src = (item.get('source_id') or
               item.get('source_name') or
               source_override or
               urllib.parse.urlparse(url_a).netloc.replace('www.', ''))

    pub_raw  = item.get('pubDate', '') or item.get('publishedAt', '')
    pub_dt   = parse_date(pub_raw)
    date_str = pub_dt.strftime('%Y-%m-%d') if pub_dt else datetime.now().strftime('%Y-%m-%d')
    summ     = clean_html(item.get('description', '') or item.get('content', ''))[:500]
    sector   = classify_sector(title, summ)
    province = extract_province(title + ' ' + summ)

    return {
        'title_en'      : title,
        'title'         : title,
        'source'        : raw_src,
        'src_type'      : 'NewsData.io',
        'date'          : date_str,
        'published_date': date_str,
        'province'      : province,
        'plan'          : '',
        'sector'        : sector,
        'area'          : area_fill(sector),
        'sum_en'        : summ,
        'summary'       : summ,
        'url'           : url_a,
        'title_ko'      : '',
        'title_vi'      : '',
        'sum_ko'        : '',
        'sum_vi'        : '',
        'grade'         : '',
    }


def fetch_newsdata(api_key: str, cutoff: datetime, existing: set) -> list[dict]:
    """NewsData.io 전체 쿼리 실행"""
    if not api_key:
        return []

    articles = []
    for q_cfg in NEWSDATA_QUERIES:
        params = {
            'country' : 'vn',
            'language': q_cfg['language'],
            'q'       : q_cfg['q'],
            # domain, from_date, category+domain → 422 오류 → 절대 사용 금지
        }
        results = _call_newsdata(params, api_key)
        for item in results:
            title = item.get('title', '').strip()
            url_a = item.get('link', '').strip()
            if not title or not url_a:
                continue
            if should_exclude(title):
                continue
            if not is_vietnam_related(title):
                continue
            url_hash = generate_url_hash(url_a)
            if url_hash in existing:
                continue
            a = _parse_result(item)
            pub_dt = parse_date(item.get('pubDate', ''))
            if pub_dt and pub_dt < cutoff:
                continue
            articles.append(a)
            existing.add(url_hash)
        time.sleep(0.5)

    # 전문미디어 보완 쿼리
    for q_cfg in NEWSDATA_SPECIALIST_QUERIES:
        params = {
            'country' : 'vn',
            'language': q_cfg.get('language', 'en'),
            'q'       : q_cfg['q'],
        }
        results = _call_newsdata(params, api_key)
        for item in results:
            title = item.get('title', '').strip()
            url_a = item.get('link', '').strip()
            if not title or not url_a:
                continue
            url_hash = generate_url_hash(url_a)
            if url_hash in existing:
                continue
            a = _parse_result(item, source_override=q_cfg.get('source', ''))
            a['src_type'] = 'Specialist Crawler'  # 전문미디어 출처로 분류
            articles.append(a)
            existing.add(url_hash)
        time.sleep(0.5)

    return articles


# ════════════════════════════════════════════════════════
# GNews 수집 (API키 있을 때)
# ════════════════════════════════════════════════════════
def fetch_gnews(api_key: str, query: str, cutoff: datetime,
                existing: set) -> list[dict]:
    if not api_key:
        return []
    articles = []
    try:
        params = urllib.parse.urlencode({
            'q'      : query,
            'lang'   : 'en',
            'country': 'vn',
            'max'    : 10,
            'apikey' : api_key,
        })
        url = f'https://gnews.io/api/v4/search?{params}'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as r:
            import json
            data = json.loads(r.read())
        for item in data.get('articles', []):
            title = item.get('title', '').strip()
            url_a = item.get('url', '').strip()
            if not title or not url_a:
                continue
            url_hash = generate_url_hash(url_a)
            if url_hash in existing:
                continue
            pub_raw = item.get('publishedAt', '')
            pub_dt  = parse_date(pub_raw)
            if pub_dt and pub_dt < cutoff:
                continue
            date_str = pub_dt.strftime('%Y-%m-%d') if pub_dt else datetime.now().strftime('%Y-%m-%d')
            summ     = item.get('description', '')[:500]
            sector   = classify_sector(title, summ)
            province = extract_province(title + ' ' + summ)
            articles.append({
                'title_en'      : title,
                'title'         : title,
                'source'        : item.get('source', {}).get('name', 'GNews'),
                'src_type'      : 'GNews',
                'date'          : date_str,
                'published_date': date_str,
                'province'      : province,
                'plan'          : '',
                'sector'        : sector,
                'area'          : area_fill(sector),
                'sum_en'        : summ,
                'summary'       : summ,
                'url'           : url_a,
                'title_ko'      : '', 'title_vi': '',
                'sum_ko'        : '', 'sum_vi'  : '',
                'grade'         : '',
            })
            existing.add(url_hash)
    except Exception as e:
        log(f"  GNews 오류: {e}")
    return articles


# ════════════════════════════════════════════════════════
# 메인 수집 함수
# ════════════════════════════════════════════════════════
def collect_news(hours_back: int = None) -> list[dict]:
    """
    메인 수집 함수 (Step1에서 호출)

    수집 순서:
      1. RSS 피드 (검증된 소스만, 폐쇄 소스 제외)
      2. NewsData.io API
      3. GNews API (키 있을 때)

    전문미디어(theinvestor.vn, vir.com.vn)는
    specialist_crawler.py (weekly_backfill.yml)에서 별도 처리

    Returns:
        articles: list[dict] — date/published_date 키 보장
    """
    if hours_back is None:
        hours_back = HOURS_BACK

    cutoff = datetime.utcnow() - timedelta(hours=hours_back)
    log(f"수집 시작: 최근 {hours_back}시간 (UTC {cutoff.strftime('%Y-%m-%d %H:%M')} 이후)")

    # DB 초기화 및 기존 URL 로드
    conn     = init_database()
    existing = get_existing_hashes(conn)
    log(f"기존 URL {len(existing)}개 로드")

    all_articles = []
    stats        = {}

    # ── 1. RSS 수집 ──────────────────────────────────────
    log(f"[1] RSS 수집 ({len(RSS_FEEDS)}개 소스)...")
    rss_articles = []
    for name, feed_url in RSS_FEEDS.items():
        arts = fetch_rss(feed_url, name, cutoff, existing)
        rss_articles.extend(arts)
        if arts:
            log(f"  {name}: {len(arts)}건")
        time.sleep(0.5)
    all_articles.extend(rss_articles)
    stats['RSS'] = len(rss_articles)
    log(f"  RSS 합계: {len(rss_articles)}건")

    # ── 2. NewsData.io 수집 ───────────────────────────────
    newsdata_key = os.environ.get('NEWSDATA_API_KEY', '')
    if newsdata_key:
        log(f"[2] NewsData.io 수집...")
        nd_articles = fetch_newsdata(newsdata_key, cutoff, existing)
        all_articles.extend(nd_articles)
        stats['NewsData.io'] = len(nd_articles)
        log(f"  NewsData.io: {len(nd_articles)}건")
    else:
        log("[2] NewsData.io: NEWSDATA_API_KEY 미설정 → 건너뜀")
        stats['NewsData.io'] = 0

    # ── 3. GNews 수집 ─────────────────────────────────────
    if ENABLE_GNEWS:
        log(f"[3] GNews 수집...")
        gn_arts = fetch_gnews(GNEWS_API_KEY, GNEWS_QUERY, cutoff, existing)
        gn_arts += fetch_gnews(GNEWS_API_KEY, GNEWS_ENV_QUERY, cutoff, existing)
        all_articles.extend(gn_arts)
        stats['GNews'] = len(gn_arts)
        log(f"  GNews: {len(gn_arts)}건")
    else:
        stats['GNews'] = 0

    # ── 중복 제거 (URL 기준) ──────────────────────────────
    seen = set()
    unique = []
    for a in all_articles:
        url = a.get('url', '')
        if url and url not in seen:
            seen.add(url)
            unique.append(a)
    log(f"중복 제거: {len(all_articles)} → {len(unique)}건")

    # ── date fallback 보정 (영구 제약) ───────────────────
    for a in unique:
        if not a.get('date'):
            a['date'] = a.get('published_date', '')

    # ── 섹터/Province 분류 ────────────────────────────────
    for a in unique:
        if not a.get('sector'):
            a['sector'] = classify_sector(
                a.get('title_en', '') or a.get('title', ''),
                a.get('sum_en', '') or a.get('summary', '')
            )
        if not a.get('province'):
            a['province'] = extract_province(
                a.get('title_en', '') or a.get('title', '')
            )
        if not a.get('area'):
            a['area'] = area_fill(a['sector'])

    # ── SQLite 저장 ───────────────────────────────────────
    saved_db = 0
    for a in unique:
        if save_article(conn, a):
            saved_db += 1
    conn.close()
    log(f"SQLite 저장: {saved_db}건")

    # 통계 출력
    log(f"수집 완료: RSS={stats['RSS']} NewsData={stats['NewsData.io']} GNews={stats['GNews']}")
    log(f"  (전문미디어는 weekly_backfill.yml → specialist_crawler.py 담당)")

    return unique


# ════════════════════════════════════════════════════════
# Excel 업데이트 (ExcelUpdater 위임)
# ════════════════════════════════════════════════════════
def update_excel_database(articles: list[dict]) -> dict:
    """
    ExcelUpdater.update_all() 호출
    직접 Excel 쓰기 금지 — excel_updater.py 위임
    """
    if not articles:
        return {}
    try:
        scripts_dir = Path(__file__).parent
        sys.path.insert(0, str(scripts_dir))
        from excel_updater import ExcelUpdater
        updater = ExcelUpdater(EXCEL_PATH)
        return updater.update_all(articles)
    except ImportError:
        log("ExcelUpdater 없음 → Excel 업데이트 건너뜀")
        return {}
    except Exception as e:
        log(f"Excel 업데이트 오류: {e}")
        return {}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='베트남 인프라 뉴스 수집기')
    parser.add_argument('--hours', type=int, default=24, help='수집 기간(시간)')
    args = parser.parse_args()
    articles = collect_news(hours_back=args.hours)
    log(f"수집 완료: {len(articles)}건")
