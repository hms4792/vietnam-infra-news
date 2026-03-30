#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
specialist_crawler.py
전문 인프라 미디어 3개 소급 크롤링 스크립트
대상: theinvestor.vn / vir.com.vn / hanoitimes.vn

[목적] 2025년 1월 이후 공백 기간 기사 소급 수집
[제약] 기존 파이프라인 연결 — translate_articles() → update_excel_database()
[실행] python3 scripts/specialist_crawler.py --from-date 2025-01-01
       python3 scripts/specialist_crawler.py --from-date 2025-01-01 --dry-run
[워크플로] collect_weekly.yml 에서 월 1회 자동 실행 (sogu 소급용)
"""

import os, sys, re, time, hashlib, sqlite3, argparse
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# ── 기존 파이프라인 임포트 ─────────────────────────────────────
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
    print("  → 단독 실행 모드: 수집만 하고 JSON으로 저장")
    PIPELINE_AVAILABLE = False

# ── 설정 ──────────────────────────────────────────────────────
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
}
REQUEST_DELAY  = 1.5   # 요청 간 딜레이 (초) — 서버 부하 최소화
MAX_PAGES      = 15    # 사이트당 최대 페이지
TIMEOUT        = 20    # 요청 타임아웃 (초)
MIN_TITLE_LEN  = 20    # 최소 제목 길이


# ============================================================
# SITE 1 — theinvestor.vn
# ============================================================

INVESTOR_CATEGORIES = [
    'https://theinvestor.vn/category/infrastructure',
    'https://theinvestor.vn/category/energy',
    'https://theinvestor.vn/category/real-estate',
    'https://theinvestor.vn/category/industries',
    'https://theinvestor.vn/category/environment',
]

def scrape_theinvestor(from_date, existing_urls, dry_run=False):
    """
    theinvestor.vn 크롤러
    URL 패턴: /기사제목-d숫자.html
    페이지네이션: ?page=2
    """
    articles = []
    source_name = 'The Investor'

    for cat_url in INVESTOR_CATEGORIES:
        cat_name = cat_url.split('/')[-1]
        log(f"  [theinvestor.vn] {cat_name} 크롤링...")
        page_articles = []

        for page in range(1, MAX_PAGES + 1):
            url = cat_url if page == 1 else f"{cat_url}?page={page}"
            try:
                resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
                if resp.status_code == 404:
                    break
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, 'html.parser')

                # 기사 링크 추출 — theinvestor.vn 구조
                # <article> 또는 .post-item .entry-title a
                art_links = []
                # 패턴1: article 태그
                for art in soup.find_all('article'):
                    a = art.find('a', href=True)
                    if a:
                        art_links.append(a['href'])
                # 패턴2: h2/h3 내 링크
                if not art_links:
                    for h in soup.find_all(['h2', 'h3']):
                        a = h.find('a', href=True)
                        if a and 'theinvestor.vn' in a.get('href',''):
                            art_links.append(a['href'])
                # 패턴3: 일반 기사 링크 패턴
                if not art_links:
                    for a in soup.find_all('a', href=True):
                        href = a['href']
                        if re.search(r'-d\d+\.html$', href):
                            art_links.append(href)

                art_links = list(dict.fromkeys([
                    urljoin('https://theinvestor.vn', l) for l in art_links
                    if 'theinvestor.vn' in urljoin('https://theinvestor.vn', l)
                ]))

                if not art_links:
                    log(f"    page {page}: 기사 없음 → 종료")
                    break

                # 날짜 기반 조기 종료 체크
                earliest_date = None
                stop_early = False

                for art_url in art_links:
                    if art_url in existing_urls:
                        continue

                    time.sleep(REQUEST_DELAY)
                    try:
                        art_resp = requests.get(art_url, headers=HEADERS, timeout=TIMEOUT)
                        art_resp.raise_for_status()
                        art_soup = BeautifulSoup(art_resp.text, 'html.parser')

                        # 제목
                        title = ''
                        for sel in ['h1', 'meta[property="og:title"]']:
                            el = art_soup.find(sel) if not sel.startswith('meta') \
                                 else art_soup.find('meta', property='og:title')
                            if el:
                                title = el.get('content', '') or el.get_text(strip=True)
                                break

                        # 날짜
                        pub_date = ''
                        for sel in [
                            ('meta', {'property': 'article:published_time'}),
                            ('time', {}),
                            ('span', {'class': re.compile(r'date|time|publish', re.I)}),
                        ]:
                            el = art_soup.find(sel[0], **({'attrs': sel[1]} if sel[1] else {}))
                            if el:
                                dt_str = el.get('datetime') or el.get('content') or el.get_text(strip=True)
                                if dt_str:
                                    pub_date = dt_str[:10]
                                    break

                        if pub_date and pub_date < from_date:
                            stop_early = True
                            break
                        if pub_date and pub_date > datetime.now().strftime('%Y-%m-%d'):
                            continue

                        # 요약
                        summary = ''
                        meta_desc = art_soup.find('meta', attrs={'name': 'description'}) or \
                                    art_soup.find('meta', property='og:description')
                        if meta_desc:
                            summary = meta_desc.get('content', '')

                        if len(title) < MIN_TITLE_LEN:
                            continue

                        art_data = {
                            'url':            art_url,
                            'title':          title.strip(),
                            'summary':        summary[:500],
                            'source':         source_name,
                            'source_name':    source_name,
                            'published_date': pub_date,
                            'raw_summary':    summary[:500],
                        }
                        page_articles.append(art_data)
                        if not dry_run:
                            log(f"    ✅ [{pub_date}] {title[:55]}")

                    except Exception as e:
                        log(f"    기사 오류 ({art_url[:50]}): {e}")
                    time.sleep(REQUEST_DELAY)

                if stop_early:
                    log(f"    조기 종료: {from_date} 이전 기사 도달")
                    break

                log(f"    page {page}: {len(art_links)}개 링크, {len(page_articles)}건 수집")
                time.sleep(REQUEST_DELAY)

            except Exception as e:
                log(f"    페이지 오류 (page {page}): {e}")
                break

        articles.extend(page_articles)
        log(f"  {cat_name} 완료: {len(page_articles)}건")

    log(f"theinvestor.vn 총 {len(articles)}건")
    return articles


# ============================================================
# SITE 2 — vir.com.vn (Vietnam Investment Review)
# ============================================================

VIR_CATEGORIES = [
    'https://vir.com.vn/infrastructure.html',
    'https://vir.com.vn/energy.html',
    'https://vir.com.vn/industrial-zones.html',
    'https://vir.com.vn/environment.html',
]

def scrape_vir(from_date, existing_urls, dry_run=False):
    """
    vir.com.vn 크롤러
    페이지네이션: ?start=10&limit=10
    """
    articles = []
    source_name = 'Vietnam Investment Review'

    for cat_url in VIR_CATEGORIES:
        cat_name = cat_url.split('/')[-1].replace('.html','')
        log(f"  [vir.com.vn] {cat_name} 크롤링...")
        page_articles = []

        for page in range(MAX_PAGES):
            start = page * 10
            url = cat_url if page == 0 else f"{cat_url}?start={start}&limit=10"
            try:
                resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
                if resp.status_code in (404, 403):
                    break
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, 'html.parser')

                # 기사 링크 추출
                art_links = []
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    full = urljoin('https://vir.com.vn', href)
                    if 'vir.com.vn' in full and re.search(r'-\d+\.html$', full):
                        if full not in [l for l in art_links]:
                            art_links.append(full)

                if not art_links:
                    break

                stop_early = False
                for art_url in art_links[:10]:
                    if art_url in existing_urls:
                        continue
                    time.sleep(REQUEST_DELAY)
                    try:
                        ar = requests.get(art_url, headers=HEADERS, timeout=TIMEOUT)
                        ar.raise_for_status()
                        asoup = BeautifulSoup(ar.text, 'html.parser')

                        # 제목
                        title = ''
                        el = asoup.find('meta', property='og:title') or asoup.find('h1')
                        if el:
                            title = el.get('content','') or el.get_text(strip=True)

                        # 날짜
                        pub_date = ''
                        for attr in ['article:published_time', 'datePublished']:
                            el = asoup.find('meta', property=attr) or asoup.find('meta', attrs={'name': attr})
                            if el:
                                pub_date = el.get('content','')[:10]
                                break
                        if not pub_date:
                            el = asoup.find('time') or asoup.find(class_=re.compile(r'date|publish', re.I))
                            if el:
                                pub_date = (el.get('datetime') or el.get_text(strip=True))[:10]

                        if pub_date and pub_date < from_date:
                            stop_early = True
                            break

                        # 요약
                        summary = ''
                        el = asoup.find('meta', attrs={'name':'description'}) or \
                             asoup.find('meta', property='og:description')
                        if el:
                            summary = el.get('content','')[:500]

                        if len(title) < MIN_TITLE_LEN:
                            continue

                        page_articles.append({
                            'url': art_url, 'title': title.strip(),
                            'summary': summary, 'source': source_name,
                            'source_name': source_name,
                            'published_date': pub_date, 'raw_summary': summary,
                        })
                        if not dry_run:
                            log(f"    ✅ [{pub_date}] {title[:55]}")

                    except Exception as e:
                        log(f"    기사 오류: {e}")
                    time.sleep(REQUEST_DELAY)

                if stop_early:
                    break

            except Exception as e:
                log(f"    페이지 오류: {e}")
                break

        articles.extend(page_articles)
        log(f"  {cat_name}: {len(page_articles)}건")

    log(f"vir.com.vn 총 {len(articles)}건")
    return articles


# ============================================================
# SITE 3 — hanoitimes.vn
# ============================================================

HANOITIMES_CATEGORIES = [
    'https://hanoitimes.vn/infrastructure',
    'https://hanoitimes.vn/energy',
    'https://hanoitimes.vn/urban-development',
    'https://hanoitimes.vn/business',
]

def scrape_hanoitimes(from_date, existing_urls, dry_run=False):
    """
    hanoitimes.vn 크롤러
    페이지네이션: /page/2/
    """
    articles = []
    source_name = 'Hanoi Times'

    for cat_url in HANOITIMES_CATEGORIES:
        cat_name = cat_url.split('/')[-1]
        log(f"  [hanoitimes.vn] {cat_name} 크롤링...")
        page_articles = []

        for page in range(1, MAX_PAGES + 1):
            url = cat_url if page == 1 else f"{cat_url}/page/{page}/"
            try:
                resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
                if resp.status_code == 404:
                    break
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, 'html.parser')

                art_links = []
                # h2/h3 내 링크 (주요 패턴)
                for h in soup.find_all(['h2', 'h3', 'h4']):
                    a = h.find('a', href=True)
                    if a:
                        href = urljoin('https://hanoitimes.vn', a['href'])
                        if 'hanoitimes.vn' in href and href not in art_links:
                            art_links.append(href)
                # article 태그
                for art in soup.find_all('article'):
                    a = art.find('a', href=True)
                    if a:
                        href = urljoin('https://hanoitimes.vn', a['href'])
                        if href not in art_links:
                            art_links.append(href)

                if not art_links:
                    break

                stop_early = False
                for art_url in art_links[:12]:
                    if art_url in existing_urls:
                        continue
                    time.sleep(REQUEST_DELAY)
                    try:
                        ar = requests.get(art_url, headers=HEADERS, timeout=TIMEOUT)
                        ar.raise_for_status()
                        asoup = BeautifulSoup(ar.text, 'html.parser')

                        # 제목
                        title = ''
                        el = asoup.find('h1') or asoup.find('meta', property='og:title')
                        if el:
                            title = el.get('content','') or el.get_text(strip=True)

                        # 날짜
                        pub_date = ''
                        el = asoup.find('meta', property='article:published_time')
                        if el:
                            pub_date = el.get('content','')[:10]
                        if not pub_date:
                            el = asoup.find('time')
                            if el:
                                pub_date = (el.get('datetime','') or el.get_text(strip=True))[:10]

                        if pub_date and pub_date < from_date:
                            stop_early = True
                            break

                        # 요약
                        summary = ''
                        el = asoup.find('meta', attrs={'name':'description'}) or \
                             asoup.find('meta', property='og:description')
                        if el:
                            summary = el.get('content','')[:500]

                        if len(title) < MIN_TITLE_LEN:
                            continue

                        page_articles.append({
                            'url': art_url, 'title': title.strip(),
                            'summary': summary, 'source': source_name,
                            'source_name': source_name,
                            'published_date': pub_date, 'raw_summary': summary,
                        })
                        if not dry_run:
                            log(f"    ✅ [{pub_date}] {title[:55]}")

                    except Exception as e:
                        log(f"    기사 오류: {e}")
                    time.sleep(REQUEST_DELAY)

                if stop_early:
                    break

            except Exception as e:
                log(f"    페이지 오류 page {page}: {e}")
                break

        articles.extend(page_articles)
        log(f"  {cat_name}: {len(page_articles)}건")

    log(f"hanoitimes.vn 총 {len(articles)}건")
    return articles


# ============================================================
# MAIN
# ============================================================

def run_crawl(from_date, dry_run=False, sites=None):
    """
    전문미디어 3개 크롤링 실행 → 파이프라인 연결

    Args:
        from_date: 'YYYY-MM-DD' 형식 (이 날짜 이후 기사만 수집)
        dry_run:   True면 수집만 하고 Excel 저장 안 함
        sites:     ['investor', 'vir', 'hanoitimes'] 중 선택 (None=전체)
    """
    log(f"{'='*55}")
    log(f"전문미디어 크롤러 시작 | from_date={from_date} | dry_run={dry_run}")
    log(f"{'='*55}")

    # 기존 URL 목록 (중복 방지)
    existing_urls = set()
    if PIPELINE_AVAILABLE:
        conn = init_database(DB_PATH)
        existing_urls = get_existing_hashes(conn)
        conn.close()
        # URL 자체도 수집 (hash뿐 아니라 URL 문자열)
        try:
            import openpyxl
            wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True, data_only=True)
            ws = wb.active
            link_col = 7
            for c in range(1, ws.max_column+1):
                if str(ws.cell(1,c).value or '').lower() in ('link','url'):
                    link_col = c; break
            for row in ws.iter_rows(min_row=2, values_only=True):
                url = row[link_col-1] if link_col-1 < len(row) else None
                if url:
                    existing_urls.add(str(url))
            wb.close()
        except Exception as e:
            log(f"Excel URL 로드 경고: {e}")

    log(f"기존 DB URL 수: {len(existing_urls)}개")

    all_articles = []
    sites = sites or ['investor', 'vir', 'hanoitimes']

    # ── 크롤링 실행 ──────────────────────────────────────────
    if 'investor' in sites:
        log("\n[1/3] theinvestor.vn 크롤링...")
        arts = scrape_theinvestor(from_date, existing_urls, dry_run)
        all_articles.extend(arts)

    if 'vir' in sites:
        log("\n[2/3] vir.com.vn 크롤링...")
        arts = scrape_vir(from_date, existing_urls, dry_run)
        all_articles.extend(arts)

    if 'hanoitimes' in sites:
        log("\n[3/3] hanoitimes.vn 크롤링...")
        arts = scrape_hanoitimes(from_date, existing_urls, dry_run)
        all_articles.extend(arts)

    log(f"\n{'='*55}")
    log(f"크롤링 완료: 총 {len(all_articles)}건")

    if not all_articles:
        log("수집된 기사 없음 — 종료")
        return 0

    # ── Sector·Province 분류 ─────────────────────────────────
    classified = []
    for art in all_articles:
        title   = art.get('title','')
        summary = art.get('summary','')
        url     = art.get('url','')

        if not is_vietnam_related(title, summary):
            continue

        sector, area, confidence = classify_sector(title, summary)
        if not sector:
            continue

        province = extract_province(title, summary)
        url_hash = generate_url_hash(url)

        art.update({
            'url_hash':   url_hash,
            'sector':     sector,
            'area':       area,
            'province':   province,
            'confidence': confidence,
        })
        classified.append(art)

    log(f"분류 완료: {len(classified)}건 (미분류 제외)")

    # 분류 결과 요약
    from collections import Counter
    sec_cnt  = Counter(a['sector']   for a in classified)
    prov_cnt = Counter(a['province'] for a in classified)
    log("\nSector 분포:")
    for s, c in sec_cnt.most_common():
        log(f"  {s}: {c}건")
    log(f"\nProvince 상위 5개:")
    for p, c in prov_cnt.most_common(5):
        log(f"  {p}: {c}건")
    log(f"Province='Vietnam'(미분류): {prov_cnt.get('Vietnam',0)}건 "
        f"({prov_cnt.get('Vietnam',0)/max(len(classified),1):.0%})")

    if dry_run:
        log("\n[Dry-run] Excel 저장 생략")
        import json
        out = {'collected': len(classified), 'articles': classified[:5]}
        Path('data/agent_output').mkdir(parents=True, exist_ok=True)
        with open('data/agent_output/crawler_dryrun.json', 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, default=str, indent=2)
        log("  → data/agent_output/crawler_dryrun.json 저장")
        return len(classified)

    # ── 번역 → Excel 저장 ────────────────────────────────────
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
        log(f"✅ 완료: {saved}건 SQLite 저장 | Excel 업데이트")
    else:
        log("[경고] 파이프라인 미연결 — 결과를 JSON으로 저장")
        import json
        Path('data/agent_output').mkdir(parents=True, exist_ok=True)
        with open('data/agent_output/crawler_output.json','w',encoding='utf-8') as f:
            json.dump({'collected': len(classified), 'articles': classified},
                      f, ensure_ascii=False, default=str, indent=2)

    log(f"\n{'='*55}")
    log(f"전문미디어 크롤러 완료: {len(classified)}건 처리")
    return len(classified)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='전문미디어 소급 크롤러')
    parser.add_argument('--from-date', default='2025-01-01',
                        help='수집 시작 날짜 YYYY-MM-DD (기본: 2025-01-01)')
    parser.add_argument('--dry-run',   action='store_true',
                        help='수집만 하고 Excel 저장 안 함')
    parser.add_argument('--sites',     nargs='+',
                        choices=['investor','vir','hanoitimes'],
                        help='크롤링할 사이트 선택 (기본: 전체)')
    args = parser.parse_args()

    result = run_crawl(
        from_date=args.from_date,
        dry_run=args.dry_run,
        sites=args.sites,
    )
    print(f"\n최종 결과: {result}건 처리")
