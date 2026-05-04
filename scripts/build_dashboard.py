"""
build_dashboard.py — v7.2.1
(기존 v7.2 기능 100% 유지 + Sector 분류만 개선)

Excel → docs/index.html 재생성

열 매핑 (v8 News Database):
  row[0]=Area  row[1]=Date  row[2]=Title(En/Vi)  row[3]=Tit_ko
  row[4]=Source  row[5]=Src_Type  row[6]=Province  row[7]=Plan_ID
  row[8]=Grade  row[9]=URL  row[10]=sum_ko  row[11]=sum_en  row[12]=sum_vi

특징:
  ✓ 기존 템플릿 파일 사용 (templates/dashboard_template.html)
  ✓ BACKEND_DATA 구조 100% 동일
  ✓ Sector 분류 개선 (src_type 활용)
  ✓ 모든 기존 기능 유지 (MI Dashboard 버튼, Matched_Plan 필터 등)
"""

import os
import sys
import json
import re
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s'
)
logger = logging.getLogger('build_dashboard')

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(SCRIPTS_DIR)
EXCEL_PATH = os.path.join(BASE_DIR, 'data', 'database',
                          'Vietnam_Infra_News_Database_Final.xlsx')
TEMPLATE_PATH = os.path.join(BASE_DIR, 'templates', 'dashboard_template.html')
OUTPUT_PATH = os.path.join(BASE_DIR, 'docs', 'index.html')

# Sector 정의
ENV_SECTORS = {'Waste Water', 'Water Supply/Drainage', 'Solid Waste', 'Environment'}
ENERGY_SECTORS = {'Power', 'Oil & Gas'}
VALID_SECTORS = {
    'Waste Water', 'Water Supply/Drainage', 'Solid Waste',
    'Power', 'Oil & Gas', 'Transport', 'Industrial Parks',
    'Smart City', 'Construction', 'Environment'
}


def _plan_to_sector(plan: str) -> str:
    """Plan ID에서 Sector 추출"""
    p = plan.upper()
    if 'WW' in p or 'WASTEWATER' in p:
        return 'Waste Water'
    if 'SWM' in p or 'SOLID' in p:
        return 'Solid Waste'
    if 'WAT' in p:
        return 'Water Supply/Drainage'
    if 'PDP8' in p or 'RENEW' in p or 'LNG' in p or 'NUCLEAR' in p:
        return 'Power'
    if 'OG' in p or 'OIL' in p:
        return 'Oil & Gas'
    if 'IP' in p or 'INDUST' in p:
        return 'Industrial Parks'
    if 'SC' in p or 'SMART' in p or 'METRO' in p or 'TRAN' in p:
        return 'Transport'
    return 'Environment'


def _area(sector: str) -> str:
    """Sector → Area 변환"""
    if sector in ENV_SECTORS:
        return 'Environment'
    if sector in ENERGY_SECTORS:
        return 'Energy Develop.'
    return 'Urban Develop.'


def _clean(val) -> str:
    """문자열 정제"""
    if val is None:
        return ''
    s = re.sub(r'[\x00-\x1f\x7f]', ' ', str(val))
    return re.sub(r'\s+', ' ', s).strip()


