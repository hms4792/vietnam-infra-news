#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News Collector
Strict classification - ONLY infrastructure news
Can be run directly: python news_collector.py --hours-back 48
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
import argparse
from pathlib import Path

# Setup paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    RSS_FEEDS, DATA_DIR, OUTPUT_DIR,
    SECTOR_KEYWORDS, EXCLUSION_KEYWORDS
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

EXCEL_DB_PATH = DATA_DIR / "database" / "Vietnam_Infra_News_Database_Final.xlsx"

# Province detection
PROVINCE_KEYWORDS = {
    "Ho Chi Minh City": ["ho chi minh", "hcmc", "saigon", "tp.hcm", "hồ chí minh"],
    "Hanoi": ["hanoi", "ha noi", "hà nội"],
    "Da Nang": ["da nang", "đà nẵng"],
    "Hai Phong": ["hai phong", "hải phòng"],
    "Can Tho": ["can tho", "cần thơ"],
    "Binh Duong": ["binh duong", "bình dương"],
    "Dong Nai": ["dong nai", "đồng nai"],
    "Quang Ninh": ["quang ninh", "quảng ninh", "ha long"],
    "Bac Ninh": ["bac ninh", "bắc ninh"],
    "Thanh Hoa": ["thanh hoa", "thanh hoá"],
    "Nghe An": ["nghe an", "nghệ an"],
    "Khanh Hoa": ["khanh hoa", "nha trang"],
    "Ba Ria-Vung Tau": ["ba ria", "vung tau", "vũng tàu"],
}


