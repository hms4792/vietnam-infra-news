#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
batch_translate.py
Excel DB에서 title_ko가 비어있는 기사를 배치 번역
[메모리항목15] 하루 20건씩 처리 (MyMemory API 한도 고려)
[메모리항목1] Google Translate (MyMemory 1차 + deep-translator 2차). Anthropic API 금지
"""
import os, hashlib, time
from pathlib import Path

EXCEL_PATH = os.environ.get('EXCEL_PATH', 'data/database/Vietnam_Infra_News_Database_Final.xlsx')
BATCH_SIZE = int(os.environ.get('BATCH_SIZE', 20))

def translate_text(text, target_lang='ko'):
    """MyMemory API 1차, deep-translator 2차 폴백"""
    if not text or len(text.strip()) < 3:
        return ''
    import requests
    # 1차: MyMemory API [메모리항목1]
    try:
        url = (f"https://api.mymemory.translated.net/get"
               f"?q={requests.utils.quote(str(text)[:500])}"
               f"&langpair=auto|{target_lang}")
        r = requests.get(url, timeout=10)
        data = r.json()
        result = data.get('responseData', {}).get('translatedText', '')
        if result and result != text and 'INVALID' not in str(result).upper():
            return result
    except Exception:
        pass
    # 2차: deep-translator
    try:
        from deep_translator import GoogleTranslator
        result = GoogleTranslator(source='auto', target=target_lang).translate(str(text)[:500])
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
        print(f"❌ Excel not found: {ep}")
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

    print(f"컬럼 확인: title={title_col}, title_ko={title_ko_col}")

    # title_ko 비어있는 행 찾기
    empty_rows = []
    for r in range(2, ws.max_row + 1):
        title = ws.cell(r, title_col).value
        tko   = ws.cell(r, title_ko_col).value
        if title and (not tko or str(tko).strip() == ''):
            empty_rows.append(r)

    total_empty = len(empty_rows)
    batch = empty_rows[:BATCH_SIZE]
    print(f"번역 미완료: {total_empty}건 | 이번 배치: {len(batch)}건")

    translated = 0
    DONE_FILL = PatternFill(start_color="E8F5E9", end_color="E8F5E9", fill_type="solid")

    for i, r in enumerate(batch):
        title   = str(ws.cell(r, title_col).value or '')
        summary = str(ws.cell(r, summary_col).value or '') if summary_col else ''

        try:
            # 언어 자동 감지 후 번역
            tko = translate_text(title, 'ko')
            ten = translate_text(title, 'en')
            tvi = translate_text(title, 'vi')
            sko = translate_text(summary[:300], 'ko') if summary else ''
            sen = translate_text(summary[:300], 'en') if summary else ''
            svi = translate_text(summary[:300], 'vi') if summary else ''

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
            print(f"  [{i+1}/{len(batch)}] ✅ {title[:50]}")

        except Exception as e:
            print(f"  [{i+1}/{len(batch)}] ❌ 오류: {e} | {title[:40]}")

        # API 과부하 방지
        if (i + 1) % 5 == 0:
            time.sleep(1)

    wb.save(ep)
    wb.close()
    print(f"\n완료: {translated}/{len(batch)}건 번역 | 잔여: {total_empty - translated}건")
    return translated

if __name__ == '__main__':
    run_batch()
