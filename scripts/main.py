#!/usr/bin/env python3
"""
Vietnam Infrastructure News Pipeline - Main Entry Point
Loads existing data from Excel database, collects new news, updates dashboard
"""
import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import DATA_DIR, OUTPUT_DIR

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/pipeline.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# Excel database path - adjust this to match your actual file
EXCEL_DB_FILENAME = "Vietnam_Infra_News_Database_Final.xlsx"


def find_excel_database() -> Path:
    """Find the Excel database file"""
    possible_paths = [
        DATA_DIR / "database" / EXCEL_DB_FILENAME,
        DATA_DIR / EXCEL_DB_FILENAME,
        Path("data/database") / EXCEL_DB_FILENAME,
        Path("data") / EXCEL_DB_FILENAME,
    ]
    
    for path in possible_paths:
        if path.exists():
            logger.info(f"Found Excel database: {path}")
            return path
    
    logger.warning(f"Excel database not found. Searched: {possible_paths}")
    return None


def load_existing_articles_from_excel() -> list:
    """Load ALL existing articles from Excel database"""
    try:
        import openpyxl
    except ImportError:
        logger.error("openpyxl not installed - run: pip install openpyxl")
        return []
    
    excel_path = find_excel_database()
    if not excel_path:
        return []
    
    logger.info(f"Loading articles from Excel: {excel_path}")
    
    try:
        wb = openpyxl.load_workbook(excel_path, read_only=True, data_only=True)
        ws = wb.active
        
        articles = []
        headers = []
        
        for row_idx, row in enumerate(ws.iter_rows(values_only=True), 1):
            if row_idx == 1:
                # Header row
                headers = [str(cell).strip() if cell else f"col_{i}" for i, cell in enumerate(row)]
                logger.info(f"Excel columns found: {headers}")
                continue
            
            if not any(row):
                continue
            
            # Create raw article dict
            raw = {}
            for i, value in enumerate(row):
                if i < len(headers):
                    raw[headers[i]] = value
            
            # Map to standard format - handle various possible column names
            date_val = raw.get("Date", raw.get("date", raw.get("Published", "")))
            if date_val:
                if hasattr(date_val, 'strftime'):
                    date_str = date_val.strftime("%Y-%m-%d")
                else:
                    date_str = str(date_val)[:10]
            else:
                date_str = ""
            
            article = {
                "id": row_idx,
                "title": raw.get("News Tittle", raw.get("Title", raw.get("News Title", raw.get("title", "")))),
                "title_en": raw.get("Title (EN)", raw.get("title_en", raw.get("Summary (EN)", ""))),
                "title_ko": raw.get("Title (KO)", raw.get("title_ko", raw.get("Summary (KO)", ""))),
                "summary_vi": raw.get("Short summary", raw.get("Summary", raw.get("summary", ""))),
                "summary_en": raw.get("Summary (EN)", raw.get("summary_en", "")),
                "summary_ko": raw.get("Summary (KO)", raw.get("summary_ko", "")),
                "sector": raw.get("Business Sector", raw.get("Sector", raw.get("sector", "Waste Water"))),
                "area": raw.get("Area", raw.get("area", "Environment")),
                "province": raw.get("Province", raw.get("province", "Vietnam")),
                "source": raw.get("Source Name", raw.get("Source", raw.get("source", ""))),
                "url": raw.get("Source URL", raw.get("URL", raw.get("url", raw.get("Link", "")))),
                "date": date_str,
                "published": date_str
            }
            
            # Only add if has meaningful content
            if article.get("title") or article.get("url"):
                articles.append(article)
        
        wb.close()
        logger.info(f"Successfully loaded {len(articles)} articles from Excel")
        return articles
        
    except Exception as e:
        logger.error(f"Error loading Excel: {e}")
        import traceback
        traceback.print_exc()
        return []


