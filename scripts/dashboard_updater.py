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
    """
    Convert articles to multilingual format for BACKEND_DATA.
    
    다국어 처리 전략:
    - 신규 기사 (SQLite): ai_summarizer가 생성한 summary_ko/vi 사용
    - 기존 기사 (Excel): summary_ko가 없으면 구조화 fallback 생성
    - title_ko/vi: AI 번역 있으면 사용, 없으면 EN 원문 유지
      (KO 버튼 = 한국어 요약 표시 / title은 EN 원문으로 표시)
    - summary_en이 있는 기사는 RSS description 활용
    """
    result = []

    SECTOR_KO = {
        "Waste Water": "폐수처리",
        "Water Supply/Drainage": "상수도/배수",
        "Solid Waste": "고형폐기물",
        "Power": "발전/전력",
        "Oil & Gas": "석유/가스",
        "Transport": "교통인프라",
        "Industrial Parks": "산업단지",
        "Smart City": "스마트시티",
        "Construction": "건설/도시개발",
        "Urban Development": "도시개발",
        "Climate Change": "기후변화",
    }
    SECTOR_VI = {
        "Waste Water": "Xử lý nước thải",
        "Water Supply/Drainage": "Cấp thoát nước",
        "Solid Waste": "Chất thải rắn",
        "Power": "Điện năng",
        "Oil & Gas": "Dầu khí",
        "Transport": "Giao thông",
        "Industrial Parks": "Khu công nghiệp",
        "Smart City": "Thành phố thông minh",
        "Construction": "Xây dựng",
        "Urban Development": "Phát triển đô thị",
        "Climate Change": "Biến đổi khí hậu",
    }

    for article in articles:
        title   = str(article.get("title", "") or "")
        summary = str(article.get("summary", "") or "")
        sector  = article.get("sector", "Infrastructure")
        province = article.get("province", "Vietnam")
        area    = article.get("area", "Environment")

        sector_ko = SECTOR_KO.get(sector, sector)
        sector_vi = SECTOR_VI.get(sector, sector)

        # ── title 처리 ──────────────────────────────────────────
        # EN: 항상 원문 사용
        title_en = title

        # KO: AI 번역이 있고 원문과 다르면 사용, 없으면 원문 (EN)
        raw_ko = str(article.get("title_ko") or "").strip()
        title_ko = raw_ko if (raw_ko and raw_ko != title) else title

        # VI: AI 번역이 있고 원문과 다르면 사용, 없으면 원문 (EN)
        raw_vi = str(article.get("title_vi") or "").strip()
        title_vi = raw_vi if (raw_vi and raw_vi != title) else title

        # ── summary 처리 ────────────────────────────────────────
        # EN: RSS summary 우선, 없으면 구조화 fallback
        raw_sum_en = str(article.get("summary_en") or summary or "").strip()
        if raw_sum_en and len(raw_sum_en) > 20:
            summary_en = raw_sum_en[:300]
        else:
            summary_en = f"[{sector}] Infrastructure project in {province}: {title[:100]}"

        # KO: AI 번역 우선, 없으면 구조화 fallback
        # fallback 형식: [섹터KO] Province 지역 — 원문제목 (단순 반복 방지)
        raw_sum_ko = str(article.get("summary_ko") or "").strip()
        if raw_sum_ko and not raw_sum_ko.startswith(f"[{sector_ko}] {province}"):
            summary_ko = raw_sum_ko[:300]
        else:
            # summary_en이 있으면 언급하여 한국어 맥락 제공
            summary_ko = f"[{sector_ko}] {province} 인프라 프로젝트. {title[:120]}"

        # VI: AI 번역 우선, 없으면 구조화 fallback
        raw_sum_vi = str(article.get("summary_vi") or "").strip()
        if raw_sum_vi and not raw_sum_vi.startswith(f"[{sector_vi}] {province}"):
            summary_vi = raw_sum_vi[:300]
        else:
            summary_vi = f"[{sector_vi}] Dự án hạ tầng tại {province}. {title[:120]}"

        result.append({
            "id":       article.get("id", len(result) + 1),
            "date":     str(article.get("date", "") or ""),
            "area":     area,
            "sector":   sector,
            "province": province,
            "source":   str(article.get("source", "") or ""),
            "title": {
                "ko": title_ko,
                "en": title_en,
                "vi": title_vi,
            },
            "summary": {
                "ko": summary_ko,
                "en": summary_en,
                "vi": summary_vi,
            },
            "url":    str(article.get("url", "") or ""),
            "is_new": bool(article.get("from_sqlite", False)),
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
    // 선택된 언어로 번역이 있으면 사용, 없으면 영어, 없으면 어떤 언어든 반환
    return obj[lang] || obj.en || obj.ko || obj.vi || '';
}}

