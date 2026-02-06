#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News - Dashboard Updater
Loads from BOTH Excel (historical) AND SQLite (new collected) databases.
"""

import json
import logging
import sys
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

# Setup paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
TEMPLATE_DIR = PROJECT_ROOT / "templates"

sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Database paths
EXCEL_DB_PATH = DATA_DIR / "database" / "Vietnam_Infra_News_Database_Final.xlsx"
SQLITE_DB_PATH = DATA_DIR / "vietnam_infrastructure_news.db"

# Template paths
TEMPLATE_HEADER = TEMPLATE_DIR / "dashboard_template_header.html"
TEMPLATE_FOOTER = TEMPLATE_DIR / "dashboard_template_footer.html"


def load_articles_from_sqlite():
    """Load articles from SQLite database (newly collected)"""
    if not SQLITE_DB_PATH.exists():
        logger.info(f"SQLite DB not found: {SQLITE_DB_PATH}")
        return []
    
    logger.info(f"Loading from SQLite: {SQLITE_DB_PATH}")
    
    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, url, title, title_vi, title_ko, 
                   summary, summary_vi, summary_ko,
                   source, sector, area, province, 
                   published_date, collected_date
            FROM articles
            ORDER BY published_date DESC
        """)
        
        articles = []
        for row in cursor.fetchall():
            # Parse date
            date_str = row['published_date'] or row['collected_date'] or ''
            if date_str:
                date_str = date_str[:10]  # Get YYYY-MM-DD part
            
            articles.append({
                "id": row['id'],
                "date": date_str,
                "area": row['area'] or "Environment",
                "sector": row['sector'] or "Infrastructure",
                "province": row['province'] or "Vietnam",
                "source": row['source'] or "",
                "title": row['title'] or "",
                "title_ko": row['title_ko'] or "",
                "title_vi": row['title_vi'] or "",
                "summary": row['summary'] or "",
                "summary_ko": row['summary_ko'] or "",
                "summary_vi": row['summary_vi'] or "",
                "url": row['url'] or "",
                "from_sqlite": True  # Mark as newly collected
            })
        
        conn.close()
        logger.info(f"Loaded {len(articles)} articles from SQLite")
        return articles
        
    except Exception as e:
        logger.error(f"Error loading SQLite: {e}")
        import traceback
        traceback.print_exc()
        return []