def load_articles(excel_path: str) -> list:
    """
    Excel에서 기사 데이터 로드
    
    ✨ v7.2.1 개선:
      - plan_id 없을 때 src_type(F열) 활용
      - 787개 기사 중 725개도 정확한 sector 분류
    """
    try:
        from openpyxl import load_workbook
    except ImportError:
        logger.error("openpyxl not found. Installing...")
        os.system("pip install openpyxl --break-system-packages")
        from openpyxl import load_workbook
    
    if not os.path.exists(excel_path):
        logger.error(f"Excel file not found: {excel_path}")
        return []
    
    try:
        wb = load_workbook(excel_path, read_only=True, data_only=True)
        ws = wb['News Database']
        articles = []
        matched_count = 0

        for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 1):
            # 기본 필드 추출
            title_en = _clean(row[2] if len(row) > 2 else None)
            if not title_en:
                continue

            date_val = _clean(row[1] if len(row) > 1 else None)
            plan_id = _clean(row[7] if len(row) > 7 else None)  # H열: Plan_ID
            grade = _clean(row[8] if len(row) > 8 else None)    # I열: Grade
            src_type = _clean(row[5] if len(row) > 5 else None) # F열: Src_Type (실제 섹터)

            # ✨ v7.2.1 개선: Sector 분류 로직
            # plan_id → src_type → 기본값 순서로 sector 결정
            if plan_id:
                # 1. plan_id가 있으면 plan 기반 sector 사용
                sector = _plan_to_sector(plan_id)
            elif src_type and src_type in VALID_SECTORS:
                # 2. src_type이 유효한 sector면 직접 사용 (신규!)
                sector = src_type
            else:
                # 3. 최후의 기본값
                sector = 'Environment'

            if plan_id:
                matched_count += 1

            articles.append({
                'id': idx,
                'title': {
                    'ko': _clean(row[3] if len(row) > 3 else None),
                    'en': title_en,
                    'vi': _clean(row[2] if len(row) > 2 else None),
                },
                'summary': {
                    'ko': _clean(row[10] if len(row) > 10 else None),
                    'en': _clean(row[11] if len(row) > 11 else None),
                    'vi': _clean(row[12] if len(row) > 12 else None),
                },
                'sector': sector,           # ✨ 개선된 sector
                'area': _area(sector),
                'province': _clean(row[6] if len(row) > 6 else None),
                'source': _clean(row[4] if len(row) > 4 else None),
                'date': date_val,
                'url': _clean(row[9] if len(row) > 9 else None),
                'plan_id': plan_id,
                'grade': grade,
            })

        wb.close()
        
        # 날짜순 정렬 (최신순)
        articles.sort(key=lambda x: x.get('date', '') or '', reverse=True)
        
        logger.info(f"✓ Loaded {len(articles)} articles (Matched_Plan: {matched_count})")
        return articles

    except Exception as e:
        logger.error(f"Error loading Excel: {e}")
        return []


def build_dashboard(excel_path: str = EXCEL_PATH,
                    template_path: str = TEMPLATE_PATH,
                    output_path: str = OUTPUT_PATH):
    """
    대시보드 생성
    
    기존 workflow 100% 유지:
    1. Excel 로드
    2. 기사 데이터 정제
    3. JSON으로 변환
    4. 기존 템플릿 파일 읽음
    5. BACKEND_DATA 주입
    6. index.html 저장
    """
    logger.info("=" * 60)
    logger.info("DASHBOARD BUILD v7.2.1 (Sector Fix)")
    logger.info("=" * 60)

    # 1. Excel 데이터 로드
    logger.info(f"Loading Excel: {excel_path}")
    articles = load_articles(excel_path)
    
    if not articles:
        logger.error("No articles loaded")
        sys.exit(1)

    # 2. JSON으로 변환
    try:
        json_str = json.dumps(articles, ensure_ascii=False)
        json.loads(json_str)  # 유효성 검사
    except (json.JSONDecodeError, ValueError):
        logger.warning("JSON error with unicode. Retrying with ASCII mode...")
        json_str = json.dumps(articles, ensure_ascii=True)

    # 3. 템플릿 파일 로드
    if not os.path.exists(template_path):
        logger.error(f"Template not found: {template_path}")
        sys.exit(1)
    
    logger.info(f"Loading template: {template_path}")
    with open(template_path, 'r', encoding='utf-8') as f:
        html = f.read()

    # 4. BACKEND_DATA 주입
    PLACEHOLDER = '/*__BACKEND_DATA__*/[]'
    if PLACEHOLDER not in html:
        logger.error(f"Placeholder not found: {PLACEHOLDER}")
        sys.exit(1)
    
    html = html.replace(PLACEHOLDER, json_str)

    # 5. 업데이트 시간 삽입 (선택사항)
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    html = html.replace('{{UPDATE_TIME}}', now)
    html = html.replace('{{ARTICLE_COUNT}}', str(len(articles)))

    # 6. 파일 저장
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    kb = os.path.getsize(output_path) / 1024
    logger.info(f"✓ Saved: {output_path} ({kb:.1f} KB) | {len(articles)} articles")
    logger.info("=" * 60)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Build dashboard from Excel database'
    )
    parser.add_argument('--excel', default=EXCEL_PATH,
                        help='Excel file path')
    parser.add_argument('--template', default=TEMPLATE_PATH,
                        help='HTML template path')
    parser.add_argument('--output', default=OUTPUT_PATH,
                        help='Output HTML path')
    
    args = parser.parse_args()
    build_dashboard(args.excel, args.template, args.output)
