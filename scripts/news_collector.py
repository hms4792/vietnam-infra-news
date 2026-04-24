"""
news_collector.py  — v8.1
==========================
베트남 인프라 뉴스 수집기

v8.1 변경사항 (2026-04-24):
  - NEWSDATA_QUERIES: 섹터 14개 + 마스터플랜 16개 + Province 3그룹 완전 반영
  - fetch_newsdata(): 5가지 수집 방법 통합 구현
  - should_collect(): 4단계 품질 게이트 유지
  - 영구 폐쇄 소스 제거 유지

영구 제약:
  - NewsData.io 엔드포인트: /api/1/latest 만 사용 (archive 유료)
  - 금지 파라미터: domain 단독, from_date, category+domain 조합
  - 422 오류 시 자동 재시도 (category 제거)
  - 이메일 시크릿: EMAIL_USERNAME / EMAIL_PASSWORD
  - 번역: Google Translate only (Anthropic API 금지)
  - date 키 fallback: article.get('date') or article.get('published_date')

영구 폐쇄 RSS (재추가 금지):
  theinvestor.vn RSS, vir.com.vn RSS, constructionvietnam.net,
  monre.gov.vn, vea.gov.vn, mic.gov.vn, smartcity.mobi,
  baotintuc.vn, kinhtemoitruong.vn, hanoimoi.vn
"""

import feedparser
import hashlib
import logging
import os
import re
import time
from datetime import datetime, timedelta

import requests

# ── 로깅 ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('news_collector')

# ══════════════════════════════════════════════════════════════════════════
#  RSS 소스 목록 (검증 완료, 2026-04-07 기준)
# ══════════════════════════════════════════════════════════════════════════
RSS_FEEDS = {
    # ── 환경 인프라 ────────────────────────────────────────────────────
    'Hanoi Times (Home)':      'https://hanoitimes.vn/rss/home.rss',
    'Moi truong & Cuoc song':  'https://moitruong.net.vn/rss/home.rss',

    # ── 에너지 / 전력 ──────────────────────────────────────────────────
    'PV-Tech (All)':           'https://www.pv-tech.org/feed/',
    'Energy Monitor':          'https://www.energymonitor.ai/rss',

    # ── 국제 비즈니스 (베트남 필터 적용) ───────────────────────────────
    'Nikkei Asia':             'https://asia.nikkei.com/rss/feed/nar',

    # ── 스마트시티 / ICT ───────────────────────────────────────────────
    'VietnamNet ICT':          'https://vietnamnet.vn/rss/cong-nghe.rss',

    # ── 종합 영문 (베트남) ─────────────────────────────────────────────
    'Vietnam News (Env)':      'https://vietnamnews.vn/environment/rss.xml',
    'Vietnam News (Economy)':  'https://vietnamnews.vn/economy/rss.xml',
    'Vietnam News (Society)':  'https://vietnamnews.vn/society/rss.xml',
    'VnExpress International': 'https://e.vnexpress.net/rss/news.rss',
    'VnExpress Business':      'https://e.vnexpress.net/rss/business.rss',

    # ── 수자원 / 환경 베트남어 ─────────────────────────────────────────
    'Bao Tai nguyen (VN)':     'https://baotainguyenmoitruong.vn/rss/home.rss',
}

