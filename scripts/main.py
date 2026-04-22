"""
main.py — v7.1
파이프라인 실행 순서 (변경 금지):
  Step1: collect_news(hours_back)       ← scripts/news_collector.py
  Step2: AISummarizer().summarize()     ← scripts/ai_summarizer.py (Google Translate)
  Step3: ExcelUpdater.update_all()      ← scripts/excel_updater.py
  Step4: build_dashboard.py 호출        ← scripts/build_dashboard.py

대상 파일: data/database/Vietnam_Infra_News_Database_Final.xlsx
"""

import os, sys, logging, argparse
from datetime import datetime

logging.basicConfig(level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger('main')

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
EXCEL_PATH = os.path.join(BASE_DIR, 'data', 'database',
                          'Vietnam_Infra_News_Database_Final.xlsx')

# scripts/ 폴더를 import 경로에 추가
sys.path.insert(0, os.path.join(BASE_DIR, 'scripts'))

from news_collector   import collect_news
from ai_summarizer    import AISummarizer
from excel_updater    import ExcelUpdater   # 클래스명 ExcelUpdater (ExcelManager 없음)
from build_dashboard  import build_dashboard


def main(hours_back: int = 24):
    start = datetime.utcnow()
    logger.info("=" * 60)
    logger.info(f"Vietnam Infra News Pipeline v7.1 시작 (최근 {hours_back}시간)")
    logger.info("=" * 60)

    # ── Step 1: 뉴스 수집 ────────────────────────────────
    logger.info("[Step 1/4] 뉴스 수집...")
    try:
        articles = collect_news(hours_back=hours_back)
        logger.info(f"  수집 완료: {len(articles)}건")
    except Exception as e:
        logger.error(f"Step 1 실패: {e}"); sys.exit(1)

    if not articles:
        logger.warning("수집 기사 없음 — 종료")
        return

    # ── Step 2: 번역/요약 (Google Translate, Anthropic 금지) ──
    logger.info("[Step 2/4] 번역/요약 (Google Translate)...")
    try:
        # AISummarizer: ANTHROPIC_API_KEY 체크 없음, Google Translate만 사용
        summarizer = AISummarizer()
        articles   = summarizer.summarize(articles)
        logger.info("  번역 완료")
    except Exception as e:
        logger.warning(f"번역 일부 실패 (원문 유지): {e}")

    # ── Step 3: Excel 업데이트 ────────────────────────────
    logger.info("[Step 3/4] Excel DB 업데이트...")
    try:
        updater = ExcelUpdater(EXCEL_PATH)   # ExcelManager 아님
        stats   = updater.update_all(articles)  # update() 아님
        for k, v in stats.items():
            logger.info(f"  [{k}] {v}")
    except FileNotFoundError:
        logger.error(f"Excel 없음: {EXCEL_PATH}"); sys.exit(1)
    except Exception as e:
        logger.error(f"Step 3 실패: {e}"); sys.exit(1)

    # ── Step 4: Dashboard 재생성 ──────────────────────────
    logger.info("[Step 4/4] Dashboard 재생성...")
    try:
        build_dashboard(
            excel_path    = EXCEL_PATH,
            template_path = os.path.join(BASE_DIR, 'templates', 'dashboard_template.html'),
            output_path   = os.path.join(BASE_DIR, 'docs', 'index.html'),
        )
        logger.info("  Dashboard 완료")
    except Exception as e:
        logger.error(f"Step 4 실패: {e}")

    elapsed = (datetime.utcnow() - start).total_seconds()
    logger.info(f"완료: {elapsed:.1f}초 | 수집 {len(articles)}건")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--hours', type=int, default=24, help='수집 기간(시간)')
    args = parser.parse_args()
    main(hours_back=args.hours)
