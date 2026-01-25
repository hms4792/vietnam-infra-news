#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News - AI Summarizer
Generates summaries and translations using Claude API
Works with article lists (not SQLite database)
"""

import logging
import time
import os
import sys
from datetime import datetime
from typing import List, Dict

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from config.settings import (
    ANTHROPIC_API_KEY,
    SUMMARIZATION_PROMPT_TEMPLATE,
    TRANSLATION_PROMPT_TEMPLATE
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AISummarizer:
    """AI-powered article summarizer and translator"""
    
    def __init__(self, api_key=None):
        self.api_key = api_key or ANTHROPIC_API_KEY
        self.client = None
        
        if not ANTHROPIC_AVAILABLE:
            logger.warning("Anthropic library not installed. AI summarization disabled.")
            return
        
        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY not found. AI summarization disabled.")
            return
        
        try:
            self.client = Anthropic(api_key=self.api_key)
            logger.info("AI Summarizer initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Anthropic client: {e}")
            self.client = None
    
    def _generate_summary(self, title: str, content: str, sector: str, language: str) -> str:
        """Generate summary in specified language"""
        
        if not self.client:
            return self._fallback_summary(title, sector, language)
        
        try:
            prompt = SUMMARIZATION_PROMPT_TEMPLATE.format(
                title=title,
                sector=sector,
                content=content[:2000] if content else title,
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
            logger.debug(f"Generated {language} summary: {summary[:50]}...")
            return summary
            
        except Exception as e:
            logger.error(f"Error generating {language} summary: {e}")
            return self._fallback_summary(title, sector, language)
    
    def _fallback_summary(self, title: str, sector: str, language: str) -> str:
        """Fallback summary when API is unavailable"""
        if language == "Korean":
            return f"{sector} 분야 베트남 인프라 프로젝트. {title[:100]}"
        elif language == "Vietnamese":
            return f"Dự án cơ sở hạ tầng Việt Nam trong lĩnh vực {sector}. {title[:100]}"
        else:
            return f"{sector} infrastructure project in Vietnam. {title[:100]}"
    
    def _translate_title(self, title: str, target_language: str = "English") -> str:
        """Translate title to target language"""
        
        if not self.client:
            return title
        
        try:
            prompt = f"""Translate this Vietnamese news headline to {target_language}.
Keep it concise and professional.
Return ONLY the translation, nothing else.

Vietnamese: {title}

