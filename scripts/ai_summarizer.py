"""
Vietnam Infrastructure News AI Summarizer
Uses Claude API to generate summaries in multiple languages
"""
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import sys
sys.path.append(str(Path(__file__).parent.parent))

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("Warning: anthropic package not installed. Run: pip install anthropic")

from config.settings import (
    ANTHROPIC_API_KEY, AI_MODEL, AI_MAX_TOKENS, AI_TEMPERATURE,
    SUMMARY_PROMPT_TEMPLATE, DATA_DIR, OUTPUT_DIR
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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

SECTOR_PRIORITY = ["Oil & Gas", "Waste Water", "Solid Waste", "Water Supply/Drainage", "Power", "Smart City", "Industrial Parks"]


def classify_article_by_keywords(title: str, content: str = "") -> tuple:
    text = (str(title) + " " + str(content)).lower()
    
    for sector in SECTOR_PRIORITY:
        keywords = SECTOR_KEYWORDS.get(sector, [])
        for keyword in keywords:
            if keyword.lower() in text:
                return sector, AREA_BY_SECTOR.get(sector, "Environment")
    
    return "Waste Water", "Environment"


class AISummarizer:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or ANTHROPIC_API_KEY
        self.client = None
        
        if ANTHROPIC_AVAILABLE and self.api_key:
            self.client = anthropic.Anthropic(api_key=self.api_key)
            logger.info("Anthropic client initialized")
        else:
            logger.warning("Anthropic client not available. Using fallback summarization.")
    
    def summarize_article(self, article: Dict) -> Dict:
        if self.client:
            return self._summarize_with_claude(article)
        else:
            return self._fallback_summarize(article)
    
    def _summarize_with_claude(self, article: Dict) -> Dict:
        try:
            prompt = SUMMARY_PROMPT_TEMPLATE.format(
                title=article.get("title", ""),
                content=article.get("content", article.get("summary", "")),
                source=article.get("source", ""),
                date=article.get("published", "")
            )
            
            message = self.client.messages.create(
                model=AI_MODEL,
                max_tokens=AI_MAX_TOKENS,
                temperature=AI_TEMPERATURE,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            response_text = message.content[0].text
            
            try:
                json_start = response_text.find('{')
                json_end = response_text.rfind('}') + 1
                if json_start >= 0 and json_end > json_start:
                    result = json.loads(response_text[json_start:json_end])
                    
                    article["title_ko"] = result.get("title_ko", article.get("title", ""))
                    article["title_en"] = result.get("title_en", article.get("title", ""))
                    article["title_vi"] = result.get("title_vi", article.get("title", ""))
                    article["summary_ko"] = result.get("summary_ko", "")
                    article["summary_en"] = result.get("summary_en", "")
                    article["summary_vi"] = result.get("summary_vi", "")
                    article["entities"] = result.get("entities", [])
                    article["project_value"] = result.get("project_value", "")
                    
                    if result.get("sector") and result.get("sector") in AREA_BY_SECTOR:
                        article["sector"] = result["sector"]
                        article["area"] = AREA_BY_SECTOR.get(result["sector"], result.get("area", ""))
                    else:
                        sector, area = classify_article_by_keywords(
                            article.get("title", ""), 
                            article.get("summary", "")
                        )
                        article["sector"] = sector
                        article["area"] = area
                    
                    article["ai_processed"] = True
                    logger.info(f"AI summarized: {article['title'][:50]}...")
                    
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse AI response for: {article['title'][:50]}")
                article = self._fallback_summarize(article)
                
        except Exception as e:
            logger.error(f"Claude API error: {e}")
            article = self._fallback_summarize(article)
        
        return article
    
    def _fallback_summarize(self, article: Dict) -> Dict:
        title = article.get("title", "")
        summary = article.get("summary", "")
        province = article.get("province", "Vietnam")
        
        sector, area = classify_article_by_keywords(title, summary)
        article["sector"] = sector
        article["area"] = area
        
        base_summary = summary[:200] if summary else title
        
        article["title_ko"] = title
        article["title_en"] = title
        article["title_vi"] = title
        article["summary_ko"] = f"{province} 지역 {sector} 관련 프로젝트. {base_summary}"
        article["summary_en"] = f"{sector} project in {province}. {base_summary}"
        article["summary_vi"] = f"Dự án {sector} tại {province}. {base_summary}"
        article["entities"] = []
        article["project_value"] = ""
        article["ai_processed"] = False
        
        return article
    
    async def summarize_batch(self, articles: List[Dict], batch_size: int = 5) -> List[Dict]:
        summarized = []
        
        for i in range(0, len(articles), batch_size):
            batch = articles[i:i + batch_size]
            
            for article in batch:
                if article.get("ai_processed"):
                    summarized.append(article)
                    continue
                
                result = self.summarize_article(article)
                summarized.append(result)
                
                await asyncio.sleep(0.5)
            
            logger.info(f"Processed batch {i//batch_size + 1}/{(len(articles)-1)//batch_size + 1}")
        
        return summarized
    
    def generate_daily_briefing(self, articles: List[Dict], lang: str = "ko") -> str:
        if not articles:
            return "오늘 수집된 뉴스가 없습니다." if lang == "ko" else "No news collected today."
        
        total = len(articles)
        area_counts = {}
        sector_counts = {}
        province_counts = {}
        
        for article in articles:
            area = article.get("area", "Unknown")
            sector = article.get("sector", "Unknown")
            province = article.get("province", "Unknown")
            
            area_counts[area] = area_counts.get(area, 0) + 1
            sector_counts[sector] = sector_counts.get(sector, 0) + 1
            if province != "Vietnam":
                province_counts[province] = province_counts.get(province, 0) + 1
        
        top_sector = max(sector_counts.items(), key=lambda x: x[1]) if sector_counts else ("Unknown", 0)
        top_province = max(province_counts.items(), key=lambda x: x[1]) if province_counts else ("Unknown", 0)
        
        if lang == "ko":
            briefing = f"""오늘 총 {total}건의 베트남 인프라 뉴스가 수집되었습니다.

섹터별로는 {top_sector[0]} 분야가 {top_sector[1]}건으로 가장 활발합니다.
지역별로는 {top_province[0]}에서 {top_province[1]}건으로 가장 많은 기사가 발생했습니다.

분야별 현황:
- 환경 인프라: {area_counts.get('Environment', 0)}건
- 에너지 개발: {area_counts.get('Energy Develop.', 0)}건
- 도시 개발: {area_counts.get('Urban Develop.', 0)}건

주요 기사:
"""
            for article in articles[:5]:
                title = article.get('title_ko', article.get('title', ''))[:60]
                briefing += f"• {title}... ({article.get('source', '')})\n"
                
        elif lang == "en":
            briefing = f"""Total {total} Vietnam infrastructure news collected today.

By sector, {top_sector[0]} leads with {top_sector[1]} articles.
By region, {top_province[0]} has the most with {top_province[1]} articles.

Area Summary:
- Environment: {area_counts.get('Environment', 0)}
- Energy Development: {area_counts.get('Energy Develop.', 0)}
- Urban Development: {area_counts.get('Urban Develop.', 0)}

Top Articles:
"""
            for article in articles[:5]:
                title = article.get('title_en', article.get('title', ''))[:60]
                briefing += f"• {title}... ({article.get('source', '')})\n"
        
        else:
            briefing = f"""Tổng cộng {total} tin tức hạ tầng Việt Nam được thu thập hôm nay.

Theo ngành, {top_sector[0]} dẫn đầu với {top_sector[1]} bài.
Theo vùng, {top_province[0]} có nhiều nhất với {top_province[1]} bài.

Tóm tắt theo lĩnh vực:
- Môi trường: {area_counts.get('Environment', 0)}
- Phát triển năng lượng: {area_counts.get('Energy Develop.', 0)}
- Phát triển đô thị: {area_counts.get('Urban Develop.', 0)}

Tin nổi bật:
"""
            for article in articles[:5]:
                title = article.get('title_vi', article.get('title', ''))[:60]
                briefing += f"• {title}... ({article.get('source', '')})\n"
        
        return briefing


def load_articles(filepath: str) -> List[Dict]:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("articles", [])
    except Exception as e:
        logger.error(f"Error loading articles: {e}")
        return []


def save_articles(articles: List[Dict], filepath: str):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump({
                "processed_at": datetime.now().isoformat(),
                "total_count": len(articles),
                "articles": articles
            }, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(articles)} articles to {filepath}")
    except Exception as e:
        logger.error(f"Error saving articles: {e}")


async def main():
    data_files = sorted(DATA_DIR.glob("news_*.json"), reverse=True)
    
    if not data_files:
        print("No news files found. Run news_collector.py first.")
        return
    
    latest_file = data_files[0]
    print(f"Processing: {latest_file}")
    
    articles = load_articles(str(latest_file))
    print(f"Loaded {len(articles)} articles")
    
    summarizer = AISummarizer()
    processed = await summarizer.summarize_batch(articles)
    
    output_file = DATA_DIR / f"processed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    save_articles(processed, str(output_file))
    
    briefing_ko = summarizer.generate_daily_briefing(processed, "ko")
    print(f"\n{'='*50}")
    print("AI Summarization Complete")
    print(f"{'='*50}")
    print(f"\n{briefing_ko}")
    
    return processed


if __name__ == "__main__":
    asyncio.run(main())
