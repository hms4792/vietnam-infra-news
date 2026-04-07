#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
specialist_crawler.py  v4.0
전문 인프라 미디어 직접 크롤링 스크립트

대상:
  1. theinvestor.vn — 카테고리 페이지 HTML 크롤링
  2. vir.com.vn     — 카테고리 페이지 HTML 크롤링
  (hanoitimes.vn는 RSS 정상 작동 → news_collector.py로 수집)

v4.0 변경사항 (2026-04-07):
  [재작성] 검색으로 실제 URL 패턴 확인 후 완전 재작성
  [theinvestor] 카테고리 URL / 기사 URL 패턴 (d숫자) 확인
  [vir] RSS 폐쇄 확인 → 카테고리 HTML 크롤링으로 전환
  [안전장치] 요청 간 딜레이, 최대 페이지 제한, 날짜 필터
  [파이프라인] news_collector.py 함수 재사용
               → classify_sector(), extract_province(), translate_articles()

실행:
  python3 scripts/specialist_crawler.py
  python3 scripts/specialist_crawler.py --from-date 2025-01-01
  python3 scripts/specialist_crawler.py --dry-run
  python3 scripts/specialist_crawler.py --sites investor
  python3 scripts/specialist_crawler.py --sites vir
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ── 파이프라인 임포트 ──────────────────────────────────────────
SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from news_collector import (
        classify_sector, extract_province,
        generate_url_hash, translate_articles,
        init_database, save_article, get_existing_hashes,
        EXCEL_PATH, DB_PATH,
    )
    PIPELINE_OK = True
except ImportError as e:
    print(f"[WARN] news_collector 임포트 실패: {e}")
    PIPELINE_OK = False
    EXCEL_PATH = os.environ.get(
        'EXCEL_PATH', 'data/database/Vietnam_Infra_News_Database_Final.xlsx'
    )
    DB_PATH = os.environ.get(
        'DB_PATH', 'data/vietnam_infrastructure_news.db'
    )
    def generate_url_hash(url):
        return hashlib.md5(url.encode()).hexdigest()

try:
    import openpyxl
    OPENPYXL_OK = True
except ImportError:
    OPENPYXL_OK = False

# ── 설정 ──────────────────────────────────────────────────────
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
}
DELAY        = 2.0   # 요청 간 딜레이 (초)
MAX_PAGES    = 8     # 카테고리당 최대 페이지
TIMEOUT      = 20    # 요청 타임아웃 (초)
MIN_TITLE    = 20    # 최소 제목 길이


def log(msg):
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {msg}")


