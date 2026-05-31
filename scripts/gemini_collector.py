#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gemini_collector.py — SA-9 Gemini Search 보완 수집기 v1.1 (모델명 1.5-flash 교체)
"""

import json
import logging
import os
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [SA-9/Gemini] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger('gemini_collector')

_ROOT       = Path(__file__).parent.parent
OUTPUT_FILE = _ROOT / 'data' / 'agent_output' / 'gemini_collector_output.json'

GEMINI_API_URL = 'https://generativelanguage.googleapis.com/v1beta/models'
# ★ 모델명 수정: 2.0-flash에서 1.5-flash로 변경
GEMINI_MODEL   = 'gemini-1.5-flash'
GEMINI_TIMEOUT = 60

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

def _call_gemini_search(query: str, gemini_key: str) -> str:
    url = f'{GEMINI_API_URL}/{GEMINI_MODEL}:generateContent?key={gemini_key}'
    sys_ = (
        '당신은 베트남 인프라 뉴스 수집 에이전트입니다. '
        '검색 결과에서 최신 인프라 뉴스 기사 최대 3건을 JSON 배열로 출력하세요. '
        '형식: [{"title_en":"","summary_en":"100자 이내","source":"","date":"YYYY-MM-DD","url":""}] '
        'JSON만 출력, 코드블록 없이.'
    )
    payload = {
        'system_instruction': {'parts': [{'text': sys_}]},
        'contents':           [{'parts': [{'text': f'검색: {query}'}], 'role': 'user'}],
        'tools':              [{'google_search': {}}],
        'generationConfig':   {'maxOutputTokens': 600, 'temperature': 0.1},
    }
    body = json.dumps(payload).encode('utf-8')
    req  = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')

    try:
        with urllib.request.urlopen(req, timeout=GEMINI_TIMEOUT) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            return data['candidates'][0]['content']['parts'][0]['text'].strip()
    except HTTPError as e:
        log.warning(f'Gemini Search HTTP 오류: {e.code} | 상세: {e.read().decode("utf-8")}')
        return '[]'
    except URLError as e:
        log.warning(f'Gemini Search 네트워크 오류: {e.reason}')
        return '[]'
    except Exception as e:
        log.warning(f'Gemini Search 알 수 없는 오류: {e}')
        return '[]'

def collect_gemini_articles(gemini_key: str) -> list:
    all_articles = []
    today = datetime.now().strftime('%Y-%m-%d')

    for q in SEARCH_QUERIES:
        log.info(f"  쿼리: {q['query'][:55]}...")
        raw = _call_gemini_search(q['query'], gemini_key)
        try:
            raw_clean = raw.strip().lstrip('`').rstrip('`')
            if raw_clean.startswith('json'): raw_clean = raw_clean[4:].strip()
            articles = json.loads(raw_clean)
            for art in (articles if isinstance(articles, list) else []):
                norm = {
                    'title_en': art.get('title_en', '').strip(), 'title_ko': '',
                    'summary_en': art.get('summary_en', '')[:300].strip(), 'summary_ko': '',
                    'source': art.get('source', q['source_hint']), 'date': art.get('date', today),
                    'url': art.get('url', ''), 'sector': q['sector'],
                    'src_type': 'Gemini-Search', 'collected': today,
                }
                if norm['title_en'] and norm['url']:
                    all_articles.append(norm)
                    log.info(f"    ✅ {norm['title_en'][:50]}")
        except Exception as e:
            log.warning(f'  처리 오류: {e}')
    return all_articles

def main():
    log.info('SA-9 Gemini Search 보완 수집기 v1.1 시작')
    gemini_key = os.environ.get('GEMINI_API_KEY', '').strip()
    if not gemini_key:
        log.error('GEMINI_API_KEY 없음 — 종료')
        return

    articles = collect_gemini_articles(gemini_key)
    output = {'collected_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'total': len(articles), 'articles': articles}
    
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    log.info(f'✅ 완료: {len(articles)}건 수집 → {OUTPUT_FILE}')

if __name__ == '__main__':
    main()