# ══════════════════════════════════════════════════════════════════════════
#  섹터 키워드 (SA-6 품질검증 연계)
# ══════════════════════════════════════════════════════════════════════════
SECTOR_KEYWORDS = {
    'Waste Water': [
        'wastewater', 'sewage', 'wwtp', 'nước thải', 'xử lý nước',
        'effluent', 'sewerage', 'thoát nước', 'phân bùn',
    ],
    'Water Supply/Drainage': [
        'water supply', 'clean water', 'drinking water', 'cấp nước',
        'nước sạch', 'waterworks', 'drainage', 'water treatment plant',
        'water pipe', 'thoát nước đô thị',
    ],
    'Solid Waste': [
        'solid waste', 'waste management', 'landfill', 'waste-to-energy',
        'wte', 'incineration', 'rác thải', 'chất thải rắn', 'đốt rác',
        'epr', 'recycling', 'tái chế', 'thu gom rác',
    ],
    'Power': [
        'power plant', 'electricity', 'renewable energy', 'solar', 'wind',
        'offshore wind', 'pdp8', 'điện', 'năng lượng', 'điện mặt trời',
        'điện gió', 'bess', 'battery storage', 'lng power', 'nuclear',
        'dppa', 'energy storage',
    ],
    'Oil & Gas': [
        'oil', 'gas', 'petroleum', 'lng', 'petrovietnam', 'pvn',
        'dầu khí', 'khí đốt', 'refinery', 'pipeline',
    ],
    'Industrial Parks': [
        'industrial park', 'industrial zone', 'economic zone', 'fdi',
        'vsip', 'khu công nghiệp', 'khu kinh tế', 'manufacturing',
        'semiconductor', 'deep c',
    ],
    'Smart City': [
        'smart city', 'metro', 'urban rail', 'digital city',
        'thành phố thông minh', 'tàu điện', 'công nghệ số', 'ict',
        'data center', 'đô thị thông minh',
    ],
    'Transport': [
        'expressway', 'highway', 'airport', 'port', 'logistics',
        'cao tốc', 'sân bay', 'cảng biển', 'ring road',
        'long thanh', 'metro', 'brt',
    ],
}

# ══════════════════════════════════════════════════════════════════════════
#  노이즈 필터 (should_collect 4단계 게이트)
# ══════════════════════════════════════════════════════════════════════════
NOISE_PATTERNS = [
    # 오락·스포츠
    r'\bsoccer\b', r'\bfootball\b', r'\bcelebrit\b', r'\bentertain\b',
    r'\bmusic\b', r'\bfilm\b', r'\bmovie\b', r'\bgossip\b',
    r'\bbeauty\b', r'\bfashion\b', r'\bcosmet\b',
    # 건강·의료 (인프라 제외)
    r'\bcovid\b', r'\bpandemic\b', r'\bvaccin\b', r'\bhospital bed\b',
    # 광고성
    r'\bpromotion\b', r'\bdiscount\b', r'\bsale off\b', r'\bcoupon\b',
    # 정치 일반 (인프라 정책 제외)
    r'\belection\b', r'\bvoting\b', r'\bpoll\b',
    # 베트남어 노이즈
    r'thể thao', r'giải trí', r'ca nhạc', r'phim', r'làm đẹp',
    r'khuyến mãi', r'giảm giá',
]

VIETNAM_KEYWORDS = [
    'vietnam', 'viet nam', 'việt nam', 'hanoi', 'ha noi', 'hà nội',
    'ho chi minh', 'hcmc', 'hà nội', 'saigon', 'sài gòn',
    'mekong', 'haiphong', 'hải phòng', 'danang', 'đà nẵng',
]


# ══════════════════════════════════════════════════════════════════════════
#  1단계: should_collect() — 4단계 품질 게이트
# ══════════════════════════════════════════════════════════════════════════
def should_collect(title: str, summary: str = '', source: str = '') -> tuple[bool, str]:
    """
    기사 수집 여부를 4단계로 판정합니다.

    Returns:
        (collect: bool, reason: str)
    """
    text = (title + ' ' + summary).lower()

    # ── Gate 1: 최소 길이 ────────────────────────────────────────────
    if len(title.strip()) < 10:
        return False, 'TITLE_TOO_SHORT'

    # ── Gate 2: 노이즈 패턴 ──────────────────────────────────────────
    for pat in NOISE_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return False, f'NOISE:{pat}'

    # ── Gate 3: 베트남 관련성 (국제 소스에만 엄격 적용) ──────────────
    INTL_SOURCES = ['nikkei', 'pv-tech', 'energy monitor', 'bloomberg', 'reuters']
    is_intl = any(s in source.lower() for s in INTL_SOURCES)
    if is_intl:
        has_vietnam = any(kw in text for kw in VIETNAM_KEYWORDS)
        if not has_vietnam:
            return False, 'NOT_VIETNAM_RELATED'

    # ── Gate 4: 섹터 관련성 ──────────────────────────────────────────
    has_sector = False
    for sector, keywords in SECTOR_KEYWORDS.items():
        if any(kw.lower() in text for kw in keywords):
            has_sector = True
            break

    if not has_sector:
        return False, 'NO_SECTOR_MATCH'

    return True, 'OK'


