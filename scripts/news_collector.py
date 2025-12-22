"""
Vietnam Infrastructure News Collector
Collects news from existing 310+ sources in database
Collection period: Yesterday 6PM to Today 6PM (Vietnam time)
"""
import asyncio
import aiohttp
import feedparser
import json
import logging
import re
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from bs4 import BeautifulSoup
import sys
sys.path.append(str(Path(__file__).parent.parent))

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

try:
    import pytz
    PYTZ_AVAILABLE = True
    VIETNAM_TZ = pytz.timezone('Asia/Ho_Chi_Minh')
except ImportError:
    PYTZ_AVAILABLE = False
    VIETNAM_TZ = None

from config.settings import DATA_DIR, OUTPUT_DIR

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent
EXISTING_DB_FILENAME = "Vietnam_Infra_News_Database_Final.xlsx"

PROVINCES = [
    "Hanoi", "Ho Chi Minh City", "Da Nang", "Hai Phong", "Can Tho",
    "Binh Duong", "Dong Nai", "Ba Ria-Vung Tau", "Long An", "Quang Ninh",
    "Bac Ninh", "Hai Duong", "Hung Yen", "Thai Nguyen", "Vinh Phuc",
    "Quang Nam", "Khanh Hoa", "Lam Dong", "Binh Thuan", "Ninh Thuan",
    "Thua Thien Hue", "Nghe An", "Thanh Hoa", "Nam Dinh", "Ninh Binh",
    "Phu Tho", "Bac Giang", "Lang Son", "Cao Bang", "Ha Giang",
    "Lao Cai", "Yen Bai", "Son La", "Dien Bien", "Lai Chau",
    "Hoa Binh", "Ha Nam", "Thai Binh", "Quang Binh", "Quang Tri",
    "Kon Tum", "Gia Lai", "Dak Lak", "Dak Nong", "Binh Phuoc",
    "Tay Ninh", "Ben Tre", "Tra Vinh", "Vinh Long", "Dong Thap",
    "An Giang", "Kien Giang", "Hau Giang", "Soc Trang", "Bac Lieu",
    "Ca Mau", "Phu Yen", "Binh Dinh", "Vietnam"
]

SECTOR_KEYWORDS = {
    "Oil & Gas": ["oil exploration", "gas field", "upstream", "petroleum", "offshore drilling", "lng terminal", "refinery", "oil and gas", "natural gas", "gas pipeline", "oil price", "crude oil", "petrochemical"],
    "Solid Waste": ["waste-to-energy", "solid waste", "landfill", "incineration", "recycling", "circular economy", "wte", "garbage", "municipal waste"],
    "Waste Water": ["wastewater", "waste water", "wwtp", "sewage", "water treatment plant", "sewerage", "effluent", "sludge"],
    "Water Supply/Drainage": ["clean water", "water supply", "reservoir", "potable water", "tap water", "drinking water", "water infrastructure"],
    "Power": ["power plant", "electricity", "lng power", "gas-to-power", "thermal power", "solar", "wind", "renewable", "hydropower", "pdp8"],
    "Industrial Parks": ["industrial park", "industrial zone", "fdi", "economic zone", "manufacturing zone"],
    "Smart City": ["smart city", "urban development", "digital transformation", "city planning", "urban area"],
}

AREA_BY_SECTOR = {
    "Oil & Gas": "Energy Develop.",
    "Solid Waste": "Environment",
    "Waste Water": "Environment", 
    "Water Supply/Drainage": "Environment",
    "Power": "Energy Develop.",
    "Industrial Parks": "Urban Develop.",
    "Smart City": "Urban Develop.",
}

SEARCH_KEYWORDS = [
    "Vietnam wastewater treatment plant",
    "Vietnam solid waste management",
    "Vietnam water supply project",
    "Vietnam power plant project",
    "Vietnam LNG power",
    "Vietnam solar wind energy",
    "Vietnam industrial park FDI",
    "Vietnam smart city development",
    "Vietnam infrastructure investment",
    "Vietnam environmental project",
]

DEFAULT_RSS_FEEDS = {
    "VnExpress": "https://vnexpress.net/rss/kinh-doanh.rss",
    "VnExpress English": "https://e.vnexpress.net/rss/news.rss",
    "Tuoi Tre": "https://tuoitre.vn/rss/kinh-doanh.rss",
    "VietnamPlus": "https://www.vietnamplus.vn/rss/kinhte.rss",
    "VietnamNews": "https://vietnamnews.vn/rss/economy.rss",
    "VnEconomy": "https://vneconomy.vn/rss/dau-tu.rss",
}


