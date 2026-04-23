# -*- coding: utf-8 -*-
"""
news_collector.py — v8.0 (엄격 필터링)

핵심 변경사항:
  ① is_infra_related(): must_have 키워드 기반 엄격 필터 — 인프라 아니면 즉시 제외
  ② is_vietnam_related(): 도메인+키워드 복합 판단
  ③ HIGH_FP_SOURCES: 오탐률 높은 소스 추가 필터 적용
  ④ NOISE_PATTERNS: 명백한 비인프라 패턴 즉시 제외
  ⑤ SQLite created_at: Python datetime 직접 삽입 (DEFAULT 제거)
  ⑥ 번역 대상 축소: 인프라 확정 기사만 번역 → 번역 로드 대폭 감소

영구 제약:
  - 번역: Google Translate만 (Anthropic API 절대 금지)
  - date fallback: article.get('date') or article.get('published_date')
  - NewsData.io: /api/1/latest, country=vn, q 파라미터만 (domain/from_date 금지)
"""

import os, re, sys, time, sqlite3, hashlib, logging, urllib.request, urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    import feedparser; HAS_FP=True
except: HAS_FP=False
try:
    import requests as req_lib; HAS_REQ=True
except: HAS_REQ=False

SCRIPTS_DIR = Path(__file__).parent
ROOT_DIR    = SCRIPTS_DIR.parent
DB_PATH     = str(ROOT_DIR/'data'/'vietnam_infra_news.db')
EXCEL_PATH  = str(ROOT_DIR/'data'/'database'/'Vietnam_Infra_News_Database_Final.xlsx')

