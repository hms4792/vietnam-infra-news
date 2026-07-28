#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gemini_collector.py — SA-9 Gemini 보완 수집기 v1.9 (모델명 최신화)
===========================================================
역할: 최신 사용 가능 모델인 gemini-2.5-flash로 모델 교체
"""

import json
import logging
import os
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [SA-9/Gemini] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger('gemini_collector')

_ROOT       = Path(__file__).parent.parent
OUTPUT_FILE = _ROOT / 'data' / 'agent_output' / 'gemini_collector_output.json'

# ★ 최신 사용 가능 모델명으로 교체: gemini-2.5-flash
GEMINI_API_BASE = 'https://generativelanguage.googleapis.com/v1beta'
GEMINI_MODEL    = 'gemini-2.5-flash'
GEMINI_TIMEOUT  = 60

SEARCH_QUERIES = [
    {'query': 'Vietnam Ministry of Environment MONRE wastewater water treatment project 2026', 'sector': 'Waste Water', 'source_hint': 'monre.gov.vn'},
    {'query': 'Vietnam solid waste management regulation enforcement 2026', 'sector': 'Solid Waste', 'source_hint': 'vea.gov.vn'},
    {'query': 'Asian Development Bank Vietnam infrastructure project loan approval 2026', 'sector': 'Water Supply/Drainage', 'source_hint': 'adb.org'},
    {'query': 'ADB Vietnam clean water sanitation wastewater project 2026', 'sector': 'Waste Water', 'source_hint': 'adb.org'},
    {'query': 'World Bank Vietnam water supply environment climate project 2026', 'sector': 'Water Supply/Drainage', 'source_hint': 'worldbank.org'},
    {'query': 'JICA Vietnam ODA infrastructure environment grant loan 2026', 'sector': 'Environment', 'source_hint': 'jica.go.jp'},
    {'query': 'Vietnam industrial park FDI environment infrastructure investment 2026', 'sector': 'Industrial Parks', 'source_hint': 'specialist'},
    {'query': 'Vietnam PDP8 power renewable energy offshore wind solar 2026 news', 'sector': 'Power', 'source_hint': 'specialist'},
    {'query': 'Vietnam transport expressway Long Thanh airport metro 2026', 'sector': 'Transport', 'source_hint': 'specialist'},
    {'query': 'Vietnam smart city digital infrastructure IOC 2026', 'sector': 'Smart City', 'source_hint': 'specialist'},
]

def _call_gemini_api(query: str, gemini_key: str) -> str:
    url = f'{GEMINI_API_BASE}/models/{GEMINI_MODEL}:generateContent?key={gemini_key}'
    
    # [수정] 출력 형식에 province(지역) 항목을 추가하여 Gemini에게 추출 지시
    payload = {
        "contents": [{
            "parts": [{
                "text": f"반드시 JSON 배열만 출력하세요. 검색 쿼리: {query} 출력 형식: [{{\"title_en\":\"제목\",\"summary_en\":\"100자 이내 요약\",\"province\":\"관련 지역(예: Hanoi, Ho Chi Minh, Binh Duong, Da Nang 등, 특정 지역이 없으면 Nationwide)\",\"source\":\"출처\",\"date\":\"YYYY-MM-DD\",\"url\":\"URL\"}}]"
            }]
        }],
        "tools": [{"googleSearch": {}}]
    }

    body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')

    try:
        with urllib.request.urlopen(req, timeout=GEMINI_TIMEOUT) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return data['candidates'][0]['content']['parts'][0]['text'].strip()
    except HTTPError as e:
        error_msg = e.read().decode("utf-8")
        log.warning(f'API 호출 실패 (코드 {e.code}): {error_msg}')
        return '[]'
    except Exception as e:
        log.warning(f'Gemini API 연결 오류: {e}')
        return '[]'

def collect_gemini_articles(gemini_key: str) -> list:
    all_articles = []
    today = datetime.now().strftime('%Y-%m-%d')
    
    for q in SEARCH_QUERIES:
        log.info(f"수집 중: {q['sector']} - {q['query'][:40]}...")
        raw = _call_gemini_api(q['query'], gemini_key)
        
        try:
            clean_json = raw.strip().replace('```json', '').replace('```', '').strip()
            articles = json.loads(clean_json)
            
            for art in (articles if isinstance(articles, list) else []):
                norm = {
                    'title_en': art.get('title_en', '').strip(),
                    'summary_en': art.get('summary_en', '')[:300].strip(),
                    'province': art.get('province', 'Nationwide').strip(), # [추가] 지역 정보 매핑 (없으면 Nationwide)
                    'source': art.get('source', '').strip(),
                    'date': art.get('date', today),
                    'url': art.get('url', ''),
                    'sector': q['sector'],
                    'src_type': 'Gemini-API',
                    'collected': today,
                }
                
                # 자가 정화 필터 함수 통과
                norm = apply_self_cleaning_loop(norm)
                
                if norm['title_en'] and norm['url'] and norm['QC_Grade'] != 'REJECTED':
                    all_articles.append(norm)
                
                # [Step 2 적용] 자가 정화 필터 함수 통과시키기
                norm = apply_self_cleaning_loop(norm)
                
                # REJECTED가 아닌 정상 기사만 최종 목록에 추가
                if norm['title_en'] and norm['url'] and norm['QC_Grade'] != 'REJECTED':
                    all_articles.append(norm)
                    
        except Exception as e:
            log.warning(f'데이터 파싱 오류: {e}')
    return all_articles

def apply_self_cleaning_loop(article: dict) -> dict:
    # 1. 걸러낼 부정적 시그널 키워드 목록 정의
    rejection_signals = [
        "무관함", "부적합합니다", "연관성이 명확하지 않습니다", 
        "직접적 연관성 확인 불가", "진행 상황 파악 불가"
    ]
    
    # 기본 등급 설정
    article['QC_Grade'] = 'NORMAL'
    
    # 2. summary_en 필드에 해당 시그널이 있는지 확인 (수정: sum_ko -> summary_en)
    summary_text = article.get('summary_en', '')
    
    for signal in rejection_signals:
        if signal in summary_text:
            # 3. 시그널 발견 시, 등급을 REJECTED로 변경 (문자열 대입 오류 수정)
            article['QC_Grade'] = 'REJECTED'
            break  # 하나라도 발견되면 즉시 종료
            
    return article

import pandas as pd  # 파일 맨 위 임포트 영역에 없다면 추가해주세요

# ==========================================
# Step 3: 최종 엑셀 데이터베이스 업데이트 함수
# ==========================================
def update_excel_database(articles: list):
    # 엑셀 파일이 저장될 경로 설정 (프로젝트 내 data/database 폴더)
    db_path = _ROOT / 'data' / 'database' / 'Vietnam_Infra_News_Database_Final.xlsx'
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    new_df = pd.DataFrame(articles)
    
    if db_path.exists():
        existing_df = pd.read_excel(db_path)
        # 기존 데이터와 새 데이터를 합치고, 중복된 URL이 있다면 최신 내용으로 유지
        combined_df = pd.concat([existing_df, new_df]).drop_duplicates(subset=['url'], keep='last')
    else:
        combined_df = new_df
        
    combined_df.to_excel(db_path, index=False)
    log.info(f'Step 3 완료: 엑셀 데이터베이스 갱신됨 (총 {len(combined_df)}건)')


# ==========================================
# Step 4: 웹 대시보드(index.html) 재생성 함수
# ==========================================
def generate_html_dashboard():
    db_path = _ROOT / 'data' / 'database' / 'Vietnam_Infra_News_Database_Final.xlsx'
    output_html = _ROOT / 'docs' / 'index.html'  # 대시보드가 위치할 경로
    
    if not db_path.exists():
        log.warning('Step 4 스킵: 대시보드를 만들 엑셀 파일이 존재하지 않습니다.')
        return
        
    df = pd.read_excel(db_path)
    # 날짜 기준 내림차순 정렬 (최신 글이 위로 오도록)
    df = df.sort_values(by='date', ascending=False)
    
    # 웹 브라우저에 보여줄 기본 HTML 구조 작성
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Vietnam Infra News Dashboard</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 40px; }}
            table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
            th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
            th {{ background-color: #f4f4f4; }}
        </style>
    </head>
    <body>
        <h1>Vietnam Infrastructure News Dashboard</h1>
        <p>최종 업데이트 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <table>
            <tr>
                <th>날짜</th>
                <th>섹터</th>
                <th>기사 제목 (영문)</th>
                <th>출처</th>
            </tr>
    """
    
    # 상위 50개 기사를 HTML 표 행(row)으로 변환
    for _, row in df.head(50).iterrows():
        html_content += f"""
            <tr>
                <td>{row.get('date', '')}</td>
                <td>{row.get('sector', '')}</td>
                <td><a href="{row.get('url', '#')}" target="_blank">{row.get('title_en', '')}</a></td>
                <td>{row.get('source', '')}</td>
            </tr>
        """
        
    html_content += """
        </table>
    </body>
    </html>
    """
    
    output_html.parent.mkdir(parents=True, exist_ok=True)
    with open(output_html, 'w', encoding='utf-8') as f:
        f.write(html_content)
        
    log.info('Step 4 완료: 웹 대시보드(index.html) 재생성됨')
    

def main():
    log.info('SA-9 Gemini 수집기 시작')
    key = os.environ.get('GEMINI_API_KEY', '').strip()
    if not key:
        log.error('GEMINI_API_KEY가 설정되지 않았습니다.')
        return
        
    # 1. 기사 수집 및 자가 정화 실행
    articles = collect_gemini_articles(key)
    output = {'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'total': len(articles), 'articles': articles}
    
    # 기존 JSON 파일 저장 로직[cite: 1]
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        
    log.info(f'수집 완료: 총 {len(articles)}건 JSON 저장됨')
    
    # ==========================================
    # [추가] Step 3 실행: 엑셀 DB 갱신
    # ==========================================
    update_excel_database(articles)
    
    # ==========================================
    # [추가] Step 4 실행: 대시보드 HTML 재생성
    # ==========================================
    generate_html_dashboard()

if __name__ == '__main__':
    main()
