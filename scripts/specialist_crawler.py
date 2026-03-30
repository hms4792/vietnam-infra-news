#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
specialist_crawler.py  v3.0
전문 인프라 미디어 소급 크롤링 스크립트
대상: theinvestor.vn / vir.com.vn / hanoitimes.vn

v3.0 수정사항 (2026-03-30):
  - theinvestor.vn: /infrastructure/, /energy/ 카테고리 URL 수정 (슬래시 필수)
    기사링크 패턴: -d숫자.html (예: -d18183.html)
  - vir.com.vn: RSS 피드 방식으로 전환 (검색 URL 500 오류 해결)
  - hanoitimes.vn: RSS 피드 방식으로 전환 (/tag/ 빈 페이지 해결)
  - 공통: news_collector.py RSS 파서 로직 재활용

[실행]
  python3 scripts/specialist_crawler.py --from-date 2025-01-01
  python3 scripts/specialist_crawler.py --from-date 2025-01-01 --dry-run
  python3 scripts/specialist_crawler.py --from-date 2025-01-01 --sites investor
"""

import os, sys, re, time, hashlib, argparse
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent))
try:
    from news_collector import (
        classify_sector, extract_province, is_vietnam_related,
        generate_url_hash, translate_articles, update_excel_database,
        init_database, save_article, get_existing_hashes, log,
        EXCEL_PATH, DB_PATH, fetch_rss, parse_date, clean_html,
    )
    PIPELINE_AVAILABLE = True
except ImportError as e:
    print(f"[경고] news_collector 임포트 실패: {e}")
    PIPELINE_AVAILABLE = False
    def log(m): print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {m}")
    EXCEL_PATH = os.environ.get('EXCEL_PATH','data/database/Vietnam_Infra_News_Database_Final.xlsx')
    DB_PATH    = os.environ.get('DB_PATH','data/vietnam_infrastructure_news.db')
    def generate_url_hash(u):
        import hashlib; return hashlib.md5(u.encode()).hexdigest()

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0',
    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}
REQUEST_DELAY = 2.0
MAX_PAGES     = 15
TIMEOUT       = 20
MIN_TITLE_LEN = 20

# 인프라 1차 키워드 필터
INFRA_KEYWORDS = [
    'infrastructure','wastewater','water supply','drainage','flood',
    'power plant','solar','wind farm','energy','electricity','grid',
    'oil','gas','lng','petroleum','pipeline',
    'industrial park','industrial zone','economic zone','fdi',
    'transport','expressway','highway','metro','railway','airport','port',
    'solid waste','landfill','recycling','waste-to-energy',
    'smart city','urban development','construction',
    'nước thải','điện','khu công nghiệp','cao tốc','cảng','rác thải',
]

def is_infra_related(title, summary=''):
    text = (title + ' ' + summary).lower()
    return any(kw in text for kw in INFRA_KEYWORDS)

def get_html(url, retry=2):
    for attempt in range(retry + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.text
            if r.status_code in (404, 403):
                return None
            if attempt < retry:
                time.sleep(3)
        except Exception as e:
            if attempt == retry:
                log(f"    GET 실패 ({url[:60]}): {e}")
            time.sleep(2)
    return None

def extract_meta(soup, url=''):
    """제목·날짜·요약 추출 — 다중 패턴 fallback"""
    # 제목
    title = ''
    for sel in [('meta',{'property':'og:title'}), ('meta',{'name':'title'}), ('h1',{})]:
        el = soup.find(sel[0], attrs=sel[1]) if sel[1] else soup.find(sel[0])
        if el:
            t = el.get('content','') or el.get_text(strip=True)
            if len(t) >= MIN_TITLE_LEN:
                title = t.strip(); break

    # 날짜
    pub_date = ''
    for prop in ['article:published_time','datePublished','pubdate']:
        el = (soup.find('meta', property=prop) or
              soup.find('meta', attrs={'name':prop}) or
              soup.find('meta', attrs={'itemprop':prop}))
        if el:
            d = el.get('content','')[:10]
            if re.match(r'\d{4}-\d{2}-\d{2}', d):
                pub_date = d; break
    if not pub_date:
        el = soup.find('time', attrs={'datetime': True})
        if el and re.match(r'\d{4}-\d{2}-\d{2}', el['datetime'][:10]):
            pub_date = el['datetime'][:10]
    if not pub_date:
        m = re.search(r'(\d{4})[/-](\d{2})[/-](\d{2})', url)
        if m:
            pub_date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    # 요약
    summary = ''
    el = (soup.find('meta', property='og:description') or
          soup.find('meta', attrs={'name':'description'}))
    if el:
        summary = el.get('content','').strip()[:500]

    return title, pub_date, summary


# ============================================================
# RSS 기반 수집 (vir.com.vn, hanoitimes.vn 공통)
# news_collector.py fetch_rss() 재활용
# ============================================================

def collect_from_rss(rss_urls, source_name, from_date, existing_urls, dry_run=False):
    """RSS 피드 기반 기사 수집 — news_collector.py 로직 재활용"""
    articles = []
    cutoff = datetime.strptime(from_date, '%Y-%m-%d')

    for feed_url in rss_urls:
        log(f"  RSS: {feed_url}")
        try:
            if PIPELINE_AVAILABLE:
                feed = fetch_rss(feed_url)
            else:
                import feedparser
                feed = feedparser.parse(requests.get(feed_url, headers=HEADERS, timeout=20).text)

            if not feed.entries:
                log(f"    → 항목 없음")
                continue

            count = 0
            for entry in feed.entries:
                title   = clean_html(getattr(entry, 'title', '')) if PIPELINE_AVAILABLE \
                          else getattr(entry, 'title', '')
                link    = getattr(entry, 'link', '')
                summary = clean_html(getattr(entry, 'summary',
                          getattr(entry, 'description', ''))) if PIPELINE_AVAILABLE \
                          else getattr(entry, 'summary', getattr(entry, 'description', ''))
                pubdate = getattr(entry, 'published', getattr(entry, 'pubDate', ''))

                if not title or not link or len(title) < MIN_TITLE_LEN:
                    continue
                if link in existing_urls:
                    continue
                if not is_infra_related(title, summary):
                    continue

                # 날짜 필터
                if PIPELINE_AVAILABLE:
                    pub_dt = parse_date(pubdate)
                else:
                    from email.utils import parsedate_to_datetime
                    try:
                        pub_dt = parsedate_to_datetime(pubdate).replace(tzinfo=None)
                    except Exception:
                        pub_dt = None

                if pub_dt:
                    if pub_dt.tzinfo:
                        pub_dt = pub_dt.replace(tzinfo=None)
                    if pub_dt < cutoff:
                        continue
                    pub_date_str = pub_dt.strftime('%Y-%m-%d')
                else:
                    pub_date_str = ''

                art = {
                    'url':            link,
                    'title':          title.strip(),
                    'summary':        summary[:500] if summary else '',
                    'source':         source_name,
                    'source_name':    source_name,
                    'published_date': pub_date_str,
                    'raw_summary':    summary[:500] if summary else '',
                }
                articles.append(art)
                count += 1
                if not dry_run:
                    log(f"    ✅ [{pub_date_str}] {title[:55]}")

            log(f"    → {count}건 수집")
        except Exception as e:
            log(f"    RSS 오류 ({feed_url}): {e}")
        time.sleep(REQUEST_DELAY)

    return articles


# ============================================================
# SITE 1 — theinvestor.vn  (v3.0: 올바른 카테고리 URL)
# ============================================================

# 검색 결과로 확인된 실제 카테고리 URL (슬래시 끝 필수)
INVESTOR_CATEGORIES = [
    'https://theinvestor.vn/infrastructure/',
    'https://theinvestor.vn/energy/',
    'https://theinvestor.vn/environment/',
    'https://theinvestor.vn/industries/',
    'https://theinvestor.vn/real-estate/',
]

def scrape_theinvestor(from_date, existing_urls, dry_run=False):
    articles = []
    source   = 'The Investor'
    log(f"[theinvestor.vn] 카테고리 페이지 크롤링...")
    cutoff = datetime.strptime(from_date, '%Y-%m-%d')

    for cat_url in INVESTOR_CATEGORIES:
        cat_name = cat_url.split('/')[-2]
        cat_arts = []

        for page in range(1, MAX_PAGES + 1):
            # theinvestor.vn 페이지네이션: ?page=2
            url = cat_url if page == 1 else f"{cat_url}?page={page}"
            html = get_html(url)
            if not html:
                log(f"  {cat_name} page {page}: 응답 없음")
                break

            soup = BeautifulSoup(html, 'html.parser')

            # 기사 링크 추출 — 실제 패턴: -d숫자.html (예: -d18183.html)
            art_urls = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                full = urljoin('https://theinvestor.vn', href)
                if (re.search(r'-d\d+\.html$', full) and
                    'theinvestor.vn' in full and
                    full not in art_urls):
                    art_urls.append(full)

            if not art_urls:
                log(f"  {cat_name} page {page}: 기사 링크 없음 → 종료")
                break

            stop = False
            for art_url in art_urls:
                if art_url in existing_urls:
                    continue
                time.sleep(REQUEST_DELAY)
                art_html = get_html(art_url)
                if not art_html:
                    continue
                art_soup  = BeautifulSoup(art_html, 'html.parser')
                title, pub_date, summary = extract_meta(art_soup, art_url)

                if not title or len(title) < MIN_TITLE_LEN:
                    continue
                if pub_date and pub_date < from_date:
                    stop = True; break
                if not is_infra_related(title, summary):
                    continue

                cat_arts.append({
                    'url': art_url, 'title': title,
                    'summary': summary, 'source': source, 'source_name': source,
                    'published_date': pub_date, 'raw_summary': summary,
                })
                if not dry_run:
                    log(f"  ✅ [{pub_date}] {title[:55]}")

            log(f"  {cat_name} page {page}: {len(art_urls)}링크 → {len(cat_arts)}건")
            if stop:
                log(f"  {cat_name}: {from_date} 이전 도달 → 종료")
                break
            time.sleep(REQUEST_DELAY)

        articles.extend(cat_arts)

    log(f"theinvestor.vn 총 {len(articles)}건")
    return articles


# ============================================================
# SITE 2 — vir.com.vn  (v3.0: RSS 피드 방식)
# ============================================================

VIR_RSS_FEEDS = [
    'https://vir.com.vn/rss/home.rss',
    'https://vir.com.vn/rss/business.rss',
    'https://vir.com.vn/rss/real-estate.rss',
]

def scrape_vir(from_date, existing_urls, dry_run=False):
    log(f"[vir.com.vn] RSS 피드 수집...")
    arts = collect_from_rss(VIR_RSS_FEEDS, 'Vietnam Investment Review',
                            from_date, existing_urls, dry_run)
    log(f"vir.com.vn 총 {len(arts)}건")
    return arts


# ============================================================
# SITE 3 — hanoitimes.vn  (v3.0: RSS 피드 방식)
# ============================================================

HANOITIMES_RSS_FEEDS = [
    'https://hanoitimes.vn/rss',
    'https://hanoitimes.vn/rss/business.rss',
    'https://hanoitimes.vn/feed',
]

def scrape_hanoitimes(from_date, existing_urls, dry_run=False):
    log(f"[hanoitimes.vn] RSS 피드 수집...")
    arts = collect_from_rss(HANOITIMES_RSS_FEEDS, 'Hanoi Times',
                            from_date, existing_urls, dry_run)
    log(f"hanoitimes.vn 총 {len(arts)}건")
    return arts


# ============================================================
# MAIN
# ============================================================

def run_crawl(from_date, dry_run=False, sites=None):
    log('='*55)
    log(f"전문미디어 크롤러 v3.0 | from_date={from_date} | dry_run={dry_run}")
    log('='*55)

    # 기존 URL 로드 (중복 방지)
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
            if u:
                existing_urls.add(str(u))
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
    if PIPELINE_AVAILABLE:
        for art in all_raw:
            title   = art.get('title','')
            summary = art.get('summary','')
            url     = art.get('url','')
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
    else:
        classified = all_raw

    log(f"분류 완료: {len(classified)}건")

    if classified:
        from collections import Counter
        sec_cnt  = Counter(a.get('sector','?')   for a in classified)
        prov_cnt = Counter(a.get('province','?') for a in classified)
        log("Sector 분포:")
        for s, c in sec_cnt.most_common():
            log(f"  {s}: {c}건")
        vn = prov_cnt.get('Vietnam',0)
        log(f"Province='Vietnam'(미분류): {vn}건 ({vn/max(len(classified),1):.0%})")

    if dry_run:
        log("\n[Dry-run] Excel 저장 생략")
        import json
        Path('data/agent_output').mkdir(parents=True, exist_ok=True)
        with open('data/agent_output/crawler_dryrun.json','w',encoding='utf-8') as f:
            json.dump({'total':len(classified),'articles':classified[:10]},
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
    log(f"크롤러 v3.0 완료: {len(classified)}건 처리")
    return len(classified)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--from-date', default='2025-01-01')
    p.add_argument('--dry-run',   action='store_true')
    p.add_argument('--sites',     nargs='+', choices=['investor','vir','hanoitimes'])
    args = p.parse_args()
    result = run_crawl(args.from_date, args.dry_run, args.sites)
    print(f"\n최종: {result}건 처리")
