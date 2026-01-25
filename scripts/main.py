#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News - Main Pipeline
"""

import logging
import sys
import os
from datetime import datetime
from pathlib import Path

# Setup paths FIRST
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Now import settings
from config.settings import DATA_DIR, OUTPUT_DIR

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

EXCEL_DB_PATH = DATA_DIR / "database" / "Vietnam_Infra_News_Database_Final.xlsx"


def load_all_articles_from_excel():
    """Load ALL articles from Excel database"""
    try:
        import openpyxl
    except ImportError:
        logger.error("openpyxl not installed")
        return []
    
    if not EXCEL_DB_PATH.exists():
        logger.warning(f"Excel not found: {EXCEL_DB_PATH}")
        return []
    
    logger.info(f"Loading from: {EXCEL_DB_PATH}")
    
    try:
        wb = openpyxl.load_workbook(EXCEL_DB_PATH, read_only=True, data_only=True)
        ws = wb.active
        
        headers = [cell.value for cell in ws[1]]
        col_map = {str(h).strip(): i for i, h in enumerate(headers) if h}
        
        articles = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not any(row):
                continue
            
            date_val = row[col_map.get("Date", 4)] if "Date" in col_map else None
            if date_val:
                date_str = date_val.strftime("%Y-%m-%d") if hasattr(date_val, 'strftime') else str(date_val)[:10]
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
        
        year_counts = {}
        for a in articles:
            year = a.get("date", "")[:4]
            if year:
                year_counts[year] = year_counts.get(year, 0) + 1
        
        logger.info(f"Loaded {len(articles)} articles")
        logger.info(f"By year: {dict(sorted(year_counts.items()))}")
        return articles
        
    except Exception as e:
        logger.error(f"Excel load error: {e}")
        import traceback
        traceback.print_exc()
        return []


def main():
    """Main pipeline - synchronous version"""
    
    print("=" * 70)
    print("VIETNAM INFRASTRUCTURE NEWS PIPELINE")
    print(f"Started: {datetime.now()}")
    print("=" * 70)
    
    # Ensure output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {OUTPUT_DIR}")
    
    # Step 1: Load existing articles
    print("\n[Step 1] Loading existing articles...")
    existing_articles = load_all_articles_from_excel()
    print(f"Loaded {len(existing_articles)} existing articles")
    
    # Step 2: Collect new articles
    print("\n[Step 2] Collecting new articles...")
    new_articles = []
    collector = None
    
    try:
        # Direct import from file
        import importlib.util
        collector_path = SCRIPT_DIR / "news_collector.py"
        print(f"Loading collector from: {collector_path}")
        
        spec = importlib.util.spec_from_file_location("news_collector", collector_path)
        collector_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(collector_module)
        
        collector = collector_module.NewsCollector()
        new_articles = collector.collect_from_rss(hours_back=48)
        print(f"Collected {len(new_articles)} new articles")
        
    except Exception as e:
        print(f"Collection error: {e}")
        import traceback
        traceback.print_exc()
    
    # Step 3: Save new articles
    if new_articles and collector:
        print("\n[Step 3] Saving new articles...")
        try:
            collector.save_to_excel()
        except Exception as e:
            print(f"Save error: {e}")
    
    # Step 4: Combine articles
    all_articles = existing_articles + new_articles
    print(f"\n[Step 4] Total articles: {len(all_articles)}")
    
    # Step 5: Create dashboard
    print("\n[Step 5] Creating dashboard...")
    try:
        import importlib.util
        # Direct import
        dashboard_path = SCRIPT_DIR / "dashboard_updater.py"
        print(f"Loading dashboard from: {dashboard_path}")
        
        spec = importlib.util.spec_from_file_location("dashboard_updater", dashboard_path)
        dashboard_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dashboard_module)
        
        print("Creating DashboardUpdater instance...")
        dashboard = dashboard_module.DashboardUpdater()
        
        print(f"Updating dashboard with {len(all_articles)} articles...")
        result = dashboard.update(all_articles)
        print(f"Dashboard result: {result}")
        
        print("Creating ExcelUpdater instance...")
        excel = dashboard_module.ExcelUpdater()
        excel_result = excel.update(all_articles)
        print(f"Excel result: {excel_result}")
        
    except Exception as e:
        print(f"Dashboard error: {e}")
        import traceback
        traceback.print_exc()
    
    # Verify outputs
    print("\n[Step 6] Verifying outputs...")
    index_file = OUTPUT_DIR / "index.html"
    dashboard_file = OUTPUT_DIR / "vietnam_dashboard.html"
    
    if index_file.exists():
        print(f"✓ index.html exists ({index_file.stat().st_size} bytes)")
    else:
        print(f"✗ index.html NOT found at {index_file}")
    
    if dashboard_file.exists():
        print(f"✓ vietnam_dashboard.html exists ({dashboard_file.stat().st_size} bytes)")
    else:
        print(f"✗ vietnam_dashboard.html NOT found")
    
    # List output files
    print("\nOutput directory contents:")
    for f in OUTPUT_DIR.iterdir():
        print(f"  {f.name} ({f.stat().st_size} bytes)")
    
    # Step 7: Send notification (skip if no email config)
    print("\n[Step 7] Notifications...")
    try:
        from config.settings import EMAIL_USERNAME, EMAIL_PASSWORD
        if EMAIL_USERNAME and EMAIL_PASSWORD:
            notifier_path = SCRIPT_DIR / "send_notification.py"
            spec = importlib.util.spec_from_file_location("send_notification", notifier_path)
            notifier_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(notifier_module)
            
            notifier = notifier_module.EmailNotifier()
            notifier.run()
        else:
            print("Email credentials not set, skipping notification")
    except Exception as e:
        print(f"Notification error: {e}")
    
    print("\n" + "=" * 70)
    print("PIPELINE COMPLETE")
    print(f"Total: {len(all_articles)} | New: {len(new_articles)}")
    print("=" * 70)


if __name__ == "__main__":
    main()
