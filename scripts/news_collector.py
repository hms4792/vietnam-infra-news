#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News Collector
Enhanced sector classification and full month collection
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import logging
import sys
import os
import time
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import (
    RSS_FEEDS,
    DATA_DIR,
    OUTPUT_DIR
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Excel database path
EXCEL_DB_PATH = DATA_DIR / "database" / "Vietnam_Infra_News_Database_Final.xlsx"

# Source status log path
SOURCE_STATUS_PATH = OUTPUT_DIR / "news_sources_status.json"

# ============================================================
# ENHANCED SECTOR CLASSIFICATION
# ============================================================

SECTOR_KEYWORDS = {
    "Waste Water": {
        "keywords": [
            "wastewater", "waste water", "sewage", "sewerage", 
            "effluent", "wwtp", "drainage", "sewer",
            "wastewater treatment", "sewage treatment",
            "water pollution", "effluent treatment",
            "nước thải", "xử lý nước thải", "thoát nước",
            "nhà máy xử lý nước thải", "hệ thống thoát nước"
        ],
        "area": "Environment",
        "priority": 1
    },
    "Solid Waste": {
        "keywords": [
            "solid waste", "garbage", "trash", "landfill",
            "waste-to-energy", "incineration", "recycling",
            "waste management", "municipal waste", "hazardous waste",
            "waste collection", "waste disposal", "composting",
            "rác thải", "chất thải rắn", "bãi rác", "xử lý rác",
            "đốt rác", "tái chế", "chất thải sinh hoạt"
        ],
        "area": "Environment",
        "priority": 2
    },
    "Water Supply/Drainage": {
        "keywords": [
            "water supply", "clean water", "drinking water",
            "water treatment", "potable water", "tap water",
            "water plant", "water infrastructure", "water network",
            "cấp nước", "nước sạch", "nước sinh hoạt",
            "nhà máy nước", "hệ thống cấp nước"
        ],
        "area": "Environment",
        "priority": 3
    },
    "Power": {
        "keywords": [
            "power plant", "electricity", "solar", "wind power",
            "hydropower", "thermal power", "renewable energy",
            "power generation", "energy project", "grid",
            "solar farm", "wind farm", "photovoltaic",
            "power station", "megawatt", "MW",
            "coal power", "gas turbine", "power capacity",
            "nhà máy điện", "điện mặt trời", "điện gió",
            "thủy điện", "nhiệt điện", "năng lượng tái tạo"
        ],
        "area": "Energy Develop.",
        "priority": 4
    },
    "Oil & Gas": {
        "keywords": [
            "oil", "gas", "petroleum", "lng", "refinery",
            "offshore", "drilling", "pipeline", "petrochemical",
            "natural gas", "crude oil", "oil field", "gas field",
            "dầu khí", "khí đốt", "lọc dầu", "đường ống"
        ],
        "area": "Energy Develop.",
        "priority": 5
    },
    "Industrial Parks": {
        "keywords": [
            "industrial park", "industrial zone", "economic zone",
            "export processing", "manufacturing zone", "factory",
            "industrial estate", "industrial complex",
            "fdi", "foreign investment",
            "khu công nghiệp", "khu chế xuất", "khu kinh tế"
        ],
        "area": "Urban Develop.",
        "priority": 6
    },
    "Smart City": {
        "keywords": [
            "smart city", "smart urban", "digital city",
            "urban development", "city planning", "urban infrastructure",
            "thành phố thông minh", "đô thị thông minh",
            "phát triển đô thị"
        ],
        "area": "Urban Develop.",
        "priority": 7
    },
    "Transport": {
        "keywords": [
            "railway", "metro", "subway", "airport", "seaport",
            "highway", "expressway", "road construction",
            "bridge", "tunnel", "logistics", "port",
            "đường sắt", "metro", "sân bay", "cảng biển",
            "cao tốc", "đường cao tốc"
        ],
        "area": "Urban Develop.",
        "priority": 8
    }
}

PROVINCE_KEYWORDS = {
    "Ho Chi Minh City": ["ho chi minh", "hcmc", "saigon", "tp.hcm", "hồ chí minh"],
    "Hanoi": ["hanoi", "ha noi", "hà nội"],
    "Da Nang": ["da nang", "đà nẵng"],
    "Hai Phong": ["hai phong", "hải phòng"],
    "Can Tho": ["can tho", "cần thơ"],
    "Binh Duong": ["binh duong", "bình dương"],
    "Dong Nai": ["dong nai", "đồng nai"],
    "Ba Ria-Vung Tau": ["ba ria", "vung tau", "vũng tàu"],
    "Long An": ["long an"],
    "Quang Ninh": ["quang ninh", "quảng ninh", "ha long"],
    "Bac Ninh": ["bac ninh", "bắc ninh"],
    "Hai Duong": ["hai duong", "hải dương"],
    "Thai Nguyen": ["thai nguyen", "thái nguyên"],
    "Thanh Hoa": ["thanh hoa", "thanh hoá"],
    "Nghe An": ["nghe an", "nghệ an"],
    "Hue": ["hue", "huế", "thua thien"],
    "Quang Nam": ["quang nam", "quảng nam"],
    "Khanh Hoa": ["khanh hoa", "nha trang"],
    "Lam Dong": ["lam dong", "da lat"],
    "Dak Lak": ["dak lak", "đắk lắk"],
    "Binh Thuan": ["binh thuan", "phan thiet"],
    "An Giang": ["an giang"],
    "Kien Giang": ["kien giang", "phu quoc"],
    "Ca Mau": ["ca mau", "cà mau"],
    "Quang Ngai": ["quang ngai", "quảng ngãi"],
    "Quang Binh": ["quang binh", "quảng bình"],
    "Ha Tinh": ["ha tinh", "hà tĩnh"],
    "Quang Tri": ["quang tri", "quảng trị"],
}


class NewsCollector:
    """News collector with enhanced sector classification"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8',
        }
        self.collected_articles = []
        self.existing_urls = set()
        self.source_status = {}
        self._load_existing_urls()
    
    def _load_existing_urls(self):
        """Load existing URLs from Excel"""
        try:
            import openpyxl
            if EXCEL_DB_PATH.exists():
                wb = openpyxl.load_workbook(EXCEL_DB_PATH, read_only=True)
                ws = wb.active
                headers = [cell.value for cell in ws[1]]
                
                url_col = None
                for i, h in enumerate(headers):
                    if h and ('Link' in str(h) or 'URL' in str(h).upper()):
                        url_col = i
                        break
                
                if url_col is not None:
                    for row in ws.iter_rows(min_row=2, values_only=True):
                        if row[url_col]:
                            self.existing_urls.add(str(row[url_col]).strip())
                
                wb.close()
                logger.info(f"Loaded {len(self.existing_urls)} existing URLs")
        except Exception as e:
            logger.error(f"Error loading URLs: {e}")
    
    def classify_sector(self, title: str, content: str) -> tuple:
        """Enhanced sector classification"""
        
        text = f"{title} {content[:1500] if content else ''}".lower()
        
        matched_sectors = []
        
        for sector_name, sector_info in SECTOR_KEYWORDS.items():
            keywords = sector_info["keywords"]
            match_count = sum(1 for kw in keywords if kw.lower() in text)
            
            if match_count > 0:
                matched_sectors.append({
                    "sector": sector_name,
                    "area": sector_info["area"],
                    "priority": sector_info["priority"],
                    "matches": match_count
                })
        
        if matched_sectors:
            matched_sectors.sort(key=lambda x: (-x["matches"], x["priority"]))
            best = matched_sectors[0]
            return best["sector"], best["area"]
        
        # No specific sector match - skip article
        return None, None
    
    def extract_province(self, title: str, content: str) -> str:
        """Extract province from text"""
        text = f"{title} {content[:1000] if content else ''}".lower()
        
        for province, keywords in PROVINCE_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    return province
        return "Vietnam"
    
    def extract_content(self, soup, url):
        """Extract article content"""
        
        if 'vnexpress' in url.lower():
            for selector in ['div.article-content', 'div.fck_detail', 'article']:
                content = soup.select_one(selector)
                if content:
                    paragraphs = content.find_all('p')
                    text = ' '.join([p.get_text(strip=True) for p in paragraphs])
                    if len(text) > 100:
                        return text
        
        for selector in ['article', '.article-content', '.post-content', '.content']:
            content = soup.select_one(selector)
            if content:
                text = content.get_text(strip=True, separator=' ')
                if len(text) > 100:
                    return text
        
        meta = soup.find('meta', property='og:description')
        if meta and meta.get('content'):
            return meta['content']
        
        return ""
    
    def extract_title(self, soup, url):
        """Extract article title"""
        
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            title = og_title['content'].strip()
            if len(title) > 10:
                return title
        
        h1 = soup.select_one('h1')
        if h1:
            title = h1.get_text().strip()
            if len(title) > 10:
                return title
        
        if soup.title:
            title = re.sub(r'\s*[-|].*$', '', soup.title.get_text().strip())
            if len(title) > 10:
                return title
        
        return None
    
    def extract_date(self, soup, url):
        """Extract article date"""
        
        for tag, attrs in [
            ('meta', {'property': 'article:published_time'}),
            ('meta', {'name': 'pubdate'}),
        ]:
            meta = soup.find(tag, attrs)
            if meta and meta.get('content'):
                try:
                    return datetime.strptime(meta['content'][:10], '%Y-%m-%d')
                except:
                    pass
        
        time_tag = soup.find('time', datetime=True)
        if time_tag:
            try:
                return datetime.strptime(time_tag['datetime'][:10], '%Y-%m-%d')
            except:
                pass
        
        return datetime.now()
    
    def collect_article(self, url: str, source_name: str = "Unknown") -> dict:
        """Collect single article"""
        
        if url in self.existing_urls:
            return None
        
        logger.info(f"Collecting: {url[:70]}...")
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            time.sleep(1)
        except Exception as e:
            logger.error(f"Fetch error: {e}")
            return None
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        title = self.extract_title(soup, url)
        if not title:
            return None
        
        content = self.extract_content(soup, url)
        
        # CRITICAL: Sector classification
        sector, area = self.classify_sector(title, content)
        
        if not sector:
            logger.info(f"  Skipped (no sector): {title[:40]}...")
            return None
        
        article_date = self.extract_date(soup, url)
        province = self.extract_province(title, content)
        
        article = {
            "title": title,
            "sector": sector,
            "area": area,
            "province": province,
            "source": source_name,
            "url": url,
            "date": article_date.strftime("%Y-%m-%d"),
            "summary_vi": content[:500] if content else title,
            "content": content[:2000] if content else ""
        }
        
        self.collected_articles.append(article)
        self.existing_urls.add(url)
        
        logger.info(f"  ✓ [{sector}] {title[:40]}...")
        return article
    
    def collect_from_rss(self, hours_back: int = 720):
        """Collect from RSS feeds (default 30 days)"""
        
        logger.info("="*60)
        logger.info(f"Collecting news (last {hours_back//24} days)")
        logger.info(f"Sources: {len(RSS_FEEDS)}")
        logger.info("="*60)
        
        for source_name, feed_url in RSS_FEEDS.items():
            logger.info(f"\n--- {source_name} ---")
            
            source_result = {
                "name": source_name,
                "url": feed_url,
                "status": "unknown",
                "articles_found": 0,
                "articles_collected": 0,
                "error": None,
                "timestamp": datetime.now().isoformat()
            }
            
            try:
                response = requests.get(feed_url, headers=self.headers, timeout=30)
                
                if response.status_code != 200:
                    source_result["status"] = "http_error"
                    source_result["error"] = f"HTTP {response.status_code}"
                    self.source_status[source_name] = source_result
                    continue
                
                soup = BeautifulSoup(response.content, 'xml')
                items = soup.find_all('item') or soup.find_all('entry')
                
                source_result["articles_found"] = len(items)
                logger.info(f"  Found: {len(items)} items")
                
                if not items:
                    source_result["status"] = "empty"
                    self.source_status[source_name] = source_result
                    continue
                
                source_result["status"] = "success"
                collected = 0
                
                for item in items[:50]:
                    link = item.find('link')
                    if link:
                        url = link.get('href') or link.get_text().strip()
                        if url and self.collect_article(url, source_name):
                            collected += 1
                        time.sleep(1.5)
                
                source_result["articles_collected"] = collected
                logger.info(f"  Collected: {collected}")
                
            except Exception as e:
                source_result["status"] = "error"
                source_result["error"] = str(e)[:100]
                logger.error(f"  Error: {e}")
            
            self.source_status[source_name] = source_result
            time.sleep(2)
        
        self._save_source_status()
        
        # Summary
        sector_counts = {}
        for a in self.collected_articles:
            s = a.get("sector", "Unknown")
            sector_counts[s] = sector_counts.get(s, 0) + 1
        
        logger.info(f"\n{'='*60}")
        logger.info(f"TOTAL COLLECTED: {len(self.collected_articles)}")
        for sector, count in sorted(sector_counts.items(), key=lambda x: -x[1]):
            logger.info(f"  {sector}: {count}")
        
        return self.collected_articles
    
    def _save_source_status(self):
        """Save source status"""
        try:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            
            sector_counts = {}
            for a in self.collected_articles:
                s = a.get("sector", "Unknown")
                sector_counts[s] = sector_counts.get(s, 0) + 1
            
            report = {
                "generated_at": datetime.now().isoformat(),
                "total_collected": len(self.collected_articles),
                "sector_distribution": sector_counts,
                "sources": self.source_status
            }
            
            with open(SOURCE_STATUS_PATH, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            
        except Exception as e:
            logger.error(f"Save error: {e}")
    
    async def collect_all(self):
        """Async interface"""
        return self.collect_from_rss(hours_back=720)
    
    def save_to_excel(self):
        """Save to Excel database"""
        
        if not self.collected_articles:
            logger.info("No articles to save")
            return
        
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill
        except ImportError:
            logger.error("openpyxl not installed")
            return
        
        try:
            if EXCEL_DB_PATH.exists():
                wb = openpyxl.load_workbook(EXCEL_DB_PATH)
                ws = wb.active
                start_row = ws.max_row + 1
            else:
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = "News Database"
                headers = ["Area", "Business Sector", "Province", "News Tittle",
                          "Date", "Source", "Link", "Short summary"]
                for col, h in enumerate(headers, 1):
                    ws.cell(row=1, column=col, value=h).font = Font(bold=True)
                start_row = 2
            
            highlight = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
            
            for i, article in enumerate(self.collected_articles):
                row = start_row + i
                ws.cell(row=row, column=1, value=article.get("area", "Environment"))
                ws.cell(row=row, column=2, value=article.get("sector", ""))
                ws.cell(row=row, column=3, value=article.get("province", "Vietnam"))
                ws.cell(row=row, column=4, value=article.get("title", ""))
                ws.cell(row=row, column=5, value=article.get("date", ""))
                ws.cell(row=row, column=6, value=article.get("source", ""))
                ws.cell(row=row, column=7, value=article.get("url", ""))
                ws.cell(row=row, column=8, value=article.get("summary_vi", "")[:500])
                
                for col in range(1, 9):
                    ws.cell(row=row, column=col).fill = highlight
            
            EXCEL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            wb.save(EXCEL_DB_PATH)
            logger.info(f"✓ Saved {len(self.collected_articles)} articles to Excel")
            
        except Exception as e:
            logger.error(f"Excel save error: {e}")
            import traceback
            traceback.print_exc()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--days-back', type=int, default=30)
    parser.add_argument('--hours-back', type=int, default=None,
                       help='Hours to look back (overrides days-back)')
    args = parser.parse_args()
    
    # hours-back takes priority if specified
    if args.hours_back:
        hours = args.hours_back
    else:
        hours = args.days_back * 24
    
    collector = NewsCollector()
    articles = collector.collect_from_rss(hours_back=hours)
    
    if articles:
        collector.save_to_excel()
    
    print(f"\nTotal: {len(articles)} articles")


if __name__ == "__main__":
    main()
