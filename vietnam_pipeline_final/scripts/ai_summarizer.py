#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News - AI Summarizer
Generates multilingual summaries and translations
Can be run directly: python ai_summarizer.py
"""

import logging
import sys
import os
from pathlib import Path
from typing import List, Dict

# Setup paths
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import ANTHROPIC_API_KEY

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


class AISummarizer:
    """AI-powered summarizer and translator"""
    
    def __init__(self):
        self.client = None
        
        if not ANTHROPIC_AVAILABLE:
            logger.warning("Anthropic library not installed")
            return
        
        if not ANTHROPIC_API_KEY:
            logger.warning("ANTHROPIC_API_KEY not set")
            return
        
        try:
            self.client = Anthropic(api_key=ANTHROPIC_API_KEY)
            logger.info("AI Summarizer initialized")
        except Exception as e:
            logger.error(f"Anthropic init error: {e}")
    
    def _fallback_summary(self, title: str, sector: str, province: str, lang: str) -> str:
        """Generate fallback summary when API unavailable"""
        if lang == "ko":
            return f"{province} 지역 {sector} 관련 프로젝트. {title[:100]}"
        elif lang == "vi":
            return f"Dự án {sector} tại {province}. {title[:100]}"
        else:
            return f"{sector} project in {province}. {title[:100]}"
    
    def process_articles(self, articles: List[Dict], max_articles: int = 10) -> List[Dict]:
        """Add multilingual summaries to articles"""
        
        if not articles:
            return articles
        
        for article in articles[:max_articles]:
            title = str(article.get("title", ""))
            sector = article.get("sector", "Infrastructure")
            province = article.get("province", "Vietnam")
            existing_summary = article.get("summary", "")
            
            # Generate summaries for each language
            if not article.get("summary_ko"):
                article["summary_ko"] = self._fallback_summary(title, sector, province, "ko")
            
            if not article.get("summary_en"):
                if existing_summary and len(existing_summary) > 50:
                    article["summary_en"] = existing_summary[:300]
                else:
                    article["summary_en"] = self._fallback_summary(title, sector, province, "en")
            
            if not article.get("summary_vi"):
                article["summary_vi"] = self._fallback_summary(title, sector, province, "vi")
            
            # Copy titles
            if not article.get("title_ko"):
                article["title_ko"] = title
            if not article.get("title_en"):
                article["title_en"] = title
            if not article.get("title_vi"):
                article["title_vi"] = title
        
        return articles


def main():
    """Main function"""
    print("=" * 60)
    print("AI SUMMARIZER")
    print("=" * 60)
    
    if ANTHROPIC_AVAILABLE and ANTHROPIC_API_KEY:
        print("✓ Anthropic API available")
    else:
        print("Running in fallback mode (no API calls)")
        print("Summaries will be generated using templates")
    
    print("\nDone!")


if __name__ == "__main__":
    main()
