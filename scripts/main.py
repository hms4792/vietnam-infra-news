#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News - Main Pipeline
Ensures dashboard is ALWAYS created even if other steps fail
"""

import logging
import sys
import os
from datetime import datetime
from pathlib import Path

# Setup paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Direct paths
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
EXCEL_DB_PATH = DATA_DIR / "database" / "Vietnam_Infra_News_Database_Final.xlsx"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def load_articles_from_excel():
    """Load articles from Excel - standalone function"""
    try:
        import openpyxl
    except ImportError:
        print("ERROR: openpyxl not installed")
        return []
    
    if not EXCEL_DB_PATH.exists():
        print(f"WARNING: Excel not found: {EXCEL_DB_PATH}")
        return []
    
    print(f"Loading from: {EXCEL_DB_PATH}")
    
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
        
        print(f"Loaded {len(articles)} articles")
        print(f"By year: {dict(sorted(year_counts.items()))}")
        return articles
        
    except Exception as e:
        print(f"Excel load error: {e}")
        import traceback
        traceback.print_exc()
        return []


def collect_new_articles():
    """Collect new articles - isolated with full error handling"""
    print("\n[Step 2] Collecting new articles...")
    
    try:
        import importlib.util
        collector_path = SCRIPT_DIR / "news_collector.py"
        print(f"Loading collector from: {collector_path}")
        
        if not collector_path.exists():
            print(f"ERROR: news_collector.py not found!")
            return []
        
        spec = importlib.util.spec_from_file_location("news_collector", collector_path)
        collector_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(collector_module)
        
        collector = collector_module.NewsCollector()
        new_articles = collector.collect_from_rss(hours_back=48)
        print(f"Collected {len(new_articles)} new articles")
        
        # Save to Excel
        if new_articles:
            try:
                collector.save_to_excel()
            except Exception as e:
                print(f"Save error: {e}")
        
        return new_articles
        
    except Exception as e:
        print(f"Collection error: {e}")
        import traceback
        traceback.print_exc()
        return []


def create_dashboard(all_articles):
    """Create dashboard - isolated with full error handling"""
    print("\n[Step 5] Creating dashboard...")
    print(f"Articles to process: {len(all_articles)}")
    
    # Ensure output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    try:
        import importlib.util
        dashboard_path = SCRIPT_DIR / "dashboard_updater.py"
        print(f"Loading dashboard from: {dashboard_path}")
        
        if not dashboard_path.exists():
            print(f"ERROR: dashboard_updater.py not found!")
            return False
        
        spec = importlib.util.spec_from_file_location("dashboard_updater", dashboard_path)
        dashboard_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dashboard_module)
        
        print("Creating DashboardUpdater instance...")
        dashboard = dashboard_module.DashboardUpdater()
        
        print(f"Calling update() with {len(all_articles)} articles...")
        result = dashboard.update(all_articles)
        print(f"Dashboard result: {result}")
        
        print("Creating ExcelUpdater instance...")
        excel = dashboard_module.ExcelUpdater()
        excel_result = excel.update(all_articles)
        print(f"Excel result: {excel_result}")
        
        return True
        
    except Exception as e:
        print(f"Dashboard error: {e}")
        import traceback
        traceback.print_exc()
        
        # FALLBACK: Create minimal dashboard directly
        print("\n[FALLBACK] Creating minimal dashboard...")
        return create_minimal_dashboard(all_articles)


def create_minimal_dashboard(articles):
    """Emergency fallback - create basic dashboard HTML"""
    try:
        import json
        
        js_data = json.dumps([{
            "id": i,
            "title": {"vi": str(a.get("title", ""))[:200], "en": str(a.get("title", ""))[:200], "ko": str(a.get("title", ""))[:200]},
            "summary": {"vi": "", "en": "", "ko": ""},
            "sector": a.get("sector", "Unknown"),
            "area": a.get("area", "Environment"),
            "province": a.get("province", "Vietnam"),
            "source": a.get("source", ""),
            "url": a.get("url", ""),
            "date": str(a.get("date", ""))[:10]
        } for i, a in enumerate(articles, 1)], ensure_ascii=False)
        
        html = f'''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Vietnam Infrastructure News</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-100 p-8">
    <h1 class="text-2xl font-bold mb-4">🇻🇳 Vietnam Infrastructure News ({len(articles)} articles)</h1>
    <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
    <div id="list" class="mt-4 space-y-2"></div>
    <script>
    const DATA = {js_data};
    document.getElementById('list').innerHTML = DATA.slice(0, 100).map(a => 
        `<div class="bg-white p-3 rounded shadow">
            <span class="text-xs bg-teal-100 px-2 py-1 rounded">${{a.sector}}</span>
            <span class="text-xs text-slate-500 ml-2">${{a.date}}</span>
            <div class="font-medium mt-1">${{a.title.vi}}</div>
            <div class="text-sm text-slate-500">${{a.source}} | ${{a.province}}</div>
        </div>`
    ).join('');
    </script>
</body>
</html>'''
        
        index_path = OUTPUT_DIR / "index.html"
        dashboard_path = OUTPUT_DIR / "vietnam_dashboard.html"
        
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(html)
        with open(dashboard_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        print(f"Minimal dashboard created: {index_path}")
        return True
        
    except Exception as e:
        print(f"Minimal dashboard error: {e}")
        return False


def main():
    """Main pipeline"""
    
    print("=" * 70)
    print("VIETNAM INFRASTRUCTURE NEWS PIPELINE")
    print(f"Started: {datetime.now()}")
    print("=" * 70)
    
    # Ensure output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {OUTPUT_DIR}")
    
    # Step 1: Load existing articles
    print("\n[Step 1] Loading existing articles...")
    existing_articles = load_articles_from_excel()
    print(f"Existing articles: {len(existing_articles)}")
    
    # Step 2: Collect new articles (may fail, that's OK)
    new_articles = collect_new_articles()
    
    # Step 4: Combine
    all_articles = existing_articles + new_articles
    print(f"\n[Step 4] Total articles: {len(all_articles)}")
    
    # Step 5: Create dashboard (MUST succeed)
    dashboard_ok = create_dashboard(all_articles)
    
    # Step 6: Verify
    print("\n[Step 6] Verifying outputs...")
    index_file = OUTPUT_DIR / "index.html"
    dashboard_file = OUTPUT_DIR / "vietnam_dashboard.html"
    
    if index_file.exists():
        print(f"✓ index.html exists ({index_file.stat().st_size} bytes)")
    else:
        print(f"✗ index.html NOT found")
    
    if dashboard_file.exists():
        print(f"✓ vietnam_dashboard.html exists ({dashboard_file.stat().st_size} bytes)")
    else:
        print(f"✗ vietnam_dashboard.html NOT found")
    
    # List all output files
    print("\nOutput directory contents:")
    for f in OUTPUT_DIR.iterdir():
        print(f"  {f.name} ({f.stat().st_size} bytes)")
    
    # Step 7: Notifications (optional)
    print("\n[Step 7] Notifications (skipping)...")
    
    print("\n" + "=" * 70)
    print("PIPELINE COMPLETE")
    print(f"Total: {len(all_articles)} | New: {len(new_articles)}")
    print(f"Dashboard: {'OK' if dashboard_ok else 'FAILED'}")
    print("=" * 70)


if __name__ == "__main__":
    main()
