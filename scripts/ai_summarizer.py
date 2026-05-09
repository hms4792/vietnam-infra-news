"""
ai_summarizer.py  ── v3.0 (2026-05-09)
===================================================
역할: 수집된 기사 번역/요약 처리

변경 이력:
  v3.0: 번역 성공률 대폭 개선
    - Google Translate: 지수 백오프(Exponential Backoff) 재시도 3회
    - User-Agent 로테이션으로 차단 우회
    - LibreTranslate (무료 공개 API) fallback 추가
    - MyMemory API 재정비 (문장 분할 + 병합)
    - 번역 캐시 (session 내 중복 번역 방지)
    - DeepL 의존성 완전 제거 (차단됨)
    - 영문 기사: 영→한 번역만 수행 (EN 원본 보존)
    - 통계 로그: 번역 엔진별 성공 건수 출력

영구 제약:
  - Anthropic API 번역 금지 (GitHub Actions 연결 오류)
  - EMAIL_USERNAME / EMAIL_PASSWORD 시크릿 유지
"""

import logging
import random
import re
import time
from typing import Optional

import requests

# ── 로깅 ──────────────────────────────────────────────────────────────────
log = logging.getLogger('ai_summarizer')
if not log.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S'
    )

# ══════════════════════════════════════════════════════════════════════════
#  번역 엔진 설정
# ══════════════════════════════════════════════════════════════════════════

# Google Translate 비공식 API (무료, rate limit 있음)
GOOGLE_TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"

# MyMemory API (무료, 1000 words/day per IP)
MYMEMORY_URL = "https://api.mymemory.translated.net/get"

# LibreTranslate 공개 인스턴스 목록 (백업용)
# 참조: https://github.com/LibreTranslate/LibreTranslate
LIBRETRANSLATE_INSTANCES = [
    "https://libretranslate.com",          # 공식 (무료 플랜 제한적)
    "https://translate.fedilab.app",        # 커뮤니티 인스턴스
    "https://lt.vern.cc",                   # 커뮤니티 인스턴스
]

# User-Agent 풀 (로테이션으로 차단 우회)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]

# 번역 결과 캐시 (session 내 중복 방지)
_TRANSLATION_CACHE: dict[str, str] = {}


# ══════════════════════════════════════════════════════════════════════════
#  핵심 번역 함수
# ══════════════════════════════════════════════════════════════════════════

def _google_translate(text: str, src: str, tgt: str, retry: int = 3) -> Optional[str]:
    """
    Google Translate 비공식 API 호출.
    
    지수 백오프(Exponential Backoff):
      - 1회 실패: 2초 대기 후 재시도
      - 2회 실패: 4초 대기 후 재시도
      - 3회 모두 실패: None 반환
    
    User-Agent 로테이션: 매 호출마다 다른 UA 사용
    """
    if not text or not text.strip():
        return None

    cache_key = f"google|{src}|{tgt}|{text[:100]}"
    if cache_key in _TRANSLATION_CACHE:
        return _TRANSLATION_CACHE[cache_key]

    params = {
        "client": "gtx",       # gtx = 비공식 클라이언트 식별자
        "sl": src,             # source language
        "tl": tgt,             # target language
        "dt": "t",             # 번역 결과만 요청
        "q": text[:4500],      # 최대 5000자 제한 (여유 두기)
    }

    for attempt in range(retry):
        try:
            ua = random.choice(USER_AGENTS)
            headers = {
                "User-Agent": ua,
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
                "Referer": "https://translate.google.com/",
            }
            resp = requests.get(
                GOOGLE_TRANSLATE_URL, params=params,
                headers=headers, timeout=15
            )

            if resp.status_code == 429:
                # Rate limit: 더 긴 대기 후 재시도
                wait = (2 ** attempt) * 3  # 3, 6, 12초
                log.debug(f"Google Translate 429 rate limit — {wait}초 대기")
                time.sleep(wait)
                continue

            if resp.status_code != 200:
                log.debug(f"Google Translate HTTP {resp.status_code}")
                time.sleep(2 ** attempt)
                continue

            # 응답 파싱: [[["translated", "original", ...]]] 구조
            data = resp.json()
            translated_parts = []
            if isinstance(data, list) and data:
                for segment in data[0]:
                    if isinstance(segment, list) and segment[0]:
                        translated_parts.append(segment[0])

            result = "".join(translated_parts).strip()
            if result:
                _TRANSLATION_CACHE[cache_key] = result
                return result

        except requests.exceptions.Timeout:
            log.debug(f"Google Translate 타임아웃 (시도 {attempt+1}/{retry})")
            time.sleep(2 ** attempt)
        except Exception as e:
            log.debug(f"Google Translate 오류: {e} (시도 {attempt+1}/{retry})")
            time.sleep(2 ** attempt)

    return None


