#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News - Dashboard Updater
Can be run directly: python dashboard_updater.py
Loads ALL data from Excel and generates complete dashboard
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter
import sys

# Setup paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "outputs"

sys.path.insert(0, str(PROJECT_ROOT))

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

EXCEL_DB_PATH = DATA_DIR / "database" / "Vietnam_Infra_News_Database_Final.xlsx"


def load_all_articles():
    """Load ALL articles from Excel database"""
    if not OPENPYXL_AVAILABLE:
        logger.error("openpyxl not installed")
        return []
    
    if not EXCEL_DB_PATH.exists():
        logger.warning(f"Excel not found: {EXCEL_DB_PATH}")
        return []
    
    logger.info(f"Loading from: {EXCEL_DB_PATH}")
    
    try:
        wb = openpyxl.load_workbook(EXCEL_DB_PATH, read_only=True, data_only=True)
        ws = wb.active
        
        headers = [cell.value for cell in ws[1]]
        col_map = {str(h).strip(): i for i, h in enumerate(headers) if h}
        
        articles = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not any(row):
                continue
            
            # Parse date
            date_val = row[col_map.get("Date", 4)] if "Date" in col_map else None
            if date_val:
                if hasattr(date_val, 'strftime'):
                    date_str = date_val.strftime("%Y-%m-%d")
                else:
                    date_str = str(date_val)[:10]
            else:
                date_str = ""
            
            article = {
                "area": row[col_map.get("Area", 0)] or "Environment",
                "sector": row[col_map.get("Business Sector", 1)] or "Unknown",
                "province": row[col_map.get("Province", 2)] or "Vietnam",
                "title": row[col_map.get("News Tittle", 3)] or "",
                "date": date_str,
                "source": row[col_map.get("Source", 5)] or "",
                "url": row[col_map.get("Link", 6)] or "",
                "summary": row[col_map.get("Short summary", 7)] or "",
            }
            
            if article["title"] or article["url"]:
                articles.append(article)
        
        wb.close()
        
        # Statistics
        year_counts = Counter(a["date"][:4] for a in articles if a["date"])
        sector_counts = Counter(a["sector"] for a in articles)
        
        logger.info(f"Loaded {len(articles)} articles")
        logger.info(f"Years: {dict(sorted(year_counts.items()))}")
        logger.info(f"Sectors: {dict(sector_counts.most_common(5))}")
        
        return articles
        
    except Exception as e:
        logger.error(f"Load error: {e}")
        import traceback
        traceback.print_exc()
        return []


