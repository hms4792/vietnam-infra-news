"""
ai_summarizer.py
================
Claude API를 사용해 베트남어 기사를 3개국어로 번역/요약하는 모듈

Gemini 진단 수정사항 반영:
  1. anthropic 패키지 임포트 확인 및 명확한 에러 메시지
  2. 번역 결과를 반드시 title_en/ko/vi, summary_en/ko/vi 필드로 반환
  3. API 실패 시 구조화된 fallback 데이터 반환 (파이프라인 중단 방지)
"""

import json
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ── Claude API 모델 설정 ───────────────────────────────────
CLAUDE_MODEL   = "claude-haiku-4-5-20251001"   # 비용 효율적 모델
MAX_TOKENS     = 800
BATCH_SIZE     = 5    # 한 번에 처리할 기사 수 (API 부하 조절)
RETRY_COUNT    = 5    # API 실패 시 재시도 횟수
RETRY_DELAY    = 10.0  # 재시도 대기 시간(초)


class AISummarizer:
    """
    Claude API 기반 베트남어 → 3개국어 번역/요약기
    
    출력 필드 (반드시 모든 기사에 포함):
      - title_en:   영어 제목
      - title_ko:   한국어 제목
      - title_vi:   베트남어 제목 (원문)
      - summary_en: 영어 요약 (2~3문장)
      - summary_ko: 한국어 요약 (2~3문장)
      - summary_vi: 베트남어 요약 (2~3문장)
    """

    def __init__(self):
        self.api_key = os.environ.get('ANTHROPIC_API_KEY', '')
        self.client  = None
        self._init_client()

    def _init_client(self):
        """Anthropic 클라이언트 초기화"""
        if not self.api_key:
            logger.error(
                "[AISummarizer] ANTHROPIC_API_KEY 없음!\n"
                "  → GitHub Secrets에 ANTHROPIC_API_KEY 등록 필요\n"
                "  → workflow yml의 env에 ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }} 확인"
            )
            return

        try:
            # ★★★ Gemini 진단 #1: anthropic 패키지 필수 ★★★
            import anthropic
            self.client = anthropic.Anthropic(api_key=self.api_key)
            logger.info("[AISummarizer] Claude API 클라이언트 초기화 완료")
        except ImportError:
            logger.error(
                "[AISummarizer] anthropic 패키지 미설치!\n"
                "  → workflow yml의 pip install 목록에 'anthropic' 추가 필요\n"
                "  → pip install anthropic"
            )
        except Exception as e:
            logger.error(f"[AISummarizer] 클라이언트 초기화 실패: {e}")

    def process_articles(self, articles: list) -> list:
        """
        전체 기사 리스트 번역 처리
        
        Args:
            articles: 수집된 원문 기사 리스트
        Returns:
            번역 완료 기사 리스트 (title_en/ko/vi, summary_en/ko/vi 포함)
        """
        if not articles:
            return []

        if not self.client:
            logger.warning("[AISummarizer] API 클라이언트 없음 → fallback 모드")
            return [self._make_fallback(a) for a in articles]

        logger.info(f"[AISummarizer] {len(articles)}건 번역 시작 (배치 크기: {BATCH_SIZE})")

        processed = []
        total = len(articles)

        # 배치 처리: BATCH_SIZE 단위로 묶어 처리
        for i in range(0, total, BATCH_SIZE):
            batch = articles[i:i + BATCH_SIZE]
            batch_num = i // BATCH_SIZE + 1
            batch_total = (total + BATCH_SIZE - 1) // BATCH_SIZE

            logger.info(f"[AISummarizer] 배치 {batch_num}/{batch_total} 처리 중...")

            for article in batch:
                result = self._translate_single(article)
                processed.append(result)

            # API 호출 속도 제한 (Rate Limit) 방지
            if i + BATCH_SIZE < total:
                time.sleep(0.5)

        success = sum(
            1 for a in processed
            if a.get('title_en') and a['title_en'] != a.get('title', '')
        )
        logger.info(f"[AISummarizer] 번역 완료: {success}/{len(processed)}건 성공")
        return processed

    def _translate_single(self, article: dict) -> dict:
        """단일 기사 번역 (재시도 포함)"""
        title   = article.get('title', '')
        content = article.get('content', '') or article.get('summary', '') or ''
        sector  = article.get('sector', 'Infrastructure')

        # 제목이 없으면 번역 생략
        if not title.strip():
            return self._make_fallback(article)

        # ── Claude API 프롬프트 ─────────────────────────────
        prompt = f"""You are a professional Vietnamese infrastructure news translator.
Translate and summarize this Vietnamese news article into 3 languages.

Sector: {sector}
Title (Vietnamese): {title}
Content snippet: {content[:300] if content else 'N/A'}

Respond ONLY with valid JSON (no markdown, no explanation):
{{
  "title_en": "English title translation",
  "title_ko": "한국어 제목 번역",
  "title_vi": "Vietnamese original or cleaned title",
  "summary_en": "2-3 sentence English summary of the infrastructure news",
  "summary_ko": "2-3문장 한국어 요약",
  "summary_vi": "Tóm tắt 2-3 câu bằng tiếng Việt"
}}"""

        # 재시도 로직
        for attempt in range(RETRY_COUNT):
            try:
                response = self.client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=MAX_TOKENS,
                    messages=[{"role": "user", "content": prompt}]
                )

                raw_text = response.content[0].text.strip()

                # JSON 파싱
                # (모델이 간혹 ```json ... ``` 형태로 반환할 경우 제거)
                if raw_text.startswith('```'):
                    raw_text = raw_text.split('```')[1]
                    if raw_text.startswith('json'):
                        raw_text = raw_text[4:]
                raw_text = raw_text.strip()

                translated = json.loads(raw_text)

                # 필수 키 검증
                required = ['title_en', 'title_ko', 'title_vi',
                            'summary_en', 'summary_ko', 'summary_vi']
                if not all(k in translated for k in required):
                    raise ValueError(f"번역 응답에 필수 키 누락: {translated.keys()}")

                # 원본 데이터에 번역 결과 병합
                article.update(translated)
                return article

            except json.JSONDecodeError as e:
                logger.warning(f"[번역] JSON 파싱 실패 (시도 {attempt+1}/{RETRY_COUNT}): {e}")
                if attempt < RETRY_COUNT - 1:
                    time.sleep(RETRY_DELAY)

            except Exception as e:
                logger.warning(f"[번역] API 오류 (시도 {attempt+1}/{RETRY_COUNT}): {e}")
                if attempt < RETRY_COUNT - 1:
                    time.sleep(RETRY_DELAY * (attempt + 1))  # 점진적 대기

        # 모든 재시도 실패 → fallback
        logger.error(f"[번역] 최종 실패: {title[:50]}")
        return self._make_fallback(article)

    def _make_fallback(self, article: dict) -> dict:
        """
        번역 실패 시 fallback 데이터 생성
        - 원문을 VI 필드에, 영어 템플릿을 EN/KO 필드에 넣어
          파이프라인과 대시보드가 중단 없이 동작하도록 함
        """
        title   = article.get('title', '')
        sector  = article.get('sector', 'Infrastructure')
        summary = article.get('summary', '') or article.get('content', '')[:200] or ''

        article.setdefault('title_en',   title)   # 원문 그대로 (번역 실패)
        article.setdefault('title_ko',   title)
        article.setdefault('title_vi',   title)
        article.setdefault('summary_en', summary or f"{sector} project news in Vietnam.")
        article.setdefault('summary_ko', summary or f"베트남 {sector} 관련 뉴스.")
        article.setdefault('summary_vi', summary or f"Tin tức {sector} tại Việt Nam.")
        return article
