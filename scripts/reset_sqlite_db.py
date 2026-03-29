#!/usr/bin/env python3
"""
reset_sqlite_db.py
SQLite DB를 Excel DB 기준으로 재동기화 (1회성 실행)
GitHub Actions에서 scripts/reset_sqlite_db.py로 실행
"""
import sqlite3, hashlib, os
from pathlib import Path

EXCEL_PATH = os.environ.get('EXCEL_PATH', 'data/database/Vietnam_Infra_News_Database_Final.xlsx')
DB_PATH    = os.environ.get('DB_PATH', 'data/vietnam_infrastructure_news.db')

print(f"Excel: {EXCEL_PATH}")
print(f"SQLite: {DB_PATH}")

# Excel에서 기존 URL 수집
excel_urls = set()
try:
    import openpyxl
    wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True, data_only=True)
    ws = wb.active
    link_col = 7
    for c in range(1, ws.max_column + 1):
        h = str(ws.cell(1, c).value or '').lower()
        if h in ('link', 'url'):
            link_col = c
            break
    for row in ws.iter_rows(min_row=2, values_only=True):
        url = row[link_col - 1] if link_col - 1 < len(row) else None
        if url and str(url).startswith('http'):
            excel_urls.add(str(url))
    wb.close()
    print(f"Excel URL 수: {len(excel_urls)}")
except Exception as e:
    print(f"Excel 읽기 오류: {e}")

# Excel URL 기반 hash 생성
excel_hashes = {hashlib.md5(u.encode()).hexdigest() for u in excel_urls}
print(f"Excel hash 수: {len(excel_hashes)}")

# SQLite DB 연결
Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
conn = sqlite3.connect(DB_PATH)

# 테이블 생성 (없는 경우)
conn.execute("""
    CREATE TABLE IF NOT EXISTS articles (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        url_hash       TEXT UNIQUE,
        url            TEXT,
        title          TEXT,
        summary        TEXT,
        source         TEXT,
        sector         TEXT,
        area           TEXT,
        province       TEXT,
        confidence     INTEGER DEFAULT 0,
        published_date TEXT,
        collected_date TEXT,
        processed      INTEGER DEFAULT 0
    )
""")

# 현재 SQLite hash 수
cur = conn.execute("SELECT COUNT(*) FROM articles")
before = cur.fetchone()[0]
print(f"SQLite 현재 hash 수: {before}")

# Excel에 없는 hash 삭제 (잘못 저장된 기사 제거)
# Excel hash에 없는 row만 삭제
conn.execute(f"""
    DELETE FROM articles
    WHERE url_hash NOT IN ({','.join('?' for _ in excel_hashes)})
""", list(excel_hashes))
conn.commit()

cur = conn.execute("SELECT COUNT(*) FROM articles")
after = cur.fetchone()[0]
print(f"SQLite 정리 후 hash 수: {after} (삭제: {before - after}건)")
conn.close()
print("완료 — 다음 워크플로 실행 시 중복 없이 신규 기사 수집됩니다.")
