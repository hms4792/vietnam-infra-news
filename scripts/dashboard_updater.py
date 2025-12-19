"""
Vietnam Infrastructure News Dashboard Updater
Updates dashboard HTML and Excel database files
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
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

from config.settings import (
    DATA_DIR, OUTPUT_DIR, TEMPLATE_DIR,
    DASHBOARD_FILENAME, DATABASE_FILENAME
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DashboardUpdater:
    """Updates HTML dashboard with latest data"""
    
    def __init__(self):
        self.template_path = TEMPLATE_DIR / "dashboard_template.html"
        self.output_path = OUTPUT_DIR / DASHBOARD_FILENAME
    
    def update(self, articles: List[Dict]) -> str:
        """Update dashboard HTML with new data"""
        # Generate JavaScript data
        js_data = self._generate_js_data(articles)
        
        # Read template or create new
        if self.template_path.exists():
            with open(self.template_path, 'r', encoding='utf-8') as f:
                template = f.read()
        else:
            template = self._get_default_template()
        
        # Replace data placeholder
        html = template.replace('const BACKEND_DATA = [];', f'const BACKEND_DATA = {js_data};')
        html = html.replace('{{LAST_UPDATED}}', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        # Save
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        logger.info(f"Dashboard updated: {self.output_path}")
        return str(self.output_path)
    
    def _generate_js_data(self, articles: List[Dict]) -> str:
        """Generate JavaScript array from articles"""
        js_articles = []
        
        for i, article in enumerate(articles, 1):
            js_article = {
                "id": i,
                "date": article.get("published", datetime.now().strftime("%Y-%m-%d")),
                "area": article.get("area", "Environment"),
                "sector": article.get("sector", "Waste Water"),
                "province": article.get("province", "Vietnam"),
                "source": article.get("source", "Unknown"),
                "title": {
                    "ko": article.get("summary_ko", article.get("title", ""))[:100],
                    "en": article.get("title", ""),
                    "vi": article.get("summary_vi", article.get("title", ""))[:100]
                },
                "summary": {
                    "ko": article.get("summary_ko", ""),
                    "en": article.get("summary_en", article.get("summary", "")),
                    "vi": article.get("summary_vi", "")
                },
                "url": article.get("url", "")
            }
            js_articles.append(js_article)
        
        return json.dumps(js_articles, ensure_ascii=False, indent=2)
    
    def _get_default_template(self) -> str:
        """Return default dashboard template"""
        return """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Vietnam Infrastructure News Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50">
    <div class="max-w-7xl mx-auto p-4">
        <h1 class="text-2xl font-bold text-teal-700 mb-4">Vietnam Infrastructure News</h1>
        <p class="text-sm text-gray-500 mb-4">Last Updated: {{LAST_UPDATED}}</p>
        <div id="news-container"></div>
    </div>
    <script>
        const BACKEND_DATA = [];
        
        function renderNews() {
            const container = document.getElementById('news-container');
            container.innerHTML = BACKEND_DATA.slice(0, 20).map(n => `
                <div class="bg-white p-4 rounded-lg shadow mb-2">
                    <span class="text-xs bg-teal-100 text-teal-700 px-2 py-1 rounded">${n.sector}</span>
                    <span class="text-xs text-gray-500 ml-2">${n.province}</span>
                    <h3 class="font-semibold mt-2">${n.title.en}</h3>
                    <p class="text-sm text-gray-600 mt-1">${n.summary.en}</p>
                    <p class="text-xs text-gray-400 mt-2">${n.date} | ${n.source}</p>
                </div>
            `).join('');
        }
        
        renderNews();
    </script>
