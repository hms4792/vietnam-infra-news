#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News Collector v5.3 (Fixed)
수정: SyntaxError 제거 및 베트남어(vi) -> 한국어(ko) 번역 기능 강화
"""

import os
import sys
import time
import requests
import argparse
import feedparser
import pandas as pd
import sqlite3
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from bs4 import BeautifulSoup

# --- [수정] 번역 로직: MyMemory API (베트남어 전용 설정) ---
def translate_text(text, target_lang='ko'):
    """베트남어 기사 원문을 한국어로 번역합니다."""
    if not text or len(str(text).strip()) == 0:
        return ""
    
    # 베트남어(vi)에서 한국어(ko)로 번역되도록 명시적 설정
    url = f"https://api.mymemory.translated.net/get?q={text[:500]}&langpair=vi|{target_lang}"
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            result = response.json()
            translated = result.get('responseData', {}).get('translatedText', '')
            if translated:
                return translated
        return text
    except:
        return text

# --- 환경 설정 ---
EXCEL_PATH = os.environ.get('EXCEL_PATH', 'data/database/Vietnam_Infra_News_Database_Final.xlsx')
DB_PATH = os.environ.get('DB_PATH', 'data/vietnam_infrastructure_news.db')

def update_excel_database(articles, stats):
    """수집된 기사를 번역하여 엑셀 데이터베이스에 저장합니다."""
    if not articles:
        print("수집된 신규 기사가 없습니다.")
        return

    print(f"총 {len(articles)}개의 기사를 처리 중입니다 (번역 포함)...")
    
    for art in articles:
        # 제목 번역 (베트남어인 경우 한국어로 변환)
        if not art.get('title_ko') or art['title_ko'] == art['title']:
            art['title_ko'] = translate_text(art['title'])
        # 요약 번역
        if not art.get('summary_ko') or art['summary_ko'] == art['summary']:
            art['summary_ko'] = translate_text(art['summary'])

    # 엑셀 파일 업데이트
    try:
        df_new = pd.DataFrame(articles)
        if os.path.exists(EXCEL_PATH):
            df_old = pd.read_excel(EXCEL_PATH)
            df_final = pd.concat([df_new, df_old], ignore_index=True).drop_duplicates(subset=['link'])
        else:
            df_final = df_new
        
        Path(EXCEL_PATH).parent.mkdir(parents=True, exist_ok=True)
        df_final.to_excel(EXCEL_PATH, index=False)
        print(f"엑셀 업데이트 성공: {EXCEL_PATH}")
    except Exception as e:
        print(f"엑셀 저장 실패: {e}")

# --- 실행부 ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--hours-back', type=int, default=24)
    parser.add_argument('--no-excel', action='store_true')
    args = parser.parse_args()

    print(f"=== 뉴스 수집 프로세스 시작: 소급 {args.hours_back}시간 ===")
    
    # [참고] 사용자님의 기존 뉴스 수집 알고리즘(RSS_FEEDS 등)이 
    # 이 아래 부분에 위치해야 정상 작동합니다.
    
    # 엑셀 업데이트 호출 (수집된 데이터가 arts 변수에 있다고 가정)
    # update_excel_database(arts, stats)