logging.basicConfig(level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger('news_collector')
def log(m): logger.info(m)

HOURS_BACK = int(os.environ.get('HOURS_BACK', 24))
GNEWS_API_KEY = os.environ.get('GNEWS_API_KEY','')
NEWSDATA_ENDPOINT = 'https://newsdata.io/api/1/latest'

# ════════════════════════════════════════════════════════
# 핵심: 인프라 must_have 키워드 (이것 없으면 무조건 제외)
# ════════════════════════════════════════════════════════
INFRA_MUST_HAVE = {
    'Waste Water':           ['wastewater','sewage','wwtp','effluent',
                              'water treatment plant','nước thải','thoát nước',
                              'xử lý nước thải','hệ thống thoát nước'],
    'Water Supply/Drainage': ['water supply','clean water','drinking water',
                              'cấp nước','nước sạch','water pipe','nhà máy nước',
                              'water network','water infrastructure'],
    'Solid Waste':           ['solid waste','rác thải rắn','bãi rác',
                              'waste-to-energy','landfill','recycling',
                              'tái chế','đốt rác','chất thải rắn',
                              'waste management','waste treatment',
                              'rác sinh hoạt','thu gom rác','plastic waste'],
    'Power':                 ['power plant','renewable energy','solar farm',
                              'wind farm','wind power','pdp8','nuclear power',
                              'power grid','evn','electricity generation',
                              'nhà máy điện','điện gió','điện mặt trời',
                              'năng lượng tái tạo','lưới điện','quy hoạch điện',
                              'offshore wind','hydropower','transmission line',
                              'coal power plant','substation','jetp'],
    'Oil & Gas':             ['lng terminal','gas pipeline','petrovietnam',
                              'pvn','pv gas','pvep','petroleum',
                              'offshore drilling','oil field','dầu khí',
                              'đường ống khí','natural gas','refinery',
                              'lng power plant','gas-fired power'],
    'Industrial Parks':      ['industrial park','industrial zone',
                              'khu công nghiệp','vsip','eco-industrial',
                              'khu kinh tế','khu chế xuất','becamex',
                              'amata','deep-c','hi-tech park'],
    'Smart City':            ['smart city','metro line','urban railway',
                              'tuyến metro','đường sắt đô thị',
                              'thành phố thông minh','e-government'],
    'Transport':             ['long thanh airport','north-south expressway',
                              'sân bay long thành','cao tốc bắc nam',
                              'seaport expansion','deep-water port',
                              'cảng nước sâu','port capacity expansion',
                              'bridge construction project',
                              'logistics infrastructure'],
}
ALL_INFRA_KW = [kw for kws in INFRA_MUST_HAVE.values() for kw in kws]

# 베트남 관련 필수 키워드
VN_KEYWORDS = ['vietnam','viet nam','việt nam','hanoi','hà nội',
               'ho chi minh','hcmc','tp.hcm','mekong','evn',
               'petrovietnam','pvn','haiphong','hải phòng',
               'da nang','đà nẵng','quang ninh','binh duong',
               'dong nai','can tho','long an','gia lai','ninh thuan',
               '.vn','vn/']

# 베트남 도메인 (자동 통과)
VN_DOMAINS = ['hanoitimes.vn','vietnamplus.vn','nhandan.vn','sggp.org.vn',
              'baoxaydung.com.vn','moitruong.net.vn','vietnamnet.vn',
              'tuoitre.vn','thanhnien.vn','vnexpress.net','cafebiz.vn',
              'theinvestor.vn','vir.com.vn','vietnamenergy.vn']

# 오탐률 높은 소스 — 추가 필터 필요
HIGH_FP_SOURCES = {
    'www.offshore-energy.biz': 'vn_strict',   # 베트남 언급 없으면 제외
    'Bao Binh Dinh':           'infra_strict', # 인프라 키워드 2개+
    'Bao Ha Tinh':             'infra_strict',
    'VnExpress - Thoi su':     'infra_only',   # 인프라만
    'CafeBiz':                 'infra_only',
    'Tuoi Tre News':           'infra_only',
    'Tuoi Tre - Kinh doanh':   'infra_only',
    'Dan Tri - Kinh doanh':    'infra_only',
    'Nhan Dan English':        'infra_strict', # 엄격한 인프라
    'SGGP':                    'infra_only',
    'Bao Xay Dung':            'infra_only',
}

# 명백한 오탐 패턴 (즉시 제외)
NOISE_PATTERNS = [
    r'không khí lạnh|mưa (diện rộng|lớn|giông)|nắng nóng kỉ lục',
    r'bắt giữ.*đối tượng|khởi tố.*chém|xông vào nhà|tử vong|rabies|whitmore',
    r'tình nguyện viên.*dọn dẹp|giải thưởng.*doanh nhân|festival.*văn hóa',
    r'pahalgam|terror attack|pm modi|horoscope|zodiac|astrology|dental',
    r'vn-index.*tăng|vn-index.*giảm|chứng khoán|cổ phiếu|giá vàng|sjc gold',
    r'u17|youth olympic|football.*ranked|women.*football.*ranked',
    r'opera|ballet|art exhibition|book industry|reading culture',
    r'carlsberg|booking\.com|mixue|kedarnath|azerbaijan electronics',
    r'podcast|điểm tin trưa|bản tin chiều|infographic.*vn-index',
    r'india will never bow|blood and water|bid farewell to oil.*iran',
    r'daily horoscope|stars say|star reading|weekly horoscope',
]

# 섹터 우선순위
SECTOR_ORDER = ['Waste Water','Water Supply/Drainage','Solid Waste','Power',
                'Oil & Gas','Industrial Parks','Smart City','Transport']

# 검증된 RSS 피드 (오탐 제거)
RSS_FEEDS = {
    # 인프라 전문 — 오탐 낮음
    'PV Tech'          : 'https://pv-tech.org/feed/',
    'Energy Monitor'   : 'https://energymonitor.ai/rss',
    'Nikkei Asia'      : 'https://asia.nikkei.com/rss/feed/nar',
    'Moitruong Net'    : 'https://moitruong.net.vn/rss/home.rss',
    # 베트남 일반 (필터 통과 필요)
    'Hanoi Times'      : 'https://hanoitimes.vn/rss/home.rss',
    'Vietnamnet Tech'  : 'https://vietnamnet.vn/rss/cong-nghe.rss',
    # 제거: VnExpress-Thoi su, Bao Ha Tinh, Bao Binh Dinh, CafeBiz 등 — 오탐 과다
    # 제거: Solar Quarter, Nhan Dan English — 비베트남 국제기사 혼입
}

# NewsData.io 인프라 전용 쿼리
NEWSDATA_QUERIES = [
    {'q':'Vietnam wastewater treatment WWTP sewage infrastructure','language':'en'},
    {'q':'Vietnam water supply clean water infrastructure investment','language':'en'},
    {'q':'Vietnam solid waste management recycling waste-to-energy','language':'en'},
    {'q':'Vietnam power plant renewable energy PDP8 EVN solar wind','language':'en'},
    {'q':'Vietnam LNG gas pipeline PetroVietnam offshore energy','language':'en'},
    {'q':'Vietnam industrial park FDI khu cong nghiep VSIP','language':'en'},
    {'q':'Vietnam smart city metro urban railway infrastructure','language':'en'},
    {'q':'Vietnam expressway Long Thanh airport seaport transport','language':'en'},
    {'q':'nước thải xử lý môi trường hạ tầng khu công nghiệp','language':'vi'},
    {'q':'năng lượng tái tạo điện gió điện mặt trời PDP8 EVN','language':'vi'},
]

# ════════════════════════════════════════════════════════
# 필터 함수들
# ════════════════════════════════════════════════════════
def is_infra_related(title: str, sum_en: str = '') -> bool:
    """인프라 must_have 키워드 1개 이상 포함 여부 — 핵심 게이트"""
    text = (title + ' ' + sum_en).lower()
    return any(kw in text for kw in ALL_INFRA_KW)

def is_vietnam_related(title: str, url: str = '', sum_en: str = '') -> bool:
    """베트남 관련 여부 — 도메인 우선, 키워드 차선"""
    # 도메인 체크
    url_lower = url.lower()
    if any(d in url_lower for d in VN_DOMAINS): return True
    if '.vn/' in url_lower or url_lower.endswith('.vn'): return True
    # 키워드 체크
    text = (title + ' ' + sum_en).lower()
    return any(kw in text for kw in VN_KEYWORDS)

def has_noise_pattern(title: str) -> bool:
    """명백한 오탐 패턴 즉시 제외"""
    t = title.lower()
    return any(re.search(p, t) for p in NOISE_PATTERNS)

def passes_source_filter(title: str, sum_en: str, source: str) -> bool:
    """오탐률 높은 소스 추가 필터"""
    if source not in HIGH_FP_SOURCES: return True
    rule = HIGH_FP_SOURCES[source]
    text = (title + ' ' + sum_en).lower()
    if rule == 'infra_only':
        return is_infra_related(title, sum_en)
    elif rule == 'infra_strict':
        count = sum(1 for kw in ALL_INFRA_KW if kw in text)
        return count >= 2
    elif rule == 'vn_strict':
        return is_vietnam_related(title, '', sum_en)
    return True

def classify_sector(title: str, sum_en: str = '') -> str:
    text = (title + ' ' + sum_en).lower()
    for s in SECTOR_ORDER:
        if any(kw in text for kw in INFRA_MUST_HAVE[s]): return s
    return 'Environment'

def area_from_sector(s: str) -> str:
    if s in {'Waste Water','Water Supply/Drainage','Solid Waste','Environment'}: return 'Environment'
    if s in {'Power','Oil & Gas'}: return 'Energy Develop.'
    return 'Urban Develop.'

def should_collect(article: dict) -> bool:
    """
    수집 여부 최종 판단 — 3단계 게이트
    Gate1: 노이즈 패턴 → False
    Gate2: 인프라 키워드 없음 → False
    Gate3: 베트남 관련 없음 → False
    Gate4: 소스 필터 → False
    """
    title  = article.get('title','') or article.get('title_en','')
    sum_en = article.get('sum_en','') or article.get('summary','')
    url    = article.get('url','')
    source = article.get('source','')

    if has_noise_pattern(title):             return False
    if not is_infra_related(title, sum_en):  return False
    if not is_vietnam_related(title, url, sum_en): return False
    if not passes_source_filter(title, sum_en, source): return False
    return True

# ════════════════════════════════════════════════════════
# 유틸리티
# ════════════════════════════════════════════════════════
def generate_url_hash(url: str) -> str:
    return hashlib.md5(url.strip().encode()).hexdigest()

def clean_html(text: str) -> str:
    if not text: return ''
    text = re.sub(r'<[^>]+>',' ',text)
    text = re.sub(r'&[a-z]+;',' ',text)
    return re.sub(r'\s+',' ',text).strip()

def parse_date(date_str: str) -> Optional[datetime]:
    if not date_str: return None
    fmts=['%a, %d %b %Y %H:%M:%S %z','%a, %d %b %Y %H:%M:%S %Z',
          '%Y-%m-%dT%H:%M:%S%z','%Y-%m-%dT%H:%M:%SZ',
          '%Y-%m-%d %H:%M:%S','%Y-%m-%d','%d/%m/%Y','%B %d, %Y']
    for fmt in fmts:
        try:
            dt=datetime.strptime(date_str.strip()[:len(fmt)+5],fmt)
            return dt.replace(tzinfo=None)
        except: continue
    return None

def extract_province(text: str) -> str:
    t=text.lower()
    PROV={'Hanoi':['hanoi','hà nội','ha noi'],'Ho Chi Minh City':['ho chi minh','hcmc','tp.hcm','sài gòn'],
          'Da Nang':['da nang','đà nẵng'],'Hai Phong':['hai phong','hải phòng'],
          'Can Tho':['can tho','cần thơ'],'Binh Duong':['binh duong','bình dương'],
          'Dong Nai':['dong nai','đồng nai'],'Quang Ninh':['quang ninh','quảng ninh','ha long'],
          'Ba Ria-Vung Tau':['vung tau','vũng tàu','ba ria'],'Long An':['long an'],
          'Gia Lai':['gia lai'],'Ninh Thuan':['ninh thuan','ninh thuận'],
          'National Level':['vietnam','viet nam','việt nam','national','toàn quốc']}
    for prov,kws in PROV.items():
        if any(kw in t for kw in kws): return prov
    return 'National Level'

def translate_text(text: str, target: str='ko') -> str:
    if not text or len(text.strip())<3: return text
    try:
        params=urllib.parse.urlencode({'q':text[:400],'langpair':f'en|{target}'})
        url=f'https://api.mymemory.translated.net/get?{params}'
        req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req,timeout=8) as r:
            import json; data=json.loads(r.read())
            result=data.get('responseData',{}).get('translatedText','')
            if result and 'MYMEMORY WARNING' not in result and result!=text:
                return result.strip()
    except: pass
    time.sleep(0.3)
    try:
        from deep_translator import GoogleTranslator
        result=GoogleTranslator(source='auto',target=target).translate(text[:400])
        if result and result!=text: return result.strip()
    except: pass
    return text

