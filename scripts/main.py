"""
main.py — v7.2
파이프라인 실행 순서 (변경 금지):
  Step1: collect_news(hours_back)       ← scripts/news_collector.py
  Step2: AISummarizer().process_articles() ← scripts/ai_summarizer.py
  Step3: ExcelUpdater.update_all()      ← scripts/excel_updater.py
  Step4: build_dashboard()              ← scripts/build_dashboard.py

수정사항 (v7.2):
  - AISummarizer().summarize() → process_articles() 로 수정
  - BASE_DIR: scripts/ 안에 있으므로 상위 폴더(ROOT_DIR)를 별도 계산
  - EXCEL_PATH: ROOT_DIR 기준으로 설정
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
# main.py 위치: scripts/main.py
# ROOT_DIR: 저장소 루트 (scripts/ 의 상위)
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.dirname(SCRIPTS_DIR)   # ← scripts/ 상위 = 저장소 루트

EXCEL_PATH    = os.path.join(ROOT_DIR, 'data', 'database',
                              'Vietnam_Infra_News_Database_Final.xlsx')
TEMPLATE_PATH = os.path.join(ROOT_DIR, 'templates', 'dashboard_template.html')
OUTPUT_PATH   = os.path.join(ROOT_DIR, 'docs', 'index.html')

# scripts/ 폴더를 import 경로에 추가
sys.path.insert(0, SCRIPTS_DIR)

from news_collector  import collect_news
from ai_summarizer   import AISummarizer
from excel_updater   import ExcelUpdater
from build_dashboard import build_dashboard


def main(hours_back: int = 24):
    start = datetime.utcnow()
    logger.info('=' * 60)
    logger.info(f'Vietnam Infra News Pipeline v7.2 시작 (최근 {hours_back}시간)')
    logger.info(f'EXCEL_PATH: {EXCEL_PATH}')
    logger.info('=' * 60)

    # ── Step 1: 뉴스 수집 ────────────────────────────────────
    logger.info('[Step 1/4] 뉴스 수집...')
    try:
        articles = collect_news(hours_back=hours_back)
        logger.info(f'  수집 완료: {len(articles)}건')
    except Exception as e:
        logger.error(f'Step 1 실패: {e}')
        sys.exit(1)

    if not articles:
        logger.warning('수집 기사 없음 — 종료')
        return

    # ── Step 2: 번역/요약 (Google Translate) ─────────────────
    # 메서드: process_articles() — summarize() 아님
    logger.info('[Step 2/4] 번역/요약 (Google Translate)...')
    try:
        summarizer = AISummarizer()
        articles   = summarizer.process_articles(articles)  # ← process_articles
        logger.info('  번역 완료')
    except Exception as e:
        logger.warning(f'번역 일부 실패 (원문 유지): {e}')
        # 번역 실패해도 계속 진행 (기사 손실 방지)

    # ── Step 3: Excel 업데이트 ───────────────────────────────
    logger.info('[Step 3/4] Excel DB 업데이트...')
    if not os.path.exists(EXCEL_PATH):
        logger.error(f'Excel 없음: {EXCEL_PATH}')
        logger.error(f'  ROOT_DIR={ROOT_DIR}')
        logger.error(f'  존재하는지 확인: {os.path.exists(os.path.dirname(EXCEL_PATH))}')
        sys.exit(1)

    try:
        # ExcelUpdater.update_all() 은 통계 dict를 반환하지 않고, 엑셀 시트만 갱신합니다.
        updater = ExcelUpdater(EXCEL_PATH)   # ExcelManager 아님
        updater.update_all(articles)         # update() 아님, 반환값 사용 안 함
        logger.info('  Excel 업데이트 완료')
    except Exception as e:
        logger.error(f'Step 3 실패: {e}')
        sys.exit(1)

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
        # Dashboard 실패는 치명적이지 않음

    elapsed = (datetime.utcnow() - start).total_seconds()
    logger.info(f'완료: {elapsed:.1f}초 | 수집 {len(articles)}건')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--hours', type=int, default=24)
    args = parser.parse_args()
    main(hours_back=args.hours)
