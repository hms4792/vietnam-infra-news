"""
main.py — v7.3 (Gemini Collector 연동 버전)
파이프라인 실행 순서 (변경 금지):
  Step1: collect_news() + collect_gemini_articles() ← news_collector.py & gemini_collector.py
  Step2: AISummarizer().process_articles()          ← scripts/ai_summarizer.py
  Step3: ExcelUpdater.update_all()                 ← scripts/excel_updater.py
  Step4: build_dashboard()                         ← scripts/build_dashboard.py
"""

import os
import sys
import logging
import argparse
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('main')

# ── 경로 설정 ─────────────────────────────────────────────
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.dirname(SCRIPTS_DIR)   

EXCEL_PATH    = os.path.join(ROOT_DIR, 'data', 'database',
                              'Vietnam_Infra_News_Database_Final.xlsx')
TEMPLATE_PATH = os.path.join(ROOT_DIR, 'templates', 'dashboard_template.html')
OUTPUT_PATH   = os.path.join(ROOT_DIR, 'docs', 'index.html')

# scripts/ 폴더를 import 경로에 추가
sys.path.insert(0, SCRIPTS_DIR)

from news_collector   import collect_news
from gemini_collector import collect_gemini_articles  # [추가] Gemini 수집기 연동
from ai_summarizer    import AISummarizer
from excel_updater    import ExcelUpdater
from build_dashboard  import build_dashboard


def main(hours_back: int = 24):
    start = datetime.utcnow()
    logger.info('=' * 60)
    logger.info(f'Vietnam Infra News Pipeline v7.3 시작 (최근 {hours_back}시간)')
    logger.info(f'EXCEL_PATH: {EXCEL_PATH}')
    logger.info('=' * 60)

    # ── Step 1: 뉴스 수집 (RSS/NewsData + Gemini 통합) ─────────
    logger.info('[Step 1/4] 뉴스 수집 (News + Gemini)...')
    try:
        articles = collect_news(hours_back=hours_back)
        
        # Gemini API 키가 존재하는 경우 보완 수집 병합 실행
        gemini_key = os.environ.get('GEMINI_API_KEY', '').strip()
        if gemini_key:
            gemini_articles = collect_gemini_articles(gemini_key)
            logger.info(f'  Gemini 보완 수집 완료: {len(gemini_articles)}건')
            articles.extend(gemini_articles)
        else:
            logger.warning('GEMINI_API_KEY 미설정으로 Gemini 수집 생략')
            
        logger.info(f'  통합 수집 완료: 총 {len(articles)}건')
    except Exception as e:
        logger.error(f'Step 1 실패: {e}')
        sys.exit(1)

    if not articles:
        logger.warning('수집 기사 없음 — 종료')
        return

    # ── Step 2: 번역/요약 (Google Translate) ─────────────────
    logger.info('[Step 2/4] 번역/요약 (Google Translate)...')
    try:
        summarizer = AISummarizer()
        articles   = summarizer.process_articles(articles)
        logger.info('  번역 완료')
    except Exception as e:
        logger.warning(f'번역 일부 실패 (원문 유지): {e}')

    # ── Step 3: Excel 업데이트 ───────────────────────────────
    logger.info('[Step 3/4] Excel DB 업데이트...')
    if not os.path.exists(EXCEL_PATH):
        logger.error(f'Excel 없음: {EXCEL_PATH}')
        sys.exit(1)

    try:
        updater = ExcelUpdater(EXCEL_PATH)
        updater.update_all(articles)
        logger.info('  Excel 업데이트 완료')
    except Exception as e:
        logger.warning(f"[Step 3 경고] Excel 업데이트 실패했으나 계속 진행: {e}")

    # ── Step 4: Dashboard 재생성 ─────────────────────────────
    logger.info('[Step 4/4] Dashboard 재생성...')
    try:
        build_dashboard(
            excel_path    = EXCEL_PATH,
            template_path = TEMPLATE_PATH,
            output_path   = OUTPUT_PATH,
        )
        logger.info('  Dashboard 완료')
    except Exception as e:
        logger.error(f'Step 4 실패 (Dashboard): {e}')

    elapsed = (datetime.utcnow() - start).total_seconds()
    logger.info(f'완료: {elapsed:.1f}초 | 통합 수집 {len(articles)}건')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--hours', type=int, default=24)
    args = parser.parse_args()
    main(hours_back=args.hours)