def _mymemory_translate(text: str, src: str, tgt: str) -> Optional[str]:
    """
    MyMemory API 번역.
    
    제한: 1000 words/day (IP당)
    긴 텍스트는 문장으로 분할 후 번역하여 합산.
    
    언어 코드:
      - ko = 한국어
      - en = 영어
      - vi = 베트남어
    """
    if not text or not text.strip():
        return None

    cache_key = f"mymemory|{src}|{tgt}|{text[:100]}"
    if cache_key in _TRANSLATION_CACHE:
        return _TRANSLATION_CACHE[cache_key]

    # 500자 초과 시 문장 단위 분할
    chunks = _split_text(text, max_len=500)
    results = []

    for chunk in chunks:
        if not chunk.strip():
            continue
        try:
            params = {
                "q": chunk,
                "langpair": f"{src}|{tgt}",
                "de": "pipeline@infra-news.com",  # 등록 이메일로 한도 상향
            }
            resp = requests.get(MYMEMORY_URL, params=params, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                translated = data.get("responseData", {}).get("translatedText", "")
                if translated and translated != chunk:
                    results.append(translated)
                else:
                    results.append(chunk)  # 번역 실패 시 원문 유지
            time.sleep(0.3)  # rate limit 방지
        except Exception as e:
            log.debug(f"MyMemory 오류: {e}")
            results.append(chunk)

    result = " ".join(results).strip()
    if result and result != text:
        _TRANSLATION_CACHE[cache_key] = result
        return result
    return None


def _libretranslate(text: str, src: str, tgt: str) -> Optional[str]:
    """
    LibreTranslate 오픈소스 번역 API (최후 백업).
    
    여러 공개 인스턴스를 순서대로 시도.
    API key 불필요 (무료 공개 인스턴스).
    
    참고: 일부 인스턴스는 vi(베트남어) 미지원
    → 미지원 시 en→ko만 처리 가능
    """
    if not text or not text.strip():
        return None

    # LibreTranslate 언어 코드 매핑
    lang_map = {"ko": "ko", "en": "en", "vi": "vi", "auto": "auto"}
    lt_src = lang_map.get(src, "auto")
    lt_tgt = lang_map.get(tgt, "en")

    for instance_url in LIBRETRANSLATE_INSTANCES:
        try:
            payload = {
                "q": text[:3000],
                "source": lt_src,
                "target": lt_tgt,
                "format": "text",
            }
            resp = requests.post(
                f"{instance_url}/translate",
                json=payload, timeout=20
            )
            if resp.status_code == 200:
                data = resp.json()
                translated = data.get("translatedText", "")
                if translated and translated != text:
                    return translated
        except Exception as e:
            log.debug(f"LibreTranslate [{instance_url}] 오류: {e}")
            continue

    return None


def _split_text(text: str, max_len: int = 500) -> list[str]:
    """
    텍스트를 max_len 이하로 분할.
    문장 경계(마침표/줄바꿈)를 존중하여 분할.
    """
    if len(text) <= max_len:
        return [text]

    # 문장 분리 패턴: 마침표/느낌표/물음표 뒤 공백
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) + 1 <= max_len:
            current = (current + " " + sentence).strip() if current else sentence
        else:
            if current:
                chunks.append(current)
            # 단일 문장이 max_len 초과 시 강제 분할
            if len(sentence) > max_len:
                for i in range(0, len(sentence), max_len):
                    chunks.append(sentence[i:i+max_len])
            else:
                current = sentence

    if current:
        chunks.append(current)

    return chunks if chunks else [text]