def load_articles_from_json() -> list:
    """Load articles from JSON files as fallback"""
    all_articles = []
    
    json_files = sorted(DATA_DIR.glob("processed_*.json"), reverse=True)
    if not json_files:
        json_files = sorted(DATA_DIR.glob("news_*.json"), reverse=True)
    
    for json_file in json_files[:5]:
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                articles = data.get("articles", data if isinstance(data, list) else [])
                all_articles.extend(articles)
        except Exception as e:
            logger.error(f"Error loading {json_file}: {e}")
    
    # Deduplicate
    seen = set()
    unique = []
    for a in all_articles:
        url = a.get("url", a.get("source_url", ""))
        if url and url not in seen:
            seen.add(url)
            unique.append(a)
    
    return unique


def save_new_articles_to_excel(new_articles: list, existing_urls: set):
    """Append new articles to Excel database"""
    try:
        import openpyxl
    except ImportError:
        return
    
    excel_path = find_excel_database()
    if not excel_path:
        return
    
    # Filter truly new articles
    truly_new = [a for a in new_articles if a.get("url", "") not in existing_urls]
    
    if not truly_new:
        logger.info("No new articles to add to Excel")
        return
    
    try:
        wb = openpyxl.load_workbook(excel_path)
        ws = wb.active
        start_row = ws.max_row + 1
        
        for i, article in enumerate(truly_new):
            row = start_row + i
            ws.cell(row=row, column=1, value=row - 1)
            ws.cell(row=row, column=2, value=article.get("date", ""))
            ws.cell(row=row, column=3, value=article.get("area", "Environment"))
            ws.cell(row=row, column=4, value=article.get("sector", "Waste Water"))
            ws.cell(row=row, column=5, value=article.get("province", "Vietnam"))
            ws.cell(row=row, column=6, value=article.get("title", ""))
            ws.cell(row=row, column=7, value=article.get("summary_en", ""))
            ws.cell(row=row, column=8, value=article.get("summary_ko", ""))
            ws.cell(row=row, column=9, value=article.get("source", ""))
            ws.cell(row=row, column=10, value=article.get("url", ""))
        
        wb.save(excel_path)
        logger.info(f"Added {len(truly_new)} new articles to Excel")
        
    except Exception as e:
        logger.error(f"Error saving to Excel: {e}")


