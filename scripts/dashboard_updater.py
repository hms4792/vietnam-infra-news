"""
Vietnam Infrastructure News Dashboard Updater
Injects ALL articles data into dashboard template
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import quote
import sys

sys.path.append(str(Path(__file__).parent.parent))

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

from config.settings import DATA_DIR, OUTPUT_DIR, TEMPLATE_DIR

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# Sector classification
SECTOR_KEYWORDS = {
    "Waste Water": ["wastewater", "waste water", "sewage", "xử lý nước thải", "nước thải", "drainage"],
    "Solid Waste": ["solid waste", "garbage", "landfill", "rác thải", "chất thải rắn", "waste-to-energy", "incineration"],
    "Water Supply/Drainage": ["water supply", "clean water", "cấp nước", "nước sạch", "water treatment"],
    "Power": ["power plant", "electricity", "điện", "nhiệt điện", "lng", "thermal power"],
    "Oil & Gas": ["oil", "gas", "petroleum", "dầu khí", "lng terminal"],
    "Smart City": ["smart city", "thành phố thông minh", "digital city"],
    "Industrial Parks": ["industrial park", "khu công nghiệp", "industrial zone"],
}

AREA_BY_SECTOR = {
    "Waste Water": "Environment",
    "Solid Waste": "Environment",
    "Water Supply/Drainage": "Environment",
    "Power": "Energy Develop.",
    "Oil & Gas": "Energy Develop.",
    "Smart City": "Urban Develop.",
    "Industrial Parks": "Urban Develop.",
}

SECTOR_PRIORITY = [
    "Waste Water", "Solid Waste", "Water Supply/Drainage",
    "Power", "Oil & Gas", "Smart City", "Industrial Parks"
]


def classify_article(title: str, summary: str = "") -> Tuple[str, str]:
    """Classify article into sector and area based on keywords"""
    text = (str(title) + " " + str(summary)).lower()
    
    for sector in SECTOR_PRIORITY:
        keywords = SECTOR_KEYWORDS.get(sector, [])
        for keyword in keywords:
            if keyword.lower() in text:
                return sector, AREA_BY_SECTOR.get(sector, "Environment")
    
    return "Waste Water", "Environment"


class DashboardUpdater:
    """Updates HTML dashboard with all articles data"""
    
    def __init__(self):
        self.template_path = TEMPLATE_DIR / "dashboard_template.html"
        self.output_path = OUTPUT_DIR / "vietnam_dashboard.html"
    
    def update(self, all_articles: List[Dict]) -> str:
        """Update dashboard HTML with all articles"""
        
        logger.info(f"Generating dashboard with {len(all_articles)} articles")
        
        # Generate JavaScript data array
        js_data = self._generate_js_data(all_articles)
        
        # Check template exists
        if not self.template_path.exists():
            logger.error(f"Template not found: {self.template_path}")
            # Create a basic dashboard if no template
            html = self._create_standalone_dashboard(all_articles)
        else:
            # Load template
            with open(self.template_path, 'r', encoding='utf-8') as f:
                template = f.read()
            
            # Replace placeholder with actual data
            if '/*__BACKEND_DATA__*/[]' in template:
                html = template.replace('/*__BACKEND_DATA__*/[]', js_data)
                logger.info("Replaced /*__BACKEND_DATA__*/[] placeholder")
            elif 'const ALL_DATA = []' in template:
                html = template.replace('const ALL_DATA = []', f'const ALL_DATA = {js_data}')
                logger.info("Replaced const ALL_DATA = [] placeholder")
            elif 'let ALL_DATA = []' in template:
                html = template.replace('let ALL_DATA = []', f'let ALL_DATA = {js_data}')
                logger.info("Replaced let ALL_DATA = [] placeholder")
            else:
                logger.warning("No data placeholder found in template, creating standalone dashboard")
                html = self._create_standalone_dashboard(all_articles)
        
        # Replace last updated timestamp
        html = html.replace('{{LAST_UPDATED}}', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        # Ensure output directory exists
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save main dashboard
        with open(self.output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        # Also save as index.html for GitHub Pages
        index_path = OUTPUT_DIR / "index.html"
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        logger.info(f"Dashboard saved: {self.output_path}")
        logger.info(f"Index saved: {index_path}")
        
        return str(self.output_path)
    
    def _generate_js_data(self, articles: List[Dict]) -> str:
        """Generate JavaScript array from all articles"""
        js_articles = []
        
        for i, article in enumerate(articles, 1):
            # Extract title (handle various field names)
            title = article.get("title", article.get("News Tittle", "No title"))
            
            # Handle multilingual titles
            if isinstance(title, dict):
                title_vi = title.get("vi", "")
                title_en = title.get("en", "")
                title_ko = title.get("ko", "")
            else:
                title_vi = str(title)
                title_en = article.get("title_en", article.get("summary_en", str(title)))
                title_ko = article.get("title_ko", article.get("summary_ko", ""))
            
            # Extract summary
            summary = article.get("summary", article.get("Short summary", ""))
            if isinstance(summary, dict):
                summary_vi = summary.get("vi", "")
                summary_en = summary.get("en", "")
                summary_ko = summary.get("ko", "")
            else:
                summary_vi = article.get("summary_vi", str(summary))
                summary_en = article.get("summary_en", str(summary))
                summary_ko = article.get("summary_ko", "")
            
            # Get sector and area
            sector = article.get("sector", article.get("Business Sector", ""))
            area = article.get("area", article.get("Area", ""))
            
            # Classify if not set
            if not sector or sector == "Unknown":
                sector, area = classify_article(title_vi, summary_vi)
            if not area:
                area = AREA_BY_SECTOR.get(sector, "Environment")
            
            # Get other fields
            province = article.get("province", article.get("Province", "Vietnam"))
            source = article.get("source", article.get("source_name", article.get("Source Name", "")))
            url = article.get("url", article.get("source_url", article.get("Source URL", "")))
            
            # Handle date
            date_str = article.get("date", article.get("published", article.get("article_date", article.get("Date", ""))))
            if date_str:
                date_str = str(date_str)[:10]  # Keep only YYYY-MM-DD
            else:
                date_str = datetime.now().strftime("%Y-%m-%d")
            
            # Build JavaScript object
            js_obj = {
                "id": i,
                "title": {
                    "vi": self._escape_js(title_vi),
                    "en": self._escape_js(title_en) if title_en else self._escape_js(title_vi),
                    "ko": self._escape_js(title_ko) if title_ko else self._escape_js(title_en or title_vi)
                },
                "summary": {
                    "vi": self._escape_js(summary_vi),
                    "en": self._escape_js(summary_en) if summary_en else self._escape_js(summary_vi),
                    "ko": self._escape_js(summary_ko) if summary_ko else self._escape_js(summary_en or summary_vi)
                },
                "sector": sector,
                "area": area,
                "province": province,
                "source": source,
                "url": url,
                "date": date_str
            }
            
            js_articles.append(js_obj)
        
        return json.dumps(js_articles, ensure_ascii=False, indent=2)
    
    def _escape_js(self, text: str) -> str:
        """Escape text for JavaScript string"""
        if not text:
            return ""
        text = str(text)
        text = text.replace("\\", "\\\\")
        text = text.replace('"', '\\"')
        text = text.replace("'", "\\'")
        text = text.replace("\n", " ")
        text = text.replace("\r", "")
        text = text.replace("\t", " ")
        return text[:500]  # Limit length
    
    def _create_standalone_dashboard(self, articles: List[Dict]) -> str:
        """Create a complete standalone dashboard HTML"""
        js_data = self._generate_js_data(articles)
        
        # Count statistics
        today = datetime.now().strftime("%Y-%m-%d")
        today_count = sum(1 for a in articles if str(a.get("date", ""))[:10] == today)
        total_count = len(articles)
        
        html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🇻🇳 Vietnam Infrastructure News Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        .news-card {{ transition: all 0.3s ease; }}
        .news-card:hover {{ transform: translateY(-2px); box-shadow: 0 10px 25px -5px rgba(0,0,0,0.1); }}
        .filter-btn {{ transition: all 0.2s ease; }}
        .filter-btn.active {{ background: #0d9488; color: white; }}
    </style>
</head>
<body class="bg-gradient-to-br from-slate-50 to-slate-100 min-h-screen">

<header class="bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 text-white sticky top-0 z-50 shadow-xl">
    <div class="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
        <div class="flex items-center gap-4">
            <span class="text-4xl">🇻🇳</span>
            <div>
                <h1 class="font-bold text-xl">Vietnam Infrastructure News</h1>
                <p class="text-sm text-slate-300">Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
            </div>
        </div>
        <div class="flex gap-2">
            <button onclick="setLang('ko')" class="lang-btn px-3 py-1 rounded bg-slate-700 hover:bg-slate-600">한국어</button>
            <button onclick="setLang('en')" class="lang-btn px-3 py-1 rounded bg-slate-700 hover:bg-slate-600">English</button>
            <button onclick="setLang('vi')" class="lang-btn px-3 py-1 rounded bg-slate-700 hover:bg-slate-600">Tiếng Việt</button>
        </div>
    </div>
</header>

<main class="max-w-7xl mx-auto px-4 py-6">
    <!-- KPI Cards -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div class="bg-white rounded-xl p-4 shadow-md">
            <div class="text-sm text-slate-500">Today</div>
            <div class="text-3xl font-bold text-teal-600" id="kpi-today">{today_count}</div>
        </div>
        <div class="bg-white rounded-xl p-4 shadow-md">
            <div class="text-sm text-slate-500">This Week</div>
            <div class="text-3xl font-bold text-blue-600" id="kpi-week">0</div>
        </div>
        <div class="bg-white rounded-xl p-4 shadow-md">
            <div class="text-sm text-slate-500">This Month</div>
            <div class="text-3xl font-bold text-purple-600" id="kpi-month">0</div>
        </div>
        <div class="bg-white rounded-xl p-4 shadow-md">
            <div class="text-sm text-slate-500">Total Database</div>
            <div class="text-3xl font-bold text-slate-700" id="kpi-total">{total_count}</div>
        </div>
    </div>
    
    <!-- Filter Buttons -->
    <div class="flex flex-wrap gap-2 mb-4">
        <button onclick="filterByPeriod('today')" class="filter-btn px-4 py-2 rounded-lg bg-white shadow">Today</button>
        <button onclick="filterByPeriod('week')" class="filter-btn px-4 py-2 rounded-lg bg-white shadow">This Week</button>
        <button onclick="filterByPeriod('month')" class="filter-btn px-4 py-2 rounded-lg bg-white shadow">This Month</button>
        <button onclick="filterByPeriod('2025')" class="filter-btn px-4 py-2 rounded-lg bg-white shadow">2025</button>
        <button onclick="filterByPeriod('2024')" class="filter-btn px-4 py-2 rounded-lg bg-white shadow">2024</button>
        <button onclick="filterByPeriod('all')" class="filter-btn px-4 py-2 rounded-lg bg-white shadow active">All</button>
    </div>
    
    <!-- Sector Filter -->
    <div class="flex flex-wrap gap-2 mb-6">
        <button onclick="filterBySector('all')" class="filter-btn px-3 py-1 rounded bg-white shadow text-sm">All Sectors</button>
        <button onclick="filterBySector('Waste Water')" class="filter-btn px-3 py-1 rounded bg-white shadow text-sm">Waste Water</button>
        <button onclick="filterBySector('Solid Waste')" class="filter-btn px-3 py-1 rounded bg-white shadow text-sm">Solid Waste</button>
        <button onclick="filterBySector('Water Supply/Drainage')" class="filter-btn px-3 py-1 rounded bg-white shadow text-sm">Water Supply</button>
        <button onclick="filterBySector('Power')" class="filter-btn px-3 py-1 rounded bg-white shadow text-sm">Power</button>
        <button onclick="filterBySector('Oil & Gas')" class="filter-btn px-3 py-1 rounded bg-white shadow text-sm">Oil & Gas</button>
    </div>
    
    <!-- News List -->
    <div class="bg-white rounded-xl shadow-lg p-4">
        <h2 class="text-lg font-bold mb-4">📰 News Articles (<span id="filtered-count">{total_count}</span>)</h2>
        <div id="news-list" class="space-y-3"></div>
    </div>
</main>

<script>
const ALL_DATA = {js_data};

let currentLang = 'en';
let currentPeriod = 'all';
let currentSector = 'all';

function setLang(lang) {{
    currentLang = lang;
    renderNews();
}}

function filterByPeriod(period) {{
    currentPeriod = period;
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    event.target.classList.add('active');
    renderNews();
}}

function filterBySector(sector) {{
    currentSector = sector;
    renderNews();
}}

function getFilteredData() {{
    const today = new Date();
    const todayStr = today.toISOString().slice(0, 10);
    
    const weekAgo = new Date(today);
    weekAgo.setDate(weekAgo.getDate() - 7);
    const weekStr = weekAgo.toISOString().slice(0, 10);
    
    const monthAgo = new Date(today);
    monthAgo.setMonth(monthAgo.getMonth() - 1);
    const monthStr = monthAgo.toISOString().slice(0, 10);
    
    let filtered = ALL_DATA;
    
    // Period filter
    if (currentPeriod === 'today') {{
        filtered = filtered.filter(d => d.date === todayStr);
    }} else if (currentPeriod === 'week') {{
        filtered = filtered.filter(d => d.date >= weekStr);
    }} else if (currentPeriod === 'month') {{
        filtered = filtered.filter(d => d.date >= monthStr);
    }} else if (currentPeriod === '2025') {{
        filtered = filtered.filter(d => d.date && d.date.startsWith('2025'));
    }} else if (currentPeriod === '2024') {{
        filtered = filtered.filter(d => d.date && d.date.startsWith('2024'));
    }}
    
    // Sector filter
    if (currentSector !== 'all') {{
        filtered = filtered.filter(d => d.sector === currentSector);
    }}
    
    return filtered;
}}

function renderNews() {{
    const data = getFilteredData();
    const container = document.getElementById('news-list');
    document.getElementById('filtered-count').textContent = data.length;
    
    if (data.length === 0) {{
        container.innerHTML = '<p class="text-slate-500 text-center py-8">No articles found for this filter.</p>';
        return;
    }}
    
    container.innerHTML = data.slice(0, 100).map(article => `
        <div class="news-card bg-slate-50 rounded-lg p-4 border-l-4 border-teal-500">
            <div class="flex justify-between items-start mb-2">
                <span class="text-xs px-2 py-1 bg-teal-100 text-teal-700 rounded">${{article.sector}}</span>
                <span class="text-xs text-slate-500">${{article.date}}</span>
            </div>
            <h3 class="font-semibold text-slate-800 mb-2">
                ${{article.title[currentLang] || article.title.vi}}
            </h3>
            <p class="text-sm text-slate-600 mb-2">
                ${{(article.summary[currentLang] || article.summary.vi || '').slice(0, 200)}}...
            </p>
            <div class="flex justify-between items-center text-xs text-slate-500">
                <span>📍 ${{article.province}} | ${{article.source}}</span>
                <a href="${{article.url}}" target="_blank" class="text-teal-600 hover:underline">Read more →</a>
            </div>
        </div>
    `).join('');
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
    document.getElementById('kpi-total').textContent = ALL_DATA.length;
}}

// Initialize
updateKPIs();
renderNews();
</script>

</body>
</html>'''
        
        return html


class ExcelUpdater:
    """Updates Excel file with all articles"""
    
    def __init__(self):
        self.output_path = OUTPUT_DIR / f"vietnam_news_{datetime.now().strftime('%Y%m%d')}.xlsx"
    
    def update(self, articles: List[Dict]) -> str:
        """Update Excel file with all articles"""
        
        if not OPENPYXL_AVAILABLE:
            logger.warning("openpyxl not available, skipping Excel update")
            return ""
        
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "News Database"
        
        # Headers
        headers = ["No", "Date", "Area", "Sector", "Province", "Title (EN)", "Title (VI)", "Summary (EN)", "Source", "URL"]
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill(start_color="0D9488", end_color="0D9488", fill_type="solid")
            cell.alignment = Alignment(horizontal="center")
        
        # Data rows
        for i, article in enumerate(articles, 1):
            title = article.get("title", "")
            if isinstance(title, dict):
                title_en = title.get("en", title.get("vi", ""))
                title_vi = title.get("vi", "")
            else:
                title_en = article.get("title_en", article.get("summary_en", str(title)))
                title_vi = str(title)
            
            summary = article.get("summary", "")
            if isinstance(summary, dict):
                summary_en = summary.get("en", summary.get("vi", ""))
            else:
                summary_en = article.get("summary_en", str(summary))
            
            row_data = [
                i,
                str(article.get("date", ""))[:10],
                article.get("area", "Environment"),
                article.get("sector", "Waste Water"),
                article.get("province", "Vietnam"),
                title_en[:200] if title_en else "",
                title_vi[:200] if title_vi else "",
                summary_en[:500] if summary_en else "",
                article.get("source", ""),
                article.get("url", "")
            ]
            
            for col, value in enumerate(row_data, 1):
                ws.cell(row=i+1, column=col, value=value)
        
        # Adjust column widths
        ws.column_dimensions['A'].width = 6
        ws.column_dimensions['B'].width = 12
        ws.column_dimensions['C'].width = 15
        ws.column_dimensions['D'].width = 20
        ws.column_dimensions['E'].width = 15
        ws.column_dimensions['F'].width = 50
        ws.column_dimensions['G'].width = 50
        ws.column_dimensions['H'].width = 60
        ws.column_dimensions['I'].width = 20
        ws.column_dimensions['J'].width = 40
        
        # Save
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(self.output_path)
        
        logger.info(f"Excel saved with {len(articles)} articles: {self.output_path}")
        return str(self.output_path)


def main():
    """Standalone dashboard update - loads from Excel database"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    
    # Try to load from Excel database
    try:
        import openpyxl
        
        # Find Excel file
        possible_paths = [
            DATA_DIR / "database" / "Vietnam_Infra_News_Database_Final.xlsx",
            DATA_DIR / "Vietnam_Infra_News_Database_Final.xlsx",
            Path("data/database/Vietnam_Infra_News_Database_Final.xlsx"),
        ]
        
        excel_path = None
        for path in possible_paths:
            if path.exists():
                excel_path = path
                break
        
        if not excel_path:
            print("Excel database not found!")
            return
        
        print(f"Loading from: {excel_path}")
        wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
        ws = wb.active
        
        articles = []
        headers = []
        
        for row_idx, row in enumerate(ws.iter_rows(values_only=True), 1):
            if row_idx == 1:
                headers = [str(cell).strip() if cell else f"col_{i}" for i, cell in enumerate(row)]
                continue
            
            if not any(row):
                continue
            
            raw = {}
            for i, value in enumerate(row):
                if i < len(headers):
                    raw[headers[i]] = value
            
            date_val = raw.get("Date", "")
            if date_val and hasattr(date_val, 'strftime'):
                date_str = date_val.strftime("%Y-%m-%d")
            else:
                date_str = str(date_val)[:10] if date_val else ""
            
            article = {
                "title": raw.get("News Tittle", raw.get("Title", "")),
                "title_en": raw.get("Summary (EN)", ""),
                "title_ko": raw.get("Summary (KO)", ""),
                "summary_en": raw.get("Summary (EN)", ""),
                "summary_ko": raw.get("Summary (KO)", ""),
                "sector": raw.get("Business Sector", "Waste Water"),
                "area": raw.get("Area", "Environment"),
                "province": raw.get("Province", "Vietnam"),
                "source": raw.get("Source Name", ""),
                "url": raw.get("Source URL", ""),
                "date": date_str
            }
            
            if article.get("title") or article.get("url"):
                articles.append(article)
        
        wb.close()
        print(f"Loaded {len(articles)} articles")
        
        if articles:
            dashboard = DashboardUpdater()
            result = dashboard.update(articles)
            print(f"Dashboard created: {result}")
            
            excel = ExcelUpdater()
            excel.update(articles)
        else:
            print("No articles found in Excel!")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
