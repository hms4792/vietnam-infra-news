#!/usr/bin/env python3
"""
Vietnam Infrastructure News Pipeline - Main Entry Point
Collects news, processes with AI, updates dashboard, sends notifications
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

from config.settings import DATA_DIR, OUTPUT_DIR, DATABASE_PATH
from scripts.news_collector import NewsCollector
from scripts.ai_summarizer import AISummarizer
from scripts.dashboard_updater import DashboardUpdater, ExcelUpdater
from scripts.notifier import NotificationManager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('logs/pipeline.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


def load_existing_articles_from_db() -> list:
    """Load ALL existing articles from SQLite database"""
    import sqlite3
    
    if not DATABASE_PATH.exists():
        logger.warning(f"Database not found: {DATABASE_PATH}")
        return []
    
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                id, title, title_en, title_ko,
                summary_vi, summary_en, summary_ko,
                sector, area, province,
                source_name, source_url,
                article_date, collection_date
            FROM news_articles
            ORDER BY article_date DESC
        """)
        
        articles = []
        for row in cursor.fetchall():
            article = {
                "id": row["id"],
                "title": row["title"] or "",
                "title_en": row["title_en"] or row["title"] or "",
                "title_ko": row["title_ko"] or "",
                "summary_vi": row["summary_vi"] or "",
                "summary_en": row["summary_en"] or "",
                "summary_ko": row["summary_ko"] or "",
                "sector": row["sector"] or "Waste Water",
                "area": row["area"] or "Environment",
                "province": row["province"] or "Vietnam",
                "source": row["source_name"] or "",
                "url": row["source_url"] or "",
                "date": row["article_date"] or row["collection_date"] or "",
                "published": row["article_date"] or row["collection_date"] or ""
            }
            articles.append(article)
        
        conn.close()
        logger.info(f"Loaded {len(articles)} articles from database")
        return articles
        
    except Exception as e:
        logger.error(f"Error loading from database: {e}")
        return []


def load_existing_articles_from_json() -> list:
    """Load existing articles from JSON files as fallback"""
    all_articles = []
    
    # Check for processed files
    json_files = sorted(DATA_DIR.glob("processed_*.json"), reverse=True)
    if not json_files:
        json_files = sorted(DATA_DIR.glob("news_*.json"), reverse=True)
    
    for json_file in json_files[:5]:  # Load from recent files
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                articles = data.get("articles", data if isinstance(data, list) else [])
                all_articles.extend(articles)
        except Exception as e:
            logger.error(f"Error loading {json_file}: {e}")
    
    # Deduplicate by URL
    seen_urls = set()
    unique_articles = []
    for article in all_articles:
        url = article.get("url", article.get("source_url", ""))
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_articles.append(article)
    
    logger.info(f"Loaded {len(unique_articles)} unique articles from JSON files")
    return unique_articles


def save_articles_to_db(articles: list):
    """Save new articles to SQLite database"""
    import sqlite3
    
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Create table if not exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS news_articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            title_en TEXT,
            title_ko TEXT,
            summary_vi TEXT,
            summary_en TEXT,
            summary_ko TEXT,
            sector TEXT,
            area TEXT,
            province TEXT,
            source_name TEXT,
            source_url TEXT UNIQUE,
            article_date TEXT,
            collection_date TEXT
        )
    """)
    
    inserted = 0
    for article in articles:
        try:
            cursor.execute("""
                INSERT OR IGNORE INTO news_articles 
                (title, title_en, title_ko, summary_vi, summary_en, summary_ko,
                 sector, area, province, source_name, source_url, article_date, collection_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                article.get("title", ""),
                article.get("title_en", article.get("summary_en", "")),
                article.get("title_ko", article.get("summary_ko", "")),
                article.get("summary_vi", article.get("title", "")),
                article.get("summary_en", ""),
                article.get("summary_ko", ""),
                article.get("sector", "Waste Water"),
                article.get("area", "Environment"),
                article.get("province", "Vietnam"),
                article.get("source", article.get("source_name", "")),
                article.get("url", article.get("source_url", "")),
                article.get("date", article.get("published", "")),
                datetime.now().strftime("%Y-%m-%d")
            ))
            if cursor.rowcount > 0:
                inserted += 1
        except Exception as e:
            logger.debug(f"Insert error (likely duplicate): {e}")
    
    conn.commit()
    conn.close()
    logger.info(f"Saved {inserted} new articles to database")
    return inserted


