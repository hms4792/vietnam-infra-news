"""
Vietnam Infrastructure News Collector
Collects news from various Vietnamese news sources
"""
import asyncio
import aiohttp
import feedparser
import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
import sys
sys.path.append(str(Path(__file__).parent.parent))

from config.settings import (
    NEWS_SOURCES, SECTOR_KEYWORDS, PROVINCES, PROVINCE_ALIASES,
    DATA_DIR, OUTPUT_DIR
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class NewsCollector:
    """Collects infrastructure news from Vietnamese sources"""
    
    def __init__(self):
        self.collected_news = []
        self.session = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def fetch_url(self, url: str) -> Optional[str]:
        """Fetch content from URL"""
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                logger.warning(f"Failed to fetch {url}: Status {response.status}")
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
        return None
    
    async def collect_from_rss(self, source_name: str, feed_url: str) -> List[Dict]:
        """Collect news from RSS feed"""
        articles = []
        
        try:
            content = await self.fetch_url(feed_url)
            if not content:
                return articles
            
            feed = feedparser.parse(content)
            
            for entry in feed.entries[:20]:  # Limit to 20 per feed
                article = {
                    "id": hash(entry.link) % 10**8,
                    "title": entry.title,
                    "url": entry.link,
                    "source": source_name,
                    "published": self._parse_date(entry.get("published", "")),
                    "summary": entry.get("summary", ""),
                    "content": "",
                }
                
                # Check if infrastructure related
                if self._is_infrastructure_related(article):
                    # Classify article
                    area, sector = self._classify_article(article)
                    province = self._extract_province(article)
                    
                    article["area"] = area
                    article["sector"] = sector
                    article["province"] = province
                    
                    articles.append(article)
            
            logger.info(f"Collected {len(articles)} articles from {source_name} RSS")
            
        except Exception as e:
            logger.error(f"Error parsing RSS {feed_url}: {e}")
        
        return articles
    
    async def collect_from_search(self, source_name: str, keywords: List[str]) -> List[Dict]:
        """Collect news by searching keywords"""
        articles = []
        source_config = NEWS_SOURCES.get(source_name, {})
        search_url = source_config.get("search_url", "")
        
        if not search_url:
            return articles
        
        for keyword in keywords[:3]:  # Limit keywords
            try:
                url = f"{search_url}{keyword}"
                content = await self.fetch_url(url)
                
                if content:
                    soup = BeautifulSoup(content, 'html.parser')
                    # Parse search results (site-specific logic needed)
                    # This is a simplified version
                    
                    for link in soup.find_all('a', href=True)[:10]:
                        href = link.get('href', '')
                        title = link.get_text(strip=True)
                        
                        if title and len(title) > 20 and self._is_valid_article_url(href):
                            article = {
                                "id": hash(href) % 10**8,
                                "title": title,
                                "url": href if href.startswith('http') else source_config.get('base_url', '') + href,
                                "source": source_name,
                                "published": datetime.now().strftime("%Y-%m-%d"),
                                "summary": "",
                                "content": "",
                            }
                            
                            if self._is_infrastructure_related(article):
                                area, sector = self._classify_article(article)
                                province = self._extract_province(article)
                                
                                article["area"] = area
                                article["sector"] = sector
                                article["province"] = province
                                
                                articles.append(article)
                
                await asyncio.sleep(1)  # Rate limiting
                
            except Exception as e:
                logger.error(f"Error searching {source_name} for '{keyword}': {e}")
        
        return articles
    
    def _is_infrastructure_related(self, article: Dict) -> bool:
        """Check if article is infrastructure related"""
        text = f"{article.get('title', '')} {article.get('summary', '')}".lower()
        
        infra_keywords = [
            "infrastructure", "wastewater", "sewage", "solar", "wind", "power plant",
            "industrial park", "smart city", "LNG", "energy", "construction",
            "hạ tầng", "nước thải", "điện", "năng lượng", "khu công nghiệp",
            "đô thị", "xây dựng", "dự án", "đầu tư", "FDI"
        ]
        
        return any(kw in text for kw in infra_keywords)
    
    def _classify_article(self, article: Dict) -> tuple:
        """Classify article into Area and Sector"""
        text = f"{article.get('title', '')} {article.get('summary', '')}".lower()
        
        for area, sectors in SECTOR_KEYWORDS.items():
            for sector, keywords in sectors.items():
                if any(kw.lower() in text for kw in keywords):
                    return area, sector
        
        return "Environment", "Waste Water"  # Default
    
    def _extract_province(self, article: Dict) -> str:
        """Extract province from article"""
        text = f"{article.get('title', '')} {article.get('summary', '')}"
        
        # Check aliases first
        for alias, province in PROVINCE_ALIASES.items():
            if alias.lower() in text.lower():
                return province
        
        # Check province names
        for province in PROVINCES:
            if province.lower() in text.lower():
                return province
        
        return "Vietnam"  # Default
    
    def _parse_date(self, date_str: str) -> str:
        """Parse date string to standard format"""
        if not date_str:
            return datetime.now().strftime("%Y-%m-%d")
        
        try:
            # Try various formats
            for fmt in ["%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"]:
                try:
                    dt = datetime.strptime(date_str[:25], fmt[:len(date_str)])
                    return dt.strftime("%Y-%m-%d")
                except:
                    continue
        except:
            pass
        
        return datetime.now().strftime("%Y-%m-%d")
    
    def _is_valid_article_url(self, url: str) -> bool:
        """Check if URL is a valid article URL"""
        invalid_patterns = [
            '/tag/', '/category/', '/author/', '/page/', 
            '.css', '.js', '.png', '.jpg', '/rss'
        ]
        return not any(p in url.lower() for p in invalid_patterns)
    
    async def collect_all(self) -> List[Dict]:
        """Collect news from all sources"""
        all_articles = []
        
        for source_name, config in NEWS_SOURCES.items():
            logger.info(f"Collecting from {source_name}...")
            
            # Collect from RSS feeds
            for feed_url in config.get("rss_feeds", []):
                articles = await self.collect_from_rss(source_name, feed_url)
                all_articles.extend(articles)
            
            # Collect from search
            keywords = config.get("keywords", [])
            if keywords:
                articles = await self.collect_from_search(source_name, keywords)
                all_articles.extend(articles)
            
            await asyncio.sleep(2)  # Rate limiting between sources
        
        # Remove duplicates based on URL
        seen_urls = set()
        unique_articles = []
        for article in all_articles:
            if article["url"] not in seen_urls:
                seen_urls.add(article["url"])
                unique_articles.append(article)
        
        self.collected_news = unique_articles
        logger.info(f"Total unique articles collected: {len(unique_articles)}")
        
        return unique_articles
    
    def save_to_json(self, filename: str = None) -> str:
        """Save collected news to JSON file"""
        if not filename:
            filename = f"news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        filepath = DATA_DIR / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                "collected_at": datetime.now().isoformat(),
                "total_count": len(self.collected_news),
                "articles": self.collected_news
            }, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved {len(self.collected_news)} articles to {filepath}")
        return str(filepath)
    
    def load_existing_data(self, filepath: str) -> List[Dict]:
        """Load existing news data"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("articles", [])
        except Exception as e:
            logger.error(f"Error loading {filepath}: {e}")
            return []
    
    def merge_with_existing(self, existing_filepath: str) -> List[Dict]:
        """Merge new articles with existing data"""
        existing = self.load_existing_data(existing_filepath)
        existing_urls = {a["url"] for a in existing}
        
        new_articles = [a for a in self.collected_news if a["url"] not in existing_urls]
        merged = new_articles + existing
        
        # Sort by date
        merged.sort(key=lambda x: x.get("published", ""), reverse=True)
        
        logger.info(f"Merged: {len(new_articles)} new + {len(existing)} existing = {len(merged)} total")
        
        self.collected_news = merged
        return merged


async def main():
    """Main function to run news collection"""
    async with NewsCollector() as collector:
        articles = await collector.collect_all()
        
        # Save to JSON
        json_file = collector.save_to_json()
        
        # Print summary
        print(f"\n{'='*50}")
        print(f"News Collection Complete")
        print(f"{'='*50}")
        print(f"Total Articles: {len(articles)}")
        print(f"Saved to: {json_file}")
        
        # Summary by area
        area_counts = {}
        for article in articles:
            area = article.get("area", "Unknown")
            area_counts[area] = area_counts.get(area, 0) + 1
        
        print(f"\nBy Area:")
        for area, count in area_counts.items():
            print(f"  - {area}: {count}")
        
        return articles


if __name__ == "__main__":
    asyncio.run(main())
