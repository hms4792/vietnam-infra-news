#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News Collector
Strict sector classification - ONLY infrastructure news
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
    OUTPUT_DIR,
    SECTOR_KEYWORDS,
    EXCLUSION_KEYWORDS
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EXCEL_DB_PATH = DATA_DIR / "database" / "Vietnam_Infra_News_Database_Final.xlsx"
SOURCE_STATUS_PATH = OUTPUT_DIR / "news_sources_status.json"

# Province detection
PROVINCE_KEYWORDS = {
    "Ho Chi Minh City": ["ho chi minh", "hcmc", "saigon", "tp.hcm", "hồ chí minh", "sài gòn"],
    "Hanoi": ["hanoi", "ha noi", "hà nội"],
    "Da Nang": ["da nang", "đà nẵng"],
    "Hai Phong": ["hai phong", "hải phòng"],
    "Can Tho": ["can tho", "cần thơ"],
    "Binh Duong": ["binh duong", "bình dương"],
    "Dong Nai": ["dong nai", "đồng nai"],
    "Ba Ria-Vung Tau": ["ba ria", "vung tau", "vũng tàu", "bà rịa"],
    "Long An": ["long an"],
    "Quang Ninh": ["quang ninh", "quảng ninh", "ha long", "hạ long"],
    "Bac Ninh": ["bac ninh", "bắc ninh"],
    "Hai Duong": ["hai duong", "hải dương"],
    "Thai Nguyen": ["thai nguyen", "thái nguyên"],
    "Thanh Hoa": ["thanh hoa", "thanh hoá"],
    "Nghe An": ["nghe an", "nghệ an"],
    "Hue": ["hue", "huế", "thua thien"],
    "Quang Nam": ["quang nam", "quảng nam"],
    "Binh Dinh": ["binh dinh", "bình định"],
    "Khanh Hoa": ["khanh hoa", "nha trang", "khánh hoà"],
    "Lam Dong": ["lam dong", "da lat", "đà lạt"],
    "Dak Lak": ["dak lak", "đắk lắk"],
    "Binh Thuan": ["binh thuan", "bình thuận", "phan thiet"],
    "An Giang": ["an giang"],
    "Kien Giang": ["kien giang", "phu quoc", "phú quốc"],
    "Ca Mau": ["ca mau", "cà mau"],
    "Quang Ngai": ["quang ngai", "quảng ngãi"],
    "Quang Binh": ["quang binh", "quảng bình"],
    "Ha Tinh": ["ha tinh", "hà tĩnh"],
    "Mekong Delta": ["mekong", "cuu long", "cửu long", "đồng bằng sông cửu long"],
}