# ══════════════════════════════════════════════════════════════════════════
#  2단계: RSS 수집
# ══════════════════════════════════════════════════════════════════════════
def fetch_rss_articles(hours_back: int = 24) -> list[dict]:
    """
    RSS_FEEDS에서 기사 수집 후 should_collect 필터 적용.
    """
    cutoff = datetime.now() - timedelta(hours=hours_back)
    articles = []
    seen_urls = set()

    for source_name, feed_url in RSS_FEEDS.items():
        try:
            feed = feedparser.parse(feed_url)
            if not feed.entries:
                log.warning(f'[RSS] 빈 피드: {source_name}')
                continue

            count = 0
            for entry in feed.entries:
                url = entry.get('link', '').strip()
                if not url or url in seen_urls:
                    continue

                title   = entry.get('title', '').strip()
                summary = entry.get('summary', entry.get('description', '')).strip()

                # 날짜 파싱
                pub_date = None
                for date_field in ('published_parsed', 'updated_parsed', 'created_parsed'):
                    if hasattr(entry, date_field) and getattr(entry, date_field):
                        try:
                            import calendar
                            t = getattr(entry, date_field)
                            pub_date = datetime.fromtimestamp(calendar.timegm(t))
                            break
                        except Exception:
                            pass
                if not pub_date:
                    pub_date = datetime.now()

                if pub_date < cutoff:
                    continue

                # 품질 게이트
                ok, reason = should_collect(title, summary, source_name)
                if not ok:
                    continue

                seen_urls.add(url)
                articles.append({
                    'title':          title,
                    'summary':        summary[:500],
                    'url':            url,
                    # source fallback — Python or 연산자 (빈 문자열 방지)
                    'source':         source_name or 'Unknown',
                    'date':           pub_date.strftime('%Y-%m-%d'),
                    'published_date': pub_date.strftime('%Y-%m-%d'),
                    'collector':      'rss',
                    'ctx_grade':      'MEDIUM',
                    'ctx_plans':      '',
                })
                count += 1

            if count > 0:
                log.info(f'[RSS] {source_name}: {count}건')

        except Exception as e:
            log.warning(f'[RSS] {source_name} 오류: {e}')

    log.info(f'[RSS] 총 {len(articles)}건 수집')
    return articles


# ══════════════════════════════════════════════════════════════════════════
#  3단계: NEWSDATA_QUERIES — 5가지 방법 통합
# ══════════════════════════════════════════════════════════════════════════

# ── 방법1-A: 7개 섹터 기본 쿼리 (매일) ──────────────────────────────────
NEWSDATA_SECTOR_QUERIES = [
    # Waste Water
    {'q': 'Vietnam wastewater treatment plant WWTP sewage 2026',
     'language': 'en', 'sector': 'Waste Water', 'label': 'WW-EN'},
    {'q': 'nước thải xử lý Việt Nam 2026',
     'language': 'vi', 'sector': 'Waste Water', 'label': 'WW-VI'},
    # Water Supply/Drainage
    {'q': 'Vietnam water supply clean water infrastructure 2026',
     'language': 'en', 'sector': 'Water Supply/Drainage', 'label': 'WAT-EN'},
    {'q': 'nước sạch cấp nước thoát nước Việt Nam 2026',
     'language': 'vi', 'sector': 'Water Supply/Drainage', 'label': 'WAT-VI'},
    # Solid Waste
    {'q': 'Vietnam solid waste management waste-to-energy landfill 2026',
     'language': 'en', 'sector': 'Solid Waste', 'label': 'SW-EN'},
    {'q': 'rác thải chất thải rắn Việt Nam đốt rác 2026',
     'language': 'vi', 'sector': 'Solid Waste', 'label': 'SW-VI'},
    # Power
    {'q': 'Vietnam power plant renewable energy PDP8 electricity 2026',
     'language': 'en', 'sector': 'Power', 'label': 'PWR-EN'},
    {'q': 'điện năng lượng tái tạo phát điện Việt Nam 2026',
     'language': 'vi', 'sector': 'Power', 'label': 'PWR-VI'},
    # Oil & Gas
    {'q': 'Vietnam LNG oil gas PetroVietnam offshore 2026',
     'language': 'en', 'sector': 'Oil & Gas', 'label': 'OG-EN'},
    {'q': 'dầu khí LNG PetroVietnam Việt Nam 2026',
     'language': 'vi', 'sector': 'Oil & Gas', 'label': 'OG-VI'},
    # Industrial Parks
    {'q': 'Vietnam industrial park zone FDI investment 2026',
     'language': 'en', 'sector': 'Industrial Parks', 'label': 'IND-EN'},
    {'q': 'khu công nghiệp FDI đầu tư Việt Nam 2026',
     'language': 'vi', 'sector': 'Industrial Parks', 'label': 'IND-VI'},
    # Smart City / Transport
    {'q': 'Vietnam smart city metro airport expressway 2026',
     'language': 'en', 'sector': 'Smart City', 'label': 'SC-EN'},
    {'q': 'thành phố thông minh tàu điện sân bay cao tốc Việt Nam 2026',
     'language': 'vi', 'sector': 'Smart City', 'label': 'SC-VI'},
]

