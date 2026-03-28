"""
ai_summarizer.py
================
Vietnam Infrastructure News - 3개국어 번역 모듈

번역 방식 (Anthropic API Connection error 완전 해결):
  1차: MyMemory API  (무료 공식 REST API, 인증 불필요)
  2차: deep-translator (Google Translate 무료 비공식)
  3차: Fallback (원문 그대로 사용)

장점:
  - Connection error 없음 (일반 HTTPS 요청)
  - API 키 불필요 (GitHub Secrets 추가 불필요)
  - GitHub Actions에서 안정적 작동
  - 주간 실행 기준 MyMemory 무료 할당량 충분
"""

import logging
import time
import requests
from typing import Optional

logger = logging.getLogger(__name__)

DELAY_SEC    = 0.3   # 번역 요청 간 대기 (초)
MAX_TEXT_LEN = 400   # 번역 최대 길이


# ════════════════════════════════════════════════════════════
# 번역 엔진 1: MyMemory 공식 무료 API
# ════════════════════════════════════════════════════════════

def _translate_mymemory(text: str, source: str, target: str) -> Optional[str]:
    """MyMemory REST API - 무료, 인증 불필요, 1일 5000단어"""
    if not text or not text.strip():
        return None
    try:
        resp = requests.get(
            "https://api.mymemory.translated.net/get",
            params={
                "q":        text[:MAX_TEXT_LEN],
                "langpair": f"{source}|{target}",
                "de":       "hms4792@gmail.com",
            },
            timeout=15,
        )
        data = resp.json()
        if data.get("responseStatus") == 200:
            result = data["responseData"]["translatedText"]
            if result and "MYMEMORY WARNING" not in result:
                return result.strip()
    except Exception as e:
        logger.debug(f"[MyMemory] {e}")
    return None


# ════════════════════════════════════════════════════════════
# 번역 엔진 2: deep-translator (Google Translate 무료)
# ════════════════════════════════════════════════════════════

def _translate_google_free(text: str, source: str, target: str) -> Optional[str]:
    """deep-translator 라이브러리 - Google Translate 무료"""
    if not text or not text.strip():
        return None
    try:
        from deep_translator import GoogleTranslator
        result = GoogleTranslator(source=source, target=target).translate(text[:MAX_TEXT_LEN])
        if result and result.strip():
            return result.strip()
    except Exception as e:
        logger.debug(f"[GoogleFree] {e}")
    return None


# ════════════════════════════════════════════════════════════
# 번역 메인 함수 (이중 방식)
# ════════════════════════════════════════════════════════════

def translate(text: str, source: str = "vi", target: str = "en") -> str:
    """
    1차 MyMemory → 2차 Google → 3차 원문 반환
    """
    if not text or not text.strip():
        return text or ""

    result = _translate_mymemory(text, source, target)
    if result:
        return result

    result = _translate_google_free(text, source, target)
    if result:
        return result

    logger.warning(f"[번역] 실패, 원문 사용: {text[:50]}")
    return text


# ════════════════════════════════════════════════════════════
# AISummarizer 클래스 (main.py 호환)
# ════════════════════════════════════════════════════════════

class AISummarizer:
    """
    3개국어 번역 클래스 - Google Translate 기반
    (Anthropic API Connection error 문제 해결)
    """

    def __init__(self):
        logger.info("[AISummarizer] Google Translate 모드 초기화")
        try:
            import deep_translator  # noqa
            logger.info("[AISummarizer] deep-translator 확인 완료")
        except ImportError:
            logger.warning("[AISummarizer] deep-translator 없음 - MyMemory만 사용")

    def process_articles(self, articles: list) -> list:
        if not articles:
            return []

        logger.info(f"[AISummarizer] {len(articles)}건 번역 시작")
        processed = []
        success   = 0

        for i, article in enumerate(articles):
            result = self._process_single(article, i + 1, len(articles))
            processed.append(result)
            if result.get("title_en") and result["title_en"] != result.get("title", ""):
                success += 1
            if i < len(articles) - 1:
                time.sleep(DELAY_SEC)

        logger.info(f"[AISummarizer] 번역 완료: {success}/{len(processed)}건 성공")
        return processed

    def _process_single(self, article: dict, idx: int, total: int) -> dict:
        title   = article.get("title", "") or ""
        summary = (article.get("summary", "") or article.get("raw_summary", "") or "")[:300]
        is_vi   = self._is_vietnamese(title)

        logger.info(f"  [{idx}/{total}] {'VI' if is_vi else 'EN'} → EN/KO: {title[:55]}...")

        if is_vi:
            title_en   = translate(title,   source="vi", target="en")
            title_ko   = translate(title,   source="vi", target="ko")
            title_vi   = title
            summary_en = translate(summary, source="vi", target="en") if summary else ""
            summary_ko = translate(summary, source="vi", target="ko") if summary else ""
            summary_vi = summary
        else:
            title_en   = title
            title_ko   = translate(title,   source="en", target="ko")
            title_vi   = translate(title,   source="en", target="vi")
            summary_en = summary
            summary_ko = translate(summary, source="en", target="ko") if summary else ""
            summary_vi = translate(summary, source="en", target="vi") if summary else ""

        # 요약이 없으면 섹터 기반 기본값 생성
        if not summary_en:
            sector = article.get("sector", "Infrastructure")
            summary_en = f"{sector} project news in Vietnam."
            summary_ko = f"베트남 {sector} 관련 뉴스."
            summary_vi = f"Tin tức {sector} tại Việt Nam."

        article["title_en"]   = title_en   or title
        article["title_ko"]   = title_ko   or title
        article["title_vi"]   = title_vi   or title
        article["summary_en"] = summary_en
        article["summary_ko"] = summary_ko
        article["summary_vi"] = summary_vi

        return article

    @staticmethod
    def _is_vietnamese(text: str) -> bool:
        vi_chars = set(
            "àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩị"
            "òóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ"
            "ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊ"
            "ÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ"
        )
        return any(c in vi_chars for c in (text or ""))
