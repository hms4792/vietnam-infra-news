#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gemini_collector.py — SA-9 Gemini 보완 수집기 v1.7 (최종 디버깅)
===========================================================
역할: 모델명 자동 진단 및 뉴스 수집
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

# ★ 최신 안정 모델로 교체: gemini-1.5-flash-002
GEMINI_API_BASE = 'https://generativelanguage.googleapis.com/v1beta'
GEMINI_MODEL    = 'gemini-1.5-flash-002'
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

def list_available_models(gemini_key: str):
    """사용 가능한 모델 목록을 출력하여 404 에러의 근본 원인을 진단"""
    url = f'{GEMINI_API_BASE}/models?key={gemini_key}'
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            model_names = [m['name'] for m in data.get('models', [])]
            log.info(f"사용 가능한 모델 목록: {model_names}")
    except Exception as e:
        log.warning(f"모델 목록 조회 실패: {e}")

def _call_gemini_api(query: str, gemini_key: str) -> str:
    url = f'{GEMINI_API_BASE}/models/{GEMINI_MODEL}:generateContent?key={gemini_key}'
    
    payload = {
        "contents": [{"parts": [{"text": (
            "당신은 인프라 뉴스 전문가입니다. "
            "다음 쿼리에 대해 2026년 최신 정보를 바탕으로 뉴스 기사 최대 3건을 JSON 배열로 출력하세요. "
            "출력 형식: [{\"title_en\":\"제목\",\"summary_en\":\"100자 이내 요약\",\"source\":\"출처\",\"date\":\"YYYY-MM-DD\",\"url\":\"URL\"}] "
            "반드시 JSON 배열만 출력하세요. 검색 쿼리: " + query
        )}]}]
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
        if e.code == 404:
            list_available_models(gemini_key) # 404시 모델 목록 진단
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
                    'source': art.get('source', q['source_hint']),
                    'date': art.get('date', today),
                    'url': art.get('url', ''),
                    'sector': q['sector'],
                    'src_type': 'Gemini-API',
                    'collected': today,
                }
                if norm['title_en'] and norm['url']:
                    all_articles.append(norm)
        except Exception as e:
            log.warning(f'데이터 파싱 오류: {e}')
    return all_articles

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
