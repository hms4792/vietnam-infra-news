#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News Collector - Fixed for VnExpress
Handles JavaScript-rendered content
"""

import requests
from bs4 import BeautifulSoup
import sqlite3
from datetime import datetime, timedelta
import re
import logging
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import (
    SECTOR_KEYWORDS,
    URL_BLACKLIST_PATTERNS,
    URL_NEWS_PATTERNS,
    RSS_FEEDS,
    DATABASE_PATH
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ImprovedNewsCollector:
    """개선된 뉴스 수집기 - VnExpress 대응"""
    
    def __init__(self, db_path=DATABASE_PATH):
        self.db_path = db_path
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
        }
        self._init_database()
    
    def _init_database(self):
        """데이터베이스 초기화"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS news_articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                title_ko TEXT,
                title_en TEXT,
                title_vi TEXT,
                source_url TEXT UNIQUE NOT NULL,
                source_name TEXT,
                sector TEXT,
                area TEXT,
                province TEXT,
                collection_date TEXT,
                article_date TEXT,
                summary_ko TEXT,
                summary_en TEXT,
                summary_vi TEXT,
                content TEXT,
                validated BOOLEAN DEFAULT 0
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info(f"Database initialized at {self.db_path}")
    
    def extract_content_vnexpress(self, soup, url):
        """VnExpress 전용 본문 추출"""
        
        # 방법 1: article-content 클래스
        content_div = soup.find('div', class_='article-content')
        if content_div:
            paragraphs = content_div.find_all('p', class_='Normal')
            if paragraphs:
                text = ' '.join([p.get_text(strip=True) for p in paragraphs])
                if len(text) > 100:
                    logger.info(f"Content extracted via article-content: {len(text)} chars")
                    return text
        
        # 방법 2: fck_detail 클래스 (이전 버전)
        content_div = soup.find('div', class_='fck_detail')
        if content_div:
            paragraphs = content_div.find_all('p')
            if paragraphs:
                text = ' '.join([p.get_text(strip=True) for p in paragraphs])
                if len(text) > 100:
                    logger.info(f"Content extracted via fck_detail: {len(text)} chars")
                    return text
        
        # 방법 3: article 태그 내 모든 p 태그
        article = soup.find('article')
        if article:
            paragraphs = article.find_all('p')
            text = ' '.join([p.get_text(strip=True) for p in paragraphs 
                           if p.get_text(strip=True) and len(p.get_text(strip=True)) > 20])
            if len(text) > 100:
                logger.info(f"Content extracted via article tag: {len(text)} chars")
                return text
        
        # 방법 4: description meta 태그
        meta_desc = soup.find('meta', property='og:description')
        if meta_desc and meta_desc.get('content'):
            desc = meta_desc['content']
            if len(desc) > 50:
                logger.info(f"Using meta description as content: {len(desc)} chars")
                return desc
        
        logger.warning(f"Could not extract content from {url}")
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
        content_selectors = [
            '.article-content', '.post-content', '.entry-content',
            '.content', '.main-content', '.article-body',
            '.detail-content', '.news-content'
        ]
        
        for selector in content_selectors:
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
        """본문 추출 - 사이트별 처리"""
        
        # VnExpress 전용 처리
        if 'vnexpress.net' in url.lower():
            return self.extract_content_vnexpress(soup, url)
        
        # 일반 사이트
        return self.extract_content_generic(soup)
    
    def extract_title(self, soup, url):
        """개선된 제목 추출"""
        
        # 1순위: og:title
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            title = og_title['content'].strip()
            if len(title) > 10:
                return title
        
        # 2순위: article h1
        article_h1 = soup.select_one('article h1, .article h1, .post h1')
        if article_h1:
            title = article_h1.get_text().strip()
            if len(title) > 10:
                return title
        
        # 3순위: title 태그
        if soup.title:
            title = soup.title.get_text().strip()
            # 사이트명 제거
            title = re.sub(r'\s*[-|]\s*.*(?:VnExpress|Vietnam|News).*$', '', title, flags=re.IGNORECASE)
            if len(title) > 10:
                return title
        
        logger.warning(f"No valid title found for {url}")
        return None
    
    def classify_sector(self, title, content):
        """섹터 분류 - 완화된 버전"""
        
        if not content or len(content) < 50:
            # 본문이 없으면 제목만으로 판단
            text = title.lower()
        else:
            text = f"{title} {content[:500]}".lower()
        
        # Infrastructure 관련 키워드 (넓게)
        infra_keywords = [
            'infrastructure', 'construction', 'project', 'development',
            'wastewater', 'sewage', 'water supply', 'treatment plant',
            'power plant', 'solar', 'wind', 'energy', 'electricity',
            'railway', 'metro', 'airport', 'highway', 'expressway',
            'industrial park', 'economic zone', 'smart city',
            'investment', 'fdi', 'billion', 'million'
        ]
        
        # 키워드 매칭
        matches = sum(1 for kw in infra_keywords if kw in text)
        
        if matches >= 1:  # 1개 이상 매칭
            # 구체적인 섹터 분류
            sector_priority = [
                ("Oil & Gas", ["oil", "gas", "petroleum", "lng", "refinery"]),
                ("Waste Water", ["wastewater", "sewage", "effluent", "wwtp"]),
                ("Water Supply", ["water supply", "clean water", "drinking water"]),
                ("Solid Waste", ["solid waste", "landfill", "recycling"]),
                ("Power", ["power plant", "solar", "wind", "hydropower", "electricity"]),
                ("Transport", ["railway", "metro", "airport", "highway", "expressway"]),
                ("Industrial Parks", ["industrial park", "economic zone"]),
                ("Smart City", ["smart city", "urban development"]),
                ("Construction", ["construction", "real estate", "housing"])
            ]
            
            for sector, keywords in sector_priority:
                if any(kw in text for kw in keywords):
                    area_mapping = {
                        "Oil & Gas": "Energy Develop.",
                        "Power": "Energy Develop.",
                        "Waste Water": "Environment",
                        "Solid Waste": "Environment",
                        "Water Supply": "Environment",
                        "Industrial Parks": "Urban Develop.",
                        "Smart City": "Urban Develop.",
                        "Transport": "Urban Develop.",
                        "Construction": "Urban Develop."
                    }
                    area = area_mapping.get(sector, "General")
                    logger.info(f"Classified as {sector}")
                    return sector, area
            
            # 기본값: Infrastructure
            logger.info("Classified as Infrastructure (General)")
            return "Infrastructure", "General"
        
        logger.info("No infrastructure match")
        return None, None
    
    def collect_article(self, url, source_name="Unknown"):
        """기사 수집 및 처리"""
        
        logger.info(f"Processing: {url}")
        
        # 1. 이미 수집했는지 확인
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM news_articles WHERE source_url = ?", (url,))
        if cursor.fetchone():
            logger.info(f"Article already exists: {url}")
            conn.close()
            return None
        conn.close()
        
        # 2. 페이지 가져오기
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            time.sleep(1)  # 요청 간격
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 3. 제목 추출
        title = self.extract_title(soup, url)
        if not title:
            logger.warning(f"No valid title for {url}")
            return None
        
        # 4. 본문 추출
        content = self.extract_content(soup, url)
        if len(content) < 50:
            logger.warning(f"Content too short ({len(content)} chars): {url}")
            # 본문이 짧아도 제목으로 섹터 분류 시도
        
        # 5. 날짜 추출 (없어도 진행)
        article_date = datetime.now()  # 기본값
        
        # 6. 섹터 분류
        sector, area = self.classify_sector(title, content)
        if not sector:
            logger.info(f"No sector match for {url}")
            return None
        
        # 7. DB 저장
        article_data = {
            'title': title,
            'source_url': url,
            'source_name': source_name,
            'sector': sector,
            'area': area,
            'province': 'Vietnam',
            'collection_date': datetime.now().isoformat(),
            'article_date': article_date.isoformat(),
            'content': content[:2000] if content else title,
            'validated': 0
        }
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO news_articles 
                (title, source_url, source_name, sector, area, province,
                 collection_date, article_date, content, validated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                article_data['title'],
                article_data['source_url'],
                article_data['source_name'],
                article_data['sector'],
                article_data['area'],
                article_data['province'],
                article_data['collection_date'],
                article_data['article_date'],
                article_data['content'],
                article_data['validated']
            ))
            
            conn.commit()
            article_id = cursor.lastrowid
            conn.close()
            
            logger.info(f"✓ Article saved (ID: {article_id}): {title}")
            return article_data
            
        except Exception as e:
            logger.error(f"Failed to save article: {e}")
            return None
    
    def collect_from_rss(self, hours_back=24):
        """RSS 피드에서 뉴스 수집"""
        
        cutoff_time = datetime.now() - timedelta(hours=hours_back)
        collected_count = 0
        
        logger.info(f"Collecting articles from last {hours_back} hours")
        logger.info(f"Cutoff time: {cutoff_time}")
        
        for source_name, feed_url in RSS_FEEDS.items():
            logger.info(f"\nProcessing feed: {source_name}")
            
            try:
                response = requests.get(feed_url, headers=self.headers, timeout=30)
                soup = BeautifulSoup(response.content, 'xml')
                
                items = soup.find_all('item')
                logger.info(f"Found {len(items)} items in {source_name}")
                
                for item in items[:20]:  # 최근 20개만
                    link = item.find('link')
                    if link:
                        article_url = link.get_text().strip()
                        
                        # 수집
                        result = self.collect_article(article_url, source_name)
                        if result:
                            collected_count += 1
                        
                        time.sleep(2)  # 요청 간격
                
            except Exception as e:
                logger.error(f"Error processing feed {source_name}: {e}")
        
        logger.info(f"\n✓ Collection complete: {collected_count} articles collected")
        return collected_count


def main():
    """메인 실행 함수"""
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--hours-back', type=int, default=24)
    args = parser.parse_args()
    
    collector = ImprovedNewsCollector()
    collected = collector.collect_from_rss(hours_back=args.hours_back)
    
    print(f"\nCollection Summary:")
    print(f"  Articles collected: {collected}")


if __name__ == "__main__":
    main()