def load_articles_from_excel():
    """Load ALL articles from Excel database (historical)"""
    try:
        import openpyxl
    except ImportError:
        logger.error("openpyxl not installed")
        return []
    
    if not EXCEL_DB_PATH.exists():
        logger.warning(f"Excel database not found: {EXCEL_DB_PATH}")
        return []
    
    logger.info(f"Loading from Excel: {EXCEL_DB_PATH}")
    
    try:
        wb = openpyxl.load_workbook(EXCEL_DB_PATH, read_only=True, data_only=True)
        
        logger.info(f"Available sheets: {wb.sheetnames}")
        
        # Find the News data sheet (not Summary or other sheets)
        ws = None
        
        # Priority 1: Look for sheet named "News"
        for sheet_name in wb.sheetnames:
            if sheet_name.lower() == 'news':
                ws = wb[sheet_name]
                logger.info(f"Using sheet: {sheet_name}")
                break
        
        # Priority 2: Look for sheet with "Area" header (main data sheet)
        if ws is None:
            for sheet_name in wb.sheetnames:
                if 'summary' in sheet_name.lower() or 'rss' in sheet_name.lower() or 'keyword' in sheet_name.lower() or 'log' in sheet_name.lower():
                    continue
                test_ws = wb[sheet_name]
                try:
                    first_row = [cell.value for cell in test_ws[1]]
                    # Check for expected headers: Area, Business Sector, Province, News Tittle, Date
                    if any(h and str(h).strip() == 'Area' for h in first_row):
                        ws = test_ws
                        logger.info(f"Using sheet with Area header: {sheet_name}")
                        break
                except:
                    continue
        
        # Priority 3: Use first sheet that's not Summary/RSS/Keywords/Log
        if ws is None:
            for sheet_name in wb.sheetnames:
                if 'summary' not in sheet_name.lower() and 'rss' not in sheet_name.lower() and 'keyword' not in sheet_name.lower() and 'log' not in sheet_name.lower():
                    ws = wb[sheet_name]
                    logger.info(f"Using fallback sheet: {sheet_name}")
                    break
        
        if ws is None:
            ws = wb.active
            logger.warning(f"Using active sheet as last fallback: {ws.title}")
        
        headers = [cell.value for cell in ws[1]]
        col_map = {str(h).strip(): i for i, h in enumerate(headers) if h}
        
        logger.info(f"Excel headers: {list(col_map.keys())}")
        
        # Helper function to safely get column value
        def safe_get(row, col_name, default_idx, default_val=""):
            idx = col_map.get(col_name, default_idx)
            if idx < len(row):
                return row[idx] if row[idx] is not None else default_val
            return default_val
        
        articles = []
        for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if not any(row):
                continue
            
            # Safely get date
            date_idx = col_map.get("Date", 4)
            date_val = row[date_idx] if date_idx < len(row) else None
            if date_val:
                if hasattr(date_val, 'strftime'):
                    date_str = date_val.strftime("%Y-%m-%d")
                else:
                    date_str = str(date_val)[:10]
            else:
                date_str = ""
            
            area = safe_get(row, "Area", 0, "Environment")
            sector = safe_get(row, "Business Sector", 1, "Unknown")
            province = safe_get(row, "Province", 2, "Vietnam")
            title = str(safe_get(row, "News Tittle", 3, ""))
            source = safe_get(row, "Source", 5, "")
            url = safe_get(row, "Link", 6, "")
            summary = str(safe_get(row, "Short summary", 7, ""))
            
            if not title and not url:
                continue
            
            articles.append({
                "id": len(articles) + 1,
                "date": date_str,
                "area": area,
                "sector": sector,
                "province": province,
                "source": source,
                "title": title,
                "summary": summary,
                "url": url,
                "from_sqlite": False
            })
        
        wb.close()
        logger.info(f"Loaded {len(articles)} articles from Excel")
        return articles
        
    except Exception as e:
        logger.error(f"Error loading Excel: {e}")
        import traceback
        traceback.print_exc()
        return []


def merge_articles(excel_articles, sqlite_articles):
    """Merge articles from both sources, removing duplicates"""
    
    # Debug: Count 2026 articles before merge
    excel_2026 = [a for a in excel_articles if a.get('date', '').startswith('2026')]
    sqlite_2026 = [a for a in sqlite_articles if a.get('date', '').startswith('2026')]
    logger.info(f"Before merge - Excel 2026 articles: {len(excel_2026)}, SQLite 2026: {len(sqlite_2026)}")
    
    # Create URL set for deduplication
    seen_urls = set()
    seen_titles = set()
    merged = []
    
    # Add SQLite articles first (newer, higher priority)
    for article in sqlite_articles:
        url = article.get('url', '')
        title = article.get('title', '')
        if url and url not in seen_urls:
            seen_urls.add(url)
            if title:
                seen_titles.add(title)
            merged.append(article)
        elif not url and title and title not in seen_titles:
            seen_titles.add(title)
            merged.append(article)
    
    # Add Excel articles (skip duplicates)
    skipped_no_url = 0
    skipped_dup_url = 0
    skipped_dup_title = 0
    skipped_2026 = []
    
    for article in excel_articles:
        url = article.get('url', '')
        title = article.get('title', '')
        date = article.get('date', '')
        
        if url:
            if url not in seen_urls:
                seen_urls.add(url)
                if title:
                    seen_titles.add(title)
                merged.append(article)
            else:
                skipped_dup_url += 1
                if date.startswith('2026'):
                    skipped_2026.append(f"URL dup: {title[:50]}")
        else:
            # No URL - check by title
            if title and title not in seen_titles:
                seen_titles.add(title)
                merged.append(article)
            elif title:
                skipped_dup_title += 1
                if date.startswith('2026'):
                    skipped_2026.append(f"Title dup: {title[:50]}")
            else:
                skipped_no_url += 1
                if date.startswith('2026'):
                    skipped_2026.append(f"No URL/title: {date}")
    
    logger.info(f"Merge stats: skipped {skipped_dup_url} dup URLs, {skipped_dup_title} dup titles, {skipped_no_url} no URL/title")
    
    # Debug: Count 2026 articles after merge
    merged_2026 = [a for a in merged if a.get('date', '').startswith('2026')]
    logger.info(f"After merge - 2026 articles: {len(merged_2026)}")
    if skipped_2026:
        logger.info(f"Skipped 2026 articles: {skipped_2026[:5]}")  # Show first 5
    
    # Sort by date (newest first)
    merged.sort(key=lambda x: x.get('date', ''), reverse=True)
    
    # Re-assign IDs
    for i, article in enumerate(merged):
        article['id'] = i + 1
    
    return merged


