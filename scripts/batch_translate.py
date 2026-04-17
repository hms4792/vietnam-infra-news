#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
batch_translate.py
Excel DB에서 title_ko가 비어있는 기사를 배치 번역

번역 폴백 체인 (v5.7):
  1순위: DeepL API Free   (월 500K자, 품질 최상) — DEEPL_API_KEY 환경변수 필요
  2순위: MyMemory         (일 5,000자, WARNING 필터)
  3순위: deep-translator  (Google Translate 비공식)

- 하루 20건씩 처리
- 2025년 이후 기사 우선, 최신순 역순
- Anthropic API 금지
"""
import sys
import os
import time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from pathlib import Path

EXCEL_PATH    = os.environ.get('EXCEL_PATH', 'data/database/Vietnam_Infra_News_Database_Final.xlsx')
BATCH_SIZE    = int(os.environ.get('BATCH_SIZE', 40))  # 14주→7주 단축
DEEPL_API_KEY = os.environ.get('DEEPL_API_KEY', '').strip()

# DeepL 언어 코드 매핑
_DEEPL_LANG = {'ko': 'KO', 'en': 'EN-US', 'vi': 'VI'}
_deepl_ok   = True  # 한도 초과 시 False


def _try_deepl(text, target_lang):
    """DeepL API Free 번역. 실패/한도초과 시 '' 반환."""
    global _deepl_ok
    if not DEEPL_API_KEY or not _deepl_ok:
        return ''
    import requests
    try:
        resp = requests.post(
            'https://api-free.deepl.com/v2/translate',
            headers={'Authorization': f'DeepL-Auth-Key {DEEPL_API_KEY}'},
            data={'text': str(text)[:500],
                  'target_lang': _DEEPL_LANG.get(target_lang, target_lang.upper())},
            timeout=10,
        )
        if resp.status_code == 456:
            print("  [DeepL] 월 한도 초과 → MyMemory 폴백")
            _deepl_ok = False
            return ''
        if resp.status_code != 200:
            return ''
        result = resp.json().get('translations', [{}])[0].get('text', '')
        return result if result and result != text else ''
    except Exception:
        return ''


def _is_warning(v):
    """MyMemory 경고 메시지 / 오번역 패턴 감지"""
    if not v:
        return False
    u = str(v).upper()
    # MyMemory API 경고 메시지
    if any(k in u for k in ('MYMEMORY WARNING', 'PLEASE SELECT',
                             'YOU USED ALL', 'INVALID', 'QUERY LENGTH')):
        return True
    # 반복 패턴 감지 — "베트남, 베트남, 베트남..." 형태
    parts = [p.strip() for p in str(v).split(',')]
    if len(parts) >= 3 and len(set(parts[:3])) == 1 and parts[0]:
        return True
    # 단어 반복 감지 — "Vietnam Vietnam Vietnam" 형태
    words = str(v).split()
    if len(words) >= 4 and len(set(words[:4])) == 1:
        return True
    return False


def translate_text(text, target_lang='ko'):
    """
    3단계 폴백 번역:
      DeepL (1순위) → MyMemory (2순위) → Google (3순위)
    """
    if not text or len(str(text).strip()) < 3:
        return ''
    import requests

    # 1순위: DeepL
    result = _try_deepl(text, target_lang)
    if result:
        return result

    # 2순위: MyMemory
    try:
        url = (
            "https://api.mymemory.translated.net/get"
            "?q=" + requests.utils.quote(str(text)[:500]) +
            "&langpair=auto|" + target_lang
        )
        r      = requests.get(url, timeout=10)
        result = r.json().get('responseData', {}).get('translatedText', '')
        if result and not _is_warning(result) and result != text:
            return result
    except Exception:
        pass

    # 3순위: Google (deep-translator)
    try:
        from deep_translator import GoogleTranslator
        result = GoogleTranslator(
            source='auto', target=target_lang
        ).translate(str(text)[:500])
        if result:
            return result
    except Exception:
        pass

    return text


def run_batch():
    import openpyxl
    from openpyxl.styles import PatternFill

    ep = Path(EXCEL_PATH)
    if not ep.exists():
        print(f"Excel not found: {ep}")
        return 0

    print(f"Excel: {ep}")
    wb = openpyxl.load_workbook(ep)
    ws = wb.active

    # 헤더에서 컬럼 위치 확인
    headers = {}
    for c in range(1, ws.max_column + 1):
        h = str(ws.cell(1, c).value or '').strip()
        if h:
            headers[h] = c

    title_col    = headers.get('News Title', 4)
    title_ko_col = headers.get('title_ko', 9)
    title_en_col = headers.get('title_en', 10)
    title_vi_col = headers.get('title_vi', 11)
    sum_ko_col   = headers.get('summary_ko', 12)
    sum_en_col   = headers.get('summary_en', 13)
    sum_vi_col   = headers.get('summary_vi', 14)
    summary_col  = headers.get('Short Summary', 8)
    date_col     = headers.get('Date', 5)

    print(f"컬럼 확인: title={title_col}, title_ko={title_ko_col}, date={date_col}")

    # title_ko 비어있는 행 찾기
    empty_rows = []
    for r in range(2, ws.max_row + 1):
        title = ws.cell(r, title_col).value
        tko   = ws.cell(r, title_ko_col).value
        # 오번역 감지 (반복 패턴) — 공란 처리하여 재번역 대상 포함
        if tko and _is_warning(tko):
            ws.cell(r, title_ko_col).value = ''
            tko = ''
        if title and (not tko or str(tko).strip() == ''):
            empty_rows.append(r)

    # 2025년 이후 기사 우선, 최신순 역순 (2026년 -> 2025년 -> 2024년 이전)
    priority = []
    others   = []
    for r in empty_rows:
        date_val = str(ws.cell(r, date_col).value or '')[:10]
        if date_val >= '2025-01-01':
            priority.append((r, date_val))
        else:
            others.append((r, date_val))

    priority.sort(key=lambda x: x[1], reverse=True)
    others.sort(key=lambda x: x[1], reverse=True)
    empty_rows = [r for r, _ in priority] + [r for r, _ in others]

    total_empty = len(empty_rows)
    batch       = empty_rows[:BATCH_SIZE]
    print(f"번역 미완료: {total_empty}건 (2025년 이후: {len(priority)}건) | 이번 배치: {len(batch)}건")

    translated = 0
    api_limit  = False  # API 한도 초과 플래그
    DONE_FILL  = PatternFill(start_color="E8F5E9", end_color="E8F5E9", fill_type="solid")

    for i, r in enumerate(batch):
        title   = str(ws.cell(r, title_col).value or '')
        summary = str(ws.cell(r, summary_col).value or '') if summary_col else ''

        # API 한도 초과 후 나머지 건너뜀
        if api_limit:
            print(f"  [{i+1}/{len(batch)}] SKIP (API limit reached)")
            continue

        try:
            tko = translate_text(title, 'ko')
            ten = translate_text(title, 'en')
            tvi = translate_text(title, 'vi')
            sko = translate_text(summary[:300], 'ko') if summary else ''
            sen = translate_text(summary[:300], 'en') if summary else ''
            svi = translate_text(summary[:300], 'vi') if summary else ''

            # 번역 경고/오번역 감지 — 전역 _is_warning() 사용
            if any(_is_warning(v) for v in [tko, ten, tvi] if v):
                api_limit = True
                print(f"  [{i+1}/{len(batch)}] SKIP (API limit) {title[:40]}")
                continue

            ws.cell(r, title_ko_col).value = tko
            ws.cell(r, title_en_col).value = ten
            ws.cell(r, title_vi_col).value = tvi
            ws.cell(r, sum_ko_col).value   = sko
            ws.cell(r, sum_en_col).value   = sen
            ws.cell(r, sum_vi_col).value   = svi

            # 번역 완료 표시 (연초록)
            for c in range(1, ws.max_column + 1):
                ws.cell(r, c).fill = DONE_FILL

            translated += 1
            print(f"  [{i+1}/{len(batch)}] OK {title[:50]}")

        except Exception as e:
            print(f"  [{i+1}/{len(batch)}] ERROR: {e} | {title[:40]}")

        # API 과부하 방지
        if (i + 1) % 5 == 0:
            time.sleep(1)

    wb.save(ep)
    wb.close()
    print(f"\n완료: {translated}/{len(batch)}건 번역 | 잔여: {total_empty - translated}건 (2025년~ 기준)")
    return translated


if __name__ == '__main__':
    run_batch()