{target_language}:"""
            
            message = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=200,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            translation = message.content[0].text.strip()
            logger.debug(f"Translated to {target_language}: {translation[:50]}...")
            return translation
            
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return title
    
    async def process_articles(self, articles: List[Dict], max_articles: int = 20) -> List[Dict]:
        """Process articles: translate titles and generate summaries
        
        Args:
            articles: List of article dictionaries
            max_articles: Maximum number of articles to process with AI (to control API costs)
        
        Returns:
            List of processed articles with summaries
        """
        
        if not articles:
            logger.info("No articles to process")
            return articles
        
        # Only process articles that don't have summaries yet
        articles_to_process = []
        for article in articles:
            # Check if already has summaries
            has_summary = (
                article.get("summary_en") and 
                article.get("summary_ko") and
                len(str(article.get("summary_en", ""))) > 50
            )
            if not has_summary:
                articles_to_process.append(article)
        
        # Limit to max_articles for API cost control
        articles_to_process = articles_to_process[:max_articles]
        
        if not articles_to_process:
            logger.info("All articles already have summaries")
            return articles
        
        logger.info(f"Processing {len(articles_to_process)} articles with AI...")
        
        if not self.client:
            logger.warning("AI client not available. Using fallback summaries.")
            for article in articles_to_process:
                self._add_fallback_summaries(article)
            return articles
        
        for idx, article in enumerate(articles_to_process, 1):
            title = article.get("title", "")
            content = article.get("content", article.get("summary_vi", title))
            sector = article.get("sector", "Infrastructure")
            
            logger.info(f"Processing {idx}/{len(articles_to_process)}: {str(title)[:50]}...")
            
            try:
                # Check if title is Vietnamese (contains non-ASCII)
                is_vietnamese = any(ord(c) > 127 for c in str(title))
                
                if is_vietnamese:
                    # Translate title to English
                    title_en = self._translate_title(title, "English")
                    title_ko = self._translate_title(title, "Korean")
                    time.sleep(0.5)
                else:
                    title_en = title
                    title_ko = title
                
                # Generate summaries
                summary_en = self._generate_summary(title_en, content, sector, "English")
                time.sleep(0.5)
                
                summary_ko = self._generate_summary(title_en, content, sector, "Korean")
                time.sleep(0.5)
                
                summary_vi = self._generate_summary(title_en, content, sector, "Vietnamese")
                time.sleep(0.5)
                
                # Update article
                article["title_en"] = title_en
                article["title_ko"] = title_ko
                article["summary_en"] = summary_en
                article["summary_ko"] = summary_ko
                article["summary_vi"] = summary_vi
                
                logger.info(f"✓ Processed article {idx}")
                
            except Exception as e:
                logger.error(f"Error processing article: {e}")
                self._add_fallback_summaries(article)
        
        logger.info(f"✓ AI processing complete: {len(articles_to_process)} articles")
        return articles
    
    def _add_fallback_summaries(self, article: Dict):
        """Add fallback summaries to article"""
        title = str(article.get("title", ""))[:100]
        sector = article.get("sector", "Infrastructure")
        
        if not article.get("title_en"):
            article["title_en"] = title
        if not article.get("title_ko"):
            article["title_ko"] = title
        if not article.get("summary_en"):
            article["summary_en"] = f"{sector} infrastructure project in Vietnam. {title}"
        if not article.get("summary_ko"):
            article["summary_ko"] = f"{sector} 분야 베트남 인프라 프로젝트. {title}"
        if not article.get("summary_vi"):
            article["summary_vi"] = f"Dự án cơ sở hạ tầng Việt Nam trong lĩnh vực {sector}. {title}"
    
    def summarize_single(self, article: Dict) -> Dict:
        """Summarize a single article (synchronous)"""
        
        title = article.get("title", "")
        content = article.get("content", article.get("summary_vi", title))
        sector = article.get("sector", "Infrastructure")
        
        try:
            is_vietnamese = any(ord(c) > 127 for c in str(title))
            
            if is_vietnamese and self.client:
                title_en = self._translate_title(title, "English")
                title_ko = self._translate_title(title, "Korean")
            else:
                title_en = title
                title_ko = title
            
            article["title_en"] = title_en
            article["title_ko"] = title_ko
            article["summary_en"] = self._generate_summary(title_en, content, sector, "English")
            article["summary_ko"] = self._generate_summary(title_en, content, sector, "Korean")
            article["summary_vi"] = self._generate_summary(title_en, content, sector, "Vietnamese")
            
        except Exception as e:
            logger.error(f"Error in summarize_single: {e}")
            self._add_fallback_summaries(article)
        
        return article


def main():
    """Main execution for testing"""
    
    import argparse
    
    parser = argparse.ArgumentParser(description='AI Summarizer for Vietnam Infrastructure News')
    parser.add_argument('--test', action='store_true', help='Run test summarization')
    
    args = parser.parse_args()
    
    try:
        summarizer = AISummarizer()
        
        if args.test:
            # Test with sample article
            test_article = {
                "title": "Dự án xử lý nước thải tại TP.HCM được phê duyệt",
                "content": "Dự án nhà máy xử lý nước thải công suất 200.000 m3/ngày tại TP.HCM đã được phê duyệt với tổng vốn đầu tư 500 triệu USD.",
                "sector": "Waste Water",
                "province": "Ho Chi Minh City"
            }
            
            result = summarizer.summarize_single(test_article)
            
            print("\nTest Result:")
            print(f"  Title (EN): {result.get('title_en')}")
            print(f"  Title (KO): {result.get('title_ko')}")
            print(f"  Summary (EN): {result.get('summary_en')}")
            print(f"  Summary (KO): {result.get('summary_ko')}")
            print(f"  Summary (VI): {result.get('summary_vi')}")
        else:
            print("AI Summarizer ready. Use --test to run a test.")
            
    except Exception as e:
        logger.error(f"Error in main: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
