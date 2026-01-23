#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News Collector - Improved Version
URL 필터링, 제목 추출, 섹터 분류 개선
"""

import requests
from bs4 import BeautifulSoup
import sqlite3
from datetime import datetime, timedelta
import re
import logging
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
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
    """개선된 뉴스 수집기"""
    
    def __init__(self, db_path=DATABASE_PATH):
        self.db_path = db_path
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
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
    
    def is_blacklisted_url(self, url):
        """URL이 블랙리스트에 있는지 확인"""
        url_lower = url.lower()
        
        for pattern in URL_BLACKLIST_PATTERNS:
            if re.search(pattern, url_lower):
                logger.info(f"Blacklisted URL: {url} (pattern: {pattern})")
                return True
        
        return False
    
    def is_news_article_url(self, url):
        """URL이 뉴스 기사인지 확인"""
        
        # 블랙리스트 먼저 체크
        if self.is_blacklisted_url(url):
            return False
        
        # 뉴스 패턴 확인
        url_lower = url.lower()
        for pattern in URL_NEWS_PATTERNS:
            if re.search(pattern, url_lower):
                return True
        
        return False
    
    def extract_title(self, soup, url):
        """개선된 제목 추출"""
        
        # 1순위: article 태그 내의 h1
        article_h1 = soup.select_one('article h1, .article h1, .post h1, .entry h1')
        if article_h1:
            title = article_h1.get_text().strip()
            if len(title) > 10:
                return title
        
        # 2순위: og:title 메타 태그
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            title = og_title['content'].strip()
            if len(title) > 10:
                return title
        
        # 3순위: main h1 (네비게이션 제외)
        main_h1 = soup.select_one('main h1, .main-content h1')
        if main_h1:
            title = main_h1.get_text().strip()
            if len(title) > 10:
                return title
        
        # 4순위: 일반 h1 (네비게이션/헤더 제외)
        h1_tags = soup.find_all('h1')
        for h1 in h1_tags:
            parent = h1.find_parent(['nav', 'header', 'aside', 'footer'])
            if not parent:
                title = h1.get_text().strip()
                # 카테고리명 필터링
                category_keywords = [
                    'cooperation-investment', 'investment', 'business',
                    'economy', 'society', 'news', 'home'
                ]
                if title.lower() not in category_keywords and len(title) > 10:
                    return title
        
        # 5순위: title 태그
        if soup.title:
            title = soup.title.get_text().strip()
            # 사이트명 제거
            title = re.sub(r'\s*[-|]\s*.*$', '', title)
            if len(title) > 10:
                return title
        
        logger.warning(f"No valid title found for {url}")
        return None
    
    def extract_date(self, soup):
        """기사 날짜 추출"""
        
        # meta 태그에서 날짜 찾기
        date_metas = [
            ('property', 'article:published_time'),
            ('name', 'publish_date'),
            ('name', 'date'),
            ('property', 'og:published_time')
        ]
        
        for attr, value in date_metas:
            meta = soup.find('meta', {attr: value})
            if meta and meta.get('content'):
                try:
                    date_str = meta['content']
                    return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                except:
                    continue
        
        # time 태그에서 날짜 찾기
        time_tag = soup.find('time')
        if time_tag and time_tag.get('datetime'):
            try:
                return datetime.fromisoformat(time_tag['datetime'].replace('Z', '+00:00'))
            except:
                pass
        
        return None
    
    def extract_content(self, soup):
        """기사 본문 추출"""
        
        # article 태그
        article = soup.find('article')
        if article:
            return article.get_text(strip=True, separator=' ')
        
        # 클래스명으로 찾기
        content_selectors = [
            '.article-content', '.post-content', '.entry-content',
            '.content', '.main-content', '.article-body'
        ]
        
        for selector in content_selectors:
            content = soup.select_one(selector)
            if content:
                return content.get_text(strip=True, separator=' ')
        
        # main 태그
        main = soup.find('main')
        if main:
            return main.get_text(strip=True, separator=' ')
        
        return ""
    
    def classify_sector(self, title, content):
        """개선된 섹터 분류"""
        
        text = f"{title} {content}".lower()
        
        # 일반 투자/정책 기사 필터링
        policy_keywords = [
            'investment policy', 'investment climate', 'doing business',
            'investment guide', 'business climate'
        ]
        
        if any(kw in text for kw in policy_keywords):
            # 구체적인 프로젝트 언급이 없으면 제외
            project_indicators = [
                'construction of', 'project launched', 'plant opened',
                'signed contract', 'awarded', 'inaugurated'
            ]
            if not any(ind in text for ind in project_indicators):
                logger.info("Filtered out: General policy article")
                return None, None
        
        # 섹터별 점수 계산
        sector_scores = {}
        
        # 섹터 우선순위 (Oil & Gas 최우선)
        sector_priority = [
            "Oil & Gas", "Waste Water", "Solid Waste", 
            "Water Supply", "Power", "Industrial Parks",
            "Smart City", "Transport", "Construction"
        ]
        
        for sector in sector_priority:
            keywords = SECTOR_KEYWORDS.get(sector, {})
            score = 0
            
            # Primary keywords (더 높은 점수)
            for kw in keywords.get('primary', []):
                if kw.lower() in text:
                    score += 3
            
            # Secondary keywords (낮은 점수)
            for kw in keywords.get('secondary', []):
                if kw.lower() in text:
                    score += 1
            
            sector_scores[sector] = score
        
        # 최고 점수 섹터
        if sector_scores:
            max_sector = max(sector_scores, key=sector_scores.get)
            max_score = sector_scores[max_sector]
            
            if max_score >= 3:  # 최소 primary keyword 1개 이상
                # Area 매핑
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
                
                area = area_mapping.get(max_sector, "Environment")
                logger.info(f"Classified as {max_sector} (score: {max_score})")
                return max_sector, area
        
        logger.info("No sector match")
        return None, None
    
    def collect_article(self, url, source_name="Unknown"):
        """기사 수집 및 처리"""
        
        logger.info(f"Processing: {url}")
        
        # 1. URL 검증
        if not self.is_news_article_url(url):
            logger.info(f"Rejected URL (not a news article): {url}")
            return None
        
        # 2. 이미 수집했는지 확인
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM news_articles WHERE source_url = ?", (url,))
        if cursor.fetchone():
            logger.info(f"Article already exists: {url}")
            conn.close()
            return None
        conn.close()
        
        # 3. 페이지 가져오기
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # 4. 제목 추출
        title = self.extract_title(soup, url)
        if not title:
            logger.warning(f"No valid title for {url}")
            return None
        
        # 5. 날짜 추출
        article_date = self.extract_date(soup)
        if not article_date:
            logger.warning(f"No publication date for {url}")
            # 날짜 없어도 수집 (현재 날짜로 대체)
            article_date = datetime.now()
        
        # 6. 본문 추출
        content = self.extract_content(soup)
        if len(content) < 200:
            logger.warning(f"Content too short ({len(content)} chars): {url}")
            return None
        
        # 7. 섹터 분류
        sector, area = self.classify_sector(title, content)
        if not sector:
            logger.info(f"No sector match for {url}")
            return None
        
        # 8. DB 저장
        article_data = {
            'title': title,
            'source_url': url,
            'source_name': source_name,
            'sector': sector,
            'area': area,
            'province': 'Vietnam',  # 기본값
            'collection_date': datetime.now().isoformat(),
            'article_date': article_date.isoformat(),
            'content': content[:2000],  # 처음 2000자만
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
                # RSS 파싱은 기존 로직 사용
                # 여기서는 간단하게 처리
                # 실제로는 feedparser 등을 사용
                
                # 예시: 직접 URL에서 링크 추출
                response = requests.get(feed_url, headers=self.headers, timeout=30)
                soup = BeautifulSoup(response.content, 'xml')
                
                items = soup.find_all('item')
                
                for item in items:
                    link = item.find('link')
                    if link:
                        article_url = link.get_text().strip()
                        
                        # 수집
                        result = self.collect_article(article_url, source_name)
                        if result:
                            collected_count += 1
                
            except Exception as e:
                logger.error(f"Error processing feed {source_name}: {e}")
        
        logger.info(f"\n✓ Collection complete: {collected_count} articles collected")
        return collected_count


def main():
    """메인 실행 함수"""
    collector = ImprovedNewsCollector()
    
    # 지난 24시간 기사 수집
    collected = collector.collect_from_rss(hours_back=24)
    
    print(f"\nCollection Summary:")
    print(f"  Articles collected: {collected}")


if __name__ == "__main__":
    main()