async def run_full_pipeline():
    """Run the complete news pipeline"""
    logger.info("=" * 60)
    logger.info("Starting Vietnam Infrastructure News Pipeline")
    logger.info("=" * 60)
    
    # Ensure directories
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    Path("logs").mkdir(exist_ok=True)
    
    # Step 1: Load existing articles from Excel database
    logger.info("Step 1: Loading existing articles from Excel database...")
    existing_articles = load_existing_articles_from_excel()
    
    if not existing_articles:
        logger.warning("No articles in Excel, trying JSON files...")
        existing_articles = load_articles_from_json()
    
    existing_urls = set(a.get("url", "") for a in existing_articles if a.get("url"))
    logger.info(f"Loaded {len(existing_articles)} existing articles")
    
    # Step 2: Collect new news (last 30 days for full coverage)
    logger.info("Step 2: Collecting new news (last 30 days)...")
    new_articles = []
    collector = None
    try:
        from scripts.news_collector import NewsCollector
        collector = NewsCollector()
        new_articles = collector.collect_from_rss(hours_back=720)  # 30 days
        logger.info(f"Collected {len(new_articles)} new articles")
        
        # Log sector distribution
        sector_counts = {}
        for a in new_articles:
            s = a.get("sector", "Unknown")
            sector_counts[s] = sector_counts.get(s, 0) + 1
        logger.info(f"Sector distribution: {sector_counts}")
        
    except Exception as e:
        logger.error(f"News collection error: {e}")
        import traceback
        traceback.print_exc()
    
    # Step 3: AI Summarization
    if new_articles:
        logger.info("Step 3: AI Summarization...")
        try:
            from scripts.ai_summarizer import AISummarizer
            summarizer = AISummarizer()
            new_articles = await summarizer.process_articles(new_articles)
        except Exception as e:
            logger.error(f"Summarization error: {e}")
    
    # Step 4: Save new articles to Excel
    if new_articles and collector:
        logger.info("Step 4: Saving new articles to Excel...")
        try:
            collector.save_to_excel()
            logger.info(f"Saved {len(new_articles)} new articles to Excel database")
        except Exception as e:
            logger.error(f"Error saving to Excel: {e}")
    
    # Step 5: Combine all articles
    all_articles = existing_articles.copy()
    for article in new_articles:
        if article.get("url", "") not in existing_urls:
            all_articles.append(article)
    
    logger.info(f"Total articles for dashboard: {len(all_articles)}")
    
    # Step 6: Update Dashboard with ALL articles
    logger.info("Step 5: Updating dashboard...")
    try:
        from scripts.dashboard_updater import DashboardUpdater
        dashboard = DashboardUpdater()
        dashboard_path = dashboard.update(all_articles)
        logger.info(f"Dashboard updated: {dashboard_path}")
    except Exception as e:
        logger.error(f"Dashboard error: {e}")
        import traceback
        traceback.print_exc()
    
    # Step 7: Update Excel export
    logger.info("Step 6: Updating Excel export...")
    try:
        from scripts.dashboard_updater import ExcelUpdater
        excel = ExcelUpdater()
        excel_path = excel.update(all_articles)
        logger.info(f"Excel export: {excel_path}")
    except Exception as e:
        logger.error(f"Excel error: {e}")
    
    # Step 8: Send notifications
    logger.info("Step 7: Sending notifications...")
    try:
        from scripts.notifier import NotificationManager
        notifier = NotificationManager()
        results = await notifier.send_all(all_articles)
        logger.info(f"Notifications: {results}")
    except Exception as e:
        logger.error(f"Notification error: {e}")
    
    # Summary
    logger.info("=" * 60)
    logger.info("Pipeline Complete!")
    logger.info(f"  Existing articles: {len(existing_articles)}")
    logger.info(f"  New articles: {len(new_articles)}")
    logger.info(f"  Total in dashboard: {len(all_articles)}")
    logger.info("=" * 60)


async def run_dashboard_only():
    """Update dashboard without collecting new articles"""
    logger.info("Updating dashboard only...")
    
    all_articles = load_existing_articles_from_excel()
    if not all_articles:
        all_articles = load_articles_from_json()
    
    if not all_articles:
        logger.error("No articles found!")
        return
    
    logger.info(f"Updating dashboard with {len(all_articles)} articles")
    
    from scripts.dashboard_updater import DashboardUpdater, ExcelUpdater
    
    dashboard = DashboardUpdater()
    dashboard.update(all_articles)
    
    excel = ExcelUpdater()
    excel.update(all_articles)


async def run_notify_only():
    """Send notifications only"""
    logger.info("Sending notifications only...")
    
    all_articles = load_existing_articles_from_excel()
    if not all_articles:
        all_articles = load_articles_from_json()
    
    if not all_articles:
        logger.error("No articles found!")
        return
    
    from scripts.notifier import NotificationManager
    notifier = NotificationManager()
    await notifier.send_all(all_articles)


def main():
    parser = argparse.ArgumentParser(description='Vietnam Infrastructure News Pipeline')
    parser.add_argument('--full', action='store_true', help='Run full pipeline')
    parser.add_argument('--collect', action='store_true', help='Collect news only')
    parser.add_argument('--notify', action='store_true', help='Send notifications only')
    parser.add_argument('--dashboard', action='store_true', help='Update dashboard only')
    
    args = parser.parse_args()
    
    if args.notify:
        asyncio.run(run_notify_only())
    elif args.dashboard:
        asyncio.run(run_dashboard_only())
    else:
        asyncio.run(run_full_pipeline())


if __name__ == "__main__":
    main()
