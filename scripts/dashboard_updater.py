"""
Vietnam Infrastructure News Dashboard Updater
Maintains existing database and appends new articles only
Uses Keywords sheet Category for Business Sector classification
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
    from openpyxl.styles import Font, PatternFill, Alignment
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

from config.settings import DATA_DIR, OUTPUT_DIR, TEMPLATE_DIR

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

EXISTING_DB_PATH = Path(__file__).parent.parent / "data" / "Vietnam_Infra_News_Database_Final.xlsx"

KEYWORDS_BY_SECTOR = {
    "Solid Waste": ["waste-to-energy", "solid waste", "landfill", "incineration", "recycling", 
                   "circular economy", "wte", "garbage", "rubbish", "trash", "municipal waste"],
    "Waste Water": ["wastewater", "waste water", "wwtp", "sewage", "water treatment plant", 
                   "sewerage", "effluent", "sludge", "drainage"],
    "Water Supply/Drainage": ["clean water", "water supply", "water scarcity", "reservoir", 
                             "potable water", "tap water", "water infrastructure", "drinking water"],
    "Power": ["power plant", "electricity", "lng power", "gas-to-power", "thermal power", 
             "natural gas", "ccgt", "combined cycle", "solar", "wind", "renewable", 
             "biomass", "offshore wind", "onshore wind", "pdp8", "feed-in tariff", "hydropower"],
    "Oil & Gas": ["oil exploration", "gas field", "upstream", "midstream", "petroleum", 
                 "offshore drilling", "oil and gas", "lng terminal", "refinery"],
    "Industrial Parks": ["industrial park", "industrial zone", "fdi", "foreign investment", 
                        "manufacturing zone", "eco-industrial", "economic zone"],
    "Smart City": ["smart city", "urban area", "zoning", "new urban", "tod", 
                  "digital transformation", "urban development", "city planning"],
}

AREA_BY_SECTOR = {
    "Solid Waste": "Environment",
    "Waste Water": "Environment",
    "Water Supply/Drainage": "Environment",
    "Power": "Energy Develop.",
    "Oil & Gas": "Energy Develop.",
    "Industrial Parks": "Urban Develop.",
    "Smart City": "Urban Develop.",
}

SECTOR_PRIORITY = [
    "Waste Water",
    "Solid Waste", 
    "Water Supply/Drainage",
    "Power",
    "Oil & Gas",
    "Smart City",
    "Industrial Parks",
]


def classify_by_keywords(title: str, summary: str = "") -> Tuple[str, str]:
    text = (str(title) + " " + str(summary)).lower()
    
    for sector in SECTOR_PRIORITY:
        keywords = KEYWORDS_BY_SECTOR.get(sector, [])
        for keyword in keywords:
            if keyword.lower() in text:
                area = AREA_BY_SECTOR.get(sector, "Environment")
                return sector, area
    
    return "Waste Water", "Environment"


class DashboardUpdater:
    def __init__(self):
        self.template_path = TEMPLATE_DIR / "dashboard_template.html"
        self.output_path = OUTPUT_DIR / "vietnam_dashboard.html"
    
    def update(self, all_articles: List[Dict]) -> str:
        js_data = self._generate_js_data(all_articles)
        
        if not self.template_path.exists():
            logger.error("Template not found")
            return ""
        
        with open(self.template_path, 'r', encoding='utf-8') as f:
            template = f.read()
        
        if '/*__BACKEND_DATA__*/[]' in template:
            html = template.replace('/*__BACKEND_DATA__*/[]', js_data)
        else:
            logger.error("Placeholder not found in template")
            return ""
        
        html = html.replace('{{LAST_UPDATED}}', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        logger.info(f"Dashboard updated with {len(all_articles)} articles")
        return str(self.output_path)
    
    def _generate_js_data(self, articles: List[Dict]) -> str:
        js_articles = []
        
        for i, article in enumerate(articles, 1):
            title = article.get("title", article.get("News Tittle", "No title"))
            summary = article.get("summary", article.get("Short summary", ""))
            
            if isinstance(title, dict):
                title_ko = title.get("ko", "")
                title_en = title.get("en", "")
                title_vi = title.get("vi", "")
            else:
                title_str = str(title)
                title_ko = article.get("summary_ko", title_str)[:150]
                title_en = article.get("summary_en", title_str)[:150]
                title_vi = title_str
            
            if isinstance(summary, dict):
                summary_ko = summary.get("ko", "")
                summary_en = summary.get("en", "")
                summary_vi = summary.get("vi", "")
            else:
                summary_str = str(summary)
                summary_ko = article.get("summary_ko", summary_str)
                summary_en = article.get("summary_en", summary_str)
                summary_vi = summary_str
            
            date_str = article.get("date", article.get("Date", article.get("published", "")))
            if hasattr(date_str, 'strftime'):
                date_str = date_str.strftime("%Y-%m-%d")
            elif date_str:
                date_str = str(date_str)[:10]
            else:
                date_str = datetime.now().strftime("%Y-%m-%d")
            
            sector = article.get("sector", article.get("Business Sector", ""))
            area = article.get("area", article.get("Area", ""))
            
            if not sector or sector not in AREA_BY_SECTOR:
                sector, area = classify_by_keywords(title, summary)
            elif not area:
                area = AREA_BY_SECTOR.get(sector, "Environment")
            
            js_article = {
                "id": i,
                "date": date_str,
                "area": area,
                "sector": sector,
                "province": article.get("province", article.get("Province", "Vietnam")),
                "source": article.get("source", article.get("Source", "Unknown")),
                "title": {
                    "ko": (title_ko or title_vi)[:200],
                    "en": (title_en or title_vi)[:200],
                    "vi": (title_vi or str(title))[:200]
                },
                "summary": {
                    "ko": (summary_ko or summary_vi)[:500],
                    "en": (summary_en or summary_vi)[:500],
                    "vi": (summary_vi or str(summary))[:500]
                },
                "url": article.get("url", article.get("Link", ""))
            }
            js_articles.append(js_article)
        
        return json.dumps(js_articles, ensure_ascii=False, indent=2)


class ExcelUpdater:
    def __init__(self):
        self.existing_db_path = EXISTING_DB_PATH
        self.output_path = OUTPUT_DIR / "vietnam_infra_news_database.xlsx"
    
    def load_existing_data(self) -> List[Dict]:
        if not PANDAS_AVAILABLE:
            logger.warning("pandas not available")
            return []
        
        if not self.existing_db_path.exists():
            logger.warning(f"Existing database not found: {self.existing_db_path}")
            return []
        
        try:
            xl = pd.ExcelFile(self.existing_db_path)
            sheet_name = None
            for name in xl.sheet_names:
                if "Data" in name or "Database" in name:
                    sheet_name = name
                    break
            
            if not sheet_name:
                sheet_name = xl.sheet_names[0]
            
            df = pd.read_excel(self.existing_db_path, sheet_name=sheet_name)
            logger.info(f"Loaded {len(df)} existing articles from '{sheet_name}'")
            
            articles = []
            for _, row in df.iterrows():
                date_val = row.get("Date", "")
                if hasattr(date_val, 'strftime'):
                    date_val = date_val.strftime("%Y-%m-%d")
                elif pd.notna(date_val):
                    date_val = str(date_val)[:10]
                else:
                    date_val = ""
                
                articles.append({
                    "Area": str(row.get("Area", "")) if pd.notna(row.get("Area")) else "",
                    "Business Sector": str(row.get("Business Sector", "")) if pd.notna(row.get("Business Sector")) else "",
                    "Province": str(row.get("Province", "")) if pd.notna(row.get("Province")) else "",
                    "News Tittle": str(row.get("News Tittle", "")) if pd.notna(row.get("News Tittle")) else "",
                    "Date": date_val,
                    "Source": str(row.get("Source", "")) if pd.notna(row.get("Source")) else "",
                    "Link": str(row.get("Link", "")) if pd.notna(row.get("Link")) else "",
                    "Short summary": str(row.get("Short summary", "")) if pd.notna(row.get("Short summary")) else "",
                })
            return articles
        except Exception as e:
            logger.error(f"Error loading existing database: {e}")
            return []
    
    def merge_articles(self, existing: List[Dict], new_articles: List[Dict]) -> List[Dict]:
        existing_keys = set()
        for article in existing:
            url = str(article.get("Link", "")).lower().strip()
            title = str(article.get("News Tittle", "")).lower().strip()[:80]
            if url and url != "nan":
                existing_keys.add(url)
            if title and title != "nan":
                existing_keys.add(title)
        
        new_count = 0
        for article in new_articles:
            url = str(article.get("url", article.get("Link", ""))).lower().strip()
            title = str(article.get("title", article.get("News Tittle", ""))).lower().strip()[:80]
            
            is_duplicate = False
            if url and url != "nan" and url in existing_keys:
                is_duplicate = True
            if title and title != "nan" and title in existing_keys:
                is_duplicate = True
            
            if not is_duplicate:
                original_title = article.get("title", article.get("News Tittle", ""))
                summary = article.get("summary_en", article.get("summary", article.get("Short summary", "")))
                
                sector, area = classify_by_keywords(str(original_title), str(summary))
                
                date_val = article.get("published", article.get("Date", ""))
                if isinstance(date_val, str) and 'T' in date_val:
                    date_val = date_val.split('T')[0]
                elif not date_val:
                    date_val = datetime.now().strftime("%Y-%m-%d")
                
                new_article = {
                    "Area": area,
                    "Business Sector": sector,
                    "Province": article.get("province", article.get("Province", "Vietnam")),
                    "News Tittle": str(original_title)[:200],
                    "Date": str(date_val)[:10],
                    "Source": article.get("source", article.get("Source", "Unknown")),
                    "Link": article.get("url", article.get("Link", "")),
                    "Short summary": str(summary)[:500],
                }
                existing.append(new_article)
                
                if url and url != "nan":
                    existing_keys.add(url)
                if title and title != "nan":
                    existing_keys.add(title)
                new_count += 1
        
        logger.info(f"Added {new_count} new articles (total: {len(existing)})")
        return existing
    
    def update(self, new_articles: List[Dict]) -> str:
        if not OPENPYXL_AVAILABLE or not PANDAS_AVAILABLE:
            logger.warning("Required libraries not available")
            return ""
        
        existing = self.load_existing_data()
        all_articles = self.merge_articles(existing, new_articles)
        
        all_articles.sort(key=lambda x: str(x.get("Date", ""))[:10], reverse=True)
        
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Data set (Database)"
        
        columns = ["Area", "Business Sector", "Province", "News Tittle", "Date", "Source", "Link", "Short summary"]
        
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="0D9488", fill_type="solid")
        
        for col, header in enumerate(columns, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")
        
        yellow_fill = PatternFill(start_color="FFFF00", fill_type="solid")
        current_year = datetime.now().year
        
        for row_idx, article in enumerate(all_articles, 2):
            for col_idx, col_name in enumerate(columns, 1):
                value = article.get(col_name, "")
                cell = ws.cell(row=row_idx, column=col_idx, value=str(value)[:500] if col_idx == 8 else str(value)[:200])
                
                date_val = article.get("Date", "")
                if date_val:
                    try:
                        year = int(str(date_val)[:4])
                        if year == current_year:
                            cell.fill = yellow_fill
                    except:
                        pass
        
        col_widths = [15, 22, 18, 70, 12, 22, 60, 100]
        for i, width in enumerate(col_widths, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = width
        
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(self.output_path)
        
        logger.info(f"Excel updated: {self.output_path} ({len(all_articles)} total)")
        return str(self.output_path)
    
    def get_all_articles_for_dashboard(self, new_articles: List[Dict]) -> List[Dict]:
        existing = self.load_existing_data()
        all_articles = self.merge_articles(existing.copy(), new_articles)
        
        dashboard_articles = []
        for article in all_articles:
            title = article.get("News Tittle", "")
            summary = article.get("Short summary", "")
            
            sector = article.get("Business Sector", "")
            area = article.get("Area", "")
            
            if not sector or sector not in AREA_BY_SECTOR:
                sector, area = classify_by_keywords(title, summary)
            elif not area:
                area = AREA_BY_SECTOR.get(sector, "Environment")
            
            dashboard_articles.append({
                "area": area,
                "sector": sector,
                "province": article.get("Province", "Vietnam"),
                "title": title,
                "date": str(article.get("Date", ""))[:10],
                "source": article.get("Source", ""),
                "url": article.get("Link", ""),
                "summary": summary,
                "summary_en": summary,
                "summary_ko": summary,
                "summary_vi": summary,
            })
        
        return dashboard_articles


class OutputGenerator:
    def __init__(self):
        self.dashboard = DashboardUpdater()
        self.excel = ExcelUpdater()
    
    def generate_all(self, new_articles: List[Dict]) -> Dict[str, str]:
        outputs = {}
        
        all_articles = self.excel.get_all_articles_for_dashboard(new_articles)
        
        try:
            outputs["dashboard"] = self.dashboard.update(all_articles)
        except Exception as e:
            logger.error(f"Dashboard error: {e}")
            outputs["dashboard"] = ""
        
        try:
            outputs["excel"] = self.excel.update(new_articles)
        except Exception as e:
            logger.error(f"Excel error: {e}")
            outputs["excel"] = ""
        
        try:
            json_path = OUTPUT_DIR / f"news_data_{datetime.now().strftime('%Y%m%d')}.json"
            json_path.parent.mkdir(parents=True, exist_ok=True)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "generated_at": datetime.now().isoformat(),
                    "total": len(all_articles),
                    "new_articles": len(new_articles),
                    "articles": all_articles
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
    generator = OutputGenerator()
    outputs = generator.generate_all(articles)
    print(f"Generated outputs")


if __name__ == "__main__":
    main()