# ── 방법1-B: 12개 마스터플랜 전용 쿼리 (매일) ────────────────────────────
NEWSDATA_MASTER_QUERIES = [
    # VN-WW-2030
    {'q': 'Yen Xa WWTP wastewater Hanoi Binh Hung Thu Duc treatment plant',
     'language': 'en', 'plan_id': 'VN-WW-2030', 'sector': 'Waste Water'},
    {'q': '"Yen Xa" OR "nhà máy xử lý nước thải" Hà Nội 2026',
     'language': 'vi', 'plan_id': 'VN-WW-2030', 'sector': 'Waste Water'},
    # VN-SWM-NATIONAL-2030
    {'q': 'Soc Son waste-to-energy Vietnam landfill EPR solid waste 2026',
     'language': 'en', 'plan_id': 'VN-SWM-NATIONAL-2030', 'sector': 'Solid Waste'},
    {'q': '"Sóc Sơn" OR "đốt rác phát điện" OR "EPR" rác thải Hà Nội 2026',
     'language': 'vi', 'plan_id': 'VN-SWM-NATIONAL-2030', 'sector': 'Solid Waste'},
    # VN-PWR-PDP8
    {'q': 'PDP8 Vietnam power development plan Decision 768 offshore wind nuclear',
     'language': 'en', 'plan_id': 'VN-PWR-PDP8', 'sector': 'Power'},
    {'q': '"Quy hoạch điện 8" OR "Quyết định 768" năng lượng Việt Nam 2026',
     'language': 'vi', 'plan_id': 'VN-PWR-PDP8', 'sector': 'Power'},
    # VN-PWR-PDP8-RENEWABLE
    {'q': 'Vietnam offshore wind solar BESS battery energy storage DPPA 2026',
     'language': 'en', 'plan_id': 'VN-PWR-PDP8-RENEWABLE', 'sector': 'Power'},
    {'q': 'điện gió ngoài khơi điện mặt trời BESS Việt Nam 2026',
     'language': 'vi', 'plan_id': 'VN-PWR-PDP8-RENEWABLE', 'sector': 'Power'},
    # VN-TRAN-2055
    {'q': 'Long Thanh airport Vietnam expressway Ring Road 4 metro 2026',
     'language': 'en', 'plan_id': 'VN-TRAN-2055', 'sector': 'Transport'},
    {'q': '"Sân bay Long Thành" OR "đường vành đai 4" OR "cao tốc" Việt Nam 2026',
     'language': 'vi', 'plan_id': 'VN-TRAN-2055', 'sector': 'Transport'},
    # VN-WAT-URBAN
    {'q': 'Vietnam urban water supply clean water PPP infrastructure 2026',
     'language': 'en', 'plan_id': 'VN-WAT-URBAN', 'sector': 'Water Supply/Drainage'},
    {'q': 'cấp nước đô thị Việt Nam PPP đầu tư hạ tầng nước 2026',
     'language': 'vi', 'plan_id': 'VN-WAT-URBAN', 'sector': 'Water Supply/Drainage'},
    # VN-URB-METRO-2030
    {'q': 'Hanoi Ho Chi Minh metro BRT urban rail transit 2026',
     'language': 'en', 'plan_id': 'VN-URB-METRO-2030', 'sector': 'Smart City'},
    {'q': '"Metro" OR "tàu điện ngầm" Hà Nội "Hồ Chí Minh" 2026',
     'language': 'vi', 'plan_id': 'VN-URB-METRO-2030', 'sector': 'Smart City'},
    # VN-ENV-IND-1894
    {'q': 'Vietnam green industrial park eco-zone environmental technology 2026',
     'language': 'en', 'plan_id': 'VN-ENV-IND-1894', 'sector': 'Industrial Parks'},
    {'q': '"khu công nghiệp xanh" OR "công nghệ môi trường" Việt Nam 2026',
     'language': 'vi', 'plan_id': 'VN-ENV-IND-1894', 'sector': 'Industrial Parks'},
]

