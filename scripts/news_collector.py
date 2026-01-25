#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News Collector
Collects news from multiple sources and saves to Excel database
Includes source status logging for troubleshooting
"""

import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import logging
import sys
import os
import time
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import (
    SECTOR_KEYWORDS,
    URL_BLACKLIST_PATTERNS,
    URL_NEWS_PATTERNS,
    RSS_FEEDS,
    DATA_DIR,
    OUTPUT_DIR
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Excel database path
EXCEL_DB_PATH = DATA_DIR / "database" / "Vietnam_Infra_News_Database_Final.xlsx"

# Source status log path
SOURCE_STATUS_PATH = OUTPUT_DIR / "news_sources_status.json"


class NewsCollector:
    """뉴스 수집기 - Excel 데이터베이스에 저장, 소스 상태 로깅"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,vi;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
        self.collected_articles = []
        self.existing_urls = set()
        self.source_status = {}  # Track source accessibility
        self._load_existing_urls()
    
    def _load_existing_urls(self):
        """기존 Excel에서 URL 목록 로드 (중복 방지)"""
        try:
            import openpyxl
            if EXCEL_DB_PATH.exists():
                wb = openpyxl.load_workbook(EXCEL_DB_PATH, read_only=True)
                ws = wb.active
                
                # Find URL column
                headers = [cell.value for cell in ws[1]]
                url_col = None
                for i, h in enumerate(headers):
                    if h and 'URL' in str(h).upper():
                        url_col = i
                        break
                
                if url_col is not None:
                    for row in ws.iter_rows(min_row=2, values_only=True):
                        if row[url_col]:
                            self.existing_urls.add(str(row[url_col]).strip())
                
                wb.close()
                logger.info(f"Loaded {len(self.existing_urls)} existing URLs from Excel")
        except Exception as e:
            logger.error(f"Error loading existing URLs: {e}")
    
    def extract_content_vnexpress(self, soup, url):
        """VnExpress 전용 본문 추출"""
        
        # article-content 클래스
        content_div = soup.find('div', class_='article-content')
        if content_div:
            paragraphs = content_div.find_all('p', class_='Normal')
            if paragraphs:
                text = ' '.join([p.get_text(strip=True) for p in paragraphs])
                if len(text) > 100:
                    return text
        
        # fck_detail 클래스
        content_div = soup.find('div', class_='fck_detail')
        if content_div:
            paragraphs = content_div.find_all('p')
            if paragraphs:
                text = ' '.join([p.get_text(strip=True) for p in paragraphs])
                if len(text) > 100:
                    return text
        
        # article 태그
        article = soup.find('article')
        if article:
            paragraphs = article.find_all('p')
            text = ' '.join([p.get_text(strip=True) for p in paragraphs 
                           if p.get_text(strip=True) and len(p.get_text(strip=True)) > 20])
            if len(text) > 100:
                return text
        
        # meta description
        meta_desc = soup.find('meta', property='og:description')
        if meta_desc and meta_desc.get('content'):
            return meta_desc['content']
        
        return ""
    
    def extract_content_generic(self, soup):
        """일반 사이트 본문 추출"""
        
        # article 태그
        article = soup.find('article')
        if article:
            text = article.get_text(strip=True, separator=' ')
            if len(text) > 100:
                return text
        
        # 클래스명으로 찾기
        selectors = ['.article-content', '.post-content', '.entry-content',
                    '.content', '.main-content', '.article-body']
        
        for selector in selectors:
            content = soup.select_one(selector)
            if content:
                text = content.get_text(strip=True, separator=' ')
                if len(text) > 100:
                    return text
        
        # main 태그
        main = soup.find('main')
        if main:
            text = main.get_text(strip=True, separator=' ')
            if len(text) > 100:
                return text
        
        return ""
    
    def extract_content(self, soup, url):
        """본문 추출"""
        if 'vnexpress.net' in url.lower():
            return self.extract_content_vnexpress(soup, url)
        return self.extract_content_generic(soup)
    
    def extract_title(self, soup, url):
        """제목 추출"""
        
        # og:title
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            title = og_title['content'].strip()
            if len(title) > 10:
                return title
        
        # h1 태그
        h1 = soup.select_one('article h1, .article h1, h1.title, h1')
        if h1:
            title = h1.get_text().strip()
            if len(title) > 10:
                return title
        
        # title 태그
        if soup.title:
            title = soup.title.get_text().strip()
            title = re.sub(r'\s*[-|]\s*.*$', '', title)
            if len(title) > 10:
                return title
        
        return None
    
    def extract_date(self, soup, url):
        """날짜 추출"""
        
        # meta tags
        date_metas = [
            ('meta', {'property': 'article:published_time'}),
            ('meta', {'name': 'pubdate'}),
            ('meta', {'name': 'date'}),
        ]
        
        for tag, attrs in date_metas:
            meta = soup.find(tag, attrs)
            if meta and meta.get('content'):
                try:
                    date_str = meta['content'][:10]
                    return datetime.strptime(date_str, '%Y-%m-%d')
                except:
                    pass
        
        # time 태그
        time_tag = soup.find('time', datetime=True)
        if time_tag:
            try:
                date_str = time_tag['datetime'][:10]
                return datetime.strptime(date_str, '%Y-%m-%d')
            except:
                pass
        
        return datetime.now()
    
    def classify_sector(self, title, content):
        """섹터 분류"""
        
        text = f"{title} {content[:1000] if content else ''}".lower()
        
        # 섹터 우선순위
        sector_keywords = [
            ("Waste Water", ["wastewater", "waste water", "sewage", "nước thải", "xử lý nước thải", "drainage", "effluent", "wwtp"]),
            ("Solid Waste", ["solid waste", "garbage", "landfill", "rác thải", "chất thải rắn", "waste-to-energy", "incineration", "recycling"]),
            ("Water Supply/Drainage", ["water supply", "clean water", "cấp nước", "nước sạch", "water treatment", "drinking water"]),
            ("Power", ["power plant", "electricity", "điện", "nhiệt điện", "solar", "wind power", "hydropower", "thermal power"]),
            ("Oil & Gas", ["oil", "gas", "petroleum", "dầu khí", "lng", "refinery"]),
            ("Smart City", ["smart city", "thành phố thông minh", "digital city", "urban development"]),
            ("Industrial Parks", ["industrial park", "khu công nghiệp", "industrial zone", "economic zone"]),
        ]
        
        for sector, keywords in sector_keywords:
            if any(kw in text for kw in keywords):
                area_map = {
                    "Waste Water": "Environment",
                    "Solid Waste": "Environment",
                    "Water Supply/Drainage": "Environment",
                    "Power": "Energy Develop.",
                    "Oil & Gas": "Energy Develop.",
                    "Smart City": "Urban Develop.",
                    "Industrial Parks": "Urban Develop.",
                }
                return sector, area_map.get(sector, "Environment")
        
        # Infrastructure 일반 키워드
        infra_keywords = ['infrastructure', 'construction', 'project', 'development', 
                         'investment', 'billion', 'million', 'fdi']
        if any(kw in text for kw in infra_keywords):
            return "Infrastructure", "General"
        
        return None, None
    
    def extract_province(self, title, content):
        """지역(Province) 추출"""
        
        text = f"{title} {content[:500] if content else ''}".lower()
        
        provinces = [
            "Ho Chi Minh", "Hanoi", "Da Nang", "Hai Phong", "Can Tho",
            "Binh Duong", "Dong Nai", "Ba Ria-Vung Tau", "Long An",
            "Quang Ninh", "Bac Ninh", "Hai Duong", "Hung Yen",
            "Thai Nguyen", "Vinh Phuc", "Phu Tho", "Nam Dinh",
            "Thanh Hoa", "Nghe An", "Ha Tinh", "Quang Binh",
            "Hue", "Quang Nam", "Quang Ngai", "Binh Dinh",
            "Khanh Hoa", "Ninh Thuan", "Binh Thuan", "Lam Dong",
            "Dak Lak", "Gia Lai", "Kon Tum", "Tay Ninh",
            "Binh Phuoc", "An Giang", "Kien Giang", "Ca Mau",
            "Soc Trang", "Bac Lieu", "Tra Vinh", "Ben Tre", "Vinh Long"
        ]
        
        for province in provinces:
            if province.lower() in text:
                return province
        
        return "Vietnam"
    
    def collect_article(self, url, source_name="Unknown"):
        """기사 수집"""
        
        # 중복 체크
        if url in self.existing_urls:
            logger.debug(f"Already exists: {url}")
            return None
        
        logger.info(f"Collecting: {url}")
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            time.sleep(1)
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 제목
        title = self.extract_title(soup, url)
        if not title:
            logger.warning(f"No title: {url}")
            return None
        
        # 본문
        content = self.extract_content(soup, url)
        
        # 섹터 분류
        sector, area = self.classify_sector(title, content)
        if not sector:
            logger.info(f"No sector match: {url}")
            return None
        
        # 날짜
        article_date = self.extract_date(soup, url)
        
        # 지역
        province = self.extract_province(title, content)
        
        article = {
            "title": title,
            "title_en": "",  # AI 요약에서 채움
            "title_ko": "",
            "summary_vi": content[:500] if content else title,
            "summary_en": "",
            "summary_ko": "",
            "sector": sector,
            "area": area,
            "province": province,
            "source": source_name,
            "url": url,
            "date": article_date.strftime("%Y-%m-%d"),
            "published": article_date.strftime("%Y-%m-%d"),
            "content": content[:2000] if content else ""
        }
        
        self.collected_articles.append(article)
        self.existing_urls.add(url)
        
        logger.info(f"✓ Collected: {title[:50]}...")
        return article
    
    def collect_from_rss(self, hours_back=48):
        """RSS 피드에서 수집 - 소스별 상태 기록"""
        
        logger.info(f"Collecting from RSS feeds (last {hours_back} hours)")
        logger.info(f"Total RSS sources configured: {len(RSS_FEEDS)}")
        
        for source_name, feed_url in RSS_FEEDS.items():
            logger.info(f"\n{'='*50}")
            logger.info(f"Processing: {source_name}")
            logger.info(f"RSS URL: {feed_url}")
            
            source_result = {
                "name": source_name,
                "url": feed_url,
                "status": "unknown",
                "articles_found": 0,
                "articles_collected": 0,
                "error": None,
                "timestamp": datetime.now().isoformat()
            }
            
            try:
                response = requests.get(feed_url, headers=self.headers, timeout=30)
                
                if response.status_code != 200:
                    source_result["status"] = "http_error"
                    source_result["error"] = f"HTTP {response.status_code}"
                    logger.error(f"  ✗ HTTP Error: {response.status_code}")
                    self.source_status[source_name] = source_result
                    continue
                
                # Check if valid RSS/XML
                content_type = response.headers.get('content-type', '').lower()
                content_preview = response.text[:500].lower()
                
                if not ('<rss' in content_preview or '<feed' in content_preview or '<?xml' in content_preview):
                    source_result["status"] = "invalid_rss"
                    source_result["error"] = "Not valid RSS format"
                    logger.error(f"  ✗ Invalid RSS format")
                    self.source_status[source_name] = source_result
                    continue
                
                soup = BeautifulSoup(response.content, 'xml')
                items = soup.find_all('item')
                
                if not items:
                    items = soup.find_all('entry')  # Atom format
                
                source_result["articles_found"] = len(items)
                logger.info(f"  Found {len(items)} items in feed")
                
                if len(items) == 0:
                    source_result["status"] = "empty_feed"
                    source_result["error"] = "No articles in feed"
                    self.source_status[source_name] = source_result
                    continue
                
                source_result["status"] = "success"
                collected_from_source = 0
                
                for item in items[:30]:  # 최근 30개
                    link = item.find('link')
                    if link:
                        # Handle different link formats
                        if link.get('href'):
                            article_url = link.get('href')
                        else:
                            article_url = link.get_text().strip()
                        
                        if article_url:
                            result = self.collect_article(article_url, source_name)
                            if result:
                                collected_from_source += 1
                            time.sleep(2)
                
                source_result["articles_collected"] = collected_from_source
                logger.info(f"  ✓ Collected {collected_from_source} articles from {source_name}")
                
            except requests.exceptions.Timeout:
                source_result["status"] = "timeout"
                source_result["error"] = "Request timed out (30s)"
                logger.error(f"  ✗ Timeout: {source_name}")
            except requests.exceptions.ConnectionError as e:
                source_result["status"] = "connection_error"
                source_result["error"] = f"Connection failed: {str(e)[:100]}"
                logger.error(f"  ✗ Connection Error: {source_name}")
            except Exception as e:
                source_result["status"] = "error"
                source_result["error"] = str(e)[:200]
                logger.error(f"  ✗ Error with {source_name}: {e}")
            
            self.source_status[source_name] = source_result
            time.sleep(1)
        
        # Save source status log
        self._save_source_status()
        
        logger.info(f"\n{'='*50}")
        logger.info(f"✓ Total collected: {len(self.collected_articles)} articles")
        return self.collected_articles
    
    def _save_source_status(self):
        """소스 상태를 JSON 파일로 저장"""
        try:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            
            status_report = {
                "generated_at": datetime.now().isoformat(),
                "total_sources": len(RSS_FEEDS),
                "sources_checked": len(self.source_status),
                "successful_sources": sum(1 for s in self.source_status.values() if s["status"] == "success"),
                "total_articles_collected": len(self.collected_articles),
                "source_details": self.source_status
            }
            
            with open(SOURCE_STATUS_PATH, 'w', encoding='utf-8') as f:
                json.dump(status_report, f, ensure_ascii=False, indent=2)
            
            logger.info(f"Source status saved to: {SOURCE_STATUS_PATH}")
            
            # Also create a readable summary
            summary_path = OUTPUT_DIR / "news_sources_summary.txt"
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write("=" * 60 + "\n")
                f.write("VIETNAM INFRASTRUCTURE NEWS - SOURCE STATUS REPORT\n")
                f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 60 + "\n\n")
                
                f.write(f"Total Sources Configured: {len(RSS_FEEDS)}\n")
                f.write(f"Sources Checked: {len(self.source_status)}\n")
                f.write(f"Successful Sources: {status_report['successful_sources']}\n")
                f.write(f"Total Articles Collected: {len(self.collected_articles)}\n\n")
                
                f.write("-" * 60 + "\n")
                f.write("SUCCESSFUL SOURCES:\n")
                f.write("-" * 60 + "\n")
                for name, status in self.source_status.items():
                    if status["status"] == "success":
                        f.write(f"✓ {name}\n")
                        f.write(f"  URL: {status['url']}\n")
                        f.write(f"  Found: {status['articles_found']}, Collected: {status['articles_collected']}\n\n")
                
                f.write("-" * 60 + "\n")
                f.write("FAILED SOURCES:\n")
                f.write("-" * 60 + "\n")
                for name, status in self.source_status.items():
                    if status["status"] != "success":
                        f.write(f"✗ {name}\n")
                        f.write(f"  URL: {status['url']}\n")
                        f.write(f"  Status: {status['status']}\n")
                        f.write(f"  Error: {status.get('error', 'Unknown')}\n\n")
            
            logger.info(f"Source summary saved to: {summary_path}")
            
        except Exception as e:
            logger.error(f"Error saving source status: {e}")
    
    async def collect_all(self):
        """비동기 인터페이스 (main.py 호환)"""
        return self.collect_from_rss(hours_back=48)
    
    def save_to_excel(self):
        """수집된 기사를 Excel에 저장"""
        
        if not self.collected_articles:
            logger.info("No new articles to save")
            return
        
        try:
            import openpyxl
            from openpyxl.styles import Font, PatternFill
        except ImportError:
            logger.error("openpyxl not installed")
            return
        
        try:
            if EXCEL_DB_PATH.exists():
                wb = openpyxl.load_workbook(EXCEL_DB_PATH)
                ws = wb.active
                start_row = ws.max_row + 1
            else:
                wb = openpyxl.Workbook()
                ws = wb.active
                ws.title = "News Database"
                
                # Headers
                headers = ["No", "Date", "Area", "Business Sector", "Province",
                          "News Tittle", "Summary (EN)", "Summary (KO)", 
                          "Source Name", "Source URL"]
                for col, header in enumerate(headers, 1):
                    cell = ws.cell(row=1, column=col, value=header)
                    cell.font = Font(bold=True)
                start_row = 2
            
            # Add articles
            for i, article in enumerate(self.collected_articles):
                row = start_row + i
                ws.cell(row=row, column=1, value=row - 1)
                ws.cell(row=row, column=2, value=article.get("date", ""))
                ws.cell(row=row, column=3, value=article.get("area", "Environment"))
                ws.cell(row=row, column=4, value=article.get("sector", ""))
                ws.cell(row=row, column=5, value=article.get("province", "Vietnam"))
                ws.cell(row=row, column=6, value=article.get("title", ""))
                ws.cell(row=row, column=7, value=article.get("summary_en", ""))
                ws.cell(row=row, column=8, value=article.get("summary_ko", ""))
                ws.cell(row=row, column=9, value=article.get("source", ""))
                ws.cell(row=row, column=10, value=article.get("url", ""))
            
            # Ensure directory exists
            EXCEL_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
            wb.save(EXCEL_DB_PATH)
            
            logger.info(f"✓ Saved {len(self.collected_articles)} articles to Excel")
            
        except Exception as e:
            logger.error(f"Error saving to Excel: {e}")
            import traceback
            traceback.print_exc()


def main():
    """메인 실행"""
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--hours-back', type=int, default=48)
    args = parser.parse_args()
    
    collector = NewsCollector()
    articles = collector.collect_from_rss(hours_back=args.hours_back)
    
    if articles:
        collector.save_to_excel()
    
    print(f"\nCollection Summary:")
    print(f"  Articles collected: {len(articles)}")


if __name__ == "__main__":
    main()
