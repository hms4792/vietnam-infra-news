#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News - Main Pipeline
Preserves existing Excel data (2019-2025) and adds new articles
"""

import asyncio
import logging
import sys
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import DATA_DIR, OUTPUT_DIR

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

EXCEL_DB_PATH = DATA_DIR / "database" / "Vietnam_Infra_News_Database_Final.xlsx"


def load_all_articles_from_excel():
    """Load ALL articles from Excel database (2019-present)"""
    
    try:
        import openpyxl
    except ImportError:
        logger.error("openpyxl not installed")
        return []
    
    if not EXCEL_DB_PATH.exists():
        logger.warning(f"Excel database not found: {EXCEL_DB_PATH}")
        return []
    
    logger.info(f"Loading articles from: {EXCEL_DB_PATH}")
    
    try:
        wb = openpyxl.load_workbook(EXCEL_DB_PATH, read_only=True, data_only=True)
        ws = wb.active
        
        headers = [cell.value for cell in ws[1]]
        logger.info(f"Excel headers: {headers}")
        
        # Column mapping
        col_map = {}
        for i, h in enumerate(headers):
            if h:
                col_map[str(h).strip()] = i
        
        articles = []
        
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not any(row):
                continue
            
            # Parse date
            date_val = row[col_map.get("Date", 4)] if "Date" in col_map else None
            if date_val:
                if hasattr(date_val, 'strftime'):
                    date_str = date_val.strftime("%Y-%m-%d")
                else:
                    date_str = str(date_val)[:10]
            else:
                date_str = ""
            
            article = {
                "area": row[col_map.get("Area", 0)] or "Environment",
                "sector": row[col_map.get("Business Sector", 1)] or "",
                "province": row[col_map.get("Province", 2)] or "Vietnam",
                "title": row[col_map.get("News Tittle", 3)] or "",
                "date": date_str,
                "source": row[col_map.get("Source", 5)] or "",
                "url": row[col_map.get("Link", 6)] or "",
                "summary_vi": row[col_map.get("Short summary", 7)] or "",
            }
            
            if article["title"] or article["url"]:
                articles.append(article)
        
        wb.close()
        
        # Count by year
        year_counts = {}
        for a in articles:
            year = a.get("date", "")[:4]
            if year:
                year_counts[year] = year_counts.get(year, 0) + 1
        
        logger.info(f"Loaded {len(articles)} total articles from Excel")
        logger.info(f"By year: {dict(sorted(year_counts.items()))}")
        
        return articles
        
    except Exception as e:
        logger.error(f"Error loading Excel: {e}")
        import traceback
        traceback.print_exc()
        return []


async def main():
    """Main pipeline execution"""
    
    logger.info("=" * 70)
    logger.info("VIETNAM INFRASTRUCTURE NEWS PIPELINE")
    logger.info(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)
    
    # Step 1: Load existing articles from Excel (ALL years)
    logger.info("\nStep 1: Loading existing articles from Excel...")
    existing_articles = load_all_articles_from_excel()
    logger.info(f"Found {len(existing_articles)} existing articles (2019-present)")
    
    # Step 2: Collect new articles
    logger.info("\nStep 2: Collecting new infrastructure news...")
    new_articles = []
    collector = None
    
    try:
        from scripts.news_collector import NewsCollector
        collector = NewsCollector()
        new_articles = collector.collect_from_rss(hours_back=48)
        logger.info(f"Collected {len(new_articles)} new articles")
    except Exception as e:
        logger.error(f"News collection error: {e}")
        import traceback
        traceback.print_exc()
    
    # Step 3: Save new articles to Excel
    if new_articles and collector:
        logger.info("\nStep 3: Saving new articles to Excel...")
        try:
            collector.save_to_excel()
        except Exception as e:
            logger.error(f"Error saving to Excel: {e}")
    
    # Step 4: Combine all articles for dashboard
    all_articles = existing_articles + new_articles
    logger.info(f"\nStep 4: Total articles for dashboard: {len(all_articles)}")
    
    # Step 5: Update dashboard
    logger.info("\nStep 5: Updating dashboard...")
    try:
        from scripts.dashboard_updater import DashboardUpdater, ExcelUpdater
        
        dashboard = DashboardUpdater()
        dashboard.update(all_articles)
        
        excel = ExcelUpdater()
        excel.update(all_articles)
        
        logger.info("Dashboard and Excel output updated")
    except Exception as e:
        logger.error(f"Dashboard update error: {e}")
        import traceback
        traceback.print_exc()
    
    # Step 6: Send notifications
    logger.info("\nStep 6: Sending notifications...")
    try:
        from scripts.send_notification import EmailNotifier
        notifier = EmailNotifier()
        notifier.run()
    except Exception as e:
        logger.error(f"Notification error: {e}")
    
    logger.info("\n" + "=" * 70)
    logger.info("PIPELINE COMPLETE")
    logger.info(f"Total articles in database: {len(all_articles)}")
    logger.info(f"New articles collected: {len(new_articles)}")
    logger.info("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
