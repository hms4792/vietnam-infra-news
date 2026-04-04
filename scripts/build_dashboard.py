#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_dashboard.py
==================
dashboard_updater.py 우회 — Excel 직접 읽기 → docs/index.html 재빌드

[메모리항목2] templates/dashboard_template.html → docs/index.html
             /*__BACKEND_DATA__*/[] 플레이스홀더에 주입
"""

import json, os, sys, re
from datetime import datetime
from pathlib import Path

try:
    import openpyxl
except ImportError:
    print("ERROR: openpyxl not installed")
    sys.exit(1)

EXCEL_PATH    = Path(os.environ.get('EXCEL_PATH',
                    'data/database/Vietnam_Infra_News_Database_Final.xlsx'))
TEMPLATE_PATH = Path('templates/dashboard_template.html')
OUTPUT_PATH   = Path('docs/index.html')
PLACEHOLDER   = '/*__BACKEND_DATA__*/[]'

SECTOR_TO_AREA = {
    'Waste Water':'Environment','Water Supply/Drainage':'Environment',
    'Solid Waste':'Environment','Power':'Energy Develop.',
    'Oil & Gas':'Energy Develop.','Transport':'Urban Develop.',
    'Industrial Parks':'Urban Develop.','Smart City':'Urban Develop.',
    'Construction':'Urban Develop.','Urban Development':'Urban Develop.',
}

def normalize_area(area_val, sector_val):
    a = str(area_val or '').lower()
    if 'environ' in a: return 'Environment'
    if 'energy'  in a: return 'Energy Develop.'
    if 'urban'   in a: return 'Urban Develop.'
    return SECTOR_TO_AREA.get(str(sector_val or ''), 'Urban Develop.')

def clean(v):
    if v is None: return ''
    s = str(v).strip()
    # JSON 안전: 줄바꿈·탭 등 제어문자 공백으로 치환
    s = re.sub(r'[\x00-\x1f\x7f]', ' ', s)
    # 연속 공백 정리
    s = re.sub(r'  +', ' ', s).strip()
    return s

def load_articles():
    if not EXCEL_PATH.exists():
        print(f"ERROR: Excel 파일 없음: {EXCEL_PATH}")
        sys.exit(1)

    print(f"Excel 읽기: {EXCEL_PATH} ({EXCEL_PATH.stat().st_size:,} bytes)")
    wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True, data_only=True)
    ws = wb['News Database'] if 'News Database' in wb.sheetnames else wb.active

    # 헤더 인덱스 매핑
    header_row = next(ws.iter_rows(min_row=1, max_row=1, values_only=True))
    col = {}
    for i, h in enumerate(header_row):
        if h:
            col[str(h).strip().lower().replace(' ','').replace('_','')] = i

    def get(row, *keys):
        for k in keys:
            k2 = k.lower().replace(' ','').replace('_','')
            if k2 in col and col[k2] < len(row):
                v = row[col[k2]]
                if v is not None:
                    s = clean(v)
                    if s:
                        return s
        return ''

    articles = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        title_raw = get(row, 'News Title', 'title', 'NewTitle')
        if not title_raw:
            continue

        date_raw = row[col.get('date', 4)] if 'date' in col else None
        if hasattr(date_raw, 'strftime'):
            date_str = date_raw.strftime('%Y-%m-%d')
        else:
            date_str = clean(date_raw)[:10] if date_raw else ''

        area_val   = get(row, 'Area')
        sector_val = get(row, 'Business Sector', 'Sector')

        title_ko = get(row, 'title_ko')
        title_en = get(row, 'title_en')
        title_vi = get(row, 'title_vi')
        sum_ko   = get(row, 'summary_ko')
        sum_en   = get(row, 'summary_en')
        sum_vi   = get(row, 'summary_vi')
        raw_sum  = get(row, 'Short Summary', 'summary')

        articles.append({
            'id':       len(articles) + 1,
            'title':    {
                'ko': title_ko or title_raw,
                'en': title_en or title_raw,
                'vi': title_vi or title_raw,
            },
            'summary':  {
                'ko': sum_ko or raw_sum,
                'en': sum_en or raw_sum,
                'vi': sum_vi or raw_sum,
            },
            'sector':   sector_val,
            'area':     normalize_area(area_val, sector_val),
            'province': get(row, 'Province') or 'Vietnam',
            'source':   get(row, 'Source'),
            'date':     date_str,
            'url':      get(row, 'Link', 'URL', 'url'),
        })

    wb.close()
    return articles


def build():
    articles = load_articles()
    total    = len(articles)
    print(f"  총 {total}건 로드")
    if total == 0:
        print("ERROR: 기사 없음"); sys.exit(1)

    articles.sort(key=lambda a: a.get('date','') or '', reverse=True)
    latest = articles[0]['date'] if articles else ''
    trans  = sum(1 for a in articles
                 if a['title'].get('ko') != a['title'].get('en'))
    print(f"  최신: {latest}")
    print(f"  번역: {trans}건 ({trans/total:.1%})")

    # JSON 직렬화
    json_str     = json.dumps(articles, ensure_ascii=False, separators=(',',':'))
    backend_data = '/*__BACKEND_DATA__*/' + json_str

    # 검증
    try:
        json.loads(json_str)
        print(f"  JSON 검증 [OK] ({len(json_str):,} bytes)")
    except json.JSONDecodeError as e:
        print(f"  JSON 검증 [ERROR] {e}")
        sys.exit(1)

    if not TEMPLATE_PATH.exists():
        print(f"ERROR: 템플릿 없음: {TEMPLATE_PATH}"); sys.exit(1)

    print(f"\n템플릿 읽기: {TEMPLATE_PATH}")
    with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    if PLACEHOLDER not in html:
        print(f"ERROR: 플레이스홀더 없음: '{PLACEHOLDER}'"); sys.exit(1)

    html_out = html.replace(PLACEHOLDER, backend_data)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.write(html_out)

    size = OUTPUT_PATH.stat().st_size
    print(f"\n[OK] 저장 완료: {OUTPUT_PATH} ({size:,} bytes)")
    print(f"   기사: {total}건 | 최신: {latest}")
    print(f"   빌드: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == '__main__':
    build()
