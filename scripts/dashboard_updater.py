#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News Dashboard Updater
Standalone version - no external config imports
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

# Setup paths directly
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
TEMPLATE_DIR = PROJECT_ROOT / "templates"

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DashboardUpdater:
    """Updates HTML dashboard with ALL articles data"""
    
    def __init__(self):
        self.template_path = TEMPLATE_DIR / "dashboard_template.html"
        self.output_path = OUTPUT_DIR / "vietnam_dashboard.html"
        # Ensure output directory exists
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    def update(self, all_articles: List[Dict]) -> str:
        """Update dashboard HTML with all articles"""
        
        logger.info(f"Generating dashboard with {len(all_articles)} articles")
        
        # Create standalone dashboard
        html = self._create_standalone_dashboard(all_articles)
        
        # Save dashboard
        with open(self.output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        # Also save as index.html
        index_path = OUTPUT_DIR / "index.html"
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        logger.info(f"Dashboard saved: {self.output_path}")
        logger.info(f"Index saved: {index_path}")
        
        return str(self.output_path)
    
    def _generate_js_data(self, articles: List[Dict]) -> str:
        """Generate JavaScript array with multilingual support"""
        js_articles = []
        
        for i, article in enumerate(articles, 1):
            title = article.get("title", article.get("News Tittle", ""))
            title_vi = str(title) if title else ""
            title_en = article.get("title_en", "") or title_vi
            title_ko = article.get("title_ko", "") or title_en
            
            summary = article.get("summary_vi", article.get("Short summary", ""))
            summary_vi = str(summary) if summary else ""
            summary_en = article.get("summary_en", "") or summary_vi
            summary_ko = article.get("summary_ko", "") or summary_en
            
            sector = article.get("sector", article.get("Business Sector", ""))
            area = article.get("area", article.get("Area", "Environment"))
            province = article.get("province", article.get("Province", "Vietnam"))
            source = article.get("source", article.get("Source", ""))
            url = article.get("url", article.get("Link", ""))
            
            date_str = article.get("date", article.get("Date", ""))
            if date_str:
                if hasattr(date_str, 'strftime'):
                    date_str = date_str.strftime("%Y-%m-%d")
                else:
                    date_str = str(date_str)[:10]
            
            js_obj = {
                "id": i,
                "title": {
                    "vi": self._escape_js(title_vi),
                    "en": self._escape_js(title_en),
                    "ko": self._escape_js(title_ko)
                },
                "summary": {
                    "vi": self._escape_js(summary_vi),
                    "en": self._escape_js(summary_en),
                    "ko": self._escape_js(summary_ko)
                },
                "sector": sector or "Unknown",
                "area": area or "Environment",
                "province": province or "Vietnam",
                "source": source or "Unknown",
                "url": url or "",
                "date": date_str or ""
            }
            
            js_articles.append(js_obj)
        
        return json.dumps(js_articles, ensure_ascii=False)
    
    def _escape_js(self, text: str) -> str:
        """Escape text for JavaScript"""
        if not text:
            return ""
        text = str(text)
        text = text.replace("\\", "\\\\")
        text = text.replace('"', '\\"')
        text = text.replace("'", "\\'")
        text = text.replace("\n", " ")
        text = text.replace("\r", "")
        return text[:500]
    
    def _create_standalone_dashboard(self, articles: List[Dict]) -> str:
        """Create complete dashboard HTML"""
        
        js_data = self._generate_js_data(articles)
        today = datetime.now().strftime("%Y-%m-%d")
        
        today_count = sum(1 for a in articles if str(a.get("date", ""))[:10] == today)
        total_count = len(articles)
        
        # Count by year
        year_counts = {}
        for a in articles:
            year = str(a.get("date", ""))[:4]
            if year and year.isdigit():
                year_counts[year] = year_counts.get(year, 0) + 1
        
        # Count by sector
        sector_counts = {}
        for a in articles:
            s = a.get("sector", a.get("Business Sector", "Unknown"))
            if s:
                sector_counts[s] = sector_counts.get(s, 0) + 1
        
        # Count by source
        source_counts = {}
        for a in articles:
            src = a.get("source", a.get("Source", "Unknown"))
            if src:
                source_counts[src] = source_counts.get(src, 0) + 1
        
        html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vietnam Infrastructure News Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .news-card {{ transition: all 0.3s ease; }}
        .news-card:hover {{ transform: translateY(-2px); box-shadow: 0 10px 25px -5px rgba(0,0,0,0.1); }}
        .filter-btn {{ transition: all 0.2s ease; }}
        .filter-btn.active {{ background: #0d9488 !important; color: white !important; }}
        .lang-btn.active {{ background: #0d9488 !important; }}
        .sector-badge {{ font-size: 11px; padding: 2px 8px; border-radius: 4px; }}
    </style>
</head>
<body class="bg-gradient-to-br from-slate-50 to-slate-100 min-h-screen">

<header class="bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 text-white sticky top-0 z-50 shadow-xl">
    <div class="max-w-7xl mx-auto px-4 py-4">
        <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
            <div class="flex items-center gap-4">
                <span class="text-4xl">🇻🇳</span>
                <div>
                    <h1 class="font-bold text-xl">Vietnam Infrastructure News</h1>
                    <p class="text-sm text-slate-300">Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
                </div>
            </div>
            <div class="flex gap-2">
                <button onclick="setLang('ko')" id="lang-ko" class="lang-btn px-3 py-1.5 rounded text-sm bg-slate-700 hover:bg-slate-600">한국어</button>
                <button onclick="setLang('en')" id="lang-en" class="lang-btn px-3 py-1.5 rounded text-sm bg-teal-600 active">English</button>
                <button onclick="setLang('vi')" id="lang-vi" class="lang-btn px-3 py-1.5 rounded text-sm bg-slate-700 hover:bg-slate-600">Tiếng Việt</button>
            </div>
        </div>
    </div>
</header>

<main class="max-w-7xl mx-auto px-4 py-6">
    <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        <div class="bg-white rounded-xl p-4 shadow-md border-l-4 border-yellow-500">
            <div class="text-sm text-slate-500">Today</div>
            <div class="text-2xl font-bold text-yellow-600" id="kpi-today">{today_count}</div>
        </div>
        <div class="bg-white rounded-xl p-4 shadow-md border-l-4 border-blue-500">
            <div class="text-sm text-slate-500">This Week</div>
            <div class="text-2xl font-bold text-blue-600" id="kpi-week">0</div>
        </div>
        <div class="bg-white rounded-xl p-4 shadow-md border-l-4 border-purple-500">
            <div class="text-sm text-slate-500">This Month</div>
            <div class="text-2xl font-bold text-purple-600" id="kpi-month">0</div>
        </div>
        <div class="bg-white rounded-xl p-4 shadow-md border-l-4 border-teal-500">
            <div class="text-sm text-slate-500">2026</div>
            <div class="text-2xl font-bold text-teal-600" id="kpi-2026">{year_counts.get('2026', 0)}</div>
        </div>
        <div class="bg-white rounded-xl p-4 shadow-md border-l-4 border-slate-500">
            <div class="text-sm text-slate-500">Total</div>
            <div class="text-2xl font-bold text-slate-700" id="kpi-total">{total_count:,}</div>
        </div>
    </div>
    
    <div class="bg-white rounded-xl p-4 shadow-md mb-4">
        <h3 class="text-sm font-semibold text-slate-600 mb-2">📅 Filter by Year</h3>
        <div class="flex flex-wrap gap-2">
            <button onclick="filterByYear('all')" class="year-btn filter-btn px-4 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-sm active">All Years</button>
            <button onclick="filterByYear('2026')" class="year-btn filter-btn px-4 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-sm">2026 ({year_counts.get('2026', 0)})</button>
            <button onclick="filterByYear('2025')" class="year-btn filter-btn px-4 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-sm">2025 ({year_counts.get('2025', 0)})</button>
            <button onclick="filterByYear('2024')" class="year-btn filter-btn px-4 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-sm">2024 ({year_counts.get('2024', 0)})</button>
            <button onclick="filterByYear('2023')" class="year-btn filter-btn px-4 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-sm">2023 ({year_counts.get('2023', 0)})</button>
            <button onclick="filterByYear('2022')" class="year-btn filter-btn px-4 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-sm">2022 ({year_counts.get('2022', 0)})</button>
            <button onclick="filterByYear('2021')" class="year-btn filter-btn px-4 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-sm">2021 ({year_counts.get('2021', 0)})</button>
            <button onclick="filterByYear('2020')" class="year-btn filter-btn px-4 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-sm">2020 ({year_counts.get('2020', 0)})</button>
            <button onclick="filterByYear('2019')" class="year-btn filter-btn px-4 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-sm">2019 ({year_counts.get('2019', 0)})</button>
        </div>
    </div>
    
    <div class="bg-white rounded-xl p-4 shadow-md mb-4">
        <h3 class="text-sm font-semibold text-slate-600 mb-2">🏭 Filter by Sector</h3>
        <div class="flex flex-wrap gap-2">
            <button onclick="filterBySector('all')" class="sector-btn filter-btn px-3 py-1.5 rounded bg-slate-100 hover:bg-slate-200 text-sm active">All Sectors</button>
'''
        
        for sector, count in sorted(sector_counts.items(), key=lambda x: -x[1])[:10]:
            html += f'''            <button onclick="filterBySector('{sector}')" class="sector-btn filter-btn px-3 py-1.5 rounded bg-slate-100 hover:bg-slate-200 text-sm">{sector} ({count})</button>\n'''
        
        html += '''        </div>
    </div>
    
    <div class="bg-white rounded-xl p-4 shadow-md mb-6">
        <h3 class="text-sm font-semibold text-slate-600 mb-2">📰 Filter by Source</h3>
        <div class="flex flex-wrap gap-2">
            <button onclick="filterBySource('all')" class="source-btn filter-btn px-3 py-1.5 rounded bg-slate-100 hover:bg-slate-200 text-sm active">All Sources</button>
'''
        
        for source, count in sorted(source_counts.items(), key=lambda x: -x[1])[:15]:
            safe_source = source.replace("'", "\\'")
            html += f'''            <button onclick="filterBySource('{safe_source}')" class="source-btn filter-btn px-3 py-1.5 rounded bg-slate-100 hover:bg-slate-200 text-xs">{source} ({count})</button>\n'''
        
        html += f'''        </div>
    </div>
    
    <div class="bg-white rounded-xl shadow-lg p-4">
        <div class="flex justify-between items-center mb-4">
            <h2 class="text-lg font-bold">📰 News Articles (<span id="filtered-count">{total_count}</span>)</h2>
            <div class="text-sm text-slate-500">
                Showing <span id="showing-count">100</span> of <span id="total-filtered">0</span>
            </div>
        </div>
        <div id="news-list" class="space-y-3"></div>
        <div id="load-more-container" class="text-center mt-4 hidden">
            <button onclick="loadMore()" class="px-6 py-2 bg-teal-600 text-white rounded-lg hover:bg-teal-700">Load More</button>
        </div>
    </div>
</main>

<script>
const ALL_DATA = {js_data};

let currentLang = 'en';
let currentYear = 'all';
let currentSector = 'all';
let currentSource = 'all';
let displayCount = 100;

function setLang(lang) {{
    currentLang = lang;
    document.querySelectorAll('.lang-btn').forEach(btn => {{
        btn.classList.remove('active', 'bg-teal-600');
        btn.classList.add('bg-slate-700');
    }});
    document.getElementById('lang-' + lang).classList.add('active', 'bg-teal-600');
    document.getElementById('lang-' + lang).classList.remove('bg-slate-700');
    renderNews();
}}

function getText(textObj, lang) {{
    if (!textObj) return '';
    if (typeof textObj === 'string') return textObj;
    if (textObj[lang] && textObj[lang].trim()) return textObj[lang];
    if (textObj.en && textObj.en.trim()) return textObj.en;
    if (textObj.vi && textObj.vi.trim()) return textObj.vi;
    if (textObj.ko && textObj.ko.trim()) return textObj.ko;
    return Object.values(textObj).find(v => v && v.trim()) || '';
}}

function filterByYear(year) {{
    currentYear = year;
    displayCount = 100;
    document.querySelectorAll('.year-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    renderNews();
}}

function filterBySector(sector) {{
    currentSector = sector;
    displayCount = 100;
    document.querySelectorAll('.sector-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    renderNews();
}}

function filterBySource(source) {{
    currentSource = source;
    displayCount = 100;
    document.querySelectorAll('.source-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    renderNews();
}}

function getFilteredData() {{
    let filtered = ALL_DATA;
    if (currentYear !== 'all') {{
        filtered = filtered.filter(d => d.date && d.date.startsWith(currentYear));
    }}
    if (currentSector !== 'all') {{
        filtered = filtered.filter(d => d.sector === currentSector);
    }}
    if (currentSource !== 'all') {{
        filtered = filtered.filter(d => d.source === currentSource);
    }}
    filtered.sort((a, b) => (b.date || '').localeCompare(a.date || ''));
    return filtered;
}}

function loadMore() {{
    displayCount += 100;
    renderNews();
}}

function getSectorColor(sector) {{
    const colors = {{
        'Waste Water': 'bg-blue-100 text-blue-700',
        'Solid Waste': 'bg-red-100 text-red-700',
        'Water Supply/Drainage': 'bg-cyan-100 text-cyan-700',
        'Power': 'bg-yellow-100 text-yellow-700',
        'Oil & Gas': 'bg-purple-100 text-purple-700',
        'Industrial Parks': 'bg-green-100 text-green-700',
        'Smart City': 'bg-indigo-100 text-indigo-700',
        'Transport': 'bg-orange-100 text-orange-700'
    }};
    return colors[sector] || 'bg-slate-100 text-slate-700';
}}

function renderNews() {{
    const data = getFilteredData();
    const container = document.getElementById('news-list');
    const toShow = data.slice(0, displayCount);
    
    document.getElementById('filtered-count').textContent = data.length.toLocaleString();
    document.getElementById('total-filtered').textContent = data.length.toLocaleString();
    document.getElementById('showing-count').textContent = Math.min(displayCount, data.length);
    
    const loadMoreBtn = document.getElementById('load-more-container');
    if (data.length > displayCount) {{
        loadMoreBtn.classList.remove('hidden');
    }} else {{
        loadMoreBtn.classList.add('hidden');
    }}
    
    if (data.length === 0) {{
        container.innerHTML = '<p class="text-slate-500 text-center py-8">No articles found.</p>';
        return;
    }}
    
    const today = new Date().toISOString().slice(0, 10);
    
    container.innerHTML = toShow.map(article => {{
        const title = getText(article.title, currentLang);
        const summary = getText(article.summary, currentLang);
        const isToday = article.date === today;
        const sectorColor = getSectorColor(article.sector);
        
        return `
        <div class="news-card ${{isToday ? 'bg-yellow-50 border-l-4 border-yellow-400' : 'bg-slate-50 border-l-4 border-teal-500'}} rounded-lg p-4">
            <div class="flex flex-wrap justify-between items-start gap-2 mb-2">
                <div class="flex flex-wrap gap-2">
                    <span class="sector-badge ${{sectorColor}}">${{article.sector || 'Unknown'}}</span>
                    ${{isToday ? '<span class="sector-badge bg-yellow-200 text-yellow-800">NEW</span>' : ''}}
                </div>
                <span class="text-xs text-slate-500">${{article.date}}</span>
            </div>
            <h3 class="font-semibold text-slate-800 mb-2 text-sm md:text-base">${{title || 'No title'}}</h3>
            <p class="text-sm text-slate-600 mb-2 line-clamp-2">${{summary ? summary.slice(0, 200) + (summary.length > 200 ? '...' : '') : ''}}</p>
            <div class="flex flex-wrap justify-between items-center text-xs text-slate-500 gap-2">
                <div>
                    <span>📍 ${{article.province}}</span>
                    <span class="mx-2">|</span>
                    <span class="font-medium">${{article.source}}</span>
                </div>
                ${{article.url ? `<a href="${{article.url}}" target="_blank" class="text-teal-600 hover:underline font-medium">Read more →</a>` : ''}}
            </div>
        </div>`;
    }}).join('');
}}

function updateKPIs() {{
    const today = new Date().toISOString().slice(0, 10);
    const weekAgo = new Date();
    weekAgo.setDate(weekAgo.getDate() - 7);
    const weekStr = weekAgo.toISOString().slice(0, 10);
    const monthAgo = new Date();
    monthAgo.setMonth(monthAgo.getMonth() - 1);
    const monthStr = monthAgo.toISOString().slice(0, 10);
    
    document.getElementById('kpi-today').textContent = ALL_DATA.filter(d => d.date === today).length;
    document.getElementById('kpi-week').textContent = ALL_DATA.filter(d => d.date >= weekStr).length;
    document.getElementById('kpi-month').textContent = ALL_DATA.filter(d => d.date >= monthStr).length;
    document.getElementById('kpi-2026').textContent = ALL_DATA.filter(d => d.date && d.date.startsWith('2026')).length;
    document.getElementById('kpi-total').textContent = ALL_DATA.length.toLocaleString();
}}

updateKPIs();
renderNews();
</script>
</body>
</html>'''
        
        return html


class ExcelUpdater:
    """Updates Excel output file"""
    
    def __init__(self):
        self.output_path = OUTPUT_DIR / f"vietnam_news_{datetime.now().strftime('%Y%m%d')}.xlsx"
        self.today = datetime.now().strftime("%Y-%m-%d")
    
    def update(self, articles: List[Dict]) -> str:
        if not OPENPYXL_AVAILABLE:
            logger.warning("openpyxl not available")
            return ""
        
        wb = openpyxl.Workbook()
        self._create_database_sheet(wb, articles)
        self._create_summary_sheet(wb, articles)
        
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        wb.save(self.output_path)
        logger.info(f"Excel saved: {self.output_path}")
        return str(self.output_path)
    
    def _create_database_sheet(self, wb, articles):
        ws = wb.active
        ws.title = "News Database"
        
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="0D9488", end_color="0D9488", fill_type="solid")
        highlight_fill = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
        
        headers = ["No", "Date", "Area", "Sector", "Province", "Title", "Summary", "Source", "URL"]
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.font = header_font
            cell.fill = header_fill
        
        sorted_articles = sorted(articles, key=lambda x: str(x.get("date", ""))[:10], reverse=True)
        
        for i, article in enumerate(sorted_articles, 1):
            row = i + 1
            date_str = str(article.get("date", article.get("Date", "")))[:10]
            
            ws.cell(row=row, column=1, value=i)
            ws.cell(row=row, column=2, value=date_str)
            ws.cell(row=row, column=3, value=article.get("area", article.get("Area", "")))
            ws.cell(row=row, column=4, value=article.get("sector", article.get("Business Sector", "")))
            ws.cell(row=row, column=5, value=article.get("province", article.get("Province", "")))
            ws.cell(row=row, column=6, value=str(article.get("title", article.get("News Tittle", "")))[:200])
            ws.cell(row=row, column=7, value=str(article.get("summary_vi", article.get("Short summary", "")))[:300])
            ws.cell(row=row, column=8, value=article.get("source", article.get("Source", "")))
            ws.cell(row=row, column=9, value=article.get("url", article.get("Link", "")))
            
            if date_str == self.today:
                for col in range(1, 10):
                    ws.cell(row=row, column=col).fill = highlight_fill
        
        widths = [6, 12, 12, 20, 15, 50, 40, 20, 40]
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[chr(64+i)].width = w
        
        ws.freeze_panes = 'A2'
    
    def _create_summary_sheet(self, wb, articles):
        from collections import Counter
        
        ws = wb.create_sheet("Summary")
        
        ws.cell(row=1, column=1, value="Vietnam Infrastructure News - Summary")
        ws.cell(row=1, column=1).font = Font(bold=True, size=14)
        ws.cell(row=2, column=1, value=f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        
        today_count = sum(1 for a in articles if str(a.get("date", ""))[:10] == self.today)
        
        row = 4
        ws.cell(row=row, column=1, value="Overview").font = Font(bold=True)
        row += 1
        ws.cell(row=row, column=1, value="Total Articles")
        ws.cell(row=row, column=2, value=len(articles))
        row += 1
        ws.cell(row=row, column=1, value="Today's Articles")
        ws.cell(row=row, column=2, value=today_count)
        row += 2
        
        ws.cell(row=row, column=1, value="By Year").font = Font(bold=True)
        row += 1
        
        year_counts = Counter(str(a.get("date", ""))[:4] for a in articles if a.get("date"))
        for year, count in sorted(year_counts.items(), reverse=True):
            if year.isdigit():
                ws.cell(row=row, column=1, value=year)
                ws.cell(row=row, column=2, value=count)
                row += 1
        
        row += 1
        ws.cell(row=row, column=1, value="By Sector").font = Font(bold=True)
        row += 1
        
        sector_counts = Counter(a.get("sector", a.get("Business Sector", "Unknown")) for a in articles)
        for sector, count in sector_counts.most_common():
            ws.cell(row=row, column=1, value=sector)
            ws.cell(row=row, column=2, value=count)
            row += 1
        
        ws.column_dimensions['A'].width = 30
        ws.column_dimensions['B'].width = 15


def main():
    """Generate dashboard from Excel database"""
    import openpyxl
    
    print("=" * 60)
    print("DASHBOARD GENERATOR")
    print("=" * 60)
    
    # Ensure output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load articles from Excel
    EXCEL_DB_PATH = DATA_DIR / "database" / "Vietnam_Infra_News_Database_Final.xlsx"
    
    articles = []
    
    if EXCEL_DB_PATH.exists():
        print(f"Loading from: {EXCEL_DB_PATH}")
        
        wb = openpyxl.load_workbook(EXCEL_DB_PATH, read_only=True, data_only=True)
        ws = wb.active
        
        headers = [cell.value for cell in ws[1]]
        col_map = {str(h).strip(): i for i, h in enumerate(headers) if h}
        
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not any(row):
                continue
            
            date_val = row[col_map.get("Date", 4)] if "Date" in col_map else None
            date_str = date_val.strftime("%Y-%m-%d") if hasattr(date_val, 'strftime') else str(date_val)[:10] if date_val else ""
            
            articles.append({
                "area": row[col_map.get("Area", 0)] or "Environment",
                "sector": row[col_map.get("Business Sector", 1)] or "",
                "province": row[col_map.get("Province", 2)] or "Vietnam",
                "title": row[col_map.get("News Tittle", 3)] or "",
                "date": date_str,
                "source": row[col_map.get("Source", 5)] or "",
                "url": row[col_map.get("Link", 6)] or "",
                "summary_vi": row[col_map.get("Short summary", 7)] or "",
            })
        
        wb.close()
        print(f"Loaded {len(articles)} articles")
        
        # Count by year
        year_counts = {}
        for a in articles:
            year = a.get("date", "")[:4]
            if year and year.isdigit():
                year_counts[year] = year_counts.get(year, 0) + 1
        print(f"By year: {dict(sorted(year_counts.items()))}")
    else:
        print(f"Excel not found: {EXCEL_DB_PATH}")
    
    # Generate dashboard
    print(f"\nGenerating dashboard with {len(articles)} articles...")
    
    dashboard = DashboardUpdater()
    result = dashboard.update(articles)
    print(f"Dashboard: {result}")
    
    excel = ExcelUpdater()
    excel_result = excel.update(articles)
    print(f"Excel: {excel_result}")
    
    # Verify
    index_file = OUTPUT_DIR / "index.html"
    if index_file.exists():
        print(f"\n✓ index.html created ({index_file.stat().st_size} bytes)")
    else:
        print(f"\n✗ index.html NOT found!")
    
    print("\nDone!")


if __name__ == "__main__":
    main()
