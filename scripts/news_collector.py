#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News Collector
Version 5.3 (Fixed) — Environment & North Vietnam Coverage Enhancement
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
from datetime import datetime, timedelta
from pathlib import Path
from bs4 import BeautifulSoup

# [메모리항목1] 번역: MyMemory API (Google Translate 호환)
def translate_text(text, target_lang='ko'):
    """MyMemory API를 사용하여 텍스트를 번역합니다."""
    if not text or len(text.strip()) == 0:
        return ""
    
    # 베트남어 기사는 자동 감지 혹은 'vi'에서 한국어로 번역
    url = f"https://api.mymemory.translated.net/get?q={text[:500]}&langpair=vi|{target_lang}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            translated = data.get('responseData', {}).get('translatedText', '')
            if translated:
                return translated
        return text # 번역 실패 시 원문 유지
    except Exception as e:
        print(f"Translation Error: {e}")
        return text

# --- 환경 설정 ---
EXCEL_PATH = os.environ.get('EXCEL_PATH', 'data/database/Vietnam_Infra_News_Database_Final.xlsx')
DB_PATH = os.environ.get('DB_PATH', 'data/vietnam_infrastructure_news.db')

# --- 뉴스 수집 및 처리 로직 (생략 - 기존 코드 유지) ---
# (실제 파일 저장 시에는 기존의 RSS_FEEDS 정의와 수집 로직이 이 아래에 포함됩니다.)

def update_excel_database(articles, stats):
    """수집된 기사를 번역하고 엑셀에 저장합니다."""
    if not articles:
        print("No new articles to update.")
        return

    print(f"Processing {len(articles)} articles for translation and export...")
    
    # 엑셀 저장 전 번역 실행 (베트남어 기사 대상)
    for art in articles:
        if not art.get('title_ko'):
            art['title_ko'] = translate_text(art['title'])
        if not art.get('summary_ko'):
            art['summary_ko'] = translate_text(art['summary'])

    # 엑셀 파일 로드 및 업데이트
    try:
        df_new = pd.DataFrame(articles)
        if os.path.exists(EXCEL_PATH):
            df_old = pd.read_excel(EXCEL_PATH)
            df_final = pd.concat([df_new, df_old], ignore_index=True).drop_duplicates(subset=['link'])
        else:
            df_final = df_new
        
        Path(EXCEL_PATH).parent.mkdir(parents=True, exist_ok=True)
        df_final.to_excel(EXCEL_PATH, index=False)
        print(f"Successfully updated Excel: {EXCEL_PATH}")
    except Exception as e:
        print(f"Excel Update Error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--hours-back', type=int, default=24)
    parser.add_argument('--no-excel', action='store_true')
    args = parser.parse_args()

    # 실제 수집 실행 및 엑셀 업데이트 호출
    # (이 부분에서 수집된 articles 리스트를 생성하는 로직이 작동함)
    print(f"Starting collection: {args.hours_back} hours back")
    # ... (생략: 기존 수집 함수 호출) ...
