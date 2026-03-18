#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News — AI Summarizer
Version 2.0 — Genspark Multilingual Summary Agent 스펙 완전 구현

반영된 개선사항:
  [검증보고서] API 키 미설정 시 템플릿 반복 생성 문제 해결
  [검증보고서] 요약문 71.9% 누락 → 실제 Claude API 호출로 해결
  [Genspark]  3개 국어 동시 생성 (KO / EN / VI)
  [Genspark]  Who / What / Where / When 구조화 요약 프롬프트
  [Genspark]  URL 크롤링 실패 시 RSS description 기반 fallback
  [Genspark]  Rate limit → 재시도 with 지수 백오프
  [Genspark]  confidence_score < 80인 기사 → QC 플래그 처리
  [main.py]   config.settings 의존성 제거 → 환경변수 직접 읽기
"""

import os
import sys
import time
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup

# ── 환경변수 직접 읽기 (config.settings 의존성 제거) ──────────
ANTHROPIC_API_KEY = (
    os.environ.get('ANTHROPIC_API_KEY', '')
    or os.environ.get('CLAUDE_API_KEY', '')
)
MODEL_SUMMARIZER   = os.environ.get('SUMMARIZER_MODEL', 'claude-sonnet-4-20250514')
MAX_ARTICLES_BATCH = int(os.environ.get('SUMMARIZER_BATCH', 20))
REQUEST_DELAY      = float(os.environ.get('SUMMARIZER_DELAY', 1.5))  # 초 (rate limit 방지)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    from anthropic import Anthropic, RateLimitError, APIError
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logger.warning("anthropic 패키지 미설치 — fallback 모드로 실행")


# ============================================================
# SECTOR 번역 매핑 (다국어 요약 품질 향상)
# ============================================================

SECTOR_KO = {
    "Waste Water":            "폐수처리",
    "Water Supply/Drainage":  "상수도/배수",
    "Solid Waste":            "고형폐기물",
    "Power":                  "발전/전력",
    "Oil & Gas":              "석유/가스",
    "Transport":              "교통인프라",
    "Industrial Parks":       "산업단지",
    "Smart City":             "스마트시티",
    "Construction":           "건설/도시개발",
}

SECTOR_VI = {
    "Waste Water":            "Xử lý nước thải",
    "Water Supply/Drainage":  "Cấp thoát nước",
    "Solid Waste":            "Chất thải rắn",
    "Power":                  "Điện năng",
    "Oil & Gas":              "Dầu khí",
    "Transport":              "Giao thông",
    "Industrial Parks":       "Khu công nghiệp",
    "Smart City":             "Thành phố thông minh",
    "Construction":           "Xây dựng",
}


# ============================================================
# URL CONTENT FETCHER
# [Genspark] Step 1: URL 크롤링 → 본문 추출
# ============================================================

def fetch_article_content(url: str, timeout: int = 10) -> str:
    """URL에서 기사 본문을 추출합니다. 실패 시 빈 문자열 반환."""
    if not url or not url.startswith('http'):
        return ""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0',
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'en,vi;q=0.9,ko;q=0.8',
        }
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        # nav / header / footer / aside 제거
        for tag in soup.find_all(['nav', 'header', 'footer', 'aside',
                                   'script', 'style', 'noscript']):
            tag.decompose()

        # 기사 본문 후보 태그 탐색
        for selector in ['article', '.article-body', '.post-content',
                         '.entry-content', 'main', '#content']:
            el = soup.select_one(selector)
            if el:
                text = el.get_text(separator=' ', strip=True)
                if len(text) > 200:
                    return text[:3000]

        # fallback: body 전체
        body = soup.find('body')
        return body.get_text(separator=' ', strip=True)[:3000] if body else ""

    except Exception as e:
        logger.debug(f"Content fetch failed [{url}]: {e}")
        return ""


# ============================================================
# SUMMARIZER CLASS
# ============================================================

class AISummarizer:
    """
    [Genspark Multilingual Summary Agent 구현]
    - Claude API로 EN → KO → VI 3개국어 요약 동시 생성
    - API 실패 시 구조화된 fallback 템플릿 사용
    """

    def __init__(self):
        self.client = None
        self.api_available = False

        if not ANTHROPIC_AVAILABLE:
            logger.warning("anthropic 패키지 없음 — fallback 모드")
            return

        if not ANTHROPIC_API_KEY:
            logger.warning("ANTHROPIC_API_KEY 미설정 — fallback 모드")
            return

        try:
            self.client       = Anthropic(api_key=ANTHROPIC_API_KEY)
            self.api_available = True
            logger.info(f"AISummarizer ready | model={MODEL_SUMMARIZER}")
        except Exception as e:
            logger.error(f"Anthropic 초기화 실패: {e}")

    # ── Fallback 요약 ─────────────────────────────────────────
    def _fallback(self, title: str, sector: str, province: str) -> Dict:
        """
        [검증보고서] API 미작동 시 단순 반복 템플릿 방지
        → 구조화된 정보 기반 fallback 사용
        """
        sector_ko = SECTOR_KO.get(sector, sector)
        sector_vi = SECTOR_VI.get(sector, sector)
        short     = title[:120] if len(title) > 120 else title

        return {
            "en": f"[{sector}] Infrastructure project in {province}: {short}",
            "ko": f"[{sector_ko}] {province} 인프라 프로젝트: {short}",
            "vi": f"[{sector_vi}] Dự án hạ tầng tại {province}: {short}",
            "is_fallback": True,
        }

    # ── Claude API 호출 (재시도 포함) ─────────────────────────
    def _call_api(self, prompt: str, retries: int = 3) -> Optional[str]:
        for attempt in range(retries):
            try:
                msg = self.client.messages.create(
                    model=MODEL_SUMMARIZER,
                    max_tokens=600,
                    messages=[{"role": "user", "content": prompt}],
                )
                return msg.content[0].text.strip()

            except Exception as e:
                err_str = str(e)
                if 'rate_limit' in err_str.lower() or 'overloaded' in err_str.lower():
                    wait = (2 ** attempt) * 5  # 5, 10, 20초 지수 백오프
                    logger.warning(f"Rate limit — {wait}초 대기 후 재시도...")
                    time.sleep(wait)
                elif attempt < retries - 1:
                    time.sleep(2)
                else:
                    logger.error(f"API 호출 최종 실패: {e}")
                    return None
        return None

    # ── 단일 기사 요약 ────────────────────────────────────────
    def summarize_article(self, article: Dict) -> Dict:
        """
        [Genspark] 기사 1건 요약:
          1. URL 크롤링 시도
          2. 실패 시 title + raw_summary 사용
          3. Claude API로 EN/KO/VI 동시 생성
          4. API 실패 시 fallback
        """
        title    = str(article.get('title', ''))
        sector   = article.get('sector', 'Infrastructure')
        province = article.get('province', 'Vietnam')
        url      = article.get('url', '')
        rss_desc = article.get('summary', '') or article.get('raw_summary', '')

        sector_ko = SECTOR_KO.get(sector, sector)
        sector_vi = SECTOR_VI.get(sector, sector)

        # 1. URL 크롤링
        body_text = ""
        if url:
            body_text = fetch_article_content(url)

        # 2. Source text 결정
        source_text = body_text if len(body_text) > 200 else rss_desc
        source_text = source_text[:1500] if source_text else title

        # 3. API 미사용 → fallback
        if not self.api_available:
            result = self._fallback(title, sector, province)
            article['summary_en'] = result['en']
            article['summary_ko'] = result['ko']
            article['summary_vi'] = result['vi']
            article['is_fallback'] = True
            return article

        # 4. Claude API 호출
        # [Genspark] Who / What / Where / When 구조 + 합쇼체(KO) + 전문 보도체
        prompt = f"""You are a professional infrastructure news analyst.