def generate_dashboard_html(articles):
    """Generate complete dashboard HTML"""
    
    today = datetime.now().strftime("%Y-%m-%d")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    # Calculate statistics
    total = len(articles)
    today_count = sum(1 for a in articles if a.get("date") == today)
    
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    week_count = sum(1 for a in articles if a.get("date", "") >= week_ago)
    
    month_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    month_count = sum(1 for a in articles if a.get("date", "") >= month_ago)
    
    # Count by year, sector, source
    year_counts = Counter(a["date"][:4] for a in articles if a.get("date"))
    sector_counts = Counter(a["sector"] for a in articles if a.get("sector"))
    source_counts = Counter(a["source"] for a in articles if a.get("source"))
    
    # Prepare JS data
    js_articles = []
    for i, a in enumerate(articles, 1):
        title = str(a.get("title", ""))[:300]
        summary = str(a.get("summary", ""))[:300]
        
        # Escape for JS
        title = title.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
        summary = summary.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")
        
        js_articles.append({
            "id": i,
            "title": {"vi": title, "en": title, "ko": title},
            "summary": {"vi": summary, "en": summary, "ko": summary},
            "sector": a.get("sector", "Unknown"),
            "area": a.get("area", ""),
            "province": a.get("province", "Vietnam"),
            "source": a.get("source", ""),
            "url": a.get("url", ""),
            "date": a.get("date", "")
        })
    
    js_data = json.dumps(js_articles, ensure_ascii=False)
    
    # Generate year filter buttons
    year_buttons = '<button onclick="filterYear(\'all\')" class="year-btn filter-btn active">All Years</button>\n'
    for year in sorted(year_counts.keys(), reverse=True):
        count = year_counts[year]
        year_buttons += f'            <button onclick="filterYear(\'{year}\')" class="year-btn filter-btn">{year} ({count})</button>\n'
    
    # Generate sector filter buttons
    sector_buttons = '<button onclick="filterSector(\'all\')" class="sector-btn filter-btn active">All Sectors</button>\n'
    for sector, count in sector_counts.most_common(10):
        safe_sector = sector.replace("'", "\\'")
        sector_buttons += f'            <button onclick="filterSector(\'{safe_sector}\')" class="sector-btn filter-btn">{sector} ({count})</button>\n'
    
    # Generate source filter buttons
    source_buttons = '<button onclick="filterSource(\'all\')" class="source-btn filter-btn active">All Sources</button>\n'
    for source, count in source_counts.most_common(12):
        safe_source = source.replace("'", "\\'")
        source_buttons += f'            <button onclick="filterSource(\'{safe_source}\')" class="source-btn filter-btn">{source} ({count})</button>\n'
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vietnam Infrastructure News Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }}
        .news-card {{ transition: all 0.2s ease; }}
        .news-card:hover {{ transform: translateY(-2px); box-shadow: 0 8px 25px rgba(0,0,0,0.1); }}
        .filter-btn {{ 
            padding: 6px 12px; 
            border-radius: 6px; 
            font-size: 13px;
            background: #e2e8f0;
            border: none;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .filter-btn:hover {{ background: #cbd5e1; }}
        .filter-btn.active {{ background: #0d9488 !important; color: white !important; }}
        .lang-btn {{ padding: 6px 12px; border-radius: 6px; cursor: pointer; transition: all 0.2s; }}
        .lang-btn.active {{ background: #0d9488 !important; }}
        .sector-badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }}
        .kpi-card {{ text-align: center; }}
        .kpi-value {{ font-size: 1.8rem; font-weight: bold; }}
    </style>
</head>
<body class="bg-gradient-to-br from-slate-50 to-slate-100 min-h-screen">

<!-- Header -->
<header class="bg-gradient-to-r from-slate-800 via-slate-700 to-slate-800 text-white sticky top-0 z-50 shadow-lg">
    <div class="max-w-7xl mx-auto px-4 py-4">
        <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
            <div class="flex items-center gap-3">
                <span class="text-4xl">🇻🇳</span>
                <div>
                    <h1 class="text-xl font-bold">Vietnam Infrastructure News</h1>
                    <p class="text-sm text-slate-300">Updated: {now_str}</p>
                </div>
            </div>
            <div class="flex gap-2">
                <button onclick="setLang('ko')" id="lang-ko" class="lang-btn bg-slate-600 text-white">한국어</button>
                <button onclick="setLang('en')" id="lang-en" class="lang-btn bg-teal-600 text-white active">English</button>
                <button onclick="setLang('vi')" id="lang-vi" class="lang-btn bg-slate-600 text-white">Tiếng Việt</button>
            </div>
        </div>
    </div>
</header>

<main class="max-w-7xl mx-auto px-4 py-6">
    
    <!-- KPI Cards -->
    <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        <div class="bg-white rounded-xl p-4 shadow-md kpi-card border-l-4 border-yellow-500">
            <div class="kpi-value text-yellow-600" id="kpi-today">{today_count}</div>
            <div class="text-sm text-slate-500">Today</div>
        </div>
        <div class="bg-white rounded-xl p-4 shadow-md kpi-card border-l-4 border-blue-500">
            <div class="kpi-value text-blue-600" id="kpi-week">{week_count}</div>
            <div class="text-sm text-slate-500">This Week</div>
        </div>
        <div class="bg-white rounded-xl p-4 shadow-md kpi-card border-l-4 border-purple-500">
            <div class="kpi-value text-purple-600" id="kpi-month">{month_count}</div>
            <div class="text-sm text-slate-500">This Month</div>
        </div>
        <div class="bg-white rounded-xl p-4 shadow-md kpi-card border-l-4 border-teal-500">
            <div class="kpi-value text-teal-600">{year_counts.get('2026', 0)}</div>
            <div class="text-sm text-slate-500">2026</div>
        </div>
        <div class="bg-white rounded-xl p-4 shadow-md kpi-card border-l-4 border-slate-500">
            <div class="kpi-value text-slate-700">{total:,}</div>
            <div class="text-sm text-slate-500">Total Database</div>
        </div>
    </div>
    
    <!-- Year Filter -->
    <div class="bg-white rounded-xl p-4 shadow-md mb-4">
        <h3 class="text-sm font-semibold text-slate-600 mb-3">📅 Filter by Year</h3>
        <div class="flex flex-wrap gap-2">
            {year_buttons}
        </div>
    </div>
    
    <!-- Sector Filter -->
    <div class="bg-white rounded-xl p-4 shadow-md mb-4">
        <h3 class="text-sm font-semibold text-slate-600 mb-3">🏭 Filter by Sector</h3>
        <div class="flex flex-wrap gap-2">
            {sector_buttons}
        </div>
    </div>
    
    <!-- Source Filter -->
    <div class="bg-white rounded-xl p-4 shadow-md mb-4">
        <h3 class="text-sm font-semibold text-slate-600 mb-3">📰 Filter by Source</h3>
        <div class="flex flex-wrap gap-2">
            {source_buttons}
        </div>
    </div>
    
    <!-- News List -->
    <div class="bg-white rounded-xl shadow-lg p-4">
        <div class="flex justify-between items-center mb-4">
            <h2 class="text-lg font-bold text-slate-800">📰 Articles (<span id="filtered-count">{total}</span>)</h2>
            <div class="text-sm text-slate-500">Showing <span id="showing-count">100</span> of <span id="total-count">{total}</span></div>
        </div>
        <div id="news-list" class="space-y-3"></div>
        <div id="load-more-container" class="text-center mt-6 hidden">
            <button onclick="loadMore()" class="px-8 py-3 bg-teal-600 text-white rounded-lg hover:bg-teal-700 font-medium">Load More Articles</button>
        </div>
    </div>
    
</main>

<footer class="bg-slate-800 text-white py-6 mt-10">
    <div class="max-w-7xl mx-auto px-4 text-center">
        <p class="text-slate-400">Vietnam Infrastructure News Dashboard</p>
        <p class="text-sm text-slate-500 mt-1">Data: {total:,} articles from 2019-2026</p>
    </div>
</footer>

<script>
// Data
const ALL_DATA = {js_data};

// State
let currentLang = 'en';
let currentYear = 'all';
let currentSector = 'all';
let currentSource = 'all';
let displayLimit = 100;

// Language switching
function setLang(lang) {{
    currentLang = lang;
    document.querySelectorAll('.lang-btn').forEach(btn => {{
        btn.classList.remove('active', 'bg-teal-600');
        btn.classList.add('bg-slate-600');
    }});
    const activeBtn = document.getElementById('lang-' + lang);
    activeBtn.classList.add('active', 'bg-teal-600');
    activeBtn.classList.remove('bg-slate-600');
    renderNews();
}}

// Text extraction with fallback
function getText(obj, lang) {{
    if (!obj) return '';
    if (typeof obj === 'string') return obj;
    return obj[lang] || obj.en || obj.vi || obj.ko || '';
}}

// Filters
function filterYear(year) {{
    currentYear = year;
    displayLimit = 100;
    document.querySelectorAll('.year-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    renderNews();
}}

function filterSector(sector) {{
    currentSector = sector;
    displayLimit = 100;
    document.querySelectorAll('.sector-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    renderNews();
}}

function filterSource(source) {{
    currentSource = source;
    displayLimit = 100;
    document.querySelectorAll('.source-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    renderNews();
}}

function loadMore() {{
    displayLimit += 100;
    renderNews();
}}

// Get filtered data
function getFilteredData() {{
    let data = ALL_DATA;
    
    if (currentYear !== 'all') {{
        data = data.filter(d => d.date && d.date.startsWith(currentYear));
    }}
    if (currentSector !== 'all') {{
        data = data.filter(d => d.sector === currentSector);
    }}
    if (currentSource !== 'all') {{
        data = data.filter(d => d.source === currentSource);
    }}
    
    // Sort by date descending
    return data.sort((a, b) => (b.date || '').localeCompare(a.date || ''));
}}

// Sector colors
function getSectorColor(sector) {{
    const colors = {{
        'Waste Water': 'bg-blue-100 text-blue-700',
        'Solid Waste': 'bg-red-100 text-red-700',
        'Water Supply/Drainage': 'bg-cyan-100 text-cyan-700',
        'Power': 'bg-yellow-100 text-yellow-700',
        'Oil & Gas': 'bg-purple-100 text-purple-700',
        'Oil & Gas ': 'bg-purple-100 text-purple-700',
        'Industrial Parks': 'bg-green-100 text-green-700',
        'Smart City': 'bg-indigo-100 text-indigo-700',
        'Transport': 'bg-orange-100 text-orange-700'
    }};
    return colors[sector] || 'bg-slate-100 text-slate-700';
}}

// Render news
function renderNews() {{
    const filtered = getFilteredData();
    const toShow = filtered.slice(0, displayLimit);
    const container = document.getElementById('news-list');
    
    document.getElementById('filtered-count').textContent = filtered.length.toLocaleString();
    document.getElementById('showing-count').textContent = Math.min(displayLimit, filtered.length);
    document.getElementById('total-count').textContent = filtered.length.toLocaleString();
    
    // Show/hide load more button
    const loadMoreBtn = document.getElementById('load-more-container');
    loadMoreBtn.classList.toggle('hidden', filtered.length <= displayLimit);
    
    if (filtered.length === 0) {{
        container.innerHTML = '<div class="text-center py-10 text-slate-500">No articles found matching your filters.</div>';
        return;
    }}
    
    const today = new Date().toISOString().slice(0, 10);
    
    container.innerHTML = toShow.map(article => {{
        const title = getText(article.title, currentLang);
        const summary = getText(article.summary, currentLang);
        const isToday = article.date === today;
        const sectorColor = getSectorColor(article.sector);
        
        return `
        <div class="news-card ${{isToday ? 'bg-yellow-50 border-l-4 border-yellow-500' : 'bg-slate-50 border-l-4 border-teal-500'}} rounded-lg p-4">
            <div class="flex flex-wrap justify-between items-start gap-2 mb-2">
                <div class="flex flex-wrap gap-2 items-center">
                    <span class="sector-badge ${{sectorColor}}">${{article.sector}}</span>
                    <span class="text-xs text-slate-500 font-medium">${{article.source}}</span>
                    ${{isToday ? '<span class="sector-badge bg-yellow-200 text-yellow-800">🆕 NEW</span>' : ''}}
                </div>
                <span class="text-xs text-slate-400">${{article.date}}</span>
            </div>
            <h3 class="font-semibold text-slate-800 mb-2">${{title}}</h3>
            <p class="text-sm text-slate-600 mb-3 line-clamp-2">${{summary.slice(0, 200)}}${{summary.length > 200 ? '...' : ''}}</p>
            <div class="flex justify-between items-center text-xs text-slate-500">
                <span>📍 ${{article.province}}</span>
                ${{article.url ? `<a href="${{article.url}}" target="_blank" rel="noopener" class="text-teal-600 hover:text-teal-700 font-medium">Read article →</a>` : ''}}
            </div>
        </div>`;
    }}).join('');
}}

// Initialize
renderNews();
</script>
</body>
</html>'''
    
    return html


def main():
    """Main function - generates dashboard from Excel"""
    print("=" * 60)
    print("DASHBOARD GENERATOR")
    print("=" * 60)
    
    # Ensure output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load all articles from Excel
    articles = load_all_articles()
    
    if not articles:
        print("WARNING: No articles loaded!")
    
    # Generate dashboard
    print(f"\nGenerating dashboard with {len(articles)} articles...")
    html = generate_dashboard_html(articles)
    
    # Save files
    index_path = OUTPUT_DIR / "index.html"
    dashboard_path = OUTPUT_DIR / "vietnam_dashboard.html"
    
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✓ Saved: {index_path} ({index_path.stat().st_size:,} bytes)")
    
    with open(dashboard_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"✓ Saved: {dashboard_path} ({dashboard_path.stat().st_size:,} bytes)")
    
    # Generate Excel output
    if OPENPYXL_AVAILABLE and articles:
        try:
            generate_excel_output(articles)
        except Exception as e:
            print(f"Excel output error: {e}")
    
    print("\nDone!")


def generate_excel_output(articles):
    """Generate Excel output file"""
    today = datetime.now().strftime("%Y%m%d")
    excel_path = OUTPUT_DIR / f"vietnam_news_{today}.xlsx"
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "News Database"
    
    # Headers
    headers = ["No", "Date", "Area", "Sector", "Province", "Title", "Summary", "Source", "URL"]
    header_fill = PatternFill(start_color="0D9488", end_color="0D9488", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.fill = header_fill
        cell.font = header_font
    
    # Sort by date descending
    sorted_articles = sorted(articles, key=lambda x: x.get("date", ""), reverse=True)
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    highlight = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
    
    for i, a in enumerate(sorted_articles, 1):
        row = i + 1
        ws.cell(row=row, column=1, value=i)
        ws.cell(row=row, column=2, value=a.get("date", ""))
        ws.cell(row=row, column=3, value=a.get("area", ""))
        ws.cell(row=row, column=4, value=a.get("sector", ""))
        ws.cell(row=row, column=5, value=a.get("province", ""))
        ws.cell(row=row, column=6, value=str(a.get("title", ""))[:200])
        ws.cell(row=row, column=7, value=str(a.get("summary", ""))[:300])
        ws.cell(row=row, column=8, value=a.get("source", ""))
        ws.cell(row=row, column=9, value=a.get("url", ""))
        
        # Highlight today's articles
        if a.get("date") == today_str:
            for col in range(1, 10):
                ws.cell(row=row, column=col).fill = highlight
    
    # Column widths
    ws.column_dimensions['A'].width = 6
    ws.column_dimensions['B'].width = 12
    ws.column_dimensions['C'].width = 15
    ws.column_dimensions['D'].width = 20
    ws.column_dimensions['E'].width = 15
    ws.column_dimensions['F'].width = 50
    ws.column_dimensions['G'].width = 40
    ws.column_dimensions['H'].width = 20
    ws.column_dimensions['I'].width = 40
    
    ws.freeze_panes = 'A2'
    
    wb.save(excel_path)
    print(f"✓ Saved: {excel_path}")


if __name__ == "__main__":
    main()
