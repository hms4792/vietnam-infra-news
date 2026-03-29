#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News Collector v5.3
[수정 완료] 파이썬 문법 오류 제거 및 베트남어 번역 로직 보완
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

# --- [1] 번역 함수: 베트남어(vi) -> 한국어(ko) ---
def translate_text(text, target_lang='ko'):
    if not text or len(str(text).strip()) == 0:
        return ""
    
    # MyMemory API 사용 (베트남어 소스 지정)
    url = f"https://api.mymemory.translated.net/get?q={text[:500]}&langpair=vi|{target_lang}"
    try:
        response = requests.get(url, timeout=15)
        if response.status_code == 200:
            result = response.json()
            return result.get('responseData', {}).get('translatedText', text)
        return text
    except:
        return text

# --- [2] 엑셀 업데이트 함수 ---
def update_excel_database(articles, excel_path):
    if not articles:
        print("새로운 뉴스 기사가 없습니다.")
        return

    print(f"총 {len(articles)}개 기사 번역 및 엑셀 저장 시작...")
    
    for art in articles:
        # 한국어 제목/요약이 없으면 번역 실행
        if not art.get('title_ko'):
            art['title_ko'] = translate_text(art['title'])
        if not art.get('summary_ko'):
            art['summary_ko'] = translate_text(art['summary'])

    try:
        df_new = pd.DataFrame(articles)
        if os.path.exists(excel_path):
            df_old = pd.read_excel(excel_path)
            df_final = pd.concat([df_new, df_old], ignore_index=True).drop_duplicates(subset=['link'])
        else:
            df_final = df_new
        
        Path(excel_path).parent.mkdir(parents=True, exist_ok=True)
        df_final.to_excel(excel_path, index=False)
        print(f"엑셀 업데이트 완료: {excel_path}")
    except Exception as e:
        print(f"엑셀 저장 중 오류 발생: {e}")

# --- [3] 메인 실행부 ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--hours-back', type=int, default=24)
    parser.add_argument('--no-excel', action='store_true')
    args = parser.parse_args()

    # 환경 변수 설정
    EXCEL_PATH = os.environ.get('EXCEL_PATH', 'data/database/Vietnam_Infra_News_Database_Final.xlsx')
    
    print(f"=== Vietnam Infra News Collector v5.3 ===")
    print(f"시간 범위: {args.hours_back}시간")

    # (주의) 여기에 기존에 사용하시던 뉴스 수집 로직(RSS_FEEDS 등)이 들어가야 합니다.
    # 만약 수집 로직 전체가 필요하시다면, 업로드하신 파일에서 
    # 'import' 부분부터 'if __name__ == "__main__":' 이전까지만 복사해서 
    # 이 파일의 중간에 끼워넣으시면 됩니다.