def translate_text(text: str, src_lang: str = "auto", tgt_lang: str = "ko") -> Optional[str]:
    """
    다중 엔진 폴백 번역 (주 함수).
    
    번역 시도 순서:
      1. Google Translate (3회 재시도, 지수 백오프)
      2. MyMemory API
      3. LibreTranslate 공개 인스턴스
    
    Args:
        text: 번역할 텍스트
        src_lang: 소스 언어 코드 ("auto", "vi", "en")
        tgt_lang: 목표 언어 코드 ("ko", "en")
    
    Returns:
        번역된 텍스트 또는 None (모든 엔진 실패 시)
    """
    if not text or not text.strip():
        return None

    # 1순위: Google Translate
    result = _google_translate(text, src_lang, tgt_lang)
    if result:
        return result

    # 2순위: MyMemory
    log.debug(f"Google Translate 실패 — MyMemory 시도")
    result = _mymemory_translate(text, src_lang, tgt_lang)
    if result:
        return result

    # 3순위: LibreTranslate
    log.debug(f"MyMemory 실패 — LibreTranslate 시도")
    result = _libretranslate(text, src_lang, tgt_lang)
    if result:
        return result

    return None


# ══════════════════════════════════════════════════════════════════════════
#  AISummarizer 클래스 (main.py에서 호출)
# ══════════════════════════════════════════════════════════════════════════

