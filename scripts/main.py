"""
Vietnam Infrastructure News Pipeline - Main Entry Point
=======================================================
파이프라인 실행 순서 (Gemini 진단 반영 최종 수정본):
  Step 1: 뉴스 수집 (베트남어 원문)
  Step 2: Claude AI 번역/요약 (한국어/영어/베트남어)  ← 핵심 수정
  Step 3: 번역 완료 데이터를 Excel에 저장            ← 순서 교정
  Step 4: 대시보드(HTML) 생성
  Step 5: GitHub Pages 배포

수정 이유:
  기존: 수집 직후 Excel 저장(원문) → 번역 시도 → 대시보드 생성
        => Excel에 베트남어 원문만 저장됨, 번역 데이터 누락
  수정: 수집 → 번역 완료 → 번역본 Excel 저장 → 대시보드 생성
        => Excel에 3개국어 데이터 정상 저장

데이터 유실 방지(Safety Net):
  - 번역 실패 시에도 원문(VI) 데이터는 Excel에 저장
  - 대시보드 생성 실패해도 Excel 커밋은 독립적으로 실행
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# ── 경로 설정 ──────────────────────────────────────────────
# 이 스크립트가 실행되는 위치에서 상위 폴더(프로젝트 루트)를 참조
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── 로깅 설정 ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),          # 콘솔 출력
        logging.FileHandler('pipeline.log', encoding='utf-8')  # 파일 저장
    ]
)
logger = logging.getLogger('MainPipeline')


# ════════════════════════════════════════════════════════════
# 헬퍼 함수: 각 스크립트 모듈 동적 임포트
# (설치 환경에 따라 import 실패 가능성 대비)
# ════════════════════════════════════════════════════════════

def safe_import(module_name: str, class_name: str = None):
    """모듈 임포트 실패 시 None 반환 (파이프라인 중단 방지)"""
    try:
        import importlib
        mod = importlib.import_module(module_name)
        if class_name:
            return getattr(mod, class_name)
        return mod
    except ImportError as e:
        logger.error(f"[IMPORT ERROR] {module_name}: {e}")
        return None


# ════════════════════════════════════════════════════════════
# STEP 1: 뉴스 수집
# ════════════════════════════════════════════════════════════

def step1_collect_news() -> list:
    """
    RSS 피드 및 웹 크롤링으로 베트남 인프라 뉴스 수집
    반환값: 수집된 원문 기사 리스트 (dict 형태)
    
    각 기사 dict 구조:
    {
        'title': '베트남어 원제목',
        'url': 'https://...',
        'source': '출처명',
        'date': '2026-03-28',
        'content': '본문 내용 (있을 경우)',
        'sector': '섹터명',
        'sector_score': 점수(int)
    }
    """
    logger.info("=" * 60)
    logger.info("STEP 1: 뉴스 수집 시작")
    logger.info("=" * 60)

    try:
        from scripts.news_collector import NewsCollector

        collector = NewsCollector()
        articles = collector.collect_all()   # 동기식 collect
        
        # 수집 결과 로깅
        logger.info(f"[Step1 완료] 수집 기사 수: {len(articles)}")
        
        # 원문 JSON 백업 저장 (디버깅용)
        _save_raw_backup(articles)
        
        return articles

    except Exception as e:
        logger.error(f"[Step1 실패] 뉴스 수집 오류: {e}", exc_info=True)
        return []


def _save_raw_backup(articles: list):
    """수집 원문을 JSON으로 백업 (데이터 유실 방지용)"""
    try:
        backup_dir = Path("data/raw")
        backup_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = backup_dir / f"raw_{ts}.json"
        with open(backup_path, 'w', encoding='utf-8') as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        logger.info(f"[Backup] 원문 백업 저장: {backup_path}")
    except Exception as e:
        logger.warning(f"[Backup] 원문 백업 실패 (계속 진행): {e}")


# ════════════════════════════════════════════════════════════
# STEP 2: Claude API로 3개국어 번역/요약
# ════════════════════════════════════════════════════════════

def step2_translate_articles(raw_articles: list) -> list:
    """
    Gemini 진단 수정사항 #1:
      - 기존: anthropic 패키지 미설치로 API 호출 불가 → fallback 모드로 원문 그대로 사용
      - 수정: anthropic 패키지 설치 확인 + 번역 후 processed_articles 반환
    
    Gemini 진단 수정사항 #2:
      - 기존: Step1 직후 Excel 저장(원문) → Step2 번역 실행
      - 수정: Step2 번역 완료 후 processed_articles를 Step3로 전달
    
    반환값: 번역 완료 기사 리스트
    각 기사에 추가되는 필드:
      - title_ko: 한국어 제목
      - title_en: 영어 제목
      - title_vi: 베트남어 제목 (원문)
      - summary_ko: 한국어 요약
      - summary_en: 영어 요약
      - summary_vi: 베트남어 요약
    """
    logger.info("=" * 60)
    logger.info("STEP 2: Claude API 번역/요약 시작")
    logger.info("=" * 60)

    if not raw_articles:
        logger.warning("[Step2] 수집된 기사 없음 - 번역 생략")
        return []

    # API 키 확인
    api_key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not api_key:
        logger.error("[Step2] ANTHROPIC_API_KEY 환경변수 미설정!")
        logger.warning("[Step2] 번역 없이 원문 데이터로 계속 진행")
        # fallback: 원문을 모든 언어 필드에 채움
        return _fallback_no_translation(raw_articles)

    # anthropic 패키지 설치 확인
    try:
        import anthropic  # noqa: F401 (설치 여부만 확인)
        logger.info("[Step2] anthropic 패키지 확인 완료")
    except ImportError:
        logger.error("[Step2] anthropic 패키지 미설치! pip install anthropic 필요")
        return _fallback_no_translation(raw_articles)

    try:
        from scripts.ai_summarizer import AISummarizer

        summarizer = AISummarizer()
        processed = summarizer.process_articles(raw_articles)

        # 번역 성공률 로깅
        translated = sum(
            1 for a in processed
            if a.get('title_en') and a['title_en'] != a.get('title', '')
        )
        logger.info(f"[Step2 완료] 번역 성공: {translated}/{len(processed)} 건")
        return processed

    except Exception as e:
        logger.error(f"[Step2 실패] 번역 오류: {e}", exc_info=True)
        return _fallback_no_translation(raw_articles)


def _fallback_no_translation(articles: list) -> list:
    """
    번역 실패 시 안전망:
    원문(VI)을 모든 언어 필드에 채워 파이프라인이 중단되지 않도록 함
    """
    logger.warning("[Fallback] 번역 실패 - 원문으로 대체")
    result = []
    for a in articles:
        title = a.get('title', '')
        summary = a.get('summary', '') or a.get('content', '')[:200]
        a.setdefault('title_ko', title)
        a.setdefault('title_en', title)
        a.setdefault('title_vi', title)
        a.setdefault('summary_ko', summary)
        a.setdefault('summary_en', summary)
        a.setdefault('summary_vi', summary)
        result.append(a)
    return result


# ════════════════════════════════════════════════════════════
# STEP 3: 번역 완료 데이터 → Excel 저장
# ════════════════════════════════════════════════════════════

def step3_save_to_excel(processed_articles: list) -> bool:
    """
    Gemini 진단 수정사항 #2 핵심:
      - 반드시 processed_articles (번역 완료본)를 받아 저장
      - raw_articles (원문)를 저장하는 기존 오류 수정
    
    반환값: 저장 성공 여부 (bool)
    """
    logger.info("=" * 60)
    logger.info("STEP 3: Excel 데이터베이스 저장")
    logger.info("=" * 60)

    if not processed_articles:
        logger.warning("[Step3] 저장할 기사 없음")
        return False

    try:
        from scripts.excel_manager import ExcelManager

        em = ExcelManager()
        # ↓ 반드시 processed_articles (번역 완료본) 전달!
        saved_count = em.update_database(processed_articles)
        logger.info(f"[Step3 완료] Excel 저장: {saved_count}건")
        return True

    except ImportError:
        # ExcelManager 모듈이 없을 경우 내장 함수 사용
        logger.warning("[Step3] ExcelManager 모듈 없음 - 내장 저장 사용")
        return _builtin_excel_save(processed_articles)

    except Exception as e:
        logger.error(f"[Step3 실패] Excel 저장 오류: {e}", exc_info=True)
        return False


def _builtin_excel_save(articles: list) -> bool:
    """
    ExcelManager 없을 때의 내장 Excel 저장 로직
    openpyxl을 직접 사용해 번역된 데이터를 저장
    """
    try:
        import openpyxl
        from pathlib import Path

        EXCEL_PATH = Path("data/database/Vietnam_Infra_News_Database_Final.xlsx")
        if not EXCEL_PATH.exists():
            logger.error(f"[BuiltinSave] Excel 파일 없음: {EXCEL_PATH}")
            return False

        wb = openpyxl.load_workbook(EXCEL_PATH)
        ws = wb.active

        # 헤더 행에서 컬럼 위치 파악
        headers = {cell.value: cell.column for cell in ws[1] if cell.value}
        logger.info(f"[BuiltinSave] 컬럼: {list(headers.keys())}")

        # 기존 URL 목록 (중복 방지)
        url_col = headers.get('Link') or headers.get('URL') or headers.get('url')
        existing_urls = set()
        if url_col:
            for row in ws.iter_rows(min_row=2, values_only=True):
                if row[url_col - 1]:
                    existing_urls.add(str(row[url_col - 1]).strip())

        # 신규 기사 추가
        added = 0
        for article in articles:
            url = article.get('url', '').strip()
            if url and url in existing_urls:
                continue  # 중복 건너뜀

            # 컬럼 매핑 (Excel 헤더명에 따라 조정)
            row_data = _map_article_to_row(article, headers, ws.max_column)
            ws.append(row_data)
            existing_urls.add(url)
            added += 1

        wb.save(EXCEL_PATH)
        logger.info(f"[BuiltinSave] {added}건 추가 완료 → {EXCEL_PATH}")
        return True

    except Exception as e:
        logger.error(f"[BuiltinSave] 오류: {e}", exc_info=True)
        return False


def _map_article_to_row(article: dict, headers: dict, max_col: int) -> list:
    """
    기사 dict → Excel 행 리스트로 변환
    헤더 컬럼명에 맞춰 데이터 배치
    """
    row = [''] * max_col

    # 컬럼명 → 데이터 매핑 테이블
    mapping = {
        'No':         lambda a: '',
        'Title':      lambda a: a.get('title_en') or a.get('title', ''),
        'title_ko':   lambda a: a.get('title_ko', ''),
        'title_en':   lambda a: a.get('title_en') or a.get('title', ''),
        'title_vi':   lambda a: a.get('title_vi') or a.get('title', ''),
        'Summary':    lambda a: a.get('summary_en', ''),
        'summary_ko': lambda a: a.get('summary_ko', ''),
        'summary_en': lambda a: a.get('summary_en', ''),
        'summary_vi': lambda a: a.get('summary_vi', ''),
        'Short summary': lambda a: a.get('summary_en', '')[:200],
        'Sector':     lambda a: a.get('sector', ''),
        'Date':       lambda a: a.get('date', ''),
        'Source':     lambda a: a.get('source', ''),
        'Link':       lambda a: a.get('url', ''),
        'URL':        lambda a: a.get('url', ''),
        'Area':       lambda a: a.get('area', ''),
        'Language':   lambda a: 'EN',
    }

    for col_name, col_idx in headers.items():
        if col_name in mapping and col_idx <= max_col:
            try:
                row[col_idx - 1] = mapping[col_name](article)
            except Exception:
                pass

    return row


# ════════════════════════════════════════════════════════════
# STEP 4: 대시보드(HTML) 생성
# ════════════════════════════════════════════════════════════

def step4_build_dashboard(processed_articles: list) -> bool:
    """
    Gemini 진단 수정사항 #3 반영:
    - 대시보드 HTML 카드에 data-ko / data-en / data-vi 속성 포함
    - 이 속성이 없으면 3개국어 버튼 JavaScript가 작동하지 않음
    """
    logger.info("=" * 60)
    logger.info("STEP 4: 대시보드 HTML 생성")
    logger.info("=" * 60)

    try:
        from scripts.dashboard_updater import DashboardUpdater

        updater = DashboardUpdater()
        # processed_articles에 번역 필드(title_ko/en/vi, summary_ko/en/vi)가 있어야 함
        result = updater.generate(processed_articles)
        logger.info(f"[Step4 완료] 대시보드 생성: {result}")
        return True

    except Exception as e:
        logger.error(f"[Step4 실패] 대시보드 생성 오류: {e}", exc_info=True)
        return False


# ════════════════════════════════════════════════════════════
# 메인 실행부
# ════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='Vietnam Infra News Pipeline')
    parser.add_argument(
        '--mode',
        choices=['full', 'collect-only', 'translate-only', 'dashboard-only'],
        default='full',
        help='실행 모드 선택'
    )
    parser.add_argument(
        '--full',
        action='store_true',
        help='전체 파이프라인 실행 (--mode full 과 동일)'
    )
    args = parser.parse_args()

    if args.full:
        args.mode = 'full'

    logger.info("╔══════════════════════════════════════════════════════╗")
    logger.info("║   Vietnam Infrastructure News Pipeline               ║")
    logger.info(f"║   실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                   ║")
    logger.info(f"║   모드: {args.mode:<46}║")
    logger.info("╚══════════════════════════════════════════════════════╝")

    # ─────────────────────────────────────────────────────────
    # 핵심 수정: 올바른 실행 순서
    #   [1] 수집 → [2] 번역 → [3] 저장 → [4] 대시보드
    #
    # 기존 오류 패턴 (절대 금지):
    #   [1] 수집 → [3] 저장(원문!) → [2] 번역 → [4] 대시보드
    # ─────────────────────────────────────────────────────────

    excel_saved = False
    processed_articles = []

    if args.mode in ('full', 'collect-only'):
        # ① 뉴스 수집
        raw_articles = step1_collect_news()

        if args.mode == 'collect-only':
            logger.info(f"[collect-only] 수집 완료: {len(raw_articles)}건")
            return

        # ② Claude API 번역/요약 (수집 직후 바로 실행)
        processed_articles = step2_translate_articles(raw_articles)

        # ③ 번역 완료 데이터를 Excel에 저장 (원문 저장 금지!)
        excel_saved = step3_save_to_excel(processed_articles)

        # ④ 대시보드 생성 (Excel 저장과 독립적으로 실행)
        step4_build_dashboard(processed_articles)

    elif args.mode == 'translate-only':
        # 수집 없이 번역만 재실행 (JSON 백업에서 로드)
        raw_articles = _load_latest_raw_backup()
        processed_articles = step2_translate_articles(raw_articles)
        step3_save_to_excel(processed_articles)
        step4_build_dashboard(processed_articles)

    elif args.mode == 'dashboard-only':
        # 대시보드만 재생성
        processed_articles = _load_from_excel()
        step4_build_dashboard(processed_articles)

    # 최종 결과 요약
    logger.info("=" * 60)
    logger.info("파이프라인 실행 완료")
    logger.info(f"  - 처리 기사: {len(processed_articles)}건")
    logger.info(f"  - Excel 저장: {'성공' if excel_saved else '실패/생략'}")
    logger.info("=" * 60)


def _load_latest_raw_backup() -> list:
    """가장 최신 원문 백업 JSON 로드"""
    raw_dir = Path("data/raw")
    if not raw_dir.exists():
        return []
    files = sorted(raw_dir.glob("raw_*.json"), reverse=True)
    if not files:
        return []
    with open(files[0], encoding='utf-8') as f:
        return json.load(f)


def _load_from_excel() -> list:
    """Excel에서 기사 데이터 로드 (dashboard-only 모드용)"""
    try:
        from scripts.excel_manager import ExcelManager
        em = ExcelManager()
        return em.load_recent_articles(days=7)
    except Exception:
        return []


if __name__ == "__main__":
    main()