def get_collection_time_range():
    """Get collection time range: Yesterday 6PM to Today 6PM (Vietnam time)"""
    if PYTZ_AVAILABLE and VIETNAM_TZ:
        now = datetime.now(VIETNAM_TZ)
    else:
        now = datetime.utcnow() + timedelta(hours=7)
    
    today_6pm = now.replace(hour=18, minute=0, second=0, microsecond=0)
    yesterday_6pm = today_6pm - timedelta(days=1)
    
    logger.info(f"Collection period: {yesterday_6pm.strftime('%Y-%m-%d %H:%M')} to {today_6pm.strftime('%Y-%m-%d %H:%M')} (Vietnam time)")
    
    return yesterday_6pm, today_6pm


def find_existing_database():
    possible_paths = [
        PROJECT_ROOT / "data" / EXISTING_DB_FILENAME,
        PROJECT_ROOT / EXISTING_DB_FILENAME,
        Path("/home/runner/work/vietnam-infra-news/vietnam-infra-news/data") / EXISTING_DB_FILENAME,
        Path("/home/runner/work/vietnam-infra-news/vietnam-infra-news") / EXISTING_DB_FILENAME,
        DATA_DIR / EXISTING_DB_FILENAME,
        Path(os.getcwd()) / "data" / EXISTING_DB_FILENAME,
        Path(os.getcwd()) / EXISTING_DB_FILENAME,
    ]
    
    for path in possible_paths:
        if path.exists():
            logger.info(f"Found existing database at: {path}")
            return path
    
    logger.warning("Existing database not found")
    return None


def load_sources_from_excel():
    if not PANDAS_AVAILABLE:
        logger.warning("pandas not available, using default sources")
        return []
    
    db_path = find_existing_database()
    if not db_path:
        return []
    
    try:
        xl = pd.ExcelFile(db_path)
        if "Source" not in xl.sheet_names:
            logger.warning("Source sheet not found in database")
            return []
        
        df = pd.read_excel(db_path, sheet_name="Source")
        sources = []
        
        for _, row in df.iterrows():
            domain = str(row.get("Domain", "")) if pd.notna(row.get("Domain")) else ""
            url = str(row.get("URL", "")) if pd.notna(row.get("URL")) else ""
            source_type = str(row.get("Type", "")) if pd.notna(row.get("Type")) else ""
            status = str(row.get("Status", "")) if pd.notna(row.get("Status")) else ""
            
            if domain and status.lower() in ["accessible", "active", ""]:
                sources.append({
                    "domain": domain,
                    "url": url,
                    "type": source_type,
                })
        
        logger.info(f"Loaded {len(sources)} sources from database")
        return sources
    
    except Exception as e:
        logger.error(f"Error loading sources from Excel: {e}")
        return []