# ── 방법1-C: Province × 섹터 교차 쿼리 ──────────────────────────────────
NEWSDATA_PROVINCE_QUERIES = {
    # Group A: 핵심 Province (매일)
    'group_a': [
        {'q': '"Da Nang" wastewater OR "water supply" OR infrastructure 2026',
         'language': 'en', 'province': 'Da Nang'},
        {'q': '"Đà Nẵng" nước thải OR hạ tầng 2026',
         'language': 'vi', 'province': 'Da Nang'},
        {'q': '"Binh Duong" industrial park OR wastewater OR power 2026',
         'language': 'en', 'province': 'Binh Duong'},
        {'q': '"Dong Nai" infrastructure OR industrial OR "Long Thanh" 2026',
         'language': 'en', 'province': 'Dong Nai'},
        {'q': '"Quang Ninh" port OR power OR industrial 2026',
         'language': 'en', 'province': 'Quang Ninh'},
        {'q': '"Bac Ninh" OR "Bắc Ninh" industrial OR semiconductor 2026',
         'language': 'en', 'province': 'Bac Ninh'},
        {'q': '"Hai Phong" OR "Hải Phòng" port OR industrial 2026',
         'language': 'en', 'province': 'Hai Phong'},
    ],
    # Group B: 홀수일에만 실행
    'group_b': [
        {'q': '"Ba Ria Vung Tau" OR "Vũng Tàu" oil gas OR port 2026',
         'language': 'en', 'province': 'Ba Ria Vung Tau'},
        {'q': '"Binh Dinh" OR "Bình Định" infrastructure 2026',
         'language': 'en', 'province': 'Binh Dinh'},
        {'q': '"Quang Nam" infrastructure OR industrial 2026',
         'language': 'en', 'province': 'Quang Nam'},
        {'q': '"Thai Nguyen" OR "Thái Nguyên" industrial OR Samsung 2026',
         'language': 'en', 'province': 'Thai Nguyen'},
        {'q': '"Can Tho" OR "Cần Thơ" infrastructure OR water 2026',
         'language': 'en', 'province': 'Can Tho'},
    ],
    # Group C: 월·목요일에만 실행
    'group_c': [
        {'q': '"Ninh Thuan" OR "Ninh Thuận" wind solar energy 2026',
         'language': 'en', 'province': 'Ninh Thuan'},
        {'q': '"Khanh Hoa" OR "Khánh Hòa" infrastructure 2026',
         'language': 'en', 'province': 'Khanh Hoa'},
        {'q': '"Long An" industrial OR wastewater 2026',
         'language': 'en', 'province': 'Long An'},
    ],
}

# ── 통합 기본 쿼리 리스트 ─────────────────────────────────────────────────
NEWSDATA_QUERIES = NEWSDATA_SECTOR_QUERIES + NEWSDATA_MASTER_QUERIES