function getTitleDisplay(n) {{
    // title: AI 번역 있으면 해당 언어, 없으면 영어 원문 + [번역중] 표시
    const t = getText(n.title);
    if (lang !== 'en' && n.title && n.title[lang] && n.title[lang] !== n.title['en']) {{
        return n.title[lang];  // 실제 번역된 제목
    }}
    return n.title ? (n.title.en || n.title.vi || n.title.ko || '') : '';
}}

function getSummaryDisplay(n) {{
    const s = n.summary || {{}};
    if (lang === 'ko' && s.ko) return s.ko;
    if (lang === 'vi' && s.vi) return s.vi;
    if (lang === 'en' && s.en) return s.en;
    // fallback: 어떤 언어든 있는 것 반환
    return s.en || s.ko || s.vi || '';
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
            <h3 class="font-medium text-slate-800">${{getTitleDisplay(n)}}</h3>
            <p class="text-sm text-slate-600 mt-1">${{getSummaryDisplay(n).slice(0, 180)}}${{getSummaryDisplay(n).length > 180 ? '...' : ''}}</p>
            <a href="${{n.url}}" target="_blank" class="text-xs text-teal-600 hover:underline mt-1 inline-block">원문보기 →</a>
        </div>
    `).join('');
}}

renderNews();
</script>
</body>
</html>'''
    
    return html



# ============================================================
# DashboardUpdater & ExcelUpdater 클래스
# main.py에서 module.DashboardUpdater() / module.ExcelUpdater() 로 호출됨
# ============================================================

class DashboardUpdater:
    """대시보드 HTML 생성 클래스 — main.py 호환"""

    def update(self, articles):
        """
        articles 리스트를 받아 index.html + vietnam_dashboard.html 생성.
        템플릿이 있으면 템플릿 사용, 없으면 내장 HTML 사용.
        """
        try:
            # Excel + SQLite 통합 로드 (전체 히스토리 포함)
            excel_arts  = load_articles_from_excel()
            sqlite_arts = load_articles_from_sqlite()
            all_arts    = merge_articles(excel_arts, sqlite_arts)

            # 전달받은 신규 기사를 is_new=True로 마킹
            new_urls = {a.get('url','') for a in articles}
            for a in all_arts:
                if a.get('url','') in new_urls:
                    a['from_sqlite'] = True

            logger.info(f"DashboardUpdater: {len(all_arts)} total articles "
                        f"({len(excel_arts)} Excel + {len(sqlite_arts)} SQLite)")
            result = generate_dashboard(all_arts)
            logger.info(f"Dashboard generated: {result}")
            return result
        except Exception as e:
            logger.error(f"DashboardUpdater.update error: {e}")
            import traceback; traceback.print_exc()
            return None


class ExcelUpdater:
    """Excel DB 업데이트 클래스 — main.py 호환"""

    def update(self, articles):
        """
        신규 기사를 Excel DB에 추가.
        news_collector.py의 update_excel_database()를 재사용.
        """
        if not articles:
            logger.info("ExcelUpdater: no new articles to add")
            return True

        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
            import shutil
            from collections import Counter

            ep = EXCEL_DB_PATH
            if not ep.exists():
                logger.warning(f"ExcelUpdater: Excel not found: {ep}")
                return False

            # 안전 확인
            wb_c = openpyxl.load_workbook(ep, read_only=True)
            ws_c = wb_c.active
            existing_count = sum(1 for r in ws_c.iter_rows(min_row=2, values_only=True) if any(r))
            wb_c.close()
            if existing_count < 100:
                logger.warning(f"ExcelUpdater safety check failed: {existing_count} rows")
                return False

            shutil.copy2(ep, ep.with_suffix('.xlsx.backup'))

            wb  = openpyxl.load_workbook(ep)
            ws  = wb.active
            last_row = ws.max_row

            # URL 컬럼 찾기
            url_col = 7
            for c in range(1, ws.max_column + 1):
                h = ws.cell(row=1, column=c).value
                if h and "link" in str(h).lower():
                    url_col = c
                    break

            existing_urls = set()
            for row in range(2, last_row + 1):
                v = ws.cell(row=row, column=url_col).value
                if v:
                    existing_urls.add(v)

            # 스타일
            NEW_FILL  = PatternFill(start_color="FFF9C4", end_color="FFF9C4", fill_type="solid")
            NEW_FONT  = Font(bold=True, color="1A1A1A", size=10)
            thin_b    = Border(bottom=Side(style='thin', color='E2E8F0'))

            col_map = {'area':1,'sector':2,'province':3,'title':4,
                       'date':5,'source':6,'url':7,'summary':8}

            added    = 0
            new_urls_set = set()
            for art in articles:
                if art.get('url') in existing_urls:
                    continue
                nr = last_row + 1 + added
                ws.cell(row=nr, column=col_map['area'],     value=art.get('area',''))
                ws.cell(row=nr, column=col_map['sector'],   value=art.get('sector',''))
                ws.cell(row=nr, column=col_map['province'], value=art.get('province','Vietnam'))
                ws.cell(row=nr, column=col_map['title'],    value=art.get('title',''))
                ws.cell(row=nr, column=col_map['date'],     value=(art.get('published_date','') or '')[:10])
                ws.cell(row=nr, column=col_map['source'],   value=art.get('source',''))
                ws.cell(row=nr, column=col_map['url'],      value=art.get('url',''))
                # summary: AI 요약 우선, 없으면 RSS 원문
                summary_val = (art.get('summary_ko') or art.get('summary') or '')[:500]
                ws.cell(row=nr, column=col_map['summary'],  value=summary_val)
                for c in range(1, 9):
                    ws.cell(row=nr, column=c).fill   = NEW_FILL
                    ws.cell(row=nr, column=c).font   = NEW_FONT
                    ws.cell(row=nr, column=c).border = thin_b
                added += 1
                new_urls_set.add(art.get('url'))
                existing_urls.add(art.get('url'))

            # 날짜순 정렬 (최신 → 오래된)
            if added > 0:
                max_row = ws.max_row
                ENV_FILL    = PatternFill(start_color="F0FDF4", end_color="F0FDF4", fill_type="solid")
                ENERGY_FILL = PatternFill(start_color="FFFBEB", end_color="FFFBEB", fill_type="solid")
                URBAN_FILL  = PatternFill(start_color="F5F3FF", end_color="F5F3FF", fill_type="solid")
                PLAIN_FONT  = Font(color="1A1A1A", size=10)

                def _afill(area):
                    a = str(area or '').lower()
                    if 'environment' in a: return ENV_FILL
                    if 'energy' in a:      return ENERGY_FILL
                    return URBAN_FILL

                rows_data = []
                for r in range(2, max_row + 1):
                    vals = [ws.cell(row=r, column=c).value for c in range(1, 9)]
                    date_key = str(vals[4] or '0000-00-00')[:10]
                    url_key  = str(vals[6] or '')
                    rows_data.append({'vals': vals, 'date': date_key,
                                      'is_new': url_key in new_urls_set})

                rows_data.sort(key=lambda x: x['date'], reverse=True)
                for i, rd in enumerate(rows_data, 2):
                    fill = NEW_FILL if rd['is_new'] else _afill(rd['vals'][0])
                    font = NEW_FONT if rd['is_new'] else PLAIN_FONT
                    for c in range(1, 9):
                        cell = ws.cell(row=i, column=c)
                        cell.value  = rd['vals'][c-1]
                        cell.fill   = fill
                        cell.font   = font
                        cell.border = thin_b

            for col, w in zip('ABCDEFGH', [18,22,20,60,12,22,50,60]):
                ws.column_dimensions[col].width = w
            ws.freeze_panes = 'A2'

            # Collection_Log 기록
            from datetime import datetime as _dt
            if "Collection_Log" not in wb.sheetnames:
                ws_log = wb.create_sheet("Collection_Log")
                HDR_FILL = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid")
                HDR_FONT = Font(bold=True, color="FFFFFF")
                for ci, h in enumerate(["Date","Time","Source","New Articles","Total DB"], 1):
                    c = ws_log.cell(row=1, column=ci, value=h)
                    c.fill = HDR_FILL; c.font = HDR_FONT
            else:
                ws_log = wb["Collection_Log"]

            now = _dt.now()
            lr  = ws_log.max_row + 1
            cur_total = sum(1 for r in ws.iter_rows(min_row=2, values_only=True) if any(r))
            ws_log.cell(row=lr, column=1, value=now.strftime("%Y-%m-%d"))
            ws_log.cell(row=lr, column=2, value=now.strftime("%H:%M:%S"))
            ws_log.cell(row=lr, column=3, value="main.py / ExcelUpdater")
            ws_log.cell(row=lr, column=4, value=added)
            ws_log.cell(row=lr, column=5, value=cur_total)
            ws_log.cell(row=lr, column=1).fill = PatternFill(
                start_color="DBEAFE", end_color="DBEAFE", fill_type="solid")

            wb.save(ep)
            wb.close()
            logger.info(f"ExcelUpdater: +{added} new articles (yellow) | total {cur_total} | sorted ↓date")
            return True

        except Exception as e:
            logger.error(f"ExcelUpdater.update error: {e}")
            import traceback; traceback.print_exc()
            return False


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
