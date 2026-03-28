"""
batch_translate.py
==================
기존 News Database의 번역 없는 기사를 하루 20개씩 순차 번역

실행 방법:
  python3 scripts/batch_translate.py          # 20건 번역 (기본)
  python3 scripts/batch_translate.py --batch 50  # 50건 번역

GitHub Actions yml에 추가 시:
  - name: Batch translate old articles
    run: python3 scripts/batch_translate.py --batch 20

진행 현황:
  - title_ko가 비어있는 기사를 오래된 순서로 20건씩 번역
  - 번역 완료 후 Excel 저장 및 GitHub 커밋
  - 2637건 / 20건 = 약 132회 실행 필요 (약 19주)
"""

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('BatchTranslate')


def translate_batch(batch_size: int = 20):
    """
    title_ko가 비어있는 기사를 오래된 순서부터 batch_size건 번역
    """
    try:
        import openpyxl
    except ImportError:
        logger.error("openpyxl 미설치")
        return

    EXCEL_PATH = Path("data/database/Vietnam_Infra_News_Database_Final.xlsx")
    if not EXCEL_PATH.exists():
        logger.error(f"Excel 파일 없음: {EXCEL_PATH}")
        return

    logger.info(f"[BatchTranslate] Excel 로드: {EXCEL_PATH}")
    wb = openpyxl.load_workbook(EXCEL_PATH)
    ws = wb.active

    # 헤더 인덱스 파악
    headers = [str(ws.cell(1, c).value or '').strip().lower()
               for c in range(1, ws.max_column + 1)]

    def col_idx(names):
        for n in names:
            if n in headers:
                return headers.index(n) + 1  # 1-based
        return None

    idx_title    = col_idx(['news title', 'news tittle', 'title'])
    idx_date     = col_idx(['date'])
    idx_title_ko = col_idx(['title_ko'])
    idx_title_en = col_idx(['title_en'])
    idx_title_vi = col_idx(['title_vi'])
    idx_sum_ko   = col_idx(['summary_ko'])
    idx_sum_en   = col_idx(['summary_en'])
    idx_sum_vi   = col_idx(['summary_vi'])
    idx_summary  = col_idx(['short summary', 'summary'])

    logger.info(f"  컬럼 매핑: title={idx_title}, title_ko={idx_title_ko}, date={idx_date}")

    if not all([idx_title, idx_title_ko]):
        logger.error("필수 컬럼을 찾을 수 없습니다")
        wb.close()
        return

    # 번역이 필요한 행 수집 (title_ko가 비어있는 행)
    untranslated = []
    for row_num in range(2, ws.max_row + 1):
        title_ko_val = ws.cell(row_num, idx_title_ko).value
        title_val    = ws.cell(row_num, idx_title).value
        if not title_ko_val and title_val:
            date_val = str(ws.cell(row_num, idx_date).value or '')[:10]
            untranslated.append((row_num, str(title_val), date_val))

    # 오래된 순서부터 처리 (날짜 오름차순)
    untranslated.sort(key=lambda x: x[2])

    total_untranslated = len(untranslated)
    to_translate = untranslated[:batch_size]

    logger.info(f"[BatchTranslate] 번역 필요: {total_untranslated}건 / 이번 배치: {len(to_translate)}건")

    if not to_translate:
        logger.info("[BatchTranslate] 번역할 기사 없음 - 완료!")
        wb.close()
        return

    # Google Translate 초기화
    try:
        from scripts.ai_summarizer import AISummarizer
        summarizer = AISummarizer()
    except Exception as e:
        logger.error(f"AISummarizer 초기화 실패: {e}")
        wb.close()
        return

    # 번역 실행
    success = 0
    for i, (row_num, title, date_val) in enumerate(to_translate, 1):
        logger.info(f"  [{i}/{len(to_translate)}] {date_val} | {title[:50]}...")

        try:
            # 단일 기사 번역
            article = {
                'title':    title,
                'summary':  str(ws.cell(row_num, idx_summary).value or '')[:300] if idx_summary else '',
                'date':     date_val,
                'url':      '',
                'sector':   '',
                'province': '',
                'source':   '',
                'area':     '',
            }

            result = summarizer.process_articles([article])
            if result:
                a = result[0]
                title_ko = a.get('title_ko', '')
                title_en = a.get('title_en', '')
                title_vi = a.get('title_vi', '')
                sum_ko   = a.get('summary_ko', '')
                sum_en   = a.get('summary_en', '')
                sum_vi   = a.get('summary_vi', '')

                # Excel에 번역 결과 저장
                if idx_title_ko: ws.cell(row_num, idx_title_ko).value = title_ko
                if idx_title_en: ws.cell(row_num, idx_title_en).value = title_en
                if idx_title_vi: ws.cell(row_num, idx_title_vi).value = title_vi
                if idx_sum_ko:   ws.cell(row_num, idx_sum_ko).value   = sum_ko
                if idx_sum_en:   ws.cell(row_num, idx_sum_en).value   = sum_en
                if idx_sum_vi:   ws.cell(row_num, idx_sum_vi).value   = sum_vi

                success += 1
                logger.info(f"    ✅ ko: {title_ko[:40]}")
            else:
                logger.warning(f"    ❌ 번역 결과 없음")

            # API 과부하 방지 딜레이
            time.sleep(1)

        except Exception as e:
            logger.error(f"    ❌ 번역 오류: {e}")
            continue

    # 저장
    wb.save(EXCEL_PATH)
    wb.close()

    remaining = total_untranslated - success
    logger.info(f"\n[BatchTranslate] 완료: {success}/{len(to_translate)}건 번역")
    logger.info(f"[BatchTranslate] 잔여: {remaining}건 (약 {remaining // batch_size + 1}회 실행 필요)")


def main():
    parser = argparse.ArgumentParser(description='Batch translate old articles')
    parser.add_argument('--batch', type=int, default=20,
                        help='번역할 기사 수 (기본값: 20)')
    args = parser.parse_args()

    translate_batch(batch_size=args.batch)


if __name__ == "__main__":
    main()
