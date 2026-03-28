"""
Vietnam Infrastructure News Pipeline - Main Entry Point
=======================================================
파이프라인 실행 순서:
  Step 1: 뉴스 수집 (news_collector.py의 collect_news() 함수 방식)
  Step 2: Google Translate 번역/요약 (3개국어)
  Step 3: 번역 완료 데이터를 Excel에 저장 (9개 시트)
  Step 4: 대시보드(HTML) 생성 (dashboard_template.html 템플릿 사용)
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('pipeline.log', encoding='utf-8')
    ]
)
logger = logging.getLogger('MainPipeline')


# ════════════════════════════════════════════════════════════
# STEP 1: 뉴스 수집
# news_collector.py는 클래스가 아닌 collect_news(hours_back) 함수 방식
# ════════════════════════════════════════════════════════════

def step1_collect_news(hours_back: int = 168) -> list:
    logger.info("=" * 60)
    logger.info(f"STEP 1: 뉴스 수집 시작 (최근 {hours_back}시간 = {hours_back//24}일)")
    logger.info("=" * 60)

    try:
        import importlib, sys as _sys
        _sys.path.insert(0, '.')
        import scripts.news_collector as nc

        # collect_news() 함수 직접 호출 → (count, articles, stats) 반환
        cnt, articles, stats = nc.collect_news(hours_back=hours_back)

        logger.info(f"[Step1 완료] 수집 기사 수: {len(articles)}")
        _save_raw_backup(articles)
        return articles

    except Exception as e:
        logger.error(f"[Step1 실패] 뉴스 수집 오류: {e}", exc_info=True)
        return []


def _save_raw_backup(articles: list):
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
# STEP 2: Google Translate 3개국어 번역/요약
# Anthropic API 사용 안 함 (Connection error 문제)
# MyMemory API 1차 + deep-translator 2차 방식
# ════════════════════════════════════════════════════════════

def step2_translate_articles(raw_articles: list) -> list:
    logger.info("=" * 60)
    logger.info("STEP 2: Google Translate 번역 시작")
    logger.info("=" * 60)

    if not raw_articles:
        logger.warning("[Step2] 수집된 기사 없음 - 번역 생략")
        return []

    try:
        from scripts.ai_summarizer import AISummarizer

        summarizer = AISummarizer()
        processed = summarizer.process_articles(raw_articles)

        translated = sum(
            1 for a in processed
            if a.get('title_en') and a['title_en'] != a.get('title', '')
        )
        logger.info(f"[Step2 완료] 번역 성공: {translated}/{len(processed)}건")
        return processed

    except Exception as e:
        logger.error(f"[Step2 실패] 번역 오류: {e}", exc_info=True)
        return _fallback_no_translation(raw_articles)


def _fallback_no_translation(articles: list) -> list:
    logger.warning("[Fallback] 번역 실패 - 원문으로 대체")
    for a in articles:
        title   = a.get('title', '')
        summary = a.get('summary', '') or ''
        a.setdefault('title_ko',   title)
        a.setdefault('title_en',   title)
        a.setdefault('title_vi',   title)
        a.setdefault('summary_ko', summary)
        a.setdefault('summary_en', summary)
        a.setdefault('summary_vi', summary)
    return articles


# ════════════════════════════════════════════════════════════
# STEP 3: Excel 9개 시트 저장
# excel_updater.py 사용 (14컬럼 헤더 포함)
# ════════════════════════════════════════════════════════════

def step3_save_to_excel(processed_articles: list) -> bool:
    logger.info("=" * 60)
    logger.info("STEP 3: Excel 데이터베이스 저장")
    logger.info("=" * 60)

    if not processed_articles:
        logger.warning("[Step3] 저장할 기사 없음")
        return False

    try:
        from scripts.excel_updater import ExcelUpdater

        EXCEL_PATH = Path("data/database/Vietnam_Infra_News_Database_Final.xlsx")
        updater = ExcelUpdater(EXCEL_PATH)
        result  = updater.update_all(processed_articles)
        logger.info(f"[Step3 완료] Excel 전체 시트 업데이트")
        return result

    except Exception as e:
        logger.error(f"[Step3 실패] Excel 저장 오류: {e}", exc_info=True)
        return False


# ════════════════════════════════════════════════════════════
# STEP 4: 대시보드 HTML 생성
# dashboard_template.html 템플릿 사용 (기존 기능 유지)
# /*__BACKEND_DATA__*/[] 플레이스홀더에 전체 누적 기사 주입
# ════════════════════════════════════════════════════════════

def step4_build_dashboard(processed_articles: list) -> bool:
    logger.info("=" * 60)
    logger.info("STEP 4: 대시보드 HTML 생성")
    logger.info("=" * 60)

    try:
        from scripts.dashboard_updater import DashboardUpdater

        updater = DashboardUpdater()
        result  = updater.generate(processed_articles)
        logger.info(f"[Step4 완료] docs/index.html")
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
        choices=['full', 'collect-only', 'dashboard-only'],
        default='full'
    )
    parser.add_argument('--full', action='store_true')
    parser.add_argument(
        '--hours-back',
        type=int,
        default=168,
        dest='hours_back'
    )
    args = parser.parse_args()

    if args.full:
        args.mode = 'full'

    logger.info("╔══════════════════════════════════════════════════════╗")
    logger.info("║   Vietnam Infrastructure News Pipeline               ║")
    logger.info(f"║   실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}                   ║")
    logger.info(f"║   모드:     {args.mode:<46}║")
    logger.info(f"║   수집기간: {args.hours_back}시간 ({args.hours_back//24}일)                              ║")
    logger.info("╚══════════════════════════════════════════════════════╝")

    excel_saved        = False
    processed_articles = []

    if args.mode in ('full', 'collect-only'):
        # Step1 → Step2 → Step3 → Step4 순서 엄수
        raw_articles = step1_collect_news(hours_back=args.hours_back)

        if args.mode == 'collect-only':
            logger.info(f"[collect-only] 수집 완료: {len(raw_articles)}건")
            return

        processed_articles = step2_translate_articles(raw_articles)
        excel_saved        = step3_save_to_excel(processed_articles)
        step4_build_dashboard(processed_articles)

    elif args.mode == 'dashboard-only':
        step4_build_dashboard([])

    logger.info("=" * 60)
    logger.info("파이프라인 실행 완료")
    logger.info(f"  처리 기사: {len(processed_articles)}건")
    logger.info(f"  Excel 저장: {'성공' if excel_saved else '실패/생략'}")
    logger.info("=" * 60)


def _load_latest_raw_backup() -> list:
    raw_dir = Path("data/raw")
    if not raw_dir.exists():
        return []
    files = sorted(raw_dir.glob("raw_*.json"), reverse=True)
    if not files:
        return []
    with open(files[0], encoding='utf-8') as f:
        return json.load(f)


if __name__ == "__main__":
    main()
