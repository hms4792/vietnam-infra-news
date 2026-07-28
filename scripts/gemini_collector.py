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
    
    payload = {
        "contents": "
            "반드시 JSON 배열만 출력하세요. 검색 쿼리: " + query
            "출력 형식: [{\"title_en\":\"제목\",\"summary_en\":\"100자 이내 요약\",\"source\":\"출처\",\"date\":\"YYYY-MM-DD\",\"url\":\"URL\"}] "
        )}]}],
        "tools":  # 구글 실시간 웹 검색 강제 활성화
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
                    'source': art.get('source', '').strip(),
                    'date': art.get('date', today),
                    'url': art.get('url', ''),
                    'sector': q['sector'],
                    'src_type': 'Gemini-API',
                    'collected': today,
                }
                
                # [Step 2 적용] 자가 정화 필터 함수 통과시키기
                norm = apply_self_cleaning_loop(norm)
                
                # REJECTED가 아닌 정상 기사만 최종 목록에 추가
                if norm['title_en'] and norm['url'] and norm['QC_Grade'] != 'REJECTED':
                    all_articles.append(norm)
                    
        except Exception as e:
            log.warning(f'데이터 파싱 오류: {e}')
    return all_articles

def apply_self_cleaning_loop(article):
    # 1. 걸러낼 부정적 시그널 키워드 목록 정의
    rejection_signals = [
        "무관함", "부적합합니다", "연관성이 명확하지 않습니다", 
        "직접적 연관성 확인 불가", "진행 상황 파악 불가"
    ]
    
    # 2. sum_ko 필드에 해당 시그널이 있는지 확인
    sum_ko_text = article.get('sum_ko', '')
    
    for signal in rejection_signals:
        if signal in sum_ko_text:
            # 3. 시그널 발견 시, 등급을 강등하고 매핑된 플랜 ID를 삭제 (노이즈 정화)
            article['QC_Grade'] = 'REJECTED'
            article = ''
            break  # 하나라도 발견되면 즉시 종료
            
    return article


def main():
    log.info('SA-9 Gemini 수집기 시작')
    key = os.environ.get('GEMINI_API_KEY', '').strip()
    if not key:
        log.error('GEMINI_API_KEY가 설정되지 않았습니다.')
        return
        
    articles = collect_gemini_articles(key)
    output = {'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'total': len(articles), 'articles': articles}
    
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        
    log.info(f'수집 완료: 총 {len(articles)}건 저장됨')

if __name__ == '__main__':
    main()
