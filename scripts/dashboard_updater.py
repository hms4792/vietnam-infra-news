"""
Vietnam Infrastructure News Dashboard Updater
Injects real collected data into v6 template
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
        
        if not self.template_path.exists():
            logger.error("Template not found")
            return ""
        
        with open(self.template_path, 'r', encoding='utf-8') as f:
            template = f.read()
        
        # Replace placeholder with real data
        if '/*__BACKEND_DATA__*/[]' in template:
            html = template.replace('/*__BACKEND_DATA__*/[]', js_data)
        else:
            logger.error("Placeholder not found in template")
            return ""
        
        # Update timestamp
        html = html.replace('{{LAST_UPDATED}}', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        logger.info(f"Dashboard updated with {len(articles)} articles: {self.output_path}")
        return str(self.output_path)
    
    def _generate_js_data(self, articles: List[Dict]) -> str:
        """Generate JavaScript array from collected articles"""
        js_articles = []
        
        for i, article in enumerate(articles, 1):
            # Original title (usually Vietnamese)
            original_title = article.get("title", "No title")
            
            # Get AI-generated summaries
            summary_en = article.get("summary_en", "")
            summary_ko = article.get("summary_ko", "")
            summary_vi = article.get("summary_vi", "")
            
            # Title for each language:
            # - Korean: Use Korean summary as title (or original if none)
            # - English: Use English summary as title (or original if none)
            # - Vietnamese: Use original title (Vietnamese)
            title_ko = summary_ko[:150] if summary_ko and len(summary_ko) > 10 else original_title
            title_en = summary_en[:150] if summary_en and len(summary_en) > 10 else original_title
            title_vi = original_title
            
            # Full summaries
            full_summary_ko = summary_ko if summary_ko else original_title
            full_summary_en = summary_en if summary_en else original_title
            full_summary_vi = summary_vi if summary_vi else original_title
            
            # Normalize date to YYYY-MM-DD format
            date_str = article.get("published", "")
            if date_str:
                try:
                    if 'T' in date_str:
                        date_str = date_str.split('T')[0]
                    elif len(date_str) > 10:
                        date_str = date_str[:10]
                except:
                    date_str = datetime.now().strftime("%Y-%m-%d")
            else:
                date_str = datetime.now().strftime("%Y-%m-%d")
            
            # URL
            url = article.get("url", "")
            if not url:
                url = self._generate_search_url(article)
            
            # Map area to standard names
            area = article.get("area", "Environment")
            if "Environ" in area:
                area = "Environment"
            elif "Energy" in area:
                area = "Energy Develop."
            elif "Urban" in area:
                area = "Urban Develop."
            
            js_article = {
                "id": i,
                "date": date_str,
                "area": area,
                "sector": article.get("sector", "Waste Water"),
                "province": article.get("province", "Vietnam"),
                "source": article.get("source", "Unknown"),
                "title": {
                    "ko": title_ko,
                    "en": title_en,
                    "vi": title_vi
                },
                "summary": {
                    "ko": full_summary_ko[:500] if full_summary_ko else "",
                    "en": full_summary_en[:500] if full_summary_en else "",
                    "vi": full_summary_vi[:500] if full_summary_vi else ""
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
            ws.cell(row=i, column=2, value=article.get("published", "")[:10] if article.get("published") else "")
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
            return json.load(f).get("articles", [])
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
