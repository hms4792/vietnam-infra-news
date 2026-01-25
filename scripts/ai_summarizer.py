#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News - AI Summarizer
Can be run directly: python ai_summarizer.py
"""

import logging
import sys
import os
from pathlib import Path

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
    """AI-powered article summarizer"""
    
    def __init__(self):
        self.client = None
        if ANTHROPIC_AVAILABLE and ANTHROPIC_API_KEY:
            try:
                self.client = Anthropic(api_key=ANTHROPIC_API_KEY)
                logger.info("AI Summarizer initialized with Anthropic API")
            except Exception as e:
                logger.warning(f"Anthropic init failed: {e}")
    
    def process_articles(self, articles, max_articles=10):
        """Process articles and add summaries"""
        for article in articles[:max_articles]:
            title = str(article.get("title", ""))
            sector = article.get("sector", "Infrastructure")
            
            # Add fallback summaries if not present
            if not article.get("title_en"):
                article["title_en"] = title
            if not article.get("title_ko"):
                article["title_ko"] = title
            if not article.get("summary_en"):
                article["summary_en"] = f"{sector} infrastructure project in Vietnam. {title[:100]}"
            if not article.get("summary_ko"):
                article["summary_ko"] = f"베트남 {sector} 인프라 프로젝트. {title[:100]}"
            if not article.get("summary_vi"):
                article["summary_vi"] = article.get("summary_vi", title)
        
        return articles


def main():
    """Main function"""
    print("=" * 60)
    print("AI SUMMARIZER")
    print("=" * 60)
    
    if ANTHROPIC_AVAILABLE and ANTHROPIC_API_KEY:
        print("Anthropic API available")
    else:
        print("Running in fallback mode (no API calls)")
    
    print("Summaries will be generated during dashboard creation")
    print("Done!")


if __name__ == "__main__":
    main()