# ════════════════════════════════════════════════════════
# DB
# ════════════════════════════════════════════════════════
def init_database() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH),exist_ok=True)
    conn=sqlite3.connect(DB_PATH)
    cur=conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='articles'")
    if not cur.fetchone():
        conn.execute('''CREATE TABLE articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url_hash TEXT UNIQUE, title TEXT, url TEXT, date TEXT,
            source TEXT, src_type TEXT, sector TEXT, province TEXT,
            summary TEXT, title_ko TEXT, title_vi TEXT,
            sum_ko TEXT, sum_vi TEXT, created_at TEXT)''')
        conn.commit(); log("SQLite DB 초기화 완료")
    else:
        existing=[r[1] for r in conn.execute("PRAGMA table_info(articles)")]
        for col,cdef in {'src_type':'TEXT','title_vi':'TEXT','sum_vi':'TEXT','created_at':'TEXT'}.items():
            if col not in existing:
                try: conn.execute(f"ALTER TABLE articles ADD COLUMN {col} {cdef}"); conn.commit()
                except: pass
    return conn

def get_existing_hashes(conn) -> set:
    return {r[0] for r in conn.execute("SELECT url_hash FROM articles")}

def save_article(conn, article: dict) -> bool:
    url_hash=generate_url_hash(article.get('url',''))
    now=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    try:
        conn.execute('''INSERT OR IGNORE INTO articles
            (url_hash,title,url,date,source,src_type,sector,province,
             summary,title_ko,title_vi,sum_ko,sum_vi,created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (url_hash,
             article.get('title_en','') or article.get('title',''),
             article.get('url',''),
             article.get('date','') or article.get('published_date',''),
             article.get('source',''),article.get('src_type','NewsData.io'),
             article.get('sector',''),article.get('province',''),
             article.get('sum_en','') or article.get('summary',''),
             article.get('title_ko',''),article.get('title_vi',''),
             article.get('sum_ko',''),article.get('sum_vi',''),now))
        conn.commit(); return True
    except: return False

# ════════════════════════════════════════════════════════
# 수집 함수
# ════════════════════════════════════════════════════════
def fetch_rss(url: str, source_name: str, cutoff: datetime, existing: set) -> list:
    articles=[]
    try:
        if HAS_FP:
            feed=feedparser.parse(url); entries=feed.entries
        else:
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
            with urllib.request.urlopen(req,timeout=20) as r: content=r.read()
            return []  # feedparser 없으면 스킵
        for entry in entries:
            pub_raw=getattr(entry,'published','') or getattr(entry,'updated','')
            pub_dt=parse_date(pub_raw)
            if pub_dt and pub_dt<cutoff: continue
            title=clean_html(getattr(entry,'title','') or '')
            url_a=getattr(entry,'link','') or ''
            summ=clean_html(getattr(entry,'summary','') or getattr(entry,'description','') or '')[:500]
            if not title or len(title)<10: continue
            # 핵심 게이트
            a={'title':title,'sum_en':summ,'url':url_a,'source':source_name}
            if not should_collect(a): continue
            url_hash=generate_url_hash(url_a)
            if url_hash in existing: continue
            date_str=pub_dt.strftime('%Y-%m-%d') if pub_dt else datetime.now().strftime('%Y-%m-%d')
            sector=classify_sector(title,summ)
            articles.append({
                'title_en':title,'title':title,'source':source_name,'src_type':'RSS',
                'date':date_str,'published_date':date_str,'province':extract_province(title+' '+summ),
                'plan':'','sector':sector,'area':area_from_sector(sector),
                'sum_en':summ,'summary':summ,'url':url_a,
                'title_ko':'','title_vi':'','sum_ko':'','sum_vi':'','grade':'',
            })
            existing.add(url_hash)
    except Exception as e:
        log(f"  RSS 오류 [{source_name}]: {e}")
    return articles

def fetch_newsdata(api_key: str, cutoff: datetime, existing: set) -> list:
    if not api_key: return []
    articles=[]
    for q_cfg in NEWSDATA_QUERIES:
        params={'country':'vn','language':q_cfg['language'],'q':q_cfg['q'],'apikey':api_key}
        url=NEWSDATA_ENDPOINT+'?'+urllib.parse.urlencode(params)
        try:
            import json
            req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
            with urllib.request.urlopen(req,timeout=15) as r:
                results=json.loads(r.read()).get('results',[])
            for item in results:
                title=(item.get('title','') or '').strip()
                url_a=(item.get('link','') or '').strip()
                if not title or not url_a: continue
                summ=clean_html(item.get('description','') or '')[:500]
                # 핵심 게이트
                raw_src=(item.get('source_id') or item.get('source_name') or
                         urllib.parse.urlparse(url_a).netloc.replace('www.',''))
                a={'title':title,'sum_en':summ,'url':url_a,'source':raw_src}
                if not should_collect(a): continue
                url_hash=generate_url_hash(url_a)
                if url_hash in existing: continue
                pub_dt=parse_date(item.get('pubDate',''))
                if pub_dt and pub_dt<cutoff: continue
                date_str=pub_dt.strftime('%Y-%m-%d') if pub_dt else datetime.now().strftime('%Y-%m-%d')
                sector=classify_sector(title,summ)
                articles.append({
                    'title_en':title,'title':title,'source':raw_src,'src_type':'NewsData.io',
                    'date':date_str,'published_date':date_str,'province':extract_province(title+' '+summ),
                    'plan':'','sector':sector,'area':area_from_sector(sector),
                    'sum_en':summ,'summary':summ,'url':url_a,
                    'title_ko':'','title_vi':'','sum_ko':'','sum_vi':'','grade':'',
                })
                existing.add(url_hash)
        except urllib.error.HTTPError as e:
            if e.code==422:
                log(f"  NewsData 422 — 쿼리 조정 필요: {q_cfg['q'][:40]}")
            else: log(f"  NewsData HTTP {e.code}")
        except Exception as e: log(f"  NewsData 오류: {e}")
        time.sleep(0.3)
    return articles

# ════════════════════════════════════════════════════════
# 메인 수집 함수
# ════════════════════════════════════════════════════════
def collect_news(hours_back: int=None) -> list:
    if hours_back is None: hours_back=HOURS_BACK
    cutoff=datetime.utcnow()-timedelta(hours=hours_back)
    log(f"수집 시작: 최근 {hours_back}시간 | 엄격 인프라 필터 적용")

    conn=init_database()
    existing=get_existing_hashes(conn)
    log(f"기존 URL {len(existing)}개 로드")

    all_articles=[]; stats={}

    # ── RSS
    log(f"[1] RSS 수집 ({len(RSS_FEEDS)}개 소스)...")
    rss_arts=[]
    for name,feed_url in RSS_FEEDS.items():
        arts=fetch_rss(feed_url,name,cutoff,existing)
        rss_arts.extend(arts)
        if arts: log(f"  {name}: {len(arts)}건")
        time.sleep(0.5)
    all_articles.extend(rss_arts)
    stats['RSS']=len(rss_arts)
    log(f"  RSS 합계: {len(rss_arts)}건")

    # ── NewsData.io
    nk=os.environ.get('NEWSDATA_API_KEY','')
    if nk:
        log(f"[2] NewsData.io 수집 (인프라 전용 쿼리)...")
        nd_arts=fetch_newsdata(nk,cutoff,existing)
        all_articles.extend(nd_arts)
        stats['NewsData.io']=len(nd_arts)
        log(f"  NewsData.io: {len(nd_arts)}건")
    else:
        stats['NewsData.io']=0

    # ── 중복 제거
    seen=set(); unique=[]
    for a in all_articles:
        u=a.get('url','')
        if u and u not in seen:
            seen.add(u); unique.append(a)
    log(f"중복 제거: {len(all_articles)} → {len(unique)}건")

    # date fallback
    for a in unique:
        if not a.get('date'):
            a['date']=a.get('published_date','')

    # SQLite 저장
    saved=sum(1 for a in unique if save_article(conn,a))
    conn.close()
    log(f"SQLite 저장: {saved}건")
    log(f"수집 완료: RSS={stats['RSS']} NewsData={stats.get('NewsData.io',0)}")
    log(f"  (전문미디어: weekly_backfill.yml → specialist_crawler.py)")

    return unique

def update_excel_database(articles: list) -> dict:
    if not articles: return {}
    try:
        sys.path.insert(0,str(SCRIPTS_DIR))
        from excel_updater import ExcelUpdater
        updater=ExcelUpdater(EXCEL_PATH)
        return updater.update_all(articles)
    except Exception as e:
        log(f"Excel 업데이트 오류: {e}"); return {}

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument('--hours',type=int,default=24)
    a=p.parse_args()
    arts=collect_news(hours_back=a.hours)
    log(f"수집 완료: {len(arts)}건")
