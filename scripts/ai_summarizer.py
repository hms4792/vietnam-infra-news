#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News - AI Summarizer
Generates summaries and translations using Claude API
"""

import sqlite3
import logging
import time
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anthropic import Anthropic
from config.settings import (
    ANTHROPIC_API_KEY,
    DATABASE_PATH,
    SUMMARIZATION_PROMPT_TEMPLATE,
    TRANSLATION_PROMPT_TEMPLATE
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AISummarizer:
    """AI-powered article summarizer and translator"""
    
    def __init__(self, db_path=DATABASE_PATH, api_key=None):
        self.db_path = db_path
        self.api_key = api_key or ANTHROPIC_API_KEY
        
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
        
        self.client = Anthropic(api_key=self.api_key)
        logger.info("AI Summarizer initialized")
    
    def _generate_summary(self, title, content, sector, language):
        """Generate summary in specified language"""
        
        try:
            prompt = SUMMARIZATION_PROMPT_TEMPLATE.format(
                title=title,
                sector=sector,
                content=content[:2000],  # First 2000 chars
                language=language
            )
            
            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=300,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            summary = message.content[0].text.strip()
            logger.info(f"Generated {language} summary: {summary[:50]}...")
            return summary
            
        except Exception as e:
            logger.error(f"Error generating {language} summary: {e}")
            return f"{sector} infrastructure project in Vietnam. {title}"
    
    def _translate_title_to_english(self, vietnamese_title):
        """Translate Vietnamese title to English"""
        
        try:
            prompt = TRANSLATION_PROMPT_TEMPLATE.format(title=vietnamese_title)
            
            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=200,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            translation = message.content[0].text.strip()
            logger.info(f"Translated: {translation}")
            return translation
            
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return vietnamese_title
    
    def summarize_articles(self, limit=None):
        """Summarize and translate articles (including Vietnamese title translation)"""
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        query = """
            SELECT id, title, content, sector, source_url
            FROM news_articles
            WHERE (summary_ko IS NULL OR summary_en IS NULL OR summary_vi IS NULL
                   OR title_en IS NULL)
            ORDER BY collection_date DESC
        """
        
        if limit:
            query += f" LIMIT {limit}"
        
        cursor.execute(query)
        articles = cursor.fetchall()
        
        logger.info(f"Found {len(articles)} articles to process")
        
        for idx, (article_id, title, content, sector, url) in enumerate(articles, 1):
            logger.info(f"\nProcessing {idx}/{len(articles)}: {title[:50]}...")
            
            try:
                # 1. Detect Vietnamese and translate title to English
                has_vietnamese = any(ord(c) > 127 for c in title)
                
                if has_vietnamese:
                    logger.info("Translating Vietnamese title to English...")
                    title_en = self._translate_title_to_english(title)
                else:
                    title_en = title
                
                # 2. Generate summaries in 3 languages
                summary_ko = self._generate_summary(title_en, content, sector, "Korean")
                time.sleep(1)
                
                summary_en = self._generate_summary(title_en, content, sector, "English")
                time.sleep(1)
                
                summary_vi = self._generate_summary(title_en, content, sector, "Vietnamese")
                time.sleep(1)
                
                # 3. Update database
                cursor.execute("""
                    UPDATE news_articles
                    SET title_en = ?, title_ko = ?, title_vi = ?,
                        summary_ko = ?, summary_en = ?, summary_vi = ?
                    WHERE id = ?
                """, (title_en, title_en, title, summary_ko, summary_en, summary_vi, article_id))
                
                conn.commit()
                logger.info(f"✓ Updated article {article_id}")
                
            except Exception as e:
                logger.error(f"Error processing article {article_id}: {e}")
        
        conn.close()
        logger.info(f"\n✓ Summarization complete: {len(articles)} articles processed")
        return len(articles)
    
    def get_statistics(self):
        """Get summarization statistics"""
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM news_articles")
        total = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*) FROM news_articles 
            WHERE summary_ko IS NOT NULL AND summary_en IS NOT NULL
        """)
        summarized = cursor.fetchone()[0]
        
        cursor.execute("""
            SELECT COUNT(*) FROM news_articles 
            WHERE title_en IS NOT NULL
        """)
        translated = cursor.fetchone()[0]
        
        conn.close()
        
        stats = {
            'total_articles': total,
            'summarized': summarized,
            'translated': translated,
            'pending': total - summarized
        }
        
        logger.info(f"Statistics: {stats}")
        return stats


def main():
    """Main execution"""
    
    import argparse
    
    parser = argparse.ArgumentParser(description='AI Summarizer for Vietnam Infrastructure News')
    parser.add_argument('--limit', type=int, help='Limit number of articles to process')
    parser.add_argument('--stats', action='store_true', help='Show statistics only')
    
    args = parser.parse_args()
    
    try:
        summarizer = AISummarizer()
        
        if args.stats:
            stats = summarizer.get_statistics()
            print("\nSummarization Statistics:")
            print(f"  Total articles: {stats['total_articles']}")
            print(f"  Summarized: {stats['summarized']}")
            print(f"  Translated: {stats['translated']}")
            print(f"  Pending: {stats['pending']}")
        else:
            processed = summarizer.summarize_articles(limit=args.limit)
            print(f"\n✓ Successfully processed {processed} articles")
            
    except Exception as e:
        logger.error(f"Error in main: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