def convert_to_multilingual_format(articles):
    """Convert articles to multilingual format for BACKEND_DATA."""
    result = []
    
    SECTOR_KO = {
        "Waste Water": "폐수처리",
        "Solid Waste": "고형폐기물",
        "Water Supply/Drainage": "상수도/배수",
        "Power": "발전/전력",
        "Oil & Gas": "석유/가스",
        "Industrial Parks": "산업단지",
        "Smart City": "스마트시티",
        "Urban Development": "도시개발",
        "Transport": "교통인프라",
        "Climate Change": "기후변화"
    }
    
    SECTOR_VI = {
        "Waste Water": "Xử lý nước thải",
        "Solid Waste": "Chất thải rắn",
        "Water Supply/Drainage": "Cấp thoát nước",
        "Power": "Điện năng",
        "Oil & Gas": "Dầu khí",
        "Industrial Parks": "Khu công nghiệp",
        "Smart City": "Thành phố thông minh",
        "Urban Development": "Phát triển đô thị",
        "Transport": "Giao thông",
        "Climate Change": "Biến đổi khí hậu"
    }
    
    for article in articles:
        title = article.get("title", "")
        summary = article.get("summary", "")
        sector = article.get("sector", "Infrastructure")
        province = article.get("province", "Vietnam")
        
        sector_ko = SECTOR_KO.get(sector, sector)
        sector_vi = SECTOR_VI.get(sector, sector)
        
        # Check if article has translations from SQLite
        title_ko = article.get("title_ko") or title
        title_vi = article.get("title_vi") or title
        title_en = title
        
        summary_ko = article.get("summary_ko") or f"[{sector_ko}] {province}: {title[:100]}"
        summary_vi = article.get("summary_vi") or f"[{sector_vi}] {province}: {title[:100]}"
        summary_en = summary if summary else f"[{sector}] {province}: {title[:100]}"
        
        result.append({
            "id": article.get("id", len(result) + 1),
            "date": article.get("date", ""),
            "area": article.get("area", "Environment"),
            "sector": sector,
            "province": province,
            "source": article.get("source", ""),
            "title": {
                "ko": title_ko,
                "en": title_en,
                "vi": title_vi
            },
            "summary": {
                "ko": summary_ko,
                "en": summary_en,
                "vi": summary_vi
            },
            "url": article.get("url", ""),
            "is_new": article.get("from_sqlite", False)
        })
    
    return result