async def run_full_pipeline():
    """Run the complete news pipeline"""
    logger.info("="*60)
    logger.info("Starting Vietnam Infrastructure News Pipeline")
    logger.info("="*60)
    
    # Ensure directories exist
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    Path("logs").mkdir(exist_ok=True)
    
    # Step 1: Collect news
    logger.info("Step 1: Collecting news...")
    collector = NewsCollector()
    new_articles = await collector.collect_all()
    logger.info(f"Collected {len(new_articles)} new articles")
    
    # Step 2: AI Summarization (if articles collected)
    if new_articles:
        logger.info("Step 2: AI Summarization...")
        try:
            summarizer = AISummarizer()
            new_articles = await summarizer.process_articles(new_articles)
            logger.info(f"Summarized {len(new_articles)} articles")
        except Exception as e:
            logger.error(f"Summarization error: {e}")
    
    # Step 3: Save new articles to database
    if new_articles:
        logger.info("Step 3: Saving to database...")
        save_articles_to_db(new_articles)
    
    # Step 4: Load ALL articles from database for dashboard
    logger.info("Step 4: Loading all articles for dashboard...")
    all_articles = load_existing_articles_from_db()
    
    if not all_articles:
        # Fallback to JSON files
        all_articles = load_existing_articles_from_json()
    
    logger.info(f"Total articles for dashboard: {len(all_articles)}")
    
    # Step 5: Update Dashboard with ALL articles
    logger.info("Step 5: Updating dashboard...")
    try:
        dashboard = DashboardUpdater()
        dashboard_path = dashboard.update(all_articles)
        logger.info(f"Dashboard updated: {dashboard_path}")
    except Exception as e:
        logger.error(f"Dashboard update error: {e}")
    
    # Step 6: Update Excel
    logger.info("Step 6: Updating Excel...")
    try:
        excel = ExcelUpdater()
        excel_path = excel.update(all_articles)
        logger.info(f"Excel updated: {excel_path}")
    except Exception as e:
        logger.error(f"Excel update error: {e}")
    
    # Step 7: Send notifications (use all articles for context, new for email)
    logger.info("Step 7: Sending notifications...")
    try:
        notifier = NotificationManager()
        # Pass all articles so email shows correct totals
        results = await notifier.send_all(all_articles)
        logger.info(f"Notification results: {results}")
    except Exception as e:
        logger.error(f"Notification error: {e}")
    
    # Summary
    logger.info("="*60)
    logger.info("Pipeline Complete!")
    logger.info(f"  New articles collected: {len(new_articles)}")
    logger.info(f"  Total articles in database: {len(all_articles)}")
    logger.info("="*60)
    
    return {
        "new_articles": len(new_articles),
        "total_articles": len(all_articles)
    }


async def run_notify_only():
    """Send notifications without collecting"""
    logger.info("Running notification only...")
    
    all_articles = load_existing_articles_from_db()
    if not all_articles:
        all_articles = load_existing_articles_from_json()
    
    if not all_articles:
        logger.error("No articles found to notify about")
        return
    
    notifier = NotificationManager()
    results = await notifier.send_all(all_articles)
    logger.info(f"Notification results: {results}")


async def run_dashboard_only():
    """Update dashboard without collecting"""
    logger.info("Updating dashboard only...")
    
    all_articles = load_existing_articles_from_db()
    if not all_articles:
        all_articles = load_existing_articles_from_json()
    
    if not all_articles:
        logger.warning("No articles found for dashboard")
        return
    
    logger.info(f"Updating dashboard with {len(all_articles)} articles")
    
    dashboard = DashboardUpdater()
    dashboard_path = dashboard.update(all_articles)
    logger.info(f"Dashboard updated: {dashboard_path}")
    
    excel = ExcelUpdater()
    excel_path = excel.update(all_articles)
    logger.info(f"Excel updated: {excel_path}")


def main():
    parser = argparse.ArgumentParser(description='Vietnam Infrastructure News Pipeline')
    parser.add_argument('--full', action='store_true', help='Run full pipeline')
    parser.add_argument('--collect', action='store_true', help='Collect news only')
    parser.add_argument('--notify', action='store_true', help='Send notifications only')
    parser.add_argument('--dashboard', action='store_true', help='Update dashboard only')
    
    args = parser.parse_args()
    
    if args.full or not any([args.collect, args.notify, args.dashboard]):
        asyncio.run(run_full_pipeline())
    elif args.notify:
        asyncio.run(run_notify_only())
    elif args.dashboard:
        asyncio.run(run_dashboard_only())
    elif args.collect:
        asyncio.run(run_full_pipeline())


if __name__ == "__main__":
    main()
