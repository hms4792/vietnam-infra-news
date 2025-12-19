"""
Vietnam Infrastructure News Dashboard Updater
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List
import sys
sys.path.append(str(Path(__file__).parent.parent))

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

from config.settings import DATA_DIR, OUTPUT_DIR

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DashboardUpdater:
    """Updates HTML dashboard with latest data"""
    
    def __init__(self):
        self.output_path = OUTPUT_DIR / "vietnam_dashboard.html"
    
    def update(self, articles: List[Dict]) -> str:
        """Generate dashboard HTML with real data"""
        js_data = self._generate_js_data(articles)
        html = self._generate_full_html(articles, js_data)
        
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        logger.info(f"Dashboard updated with {len(articles)} articles: {self.output_path}")
        return str(self.output_path)
    
    def _generate_js_data(self, articles: List[Dict]) -> str:
        """Generate JavaScript array from articles"""
        js_articles = []
        
        for i, article in enumerate(articles, 1):
            # Get title - prefer English
            title_en = article.get("title", "")
            title_ko = article.get("summary_ko", title_en)[:100]
            title_vi = article.get("summary_vi", title_en)[:100]
            
            # Get summary
            summary_en = article.get("summary_en", article.get("summary", ""))
            summary_ko = article.get("summary_ko", summary_en)
            summary_vi = article.get("summary_vi", summary_en)
            
            js_article = {
                "id": i,
                "date": article.get("published", datetime.now().strftime("%Y-%m-%d")),
                "area": article.get("area", "Environment"),
                "sector": article.get("sector", "Waste Water"),
                "province": article.get("province", "Vietnam"),
                "source": article.get("source", "Unknown"),
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
                "url": article.get("url", "")
            }
            js_articles.append(js_article)
        
        return json.dumps(js_articles, ensure_ascii=False, indent=2)
    
    def _generate_full_html(self, articles: List[Dict], js_data: str) -> str:
        """Generate complete dashboard HTML"""
        
        # Calculate stats
        area_counts = {"Environment": 0, "Energy Develop.": 0, "Urban Develop.": 0}
        today = datetime.now().strftime("%Y-%m-%d")
        today_count = 0
        
        for article in articles:
            area = article.get("area", "")
            if area in area_counts:
                area_counts[area] += 1
            if article.get("published", "").startswith(today):
                today_count += 1
        
        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vietnam Infrastructure News Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        .news-card:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.15); }}
        .tab-active {{ border-bottom: 3px solid #0d9488; color: #0d9488; font-weight: 600; }}
    </style>
</head>
<body class="bg-gray-50 min-h-screen">
    <header class="bg-gradient-to-r from-teal-600 to-emerald-600 text-white py-6 px-4 shadow-lg">
        <div class="max-w-7xl mx-auto">
            <h1 class="text-2xl md:text-3xl font-bold">🇻🇳 Vietnam Infrastructure News</h1>
            <p class="text-teal-100 mt-1">Daily Intelligence Dashboard</p>
            <p class="text-sm text-teal-200 mt-2">Last Updated: {datetime.now().strftime("%Y-%m-%d %H:%M")}</p>
        </div>
    </header>

    <main class="max-w-7xl mx-auto p-4">
        <!-- KPI Cards -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div class="bg-white rounded-xl p-4 shadow-md">
                <div class="text-3xl font-bold text-teal-600">{len(articles)}</div>
                <div class="text-sm text-gray-500">Total Articles</div>
            </div>
            <div class="bg-white rounded-xl p-4 shadow-md">
                <div class="text-3xl font-bold text-green-600">{area_counts["Environment"]}</div>
                <div class="text-sm text-gray-500">Environment</div>
            </div>
            <div class="bg-white rounded-xl p-4 shadow-md">
                <div class="text-3xl font-bold text-amber-600">{area_counts["Energy Develop."]}</div>
                <div class="text-sm text-gray-500">Energy</div>
            </div>
            <div class="bg-white rounded-xl p-4 shadow-md">
                <div class="text-3xl font-bold text-purple-600">{area_counts["Urban Develop."]}</div>
                <div class="text-sm text-gray-500">Urban Dev</div>
            </div>
        </div>

        <!-- Language Tabs -->
        <div class="bg-white rounded-xl shadow-md mb-6">
            <div class="flex border-b">
                <button onclick="setLanguage('en')" id="tab-en" class="px-6 py-3 tab-active">English</button>
                <button onclick="setLanguage('ko')" id="tab-ko" class="px-6 py-3 text-gray-500 hover:text-teal-600">한국어</button>
                <button onclick="setLanguage('vi')" id="tab-vi" class="px-6 py-3 text-gray-500 hover:text-teal-600">Tiếng Việt</button>
            </div>
        </div>

        <!-- Filters -->
        <div class="bg-white rounded-xl shadow-md p-4 mb-6">
            <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Area</label>
                    <select id="filterArea" onchange="filterNews()" class="w-full border rounded-lg p-2">
                        <option value="">All Areas</option>
                        <option value="Environment">Environment</option>
                        <option value="Energy Develop.">Energy Development</option>
                        <option value="Urban Develop.">Urban Development</option>
                    </select>
                </div>
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Source</label>
                    <select id="filterSource" onchange="filterNews()" class="w-full border rounded-lg p-2">
                        <option value="">All Sources</option>
                    </select>
                </div>
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Search</label>
                    <input type="text" id="searchInput" onkeyup="filterNews()" placeholder="Search..." class="w-full border rounded-lg p-2">
                </div>
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">Date</label>
                    <input type="date" id="filterDate" onchange="filterNews()" class="w-full border rounded-lg p-2">
                </div>
            </div>
        </div>

        <!-- News List -->
        <div class="bg-white rounded-xl shadow-md p-4">
            <h2 class="text-xl font-bold text-gray-800 mb-4">📰 Latest News <span id="newsCount" class="text-sm font-normal text-gray-500"></span></h2>
            <div id="newsList" class="space-y-3"></div>
        </div>
    </main>

    <script>
        const BACKEND_DATA = {js_data};
        
        let currentLang = 'en';
        let filteredData = [...BACKEND_DATA];
        
        function setLanguage(lang) {{
            currentLang = lang;
            document.querySelectorAll('[id^="tab-"]').forEach(t => t.classList.remove('tab-active'));
            document.getElementById('tab-' + lang).classList.add('tab-active');
            renderNews();
        }}
        
        function filterNews() {{
            const area = document.getElementById('filterArea').value;
            const source = document.getElementById('filterSource').value;
            const search = document.getElementById('searchInput').value.toLowerCase();
            const date = document.getElementById('filterDate').value;
            
            filteredData = BACKEND_DATA.filter(item => {{
                if (area && item.area !== area) return false;
                if (source && item.source !== source) return false;
                if (date && item.date !== date) return false;
                if (search) {{
                    const text = (item.title.en + ' ' + item.summary.en + ' ' + item.province).toLowerCase();
                    if (!text.includes(search)) return false;
                }}
                return true;
            }});
            
            renderNews();
        }}
        
        function renderNews() {{
            const container = document.getElementById('newsList');
            document.getElementById('newsCount').textContent = '(' + filteredData.length + ' articles)';
            
            if (filteredData.length === 0) {{
                container.innerHTML = '<p class="text-gray-500 text-center py-8">No articles found</p>';
                return;
            }}
            
            container.innerHTML = filteredData.slice(0, 50).map(item => `
                <div class="news-card border rounded-lg p-4 transition-all cursor-pointer hover:border-teal-300" onclick="openArticle('${{item.url}}')">
                    <div class="flex flex-wrap gap-2 mb-2">
                        <span class="px-2 py-1 bg-teal-100 text-teal-700 text-xs rounded-full">${{item.area}}</span>
                        <span class="px-2 py-1 bg-gray-100 text-gray-600 text-xs rounded-full">${{item.sector}}</span>
                        <span class="px-2 py-1 bg-blue-100 text-blue-600 text-xs rounded-full">${{item.province}}</span>
                    </div>
                    <h3 class="font-semibold text-gray-800 mb-1">${{item.title[currentLang] || item.title.en}}</h3>
                    <p class="text-sm text-gray-600 mb-2">${{(item.summary[currentLang] || item.summary.en || '').substring(0, 150)}}...</p>
                    <div class="flex justify-between items-center text-xs text-gray-400">
                        <span>${{item.date}} | ${{item.source}}</span>
                        <span class="text-teal-600 hover:underline">Read more →</span>
                    </div>
                </div>
            `).join('');
        }}
        
        function openArticle(url) {{
            if (url) window.open(url, '_blank');
        }}
        
        function initFilters() {{
            const sources = [...new Set(BACKEND_DATA.map(d => d.source))].sort();
            const sourceSelect = document.getElementById('filterSource');
            sources.forEach(s => {{
                const opt = document.createElement('option');
                opt.value = s;
                opt.textContent = s;
                sourceSelect.appendChild(opt);
            }});
        }}
        
        // Initialize
        initFilters();
        renderNews();
    </script>
</body>
</html>'''


class ExcelUpdater:
    """Updates Excel database"""
    
    def __init__(self):
        self.output_path = OUTPUT_DIR / "vietnam_infra_news_database.xlsx"
    
    def update(self, articles: List[Dict]) -> str:
        if not OPENPYXL_AVAILABLE:
            logger.warning("openpyxl not available")
            return ""
        
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Data"
        
        headers = ["ID", "Date", "Area", "Sector", "Province", "Source", "Title", "Summary", "URL"]
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill(start_color="0D9488", fill_type="solid")
        
        for i, article in enumerate(articles, 2):
            ws.cell(row=i, column=1, value=i-1)
            ws.cell(row=i, column=2, value=article.get("published", ""))
            ws.cell(row=i, column=3, value=article.get("area", ""))
            ws.cell(row=i, column=4, value=article.get("sector", ""))
            ws.cell(row=i, column=5, value=article.get("province", ""))
            ws.cell(row=i, column=6, value=article.get("source", ""))
            ws.cell(row=i, column=7, value=article.get("title", "")[:200])
            ws.cell(row=i, column=8, value=article.get("summary_en", article.get("summary", ""))[:500])
            ws.cell(row=i, column=9, value=article.get("url", ""))
        
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(self.output_path)
        logger.info(f"Excel updated: {self.output_path}")
        return str(self.output_path)


class OutputGenerator:
    def __init__(self):
        self.dashboard = DashboardUpdater()
        self.excel = ExcelUpdater()
    
    def generate_all(self, articles: List[Dict]) -> Dict[str, str]:
        outputs = {}
        
        try:
            outputs["dashboard"] = self.dashboard.update(articles)
        except Exception as e:
            logger.error(f"Dashboard error: {e}")
            outputs["dashboard"] = ""
        
        try:
            outputs["excel"] = self.excel.update(articles)
        except Exception as e:
            logger.error(f"Excel error: {e}")
            outputs["excel"] = ""
        
        try:
            json_path = OUTPUT_DIR / f"news_data_{datetime.now().strftime('%Y%m%d')}.json"
            json_path.parent.mkdir(parents=True, exist_ok=True)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump({"generated_at": datetime.now().isoformat(), "total": len(articles), "articles": articles}, f, ensure_ascii=False, indent=2)
            outputs["json"] = str(json_path)
        except Exception as e:
            logger.error(f"JSON error: {e}")
            outputs["json"] = ""
        
        return outputs


def load_articles() -> List[Dict]:
    processed_files = sorted(DATA_DIR.glob("processed_*.json"), reverse=True)
    if not processed_files:
        news_files = sorted(DATA_DIR.glob("news_*.json"), reverse=True)
        if not news_files:
            return []
        processed_files = news_files
    
    try:
        with open(processed_files[0], 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("articles", [])
    except:
        return []


def main():
    articles = load_articles()
    if not articles:
        print("No articles found")
        return
    
    generator = OutputGenerator()
    outputs = generator.generate_all(articles)
    
    print(f"Generated {len(outputs)} outputs with {len(articles)} articles")


if __name__ == "__main__":
    main()
