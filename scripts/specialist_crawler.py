#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
specialist_crawler.py  v2.0
전문 인프라 미디어 소급 크롤링 스크립트
대상: theinvestor.vn / vir.com.vn / hanoitimes.vn

v2.0 수정사항 (2026-03-30):
  - theinvestor.vn: /category/ → /tag/ URL 변경, 링크 패턴 수정
  - vir.com.vn: 500 오류 URL 수정, 검색 방식으로 전환
  - hanoitimes.vn: tag + search URL 추가, 날짜 추출 강화
  - 전체: 인프라 키워드 사전 필터로 불필요 기사 제거

[실행] python3 scripts/specialist_crawler.py --from-date 2025-01-01
       python3 scripts/specialist_crawler.py --from-date 2025-01-01 --dry-run
       python3 scripts/specialist_crawler.py --from-date 2025-01-01 --sites investor
"""

import os, sys, re, time, hashlib, argparse
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
try:
    from news_collector import (
        classify_sector, extract_province, is_vietnam_related,
        generate_url_hash, translate_articles, update_excel_database,
        init_database, save_article, get_existing_hashes, log,
        EXCEL_PATH, DB_PATH,
    )
    PIPELINE_AVAILABLE = True
except ImportError as e:
    print(f"[경고] news_collector 임포트 실패: {e}")
    PIPELINE_AVAILABLE = False
    def log(msg): print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {msg}")
    EXCEL_PATH = os.environ.get('EXCEL_PATH', 'data/database/Vietnam_Infra_News_Database_Final.xlsx')
    DB_PATH    = os.environ.get('DB_PATH', 'data/vietnam_infrastructure_news.db')
    def generate_url_hash(url): 
        import hashlib; return hashlib.md5(url.encode()).hexdigest()

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0',
    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Connection': 'keep-alive',
}
REQUEST_DELAY = 2.0
MAX_PAGES     = 10
TIMEOUT       = 20
MIN_TITLE_LEN = 20

# 인프라 관련 키워드 사전 필터 — 분류 전 1차 필터링
INFRA_KEYWORDS = [
    'infrastructure', 'wastewater', 'water supply', 'drainage', 'flood',
    'power plant', 'solar', 'wind farm', 'energy', 'electricity', 'grid',
    'oil', 'gas', 'lng', 'petroleum', 'pipeline',
    'industrial park', 'industrial zone', 'economic zone', 'fdi',
    'transport', 'expressway', 'highway', 'metro', 'railway', 'airport', 'port',
    'solid waste', 'landfill', 'recycling', 'waste-to-energy',
    'smart city', 'urban development', 'construction', 'housing',
    'nước thải', 'điện', 'khu công nghiệp', 'cao tốc', 'cảng', 'rác thải',
]

def is_infra_related(title, summary=''):
    """인프라 관련 기사인지 1차 필터링"""
    text = (title + ' ' + summary).lower()
    return any(kw in text for kw in INFRA_KEYWORDS)

def get_html(url, retry=2):
    """HTTP GET with retry"""
    for attempt in range(retry + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.text
            if r.status_code in (404, 403):
                return None
            if r.status_code == 500 and attempt < retry:
                time.sleep(3)
                continue
            return None
        except Exception as e:
            if attempt == retry:
                log(f"    GET 실패 ({url[:50]}): {e}")
            time.sleep(2)
    return None

def extract_date(soup, url=''):
    """날짜 추출 — 다중 패턴 fallback"""
    # 1) OG/메타 태그 (가장 신뢰)
    for prop in ['article:published_time', 'datePublished', 'pubdate']:
        el = (soup.find('meta', property=prop) or
              soup.find('meta', attrs={'name': prop}) or
              soup.find('meta', attrs={'itemprop': prop}))
        if el:
            d = el.get('content', '')[:10]
            if re.match(r'\d{4}-\d{2}-\d{2}', d):
                return d

    # 2) <time> 태그
    el = soup.find('time', attrs={'datetime': True})
    if el:
        d = el['datetime'][:10]
        if re.match(r'\d{4}-\d{2}-\d{2}', d):
            return d

    # 3) URL에서 날짜 추출
    m = re.search(r'(\d{4})[/-](\d{2})[/-](\d{2})', url)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # 4) 본문 텍스트에서 날짜 패턴
    text = soup.get_text()
    m = re.search(r'(January|February|March|April|May|June|July|August|'
                  r'September|October|November|December)\s+\d{1,2},?\s+202[4-6]', text)
    if m:
        try:
            d = datetime.strptime(m.group(0).replace(',',''), '%B %d %Y')
            return d.strftime('%Y-%m-%d')
        except Exception:
            pass

    return ''

def extract_title(soup):
    """제목 추출"""
    for sel in [
        ('meta', {'property': 'og:title'}),
        ('meta', {'name': 'title'}),
        ('h1', {}),
    ]:
        el = soup.find(sel[0], attrs=sel[1]) if sel[1] else soup.find(sel[0])
        if el:
            t = el.get('content', '') or el.get_text(strip=True)
            if len(t) >= MIN_TITLE_LEN:
                return t.strip()
    return ''

def extract_summary(soup):
    """요약 추출"""
    for prop in ['og:description', 'description']:
        el = (soup.find('meta', property=prop) or
              soup.find('meta', attrs={'name': prop}))
        if el:
            s = el.get('content', '').strip()
            if len(s) > 20:
                return s[:500]
    return ''

def crawl_article(url, source_name, from_date, existing_urls):
    """단일 기사 크롤링 — 공통 로직"""
    if url in existing_urls:
        return None
    time.sleep(REQUEST_DELAY)
    html = get_html(url)
    if not html:
        return None

    soup = BeautifulSoup(html, 'html.parser')
    title   = extract_title(soup)
    pub_date = extract_date(soup, url)
    summary  = extract_summary(soup)

    if not title or len(title) < MIN_TITLE_LEN:
        return None
    if pub_date and pub_date < from_date:
        return 'STOP'  # 조기 종료 신호
    if not is_infra_related(title, summary):
        return None

    return {
        'url':            url,
        'title':          title,
        'summary':        summary,
        'source':         source_name,
        'source_name':    source_name,
        'published_date': pub_date,
        'raw_summary':    summary,
    }


# ============================================================
# SITE 1 — theinvestor.vn  (v2.0: /tag/ URL 방식)
# ============================================================

INVESTOR_TAGS = [
    ('infrastructure',  'https://theinvestor.vn/tag/infrastructure'),
    ('energy',          'https://theinvestor.vn/tag/energy'),
    ('industrial-park', 'https://theinvestor.vn/tag/industrial-park'),
    ('environment',     'https://theinvestor.vn/tag/environment'),
    ('transport',       'https://theinvestor.vn/tag/transport'),
    ('wastewater',      'https://theinvestor.vn/tag/wastewater'),
    ('water-supply',    'https://theinvestor.vn/tag/water-supply'),
    ('solar-energy',    'https://theinvestor.vn/tag/solar-energy'),
    ('wind-power',      'https://theinvestor.vn/tag/wind-power'),
]

def scrape_theinvestor(from_date, existing_urls, dry_run=False):
    articles = []
    source   = 'The Investor'
    log(f"[theinvestor.vn] tag 기반 크롤링...")

    for tag_name, tag_url in INVESTOR_TAGS:
        tag_arts = []
        for page in range(1, MAX_PAGES + 1):
            url = tag_url if page == 1 else f"{tag_url}/page/{page}/"
            html = get_html(url)
            if not html:
                break

            soup = BeautifulSoup(html, 'html.parser')

            # 기사 URL 추출 — theinvestor.vn 패턴: /-d\d+ (숫자로 끝나는 링크)
            art_urls = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                full = urljoin('https://theinvestor.vn', href)
                # 실제 URL 패턴: /기사제목-d숫자
                if (re.search(r'-d\d+/?$', full) and
                    'theinvestor.vn' in full and
                    full not in art_urls):
                    art_urls.append(full)

            if not art_urls:
                log(f"  {tag_name} page {page}: 링크 없음 → 종료")
                break

            stop = False
            for art_url in art_urls:
                result = crawl_article(art_url, source, from_date, existing_urls)
                if result == 'STOP':
                    stop = True
                    break
                if result:
                    tag_arts.append(result)
                    if not dry_run:
                        log(f"  ✅ [{result['published_date']}] {result['title'][:55]}")

            log(f"  {tag_name} page {page}: {len(art_urls)}링크 → {len(tag_arts)}건")
            if stop:
                log(f"  {tag_name}: from_date 이전 도달 → 종료")
                break
            time.sleep(REQUEST_DELAY)

        articles.extend(tag_arts)

    log(f"theinvestor.vn 총 {len(articles)}건")
    return articles


# ============================================================
# SITE 2 — vir.com.vn  (v2.0: 검색 + 올바른 카테고리 URL)
# ============================================================

VIR_URLS = [
    ('search-infrastructure', 'https://vir.com.vn/search/?q=infrastructure&ordering=date_desc'),
    ('search-energy',         'https://vir.com.vn/search/?q=energy+vietnam&ordering=date_desc'),
    ('search-industrial',     'https://vir.com.vn/search/?q=industrial+park+vietnam&ordering=date_desc'),
    ('search-wastewater',     'https://vir.com.vn/search/?q=wastewater+vietnam&ordering=date_desc'),
    ('search-transport',      'https://vir.com.vn/search/?q=expressway+metro+vietnam&ordering=date_desc'),
]

def scrape_vir(from_date, existing_urls, dry_run=False):
    articles = []
    source   = 'Vietnam Investment Review'
    log(f"[vir.com.vn] 검색 기반 크롤링...")

    for search_name, search_url in VIR_URLS:
        search_arts = []
        for page in range(MAX_PAGES):
            offset = page * 10
            url = search_url if page == 0 else f"{search_url}&offset={offset}"
            html = get_html(url)
            if not html:
                break

            soup = BeautifulSoup(html, 'html.parser')

            # vir.com.vn 기사 링크 패턴: /기사제목-숫자.html
            art_urls = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                full = urljoin('https://vir.com.vn', href)
                if (re.search(r'-\d+\.html$', full) and
                    'vir.com.vn' in full and
                    '/tag/' not in full and
                    '/category/' not in full and
                    full not in art_urls):
                    art_urls.append(full)

            if not art_urls:
                break

            stop = False
            for art_url in art_urls:
                result = crawl_article(art_url, source, from_date, existing_urls)
                if result == 'STOP':
                    stop = True
                    break
                if result:
                    search_arts.append(result)
                    if not dry_run:
                        log(f"  ✅ [{result['published_date']}] {result['title'][:55]}")

            log(f"  {search_name} page {page+1}: {len(art_urls)}링크 → {len(search_arts)}건")
            if stop:
                break
            time.sleep(REQUEST_DELAY)

        articles.extend(search_arts)

    log(f"vir.com.vn 총 {len(articles)}건")
    return articles


# ============================================================
# SITE 3 — hanoitimes.vn  (v2.0: tag + search URL)
# ============================================================

HANOITIMES_URLS = [
    ('tag-infrastructure',  'https://hanoitimes.vn/tag/infrastructure'),
    ('tag-wastewater',      'https://hanoitimes.vn/tag/wastewater'),
    ('tag-energy',          'https://hanoitimes.vn/tag/energy'),
    ('tag-industrial-park', 'https://hanoitimes.vn/tag/industrial-park'),
    ('tag-transport',       'https://hanoitimes.vn/tag/transport'),
    ('tag-environment',     'https://hanoitimes.vn/tag/environment'),
    ('search-infra',        'https://hanoitimes.vn/?s=infrastructure'),
    ('search-water',        'https://hanoitimes.vn/?s=wastewater+water+supply'),
]

def scrape_hanoitimes(from_date, existing_urls, dry_run=False):
    articles = []
    source   = 'Hanoi Times'
    log(f"[hanoitimes.vn] tag+search 기반 크롤링...")

    for url_name, base_url in HANOITIMES_URLS:
        url_arts = []
        for page in range(1, MAX_PAGES + 1):
            if '/tag/' in base_url:
                url = base_url if page == 1 else f"{base_url}/page/{page}/"
            else:
                url = base_url if page == 1 else f"{base_url}&paged={page}"

            html = get_html(url)
            if not html:
                break

            soup = BeautifulSoup(html, 'html.parser')

            # hanoitimes.vn 기사 링크 패턴: /기사제목-숫자.html
            art_urls = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                full = urljoin('https://hanoitimes.vn', href)
                if (re.search(r'-\d+\.html$', full) and
                    'hanoitimes.vn' in full and
                    full not in art_urls):
                    art_urls.append(full)

            if not art_urls:
                log(f"  {url_name} page {page}: 링크 없음")
                break

            stop = False
            for art_url in art_urls:
                result = crawl_article(art_url, source, from_date, existing_urls)
                if result == 'STOP':
                    stop = True
                    break
                if result:
                    url_arts.append(result)
                    if not dry_run:
                        log(f"  ✅ [{result['published_date']}] {result['title'][:55]}")

            log(f"  {url_name} page {page}: {len(art_urls)}링크 → {len(url_arts)}건")
            if stop:
                log(f"  {url_name}: from_date 이전 도달 → 종료")
                break
            time.sleep(REQUEST_DELAY)

        articles.extend(url_arts)

    log(f"hanoitimes.vn 총 {len(articles)}건")
    return articles


# ============================================================
# MAIN
# ============================================================

def run_crawl(from_date, dry_run=False, sites=None):
    log('='*55)
    log(f"전문미디어 크롤러 v2.0 | from_date={from_date} | dry_run={dry_run}")
    log('='*55)

    # 기존 URL 수집 (중복 방지)
    existing_urls = set()
    if PIPELINE_AVAILABLE:
        try:
            conn = init_database(DB_PATH)
            existing_urls = get_existing_hashes(conn)
            conn.close()
        except Exception as e:
            log(f"DB hash 로드 경고: {e}")
    try:
        import openpyxl
        wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True, data_only=True)
        ws = wb.active
        link_col = 7
        for c in range(1, ws.max_column+1):
            if str(ws.cell(1,c).value or '').lower() in ('link','url'):
                link_col = c; break
        for row in ws.iter_rows(min_row=2, values_only=True):
            u = row[link_col-1] if link_col-1 < len(row) else None
            if u: existing_urls.add(str(u))
        wb.close()
    except Exception as e:
        log(f"Excel URL 로드 경고: {e}")
    log(f"기존 URL {len(existing_urls)}개 로드 완료")

    all_raw = []
    sites = sites or ['investor', 'vir', 'hanoitimes']

    if 'investor'   in sites:
        log("\n[1/3] theinvestor.vn...")
        all_raw.extend(scrape_theinvestor(from_date, existing_urls, dry_run))
    if 'vir'        in sites:
        log("\n[2/3] vir.com.vn...")
        all_raw.extend(scrape_vir(from_date, existing_urls, dry_run))
    if 'hanoitimes' in sites:
        log("\n[3/3] hanoitimes.vn...")
        all_raw.extend(scrape_hanoitimes(from_date, existing_urls, dry_run))

    log(f"\n{'='*55}")
    log(f"크롤링 원시 수집: {len(all_raw)}건")

    if not all_raw:
        log("수집 기사 없음 — 종료")
        return 0

    # Sector·Province 분류
    classified = []
    for art in all_raw:
        title   = art.get('title', '')
        summary = art.get('summary', '')
        url     = art.get('url', '')
        if not PIPELINE_AVAILABLE:
            break
        if not is_vietnam_related(title, summary):
            continue
        sector, area, confidence = classify_sector(title, summary)
        if not sector:
            continue
        province = extract_province(title, summary)
        art.update({
            'url_hash': generate_url_hash(url),
            'sector': sector, 'area': area,
            'province': province, 'confidence': confidence,
        })
        classified.append(art)

    log(f"분류 완료: {len(classified)}건")

    from collections import Counter
    sec_cnt  = Counter(a['sector']   for a in classified)
    prov_cnt = Counter(a['province'] for a in classified)
    log("Sector 분포:")
    for s, c in sec_cnt.most_common():
        log(f"  {s}: {c}건")
    vn_ratio = prov_cnt.get('Vietnam', 0) / max(len(classified), 1)
    log(f"Province='Vietnam'(미분류): {prov_cnt.get('Vietnam',0)}건 ({vn_ratio:.0%})")

    if dry_run:
        log("\n[Dry-run] Excel 저장 생략")
        import json
        Path('data/agent_output').mkdir(parents=True, exist_ok=True)
        with open('data/agent_output/crawler_dryrun.json','w',encoding='utf-8') as f:
            json.dump({'total': len(classified), 'articles': classified[:10]},
                      f, ensure_ascii=False, default=str, indent=2)
        return len(classified)

    if PIPELINE_AVAILABLE and classified:
        log(f"\n번역 시작 ({len(classified)}건)...")
        translated = translate_articles(classified)
        log("Excel DB 업데이트...")
        conn = init_database(DB_PATH)
        saved = 0
        for art in translated:
            if save_article(conn, art):
                saved += 1
        conn.close()
        update_excel_database(translated)
        log(f"✅ 완료: {saved}건 저장")

    log(f"\n{'='*55}")
    log(f"크롤러 v2.0 완료: {len(classified)}건 처리")
    return len(classified)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--from-date', default='2025-01-01')
    p.add_argument('--dry-run',   action='store_true')
    p.add_argument('--sites',     nargs='+', choices=['investor','vir','hanoitimes'])
    args = p.parse_args()
    result = run_crawl(args.from_date, args.dry_run, args.sites)
    print(f"\n최종: {result}건 처리")
