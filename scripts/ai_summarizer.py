#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News - AI Summarizer
"""

import logging
import os
import sys
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from anthropic import Anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from config.settings import ANTHROPIC_API_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AISummarizer:
    def __init__(self):
        self.client = None
        if ANTHROPIC_AVAILABLE and ANTHROPIC_API_KEY:
            try:
                self.client = Anthropic(api_key=ANTHROPIC_API_KEY)
                logger.info("AI Summarizer initialized")
            except Exception as e:
                logger.error(f"Init error: {e}")
    
    def process_articles(self, articles: List[Dict], max_articles: int = 10) -> List[Dict]:
        """Add fallback summaries (API disabled for cost)"""
        for article in articles:
            title = str(article.get("title", ""))
            sector = article.get("sector", "Infrastructure")
            
            if not article.get("title_en"):
                article["title_en"] = title
            if not article.get("title_ko"):
                article["title_ko"] = title
            if not article.get("summary_en"):
                article["summary_en"] = f"{sector} project in Vietnam. {title[:100]}"
            if not article.get("summary_ko"):
                article["summary_ko"] = f"베트남 {sector} 프로젝트. {title[:100]}"
            if not article.get("summary_vi"):
                article["summary_vi"] = title
        
        return articles


def main():
    logger.info("AI Summarizer ready (fallback mode)")


if __name__ == "__main__":
    main()