</body>
</html>"""


class ExcelUpdater:
    """Updates Excel database with latest data"""
    
    def __init__(self):
        self.output_path = OUTPUT_DIR / DATABASE_FILENAME
    
    def update(self, articles: List[Dict]) -> str:
        """Update Excel database with new articles"""
        if not OPENPYXL_AVAILABLE:
            logger.warning("openpyxl not available. Skipping Excel update.")
            return ""
        
        # Create or load workbook
        if self.output_path.exists():
            wb = openpyxl.load_workbook(self.output_path)
        else:
            wb = openpyxl.Workbook()
        
        # Update Data sheet
        self._update_data_sheet(wb, articles)
        
        # Update Summary sheet
        self._update_summary_sheet(wb, articles)
        
        # Save
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(self.output_path)
        
        logger.info(f"Excel database updated: {self.output_path}")
        return str(self.output_path)
    
    def _update_data_sheet(self, wb, articles: List[Dict]):
        """Update main data sheet"""
        if "Data" in wb.sheetnames:
            ws = wb["Data"]
            ws.delete_rows(2, ws.max_row)  # Keep header
        else:
            ws = wb.active
            ws.title = "Data"
            
            # Add headers
            headers = ["ID", "Date", "Area", "Sector", "Province", "Source", 
                      "Title (EN)", "Title (KO)", "Summary", "URL", "AI Processed"]
            for col, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col, value=header)
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill(start_color="0D9488", end_color="0D9488", fill_type="solid")
                cell.alignment = Alignment(horizontal="center")
        
        # Add data
        for i, article in enumerate(articles, 2):
            ws.cell(row=i, column=1, value=i-1)
            ws.cell(row=i, column=2, value=article.get("published", ""))
            ws.cell(row=i, column=3, value=article.get("area", ""))
            ws.cell(row=i, column=4, value=article.get("sector", ""))
            ws.cell(row=i, column=5, value=article.get("province", ""))
            ws.cell(row=i, column=6, value=article.get("source", ""))
            ws.cell(row=i, column=7, value=article.get("title", ""))
            ws.cell(row=i, column=8, value=article.get("summary_ko", ""))
            ws.cell(row=i, column=9, value=article.get("summary", "")[:500])
            ws.cell(row=i, column=10, value=article.get("url", ""))
            ws.cell(row=i, column=11, value="Yes" if article.get("ai_processed") else "No")
            
            # Highlight 2025 data
            if "2025" in article.get("published", ""):
                for col in range(1, 12):
                    ws.cell(row=i, column=col).fill = PatternFill(
                        start_color="FFFF00", end_color="FFFF00", fill_type="solid"
                    )
        
        # Auto-adjust column widths
        for col in ws.columns:
            max_length = max(len(str(cell.value or "")) for cell in col)
            ws.column_dimensions[col[0].column_letter].width = min(max_length + 2, 50)
    
    def _update_summary_sheet(self, wb, articles: List[Dict]):
        """Update summary sheet"""
        if "Summary" in wb.sheetnames:
            ws = wb["Summary"]
            ws.delete_rows(1, ws.max_row)
        else:
            ws = wb.create_sheet("Summary")
        
        # Calculate statistics
        area_counts = {}
        sector_counts = {}
        province_counts = {}
        year_counts = {}
        
        for article in articles:
            area = article.get("area", "Unknown")
            sector = article.get("sector", "Unknown")
            province = article.get("province", "Unknown")
            year = article.get("published", "")[:4]
            
            area_counts[area] = area_counts.get(area, 0) + 1
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
            province_counts[province] = province_counts.get(province, 0) + 1
            year_counts[year] = year_counts.get(year, 0) + 1
        
        # Write summary
        ws.cell(row=1, column=1, value="Vietnam Infra News - Summary").font = Font(bold=True, size=14)
        ws.cell(row=2, column=1, value=f"Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        ws.cell(row=3, column=1, value=f"Total Articles: {len(articles)}")
        
        row = 5
        ws.cell(row=row, column=1, value="=== By Year ===").font = Font(bold=True)
        row += 1
        for year, count in sorted(year_counts.items(), reverse=True):
            ws.cell(row=row, column=1, value=year)
            ws.cell(row=row, column=2, value=count)
            row += 1
        
        row += 1
        ws.cell(row=row, column=1, value="=== By Area ===").font = Font(bold=True)
        row += 1
        for area, count in sorted(area_counts.items(), key=lambda x: -x[1]):
            ws.cell(row=row, column=1, value=area)
            ws.cell(row=row, column=2, value=count)
            row += 1
        
        row += 1
        ws.cell(row=row, column=1, value="=== By Sector ===").font = Font(bold=True)
        row += 1
        for sector, count in sorted(sector_counts.items(), key=lambda x: -x[1]):
            ws.cell(row=row, column=1, value=sector)
            ws.cell(row=row, column=2, value=count)
            row += 1
        
        row += 1
        ws.cell(row=row, column=1, value="=== Top Provinces ===").font = Font(bold=True)
        row += 1
        for province, count in sorted(province_counts.items(), key=lambda x: -x[1])[:15]:
            ws.cell(row=row, column=1, value=province)
            ws.cell(row=row, column=2, value=count)
            row += 1


class OutputGenerator:
    """Generates all output files"""
    
    def __init__(self):
        self.dashboard_updater = DashboardUpdater()
        self.excel_updater = ExcelUpdater()
    
    def generate_all(self, articles: List[Dict]) -> Dict[str, str]:
        """Generate all output files"""
        outputs = {}
        
        # Generate dashboard HTML
        try:
            outputs["dashboard"] = self.dashboard_updater.update(articles)
        except Exception as e:
            logger.error(f"Dashboard generation error: {e}")
            outputs["dashboard"] = ""
        
        # Generate Excel
        try:
            outputs["excel"] = self.excel_updater.update(articles)
        except Exception as e:
            logger.error(f"Excel generation error: {e}")
            outputs["excel"] = ""
        
        # Generate JSON
        try:
            json_path = OUTPUT_DIR / f"news_data_{datetime.now().strftime('%Y%m%d')}.json"
            json_path.parent.mkdir(parents=True, exist_ok=True)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "generated_at": datetime.now().isoformat(),
                    "total_count": len(articles),
                    "articles": articles
                }, f, ensure_ascii=False, indent=2)
            outputs["json"] = str(json_path)
        except Exception as e:
            logger.error(f"JSON generation error: {e}")
            outputs["json"] = ""
        
        logger.info(f"Generated outputs: {list(outputs.keys())}")
        return outputs


def load_articles() -> List[Dict]:
    """Load latest articles from data directory"""
    # Try processed files first
    processed_files = sorted(DATA_DIR.glob("processed_*.json"), reverse=True)
    
    if processed_files:
        filepath = processed_files[0]
    else:
        # Try news files
        news_files = sorted(DATA_DIR.glob("news_*.json"), reverse=True)
        if not news_files:
            return []
        filepath = news_files[0]
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("articles", [])
    except Exception as e:
        logger.error(f"Error loading articles: {e}")
        return []


def main():
    """Main function to generate outputs"""
    # Load articles
    articles = load_articles()
    
    if not articles:
        print("No articles found. Run news_collector.py first.")
        return
    
    print(f"Loaded {len(articles)} articles")
    
    # Generate outputs
    generator = OutputGenerator()
    outputs = generator.generate_all(articles)
    
    print(f"\n{'='*50}")
    print("Output Generation Complete")
    print(f"{'='*50}")
    
    for output_type, path in outputs.items():
        status = "✅ Generated" if path else "❌ Failed"
        print(f"{output_type.capitalize()}: {status}")
        if path:
            print(f"   → {path}")


if __name__ == "__main__":
    main()
