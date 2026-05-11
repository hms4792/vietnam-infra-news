"""
news_collector.py  — v8.5
==========================
베트남 인프라 뉴스 수집기

v8.5 변경사항 (2026-05-11):
  ★ 무관 기사 필터 강화 (품질 개선)

  [변경 1] NOISE_PATTERNS 확장
    - 기존 29개 → 50개로 확장
    - 추가: ruby, casino, esport, IPL, cricket, robotaxi,
            game developer, psychonauts, keralam, nobitex 등
    - 효과: 무관 기사 48% → 목표 25% 이하

  [변경 2] should_collect()에 EXCLUDE_EXACT 블록 추가
    - 기존 정규식 체크 이전에 단순 문자열 즉시 제외 로직 추가
    - 처리 속도 향상 + 정확도 향상
    - 기존 4단계 게이트 구조 완전 보존

  ★ 나머지 코드 전체 v8.4 동일 (RSS_FEEDS, fetch_newsdata,
    NEWSDATA_QUERIES, collect_news 등 변경 없음)

v8.4 변경사항 (2026-05-09):
  ★ 한국 공공기관·국제개발금융기관 뉴스 수집 추가

  [배경]
  - KEITI(환경산업기술원), KOICA, KIND, 해외건설협회 공식 사이트는
    GitHub Actions 미국 IP에서 HTTP 403 전면 차단 → 직접 크롤링 불가
  - 해결책: 해당 기관 사업을 보도하는 국제기관 RSS + NewsData.io 쿼리로 우회 수집

  [추가 내용]
  1. RSS_FEEDS: 국제개발금융기관 공식 RSS 7개 추가
     - ADB, World Bank, AIIB, GIZ, Vietnam Briefing, Mekong Eye, WaterWorld
  2. fetch_newsdata() 내 방법1-D/E 블록 추가
     - 방법1-D: 한국 ODA 기관 뉴스 (KOICA·KIND·KEITI·ICAK) — 홀수일
     - 방법1-E: 국제개발금융 베트남 인프라 (ADB·WB·AIIB·JICA·GIZ) — 짝수일

v8.3 변경사항 (2026-05-04):
  ★ 429 Rate Limit 처리 방식 전면 개선 (무료 플랜 안전 운영)

v8.2 변경사항 (2026-04-25):
  - NEWSDATA_MASTER_QUERIES에 한-베 협력 쿼리 4개 추가

v8.1 변경사항 (2026-04-24):
  - NEWSDATA_QUERIES: 섹터 14개 + 마스터플랜 16개 + Province 3그룹

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
#  RSS 소스 목록 (v8.4 그대로 유지)
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

    # ── v8.4: 국제개발금융·한국 ODA 베트남 관련 RSS ────────────────────
    'ADB Vietnam':             'https://www.adb.org/news/rss.xml',
    'World Bank VN News':      'https://feeds.worldbank.org/en/rss/vietnam',
    'AIIB News':               'https://www.aiib.org/en/news-events/rss.xml',
    'GIZ Press':               'https://www.giz.de/en/newsroom/rss.xml',
    'Vietnam Briefing':        'https://www.vietnam-briefing.com/news/feed',
    'Mekong Eye':              'https://mekongeye.com/feed/',
    'Water World News':        'https://www.waterworld.com/rss.xml',
}

# ══════════════════════════════════════════════════════════════════════════
#  섹터 키워드 (v8.4 그대로 유지)
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
    'Bilateral': [
        'korea vietnam cooperation', 'korea vietnam summit',
        'south korea vietnam', 'korea-vietnam', 'rok vietnam',
        'hàn quốc việt nam', 'korea mou vietnam',
        'korea invest vietnam', 'vietnam korea energy',
        'vietnam korea nuclear', 'vietnam korea environment',
        'bilateral infrastructure', 'bilateral cooperation vietnam',
        'koica vietnam', 'keiti vietnam', 'kind korea vietnam',
        'oda korea vietnam', 'korean oda',
        'adb vietnam', 'world bank vietnam', 'jica vietnam',
        'aiib vietnam', 'giz vietnam',
    ],
}

# ══════════════════════════════════════════════════════════════════════════
#  노이즈 필터 — v8.5: 기존 29개 + 신규 21개 = 50개
# ══════════════════════════════════════════════════════════════════════════
NOISE_PATTERNS = [
    # ── 기존 v8.4 패턴 (29개) ─────────────────────────────────────────
    r'\bsoccer\b', r'\bfootball\b', r'\bcelebrit\b', r'\bentertain\b',
    r'\bmusic\b', r'\bfilm\b', r'\bmovie\b', r'\bgossip\b',
    r'\bbeauty\b', r'\bfashion\b', r'\bcosmet\b',
    r'\bcovid\b', r'\bpandemic\b', r'\bvaccin\b', r'\bhospital bed\b',
    r'\bpromotion\b', r'\bdiscount\b', r'\bsale off\b', r'\bcoupon\b',
    r'\belection\b', r'\bvoting\b', r'\bpoll\b',
    r'thể thao', r'giải trí', r'ca nhạc', r'phim', r'làm đẹp',
    r'khuyến mãi', r'giảm giá',

    # ── v8.5 신규 패턴 (21개) — 무관 기사 추가 제거 ─────────────────
    # 귀금속·도박·게임
    r'\bruby\b', r'\bdiamonds?\b', r'\bcasino\b', r'\blottery\b',
    # 스포츠·이스포츠
    r'\besport\b', r'\bgaming\b', r'\bIPL\b', r'\bcricket\b',
    r'\bfifa\b', r'\bolympic\b',
    # 연예·인물
    r'\bactor\b', r'\bsinger\b', r'\binfluencer\b',
    # 사건사고 (인프라 무관)
    r'\brobotaxi\b', r'\bgame developer\b', r'\bgame studio\b',
    r'\bpsychonauts\b',
    # 해외 정치 (베트남 무관)
    r'\bkeralam\b', r'\bcpi\(m\)\b', r'\bpinarayi\b',
    # 금융 제재 (인프라 무관)
    r'\bnobitex\b', r'\bofac blacklist\b',
]

# ══════════════════════════════════════════════════════════════════════════
#  v8.5 신규: EXCLUDE_EXACT — 단순 문자열 즉시 제외 키워드
#  (NOISE_PATTERNS 정규식보다 빠른 전처리용)
# ══════════════════════════════════════════════════════════════════════════
EXCLUDE_EXACT = [
    # 명백히 무관한 제목 패턴 (부분 문자열 매칭)
    'myanmar ruby', 'myanmar unearths', '11,000-carat',
    'singapore airlines flight', '319 people stuck',
    'waymo robotaxi', 'luggage at san jose',
    'psychonauts developer', 'double fine',
    'keralam lop', 'cpi(m) political',
    'nobitex', 'ofac blacklist',
    'happiness boost', 'ultra-wealth population',
    'airasia millionaire', 'tony fernandes launch',
    'billionaire buys australia',
    'taiwanese billionaire lin',
    'ipl 2026', 'ipl match today',
    'rr vs gt', 'csk vs lsg',
    'mitsubishi xpander recall',
    'gastric cancer journal',
    'uk institution campus',
]

VIETNAM_KEYWORDS = [
    'vietnam', 'viet nam', 'việt nam', 'hanoi', 'ha noi', 'hà nội',
    'ho chi minh', 'hcmc', 'hà nội', 'saigon', 'sài gòn',
    'mekong', 'haiphong', 'hải phòng', 'danang', 'đà nẵng',
]


# ══════════════════════════════════════════════════════════════════════════
#  v8.2 신규: 제목 기반 sector 추론 (v8.4 그대로)
# ══════════════════════════════════════════════════════════════════════════
def _infer_sector_from_title(title: str, summary: str = '') -> str:
    text = (title + ' ' + summary).lower()
    rules = [
        ('Power',                  ['nuclear power', 'offshore wind', 'solar power', 'pdp8',
                                    'renewable energy', 'lng power', 'wind farm', 'power plant',
                                    'electricity grid', 'bess', 'battery storage', 'dppa',
                                    'điện gió', 'điện mặt trời', 'năng lượng tái tạo']),
        ('Oil & Gas',              ['oil gas', 'petroleum', 'petrovietnam', 'lng terminal',
                                    'crude oil', 'natural gas', 'offshore oil', 'dầu khí']),
        ('Waste Water',            ['wastewater', 'sewage', 'wwtp', 'nước thải', 'treatment plant']),
        ('Solid Waste',            ['solid waste', 'waste-to-energy', 'wte', 'landfill',
                                    'incineration', 'rác thải', 'chất thải rắn', 'đốt rác']),
        ('Water Supply/Drainage',  ['water supply', 'clean water', 'drinking water',
                                    'cấp nước', 'nước sạch', 'water pipe']),
        ('Industrial Parks',       ['industrial park', 'industrial zone', 'vsip', 'fdi investment',
                                    'khu công nghiệp', 'semiconductor factory', 'samsung factory']),
        ('Transport',              ['expressway', 'airport', 'metro rail', 'ring road',
                                    'long thanh', 'cao tốc', 'sân bay', 'urban rail']),
        ('Smart City',             ['smart city', 'digital city', 'thành phố thông minh',
                                    'data center', 'ict infrastructure']),
        ('Bilateral',              ['korea vietnam', 'south korea vietnam', 'hàn quốc việt nam',
                                    'korea-vietnam', 'bilateral cooperation',
                                    'koica vietnam', 'keiti vietnam', 'adb vietnam',
                                    'world bank vietnam', 'jica vietnam']),
    ]
    for sector, keywords in rules:
        if any(kw in text for kw in keywords):
            return sector
    return 'General'


# ══════════════════════════════════════════════════════════════════════════
#  1단계: should_collect() — v8.5: EXCLUDE_EXACT 블록 추가
# ══════════════════════════════════════════════════════════════════════════
def should_collect(title: str, summary: str = '', source: str = '') -> tuple:
    text = (title + ' ' + summary).lower()

    if len(title.strip()) < 10:
        return False, 'TITLE_TOO_SHORT'

    # ★ v8.5 신규: EXCLUDE_EXACT 즉시 제외 (정규식보다 빠른 전처리)
    # 명백히 무관한 키워드가 제목에 있으면 즉시 제외
    title_lower = title.lower()
    for exc in EXCLUDE_EXACT:
        if exc.lower() in title_lower:
            return False, f'EXCLUDE_EXACT:{exc[:30]}'

    # 기존 NOISE_PATTERNS 체크 (v8.4 동일)
    for pat in NOISE_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return False, f'NOISE:{pat}'

    # v8.4: 국제개발금융·ODA 소스는 베트남 필터 완화
    ODA_SOURCES = ['adb', 'world bank', 'aiib', 'giz', 'jica', 'koica',
                   'vietnam briefing', 'mekong eye', 'waterworld', 'water world']
    is_oda_source = any(s in source.lower() for s in ODA_SOURCES)

    INTL_SOURCES = ['nikkei', 'pv-tech', 'energy monitor', 'bloomberg', 'reuters']
    is_intl = any(s in source.lower() for s in INTL_SOURCES)

    if is_intl and not is_oda_source:
        has_vietnam = any(kw in text for kw in VIETNAM_KEYWORDS)
        if not has_vietnam:
            return False, 'NOT_VIETNAM_RELATED'

    has_sector = False
    for sector, keywords in SECTOR_KEYWORDS.items():
        if any(kw.lower() in text for kw in keywords):
            has_sector = True
            break

    if not has_sector:
        bilateral_kw = [
            'korea vietnam', 'south korea vietnam', 'rok vietnam',
            'hàn quốc việt nam', 'korea-vietnam mou', 'bilateral infrastructure',
            'koica', 'keiti', 'oda korea',
            'adb loan', 'world bank project', 'jica grant', 'aiib', 'giz project',
        ]
        if any(kw in text for kw in bilateral_kw):
            has_sector = True

    if not has_sector:
        return False, 'NO_SECTOR_MATCH'

    return True, 'OK'


# ══════════════════════════════════════════════════════════════════════════
#  2단계: RSS 수집 (v8.4 그대로)
# ══════════════════════════════════════════════════════════════════════════
def fetch_rss_articles(hours_back: int = 24) -> list:
    cutoff    = datetime.now() - timedelta(hours=hours_back)
    articles  = []
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

                pub_date = None
                for date_field in ('published_parsed', 'updated_parsed', 'created_parsed'):
                    if hasattr(entry, date_field) and getattr(entry, date_field):
                        try:
                            import calendar
                            t        = getattr(entry, date_field)
                            pub_date = datetime.fromtimestamp(calendar.timegm(t))
                            break
                        except Exception:
                            pass
                if not pub_date:
                    pub_date = datetime.now()

                if pub_date < cutoff:
                    continue

                ok, reason = should_collect(title, summary, source_name)
                if not ok:
                    continue

                seen_urls.add(url)
                articles.append({
                    'title':          title,
                    'summary':        summary[:500],
                    'url':            url,
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
#  3단계: NEWSDATA_QUERIES (v8.4 그대로 — 변경 없음)
# ══════════════════════════════════════════════════════════════════════════

NEWSDATA_SECTOR_QUERIES = [
    {'q': 'Vietnam wastewater treatment plant WWTP sewage 2026',
     'language': 'en', 'sector': 'Waste Water', 'label': 'WW-EN'},
    {'q': 'nước thải xử lý Việt Nam 2026',
     'language': 'vi', 'sector': 'Waste Water', 'label': 'WW-VI'},
    {'q': 'Vietnam water supply clean water infrastructure 2026',
     'language': 'en', 'sector': 'Water Supply/Drainage', 'label': 'WAT-EN'},
    {'q': 'nước sạch cấp nước thoát nước Việt Nam 2026',
     'language': 'vi', 'sector': 'Water Supply/Drainage', 'label': 'WAT-VI'},
    {'q': 'Vietnam solid waste management waste-to-energy landfill 2026',
     'language': 'en', 'sector': 'Solid Waste', 'label': 'SW-EN'},
    {'q': 'rác thải chất thải rắn Việt Nam đốt rác 2026',
     'language': 'vi', 'sector': 'Solid Waste', 'label': 'SW-VI'},
    {'q': 'Vietnam power plant renewable energy PDP8 electricity 2026',
     'language': 'en', 'sector': 'Power', 'label': 'PWR-EN'},
    {'q': 'điện năng lượng tái tạo phát điện Việt Nam 2026',
     'language': 'vi', 'sector': 'Power', 'label': 'PWR-VI'},
    {'q': 'Vietnam LNG oil gas PetroVietnam offshore 2026',
     'language': 'en', 'sector': 'Oil & Gas', 'label': 'OG-EN'},
    {'q': 'dầu khí LNG PetroVietnam Việt Nam 2026',
     'language': 'vi', 'sector': 'Oil & Gas', 'label': 'OG-VI'},
    {'q': 'Vietnam industrial park zone FDI investment 2026',
     'language': 'en', 'sector': 'Industrial Parks', 'label': 'IND-EN'},
    {'q': 'khu công nghiệp FDI đầu tư Việt Nam 2026',
     'language': 'vi', 'sector': 'Industrial Parks', 'label': 'IND-VI'},
    {'q': 'Vietnam smart city metro airport expressway 2026',
     'language': 'en', 'sector': 'Smart City', 'label': 'SC-EN'},
    {'q': 'thành phố thông minh tàu điện sân bay cao tốc Việt Nam 2026',
     'language': 'vi', 'sector': 'Smart City', 'label': 'SC-VI'},
]

NEWSDATA_MASTER_QUERIES = [
    {'q': 'Yen Xa WWTP wastewater Hanoi Binh Hung Thu Duc treatment plant',
     'language': 'en', 'plan_id': 'VN-WW-2030', 'sector': 'Waste Water'},
    {'q': '"Yen Xa" OR "nhà máy xử lý nước thải" Hà Nội 2026',
     'language': 'vi', 'plan_id': 'VN-WW-2030', 'sector': 'Waste Water'},
    {'q': 'Soc Son waste-to-energy Vietnam landfill EPR solid waste 2026',
     'language': 'en', 'plan_id': 'VN-SWM-NATIONAL-2030', 'sector': 'Solid Waste'},
    {'q': '"Sóc Sơn" OR "đốt rác phát điện" OR "EPR" rác thải Hà Nội 2026',
     'language': 'vi', 'plan_id': 'VN-SWM-NATIONAL-2030', 'sector': 'Solid Waste'},
    {'q': 'PDP8 Vietnam power development plan Decision 768 offshore wind nuclear',
     'language': 'en', 'plan_id': 'VN-PWR-PDP8', 'sector': 'Power'},
    {'q': '"Quy hoạch điện 8" OR "Quyết định 768" năng lượng Việt Nam 2026',
     'language': 'vi', 'plan_id': 'VN-PWR-PDP8', 'sector': 'Power'},
    {'q': 'Vietnam offshore wind solar BESS battery energy storage DPPA 2026',
     'language': 'en', 'plan_id': 'VN-PWR-PDP8-RENEWABLE', 'sector': 'Power'},
    {'q': 'điện gió ngoài khơi điện mặt trời BESS Việt Nam 2026',
     'language': 'vi', 'plan_id': 'VN-PWR-PDP8-RENEWABLE', 'sector': 'Power'},
    {'q': 'Long Thanh airport Vietnam expressway Ring Road 4 metro 2026',
     'language': 'en', 'plan_id': 'VN-TRAN-2055', 'sector': 'Transport'},
    {'q': '"Sân bay Long Thành" OR "đường vành đai 4" OR "cao tốc" Việt Nam 2026',
     'language': 'vi', 'plan_id': 'VN-TRAN-2055', 'sector': 'Transport'},
    {'q': 'Vietnam urban water supply clean water PPP infrastructure 2026',
     'language': 'en', 'plan_id': 'VN-WAT-URBAN', 'sector': 'Water Supply/Drainage'},
    {'q': 'cấp nước đô thị Việt Nam PPP đầu tư hạ tầng nước 2026',
     'language': 'vi', 'plan_id': 'VN-WAT-URBAN', 'sector': 'Water Supply/Drainage'},
    {'q': 'Hanoi Ho Chi Minh metro BRT urban rail transit 2026',
     'language': 'en', 'plan_id': 'VN-URB-METRO-2030', 'sector': 'Smart City'},
    {'q': '"Metro" OR "tàu điện ngầm" Hà Nội "Hồ Chí Minh" 2026',
     'language': 'vi', 'plan_id': 'VN-URB-METRO-2030', 'sector': 'Smart City'},
    {'q': 'Vietnam green industrial park eco-zone environmental technology 2026',
     'language': 'en', 'plan_id': 'VN-ENV-IND-1894', 'sector': 'Industrial Parks'},
    {'q': '"khu công nghiệp xanh" OR "công nghệ môi trường" Việt Nam 2026',
     'language': 'vi', 'plan_id': 'VN-ENV-IND-1894', 'sector': 'Industrial Parks'},
    {'q': 'Korea Vietnam cooperation energy infrastructure MOU 2026',
     'language': 'en', 'plan_id': '', 'sector': 'Bilateral', 'label': 'KR-VN-EN'},
    {'q': 'South Korea Vietnam nuclear power plant LNG offshore wind cooperation',
     'language': 'en', 'plan_id': '', 'sector': 'Power', 'label': 'KR-VN-ENERGY'},
    {'q': 'Korea Vietnam summit bilateral agreement environment infrastructure',
     'language': 'en', 'plan_id': '', 'sector': 'Bilateral', 'label': 'KR-VN-SUMMIT'},
    {'q': 'hàn quốc việt nam hợp tác năng lượng hạ tầng môi trường 2026',
     'language': 'vi', 'plan_id': '', 'sector': 'Bilateral', 'label': 'KR-VN-VI'},
    {'q': '"Ca Na" OR "Lien Chieu" OR "Can Gio port" Vietnam infrastructure',
     'language': 'en', 'plan_id': 'VN-TRAN-2055', 'sector': 'Transport', 'label': 'PROJ-PORT'},
    {'q': '"Ring Road 4" OR "Vanh dai 4" Ho Chi Minh City 2026',
     'language': 'en', 'plan_id': 'VN-TRAN-2055', 'sector': 'Transport', 'label': 'PROJ-RR4'},
    {'q': '"Ninh Thuan" nuclear power plant Russia Vietnam 2026',
     'language': 'en', 'plan_id': 'VN-PWR-PDP8-NUCLEAR', 'sector': 'Power', 'label': 'PROJ-NUCLEAR'},
    {'q': 'EVN PVN "offshore wind" Vietnam 2026 MW survey',
     'language': 'en', 'plan_id': 'VN-PWR-PDP8-RENEWABLE', 'sector': 'Power', 'label': 'EVN-PVN-WIND'},
    {'q': 'Vietnam "BOT" OR "PPP" infrastructure concession 2026',
     'language': 'en', 'plan_id': '', 'sector': 'Transport', 'label': 'BOT-PPP'},
    {'q': '"VSIP" OR "Stavian" OR "Amata" Vietnam industrial park FDI 2026',
     'language': 'en', 'plan_id': 'VN-IP-NORTH-2030', 'sector': 'Industrial Parks', 'label': 'IP-SPECIFIC'},
    {'q': 'Vietnam "green bond" OR "sustainable finance" infrastructure 2026',
     'language': 'en', 'plan_id': '', 'sector': 'Industrial Parks', 'label': 'GREEN-FIN'},
    {'q': '"Decision 768" OR "PDP VIII" Vietnam power revised offshore wind',
     'language': 'en', 'plan_id': 'VN-PWR-PDP8', 'sector': 'Power', 'label': 'PDP8-768'},
    {'q': '"cảng Liên Chiểu" OR "cảng Cần Giờ" OR "cảng Long Thành" hạ tầng',
     'language': 'vi', 'plan_id': 'VN-TRAN-2055', 'sector': 'Transport', 'label': 'VN-PORT'},
    {'q': '"điện hạt nhân" "Ninh Thuận" Nga Việt Nam 2026',
     'language': 'vi', 'plan_id': 'VN-PWR-PDP8-NUCLEAR', 'sector': 'Power', 'label': 'VN-NUCLEAR'},
]

NEWSDATA_PROVINCE_QUERIES = {
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
    'group_c': [
        {'q': '"Ninh Thuan" OR "Ninh Thuận" wind solar energy 2026',
         'language': 'en', 'province': 'Ninh Thuan'},
        {'q': '"Khanh Hoa" OR "Khánh Hòa" infrastructure 2026',
         'language': 'en', 'province': 'Khanh Hoa'},
        {'q': '"Long An" industrial OR wastewater 2026',
         'language': 'en', 'province': 'Long An'},
    ],
}

NEWSDATA_KOREAN_ODA_QUERIES = [
    {'q': 'KOICA Vietnam water sanitation infrastructure development',
     'language': 'en', 'sector': 'Water Supply/Drainage', 'label': 'KOICA-WAT'},
    {'q': 'KEITI environmental technology export Vietnam',
     'language': 'en', 'sector': 'Solid Waste', 'label': 'KEITI-ENV'},
    {'q': 'Korean construction company Vietnam contract award infrastructure',
     'language': 'en', 'sector': 'Transport', 'label': 'ICAK-CONST'},
    {'q': 'Korea ODA Vietnam infrastructure development project',
     'language': 'en', 'sector': 'Bilateral', 'label': 'KR-ODA-INFRA'},
    {'q': 'Korea international cooperation Vietnam environment water energy',
     'language': 'en', 'sector': 'Bilateral', 'label': 'KR-COOP-ENV'},
]

NEWSDATA_MDB_QUERIES = [
    {'q': 'ADB Vietnam infrastructure loan project approval',
     'language': 'en', 'sector': 'Transport', 'label': 'ADB-INFRA'},
    {'q': 'World Bank Vietnam water sanitation environment project',
     'language': 'en', 'sector': 'Waste Water', 'label': 'WB-WAT'},
    {'q': 'AIIB Vietnam energy infrastructure investment',
     'language': 'en', 'sector': 'Power', 'label': 'AIIB-ENERGY'},
    {'q': 'JICA Vietnam ODA infrastructure grant loan',
     'language': 'en', 'sector': 'Water Supply/Drainage', 'label': 'JICA-ODA'},
    {'q': 'GIZ Vietnam environment sustainable development',
     'language': 'en', 'sector': 'Solid Waste', 'label': 'GIZ-ENV'},
]

NEWSDATA_QUERIES = NEWSDATA_SECTOR_QUERIES + NEWSDATA_MASTER_QUERIES


# ══════════════════════════════════════════════════════════════════════════
#  fetch_newsdata() — v8.4 그대로 유지
# ══════════════════════════════════════════════════════════════════════════
def fetch_newsdata(api_key: str, hours_back: int = 24) -> list:
    if not api_key:
        log.warning('[NewsData.io] API 키 없음 — 건너뜀')
        return []

    API_URL    = 'https://newsdata.io/api/1/latest'
    CREDIT_MAX = 190
    SIZE       = 5

    credit_used      = 0
    articles         = []
    seen_urls        = set()
    credit_exhausted = False

    today       = datetime.now()
    day_odd     = today.day % 2 == 1
    day_mon_thu = today.weekday() in (0, 3)

    def call_api(q, lang, size=SIZE):
        nonlocal credit_used, credit_exhausted

        if credit_exhausted or credit_used >= CREDIT_MAX:
            return []

        params = {
            'apikey':   api_key,
            'country':  'vn',
            'language': lang,
            'q':        q,
            'size':     size,
        }

        try:
            resp = requests.get(API_URL, params=params, timeout=15)

            if resp.status_code == 422:
                log.warning(f'[NewsData.io] 422 오류 — q={q[:40]}')
                return []

            if resp.status_code == 429:
                credit_exhausted = True
                log.warning(
                    '[NewsData.io] 429 크레딧 소진 — NewsData 수집 중단 '
                    '(RSS 수집 결과로 계속 진행, 자정 KST 리셋 후 정상화)'
                )
                return []

            resp.raise_for_status()
            data = resp.json()
            credit_used += 1
            return data.get('results', [])

        except requests.exceptions.Timeout:
            log.warning(f'[NewsData.io] 타임아웃 — q={q[:40]}')
            return []
        except Exception as e:
            log.warning(f'[NewsData.io] 오류: {e}')
            return []

    def parse_result(raw, sector='', plan_id='', province=''):
        url = (raw.get('link') or raw.get('url') or '').strip()
        if not url or url in seen_urls:
            return None
        seen_urls.add(url)

        pub_date = (raw.get('pubDate') or raw.get('publishedAt') or '')[:10]
        if not pub_date:
            pub_date = datetime.now().strftime('%Y-%m-%d')

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

        ok, reason = should_collect(title, desc, source)
        if not ok:
            return None

        inferred_sector = sector if sector else _infer_sector_from_title(title, desc)

        return {
            'title':          title,
            'summary':        desc,
            'url':            url,
            'source':         source,
            'date':           pub_date,
            'published_date': pub_date,
            'sector':         inferred_sector,
            'province':       province,
            'plan_id':        plan_id,
            'collector':      'newsdata_io',
            'ctx_grade':      'MEDIUM',
            'ctx_plans':      plan_id if plan_id else '',
        }

    # ── A: 섹터 기본 쿼리 ────────────────────────────────────────────
    log.info('[NewsData.io] 방법1-A: 섹터 기본 쿼리')
    for q_info in NEWSDATA_SECTOR_QUERIES:
        if credit_exhausted or credit_used >= CREDIT_MAX: break
        results = call_api(q_info['q'], q_info['language'])
        for raw in results:
            parsed = parse_result(raw, sector=q_info.get('sector', ''))
            if parsed: articles.append(parsed)
        time.sleep(0.3)

    # ── B: 마스터플랜 전용 쿼리 ──────────────────────────────────────
    log.info('[NewsData.io] 방법1-B: 마스터플랜 쿼리')
    for q_info in NEWSDATA_MASTER_QUERIES:
        if credit_exhausted or credit_used >= CREDIT_MAX: break
        results = call_api(q_info['q'], q_info['language'])
        for raw in results:
            parsed = parse_result(raw, sector=q_info.get('sector', ''),
                                  plan_id=q_info.get('plan_id', ''))
            if parsed: articles.append(parsed)
        time.sleep(0.3)

    # ── C-A: Province Group A ─────────────────────────────────────────
    log.info('[NewsData.io] 방법1-C: Province Group A')
    for q_info in NEWSDATA_PROVINCE_QUERIES['group_a']:
        if credit_exhausted or credit_used >= CREDIT_MAX: break
        results = call_api(q_info['q'], q_info['language'])
        for raw in results:
            parsed = parse_result(raw, province=q_info.get('province', ''))
            if parsed: articles.append(parsed)
        time.sleep(0.3)

    # ── C-B: Province Group B (홀수일) ───────────────────────────────
    if day_odd and not credit_exhausted:
        log.info('[NewsData.io] 방법1-C: Province Group B (홀수일)')
        for q_info in NEWSDATA_PROVINCE_QUERIES['group_b']:
            if credit_exhausted or credit_used >= CREDIT_MAX: break
            results = call_api(q_info['q'], q_info['language'])
            for raw in results:
                parsed = parse_result(raw, province=q_info.get('province', ''))
                if parsed: articles.append(parsed)
            time.sleep(0.3)

    # ── C-C: Province Group C (월·목) ────────────────────────────────
    if day_mon_thu and not credit_exhausted:
        log.info('[NewsData.io] 방법1-C: Province Group C (월·목)')
        for q_info in NEWSDATA_PROVINCE_QUERIES['group_c']:
            if credit_exhausted or credit_used >= CREDIT_MAX: break
            results = call_api(q_info['q'], q_info['language'])
            for raw in results:
                parsed = parse_result(raw, province=q_info.get('province', ''))
                if parsed: articles.append(parsed)
            time.sleep(0.3)

    # ── D: 한국 ODA 기관 쿼리 (홀수일) ──────────────────────────────
    if day_odd and not credit_exhausted:
        log.info('[NewsData.io] 방법1-D: 한국 ODA 기관 베트남 뉴스 (홀수일)')
        for q_info in NEWSDATA_KOREAN_ODA_QUERIES:
            if credit_exhausted or credit_used >= CREDIT_MAX: break
            results = call_api(q_info['q'], q_info['language'])
            for raw in results:
                parsed = parse_result(raw, sector=q_info.get('sector', 'Bilateral'),
                                      plan_id=q_info.get('plan_id', ''))
                if parsed: articles.append(parsed)
            time.sleep(0.3)

    # ── E: 국제개발금융기관 베트남 인프라 (짝수일) ───────────────────
    if not day_odd and not credit_exhausted:
        log.info('[NewsData.io] 방법1-E: 국제개발금융 베트남 인프라 (짝수일)')
        for q_info in NEWSDATA_MDB_QUERIES:
            if credit_exhausted or credit_used >= CREDIT_MAX: break
            results = call_api(q_info['q'], q_info['language'])
            for raw in results:
                parsed = parse_result(raw, sector=q_info.get('sector', 'Bilateral'),
                                      plan_id=q_info.get('plan_id', ''))
                if parsed: articles.append(parsed)
            time.sleep(0.3)

    if credit_exhausted:
        log.warning(
            f'[NewsData.io] 크레딧 소진으로 조기 종료 — '
            f'{len(articles)}건 수집 / {credit_used} 크레딧 사용'
        )
    else:
        log.info(
            f'[NewsData.io] 완료 — {len(articles)}건 / '
            f'{credit_used}/{CREDIT_MAX} 크레딧'
        )
    return articles


# ══════════════════════════════════════════════════════════════════════════
#  메인 수집 함수 (v8.4 그대로)
# ══════════════════════════════════════════════════════════════════════════
def collect_news(hours_back: int = 24) -> list:
    log.info(f'=== 뉴스 수집 시작 (hours_back={hours_back}) ===')

    rss_articles = fetch_rss_articles(hours_back)

    api_key     = os.getenv('NEWSDATA_API_KEY', '')
    nd_articles = fetch_newsdata(api_key, hours_back)

    all_articles = rss_articles + nd_articles
    seen         = set()
    unique_articles = []
    for art in all_articles:
        url = art.get('url', '')
        if url and url not in seen:
            seen.add(url)
            unique_articles.append(art)

    for art in unique_articles:
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
    hours    = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    articles = collect_news(hours_back=hours)
    print(f'\n수집 결과: {len(articles)}건')
    for i, art in enumerate(articles[:5], 1):
        print(f'  [{i}] {art["date"]} | {art["source"]} | {art["title"][:60]}')
    if len(articles) > 5:
        print(f'  ... 외 {len(articles) - 5}건')
