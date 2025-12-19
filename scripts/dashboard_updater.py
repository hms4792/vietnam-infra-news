"""
Vietnam Infrastructure News Dashboard Updater
Maintains existing database and appends new articles only
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
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils.dataframe import dataframe_to_rows
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

# Path to existing database
EXISTING_DB_PATH = Path(__file__).parent.parent / "data" / "Vietnam_Infra_News_Database_Final.xlsx"

# Sector mapping from keywords to standard Business Sector names
SECTOR_MAPPING = {
    # Environment
    "wastewater": "Waste Water",
    "waste water": "Waste Water",
    "sewage": "Waste Water",
    "water treatment": "Waste Water",
    "solid waste": "Solid Waste",
    "garbage": "Solid Waste",
    "landfill": "Solid Waste",
    "recycling": "Solid Waste",
    "waste management": "Solid Waste",
    "water supply": "Water Supply/Drainage",
    "drainage": "Water Supply/Drainage",
    "clean water": "Water Supply/Drainage",
    "drinking water": "Water Supply/Drainage",
    # Energy
    "power": "Power",
    "electricity": "Power",
    "solar": "Power",
    "wind": "Power",
    "renewable": "Power",
    "lng": "Power",
    "thermal": "Power",
    "hydropower": "Power",
    "oil": "Oil & Gas",
    "gas": "Oil & Gas",
    "petroleum": "Oil & Gas",
    # Urban
    "smart city": "Smart City",
    "digital": "Smart City",
    "iot": "Smart City",
    "industrial park": "Industrial Parks",
    "industrial zone": "Industrial Parks",
    "economic zone": "Industrial Parks",
    "fdi": "Industrial Parks",
}

# Area mapping
AREA_MAPPING = {
    "Waste Water": "Environment",
    "Solid Waste": "Environment",
    "Water Supply/Drainage": "Environment",
    "Power": "Energy Develop.",
    "Oil & Gas": "Energy Develop.",
    "Smart City": "Urban Develop.",
    "Industrial Parks": "Urban Develop.",
}


def classify_sector(title: str, summary: str = "") -> tuple:
    """Classify article into Business Sector and Area based on content"""
    text = (title + " " + summary).lower()
    
    for keyword, sector in SECTOR_MAPPING.items():
        if keyword in text:
            return sector, AREA_MAPPING.get(sector, "Environment")
    
    # Default
    return "Waste Water", "Environment"


class DashboardUpdater:
    """Updates HTML dashboard with all data (existing + new)"""
    
    def __init__(self):
        self.template_path = TEMPLATE_DIR / "dashboard_template.html"
        self.output_path = OUTPUT_DIR / "vietnam_dashboard.html"
    
    def update(self, all_articles: List[Dict]) -> str:
        """Update dashboard HTML with all articles"""
        
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
        
        logger.info(f"Dashboard updated with {len(all_articles)} articles: {self.output_path}")
        return str(self.output_path)
    
    def _generate_js_data(self, articles: List[Dict]) -> str:
        """Generate JavaScript array from all articles"""
        js_articles = []
        
        for i, article in enumerate(articles, 1):
            title = article.get("title", article.get("News Tittle", "No title"))
            summary = article.get("summary", article.get("Short summary", ""))
            
            # Handle multilingual titles/summaries
            if isinstance(title, dict):
                title_ko = title.get("ko", "")
                title_en = title.get("en", "")
                title_vi = title.get("vi", "")
            else:
                title_ko = article.get("summary_ko", str(title))[:150]
                title_en = article.get("summary_en", str(title))[:150]
                title_vi = str(title)
            
            if isinstance(summary, dict):
                summary_ko = summary.get("ko", "")
                summary_en = summary.get("en", "")
                summary_vi = summary.get("vi", "")
            else:
                summary_ko = article.get("summary_ko", str(summary))
                summary_en = article.get("summary_en", str(summary))
                summary_vi = str(summary)
            
            # Get date
            date_str = article.get("date", article.get("Date", article.get("published", "")))
            if hasattr(date_str, 'strftime'):
                date_str = date_str.strftime("%Y-%m-%d")
            elif date_str:
                date_str = str(date_str)[:10]
            else:
                date_str = datetime.now().strftime("%Y-%m-%d")
            
            # Get sector and area
            sector = article.get("sector", article.get("Business Sector", "Waste Water"))
            area = article.get("area", article.get("Area", "Environment"))
            
            js_article = {
                "id": i,
                "date": date_str,
                "area": area,
                "sector": sector,
                "province": article.get("province", article.get("Province", "Vietnam")),
                "source": article.get("source", article.get("Source", "Unknown")),
                "title": {
                    "ko": title_ko[:200] if title_ko else title_vi[:200],
                    "en": title_en[:200] if title_en else title_vi[:200],
                    "vi": title_vi[:200] if title_vi else str(title)[:200]
                },
                "summary": {
                    "ko": summary_ko[:500] if summary_ko else summary_vi[:500],
                    "en": summary_en[:500] if summary_en else summary_vi[:500],
                    "vi": summary_vi[:500] if summary_vi else str(summary)[:500]
                },
                "url": article.get("url", article.get("Link", ""))
            }
            js_articles.append(js_article)
        
        return json.dumps(js_articles, ensure_ascii=False, indent=2)


class ExcelUpdater:
    """Updates Excel database - maintains existing data and appends new articles"""
    
    def __init__(self):
        self.existing_db_path = EXISTING_DB_PATH
        self.output_path = OUTPUT_DIR / "vietnam_infra_news_database.xlsx"
    
    def load_existing_data(self) -> List[Dict]:
        """Load existing database"""
        if not PANDAS_AVAILABLE:
            logger.warning("pandas not available")
            return []
        
        if not self.existing_db_path.exists():
            logger.warning(f"Existing database not found: {self.existing_db_path}")
            return []
        
        try:
            df = pd.read_excel(self.existing_db_path, sheet_name="Data set (Database)")
            logger.info(f"Loaded {len(df)} existing articles from database")
            
            articles = []
            for _, row in df.iterrows():
                articles.append({
                    "Area": row.get("Area", ""),
                    "Business Sector": row.get("Business Sector", ""),
                    "Province": row.get("Province", ""),
                    "News Tittle": row.get("News Tittle", ""),
                    "Date": row.get("Date"),
                    "Source": row.get("Source", ""),
                    "Link": row.get("Link", ""),
                    "Short summary": row.get("Short summary", ""),
                })
            return articles
        except Exception as e:
            logger.error(f"Error loading existing database: {e}")
            return []
    
    def merge_articles(self, existing: List[Dict], new_articles: List[Dict]) -> List[Dict]:
        """Merge existing and new articles, avoiding duplicates"""
        # Create set of existing URLs/titles for deduplication
        existing_keys = set()
        for article in existing:
            url = article.get("Link", "")
            title = article.get("News Tittle", "")
            if url:
                existing_keys.add(url.lower().strip())
            if title:
                existing_keys.add(title.lower().strip()[:100])
        
        # Convert new articles to existing format and check for duplicates
        new_count = 0
        for article in new_articles:
            url = article.get("url", article.get("Link", ""))
            title = article.get("title", article.get("News Tittle", ""))
            
            # Check if duplicate
            is_duplicate = False
            if url and url.lower().strip() in existing_keys:
                is_duplicate = True
            if title and title.lower().strip()[:100] in existing_keys:
                is_duplicate = True
            
            if not is_duplicate:
                # Classify sector based on content
                summary = article.get("summary_en", article.get("summary", article.get("Short summary", "")))
                sector, area = classify_sector(str(title), str(summary))
                
                # Use classified values or keep original if already set properly
                orig_sector = article.get("sector", article.get("Business Sector", ""))
                orig_area = article.get("area", article.get("Area", ""))
                
                if orig_sector in AREA_MAPPING:
                    sector = orig_sector
                    area = AREA_MAPPING[orig_sector]
                
                # Get date
                date_val = article.get("published", article.get("Date", datetime.now().strftime("%Y-%m-%d")))
                if isinstance(date_val, str) and 'T' in date_val:
                    date_val = date_val.split('T')[0]
                
                new_article = {
                    "Area": area,
                    "Business Sector": sector,
                    "Province": article.get("province", article.get("Province", "Vietnam")),
                    "News Tittle": str(title)[:200],
                    "Date": date_val,
                    "Source": article.get("source", article.get("Source", "Unknown")),
                    "Link": url,
                    "Short summary": article.get("summary_en", article.get("summary", article.get("Short summary", "")))[:500],
                }
                existing.append(new_article)
                existing_keys.add(url.lower().strip() if url else "")
                existing_keys.add(title.lower().strip()[:100] if title else "")
                new_count += 1
        
        logger.info(f"Added {new_count} new articles (total: {len(existing)})")
        return existing
    
    def update(self, new_articles: List[Dict]) -> str:
        """Update Excel with existing + new articles"""
        if not OPENPYXL_AVAILABLE or not PANDAS_AVAILABLE:
            logger.warning("Required libraries not available")
            return ""
        
        # Load existing data
        existing = self.load_existing_data()
        
        # Merge with new articles
        all_articles = self.merge_articles(existing, new_articles)
        
        # Sort by date descending
        all_articles.sort(key=lambda x: str(x.get("Date", ""))[:10], reverse=True)
        
        # Create DataFrame
        df = pd.DataFrame(all_articles)
        
        # Ensure column order
        columns = ["Area", "Business Sector", "Province", "News Tittle", "Date", "Source", "Link", "Short summary"]
        for col in columns:
            if col not in df.columns:
                df[col] = ""
        df = df[columns]
        
        # Create workbook
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Data set (Database)"
        
        # Header style
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="0D9488", fill_type="solid")
        
        # Write headers
        for col, header in enumerate(columns, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")
        
        # Write data
        yellow_fill = PatternFill(start_color="FFFF00", fill_type="solid")
        current_year = datetime.now().year
        
        for row_idx, row_data in enumerate(df.values, 2):
            for col_idx, value in enumerate(row_data, 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                if hasattr(value, 'strftime'):
                    cell.value = value.strftime("%Y-%m-%d")
                elif pd.isna(value):
                    cell.value = ""
                else:
                    cell.value = str(value)[:500] if col_idx == 8 else str(value)[:200]
                
                # Highlight current year data
                date_val = row_data[4]  # Date column
                if date_val:
                    try:
                        year = int(str(date_val)[:4])
                        if year == current_year:
                            cell.fill = yellow_fill
                    except:
                        pass
        
        # Auto-adjust column widths
        col_widths = [15, 20, 15, 60, 12, 20, 50, 80]
        for i, width in enumerate(col_widths, 1):
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = width
        
        # Save
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(self.output_path)
        
        # Also update the source database
        try:
            source_output = Path(__file__).parent.parent / "data" / "Vietnam_Infra_News_Database_Final.xlsx"
            wb.save(source_output)
            logger.info(f"Source database also updated: {source_output}")
        except Exception as e:
            logger.warning(f"Could not update source database: {e}")
        
        logger.info(f"Excel updated: {self.output_path} ({len(all_articles)} total articles)")
        return str(self.output_path)
    
    def get_all_articles_for_dashboard(self, new_articles: List[Dict]) -> List[Dict]:
        """Get all articles (existing + new) formatted for dashboard"""
        existing = self.load_existing_data()
        all_articles = self.merge_articles(existing.copy(), new_articles)
        
        # Convert to dashboard format
        dashboard_articles = []
        for article in all_articles:
            dashboard_articles.append({
                "area": article.get("Area", "Environment"),
                "sector": article.get("Business Sector", "Waste Water"),
                "province": article.get("Province", "Vietnam"),
                "title": article.get("News Tittle", ""),
                "date": str(article.get("Date", ""))[:10],
                "source": article.get("Source", ""),
                "url": article.get("Link", ""),
                "summary": article.get("Short summary", ""),
                "summary_en": article.get("Short summary", ""),
                "summary_ko": article.get("Short summary", ""),
                "summary_vi": article.get("Short summary", ""),
            })
        
        return dashboard_articles


class OutputGenerator:
    def __init__(self):
        self.dashboard = DashboardUpdater()
        self.excel = ExcelUpdater()
    
    def generate_all(self, new_articles: List[Dict]) -> Dict[str, str]:
        outputs = {}
        
        # Get all articles (existing + new) for dashboard
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
```

**Commit changes** 클릭

---

## 2️⃣ `requirements.txt` 수정

GitHub → `requirements.txt` → **연필 아이콘**

**pandas 추가:**
```
aiohttp>=3.8.0
feedparser>=6.0.0
beautifulsoup4>=4.12.0
lxml>=4.9.0
anthropic>=0.18.0
openpyxl>=3.1.0
pandas>=2.0.0
python-dotenv>=1.0.0
pytz>=2024.1
requests>=2.31.0
