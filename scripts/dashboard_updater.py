"""
Vietnam Infrastructure News Dashboard Updater
Uses the original v6 template and injects real collected data
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from urllib.parse import quote
import sys
sys.path.append(str(Path(__file__).parent.parent))

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

from config.settings import DATA_DIR, OUTPUT_DIR, TEMPLATE_DIR

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DashboardUpdater:
    """Updates HTML dashboard with latest data using v6 template"""
    
    def __init__(self):
        self.template_path = TEMPLATE_DIR / "dashboard_template.html"
        self.output_path = OUTPUT_DIR / "vietnam_dashboard.html"
    
    def update(self, articles: List[Dict]) -> str:
        """Update dashboard HTML with real collected data"""
        
        js_data = self._generate_js_data(articles)
        
        if self.template_path.exists():
            with open(self.template_path, 'r', encoding='utf-8') as f:
                template = f.read()
            
            # Replace placeholder with real data
            html = template.replace('/*__BACKEND_DATA__*/[]', js_data)
            html = html.replace('{{LAST_UPDATED}}', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            
        else:
            logger.warning("Template not found")
            return ""
        
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        logger.info(f"Dashboard updated with {len(articles)} articles: {self.output_path}")
        return str(self.output_path)
    
    def _generate_js_data(self, articles: List[Dict]) -> str:
        """Generate JavaScript array from collected articles"""
        js_articles = []
        
        for i, article in enumerate(articles, 1):
            title_en = article.get("title", "No title")
            title_ko = article.get("summary_ko", title_en)[:150] if article.get("summary_ko") else title_en
            title_vi = article.get("summary_vi", title_en)[:150] if article.get("summary_vi") else title_en
            
            summary_en = article.get("summary_en", article.get("summary", ""))
            summary_ko = article.get("summary_ko", summary_en)
            summary_vi = article.get("summary_vi", summary_en)
            
            url = article.get("url", "")
            if not url:
                url = self._generate_search_url(article)
            
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
                "url": url
            }
            js_articles.append(js_article)
        
        return json.dumps(js_articles, ensure_ascii=False, indent=2)
    
    def _generate_search_url(self, article: Dict) -> str:
        """Generate search URL based on source"""
        source = article.get("source", "")
        title = article.get("title", "")
        
        source_urls = {
            "VnExpress": "https://timkiem.vnexpress.net/?q=",
            "Tuoi Tre": "https://tuoitre.vn/tim-kiem.htm?keywords=",
            "VietnamNews": "https://vietnamnews.vn/search?q=",
            "VnEconomy": "https://vneconomy.vn/tim-kiem?q=",
            "Thanh Nien": "https://thanhnien.vn/tim-kiem/?q=",
        }
        
        base_url = source_urls.get(source, "https://www.google.com/search?q=")
        query = quote(title[:100])
        return base_url + query


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
        
        headers = ["ID", "Date", "Area", "Sector", "Province", "Source", "Title", "Summary_EN", "Summary_KO", "URL"]
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
            ws.cell(row=i, column=8, value=article.get("summary_en", "")[:500])
            ws.cell(row=i, column=9, value=article.get("summary_ko", "")[:500])
            ws.cell(row=i, column=10, value=article.get("url", ""))
        
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
                json.dump({
                    "generated_at": datetime.now().isoformat(),
                    "total": len(articles),
                    "articles": articles
                }, f, ensure_ascii=False, indent=2)
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
    print(f"Generated outputs with {len(articles)} articles")


if __name__ == "__main__":
    main()
