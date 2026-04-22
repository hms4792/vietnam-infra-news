"""
build_dashboard.py — v7.1
Excel → docs/index.html 재생성 (독립 실행 가능)

열 매핑 (v7 News Database):
  row[0]=No  row[1]=Date  row[2]=Title(En/Vi)  row[3]=Tit_ko
  row[4]=Source  row[5]=Src_Type  row[6]=Province  row[7]=Plan_ID
  row[8]=Grade  row[9]=URL  row[10]=sum_ko  row[11]=sum_en  row[12]=sum_vi

BACKEND_DATA 구조 (변경 금지):
  {id, title:{ko,en,vi}, summary:{ko,en,vi},
   sector, area, province, source, date, url}

area 값 (변경 금지):
  'Environment' / 'Energy Develop.' / 'Urban Develop.'
"""

import os, sys, json, re, logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger('build_dashboard')

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
EXCEL_PATH    = os.path.join(BASE_DIR, 'data', 'database',
                             'Vietnam_Infra_News_Database_Final.xlsx')
TEMPLATE_PATH = os.path.join(BASE_DIR, 'templates', 'dashboard_template.html')
OUTPUT_PATH   = os.path.join(BASE_DIR, 'docs', 'index.html')

ENV_SECTORS    = {'Waste Water', 'Water Supply/Drainage', 'Solid Waste', 'Environment'}
ENERGY_SECTORS = {'Power', 'Oil & Gas'}

# plan_id → sector 추론 (DB에 sector 컬럼 없는 경우 fallback)
def _plan_to_sector(plan: str) -> str:
    p = plan.upper()
    if 'WW' in p or 'WASTEWATER' in p: return 'Waste Water'
    if 'SWM' in p or 'SOLID' in p:     return 'Solid Waste'
    if 'WAT' in p:                      return 'Water Supply/Drainage'
    if 'PDP8' in p or 'RENEW' in p or 'LNG' in p or 'NUCLEAR' in p: return 'Power'
    if 'OG' in p or 'OIL' in p:        return 'Oil & Gas'
    if 'IP' in p or 'INDUST' in p:     return 'Industrial Parks'
    if 'SC' in p or 'SMART' in p or 'METRO' in p or 'TRAN' in p: return 'Transport'
    return 'Environment'

def _area(sector: str) -> str:
    if sector in ENV_SECTORS:    return 'Environment'
    if sector in ENERGY_SECTORS: return 'Energy Develop.'
    return 'Urban Develop.'

def _clean(val) -> str:
    if val is None: return ''
    s = re.sub(r'[\x00-\x1f\x7f]', ' ', str(val))
    return re.sub(r'\s+', ' ', s).strip()


def load_articles(excel_path: str) -> list:
    """
    News Database 시트 로드.
    v7 열 순서: A=No B=Date C=Title D=Tit_ko E=Source F=Src_Type
                G=Province H=Plan_ID I=Grade J=URL K=sum_ko L=sum_en M=sum_vi
    """
    from openpyxl import load_workbook
    wb = load_workbook(excel_path, read_only=True, data_only=True)
    ws = wb['News Database']
    articles = []
    for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 1):
        title_en = _clean(row[2] if len(row) > 2 else None)  # C열
        if not title_en:
            continue

        date_val = _clean(row[1] if len(row) > 1 else None)  # B열 Date
        plan_id  = _clean(row[7] if len(row) > 7 else None)  # H열 Plan_ID
        sector   = _plan_to_sector(plan_id) if plan_id else 'Environment'

        articles.append({
            'id'     : idx,
            'title'  : {
                'ko': _clean(row[3]  if len(row) > 3  else None),   # D: Tit_ko
                'en': title_en,                                       # C: Title
                'vi': _clean(row[2]  if len(row) > 2  else None),   # C: 동일 (vi 없으면 en)
            },
            'summary': {
                'ko': _clean(row[10] if len(row) > 10 else None),   # K: sum_ko
                'en': _clean(row[11] if len(row) > 11 else None),   # L: sum_en
                'vi': _clean(row[12] if len(row) > 12 else None),   # M: sum_vi
            },
            'sector'  : sector,
            'area'    : _area(sector),     # 'Environment'/'Energy Develop.'/'Urban Develop.'
            'province': _clean(row[6]  if len(row) > 6  else None), # G: Province
            'source'  : _clean(row[4]  if len(row) > 4  else None), # E: Source
            'date'    : date_val,                                      # B: Date
            'url'     : _clean(row[9]  if len(row) > 9  else None), # J: URL
        })

    wb.close()

    # 날짜 내림차순 정렬 (영구 제약)
    articles.sort(key=lambda x: x.get('date', '') or '', reverse=True)
    logger.info(f"Excel 로드: {len(articles)}건")
    return articles


def build_dashboard(excel_path: str = EXCEL_PATH,
                    template_path: str = TEMPLATE_PATH,
                    output_path: str = OUTPUT_PATH):
    """
    Dashboard 재생성.
    templates/dashboard_template.html 의
    /*__BACKEND_DATA__*/[] 플레이스홀더에 JSON 주입 → docs/index.html
    """
    logger.info("Dashboard 재생성 시작")

    articles = load_articles(excel_path)
    if not articles:
        logger.error("기사 없음"); sys.exit(1)

    # JSON 직렬화 + 검증
    try:
        json_str = json.dumps(articles, ensure_ascii=False)
        json.loads(json_str)   # 유효성 검증
    except (json.JSONDecodeError, ValueError):
        logger.warning("JSON 오류 — ASCII 모드로 재시도")
        json_str = json.dumps(articles, ensure_ascii=True)

    # 템플릿 로드
    if not os.path.exists(template_path):
        logger.error(f"템플릿 없음: {template_path}"); sys.exit(1)
    with open(template_path, 'r', encoding='utf-8') as f:
        html = f.read()

    # 플레이스홀더 주입
    PLACEHOLDER = '/*__BACKEND_DATA__*/[]'
    if PLACEHOLDER not in html:
        logger.error(f"플레이스홀더 없음: {PLACEHOLDER}"); sys.exit(1)
    html = html.replace(PLACEHOLDER, json_str)

    # 메타 업데이트
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    html = html.replace('{{UPDATE_TIME}}', now)
    html = html.replace('{{ARTICLE_COUNT}}', str(len(articles)))

    # 저장
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    kb = os.path.getsize(output_path) / 1024
    logger.info(f"저장 완료: {output_path} ({kb:.1f} KB) | {len(articles)}건")


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--excel',    default=EXCEL_PATH)
    p.add_argument('--template', default=TEMPLATE_PATH)
    p.add_argument('--output',   default=OUTPUT_PATH)
    a = p.parse_args()
    build_dashboard(a.excel, a.template, a.output)