# ══════════════════════════════════════════════════════════════════════════
#  fetch_newsdata() — NewsData.io API 호출
# ══════════════════════════════════════════════════════════════════════════
def fetch_newsdata(api_key: str, hours_back: int = 24) -> list[dict]:
    """
    NewsData.io /api/1/latest API로 기사 수집.

    5가지 수집 방법 중 방법1에 해당:
      A: 7개 섹터 기본 쿼리 (매일)
      B: 12개 마스터플랜 전용 쿼리 (매일)
      C: Province × 섹터 교차 쿼리 (그룹별 주기 다름)

    제약:
      /api/1/latest 엔드포인트만 사용 (archive 유료)
      country=vn + language + q 파라미터만 사용
      domain / from_date / category+domain 조합 금지
      422 오류 시 category 없이 재시도
      일별 200 크레딧 한도
    """
    if not api_key:
        log.warning('[NewsData.io] API 키 없음 — 건너뜀')
        return []

    API_URL    = 'https://newsdata.io/api/1/latest'
    CREDIT_MAX = 190   # 안전 마진 10 크레딧
    SIZE       = 5     # 쿼리당 수집 건수

    credit_used = 0
    articles    = []
    seen_urls   = set()

    today    = datetime.now()
    day_odd  = today.day % 2 == 1           # 홀수일 여부
    day_mon_thu = today.weekday() in (0, 3)  # 월(0) 또는 목(3)

    def call_api(q, lang, size=SIZE):
        """단일 API 호출 (422 자동 재시도)."""
        nonlocal credit_used
        if credit_used >= CREDIT_MAX:
            return []

        params = {
            'apikey':   api_key,
            'country':  'vn',
            'language': lang,
            'q':        q,
            'size':     size,
        }

        for attempt in range(2):
            try:
                resp = requests.get(API_URL, params=params, timeout=15)

                if resp.status_code == 422:
                    # category 파라미터가 있다면 제거 후 재시도
                    # (이 함수는 category를 사용하지 않으므로 그냥 종료)
                    log.warning(f'[NewsData.io] 422 오류 — q={q[:40]}')
                    return []

                if resp.status_code == 429:
                    log.warning('[NewsData.io] 429 Rate Limit — 60초 대기')
                    time.sleep(60)
                    continue

                resp.raise_for_status()
                data = resp.json()
                credit_used += 1
                return data.get('results', [])

            except requests.exceptions.Timeout:
                log.warning(f'[NewsData.io] 타임아웃 ({attempt + 1}/2)')
                time.sleep(2)
            except Exception as e:
                log.warning(f'[NewsData.io] 오류: {e}')
                return []

        return []

    def parse_result(raw, sector='', plan_id='', province=''):
        """NewsData.io 결과 → 표준 기사 딕셔너리."""
        # URL 기반 중복 제거
        url = (raw.get('link') or raw.get('url') or '').strip()
        if not url or url in seen_urls:
            return None
        seen_urls.add(url)

        # 날짜 처리
        pub_date = (raw.get('pubDate') or raw.get('publishedAt') or '')[:10]
        if not pub_date:
            pub_date = datetime.now().strftime('%Y-%m-%d')

        # source 필드 fallback — Python or 연산자 (빈 문자열 방지)
        source = (
            raw.get('source_id') or
            raw.get('source_name') or
            (raw.get('creator') or [''])[0] or
            'NewsData.io'
        )

        title = (raw.get('title') or '').strip()
        desc  = (raw.get('description') or raw.get('content') or '')[:300].strip()

        if not title:
            return None

        # 품질 게이트 적용
        ok, reason = should_collect(title, desc, source)
        if not ok:
            return None

        return {
            'title':          title,
            'summary':        desc,
            'url':            url,
            'source':         source,
            'date':           pub_date,
            'published_date': pub_date,
            'sector':         sector,
            'province':       province,
            'plan_id':        plan_id,
            'collector':      'newsdata_io',
            'ctx_grade':      'MEDIUM',
            'ctx_plans':      plan_id if plan_id else '',
        }

    # ── A: 섹터 기본 쿼리 (매일) ─────────────────────────────────────
    log.info('[NewsData.io] 방법1-A: 섹터 기본 쿼리')
    for q_info in NEWSDATA_SECTOR_QUERIES:
        if credit_used >= CREDIT_MAX:
            break
        results = call_api(q_info['q'], q_info['language'])
        for raw in results:
            parsed = parse_result(raw, sector=q_info.get('sector', ''))
            if parsed:
                articles.append(parsed)
        time.sleep(0.3)

    # ── B: 마스터플랜 전용 쿼리 (매일) ──────────────────────────────
    log.info('[NewsData.io] 방법1-B: 마스터플랜 쿼리')
    for q_info in NEWSDATA_MASTER_QUERIES:
        if credit_used >= CREDIT_MAX:
            break
        results = call_api(q_info['q'], q_info['language'])
        for raw in results:
            parsed = parse_result(
                raw,
                sector=q_info.get('sector', ''),
                plan_id=q_info.get('plan_id', ''),
            )
            if parsed:
                articles.append(parsed)
        time.sleep(0.3)

    # ── C-A: Province Group A (매일) ─────────────────────────────────
    log.info('[NewsData.io] 방법1-C: Province Group A')
    for q_info in NEWSDATA_PROVINCE_QUERIES['group_a']:
        if credit_used >= CREDIT_MAX:
            break
        results = call_api(q_info['q'], q_info['language'])
        for raw in results:
            parsed = parse_result(raw, province=q_info.get('province', ''))
            if parsed:
                articles.append(parsed)
        time.sleep(0.3)

    # ── C-B: Province Group B (홀수일) ───────────────────────────────
    if day_odd:
        log.info('[NewsData.io] 방법1-C: Province Group B (홀수일)')
        for q_info in NEWSDATA_PROVINCE_QUERIES['group_b']:
            if credit_used >= CREDIT_MAX:
                break
            results = call_api(q_info['q'], q_info['language'])
            for raw in results:
                parsed = parse_result(raw, province=q_info.get('province', ''))
                if parsed:
                    articles.append(parsed)
            time.sleep(0.3)

    # ── C-C: Province Group C (월·목) ────────────────────────────────
    if day_mon_thu:
        log.info('[NewsData.io] 방법1-C: Province Group C (월·목)')
        for q_info in NEWSDATA_PROVINCE_QUERIES['group_c']:
            if credit_used >= CREDIT_MAX:
                break
            results = call_api(q_info['q'], q_info['language'])
            for raw in results:
                parsed = parse_result(raw, province=q_info.get('province', ''))
                if parsed:
                    articles.append(parsed)
            time.sleep(0.3)

    log.info(
        f'[NewsData.io] 완료 — {len(articles)}건 / '
        f'{credit_used}/{CREDIT_MAX} 크레딧'
    )
    return articles