def fetch_page(url):
    """HTML 페이지 가져오기"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        if r.status_code == 200:
            return r.text
        log(f"  [HTTP {r.status_code}] {url}")
        return None
    except Exception as e:
        log(f"  [ERR] {url}: {e}")
        return None


def parse_date_str(date_str):
    """다양한 날짜 형식 파싱"""
    if not date_str:
        return None
    date_str = date_str.strip()
    formats = [
        "%Y-%m-%dT%H:%M:%S",   # ISO
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str[:len(fmt)], fmt)
        except ValueError:
            continue
    return None


def load_existing_urls():
    """Excel에서 기존 URL 로드 (중복 방지)"""
    existing = set()
    if not OPENPYXL_OK:
        return existing
    try:
        p = Path(EXCEL_PATH)
        if not p.exists():
            return existing
        wb = openpyxl.load_workbook(p, read_only=True, data_only=True)
        ws = wb.active
        for row in ws.iter_rows(min_row=2, values_only=True):
            url = str(row[6] or '').strip()  # Link 컬럼
            if url and url.startswith('http'):
                existing.add(url)
                existing.add(generate_url_hash(url))
        wb.close()
        log(f"  기존 URL {len(existing)//2}건 로드")
    except Exception as e:
        log(f"  [WARN] Excel URL 로드 실패: {e}")
    return existing


# ============================================================
# SITE 1 — theinvestor.vn
# ============================================================

# 검색으로 확인한 실제 카테고리 URL 패턴
INVESTOR_CATEGORIES = [
    "https://theinvestor.vn/infrastructure/",
    "https://theinvestor.vn/energy/",
    "https://theinvestor.vn/industrial-real-estate/",
    "https://theinvestor.vn/real-estate/",
    "https://theinvestor.vn/industries/",
    "https://theinvestor.vn/environment/",
]

# 기사 URL 패턴: /기사제목-d숫자.html (검색에서 확인)
INVESTOR_ARTICLE_RE = re.compile(r'/[a-z0-9-]+-d\d+\.html$')


def _get_investor_article_links(html, base_url):
    """theinvestor.vn 카테고리 페이지에서 기사 링크 추출"""
    soup = BeautifulSoup(html, 'lxml')
    links = set()
    for a in soup.find_all('a', href=True):
        href = a['href']
        if not href.startswith('http'):
            href = urljoin(base_url, href)
        if INVESTOR_ARTICLE_RE.search(href) and 'theinvestor.vn' in href:
            links.add(href)
    return links


def _get_investor_article_info(html, url):
    """theinvestor.vn 기사 페이지에서 제목/날짜/요약 추출"""
    soup = BeautifulSoup(html, 'lxml')

    # 제목
    title = ''
    for sel in ['h1.article-title', 'h1', 'meta[property="og:title"]']:
        el = soup.select_one(sel)
        if el:
            title = el.get('content', '') or el.get_text(strip=True)
            if title:
                break

    # 날짜 — 여러 위치 시도
    pub_date = None
    for sel in [
        'meta[property="article:published_time"]',
        'time[datetime]',
        '.article-date',
        '.post-date',
        '.date',
    ]:
        el = soup.select_one(sel)
        if el:
            d = el.get('content', '') or el.get('datetime', '') or el.get_text(strip=True)
            pub_date = parse_date_str(d)
            if pub_date:
                break

    # 요약/본문 앞부분
    summary = ''
    for sel in [
        'meta[property="og:description"]',
        'meta[name="description"]',
        '.article-sapo',
        '.article-excerpt',
        'p:first-of-type',
    ]:
        el = soup.select_one(sel)
        if el:
            summary = el.get('content', '') or el.get_text(strip=True)
            if len(summary) > 30:
                break

    return title, pub_date, summary[:500]


def scrape_theinvestor(from_date_dt, existing_urls, dry_run=False):
    """theinvestor.vn 크롤러"""
    log("[1/2] theinvestor.vn 크롤링 시작")
    articles = []
    seen_urls = set(existing_urls)

    for cat_url in INVESTOR_CATEGORIES:
        cat_name = cat_url.rstrip('/').split('/')[-1]
        log(f"  카테고리: {cat_name}")
        stop = False

        for page in range(1, MAX_PAGES + 1):
            # 페이지네이션: ?page=N 시도
            page_url = cat_url if page == 1 else f"{cat_url}?page={page}"
            html = fetch_page(page_url)
            if not html:
                break

            links = _get_investor_article_links(html, cat_url)
            if not links:
                break

            page_arts = 0
            for art_url in links:
                if art_url in seen_urls:
                    continue
                seen_urls.add(art_url)

                time.sleep(DELAY * 0.5)
                art_html = fetch_page(art_url)
                if not art_html:
                    continue

                title, pub_dt, summary = _get_investor_article_info(art_html, art_url)

                if not title or len(title) < MIN_TITLE:
                    continue

                # 날짜 필터
                if pub_dt:
                    if pub_dt < from_date_dt:
                        stop = True
                        continue
                    date_str = pub_dt.strftime('%Y-%m-%d')
                else:
                    date_str = datetime.now().strftime('%Y-%m-%d')

                articles.append({
                    'url':            art_url,
                    'title':          title,
                    'summary':        summary,
                    'source':         'The Investor',
                    'source_name':    'The Investor',
                    'published_date': date_str,
                    'date':           date_str,
                })
                page_arts += 1
                if not dry_run:
                    log(f"    [{date_str}] {title[:55]}")

            log(f"    page {page}: {len(links)}링크 → {page_arts}건")
            if stop:
                log(f"    {from_date_dt.date()} 이전 도달 → 다음 카테고리")
                break

            time.sleep(DELAY)

    log(f"  theinvestor.vn 완료: {len(articles)}건")
    return articles


# ============================================================
# SITE 2 — vir.com.vn
# ============================================================

# 검색에서 확인한 실제 URL 패턴: /기사제목-숫자.html
VIR_CATEGORIES = [
    "https://vir.com.vn/infrastructure.html",
    "https://vir.com.vn/energy.html",
    "https://vir.com.vn/industrial-zones.html",
    "https://vir.com.vn/real-estate.html",
    "https://vir.com.vn/environment.html",
]

VIR_ARTICLE_RE = re.compile(r'/[a-z0-9-]+-\d+\.html$')


def _get_vir_article_links(html, base_url):
    """vir.com.vn 카테고리 페이지에서 기사 링크 추출"""
    soup = BeautifulSoup(html, 'lxml')
    links = set()
    for a in soup.find_all('a', href=True):
        href = a['href']
        if not href.startswith('http'):
            href = urljoin(base_url, href)
        if VIR_ARTICLE_RE.search(href) and 'vir.com.vn' in href:
            # 카테고리 자체 URL 제외
            if not href.endswith(('.html',)) or href.count('/') < 4:
                continue
            links.add(href)
    return links


def _get_vir_article_info(html, url):
    """vir.com.vn 기사 페이지에서 제목/날짜/요약 추출"""
    soup = BeautifulSoup(html, 'lxml')

    title = ''
    for sel in ['h1.cms-title', 'h1', 'meta[property="og:title"]']:
        el = soup.select_one(sel)
        if el:
            title = el.get('content', '') or el.get_text(strip=True)
            if title:
                break

    pub_date = None
    for sel in [
        'meta[property="article:published_time"]',
        'time[datetime]',
        '.cms-date',
        'span.date',
    ]:
        el = soup.select_one(sel)
        if el:
            d = el.get('content', '') or el.get('datetime', '') or el.get_text(strip=True)
            pub_date = parse_date_str(d)
            if pub_date:
                break

    # 날짜가 없으면 URL이나 페이지 텍스트에서 추출 시도
    if not pub_date:
        date_pattern = re.search(
            r'(\d{4})-(\d{2})-(\d{2})|(\w+ \d+, \d{4})', html
        )
        if date_pattern:
            pub_date = parse_date_str(date_pattern.group(0))

    summary = ''
    for sel in [
        'meta[property="og:description"]',
        'meta[name="description"]',
        '.cms-sapo',
        '.article-sapo',
    ]:
        el = soup.select_one(sel)
        if el:
            summary = el.get('content', '') or el.get_text(strip=True)
            if len(summary) > 30:
                break

    return title, pub_date, summary[:500]


def scrape_vir(from_date_dt, existing_urls, dry_run=False):
    """vir.com.vn 크롤러"""
    log("[2/2] vir.com.vn 크롤링 시작")
    articles = []
    seen_urls = set(existing_urls)

    for cat_url in VIR_CATEGORIES:
        cat_name = cat_url.rstrip('/').split('/')[-1].replace('.html', '')
        log(f"  카테고리: {cat_name}")
        stop = False

        for page in range(1, MAX_PAGES + 1):
            # vir 페이지네이션: ?start=N
            page_url = cat_url if page == 1 else f"{cat_url}?start={page * 10}"
            html = fetch_page(page_url)
            if not html:
                break

            links = _get_vir_article_links(html, cat_url)
            if not links:
                break

            page_arts = 0
            for art_url in links:
                if art_url in seen_urls:
                    continue
                seen_urls.add(art_url)

                time.sleep(DELAY * 0.5)
                art_html = fetch_page(art_url)
                if not art_html:
                    continue

                title, pub_dt, summary = _get_vir_article_info(art_html, art_url)

                if not title or len(title) < MIN_TITLE:
                    continue

                if pub_dt:
                    if pub_dt < from_date_dt:
                        stop = True
                        continue
                    date_str = pub_dt.strftime('%Y-%m-%d')
                else:
                    date_str = datetime.now().strftime('%Y-%m-%d')

                articles.append({
                    'url':            art_url,
                    'title':          title,
                    'summary':        summary,
                    'source':         'Vietnam Investment Review',
                    'source_name':    'Vietnam Investment Review',
                    'published_date': date_str,
                    'date':           date_str,
                })
                page_arts += 1
                if not dry_run:
                    log(f"    [{date_str}] {title[:55]}")

            log(f"    page {page}: {len(links)}링크 → {page_arts}건")
            if stop:
                log(f"    {from_date_dt.date()} 이전 도달 → 다음 카테고리")
                break

            time.sleep(DELAY)

    log(f"  vir.com.vn 완료: {len(articles)}건")
    return articles


# ============================================================
# 분류 및 저장
# ============================================================

def classify_and_save(articles, dry_run=False):
    """
    수집된 기사를 분류 → 번역 → 저장
    news_collector.py 함수 재사용
    """
    if not articles:
        log("수집된 기사 없음")
        return 0

    log(f"\n분류 중... {len(articles)}건")
    classified = []
    for art in articles:
        title   = art.get('title', '')
        summary = art.get('summary', '')

        if not PIPELINE_OK:
            art['sector']   = 'Unknown'
            art['area']     = ''
            art['province'] = 'Vietnam'
            classified.append(art)
            continue

        sector, area, confidence = classify_sector(title, summary)
        if not sector:
            log(f"  [SKIP 미분류] {title[:45]}")
            continue

        province = extract_province(title, summary)
        art.update({
            'sector':     sector,
            'area':       area,
            'province':   province,
            'confidence': confidence,
        })
        classified.append(art)
        log(f"  [{sector}|{confidence}%] [{province}] {title[:45]}")

    log(f"분류 완료: {len(classified)}건 / {len(articles)}건")

    if not classified or dry_run:
        if dry_run:
            log("[Dry-run] 저장 생략")
            out = Path('data/agent_output')
            out.mkdir(parents=True, exist_ok=True)
            with open(out / 'crawler_dryrun.json', 'w', encoding='utf-8') as f:
                json.dump({'count': len(classified), 'articles': classified[:5]},
                          f, ensure_ascii=False, indent=2)
        return len(classified)

    # 번역
    if PIPELINE_OK:
        log(f"\n번역 중... {len(classified)}건")
        classified = translate_articles(classified)

    # SQLite + Excel 저장
    if PIPELINE_OK:
        conn = init_database(DB_PATH)
        saved = 0
        for art in classified:
            if save_article(conn, art):
                saved += 1
        conn.close()
        log(f"SQLite 저장: {saved}건")

    # collector_output.json 으로 내보내기 (run_excel_updater가 읽음)
    out_dir = Path('data/agent_output')
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / 'collector_output.json'

    # 기존 output에 병합
    existing_arts = []
    if out_path.exists():
        try:
            with open(out_path, 'r', encoding='utf-8') as f:
                existing_arts = json.load(f).get('articles', [])
        except Exception:
            pass

    merged = existing_arts + classified
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump({
            'run_timestamp':   datetime.utcnow().isoformat() + 'Z',
            'source':          'specialist_crawler v4.0',
            'total_collected': len(merged),
            'articles':        merged,
        }, f, ensure_ascii=False, indent=2)
    log(f"collector_output.json 저장: {len(classified)}건 추가")

    return len(classified)


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='전문미디어 크롤러 v4.0')
    parser.add_argument('--from-date', default='2025-01-01',
                        help='수집 시작 날짜 (기본: 2025-01-01)')
    parser.add_argument('--dry-run',   action='store_true',
                        help='수집만 하고 저장하지 않음')
    parser.add_argument('--sites',     nargs='+',
                        choices=['investor', 'vir'],
                        help='특정 사이트만 실행 (기본: 모두)')
    args = parser.parse_args()

    from_date_dt = datetime.strptime(args.from_date, '%Y-%m-%d')
    sites = args.sites or ['investor', 'vir']

    log('=' * 60)
    log(f"전문미디어 크롤러 v4.0")
    log(f"from_date: {args.from_date} | dry_run: {args.dry_run}")
    log(f"대상 사이트: {sites}")
    log('=' * 60)

    # 기존 URL 로드
    existing_urls = load_existing_urls()

    all_articles = []

    if 'investor' in sites:
        arts = scrape_theinvestor(from_date_dt, existing_urls, args.dry_run)
        all_articles.extend(arts)
        time.sleep(DELAY)

    if 'vir' in sites:
        arts = scrape_vir(from_date_dt, existing_urls, args.dry_run)
        all_articles.extend(arts)

    log(f"\n총 수집: {len(all_articles)}건")

    saved = classify_and_save(all_articles, args.dry_run)

    log('=' * 60)
    log(f"크롤러 완료: {saved}건 처리")
    log('=' * 60)

    return saved


if __name__ == '__main__':
    main()