def generate_dashboard(articles):
    """Generate dashboard HTML"""
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    backend_data = convert_to_multilingual_format(articles)
    backend_data.sort(key=lambda x: x.get("date", ""), reverse=True)
    backend_json = json.dumps(backend_data, ensure_ascii=False, indent=2)
    
    if TEMPLATE_HEADER.exists() and TEMPLATE_FOOTER.exists():
        logger.info("Using template files")
        
        with open(TEMPLATE_HEADER, 'r', encoding='utf-8') as f:
            header = f.read()
        
        with open(TEMPLATE_FOOTER, 'r', encoding='utf-8') as f:
            footer = f.read()
        
        html = header + f"\nconst BACKEND_DATA = {backend_json};\n" + footer
    else:
        logger.info("Template not found, generating minimal dashboard")
        html = generate_minimal_dashboard(backend_data, backend_json)
    
    index_path = OUTPUT_DIR / "index.html"
    dashboard_path = OUTPUT_DIR / "vietnam_dashboard.html"
    
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(html)
    logger.info(f"Saved: {index_path} ({index_path.stat().st_size:,} bytes)")
    
    with open(dashboard_path, 'w', encoding='utf-8') as f:
        f.write(html)
    logger.info(f"Saved: {dashboard_path}")
    
    # Count today's and recent articles
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    today_count = sum(1 for a in backend_data if a.get("date") == today)
    yesterday_count = sum(1 for a in backend_data if a.get("date") == yesterday)
    new_count = sum(1 for a in backend_data if a.get("is_new", False))
    
    json_path = OUTPUT_DIR / f"news_data_{datetime.now().strftime('%Y%m%d')}.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "total": len(backend_data),
            "today_articles": today_count,
            "yesterday_articles": yesterday_count,
            "new_from_collector": new_count
        }, f, indent=2)
    
    logger.info(f"Today's articles: {today_count}")
    logger.info(f"Yesterday's articles: {yesterday_count}")
    logger.info(f"New from collector: {new_count}")
    
    return str(index_path)