# ══════════════════════════════════════════════════════════════════════════
#  메인 수집 함수
# ══════════════════════════════════════════════════════════════════════════
def collect_news(hours_back: int = 24) -> list[dict]:
    """
    RSS + NewsData.io 통합 수집.

    main.py Step1에서 호출:
        articles = collect_news(hours_back=24)

    Returns:
        list[dict]: 수집된 기사 목록
        각 기사에 date / published_date 키 모두 포함
    """
    log.info(f'=== 뉴스 수집 시작 (hours_back={hours_back}) ===')

    # ── RSS 수집 ────────────────────────────────────────────────────
    rss_articles = fetch_rss_articles(hours_back)

    # ── NewsData.io 수집 ─────────────────────────────────────────────
    api_key = os.getenv('NEWSDATA_API_KEY', '')
    nd_articles = fetch_newsdata(api_key, hours_back)

    # ── 통합 + 최종 중복 제거 ────────────────────────────────────────
    all_articles = rss_articles + nd_articles
    seen = set()
    unique_articles = []
    for art in all_articles:
        url = art.get('url', '')
        if url and url not in seen:
            seen.add(url)
            unique_articles.append(art)

    # ── 날짜 정규화: date / published_date 동시 보장 ──────────────────
    for art in unique_articles:
        # date 키 fallback
        date_val = art.get('date') or art.get('published_date', '')
        art['date']           = date_val
        art['published_date'] = date_val

    log.info(
        f'=== 수집 완료: RSS {len(rss_articles)}건 + '
        f'NewsData {len(nd_articles)}건 = '
        f'최종 {len(unique_articles)}건 ===\n'
    )
    return unique_articles


# ══════════════════════════════════════════════════════════════════════════
#  직접 실행 시 테스트
# ══════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    import sys

    hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    articles = collect_news(hours_back=hours)

    print(f'\n수집 결과: {len(articles)}건')
    for i, art in enumerate(articles[:5], 1):
        print(f'  [{i}] {art["date"]} | {art["source"]} | {art["title"][:60]}')

    if len(articles) > 5:
        print(f'  ... 외 {len(articles) - 5}건')
