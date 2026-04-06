"""
backfill_newsdata.py  v2.0
NewsData.io Latest API로 7개 섹터 기사를 수집.
기존 Excel URL과 대조해 중복 제거 후 run_excel_updater.py로 저장.

v2.0 변경사항 (2026-04-06):
  [핵심] news_collector.py의 classify_sector() 재사용
         → Master Plan 445개 키워드 자동 적용
  [개선] QUERIES에 Master Plan 핵심 프로젝트명 추가
         → API 검색 단계에서부터 관련 기사 더 많이 수집
  [개선] Province 감지를 news_collector.extract_province()로 교체
         → 34개 → 63개 Province 커버

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
API_SIZE      = 10
MAX_PER_QUERY = 10

# ── news_collector.py 함수 import ──────────────────────────────────────────
# v5.5의 classify_sector() + extract_province() 재사용
# → Master Plan 445개 키워드 자동 적용

SCRIPTS_DIR = os.path.join(BASE_DIR, "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

_USE_COLLECTOR = False
try:
    from news_collector import classify_sector, extract_province, SECTOR_AREA
    _USE_COLLECTOR = True
    print("[v2.0] news_collector.py 연동 성공 — Master Plan 445 키워드 적용")
except ImportError:
    print("[WARN] news_collector.py import 실패 — 내장 로직으로 폴백")


# ── 섹터별 API 쿼리 — v2.0: Master Plan 프로젝트명 추가 ──────────────────────
# 검색 단계에서부터 더 많은 관련 기사를 가져오기 위해
# 실제 프로젝트명을 쿼리에 포함

QUERIES = [
    (
        "Waste Water",
        'Vietnam (wastewater OR sewage OR "nuoc thai" OR "Yen Xa" OR '
        '"Binh Hung" OR "Nhon Trach wastewater" OR "Tham Luong" OR '
        '"WWTP" OR "sewage treatment plant" OR "wastewater treatment")',
    ),
    (
        "Water Supply/Drainage",
        'Vietnam ("water supply" OR "clean water" OR "cap nuoc" OR '
        '"Song Da water" OR "Thu Duc water" OR "Cau Do water" OR '
        '"water treatment plant" OR "nuoc sach" OR "flood control")',
    ),
    (
        "Solid Waste",
        'Vietnam ("solid waste" OR recycling OR "rac thai" OR '
        '"Nam Son" OR "Soc Son WTE" OR "Da Phuoc" OR '
        '"waste-to-energy" OR "incineration plant" OR "landfill")',
    ),
    (
        "Power",
        'Vietnam ("wind power" OR solar OR EVN OR "dien gio" OR '
        '"Ninh Thuan solar" OR "Bac Lieu wind" OR "PDP8" OR '
        '"power plant" OR "renewable energy" OR "offshore wind")',
    ),
    (
        "Oil & Gas",
        'Vietnam (petroleum OR LNG OR PVN OR "dau khi" OR '
        '"Nghi Son refinery" OR "Dung Quat" OR "Thi Vai LNG" OR '
        '"Son My LNG" OR "Ca Mau LNG" OR "Petrovietnam")',
    ),
    (
        "Industrial Parks",
        'Vietnam ("industrial park" OR "khu cong nghiep" OR '
        '"VSIP" OR "Amata" OR "Deep C" OR "Song Than" OR '
        '"Nhon Trach" OR "industrial zone" OR FDI)',
    ),
    (
        "Smart City",
        'Vietnam ("smart city" OR "digital infrastructure" OR '
        '"thanh pho thong minh" OR "Thu Duc" OR "BRG Smart City" OR '
        '"Hoa Lac" OR "5G" OR "e-government" OR "IoT infrastructure")',
    ),
]


# ── 폴백용 내장 설정 (news_collector import 실패 시) ───────────────────────

_FALLBACK_SECTOR_AREA = {
    "Waste Water":           "Environment",
    "Water Supply/Drainage": "Environment",
    "Solid Waste":           "Environment",
    "Power":                 "Energy Develop.",
    "Oil & Gas":             "Energy Develop.",
    "Industrial Parks":      "Urban Develop.",
    "Smart City":            "Urban Develop.",
}

_FALLBACK_PROVINCE_LIST = [
    "Hanoi", "Ho Chi Minh City", "Da Nang", "Binh Duong", "Dong Nai",
    "Hai Phong", "Can Tho", "Quang Ninh", "Binh Dinh", "Gia Lai",
    "Khanh Hoa", "Nghe An", "Ha Tinh", "Thanh Hoa", "Quang Nam",
    "Quang Ngai", "Ba Ria Vung Tau", "Long An", "Tien Giang",
    "An Giang", "Soc Trang", "Dak Lak", "Lam Dong", "Ninh Thuan",
    "Binh Thuan", "Hue", "Bac Ninh", "Vinh Phuc", "Thai Nguyen",
    "Nam Dinh", "Ninh Binh", "Bac Giang", "Hung Yen", "Hai Duong",
    "Bac Lieu", "Ca Mau", "Kien Giang", "Tra Vinh", "Vinh Long",
    "Dong Thap", "Ben Tre", "Thua Thien Hue", "Quang Tri",
    "Quang Binh", "Ha Nam", "Thai Binh", "Ha Giang", "Lao Cai",
]

def _fallback_detect_province(text):
    low = text.lower()
    for prov in _FALLBACK_PROVINCE_LIST:
        if prov.lower() in low:
            return prov
    return "Vietnam"


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
            url = str(row[6] or "").strip()
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


# ── 기사 분류 및 가공 ─────────────────────────────────────────────────────────

def tag_article(raw, sector_hint):
    """
    기사를 분류·가공합니다.

    [v2.0 핵심]
    news_collector.py import 성공 시:
      - classify_sector()로 Master Plan 445 키워드 기반 재분류
      - extract_province()로 63개 Province 감지
    import 실패 시:
      - sector_hint(쿼리 섹터)를 그대로 사용
      - 내장 Province 리스트로 감지
    """
    title   = raw.get("title") or ""
    summary = raw.get("description") or raw.get("content") or ""
    pub     = (raw.get("pubDate") or "")[:10]
    url     = raw.get("link") or ""
    source  = raw.get("source_name") or raw.get("source_id") or ""
    text    = f"{title} {summary}"

    if _USE_COLLECTOR:
        # v5.5 classify_sector() 재사용
        sector, area, confidence = classify_sector(title, summary)
        if not sector:
            # 분류 실패 시 쿼리 섹터 힌트 사용
            sector = sector_hint
            area   = SECTOR_AREA.get(sector_hint, "")
        province = extract_province(title, summary)
    else:
        # 폴백: 내장 로직
        sector   = sector_hint
        area     = _FALLBACK_SECTOR_AREA.get(sector_hint, "")
        province = _fallback_detect_province(text)

    return {
        "title":          title,
        "title_en":       title,
        "summary":        summary[:500],
        "source":         source,
        "url":            url,
        "sector":         sector,
        "area":           area,
        "province":       province,
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

    # 섹터별 수집 현황 출력
    from collections import Counter
    sector_dist = Counter(a["sector"] for a in all_articles)
    print("\n섹터별 신규 수집:")
    for s, c in sector_dist.most_common():
        print(f"  {s}: {c}건")

    # ── 결과 저장 ─────────────────────────────────────────────────────────────
    output = {
        "run_timestamp":   datetime.utcnow().isoformat() + "Z",
        "total_raw":       total_raw,
        "total_dupes":     total_dupes,
        "new_articles":    new_count,
        "articles":        all_articles,
        "stats":           {"total_raw": total_raw, "new": new_count},
        "collector_version": "v2.0 (Master Plan 445 keywords)",
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