def generate_minimal_dashboard(articles, backend_json):
    """Generate minimal dashboard when template is not available"""
    
    today = datetime.now().strftime("%Y-%m-%d")
    total = len(articles)
    today_count = sum(1 for a in articles if a.get("date") == today)
    new_count = sum(1 for a in articles if a.get("is_new", False))
    
    html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vietnam Infrastructure News Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        * {{ font-family: 'Noto Sans KR', sans-serif; }}
        .lang-btn.active {{ background: linear-gradient(135deg, #0F766E, #14B8A6); color: white; }}
        .sector-env {{ background: linear-gradient(135deg, #059669, #10B981); }}
        .sector-energy {{ background: linear-gradient(135deg, #D97706, #F59E0B); }}
        .sector-urban {{ background: linear-gradient(135deg, #7C3AED, #8B5CF6); }}
        .new-badge {{ background: #EF4444; color: white; animation: pulse 2s infinite; }}
        @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.7; }} }}
    </style>
</head>
<body class="bg-gradient-to-br from-slate-50 to-teal-50/30 min-h-screen">

<header class="sticky top-0 z-50 bg-white/90 backdrop-blur border-b border-slate-200">
    <div class="max-w-7xl mx-auto px-4 py-3">
        <div class="flex items-center justify-between">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 bg-gradient-to-br from-teal-600 to-emerald-500 rounded-lg flex items-center justify-center text-white text-xl">🏗️</div>
                <div>
                    <h1 class="text-lg font-bold text-slate-800">Vietnam Infra News</h1>
                    <p class="text-xs text-slate-500">Updated: {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
                </div>
            </div>
            <div class="flex gap-1 bg-slate-100 rounded-lg p-0.5">
                <button onclick="setLang('ko')" class="lang-btn active px-3 py-1.5 rounded text-sm font-medium" data-lang="ko">🇰🇷 한국어</button>
                <button onclick="setLang('en')" class="lang-btn px-3 py-1.5 rounded text-sm font-medium text-slate-600" data-lang="en">🇺🇸 EN</button>
                <button onclick="setLang('vi')" class="lang-btn px-3 py-1.5 rounded text-sm font-medium text-slate-600" data-lang="vi">🇻🇳 VI</button>
            </div>
        </div>
    </div>
</header>

<main class="max-w-7xl mx-auto px-4 py-6">
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div class="bg-white rounded-xl p-4 shadow-sm border">
            <div class="text-2xl font-bold text-red-500">{new_count}</div>
            <div class="text-sm text-slate-500">🆕 신규 수집</div>
        </div>
        <div class="bg-white rounded-xl p-4 shadow-sm border">
            <div class="text-2xl font-bold text-teal-600">{today_count}</div>
            <div class="text-sm text-slate-500">오늘</div>
        </div>
        <div class="bg-white rounded-xl p-4 shadow-sm border">
            <div class="text-2xl font-bold text-blue-600">{total:,}</div>
            <div class="text-sm text-slate-500">전체 DB</div>
        </div>
    </div>
    
    <div class="bg-white rounded-xl shadow-lg overflow-hidden">
        <div class="bg-gradient-to-r from-teal-700 to-emerald-600 px-4 py-3">
            <span class="text-white font-bold">📰 뉴스 목록</span>
            <span class="text-teal-100 text-sm ml-2" id="news-count">{total}건</span>
        </div>
        <div id="news-list" class="max-h-[600px] overflow-y-auto"></div>
    </div>
</main>

<script>
const BACKEND_DATA = {backend_json};

let lang = 'ko';

function setLang(l) {{
    lang = l;
    document.querySelectorAll('.lang-btn').forEach(btn => {{
        btn.classList.toggle('active', btn.dataset.lang === l);
    }});
    renderNews();
}}

function getText(obj) {{
    if (!obj) return '';
    if (typeof obj === 'string') return obj;
    return obj[lang] || obj.en || obj.ko || obj.vi || '';
}}

function getSectorColor(area) {{
    if (area === 'Environment') return 'sector-env';
    if (area === 'Energy Develop.' || area === 'Energy') return 'sector-energy';
    return 'sector-urban';
}}

function renderNews() {{
    const container = document.getElementById('news-list');
    container.innerHTML = BACKEND_DATA.slice(0, 100).map(n => `
        <div class="px-4 py-3 border-b hover:bg-slate-50">
            <div class="flex items-center gap-2 mb-1">
                ${{n.is_new ? '<span class="new-badge px-1.5 py-0.5 rounded text-xs font-bold">NEW</span>' : ''}}
                <span class="px-2 py-0.5 rounded text-xs font-semibold text-white ${{getSectorColor(n.area)}}">${{n.sector}}</span>
                <span class="text-xs text-slate-500">${{n.date}}</span>
                <span class="text-xs text-slate-400">${{n.source}}</span>
            </div>
            <h3 class="font-medium text-slate-800">${{getText(n.title)}}</h3>
            <p class="text-sm text-slate-600 mt-1">${{getText(n.summary).slice(0, 150)}}...</p>
            <a href="${{n.url}}" target="_blank" class="text-xs text-teal-600 hover:underline mt-1 inline-block">원문보기 →</a>
        </div>
    `).join('');
}}

renderNews();
</script>
</body>
</html>'''
    
    return html


def main():
    """Main function - loads from BOTH Excel and SQLite"""
    print("=" * 60)
    print("DASHBOARD GENERATOR (Merged Sources)")
    print("=" * 60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Excel DB: {EXCEL_DB_PATH}")
    print(f"SQLite DB: {SQLITE_DB_PATH}")
    
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load from both sources
    excel_articles = load_articles_from_excel()
    sqlite_articles = load_articles_from_sqlite()
    
    print(f"\nExcel articles: {len(excel_articles)}")
    print(f"SQLite articles (new): {len(sqlite_articles)}")
    
    # Merge articles
    all_articles = merge_articles(excel_articles, sqlite_articles)
    print(f"Total merged: {len(all_articles)}")
    
    # Generate dashboard
    result = generate_dashboard(all_articles)
    
    index_path = OUTPUT_DIR / "index.html"
    if index_path.exists():
        print(f"\n✓ Dashboard created: {index_path}")
        print(f"  Size: {index_path.stat().st_size:,} bytes")
    
    print("\nDone!")


if __name__ == "__main__":
    main()
