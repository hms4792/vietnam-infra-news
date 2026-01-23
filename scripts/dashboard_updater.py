"""
Vietnam Infrastructure News Dashboard Updater
Maintains existing database structure with all sheets
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple
from collections import Counter
import sys
sys.path.append(str(Path(__file__).parent.parent))

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
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

PROJECT_ROOT = Path(__file__).parent.parent
EXISTING_DB_FILENAME = "Vietnam_Infra_News_Database_Final.xlsx"

def find_existing_database():
    possible_paths = [
        PROJECT_ROOT / "data" / EXISTING_DB_FILENAME,
        PROJECT_ROOT / EXISTING_DB_FILENAME,
        Path("/home/runner/work/vietnam-infra-news/vietnam-infra-news/data") / EXISTING_DB_FILENAME,
        Path("/home/runner/work/vietnam-infra-news/vietnam-infra-news") / EXISTING_DB_FILENAME,
        DATA_DIR / EXISTING_DB_FILENAME,
        Path(os.getcwd()) / "data" / EXISTING_DB_FILENAME,
        Path(os.getcwd()) / EXISTING_DB_FILENAME,
    ]
    
    logger.info(f"Searching for existing database: {EXISTING_DB_FILENAME}")
    logger.info(f"PROJECT_ROOT: {PROJECT_ROOT}")
    logger.info(f"Current working directory: {os.getcwd()}")
    
    for path in possible_paths:
        logger.info(f"Checking path: {path} - Exists: {path.exists()}")
        if path.exists():
            logger.info(f"Found existing database at: {path}")
            return path
    
    data_dir = PROJECT_ROOT / "data"
    if data_dir.exists():
        logger.info(f"Contents of data directory: {list(data_dir.iterdir())}")
    
    logger.warning(f"Existing database not found in any location")
    return PROJECT_ROOT / "data" / EXISTING_DB_FILENAME

KEYWORDS_DATA = [
    {"Category": "Solid Waste", "Keywords": "waste-to-energy, solid waste, landfill, incineration, recycling, circular economy, WtE, garbage, municipal waste, waste treatment, waste management", "Search Query Example": "Vietnam waste-to-energy solid waste 2025", "Area": "Environment", "Status": "Original"},
    {"Category": "Waste Water", "Keywords": "wastewater treatment, wastewater plant, WWTP, sewage treatment, water treatment plant, sewerage system, effluent treatment, sludge treatment, drainage system", "Search Query Example": "Vietnam wastewater treatment plant WWTP 2025", "Area": "Environment", "Status": "Updated"},
    {"Category": "Water Supply/Drainage", "Keywords": "clean water, water supply, reservoir, potable water, tap water, drinking water, water infrastructure, water plant, water distribution", "Search Query Example": "Vietnam clean water supply plant project 2025", "Area": "Environment", "Status": "Original"},
    {"Category": "Power", "Keywords": "power plant, electricity generation, LNG power, gas-to-power, thermal power, solar power, solar farm, wind power, wind farm, renewable energy, hydropower, PDP8, biomass power", "Search Query Example": "Vietnam LNG power plant renewable energy 2025", "Area": "Energy Develop.", "Status": "Updated"},
    {"Category": "Oil & Gas", "Keywords": "oil exploration, gas field, upstream, petroleum, offshore drilling, LNG terminal, refinery, natural gas, gas pipeline, crude oil, petrochemical, PetroVietnam", "Search Query Example": "Vietnam oil gas exploration upstream 2025", "Area": "Energy Develop.", "Status": "Updated"},
    {"Category": "Industrial Parks", "Keywords": "industrial park, industrial zone, FDI investment, economic zone, manufacturing zone, factory construction, export processing zone, hi-tech park", "Search Query Example": "Vietnam industrial park FDI investment 2025", "Area": "Urban Develop.", "Status": "Updated"},
    {"Category": "Smart City", "Keywords": "smart city, urban development project, digital transformation, city planning, urban area development, new urban area, smart infrastructure", "Search Query Example": "Vietnam smart city urban development 2025", "Area": "Urban Develop.", "Status": "Original"},
    {"Category": "Climate/Environment", "Keywords": "climate change, carbon neutral, net zero, emission, environmental protection, green growth, pollution control", "Search Query Example": "Vietnam climate change carbon neutral 2025", "Area": "Environment", "Status": "Original"},
    {"Category": "Transport", "Keywords": "railway, high-speed rail, metro, subway, airport, seaport, port, highway, expressway, bridge, tunnel, logistics, transportation, Long Thanh airport", "Search Query Example": "Vietnam high-speed railway metro airport 2025", "Area": "Urban Develop.", "Status": "NEW 2025"},
    {"Category": "Construction", "Keywords": "construction project, real estate development, property, housing project, steel production, cement, building construction, mega project, billion USD", "Search Query Example": "Vietnam construction real estate steel cement 2025", "Area": "Urban Develop.", "Status": "NEW 2025"},
]

SECTOR_KEYWORDS = {
    "Oil & Gas": ["oil exploration", "gas field", "upstream", "petroleum", "offshore drilling", "lng terminal", "refinery", "oil and gas", "natural gas", "gas pipeline", "oil price", "crude oil", "petrochemical"],
    "Solid Waste": ["waste-to-energy", "solid waste", "landfill", "incineration", "recycling", "circular economy", "wte", "garbage", "municipal waste"],
    "Waste Water": ["wastewater", "waste water", "wwtp", "sewage", "water treatment plant", "sewerage", "effluent", "sludge"],
    "Water Supply/Drainage": ["clean water", "water supply", "reservoir", "potable water", "tap water", "drinking water", "water infrastructure"],
    "Power": ["power plant", "electricity", "lng power", "gas-to-power", "thermal power", "solar", "wind", "renewable", "hydropower", "pdp8", "wind farm", "solar farm"],
    "Industrial Parks": ["industrial park", "industrial zone", "fdi", "economic zone", "manufacturing zone", "factory", "manufacturing"],
    "Smart City": ["smart city", "urban development", "digital transformation", "city planning", "urban area"],
    "Transport": ["railway", "high-speed rail", "metro", "subway", "airport", "seaport", "port", "harbor", "terminal", "highway", "expressway", "road", "bridge", "tunnel", "logistics", "transportation", "train"],
    "Construction": ["construction", "real estate", "property", "housing", "steel", "cement", "building", "infrastructure project"],
}

AREA_BY_SECTOR = {
    "Oil & Gas": "Energy Develop.",
    "Solid Waste": "Environment",
    "Waste Water": "Environment",
    "Water Supply/Drainage": "Environment",
    "Power": "Energy Develop.",
    "Industrial Parks": "Urban Develop.",
    "Smart City": "Urban Develop.",
    "Transport": "Urban Develop.",
    "Construction": "Urban Develop.",
}

SECTOR_PRIORITY = ["Oil & Gas", "Transport", "Waste Water", "Solid Waste", "Water Supply/Drainage", "Power", "Construction", "Smart City", "Industrial Parks"]

def classify_article(title: str, summary: str = "") -> Tuple[str, str]:
    text = (str(title) + " " + str(summary)).lower()
    for sector in SECTOR_PRIORITY:
        keywords = SECTOR_KEYWORDS.get(sector, [])
        for keyword in keywords:
            if keyword.lower() in text:
                return sector, AREA_BY_SECTOR.get(sector, "Environment")
    return "Waste Water", "Environment"


class DashboardUpdater:
    def __init__(self):
        self.template_path = TEMPLATE_DIR / "dashboard_template.html"
        self.output_path = OUTPUT_DIR / "vietnam_dashboard.html"
    
    def update(self, all_articles: List[Dict]) -> str:
        js_data = self._generate_js_data(all_articles)
        
        if not self.template_path.exists():
            logger.error(f"Template not found: {self.template_path}")
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
        
        index_path = OUTPUT_DIR / "index.html"
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        logger.info(f"Dashboard updated with {len(all_articles)} articles")
        return str(self.output_path)
    
    def _generate_js_data(self, articles: List[Dict]) -> str:
        js_articles = []
        for i, article in enumerate(articles, 1):
            title = article.get("title", article.get("News Tittle", "No title"))
            summary = article.get("summary", article.get("Short summary", ""))
            
            title_str = str(title) if not isinstance(title, dict) else title.get("vi", str(title))
            summary_str = str(summary) if not isinstance(summary, dict) else summary.get("vi", str(summary))
            
            title_ko = article.get("title_ko", article.get("summary_ko", title_str))[:150]
            title_en = article.get("title_en", article.get("summary_en", title_str))[:150]
            title_vi = article.get("title_vi", title_str)[:150]
            
            summary_ko = article.get("summary_ko", summary_str)[:500]
            summary_en = article.get("summary_en", summary_str)[:500]
            summary_vi = article.get("summary_vi", summary_str)[:500]
            
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
                sector, area = classify_article(title_str, summary_str)
            elif not area:
                area = AREA_BY_SECTOR.get(sector, "Environment")
            
            js_articles.append({
                "id": i,
                "date": date_str,
                "area": area,
                "sector": sector,
                "province": article.get("province", article.get("Province", "Vietnam")),
                "source": article.get("source", article.get("Source", "Unknown")),
                "title": {"ko": title_ko, "en": title_en, "vi": title_vi},
                "summary": {"ko": summary_ko, "en": summary_en, "vi": summary_vi},
                "url": article.get("url", article.get("Link", ""))
            })
        return json.dumps(js_articles, ensure_ascii=False, indent=2)


class ExcelDatabaseUpdater:
    def __init__(self):
        self.existing_db_path = find_existing_database()
        self.output_path = OUTPUT_DIR / "vietnam_infra_news_database.xlsx"
    
    def load_existing_excel(self) -> Dict:
        if not PANDAS_AVAILABLE:
            logger.warning("pandas not available")
            return {"articles": [], "sources": [], "keywords": KEYWORDS_DATA}
        
        if not self.existing_db_path.exists():
            logger.error(f"CRITICAL: Existing database NOT FOUND at: {self.existing_db_path}")
            return {"articles": [], "sources": [], "keywords": KEYWORDS_DATA}
        
        try:
            logger.info(f"Loading existing database from: {self.existing_db_path}")
            xl = pd.ExcelFile(self.existing_db_path)
            logger.info(f"Available sheets: {xl.sheet_names}")
            
            articles = []
            data_sheet = None
            for name in xl.sheet_names:
                if "Data" in name:
                    data_sheet = name
                    break
            
            if data_sheet:
                df = pd.read_excel(self.existing_db_path, sheet_name=data_sheet)
                logger.info(f"Loading articles from sheet '{data_sheet}': {len(df)} rows")
                
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
                logger.info(f"Successfully loaded {len(articles)} existing articles")
            
            sources = []
            if "Source" in xl.sheet_names:
                df_src = pd.read_excel(self.existing_db_path, sheet_name="Source")
                logger.info(f"Loading sources from 'Source' sheet: {len(df_src)} rows")
                for _, row in df_src.iterrows():
                    sources.append({
                        "Domain": str(row.get("Domain", "")) if pd.notna(row.get("Domain")) else "",
                        "URL": str(row.get("URL", "")) if pd.notna(row.get("URL")) else "",
                        "Type": str(row.get("Type", "")) if pd.notna(row.get("Type")) else "",
                        "Status": str(row.get("Status", "")) if pd.notna(row.get("Status")) else "",
                        "Note": str(row.get("Note", "")) if pd.notna(row.get("Note")) else "",
                    })
                logger.info(f"Successfully loaded {len(sources)} existing sources")
            
            # Always use updated KEYWORDS_DATA (not from existing DB)
            keywords = KEYWORDS_DATA
            logger.info(f"Using updated KEYWORDS_DATA with {len(keywords)} categories")
            
            return {"articles": articles, "sources": sources, "keywords": keywords}
        
        except Exception as e:
            logger.error(f"Error loading existing database: {e}")
            import traceback
            traceback.print_exc()
            return {"articles": [], "sources": [], "keywords": KEYWORDS_DATA}
    
    def merge_new_articles(self, existing: List[Dict], new_articles: List[Dict]) -> Tuple[List[Dict], int]:
        """Merge new articles into existing database - PRESERVES ALL EXISTING DATA"""
        
        # 기존 기사 URL/제목 키 생성
        existing_keys = set()
        for article in existing:
            url = str(article.get("Link", "")).lower().strip()
            title = str(article.get("News Tittle", "")).lower().strip()[:80]
            if url and url != "nan" and len(url) > 10:
                existing_keys.add(url)
            if title and title != "nan" and len(title) > 10:
                existing_keys.add(title)
        
        logger.info(f"=== MERGE OPERATION ===")
        logger.info(f"Existing articles BEFORE merge: {len(existing)}")
        logger.info(f"Existing unique keys: {len(existing_keys)}")
        logger.info(f"New articles to process: {len(new_articles)}")
        
        new_count = 0
        for article in new_articles:
            url = str(article.get("url", article.get("Link", ""))).lower().strip()
            title = str(article.get("title", article.get("News Tittle", ""))).lower().strip()[:80]
            
            # 중복 체크
            is_duplicate = False
            if url and url != "nan" and len(url) > 10 and url in existing_keys:
                is_duplicate = True
            if title and title != "nan" and len(title) > 10 and title in existing_keys:
                is_duplicate = True
            
            if not is_duplicate:
                # 새 기사 추가
                original_title = str(article.get("title", article.get("News Tittle", "")))
                summary = str(article.get("summary_en", article.get("summary", article.get("Short summary", ""))))
                
                sector = article.get("sector", "")
                area = article.get("area", "")
                if not sector or sector not in AREA_BY_SECTOR:
                    sector, area = classify_article(original_title, summary)
                elif not area:
                    area = AREA_BY_SECTOR.get(sector, "Environment")
                
                date_val = article.get("published", article.get("Date", ""))
                if isinstance(date_val, str) and 'T' in date_val:
                    date_val = date_val.split('T')[0]
                elif not date_val:
                    date_val = datetime.now().strftime("%Y-%m-%d")
                
                new_article = {
                    "Area": area,
                    "Business Sector": sector,
                    "Province": article.get("province", article.get("Province", "Vietnam")),
                    "News Tittle": original_title[:200],
                    "Date": str(date_val)[:10],
                    "Source": article.get("source", article.get("Source", "Unknown")),
                    "Link": article.get("url", article.get("Link", "")),
                    "Short summary": summary[:500],
                }
                existing.append(new_article)
                
                # 키 추가
                if url and url != "nan" and len(url) > 10:
                    existing_keys.add(url)
                if title and title != "nan" and len(title) > 10:
                    existing_keys.add(title)
                new_count += 1
                logger.info(f"  + Added: {original_title[:50]}...")
        
        logger.info(f"=== MERGE COMPLETE ===")
        logger.info(f"New articles added: {new_count}")
        logger.info(f"Total articles AFTER merge: {len(existing)}")
        
        return existing, new_count
    
def merge_new_sources(self, existing_sources: List[Dict], new_articles: List[Dict], source_check_results: Dict = None) -> List[Dict]:
        """Merge new sources and update check status"""
        existing_domains = set(s.get("Domain", "").lower() for s in existing_sources if s.get("Domain"))
        logger.info(f"Existing sources: {len(existing_sources)}, domains: {len(existing_domains)}")
        
        # Update existing sources with check results
        if source_check_results:
            for source in existing_sources:
                domain = source.get("Domain", "").lower()
                if domain in source_check_results:
                    result = source_check_results[domain]
                    source["Last Checked"] = result.get("last_checked", "")
                    source["Check Result"] = "OK" if result.get("success") else "FAIL"
                    source["Articles Found"] = result.get("articles_found", 0)
                    if result.get("error"):
                        source["Note"] = f"Error: {result['error'][:30]}"
        
        # Add new sources from articles
        new_source_count = 0
        for article in new_articles:
            source = article.get("source", article.get("Source", ""))
            url = article.get("url", article.get("Link", ""))
            
            if url:
                try:
                    from urllib.parse import urlparse
                    domain = urlparse(url).netloc.replace("www.", "")
                except:
                    domain = source
            else:
                domain = source
            
            if domain and domain.lower() not in existing_domains and len(domain) > 3:
                new_source = {
                    "Domain": domain,
                    "URL": url[:100] if url else "",
                    "Type": "News",
                    "Status": "Accessible",
                    "Note": f"NEW {datetime.now().year}",
                    "Last Checked": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "Check Result": "OK",
                    "Articles Found": 1,
                }
                existing_sources.append(new_source)
                existing_domains.add(domain.lower())
                new_source_count += 1
        
        logger.info(f"Added {new_source_count} new sources. Total: {len(existing_sources)}")
        return existing_sources
    
    def generate_summary(self, articles: List[Dict]) -> List[List]:
        summary = []
        current_year = datetime.now().year
        
        year_counts = Counter()
        area_counts = Counter()
        sector_counts = Counter()
        
        for article in articles:
            date_str = str(article.get("Date", ""))[:4]
            try:
                year = int(date_str)
                year_counts[year] += 1
            except:
                pass
            
            area = article.get("Area", "")
            sector = article.get("Business Sector", "")
            if area:
                area_counts[area] += 1
            if sector:
                sector_counts[sector] += 1
        
        summary.append(["Vietnam Infrastructure News Database Summary", ""])
        summary.append([f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""])
        summary.append(["", ""])
        summary.append(["=== Total Statistics ===", ""])
        summary.append(["Total Articles", len(articles)])
        summary.append(["", ""])
        
        summary.append(["=== By Year ===", ""])
        for year in sorted(year_counts.keys()):
            marker = " (Current Year)" if year == current_year else ""
            summary.append([f"{year}{marker}", year_counts[year]])
        summary.append(["", ""])
        
        summary.append(["=== By Area ===", ""])
        for area, count in area_counts.most_common():
            summary.append([area, count])
        summary.append(["", ""])
        
        summary.append(["=== By Business Sector ===", ""])
        for sector, count in sector_counts.most_common():
            summary.append([sector, count])
        
        current_year_articles = [a for a in articles if str(a.get("Date", ""))[:4] == str(current_year)]
        if current_year_articles:
            summary.append(["", ""])
            summary.append([f"=== {current_year} Year Details ===", ""])
            summary.append([f"Total {current_year} Articles", len(current_year_articles)])
            
            cy_area = Counter(a.get("Area", "") for a in current_year_articles)
            cy_sector = Counter(a.get("Business Sector", "") for a in current_year_articles)
            
            summary.append(["", ""])
            summary.append([f"{current_year} By Area:", ""])
            for area, count in cy_area.most_common():
                if area:
                    summary.append([f"  {area}", count])
            
            summary.append(["", ""])
            summary.append([f"{current_year} By Sector:", ""])
            for sector, count in cy_sector.most_common():
                if sector:
                    summary.append([f"  {sector}", count])
        
        return summary

    def generate_keyword_history(self, articles: List[Dict]) -> Dict:
        """Generate keyword-based search history statistics"""
        from collections import Counter
        
        keyword_categories = {
            "Solid Waste": ["waste-to-energy", "solid waste", "landfill", "incineration", "recycling", "circular economy", "garbage", "municipal waste"],
            "Waste Water": ["wastewater treatment", "wastewater plant", "wwtp", "sewage treatment", "sewerage", "effluent", "sludge"],
            "Water Supply/Drainage": ["clean water", "water supply", "reservoir", "potable water", "tap water", "drinking water", "water infrastructure"],
            "Power": ["power plant", "solar power", "wind power", "thermal power", "lng power", "hydropower", "renewable energy", "electricity"],
            "Oil & Gas": ["oil exploration", "gas field", "petroleum", "lng terminal", "refinery", "natural gas", "crude oil", "petrochemical"],
            "Industrial Parks": ["industrial park", "industrial zone", "fdi investment", "economic zone", "manufacturing zone", "factory"],
            "Smart City": ["smart city", "urban development", "digital transformation", "city planning", "urban area"],
            "Transport": ["railway", "high-speed rail", "metro", "airport", "seaport", "highway", "expressway", "bridge", "tunnel"],
            "Construction": ["construction project", "real estate", "property", "housing", "steel", "cement", "building"],
        }
        
        keyword_stats = {}
        
        for category, keywords in keyword_categories.items():
            category_stats = []
            
            for keyword in keywords:
                kw_lower = keyword.lower()
                matched_articles = []
                
                for article in articles:
                    title = str(article.get("News Tittle", article.get("title", ""))).lower()
                    summary = str(article.get("Short summary", article.get("summary", ""))).lower()
                    
                    if kw_lower in title or kw_lower in summary:
                        matched_articles.append(article)
                
                if matched_articles:
                    # Count by year
                    count_2024 = sum(1 for a in matched_articles if str(a.get("Date", "")).startswith("2024"))
                    count_2025 = sum(1 for a in matched_articles if str(a.get("Date", "")).startswith("2025"))
                    
                    # Get last article date
                    dates = [str(a.get("Date", ""))[:10] for a in matched_articles if a.get("Date")]
                    last_date = max(dates) if dates else ""
                    
                    # Get top province
                    provinces = [a.get("Province", "Vietnam") for a in matched_articles]
                    province_counts = Counter(provinces)
                    top_province = province_counts.most_common(1)[0][0] if province_counts else "Vietnam"
                    
                    # Get sample title
                    sample_title = matched_articles[0].get("News Tittle", matched_articles[0].get("title", ""))
                    
                    category_stats.append({
                        "keyword": keyword,
                        "total": len(matched_articles),
                        "count_2024": count_2024,
                        "count_2025": count_2025,
                        "last_date": last_date,
                        "top_province": top_province,
                        "sample_title": sample_title
                    })
                else:
                    category_stats.append({
                        "keyword": keyword,
                        "total": 0,
                        "count_2024": 0,
                        "count_2025": 0,
                        "last_date": "",
                        "top_province": "",
                        "sample_title": "No articles found"
                    })
            
            # Sort by total count descending
            category_stats.sort(key=lambda x: x["total"], reverse=True)
            keyword_stats[category] = category_stats
        
        return keyword_stats


    def create_excel(self, articles: List[Dict], sources: List[Dict], keywords: List[Dict], new_count: int) -> str:
        if not OPENPYXL_AVAILABLE:
            logger.warning("openpyxl not available")
            return ""
        
        wb = openpyxl.Workbook()
        
        header_font = Font(bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="0D9488", fill_type="solid")
        yellow_fill = PatternFill(start_color="FFFF00", fill_type="solid")
        green_fill = PatternFill(start_color="90EE90", fill_type="solid")
        thin_border = Border(
            left=Side(style='thin'), right=Side(style='thin'),
            top=Side(style='thin'), bottom=Side(style='thin')
        )
        
        ws1 = wb.active
        ws1.title = "Data set (Database)"
        
        columns = ["Area", "Business Sector", "Province", "News Tittle", "Date", "Source", "Link", "Short summary"]
        col_widths = [15, 22, 18, 70, 12, 22, 60, 100]
        
        for col, header in enumerate(columns, 1):
            cell = ws1.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")
            cell.border = thin_border
        
        articles.sort(key=lambda x: str(x.get("Date", ""))[:10], reverse=True)
        
        current_year = datetime.now().year
        for row_idx, article in enumerate(articles, 2):
            is_current_year = False
            date_val = str(article.get("Date", ""))[:4]
            try:
                if int(date_val) == current_year:
                    is_current_year = True
            except:
                pass
            
            for col_idx, col_name in enumerate(columns, 1):
                value = str(article.get(col_name, ""))
                if col_idx == 8:
                    value = value[:500]
                else:
                    value = value[:200]
                
                cell = ws1.cell(row=row_idx, column=col_idx, value=value)
                cell.border = thin_border
                if is_current_year:
                    cell.fill = yellow_fill
        
        for i, width in enumerate(col_widths, 1):
            ws1.column_dimensions[get_column_letter(i)].width = width
        # Source Sheet - with check status columns
        ws2 = wb.create_sheet("Source")
        source_cols = ["Domain", "URL", "Type", "Status", "Last Checked", "Check Result", "Articles Found", "Note"]
        source_widths = [30, 50, 15, 12, 18, 12, 14, 25]
        
        # Header row
        for col, header in enumerate(source_cols, 1):
            cell = ws2.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="center")
        
        # Conditional fills
        ok_fill = PatternFill(start_color="90EE90", fill_type="solid")  # Green for OK
        fail_fill = PatternFill(start_color="FFB6C1", fill_type="solid")  # Light red for FAIL
        new_fill = PatternFill(start_color="87CEEB", fill_type="solid")  # Light blue for NEW
        
        for row_idx, source in enumerate(sources, 2):
            is_new = "NEW" in str(source.get("Note", ""))
            check_result = str(source.get("Check Result", ""))
            
            for col_idx, col_name in enumerate(source_cols, 1):
                value = source.get(col_name, "")
                if col_name == "Articles Found" and value:
                    try:
                        value = int(value)
                    except:
                        value = 0
                cell = ws2.cell(row=row_idx, column=col_idx, value=value if value else "")
                cell.border = thin_border
                
                # Apply conditional formatting
                if is_new:
                    cell.fill = new_fill
                elif col_name == "Check Result":
                    if check_result == "OK":
                        cell.fill = ok_fill
                    elif check_result == "FAIL":
                        cell.fill = fail_fill
        
        for i, width in enumerate(source_widths, 1):
            ws2.column_dimensions[get_column_letter(i)].width = width
        
# Keywords Sheet - with new columns Area and Status
        ws3 = wb.create_sheet("Keywords")
        kw_cols = ["Category", "Keywords", "Search Query Example", "Area", "Status"]
        kw_widths = [22, 100, 55, 18, 15]
        
        # Header row
        for col, header in enumerate(kw_cols, 1):
            cell = ws3.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="center")
        
        # Green fill for NEW items
        new_fill = PatternFill(start_color="90EE90", fill_type="solid")
        
        # Data rows - use KEYWORDS_DATA directly (not from existing DB)
        for row_idx, kw in enumerate(KEYWORDS_DATA, 2):
            is_new = "NEW" in str(kw.get("Status", ""))
            for col_idx, col_name in enumerate(kw_cols, 1):
                value = str(kw.get(col_name, ""))
                cell = ws3.cell(row=row_idx, column=col_idx, value=value)
                cell.border = thin_border
                if is_new:
                    cell.fill = new_fill
                if col_idx == 2:  # Keywords column - wrap text
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
        
        # Set column widths
        for i, width in enumerate(kw_widths, 1):
            ws3.column_dimensions[get_column_letter(i)].width = width
        
        ws4 = wb.create_sheet("Summary")
        summary_data = self.generate_summary(articles)
        
        for row_idx, row in enumerate(summary_data, 1):
            for col_idx, value in enumerate(row, 1):
                cell = ws4.cell(row=row_idx, column=col_idx, value=value)
                if "===" in str(value) or row_idx == 1:
                    cell.font = Font(bold=True, color="0D9488")
                if "Current Year" in str(value):
                    cell.fill = yellow_fill
        
        ws4.column_dimensions['A'].width = 40
        ws4.column_dimensions['B'].width = 20
        
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(self.output_path)
        
        logger.info(f"Excel saved: {self.output_path}")
        logger.info(f"  - Data set: {len(articles)} articles")
        logger.info(f"  - Sources: {len(sources)}")
        logger.info(f"  - Keywords: {len(keywords)} categories")
        logger.info(f"  - New articles added: {new_count}")
        
        return str(self.output_path)
        # Keyword Search History Sheet
        ws5 = wb.create_sheet("Keyword History")
        
        # Generate keyword-based statistics
        keyword_stats = self.generate_keyword_history(articles)
        
        kh_cols = ["Category", "Keyword", "Total Articles", "2024 Count", "2025 Count", "Last Article Date", "Top Province", "Sample Title"]
        kh_widths = [18, 25, 14, 12, 12, 15, 18, 60]
        
        # Header row
        for col, header in enumerate(kh_cols, 1):
            cell = ws5.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.border = thin_border
            cell.alignment = Alignment(horizontal="center")
        
        # Data rows
        row_idx = 2
        for category, keywords_data in keyword_stats.items():
            for kw_data in keywords_data:
                values = [
                    category,
                    kw_data.get("keyword", ""),
                    kw_data.get("total", 0),
                    kw_data.get("count_2024", 0),
                    kw_data.get("count_2025", 0),
                    kw_data.get("last_date", ""),
                    kw_data.get("top_province", ""),
                    kw_data.get("sample_title", "")[:80]
                ]
                
                for col_idx, value in enumerate(values, 1):
                    cell = ws5.cell(row=row_idx, column=col_idx, value=value)
                    cell.border = thin_border
                    
                    # Highlight keywords with articles
                    if col_idx == 3 and value > 0:
                        cell.fill = PatternFill(start_color="90EE90", fill_type="solid")
                    elif col_idx == 3 and value == 0:
                        cell.fill = PatternFill(start_color="FFB6C1", fill_type="solid")
                
                row_idx += 1
        
        for i, width in enumerate(kh_widths, 1):
            ws5.column_dimensions[get_column_letter(i)].width = width
            
def update(self, new_articles: List[Dict], source_check_results: Dict = None) -> Tuple[str, List[Dict]]:
        """Update database with new articles and source check results"""
        existing_data = self.load_existing_excel()
        
        articles = existing_data["articles"]
        sources = existing_data["sources"]
        keywords = existing_data["keywords"]
        
        logger.info(f"Loaded from existing DB - Articles: {len(articles)}, Sources: {len(sources)}")
        
        if len(articles) == 0:
            logger.error("WARNING: No existing articles loaded! Check database file path.")
        
        articles, new_count = self.merge_new_articles(articles, new_articles)
        sources = self.merge_new_sources(sources, new_articles, source_check_results)
        
        excel_path = self.create_excel(articles, sources, keywords, new_count)
        
        # ... rest of the method stays the same
        
        dashboard_articles = []
        for article in articles:
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
        
        for new_art in new_articles:
            for dash_art in dashboard_articles:
                if dash_art.get("url") == new_art.get("url"):
                    dash_art["title_ko"] = new_art.get("title_ko", "")
                    dash_art["title_en"] = new_art.get("title_en", "")
                    dash_art["title_vi"] = new_art.get("title_vi", "")
                    dash_art["summary_ko"] = new_art.get("summary_ko", "")
                    dash_art["summary_en"] = new_art.get("summary_en", "")
                    dash_art["summary_vi"] = new_art.get("summary_vi", "")
                    break
        
        return excel_path, dashboard_articles


class OutputGenerator:
    def __init__(self):
        self.dashboard = DashboardUpdater()
        self.excel_db = ExcelDatabaseUpdater()
    
    def generate_all(self, new_articles: List[Dict]) -> Dict[str, str]:
        outputs = {}
        
        try:
            excel_path, all_articles = self.excel_db.update(new_articles)
            outputs["excel"] = excel_path
            outputs["dashboard"] = self.dashboard.update(all_articles)
            outputs["total_articles"] = len(all_articles)
            outputs["new_articles"] = len(new_articles)
        except Exception as e:
            logger.error(f"Error generating outputs: {e}")
            import traceback
            traceback.print_exc()
            outputs["excel"] = ""
            outputs["dashboard"] = ""
        
        try:
            json_path = OUTPUT_DIR / f"news_data_{datetime.now().strftime('%Y%m%d')}.json"
            json_path.parent.mkdir(parents=True, exist_ok=True)
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump({
                    "generated_at": datetime.now().isoformat(),
                    "total": outputs.get("total_articles", 0),
                    "new_articles": outputs.get("new_articles", 0),
                }, f, ensure_ascii=False, indent=2)
            outputs["json"] = str(json_path)
            logger.info(f"Generated json: {json_path}")
        except Exception as e:
            logger.error(f"JSON error: {e}")
        
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
    print(f"Generated outputs: {outputs}")


if __name__ == "__main__":
    main()
