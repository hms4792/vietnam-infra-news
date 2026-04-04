"""
backfill_newsdata.py
NewsData.io Latest API로 7개 섹터 기사를 수집.
기존 Excel URL과 대조해 중복 제거 후 run_excel_updater.py로 저장.

API: https://newsdata.io/api/1/latest (무료 플랜 지원)
     날짜 지정 불가 — 섹터 쿼리만 사용
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime

import requests

BASE_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_OUT_DIR = os.path.join(BASE_DIR, "data", "agent_output")
OUTPUT_PATH   = os.path.join(AGENT_OUT_DIR, "backfill_output.json")
EXCEL_PATH    = os.path.join(BASE_DIR, "data", "database",
                              "Vietnam_Infra_News_Database_Final.xlsx")

API_BASE      = "https://newsdata.io/api/1/latest"
API_SIZE      = 10    # 요청당 최대 기사 수
MAX_PER_QUERY = 10    # 섹터당 최대 수집 (총 70건 이내)

# ── 섹터별 쿼리 ───────────────────────────────────────────────────────────────

QUERIES = [
    ("Waste Water",           'Vietnam wastewater OR sewage OR "nước thải"'),
    ("Water Supply/Drainage", 'Vietnam "water supply" OR "clean water" OR "cấp nước"'),
    ("Solid Waste",           'Vietnam "solid waste" OR recycling OR "rác thải"'),
    ("Power",                 'Vietnam "wind power" OR solar OR EVN OR "điện"'),
    ("Oil & Gas",             'Vietnam petroleum OR LNG OR PVN OR "dầu khí"'),
    ("Industrial Parks",      'Vietnam "industrial park" OR "khu công nghiệp"'),
    ("Smart City",            'Vietnam "smart city" OR "digital infrastructure"'),
]

SECTOR_AREA = {
    "Waste Water":           "Environment",
    "Water Supply/Drainage": "Environment",
    "Solid Waste":           "Environment",
    "Power":                 "Energy Develop.",
    "Oil & Gas":             "Energy Develop.",
    "Industrial Parks":      "Urban Develop.",
    "Smart City":            "Urban Develop.",
}

PROVINCE_LIST = [
    "Hanoi", "Ho Chi Minh City", "Da Nang", "Binh Duong", "Dong Nai",
    "Hai Phong", "Can Tho", "Quang Ninh", "Binh Dinh", "Gia Lai",
    "Khanh Hoa", "Nghe An", "Ha Tinh", "Thanh Hoa", "Quang Nam",
    "Quang Ngai", "Ba Ria Vung Tau", "Long An", "Tien Giang",
    "An Giang", "Soc Trang", "Dak Lak", "Lam Dong", "Ninh Thuan",
    "Binh Thuan", "Hue", "Bac Ninh", "Vinh Phuc", "Thai Nguyen",
    "Nam Dinh", "Ninh Binh", "Bac Giang", "Hung Yen", "Hai Duong",
]


# ── 기존 URL 로드 ─────────────────────────────────────────────────────────────

def load_existing_urls():
    existing = set()
    if not os.path.exists(EXCEL_PATH):
        return existing
    try:
        import openpyxl
        wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True)
        ws = wb["News Database"]
        for row in ws.iter_rows(min_row=2, values_only=True):
            url = str(row[6] or "").strip()   # G열
            if url:
                existing.add(url)
        wb.close()
        print(f"[Excel] 기존 URL {len(existing)}건 로드")
    except Exception as e:
        print(f"[WARN] Excel URL 로드 실패: {e}")
    return existing


# ── API 호출 ──────────────────────────────────────────────────────────────────

def fetch_articles(api_key, query):
    params = {
        "apikey":   api_key,
        "q":        query,
        "country":  "vn",
        "language": "en,vi",
        "size":     API_SIZE,
    }
    try:
        resp = requests.get(API_BASE, params=params, timeout=20)
        if resp.status_code == 429:
            print("  [LIMIT] API 요청 한도 초과")
            return []
        if resp.status_code != 200:
            print(f"  [WARN] HTTP {resp.status_code}")
            return []
        data = resp.json()
        if data.get("status") != "success":
            print(f"  [WARN] API 오류: {data.get('message', data)}")
            return []
        return data.get("results", [])
    except requests.RequestException as e:
        print(f"  [WARN] 네트워크 오류: {e}")
        return []


# ── 가공 ──────────────────────────────────────────────────────────────────────

def detect_province(text):
    low = text.lower()
    for prov in PROVINCE_LIST:
        if prov.lower() in low:
            return prov
    return "Vietnam"


def tag_article(raw, sector):
    title   = raw.get("title") or ""
    summary = raw.get("description") or raw.get("content") or ""
    pub     = (raw.get("pubDate") or "")[:10]
    url     = raw.get("link") or ""
    source  = raw.get("source_name") or raw.get("source_id") or ""
    prov    = detect_province(f"{title} {summary}")

    return {
        "title":          title,
        "title_en":       title,
        "summary":        summary[:500],
        "source":         source,
        "url":            url,
        "sector":         sector,
        "area":           SECTOR_AREA.get(sector, ""),
        "province":       prov,
        "published_date": pub,
        "date":           pub,
    }


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    api_key = os.environ.get("NEWSDATA_API_KEY", "").strip()
    if not api_key:
        print("[SKIP] NEWSDATA_API_KEY 환경변수가 설정되지 않았습니다.")
        sys.exit(0)

    os.makedirs(AGENT_OUT_DIR, exist_ok=True)

    existing_urls = load_existing_urls()
    all_articles  = []
    total_raw     = 0
    total_dupes   = 0

    print(f"\n7개 섹터 수집 시작 (섹터당 최대 {MAX_PER_QUERY}건)\n")

    for sector, query in QUERIES:
        print(f"  [{sector}] 수집 중...", end=" ", flush=True)

        raws   = fetch_articles(api_key, query)
        tagged = [tag_article(r, sector) for r in raws if r.get("link")]
        new    = [a for a in tagged if a["url"] not in existing_urls]
        dupes  = len(tagged) - len(new)

        total_raw   += len(raws)
        total_dupes += dupes

        for a in new:
            existing_urls.add(a["url"])
        all_articles.extend(new[:MAX_PER_QUERY])

        print(f"{len(raws)}건 수집 / {dupes}건 중복 / {len(new)}건 신규")
        time.sleep(0.5)

    new_count = len(all_articles)

    # ── 결과 저장 ────────────────────────────────────────────────────────────
    output = {
        "run_timestamp":   datetime.utcnow().isoformat() + "Z",
        "total_raw":       total_raw,
        "total_dupes":     total_dupes,
        "new_articles":    new_count,
        "articles":        all_articles,
        "stats":           {"total_raw": total_raw, "new": new_count},
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n수집 {total_raw}건 / 중복 제외 {total_dupes}건 / 신규 {new_count}건")

    # ── run_excel_updater.py 호출 ─────────────────────────────────────────────
    if new_count > 0:
        print(f"\n[Excel] {new_count}건 추가 중...")

        collector_path = os.path.join(AGENT_OUT_DIR, "collector_output.json")
        collector_data = {
            "run_timestamp":   output["run_timestamp"],
            "hours_back":      168,
            "total_collected": new_count,
            "articles":        all_articles,
            "quality_flags":   {},
            "stats":           output["stats"],
        }
        with open(collector_path, "w", encoding="utf-8") as f:
            json.dump(collector_data, f, ensure_ascii=False, indent=2)

        updater_script = os.path.join(BASE_DIR, "scripts", "run_excel_updater.py")
        result = subprocess.run(
            [sys.executable, updater_script],
            env={**os.environ, "EXCEL_PATH": EXCEL_PATH},
            capture_output=True, text=True, encoding="utf-8",
        )
        if result.stdout:
            print(result.stdout.strip())
        if result.stderr:
            print(result.stderr.strip())
    else:
        print("\n[INFO] 신규 기사 없음 — Excel 업데이트 건너뜀")


if __name__ == "__main__":
    main()