class NewsCollector:
    def __init__(self):
        self.collected_news = []
        self.session = None
        self.existing_sources = load_sources_from_excel()
        self.start_time, self.end_time = get_collection_time_range()
        logger.info(f"Initialized with {len(self.existing_sources)} sources from database")
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def fetch_url(self, url):
        try:
            async with self.session.get(url, ssl=False) as response:
                if response.status == 200:
                    return await response.text()
        except Exception as e:
            logger.debug(f"Error fetching {url}: {e}")
        return None
    
    def _is_within_time_range(self, pub_date_str):
        """Check if article is within collection time range"""
        if not pub_date_str:
            return True
        
        try:
            pub_date = self._parse_date_to_datetime(pub_date_str)
            if pub_date is None:
                return True
            
            if PYTZ_AVAILABLE and VIETNAM_TZ:
                if pub_date.tzinfo is None:
                    pub_date = VIETNAM_TZ.localize(pub_date)
                start_aware = self.start_time
                end_aware = self.end_time
            else:
                start_aware = self.start_time
                end_aware = self.end_time
                if hasattr(pub_date, 'replace'):
                    pub_date = pub_date.replace(tzinfo=None)
                    start_aware = start_aware.replace(tzinfo=None) if hasattr(start_aware, 'replace') else start_aware
                    end_aware = end_aware.replace(tzinfo=None) if hasattr(end_aware, 'replace') else end_aware
            
            return start_aware <= pub_date <= end_aware
        except:
            return True
    
    def _parse_date_to_datetime(self, date_str):
        """Parse date string to datetime object"""
        if not date_str:
            return None
        
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_str)
        except:
            pass
        
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(str(date_str)[:19], fmt)
            except:
                continue
        
        return None
    
    async def collect_from_rss(self, source_name, feed_url):
        articles = []
        
        try:
            content = await self.fetch_url(feed_url)
            if not content:
                return articles
            
            feed = feedparser.parse(content)
            
            for entry in feed.entries[:30]:
                pub_date = entry.get("published", "")
                
                if not self._is_within_time_range(pub_date):
                    continue
                
                article = {
                    "id": hash(entry.link) % 10**8,
                    "title": entry.title,
                    "url": entry.link,
                    "source": source_name,
                    "published": self._parse_date(pub_date),
                    "summary": self._clean_html(entry.get("summary", "")),
                }
                
                if self._is_infrastructure_related(article):
                    sector, area = self._classify_article(article)
                    province = self._extract_province(article)
                    
                    article["area"] = area
                    article["sector"] = sector
                    article["province"] = province
                    
                    articles.append(article)
            
            logger.info(f"RSS {source_name}: {len(articles)} infrastructure articles (in time range)")
            
        except Exception as e:
            logger.error(f"RSS error {feed_url}: {e}")
        
        return articles
    
    async def search_source_domain(self, source, keywords):
        articles = []
        domain = source.get("domain", "")
        
        if not domain:
            return articles
        
        search_patterns = [
            f"https://{domain}/search?q=",
            f"https://{domain}/tim-kiem?q=",
            f"https://www.{domain}/search?q=",
            f"https://{domain}/?s=",
        ]
        
        for keyword in keywords[:2]:
            for pattern in search_patterns[:1]:
                try:
                    search_url = pattern + keyword.replace(" ", "+")
                    content = await self.fetch_url(search_url)
                    
                    if content:
                        soup = BeautifulSoup(content, 'html.parser')
                        
                        for link in soup.find_all('a', href=True)[:15]:
                            href = link.get('href', '')
                            title = link.get_text(strip=True)
                            
                            if self._is_valid_article(href, title, domain):
                                full_url = href if href.startswith('http') else f"https://{domain}{href}"
                                
                                article = {
                                    "id": hash(full_url) % 10**8,
                                    "title": title[:200],
                                    "url": full_url,
                                    "source": domain,
                                    "published": datetime.now().strftime("%Y-%m-%d"),
                                    "summary": "",
                                }
                                
                                if self._is_infrastructure_related(article):
                                    sector, area = self._classify_article(article)
                                    province = self._extract_province(article)
                                    
                                    article["area"] = area
                                    article["sector"] = sector
                                    article["province"] = province
                                    
                                    articles.append(article)
                    
                    await asyncio.sleep(0.5)
                    break
                    
                except Exception as e:
                    continue
        
        return articles
    
    async def collect_all(self):
        all_articles = []
        seen_urls = set()
        seen_titles = set()
        
        logger.info("=== Starting News Collection ===")
        logger.info(f"Database sources: {len(self.existing_sources)}")
        logger.info(f"Time range: {self.start_time.strftime('%Y-%m-%d %H:%M')} to {self.end_time.strftime('%Y-%m-%d %H:%M')}")
        
        rss_tasks = []
        for name, url in DEFAULT_RSS_FEEDS.items():
            rss_tasks.append(self.collect_from_rss(name, url))
        
        rss_results = await asyncio.gather(*rss_tasks, return_exceptions=True)
        
        for result in rss_results:
            if isinstance(result, list):
                for article in result:
                    url = article.get("url", "").lower()
                    title = article.get("title", "").lower()[:60]
                    
                    if url not in seen_urls and title not in seen_titles:
                        all_articles.append(article)
                        seen_urls.add(url)
                        seen_titles.add(title)
        
        logger.info(f"After RSS: {len(all_articles)} articles")
        
        priority_domains = [
            "vietnamnews.vn", "e.vnexpress.net", "tuoitrenews.vn",
            "hanoitimes.vn", "vietnamplus.vn", "vneconomy.vn",
            "baodautu.vn", "vnexpress.net", "tuoitre.vn",
            "thanhnien.vn", "dantri.com.vn", "cafef.vn",
        ]
        
        for domain in priority_domains:
            try:
                source = {"domain": domain}
                search_articles = await self.search_source_domain(source, SEARCH_KEYWORDS[:3])
                
                for article in search_articles:
                    url = article.get("url", "").lower()
                    title = article.get("title", "").lower()[:60]
                    
                    if url not in seen_urls and title not in seen_titles:
                        all_articles.append(article)
                        seen_urls.add(url)
                        seen_titles.add(title)
                
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.debug(f"Error searching {domain}: {e}")
        
        logger.info(f"After priority domains: {len(all_articles)} articles")
        
        db_sources_to_search = [s for s in self.existing_sources if s.get("domain") not in priority_domains][:50]
        
        for source in db_sources_to_search:
            try:
                search_articles = await self.search_source_domain(source, SEARCH_KEYWORDS[:2])
                
                for article in search_articles:
                    url = article.get("url", "").lower()
                    title = article.get("title", "").lower()[:60]
                    
                    if url not in seen_urls and title not in seen_titles:
                        all_articles.append(article)
                        seen_urls.add(url)
                        seen_titles.add(title)
                
                await asyncio.sleep(0.3)
            except:
                continue
        
        logger.info(f"=== Collection Complete: {len(all_articles)} total articles ===")
        
        self.collected_news = all_articles
        return all_articles
    
    def _parse_date(self, date_str):
        if not date_str:
            return datetime.now().strftime("%Y-%m-%d")
        
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(date_str)
            return dt.strftime("%Y-%m-%d")
        except:
            pass
        
        try:
            for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S"]:
                try:
                    dt = datetime.strptime(date_str[:19], fmt)
                    return dt.strftime("%Y-%m-%d")
                except:
                    continue
        except:
            pass
        
        return datetime.now().strftime("%Y-%m-%d")
    
    def _clean_html(self, text):
        if not text:
            return ""
        soup = BeautifulSoup(text, 'html.parser')
        return soup.get_text(strip=True)[:500]
    
    def _is_valid_article(self, href, title, domain):
        if not title or len(title) < 20:
            return False
        if not href:
            return False
        
        skip_patterns = ['/tag/', '/category/', '/author/', '/page/', 'javascript:', '#', 'mailto:']
        for pattern in skip_patterns:
            if pattern in href.lower():
                return False
        
        return True
    
    def _is_infrastructure_related(self, article):
        text = (article.get("title", "") + " " + article.get("summary", "")).lower()
        
        infra_keywords = [
            "infrastructure", "wastewater", "waste water", "solid waste", "water treatment",
            "power plant", "electricity", "solar", "wind", "renewable", "lng",
            "industrial park", "fdi", "smart city", "urban development",
            "environment", "pollution", "recycling", "landfill", "sewage",
            "water supply", "drainage", "reservoir", "hydropower",
            "oil", "gas", "petroleum", "refinery",
        ]
        
        return any(kw in text for kw in infra_keywords)
    
    def _classify_article(self, article):
        text = (article.get("title", "") + " " + article.get("summary", "")).lower()
        
        sector_priority = ["Oil & Gas", "Waste Water", "Solid Waste", "Water Supply/Drainage", "Power", "Smart City", "Industrial Parks"]
        
        for sector in sector_priority:
            keywords = SECTOR_KEYWORDS.get(sector, [])
            for keyword in keywords:
                if keyword.lower() in text:
                    return sector, AREA_BY_SECTOR.get(sector, "Environment")
        
        return "Waste Water", "Environment"
    
    def _extract_province(self, article):
        text = (article.get("title", "") + " " + article.get("summary", "")).lower()
        
        for province in PROVINCES:
            if province.lower() in text:
                return province
        
        return "Vietnam"
    
    def save_to_json(self, filename=None):
        if filename is None:
            filename = f"news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        output_path = DATA_DIR / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump({
                "collected_at": datetime.now().isoformat(),
                "collection_period": {
                    "start": self.start_time.strftime("%Y-%m-%d %H:%M"),
                    "end": self.end_time.strftime("%Y-%m-%d %H:%M")
                },
                "total": len(self.collected_news),
                "articles": self.collected_news
            }, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved {len(self.collected_news)} articles to {output_path}")
        return str(output_path)


async def collect_news():
    async with NewsCollector() as collector:
        articles = await collector.collect_all()
        return articles


def save_collected_news(articles, filename=None):
    if filename is None:
        filename = f"news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    output_path = DATA_DIR / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            "collected_at": datetime.now().isoformat(),
            "total": len(articles),
            "articles": articles
        }, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Saved {len(articles)} articles to {output_path}")
    return str(output_path)


def main():
    articles = asyncio.run(collect_news())
    
    if articles:
        save_collected_news(articles)
        
        print(f"\n=== Collection Summary ===")
        print(f"Total articles: {len(articles)}")
        
        from collections import Counter
        areas = Counter(a.get("area", "") for a in articles)
        sectors = Counter(a.get("sector", "") for a in articles)
        
        print(f"\nBy Area:")
        for area, count in areas.most_common():
            print(f"  {area}: {count}")
        
        print(f"\nBy Sector:")
        for sector, count in sectors.most_common():
            print(f"  {sector}: {count}")
    else:
        print("No articles collected")


if __name__ == "__main__":
    main()