class NewsCollector:
    """News collector with strict infrastructure filtering"""
    
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
        """Load existing URLs from Excel to prevent duplicates"""
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
    
    def _should_exclude(self, text: str) -> bool:
        """Check if article should be excluded based on keywords"""
        text_lower = text.lower()
        
        for keyword in EXCLUSION_KEYWORDS:
            if keyword.lower() in text_lower:
                logger.debug(f"Excluded due to keyword: {keyword}")
                return True
        return False
    
    def classify_sector(self, title: str, content: str) -> tuple:
        """
        STRICT sector classification
        Returns (sector, area) only if article is infrastructure-related
        Returns (None, None) if not infrastructure
        """
        text = f"{title} {content[:2000] if content else ''}".lower()
        
        # First check exclusions
        if self._should_exclude(text):
            return None, None
        
        best_match = None
        best_score = 0
        
        for sector_name, sector_info in SECTOR_KEYWORDS.items():
            required_keywords = sector_info.get("required", [])
            boost_keywords = sector_info.get("boost", [])
            exclude_keywords = sector_info.get("exclude", [])
            
            # Check excludes first
            excluded = False
            for kw in exclude_keywords:
                if kw.lower() in text:
                    excluded = True
                    break
            
            if excluded:
                continue
            
            # Count required matches (MUST have at least one)
            required_matches = sum(1 for kw in required_keywords if kw.lower() in text)
            
            if required_matches == 0:
                continue  # No required keyword = not this sector
            
            # Count boost matches
            boost_matches = sum(1 for kw in boost_keywords if kw.lower() in text)
            
            # Calculate score
            score = required_matches * 10 + boost_matches * 2
            
            if score > best_score:
                best_score = score
                best_match = (sector_name, sector_info.get("area", "Environment"))
        
        return best_match if best_match else (None, None)
    
    def extract_province(self, title: str, content: str) -> str:
        """Extract province/location from text"""
        text = f"{title} {content[:1000] if content else ''}".lower()
        
        for province, keywords in PROVINCE_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    return province
        return "Vietnam"
    
    def extract_content(self, soup, url):
        """Extract article content"""
        # VnExpress specific
        if 'vnexpress' in url.lower():
            for selector in ['article.fck_detail', 'div.fck_detail', 'article']:
                content = soup.select_one(selector)
                if content:
                    paragraphs = content.find_all('p')
                    text = ' '.join([p.get_text(strip=True) for p in paragraphs])
                    if len(text) > 100:
                        return text
        
        # Generic extraction
        for selector in ['article', '.article-content', '.post-content', 
                        '.entry-content', '.detail-content', '.news-content']:
            content = soup.select_one(selector)
            if content:
                text = content.get_text(strip=True, separator=' ')
                if len(text) > 100:
                    return text
        
        # Fallback to meta description
        meta = soup.find('meta', property='og:description')
        if meta and meta.get('content'):
            return meta['content']
        
        return ""
    
    def extract_title(self, soup, url):
        """Extract article title"""
        # og:title
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            title = og_title['content'].strip()
            if len(title) > 10:
                return title
        
        # h1
        h1 = soup.select_one('h1.title, article h1, h1')
        if h1:
            title = h1.get_text().strip()
            if len(title) > 10:
                return title
        
        # title tag
        if soup.title:
            title = re.sub(r'\s*[-|–].*$', '', soup.title.get_text().strip())
            if len(title) > 10:
                return title
        
        return None
    
    def extract_date(self, soup, url):
        """Extract article date"""
        # Meta tags
        for tag, attrs in [
            ('meta', {'property': 'article:published_time'}),
            ('meta', {'name': 'pubdate'}),
            ('meta', {'name': 'date'}),
        ]:
            meta = soup.find(tag, attrs)
            if meta and meta.get('content'):
                try:
                    return datetime.strptime(meta['content'][:10], '%Y-%m-%d')
                except:
                    pass
        
        # Time tag
        time_tag = soup.find('time', datetime=True)
        if time_tag:
            try:
                return datetime.strptime(time_tag['datetime'][:10], '%Y-%m-%d')
            except:
                pass
        
        return datetime.now()
    
    def collect_article(self, url: str, source_name: str) -> dict:
        """Collect and classify a single article"""
        
        # Skip if already exists
        if url in self.existing_urls:
            return None
        
        logger.info(f"  Fetching: {url[:60]}...")
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            time.sleep(1)
        except Exception as e:
            logger.warning(f"  Failed to fetch: {e}")
            return None
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract title
        title = self.extract_title(soup, url)
        if not title:
            logger.debug("  No title found")
            return None
        
        # Extract content
        content = self.extract_content(soup, url)
        
        # STRICT sector classification
        sector, area = self.classify_sector(title, content)
        
        if not sector:
            logger.info(f"  ✗ Not infrastructure: {title[:50]}...")
            return None
        
        # Extract other fields
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
        
        logger.info(f"  ✓ [{sector}] {title[:50]}...")
        return article
    
    def collect_from_rss(self, hours_back: int = 48):
        """Collect from all RSS feeds"""
        
        logger.info("=" * 70)
        logger.info(f"VIETNAM INFRASTRUCTURE NEWS COLLECTION")
        logger.info(f"Time range: Last {hours_back} hours ({hours_back//24} days)")
        logger.info(f"RSS Sources: {len(RSS_FEEDS)}")
        logger.info("=" * 70)
        
        for source_name, feed_url in RSS_FEEDS.items():
            logger.info(f"\n[{source_name}]")
            logger.info(f"  URL: {feed_url}")
            
            source_result = {
                "name": source_name,
                "url": feed_url,
                "status": "unknown",
                "articles_found": 0,
                "articles_collected": 0,
                "articles_skipped_not_infra": 0,
                "articles_skipped_duplicate": 0,
                "error": None,
                "timestamp": datetime.now().isoformat()
            }
            
            try:
                response = requests.get(feed_url, headers=self.headers, timeout=30)
                
                if response.status_code != 200:
                    source_result["status"] = f"HTTP_{response.status_code}"
                    source_result["error"] = f"HTTP {response.status_code}"
                    logger.error(f"  ✗ HTTP {response.status_code}")
                    self.source_status[source_name] = source_result
                    continue
                
                soup = BeautifulSoup(response.content, 'xml')
                items = soup.find_all('item') or soup.find_all('entry')
                
                source_result["articles_found"] = len(items)
                logger.info(f"  Found: {len(items)} items in feed")
                
                if not items:
                    source_result["status"] = "empty_feed"
                    self.source_status[source_name] = source_result
                    continue
                
                source_result["status"] = "success"
                collected = 0
                skipped_not_infra = 0
                skipped_dup = 0
                
                for item in items[:30]:  # Max 30 per source
                    link = item.find('link')
                    if link:
                        article_url = link.get('href') or link.get_text().strip()
                        
                        if article_url:
                            if article_url in self.existing_urls:
                                skipped_dup += 1
                                continue
                            
                            result = self.collect_article(article_url, source_name)
                            if result:
                                collected += 1
                            else:
                                skipped_not_infra += 1
                            
                            time.sleep(1.5)
                
                source_result["articles_collected"] = collected
                source_result["articles_skipped_not_infra"] = skipped_not_infra
                source_result["articles_skipped_duplicate"] = skipped_dup
                
                logger.info(f"  Result: {collected} collected, {skipped_not_infra} not infra, {skipped_dup} duplicates")
                
            except requests.exceptions.Timeout:
                source_result["status"] = "timeout"
                source_result["error"] = "Connection timeout (30s)"
                logger.error(f"  ✗ Timeout")
            except Exception as e:
                source_result["status"] = "error"
                source_result["error"] = str(e)[:100]
                logger.error(f"  ✗ Error: {e}")
            
            self.source_status[source_name] = source_result
            time.sleep(2)
        
        self._save_source_status()
        self._print_summary()
        
        return self.collected_articles
    
    def _print_summary(self):
        """Print collection summary"""
        logger.info("\n" + "=" * 70)
        logger.info("COLLECTION SUMMARY")
        logger.info("=" * 70)
        
        # By source
        logger.info("\nBy Source:")
        for name, status in self.source_status.items():
            icon = "✓" if status["status"] == "success" else "✗"
            logger.info(f"  {icon} {name}: {status['articles_collected']}/{status['articles_found']} collected")
        
        # By sector
        sector_counts = {}
        for a in self.collected_articles:
            s = a.get("sector", "Unknown")
            sector_counts[s] = sector_counts.get(s, 0) + 1
        
        logger.info(f"\nTotal Collected: {len(self.collected_articles)}")
        logger.info("\nBy Sector:")
        for sector, count in sorted(sector_counts.items(), key=lambda x: -x[1]):
            logger.info(f"  {sector}: {count}")
    
    def _save_source_status(self):
        """Save detailed source status report"""
        try:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            
            sector_counts = {}
            for a in self.collected_articles:
                s = a.get("sector", "Unknown")
                sector_counts[s] = sector_counts.get(s, 0) + 1
            
            report = {
                "generated_at": datetime.now().isoformat(),
                "total_sources": len(RSS_FEEDS),
                "successful_sources": sum(1 for s in self.source_status.values() if s["status"] == "success"),
                "total_collected": len(self.collected_articles),
                "sector_distribution": sector_counts,
                "source_details": self.source_status
            }
            
            with open(SOURCE_STATUS_PATH, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            
            # Text summary
            txt_path = OUTPUT_DIR / "news_sources_summary.txt"
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write("=" * 70 + "\n")
                f.write("VIETNAM INFRASTRUCTURE NEWS - SOURCE STATUS REPORT\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 70 + "\n\n")
                
                f.write(f"TOTAL COLLECTED: {len(self.collected_articles)} articles\n\n")
                
                f.write("SECTOR DISTRIBUTION:\n")
                f.write("-" * 40 + "\n")
                for sector, count in sorted(sector_counts.items(), key=lambda x: -x[1]):
                    f.write(f"  {sector}: {count}\n")
                
                f.write("\n" + "=" * 70 + "\n")
                f.write("SOURCE STATUS:\n")
                f.write("=" * 70 + "\n")
                
                for name, status in self.source_status.items():
                    icon = "✓" if status["status"] == "success" else "✗"
                    f.write(f"\n{icon} {name}\n")
                    f.write(f"  URL: {status['url']}\n")
                    f.write(f"  Status: {status['status']}\n")
                    f.write(f"  Found: {status['articles_found']}\n")
                    f.write(f"  Collected: {status['articles_collected']}\n")
                    f.write(f"  Skipped (not infra): {status.get('articles_skipped_not_infra', 0)}\n")
                    if status.get("error"):
                        f.write(f"  Error: {status['error']}\n")
            
            logger.info(f"Source status saved: {SOURCE_STATUS_PATH}")
            
        except Exception as e:
            logger.error(f"Error saving status: {e}")
    
    def save_to_excel(self):
        """Save collected articles to Excel database"""
        if not self.collected_articles:
            logger.info("No new articles to save")
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
                
                # Highlight new rows
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
    parser.add_argument('--hours-back', type=int, default=48)
    parser.add_argument('--days-back', type=int, default=None)
    args = parser.parse_args()
    
    hours = args.days_back * 24 if args.days_back else args.hours_back
    
    collector = NewsCollector()
    articles = collector.collect_from_rss(hours_back=hours)
    
    if articles:
        collector.save_to_excel()
    
    print(f"\nCollection complete: {len(articles)} infrastructure articles")


if __name__ == "__main__":
    main()