class NewsCollector:
    """Collects infrastructure news with strict filtering"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        self.collected_articles = []
        self.existing_urls = set()
        self.source_status = {}
        
        # Load existing URLs
        self._load_existing_urls()
    
    def _load_existing_urls(self):
        """Load URLs from Excel to avoid duplicates"""
        if not EXCEL_DB_PATH.exists():
            return
        
        try:
            import openpyxl
            wb = openpyxl.load_workbook(EXCEL_DB_PATH, read_only=True, data_only=True)
            ws = wb.active
            
            headers = [cell.value for cell in ws[1]]
            link_idx = None
            for i, h in enumerate(headers):
                if h and "Link" in str(h):
                    link_idx = i
                    break
            
            if link_idx is not None:
                for row in ws.iter_rows(min_row=2, values_only=True):
                    if row[link_idx]:
                        self.existing_urls.add(str(row[link_idx]).strip())
            
            wb.close()
            logger.info(f"Loaded {len(self.existing_urls)} existing URLs")
        except Exception as e:
            logger.error(f"Error loading URLs: {e}")
    
    def _should_exclude(self, text: str) -> bool:
        """Check if article should be excluded"""
        text_lower = text.lower()
        for keyword in EXCLUSION_KEYWORDS:
            if keyword.lower() in text_lower:
                return True
        return False
    
    def _classify_sector(self, title: str, content: str = "") -> tuple:
        """
        Classify article into sector.
        Returns (sector, area) or (None, None) if not infrastructure.
        """
        text = f"{title} {content[:2000]}".lower()
        
        # Check exclusions first
        if self._should_exclude(text):
            return None, None
        
        best_sector = None
        best_area = None
        best_score = 0
        best_priority = 999
        
        for sector_name, sector_info in SECTOR_KEYWORDS.items():
            keywords = sector_info["keywords"]
            area = sector_info["area"]
            priority = sector_info["priority"]
            
            # Count keyword matches
            matches = sum(1 for kw in keywords if kw.lower() in text)
            
            if matches == 0:
                continue
            
            # Score = matches * 10 - priority (higher is better)
            score = matches * 10 - priority
            
            if score > best_score or (score == best_score and priority < best_priority):
                best_score = score
                best_priority = priority
                best_sector = sector_name
                best_area = area
        
        # Must have at least one keyword match
        if best_sector is None:
            return None, None
        
        return best_sector, best_area
    
    def _detect_province(self, text: str) -> str:
        """Detect province from text"""
        text_lower = text.lower()
        for province, keywords in PROVINCE_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    return province
        return "Vietnam"
    
    def _fetch_content(self, url: str) -> str:
        """Fetch article content"""
        try:
            resp = requests.get(url, headers=self.headers, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.content, 'html.parser')
            
            # Remove scripts and styles
            for tag in soup(['script', 'style', 'nav', 'footer', 'header']):
                tag.decompose()
            
            # Try common content selectors
            for selector in ['article', '.article-content', '.post-content', '.entry-content', '.content']:
                content = soup.select_one(selector)
                if content:
                    return content.get_text(separator=' ', strip=True)[:3000]
            
            # Fallback to body
            body = soup.find('body')
            if body:
                return body.get_text(separator=' ', strip=True)[:3000]
            
            return ""
        except:
            return ""
    
    def collect_from_rss(self, hours_back: int = 48) -> list:
        """Collect articles from RSS feeds"""
        cutoff = datetime.now() - timedelta(hours=hours_back)
        
        logger.info(f"Collecting news from last {hours_back} hours")
        logger.info(f"Cutoff: {cutoff}")
        
        for source_name, feed_url in RSS_FEEDS.items():
            status = {
                "name": source_name,
                "url": feed_url,
                "status": "pending",
                "found": 0,
                "collected": 0,
                "skipped_not_infra": 0,
                "skipped_duplicate": 0,
                "skipped_old": 0,
                "error": None
            }
            
            try:
                logger.info(f"\n--- {source_name} ---")
                
                import feedparser
                feed = feedparser.parse(feed_url)
                
                if feed.bozo and not feed.entries:
                    status["status"] = "error"
                    status["error"] = "Feed parse error"
                    continue
                
                status["found"] = len(feed.entries)
                logger.info(f"Found {len(feed.entries)} entries")
                
                for entry in feed.entries:
                    url = entry.get('link', '')
                    title = entry.get('title', '')
                    
                    if not url or not title:
                        continue
                    
                    # Check duplicate
                    if url in self.existing_urls:
                        status["skipped_duplicate"] += 1
                        continue
                    
                    # Check date
                    pub_date = None
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        pub_date = datetime(*entry.published_parsed[:6])
                    elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                        pub_date = datetime(*entry.updated_parsed[:6])
                    else:
                        pub_date = datetime.now()
                    
                    if pub_date < cutoff:
                        status["skipped_old"] += 1
                        continue
                    
                    # Fetch content for better classification
                    content = entry.get('summary', '') or entry.get('description', '')
                    
                    # Classify
                    sector, area = self._classify_sector(title, content)
                    
                    if sector is None:
                        status["skipped_not_infra"] += 1
                        logger.info(f"  ✗ Not infra: {title[:60]}...")
                        continue
                    
                    # Detect province
                    province = self._detect_province(f"{title} {content}")
                    
                    article = {
                        "title": title,
                        "url": url,
                        "date": pub_date.strftime("%Y-%m-%d"),
                        "source": source_name,
                        "sector": sector,
                        "area": area,
                        "province": province,
                        "summary_vi": content[:500] if content else title,
                    }
                    
                    self.collected_articles.append(article)
                    self.existing_urls.add(url)
                    status["collected"] += 1
                    
                    logger.info(f"  ✓ [{sector}] {title[:60]}...")
                
                status["status"] = "success"
                
            except Exception as e:
                status["status"] = "error"
                status["error"] = str(e)
                logger.error(f"Error with {source_name}: {e}")
            
            finally:
                self.source_status[source_name] = status
                time.sleep(1)  # Rate limiting
        
        self._save_source_status()
        self._print_summary()
        
        return self.collected_articles
    
    def _save_source_status(self):
        """Save source status to JSON"""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        status_path = OUTPUT_DIR / "news_sources_status.json"
        with open(status_path, 'w', encoding='utf-8') as f:
            json.dump(self.source_status, f, indent=2, ensure_ascii=False)
        
        # Also save human-readable summary
        summary_path = OUTPUT_DIR / "news_sources_summary.txt"
        with open(summary_path, 'w', encoding='utf-8') as f:
            f.write(f"News Collection Summary - {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
            f.write("=" * 60 + "\n\n")
            
            for name, status in self.source_status.items():
                f.write(f"{name}\n")
                f.write(f"  Status: {status['status']}\n")
                f.write(f"  Found: {status['found']}\n")
                f.write(f"  Collected: {status['collected']}\n")
                f.write(f"  Skipped (not infra): {status['skipped_not_infra']}\n")
                f.write(f"  Skipped (duplicate): {status['skipped_duplicate']}\n")
                if status.get('error'):
                    f.write(f"  Error: {status['error']}\n")
                f.write("\n")
    
    def _print_summary(self):
        """Print collection summary"""
        total = len(self.collected_articles)
        
        print(f"\n{'='*60}")
        print(f"COLLECTION SUMMARY")
        print(f"{'='*60}")
        print(f"Total collected: {total}")
        
        if total > 0:
            # By sector
            sectors = {}
            for a in self.collected_articles:
                s = a.get("sector", "Unknown")
                sectors[s] = sectors.get(s, 0) + 1
            
            print(f"\nBy Sector:")
            for sector, count in sorted(sectors.items(), key=lambda x: -x[1]):
                print(f"  {sector}: {count}")
            
            # By source
            sources = {}
            for a in self.collected_articles:
                s = a.get("source", "Unknown")
                sources[s] = sources.get(s, 0) + 1
            
            print(f"\nBy Source:")
            for source, count in sorted(sources.items(), key=lambda x: -x[1]):
                print(f"  {source}: {count}")
    
    def save_to_excel(self):
        """Save new articles to Excel database"""
        if not self.collected_articles:
            logger.info("No new articles to save")
            return
        
        try:
            import openpyxl
            from openpyxl.styles import PatternFill
            
            EXCEL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            
            if EXCEL_DB_PATH.exists():
                wb = openpyxl.load_workbook(EXCEL_DB_PATH)
                ws = wb.active
            else:
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = "News Database"
                headers = ["Area", "Business Sector", "Province", "News Tittle", 
                          "Date", "Source", "Link", "Short summary"]
                for col, h in enumerate(headers, 1):
                    ws.cell(row=1, column=col, value=h)
            
            # Highlight for new articles
            yellow = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
            
            # Append new articles
            for article in self.collected_articles:
                row = ws.max_row + 1
                ws.cell(row=row, column=1, value=article.get("area", "Environment"))
                ws.cell(row=row, column=2, value=article.get("sector", ""))
                ws.cell(row=row, column=3, value=article.get("province", "Vietnam"))
                ws.cell(row=row, column=4, value=article.get("title", ""))
                ws.cell(row=row, column=5, value=article.get("date", ""))
                ws.cell(row=row, column=6, value=article.get("source", ""))
                ws.cell(row=row, column=7, value=article.get("url", ""))
                ws.cell(row=row, column=8, value=article.get("summary_vi", ""))
                
                # Highlight new rows
                for col in range(1, 9):
                    ws.cell(row=row, column=col).fill = yellow
            
            wb.save(EXCEL_DB_PATH)
            logger.info(f"Saved {len(self.collected_articles)} articles to {EXCEL_DB_PATH}")
            
        except Exception as e:
            logger.error(f"Error saving to Excel: {e}")


def main():
    """Main function for command line execution"""
    parser = argparse.ArgumentParser(description='Collect Vietnam infrastructure news')
    parser.add_argument('--hours-back', type=int, default=48, help='Hours to look back')
    parser.add_argument('--days-back', type=int, default=None, help='Days to look back')
    args = parser.parse_args()
    
    # Calculate hours
    hours = args.hours_back
    if args.days_back:
        hours = args.days_back * 24
    
    print("=" * 60)
    print("VIETNAM INFRASTRUCTURE NEWS COLLECTOR")
    print("=" * 60)
    
    collector = NewsCollector()
    articles = collector.collect_from_rss(hours_back=hours)
    
    if articles:
        collector.save_to_excel()
    
    print(f"\nTotal: {len(articles)} articles collected")


if __name__ == "__main__":
    main()
