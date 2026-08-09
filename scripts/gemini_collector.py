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
import re  # <--- 이 줄이 추가되었습니다.

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
    
    # [수정] 기존 항목을 모두 유지하고, tit_ko(한국어 제목)와 sum_ko(한국어 요약)를 추가
    payload = {
        "contents": [{
            "parts": [{
                "text": f"반드시 JSON 배열만 출력하세요. 검색 쿼리: {query} 출력 형식: [{{\"title_en\":\"영어 제목\",\"summary_en\":\"100자 이내 영어 요약\",\"province\":\"관련 지역(예: Hanoi, Ho Chi Minh, Binh Duong, Da Nang 등, 특정 지역이 없으면 Nationwide)\",\"source\":\"출처\",\"date\":\"YYYY-MM-DD\",\"url\":\"URL\",\"tit_ko\":\"한국어 제목 번역\",\"sum_ko\":\"한국어 3~4문장 상세 요약\"}}]"
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
                
                # --- [추가/수정된 부분] 날짜 유효성 강력 검증 로직 ---
                raw_date = str(art.get('date', '')).strip()
                if re.match(r'^\d{4}-\d{2}-\d{2}$', raw_date) and raw_date != '2026-12-31':
                    valid_date = raw_date
                else:
                    valid_date = today
                # ------------------------------------------------
                
                norm = {
                    'title_en': art.get('title_en', '').strip(),
                    'tit_ko': art.get('tit_ko', '').strip(),      # [추가] 한국어 제목
                    'summary_en': art.get('summary_en', '')[:300].strip(),
                    'sum_ko': art.get('sum_ko', '').strip(),      # [추가] 한국어 요약
                    'province': art.get('province', 'Nationwide').strip(),
                    'source': art.get('source', '').strip(),
                    'date': valid_date,                           # [수정] 검증된 날짜 변수 적용
                    'url': art.get('url', ''),
                    'sector': q['sector'],
                    'src_type': 'Gemini-API',
                    'collected': today,
                }
                
                # 자가 정화 필터 함수 통과 (기존 로직 보존)
                norm = apply_self_cleaning_loop(norm)
                
                # REJECTED가 아닌 정상 기사만 최종 목록에 한 번만 추가 (기존 로직 보존)
                if norm['title_en'] and norm['url'] and norm.get('QC_Grade') != 'REJECTED':
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

 

def main():
    log.info('SA-9 Gemini 수집기 시작')
    key = os.environ.get('GEMINI_API_KEY', '').strip()
    if not key:
        log.error('GEMINI_API_KEY가 설정되지 않았습니다.')
        return
        
    # 1. 기사 수집 (내부 Google Search Grounding은 이미 활성화되어 있음)
    articles = collect_gemini_articles(key)
    output = {'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'total': len(articles), 'articles': articles}
    
    # JSON 파일 저장 로직 (결과 확인용)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
        
    log.info(f'수집 완료: 총 {len(articles)}건 JSON 저장됨')

if __name__ == '__main__':
    main()
