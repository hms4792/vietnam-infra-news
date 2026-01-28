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


class NewsCollector:
    """Collects infrastructure news with strict filtering"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }
        self.collected_articles = []
        self.existing_urls = set()
        self.source_status = {}
        
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
        """Classify article into sector. Returns (sector, area) or (None, None)."""
        text = f"{title} {content[:2000]}".lower()
        
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
            
            matches = sum(1 for kw in keywords if kw.lower() in text)
            
            if matches == 0:
                continue
            
            score = matches * 10 - priority
            
            if score > best_score or (score == best_score and priority < best_priority):
                best_score = score
                best_priority = priority
                best_sector = sector_name
                best_area = area
        
        if best_sector is None:
            return None, None
        
        return best_sector, best_area
    
    def collect_from_rss(self, hours_back: int = 48) -> list:
        """Collect articles from RSS feeds"""
        cutoff = datetime.now() - timedelta(hours=hours_back)
        
        logger.info(f"Collecting news from last {hours_back} hours")
        
        for source_name, feed_url in RSS_FEEDS.items():
            status = {"name": source_name, "found": 0, "collected": 0, "skipped": 0}
            
            try:
                logger.info(f"\n--- {source_name} ---")
                
                import feedparser
                feed = feedparser.parse(feed_url)
                
                status["found"] = len(feed.entries)
                
                for entry in feed.entries:
                    url = entry.get('link', '')
                    title = entry.get('title', '')
                    
                    if not url or not title:
                        continue
                    
                    if url in self.existing_urls:
                        status["skipped"] += 1
                        continue
                    
                    # Parse date
                    pub_date = datetime.now()
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        pub_date = datetime(*entry.published_parsed[:6])
                    
                    if pub_date < cutoff:
                        continue
                    
                    content = entry.get('summary', '') or entry.get('description', '')
                    
                    sector, area = self._classify_sector(title, content)
                    
                    if sector is None:
                        logger.info(f"  ✗ Not infra: {title[:50]}...")
                        continue
                    
                    article = {
                        "title": title,
                        "url": url,
                        "date": pub_date.strftime("%Y-%m-%d"),
                        "source": source_name,
                        "sector": sector,
                        "area": area,
                        "province": "Vietnam",
                        "summary": content[:500] if content else title,
                    }
                    
                    self.collected_articles.append(article)
                    self.existing_urls.add(url)
                    status["collected"] += 1
                    
                    logger.info(f"  ✓ [{sector}] {title[:50]}...")
                
            except Exception as e:
                logger.error(f"Error with {source_name}: {e}")
            
            finally:
                self.source_status[source_name] = status
                time.sleep(1)
        
        self._save_status()
        return self.collected_articles
    
    def _save_status(self):
        """Save collection status"""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        with open(OUTPUT_DIR / "news_sources_status.json", 'w') as f:
            json.dump(self.source_status, f, indent=2)
        
        total = len(self.collected_articles)
        print(f"\n{'='*50}")
        print(f"TOTAL COLLECTED: {total}")
        if total > 0:
            from collections import Counter
            sectors = Counter(a["sector"] for a in self.collected_articles)
            for s, c in sectors.most_common():
                print(f"  {s}: {c}")
    
    def save_to_excel(self):
        """Save new articles to Excel"""
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
                headers = ["Area", "Business Sector", "Province", "News Tittle", 
                          "Date", "Source", "Link", "Short summary"]
                for col, h in enumerate(headers, 1):
                    ws.cell(row=1, column=col, value=h)
            
            yellow = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
            
            for article in self.collected_articles:
                row = ws.max_row + 1
                ws.cell(row=row, column=1, value=article.get("area", "Environment"))
                ws.cell(row=row, column=2, value=article.get("sector", ""))
                ws.cell(row=row, column=3, value=article.get("province", "Vietnam"))
                ws.cell(row=row, column=4, value=article.get("title", ""))
                ws.cell(row=row, column=5, value=article.get("date", ""))
                ws.cell(row=row, column=6, value=article.get("source", ""))
                ws.cell(row=row, column=7, value=article.get("url", ""))
                ws.cell(row=row, column=8, value=article.get("summary", ""))
                
                for col in range(1, 9):
                    ws.cell(row=row, column=col).fill = yellow
            
            wb.save(EXCEL_DB_PATH)
            logger.info(f"Saved {len(self.collected_articles)} articles to Excel")
            
        except Exception as e:
            logger.error(f"Error saving: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--hours-back', type=int, default=48)
    parser.add_argument('--days-back', type=int, default=None)
    args = parser.parse_args()
    
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
