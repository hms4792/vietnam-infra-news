"""
Vietnam Infrastructure News Collector
Collects news from existing 310+ sources in database
Collection period: Yesterday 6PM to Today 6PM (Vietnam time)
Tracks source check status for verification
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
    "Oil & Gas": [
        "oil exploration", "gas field", "upstream", "petroleum", "offshore drilling", 
        "lng terminal", "refinery", "oil and gas", "natural gas", "gas pipeline", 
        "oil price", "crude oil", "petrochemical", "oil production", "gas production",
        "petrovietnam", "pvn", "binh son refinery", "nghi son refinery"
    ],
    "Transport": [
        "railway", "high-speed rail", "metro", "subway", "airport", "seaport", 
        "port", "harbor", "terminal", "highway", "expressway", "road construction",
        "bridge", "tunnel", "logistics", "transportation", "train", "rail line",
        "north-south railway", "long thanh airport", "cat lai port", "lach huyen port"
    ],
    "Solid Waste": [
        "waste-to-energy", "solid waste", "landfill", "incineration", "recycling", 
        "circular economy", "wte", "garbage", "municipal waste", "waste treatment",
        "waste management", "rubbish", "trash disposal"
    ],
    "Waste Water": [
        "wastewater treatment", "wastewater plant", "wwtp", "sewage treatment", 
        "water treatment plant", "sewerage system", "effluent treatment", "sludge treatment",
        "drainage system", "sewage plant", "waste water facility"
    ],
    "Water Supply/Drainage": [
        "clean water", "water supply", "reservoir", "potable water", "tap water", 
        "drinking water", "water infrastructure", "water plant", "water project",
        "water distribution", "water network"
    ],
    "Power": [
        "power plant", "electricity generation", "lng power", "gas-to-power", 
        "thermal power", "solar power", "solar farm", "wind power", "wind farm",
        "renewable energy", "hydropower", "pdp8", "power project", "electricity project",
        "solar panel", "wind turbine", "biomass power"
    ],
    "Construction": [
        "construction project", "real estate development", "property development", 
        "housing project", "steel production", "cement production", "building construction",
        "infrastructure project", "mega project", "billion usd investment",
        "vingroup", "novaland", "sun group"
    ],
    "Industrial Parks": [
        "industrial park", "industrial zone", "fdi investment", "economic zone", 
        "manufacturing zone", "factory construction", "manufacturing facility",
        "export processing zone", "hi-tech park", "industrial cluster"
    ],
    "Smart City": [
        "smart city", "urban development project", "digital transformation", 
        "city planning", "urban area development", "new urban area",
        "urban infrastructure", "smart infrastructure"
    ],
}

AREA_BY_SECTOR = {
    "Oil & Gas": "Energy Develop.",
    "Transport": "Urban Develop.",
    "Solid Waste": "Environment",
    "Waste Water": "Environment",
    "Water Supply/Drainage": "Environment",
    "Power": "Energy Develop.",
    "Construction": "Urban Develop.",
    "Industrial Parks": "Urban Develop.",
    "Smart City": "Urban Develop.",
    "Unclassified": "Other",
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
    "Vietnam railway high-speed",
    "Vietnam airport seaport",
    "Vietnam highway expressway",
    "Vietnam construction real estate",
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
                    "status": status,
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
        
        # Source check tracking
        self.source_check_results = {}  # domain -> {checked, success, articles_found, last_checked, error}
        
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

    def _record_source_check(self, domain, success, articles_found=0, error=None):
        """Record the result of checking a source"""
        self.source_check_results[domain] = {
            "checked": True,
            "success": success,
            "articles_found": articles_found,
            "last_checked": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "error": error
        }

    async def fetch_url(self, url):
        try:
            async with self.session.get(url, ssl=False) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    return None
        except Exception as e:
            logger.debug(f"Error fetching {url}: {e}")
            return None

    def _is_within_time_range(self, pub_date_str):
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
        domain = feed_url.split('/')[2].replace('www.', '')
        
        try:
            content = await self.fetch_url(feed_url)
            if not content:
                self._record_source_check(domain, success=False, error="No response")
                return articles
            
            feed = feedparser.parse(content)
            
            for entry in feed.entries[:50]:
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
            
            self._record_source_check(domain, success=True, articles_found=len(articles))
            logger.info(f"RSS {source_name}: {len(articles)} infrastructure articles (in time range)")
            
        except Exception as e:
            self._record_source_check(domain, success=False, error=str(e)[:50])
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
        
        found_any = False
        error_msg = None
        
        for keyword in keywords[:2]:
            for pattern in search_patterns[:1]:
                try:
                    search_url = pattern + keyword.replace(" ", "+")
                    content = await self.fetch_url(search_url)
                    
                    if content:
                        found_any = True
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
                    else:
                        error_msg = "No response"
                    
                    await asyncio.sleep(0.5)
                    break
                    
                except Exception as e:
                    error_msg = str(e)[:50]
                    continue
        
        # Record check result
        self._record_source_check(
            domain, 
            success=found_any, 
            articles_found=len(articles),
            error=error_msg if not found_any else None
        )
        
        return articles

    async def collect_all(self):
        all_articles = []
        seen_urls = set()
        seen_titles = set()
        
        logger.info("=== Starting News Collection ===")
        logger.info(f"Database sources: {len(self.existing_sources)}")
        logger.info(f"Time range: {self.start_time.strftime('%Y-%m-%d %H:%M')} to {self.end_time.strftime('%Y-%m-%d %H:%M')}")
        
        # 1. RSS Feeds
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
        
        # 2. Priority domains
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
        
        # 3. Database sources (ALL sources, not just 50)
        checked_domains = set(priority_domains)
        db_sources_to_search = [s for s in self.existing_sources if s.get("domain") not in checked_domains]
        
        logger.info(f"Checking {len(db_sources_to_search)} additional database sources...")
        
        for i, source in enumerate(db_sources_to_search):
            try:
                search_articles = await self.search_source_domain(source, SEARCH_KEYWORDS[:2])
                
                for article in search_articles:
                    url = article.get("url", "").lower()
                    title = article.get("title", "").lower()[:60]
                    
                    if url not in seen_urls and title not in seen_titles:
                        all_articles.append(article)
                        seen_urls.add(url)
                        seen_titles.add(title)
                
                # Progress log every 50 sources
                if (i + 1) % 50 == 0:
                    logger.info(f"  Checked {i + 1}/{len(db_sources_to_search)} sources, {len(all_articles)} articles so far")
                
                await asyncio.sleep(0.3)
            except:
                continue
        
        logger.info(f"=== Collection Complete: {len(all_articles)} total articles ===")
        logger.info(f"=== Sources checked: {len(self.source_check_results)} ===")
        
        # Log source check summary
        successful = sum(1 for r in self.source_check_results.values() if r['success'])
        failed = sum(1 for r in self.source_check_results.values() if not r['success'])
        with_articles = sum(1 for r in self.source_check_results.values() if r['articles_found'] > 0)
        
        logger.info(f"  - Successful: {successful}")
        logger.info(f"  - Failed: {failed}")
        logger.info(f"  - With articles: {with_articles}")
        
        self.collected_news = all_articles
        return all_articles

    def get_source_check_results(self):
        """Return source check results for updating Source sheet"""
        return self.source_check_results

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
            "environment", "pollution", "recycling", "landfill", "sewage",
            "water supply", "drainage", "reservoir",
            "power plant", "electricity", "solar", "wind", "renewable", "lng",
            "hydropower", "oil", "gas", "petroleum", "refinery", "energy",
            "thermal power", "wind farm", "solar farm",
            "industrial park", "fdi", "smart city", "urban development",
            "real estate", "property", "construction", "housing",
            "railway", "rail", "train", "metro", "subway", "high-speed",
            "airport", "seaport", "port", "harbor", "terminal",
            "highway", "expressway", "road", "bridge", "tunnel",
            "transportation", "transport", "logistics",
            "steel", "cement", "factory", "manufacturing", "plant",
            "project", "investment", "development", "billion", "million usd",
        ]
        
        return any(kw in text for kw in infra_keywords)

    def _classify_article(self, article):
    """Classify article by sector with improved accuracy"""
        title = article.get("title", "").lower()
        summary = article.get("summary", "").lower()
        text = title + " " + summary
        
        # Score-based classification for better accuracy
        sector_scores = {}
        
        for sector, keywords in SECTOR_KEYWORDS.items():
            score = 0
            matched_keywords = []
            for keyword in keywords:
                kw_lower = keyword.lower()
                # Title match = 3 points, Summary match = 1 point
                if kw_lower in title:
                    score += 3
                    matched_keywords.append(keyword)
                elif kw_lower in summary:
                    score += 1
                    matched_keywords.append(keyword)
            
            if score > 0:
                sector_scores[sector] = {
                    "score": score,
                    "keywords": matched_keywords
                }
        
        # If no matches, check for general infrastructure keywords
        if not sector_scores:
            # Default classification based on general context
            general_keywords = {
                "environment": ["Environment", "Waste Water"],
                "energy": ["Energy Develop.", "Power"],
                "urban": ["Urban Develop.", "Smart City"],
                "transport": ["Urban Develop.", "Transport"],
                "construction": ["Urban Develop.", "Construction"],
            }
            
            for key, (area, sector) in [
                ("environment", ("Environment", "Waste Water")),
                ("energy", ("Energy Develop.", "Power")),
                ("urban", ("Urban Develop.", "Smart City")),
                ("transport", ("Urban Develop.", "Transport")),
                ("construct", ("Urban Develop.", "Construction")),
            ]:
                if key in text:
                    return sector, area
            
            # Ultimate fallback - mark as "Unclassified" instead of wrong category
            return "Unclassified", "Other"
        
        # Get highest scoring sector
        best_sector = max(sector_scores.items(), key=lambda x: x[1]["score"])
        sector_name = best_sector[0]
        area = AREA_BY_SECTOR.get(sector_name, "Other")
        
        # Log classification for debugging
        logger.debug(f"Classified '{title[:50]}...' as {sector_name} (score: {best_sector[1]['score']}, keywords: {best_sector[1]['keywords'][:3]})")
        
        return sector_name, area

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
                "articles": self.collected_news,
                "source_check_results": self.source_check_results
            }, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved {len(self.collected_news)} articles to {output_path}")
        return str(output_path)


async def collect_news():
    async with NewsCollector() as collector:
        articles = await collector.collect_all()
        return articles, collector.get_source_check_results()


def save_collected_news(articles, source_results=None, filename=None):
    if filename is None:
        filename = f"news_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    output_path = DATA_DIR / filename
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            "collected_at": datetime.now().isoformat(),
            "total": len(articles),
            "articles": articles,
            "source_check_results": source_results or {}
        }, f, ensure_ascii=False, indent=2)
    
    logger.info(f"Saved {len(articles)} articles to {output_path}")
    return str(output_path)


def main():
    import asyncio
    
    async def run():
        async with NewsCollector() as collector:
            articles = await collector.collect_all()
            source_results = collector.get_source_check_results()
            return articles, source_results
    
    articles, source_results = asyncio.run(run())
    
    if articles:
        save_collected_news(articles, source_results)
        
        print(f"\n=== Collection Summary ===")
        print(f"Total articles: {len(articles)}")
        print(f"Sources checked: {len(source_results)}")
        
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
