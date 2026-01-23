"""
Vietnam Infrastructure News Pipeline - Main Entry Point
Orchestrates the entire pipeline: collect -> summarize -> update -> notify
"""
import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import DATA_DIR, OUTPUT_DIR, LOG_FILE
from scripts.news_collector import NewsCollector
from scripts.ai_summarizer import AISummarizer, load_articles, save_articles
from scripts.dashboard_updater import OutputGenerator, load_articles as load_for_dashboard
from scripts.notifier import NotificationManager, load_latest_articles

# Setup logging
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class Pipeline:
    """Main pipeline orchestrator"""
    
    def __init__(self):
        self.collector = None
        self.summarizer = AISummarizer()
        self.output_generator = OutputGenerator()
        self.notification_manager = NotificationManager()
        
        self.articles = []
        self.outputs = {}
    
    async def run_collection(self) -> int:
        """Step 1: Collect news from sources"""
        logger.info("=" * 50)
        logger.info("STEP 1: News Collection")
        logger.info("=" * 50)
        
        # In the news collection step
    async with NewsCollector() as collector:
        articles = await collector.collect_all()
        source_check_results = collector.get_source_check_results()

       # Pass to dashboard updater
    excel_path, all_articles = self.excel_db.update(processed_articles, source_check_results)
            
            # Save raw collection
            collector.save_to_json(f"news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        
        logger.info(f"Collected {len(self.articles)} articles")
        return len(self.articles)
    
    async def run_summarization(self) -> int:
        """Step 2: AI summarization"""
        logger.info("=" * 50)
        logger.info("STEP 2: AI Summarization")
        logger.info("=" * 50)
        
        if not self.articles:
            # Load from file
            data_files = sorted(DATA_DIR.glob("news_*.json"), reverse=True)
            if data_files:
                self.articles = load_articles(str(data_files[0]))
        
        if not self.articles:
            logger.warning("No articles to summarize")
            return 0
        
        # Process with AI
        self.articles = await self.summarizer.summarize_batch(self.articles)
        
        # Save processed
        save_articles(
            self.articles, 
            str(DATA_DIR / f"processed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        )
        
        processed_count = sum(1 for a in self.articles if a.get("ai_processed"))
        logger.info(f"AI processed {processed_count}/{len(self.articles)} articles")
        return processed_count
    
    def run_output_generation(self) -> dict:
        """Step 3: Generate outputs (HTML, Excel, JSON)"""
        logger.info("=" * 50)
        logger.info("STEP 3: Output Generation")
        logger.info("=" * 50)
        
        if not self.articles:
            self.articles = load_for_dashboard()
        
        if not self.articles:
            logger.warning("No articles for output generation")
            return {}
        
        self.outputs = self.output_generator.generate_all(self.articles)
        
        for output_type, path in self.outputs.items():
            if path:
                logger.info(f"Generated {output_type}: {path}")
        
        return self.outputs
    
    async def run_notifications(self, dashboard_url: str = "") -> dict:
        """Step 4: Send notifications"""
        logger.info("=" * 50)
        logger.info("STEP 4: Notifications")
        logger.info("=" * 50)
        
        if not self.articles:
            self.articles = load_latest_articles()
        
        if not self.articles:
            logger.warning("No articles for notifications")
            return {}
        
        results = await self.notification_manager.send_all(
            self.articles, 
            dashboard_url, 
            "ko"
        )
        
        for channel, success in results.items():
            status = "sent" if success else "failed/not configured"
            logger.info(f"{channel}: {status}")
        
        return results
    
    async def run_full_pipeline(self, dashboard_url: str = "") -> dict:
        """Run complete pipeline"""
        start_time = datetime.now()
        logger.info("=" * 60)
        logger.info("VIETNAM INFRASTRUCTURE NEWS PIPELINE - STARTING")
        logger.info(f"Start Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("=" * 60)
        
        results = {
            "start_time": start_time.isoformat(),
            "collection": {"count": 0, "status": "pending"},
            "summarization": {"count": 0, "status": "pending"},
            "outputs": {"files": [], "status": "pending"},
            "notifications": {"results": {}, "status": "pending"},
        }
        
        try:
            # Step 1: Collection
            count = await self.run_collection()
            results["collection"] = {"count": count, "status": "success"}
            
            # Step 2: Summarization
            processed = await self.run_summarization()
            results["summarization"] = {"count": processed, "status": "success"}
            
            # Step 3: Output Generation
            outputs = self.run_output_generation()
            results["outputs"] = {
                "files": list(outputs.keys()),
                "paths": outputs,
                "status": "success"
            }
            
            # Step 4: Notifications
            notif_results = await self.run_notifications(dashboard_url)
            results["notifications"] = {
                "results": notif_results,
                "status": "success"
            }
            
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            results["error"] = str(e)
        
        # Summary
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        results["end_time"] = end_time.isoformat()
        results["duration_seconds"] = duration
        
        logger.info("=" * 60)
        logger.info("PIPELINE COMPLETE")
        logger.info(f"Duration: {duration:.1f} seconds")
        logger.info(f"Articles Collected: {results['collection']['count']}")
        logger.info(f"Articles Processed: {results['summarization']['count']}")
        logger.info(f"Outputs Generated: {len(results['outputs'].get('files', []))}")
        logger.info("=" * 60)
        
        # Save run results
        results_file = DATA_DIR / f"run_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        return results


async def main():
    """Main entry point with CLI arguments"""
    parser = argparse.ArgumentParser(
        description="Vietnam Infrastructure News Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --full                    # Run complete pipeline
  python main.py --collect                 # Only collect news
  python main.py --summarize               # Only run AI summarization
  python main.py --output                  # Only generate outputs
  python main.py --notify                  # Only send notifications
  python main.py --full --dashboard-url https://example.com/dashboard
        """
    )
    
    parser.add_argument('--full', action='store_true', help='Run full pipeline')
    parser.add_argument('--collect', action='store_true', help='Run news collection only')
    parser.add_argument('--summarize', action='store_true', help='Run AI summarization only')
    parser.add_argument('--output', action='store_true', help='Generate outputs only')
    parser.add_argument('--notify', action='store_true', help='Send notifications only')
    parser.add_argument('--dashboard-url', type=str, default='', help='Dashboard URL for notifications')
    
    args = parser.parse_args()
    
    pipeline = Pipeline()
    
    if args.full or not any([args.collect, args.summarize, args.output, args.notify]):
        # Run full pipeline by default
        await pipeline.run_full_pipeline(args.dashboard_url)
    else:
        if args.collect:
            await pipeline.run_collection()
        
        if args.summarize:
            await pipeline.run_summarization()
        
        if args.output:
            pipeline.run_output_generation()
        
        if args.notify:
            await pipeline.run_notifications(args.dashboard_url)


if __name__ == "__main__":
    asyncio.run(main())
