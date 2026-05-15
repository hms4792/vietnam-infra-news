"""
news_collector.py  — v8.7
==========================
베트남 인프라 뉴스 수집기

v8.7 변경사항 (2026-05-15):
  ★ 변경 1: VnExpress RSS 기존 피드 복원
    [경위] v8.6에서 카테고리 피드(environment/economy/traffic.rss)로 교체
    [확인] 5/15 워크플로우: 3개 피드 모두 빈피드(GitHub Actions IP 차단)
    [복원] news.rss + business.rss 복원
    [보완] ExcelUpdater v4.0 Vietnam 필터로 무관기사 DB 삽입 단계 차단

  ★ 변경 2: 방법D/E 쿼리 재설계 (한국기관·국제기관)
    [문제] 5/11~5/15 방법D 3회, 방법E 2회 실행 → 수집 0건
    [원인] 베트남 언론은 KOICA/ADB 약어를 거의 사용 안 함
           → 기관 약어 중심 쿼리가 country=vn 기사에 히트 안 됨
    [방법D 재설계] DB 실제 수집 기사 패턴 분석 결과 적용:
           'KOICA Vietnam water' → 'South Korea Vietnam nuclear power cooperation'
           'KEITI environmental' → 'Korean company Vietnam water environment project'
           베트남어 쿼리 신규: 'Hàn Quốc đầu tư hợp tác Việt Nam hạ tầng'
    [방법E 재설계] 약어→풀네임 전환 + 베트남어 패턴 추가:
           'ADB Vietnam loan' → 'Asian Development Bank Vietnam infrastructure billion'
           베트남어 신규: 'vốn vay ADB World Bank Việt Nam hạ tầng'
    [효과] 수집 0건 → 주 2~5건 목표

  ★ v8.6 유지사항:
    - 방법D 실행 순서: A(14크레딧) 직후 → 19크레딧 시점 완료 보장
    - NOISE_PATTERNS 50개 (v8.5)
    - EXCLUDE_EXACT (v8.5)
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
#  RSS 소스 목록
#  ★ v8.6: VnExpress 종합(news/business) → 카테고리 특화(environment/economy/traffic)
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

    # ── ★ v8.7: VnExpress 카테고리 RSS 차단 확인(5/15) → 기존 피드 복원 ──
    # environment/economy/traffic.rss → GitHub Actions 미국IP 403차단 확인
    # 무관기사는 ExcelUpdater v4.0 Vietnam 필터로 DB 삽입 단계에서 차단
    'VnExpress International': 'https://e.vnexpress.net/rss/news.rss',
    'VnExpress Business':      'https://e.vnexpress.net/rss/business.rss',

    # ── 수자원 / 환경 베트남어 ─────────────────────────────────────────
    'Bao Tai nguyen (VN)':     'https://baotainguyenmoitruong.vn/rss/home.rss',

    # ── v8.4: 국제개발금융·한국 ODA 베트남 관련 RSS ────────────────────
    # GitHub Actions 미국 IP에서 전부 빈 피드(403 차단)
    # → 방법1-D/E NewsData.io 쿼리로 우회 수집
    'ADB Vietnam':             'https://www.adb.org/news/rss.xml',
    'World Bank VN News':      'https://feeds.worldbank.org/en/rss/vietnam',
    'AIIB News':               'https://www.aiib.org/en/news-events/rss.xml',
    'GIZ Press':               'https://www.giz.de/en/newsroom/rss.xml',
    'Vietnam Briefing':        'https://www.vietnam-briefing.com/news/feed',
    'Mekong Eye':              'https://mekongeye.com/feed/',
    'Water World News':        'https://www.waterworld.com/rss.xml',
}

# ══════════════════════════════════════════════════════════════════════════
#  섹터 키워드 (v8.5 그대로)
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
#  노이즈 필터 (v8.5 그대로 — 50개)
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

    # ── v8.5 신규 패턴 (21개) ─────────────────────────────────────────
    r'\bruby\b', r'\bdiamonds?\b', r'\bcasino\b', r'\blottery\b',
    r'\besport\b', r'\bgaming\b', r'\bIPL\b', r'\bcricket\b',
    r'\bfifa\b', r'\bolympic\b',
    r'\bactor\b', r'\bsinger\b', r'\binfluencer\b',
    r'\brobotaxi\b', r'\bgame developer\b', r'\bgame studio\b',
    r'\bpsychonauts\b',
    r'\bkeralam\b', r'\bcpi\(m\)\b', r'\bpinarayi\b',
    r'\bnobitex\b', r'\bofac blacklist\b',
    # v8.5 추가 (5/11 신규 발견 유형)
    r'\bhantavirus\b', r'\bwild bird\b', r'\bmigratory bird\b',
    r'\bdurian\b', r'\bmorning digest\b', r'\bdaily digest\b',
    r'\bnetanyahu\b', r'\btrump iran\b',
    r'\bamazon seller\b', r'\bhubei dinglong\b',
]

# ══════════════════════════════════════════════════════════════════════════
#  EXCLUDE_EXACT (v8.5 그대로)
# ══════════════════════════════════════════════════════════════════════════
EXCLUDE_EXACT = [
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
    # v8.5 추가 (5/11 로그 기반)
    'hantavirus', 'wild bird', 'migratory bird', 'bảo vệ chim',
    'durian price', 'fruit price', 'durian export',
    'morning digest', 'daily digest', 'evening digest',
    'netanyahu', 'trump iran', 'iran peace', 'israel us military',
    'amazon seller', 'amazon empowering',
    'hubei dinglong', 'semiconductor materials supplier',
    'ghg emissions intensity', 'esg report 2025',
]

VIETNAM_KEYWORDS = [
    'vietnam', 'viet nam', 'việt nam', 'hanoi', 'ha noi', 'hà nội',
    'ho chi minh', 'hcmc', 'hà nội', 'saigon', 'sài gòn',
    'mekong', 'haiphong', 'hải phòng', 'danang', 'đà nẵng',
]


# ══════════════════════════════════════════════════════════════════════════
#  제목 기반 sector 추론 (v8.5 그대로)
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
#  should_collect() (v8.5 그대로)
# ══════════════════════════════════════════════════════════════════════════
def should_collect(title: str, summary: str = '', source: str = '') -> tuple:
    text = (title + ' ' + summary).lower()

    if len(title.strip()) < 10:
        return False, 'TITLE_TOO_SHORT'

    # v8.5: EXCLUDE_EXACT 즉시 제외
    title_lower = title.lower()
    for exc in EXCLUDE_EXACT:
        if exc.lower() in title_lower:
            return False, f'EXCLUDE_EXACT:{exc[:30]}'

    # NOISE_PATTERNS 체크
    for pat in NOISE_PATTERNS:
        if re.search(pat, text, re.IGNORECASE):
            return False, f'NOISE:{pat}'

    # ODA 소스 베트남 필터 완화
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
#  RSS 수집 (v8.5 그대로)
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
#  NEWSDATA 쿼리 목록 (v8.5 그대로)
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

# ── 한국 ODA 기관 쿼리 (방법1-D) ─────────────────────────────────────
# ★ v8.6: 실행 순서를 방법A 직후로 이동하여 크레딧 소진 전 반드시 실행
# ★ v8.7: 방법D 쿼리 재설계
# 문제: 'KOICA'/'KEITI' 단독 단어 → 베트남 언론이 기관 약어 거의 사용 안 함
#       → 5/11~5/15 3회 실행에도 수집 0건
# 해결: DB 실제 수집 기사 패턴 분석 후 재설계
#       ① 'South Korea' + 'Vietnam' + 섹터 맥락 조합
#       ② 베트남어 보도 패턴 ('Hàn Quốc' + '협력/투자')
#       ③ 기관 약어 대신 실제 보도 키워드 사용
NEWSDATA_KOREAN_ODA_QUERIES = [
    # ① 한-베 핵심 협력 (원전/에너지) — 4/25 실제 수집 기사 패턴
    {'q': 'South Korea Vietnam nuclear power cooperation energy agreement',
     'language': 'en', 'sector': 'Power', 'label': 'KR-VN-NUCLEAR'},
    # ② 한국 기업 환경인프라 — The Investor 기사 패턴 (wastewater/recycling)
    {'q': 'Korean company Vietnam water wastewater environment infrastructure project',
     'language': 'en', 'sector': 'Waste Water', 'label': 'KR-VN-ENV'},
    # ③ 한-베 교통/도시인프라 — 4/22 Metro 기사 패턴
    {'q': 'South Korea Vietnam metro railway urban infrastructure supply',
     'language': 'en', 'sector': 'Transport', 'label': 'KR-VN-METRO'},
    # ④ 베트남어 보도 패턴 — 'Hàn Quốc' + 투자/협력 + 인프라 섹터
    {'q': 'Hàn Quốc đầu tư hợp tác Việt Nam hạ tầng nước năng lượng',
     'language': 'vi', 'sector': 'Bilateral', 'label': 'KR-VN-VI'},
    # ⑤ 한국 ODA 통합 — 'Korean' + 'ODA'/'grant' + 'billion' 정밀 조합
    {'q': 'Korean ODA grant loan Vietnam billion infrastructure industrial',
     'language': 'en', 'sector': 'Bilateral', 'label': 'KR-ODA-BROAD'},
]

# ── 국제개발금융기관 쿼리 (방법1-E) ─────────────────────────────────
# ★ v8.7: 방법E 쿼리 재설계
# 문제: 'ADB Vietnam...' → ADB 약어가 베트남 언론에 거의 안 나옴
#       5/12~5/14 2회 실행에도 수집 0건
# 해결: 기관 풀네임('Asian Development Bank') + 구체 맥락으로 정밀화
#       베트남어 ADB 차관 표현('vốn vay ADB') 추가
NEWSDATA_MDB_QUERIES = [
    # ① ADB 풀네임 — 5/4 실제 수집 기사("Vietnam regional bright spot: ADB") 패턴
    {'q': 'Asian Development Bank Vietnam infrastructure loan billion approved 2026',
     'language': 'en', 'sector': 'Transport', 'label': 'ADB-FULLNAME'},
    # ② WB 풀네임 — 구체 섹터(수자원/에너지) 결합
    {'q': 'World Bank Vietnam water energy transport infrastructure billion 2026',
     'language': 'en', 'sector': 'Waste Water', 'label': 'WB-FULLNAME'},
    # ③ AIIB/JICA 통합 — 약어 유지 (국제적으로 통용)
    {'q': 'AIIB JICA Vietnam renewable energy water infrastructure investment 2026',
     'language': 'en', 'sector': 'Power', 'label': 'AIIB-JICA'},
    # ④ 베트남어 국제기관 차관 패턴
    {'q': 'vốn vay ADB World Bank Việt Nam hạ tầng nước điện giao thông 2026',
     'language': 'vi', 'sector': 'Bilateral', 'label': 'MDB-VI'},
    # ⑤ 다자개발은행 통합 — 'multilateral'+'billion'+'Vietnam' 정밀 조합
    {'q': 'Vietnam multilateral development loan ODA billion project approved infrastructure',
     'language': 'en', 'sector': 'Bilateral', 'label': 'MDB-BROAD'},
]

NEWSDATA_QUERIES = NEWSDATA_SECTOR_QUERIES + NEWSDATA_MASTER_QUERIES


# ══════════════════════════════════════════════════════════════════════════
#  fetch_newsdata()
#  ★ v8.6 핵심 변경: 실행 순서 재배치
#    변경 전: A → B → C-A → C-B(홀) → C-C(월목) → D(홀) → E(짝)
#    변경 후: A → D(홀수일) → B → C-A → C-B(홀) → C-C(월목) → E(짝)
#    효과: D(한국ODA)가 19크레딧 시점에 확실히 실행됨
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

    # ── A: 섹터 기본 쿼리 (매일) — 14크레딧 ─────────────────────────
    log.info('[NewsData.io] 방법1-A: 섹터 기본 쿼리 (14크레딧)')
    for q_info in NEWSDATA_SECTOR_QUERIES:
        if credit_exhausted or credit_used >= CREDIT_MAX: break
        results = call_api(q_info['q'], q_info['language'])
        for raw in results:
            parsed = parse_result(raw, sector=q_info.get('sector', ''))
            if parsed: articles.append(parsed)
        time.sleep(0.3)

    # ── ★ D: 한국 ODA 기관 쿼리 (홀수일) — 방법A 직후로 이동 ─────────
    # v8.6 핵심: A(14크레딧) 소비 직후 D(5크레딧) 실행
    # → 19크레딧 시점에 D 완료 보장 (크레딧 소진 전)
    # → KOICA·KEITI·KIND·ICAK 관련 기사 수집 보장
    if day_odd and not credit_exhausted:
        log.info('[NewsData.io] 방법1-D: 한국 ODA 기관 베트남 뉴스 (홀수일) ★순서변경★')
        for q_info in NEWSDATA_KOREAN_ODA_QUERIES:
            if credit_exhausted or credit_used >= CREDIT_MAX: break
            results = call_api(q_info['q'], q_info['language'])
            for raw in results:
                parsed = parse_result(raw, sector=q_info.get('sector', 'Bilateral'),
                                      plan_id=q_info.get('plan_id', ''))
                if parsed: articles.append(parsed)
            time.sleep(0.3)
        log.info(f'[NewsData.io] 방법1-D 완료 — 누적 {credit_used}크레딧 사용')

    # ── B: 마스터플랜 전용 쿼리 (매일) — 30크레딧 ───────────────────
    log.info('[NewsData.io] 방법1-B: 마스터플랜 쿼리 (30크레딧)')
    for q_info in NEWSDATA_MASTER_QUERIES:
        if credit_exhausted or credit_used >= CREDIT_MAX: break
        results = call_api(q_info['q'], q_info['language'])
        for raw in results:
            parsed = parse_result(raw, sector=q_info.get('sector', ''),
                                  plan_id=q_info.get('plan_id', ''))
            if parsed: articles.append(parsed)
        time.sleep(0.3)

    # ── C-A: Province Group A (매일) — 7크레딧 ───────────────────────
    log.info('[NewsData.io] 방법1-C: Province Group A')
    for q_info in NEWSDATA_PROVINCE_QUERIES['group_a']:
        if credit_exhausted or credit_used >= CREDIT_MAX: break
        results = call_api(q_info['q'], q_info['language'])
        for raw in results:
            parsed = parse_result(raw, province=q_info.get('province', ''))
            if parsed: articles.append(parsed)
        time.sleep(0.3)

    # ── C-B: Province Group B (홀수일) — 5크레딧 ─────────────────────
    if day_odd and not credit_exhausted:
        log.info('[NewsData.io] 방법1-C: Province Group B (홀수일)')
        for q_info in NEWSDATA_PROVINCE_QUERIES['group_b']:
            if credit_exhausted or credit_used >= CREDIT_MAX: break
            results = call_api(q_info['q'], q_info['language'])
            for raw in results:
                parsed = parse_result(raw, province=q_info.get('province', ''))
                if parsed: articles.append(parsed)
            time.sleep(0.3)

    # ── C-C: Province Group C (월·목) — 3크레딧 ─────────────────────
    if day_mon_thu and not credit_exhausted:
        log.info('[NewsData.io] 방법1-C: Province Group C (월·목)')
        for q_info in NEWSDATA_PROVINCE_QUERIES['group_c']:
            if credit_exhausted or credit_used >= CREDIT_MAX: break
            results = call_api(q_info['q'], q_info['language'])
            for raw in results:
                parsed = parse_result(raw, province=q_info.get('province', ''))
                if parsed: articles.append(parsed)
            time.sleep(0.3)

    # ── E: 국제개발금융기관 (짝수일) — 5크레딧 ──────────────────────
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
#  메인 수집 함수 (v8.5 그대로)
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