Analyze the following Vietnam infrastructure news article and produce concise summaries in 3 languages.

## Article Information
- Title: {title}
- Sector: {sector} ({sector_ko})
- Province: {province}
- Content: {source_text}

## Output Requirements
Return ONLY a JSON object (no markdown, no explanation):
{{
  "en": "1-2 sentence English summary. Focus on: Investor/Operator, Project type & value, Location, Timeline. Max 250 chars.",
  "ko": "1-2문장 한국어 요약. 투자자/시행사, 사업 내용 및 금액, 위치, 일정 포함. 합쇼체 사용. 최대 250자.",
  "vi": "1-2 câu tóm tắt tiếng Việt. Nêu: Nhà đầu tư, Loại dự án & giá trị, Địa điểm, Thời gian. Tối đa 250 ký tự."
}}

## Style Rules
- English: Business reporting tone, factual, no sensationalism
- Korean: Professional 합쇼체 (습니다/합니다), concise
- Vietnamese: Professional business Vietnamese
- Structure: "[Sector keyword] [Main fact]. [Key detail]."
- If specific value/timeline not available, omit rather than guess"""

        raw = self._call_api(prompt)
        time.sleep(REQUEST_DELAY)  # rate limit 방지

        if raw:
            try:
                # JSON 파싱 (마크다운 펜스 제거)
                clean = raw.replace('```json', '').replace('```', '').strip()
                data  = json.loads(clean)
                article['summary_en'] = data.get('en', '')[:300]
                article['summary_ko'] = data.get('ko', '')[:300]
                article['summary_vi'] = data.get('vi', '')[:300]
                article['is_fallback'] = False
                return article
            except json.JSONDecodeError:
                logger.warning(f"JSON 파싱 실패 — fallback 적용: {title[:50]}")

        # API 실패 → fallback
        result = self._fallback(title, sector, province)
        article['summary_en'] = result['en']
        article['summary_ko'] = result['ko']
        article['summary_vi'] = result['vi']
        article['is_fallback'] = True
        return article

    # ── 배치 처리 ─────────────────────────────────────────────
    def process_articles(self, articles: List[Dict],
                         max_articles: int = None) -> List[Dict]:
        """
        [Genspark] 배치 처리:
          - confidence < 80인 기사는 'qc_flag' 마킹
          - max_articles 초과분은 fallback으로 처리
        """
        if not articles:
            return articles

        limit    = max_articles or MAX_ARTICLES_BATCH
        api_cnt  = 0
        fall_cnt = 0
        qc_cnt   = 0

        for i, article in enumerate(articles):
            # confidence 낮은 기사 QC 플래그
            conf = article.get('confidence', 100)
            if conf < 80:
                article['qc_flag'] = True
                qc_cnt += 1

            # 이미 요약 있으면 skip
            if article.get('summary_ko') and not article.get('is_fallback'):
                continue

            if i < limit and self.api_available:
                self.summarize_article(article)
                if article.get('is_fallback'):
                    fall_cnt += 1
                else:
                    api_cnt += 1
            else:
                # 배치 초과 → 구조화 fallback (단순 반복 방지)
                fb = self._fallback(
                    article.get('title', ''),
                    article.get('sector', ''),
                    article.get('province', 'Vietnam'),
                )
                article['summary_en']  = fb['en']
                article['summary_ko']  = fb['ko']
                article['summary_vi']  = fb['vi']
                article['is_fallback'] = True
                fall_cnt += 1

        logger.info(
            f"Summarizer complete: API={api_cnt} | fallback={fall_cnt} | "
            f"qc_flagged={qc_cnt} / {len(articles)} total"
        )
        return articles

    # ── SQLite 업데이트 ───────────────────────────────────────
    def update_sqlite_summaries(self, articles: List[Dict], db_path: str):
        """처리된 요약을 SQLite DB에 저장합니다."""
        import sqlite3
        try:
            conn = sqlite3.connect(db_path)
            updated = 0
            for art in articles:
                url_hash = art.get('url_hash')
                if not url_hash:
                    continue
                conn.execute(
                    """UPDATE articles SET
                         summary_ko=?, summary_en=?, summary_vi=?,
                         title_ko=?, title_en=?, title_vi=?,
                         processed=1
                       WHERE url_hash=?""",
                    (
                        art.get('summary_ko', ''),
                        art.get('summary_en', ''),
                        art.get('summary_vi', ''),
                        art.get('title', ''),
                        art.get('title', ''),
                        art.get('title', ''),
                        url_hash,
                    )
                )
                updated += 1
            conn.commit()
            conn.close()
            logger.info(f"SQLite summaries updated: {updated} articles")
        except Exception as e:
            logger.error(f"SQLite update error: {e}")


# ============================================================
# STANDALONE RUNNER
# ============================================================

def main():
    import sqlite3

    DB_PATH = os.environ.get('DB_PATH', 'data/vietnam_infrastructure_news.db')

    print("=" * 60)
    print("AI SUMMARIZER  v2.0")
    print("=" * 60)
    print(f"Model:   {MODEL_SUMMARIZER}")
    print(f"API:     {'Available' if ANTHROPIC_AVAILABLE and ANTHROPIC_API_KEY else 'Fallback mode'}")
    print(f"Batch:   {MAX_ARTICLES_BATCH} articles")
    print()

    summarizer = AISummarizer()

    # 미처리 기사 로드
    if not Path(DB_PATH).exists():
        print(f"DB not found: {DB_PATH}")
        return

    conn     = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows     = conn.execute(
        "SELECT * FROM articles WHERE processed=0 ORDER BY collected_date DESC LIMIT 100"
    ).fetchall()
    conn.close()

    articles = [dict(r) for r in rows]
    print(f"Unprocessed articles: {len(articles)}")

    if not articles:
        print("Nothing to process.")
        return

    processed = summarizer.process_articles(articles)
    summarizer.update_sqlite_summaries(processed, DB_PATH)

    api_ok   = sum(1 for a in processed if not a.get('is_fallback'))
    fallback = sum(1 for a in processed if a.get('is_fallback'))
    qc_flag  = sum(1 for a in processed if a.get('qc_flag'))

    print(f"\nDone: {api_ok} API summaries | {fallback} fallbacks | {qc_flag} QC-flagged")


if __name__ == "__main__":
    main()
