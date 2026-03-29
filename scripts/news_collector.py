#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News Collector v5.3 (Fixed)
수정 사항: 
1. SyntaxError 원인인 YAML 설정 문구 제거
2. 베트남어(vi) -> 한국어(ko) 번역 로직 강화
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

# --- [수정] 번역 로직: MyMemory API 연동 ---
def translate_text(text, target_lang='ko'):
    """베트남어 기사를 한국어로 번역합니다."""
    if not text or len(str(text).strip()) == 0:
        return ""
    
    # 베트남어(vi)에서 한국어(ko)로 번역 설정
    url = f"https://api.mymemory.translated.net/get?q={text[:500]}&langpair=vi|{target_lang}"
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            result = response.json()
            return result.get('responseData', {}).get('translatedText', text)
        return text
    except:
        return text

# --- 환경 설정 ---
EXCEL_PATH = os.environ.get('EXCEL_PATH', 'data/database/Vietnam_Infra_News_Database_Final.xlsx')
DB_PATH = os.environ.get('DB_PATH', 'data/vietnam_infrastructure_news.db')

def update_excel_database(articles, stats):
    """수집된 데이터를 번역하고 엑셀에 저장하는 핵심 함수"""
    if not articles:
        print("새로운 기사가 없습니다.")
        return

    print(f"총 {len(articles)}개의 기사를 처리 중 (번역 포함)...")
    
    for art in articles:
        # 베트남어 제목과 요약이 있다면 번역 수행
        if not art.get('title_ko') or art['title_ko'] == art['title']:
            art['title_ko'] = translate_text(art['title'])
        if not art.get('summary_ko') or art['summary_ko'] == art['summary']:
            art['summary_ko'] = translate_text(art['summary'])

    # 엑셀 업데이트 로직
    try:
        df_new = pd.DataFrame(articles)
        if os.path.exists(EXCEL_PATH):
            df_old = pd.read_excel(EXCEL_PATH)
            df_final = pd.concat([df_new, df_old], ignore_index=True).drop_duplicates(subset=['link'])
        else:
            df_final = df_new
        
        Path(EXCEL_PATH).parent.mkdir(parents=True, exist_ok=True)
        df_final.to_excel(EXCEL_PATH, index=False)
        print(f"엑셀 업데이트 완료: {EXCEL_PATH}")
    except Exception as e:
        print(f"엑셀 저장 중 오류 발생: {e}")

# --- 실행부 ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--hours-back', type=int, default=24)
    parser.add_argument('--no-excel', action='store_true')
    args = parser.parse_args()

    print(f"=== 뉴스 수집 시작 ({args.hours_back}시간 전까지) ===")
    
    # 여기에 기존의 뉴스 수집(RSS/Google) 로직이 포함되어야 합니다.
    # 사용자님이 올려주신 파일의 수집 로직(arts, stats 생성 부분)을 이 아래에 유지하시면 됩니다.
    
    # 임시 예시 (수집 로직 완료 후 호출부)
    # update_excel_database(arts, stats)