class AISummarizer:
    """
    기사 번역/요약 처리 클래스.
    
    v3.0 변경사항:
    - Google Translate 재시도 로직 (지수 백오프)
    - User-Agent 로테이션
    - MyMemory + LibreTranslate 폴백
    - 번역 캐시로 중복 번역 방지
    - 엔진별 성공 통계 출력
    """

    def __init__(self):
        log.info("[AISummarizer] Google Translate v3.0 초기화 (다중 폴백)")
        self._stats = {"google": 0, "mymemory": 0, "libretranslate": 0, "failed": 0}

        # deep-translator 존재 여부 확인 (호환성 유지)
        try:
            from deep_translator import GoogleTranslator
            self._deep_translator_available = True
            log.info("[AISummarizer] deep-translator 확인 완료 (보조 가용)")
        except ImportError:
            self._deep_translator_available = False
            log.info("[AISummarizer] deep-translator 미설치 — 내장 엔진만 사용")

    def _detect_lang(self, text: str) -> str:
        """간단한 언어 감지 (ASCII 비율 기반)."""
        if not text:
            return "en"
        ascii_ratio = sum(1 for c in text if ord(c) < 128) / len(text)
        return "en" if ascii_ratio > 0.85 else "vi"

    def _translate_one(self, text: str, src: str, tgt: str) -> str:
        """
        단일 텍스트 번역 (엔진 폴백 포함).
        성공 엔진을 통계에 기록.
        """
        if not text or not text.strip():
            return ""

        # 1순위: Google Translate (내장 구현, 재시도 포함)
        result = _google_translate(text, src, tgt, retry=3)
        if result:
            self._stats["google"] += 1
            return result

        # 2순위: deep-translator (설치된 경우)
        if self._deep_translator_available:
            try:
                from deep_translator import GoogleTranslator
                dt_src = "auto" if src == "auto" else src
                dt_result = GoogleTranslator(source=dt_src, target=tgt).translate(text[:4500])
                if dt_result and dt_result != text:
                    self._stats["google"] += 1  # deep-translator도 Google 카운트
                    return dt_result
            except Exception as e:
                log.debug(f"deep-translator 실패: {e}")

        # 3순위: MyMemory
        result = _mymemory_translate(text, src, tgt)
        if result:
            self._stats["mymemory"] += 1
            return result

        # 4순위: LibreTranslate
        result = _libretranslate(text, src, tgt)
        if result:
            self._stats["libretranslate"] += 1
            return result

        self._stats["failed"] += 1
        return ""  # 모든 엔진 실패

    def summarize_articles(self, articles: list[dict]) -> list[dict]:
        """
        기사 목록 번역/요약 처리 (main.py Step 2에서 호출).
        
        처리 로직:
          - 베트남어(vi) 기사: vi→en, vi→ko 번역
          - 영어(en) 기사: EN 원본 보존, en→ko 번역만 수행
        
        Args:
            articles: 수집된 기사 목록 (title, summary 등 포함)
        
        Returns:
            번역 완료된 기사 목록
        """
        total = len(articles)
        log.info(f"[AISummarizer] {total}건 번역 시작")

        processed = []
        success_count = 0

        for i, article in enumerate(articles, 1):
            title_orig = article.get("title", "") or article.get("title_en", "") or ""
            title_vi   = article.get("title_vi", "")
            summary    = article.get("summary", "") or article.get("summary_en", "") or ""

            # 언어 감지
            src_lang = self._detect_lang(title_orig) if title_orig else "en"
            log.info(f"  [{i}/{total}] {src_lang.upper()} → EN/KO: {title_orig[:60]}...")

            title_ko  = ""
            title_en  = ""
            summary_ko = ""
            summary_en = ""

            if src_lang == "vi":
                # 베트남어 기사: vi→EN, vi→KO 번역
                title_en   = self._translate_one(title_orig,  "vi", "en") or title_orig
                title_ko   = self._translate_one(title_orig,  "vi", "ko") or title_en
                summary_en = self._translate_one(summary,     "vi", "en") if summary else ""
                summary_ko = self._translate_one(summary,     "vi", "ko") if summary else ""
                if not summary_en:
                    summary_en = summary
            else:
                # 영어 기사: EN 원본 보존, en→KO만 번역
                title_en   = title_orig
                title_ko   = self._translate_one(title_orig, "en", "ko") or title_orig
                summary_en = summary
                summary_ko = self._translate_one(summary, "en", "ko") if summary else ""

            # 번역 성공 여부 판단 (한글 포함 여부로 확인)
            has_ko = any('\uAC00' <= c <= '\uD7A3' for c in title_ko)
            if has_ko:
                success_count += 1

            # 기사 객체 갱신
            updated = article.copy()
            updated.update({
                "title_en":   title_en  or title_orig,
                "title_ko":   title_ko  or title_en or title_orig,
                "title_vi":   title_vi  or (title_orig if src_lang == "vi" else ""),
                "summary_en": summary_en or summary or "",
                "summary_ko": summary_ko or "",
                "summary_vi": article.get("summary_vi", "") or (summary if src_lang == "vi" else ""),
            })
            processed.append(updated)

            # rate limit 방지 (번역 엔진 과부하 방지)
            time.sleep(0.2)

        # ── 번역 통계 출력 ──────────────────────────────────────────────
        log.info(f"[AISummarizer] 번역 완료: {success_count}/{total}건 성공")
        log.info(f"  엔진별: Google={self._stats['google']} | "
                 f"MyMemory={self._stats['mymemory']} | "
                 f"LibreTranslate={self._stats['libretranslate']} | "
                 f"실패={self._stats['failed']}")

        return processed

    # ── 하위 호환: 단일 번역 함수 (레거시 호출 지원) ─────────────────────
    def translate(self, text: str, src: str = "auto", tgt: str = "ko") -> str:
        """레거시 호환용 단일 번역 함수."""
        return self._translate_one(text, src, tgt)
