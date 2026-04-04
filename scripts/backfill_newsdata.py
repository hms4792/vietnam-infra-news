"""
backfill_newsdata.py
NewsData.io Archive API로 과거 기사를 최신 날짜부터 역순으로 재수집.

커서 방식: backfill_cursor.json 에 진행 위치 저장 → 다음 실행 시 이어서 진행.
크레딧 200건 초과 시 자동 중단 후 저장.
"""

import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta

import requests

BASE_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_OUT_DIR  = os.path.join(BASE_DIR, "data", "agent_output")
CURSOR_PATH    = os.path.join(AGENT_OUT_DIR, "backfill_cursor.json")
OUTPUT_PATH    = os.path.join(AGENT_OUT_DIR, "backfill_output.json")
EXCEL_PATH     = os.path.join(BASE_DIR, "data", "database",
                               "Vietnam_Infra_News_Database_Final.xlsx")

API_BASE       = "https://newsdata.io/api/1/archive"
MAX_CREDITS    = 180        # 200 중 여유분 20 확보
WINDOW_DAYS    = 14         # 2주 단위
MAX_PER_QUERY  = 30         # 섹터당 최대 수집
API_SIZE       = 10         # 1회 API 호출당 결과 수

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


# ── 커서 ─────────────────────────────────────────────────────────────────────

def load_cursor():
    """backfill_cursor.json 읽기. 없으면 오늘부터 시작하는 초기값 반환."""
    today     = date.today()
    default_to   = (today - timedelta(days=1)).isoformat()
    default_from = (today - timedelta(days=WINDOW_DAYS)).isoformat()

    env_to   = os.environ.get("BACKFILL_TO",   default_to)
    env_from = os.environ.get("BACKFILL_FROM",
                              (date.today() - timedelta(weeks=8)).isoformat())

    if os.path.exists(CURSOR_PATH):
        with open(CURSOR_PATH, encoding="utf-8") as f:
            cursor = json.load(f)
        print(f"[커서] 이전 기록 발견: next_from={cursor.get('next_from')} "
              f"~ next_to={cursor.get('next_to')}")
        return cursor, env_from

    # 초기 커서
    cursor = {
        "last_completed_to":   None,
        "last_completed_from": None,
        "next_to":             env_to,
        "next_from":           (datetime.strptime(env_to, "%Y-%m-%d")
                                - timedelta(days=WINDOW_DAYS - 1)).strftime("%Y-%m-%d"),
        "total_collected":     0,
    }
    print(f"[커서] 초기 시작: {cursor['next_from']} ~ {cursor['next_to']}")
    return cursor, env_from


def save_cursor(cursor):
    os.makedirs(AGENT_OUT_DIR, exist_ok=True)
    with open(CURSOR_PATH, "w", encoding="utf-8") as f:
        json.dump(cursor, f, ensure_ascii=False, indent=2)


# ── 기존 URL 로드 ─────────────────────────────────────────────────────────────

def load_existing_urls():
    """Excel News Database의 Link(G열) URL 집합 반환."""
    existing = set()
    if not os.path.exists(EXCEL_PATH):
        return existing
    try:
        import openpyxl
        wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True)
        ws = wb["News Database"]
        for row in ws.iter_rows(min_row=2, values_only=True):
            url = str(row[6] or "").strip()   # G열 = index 6
            if url:
                existing.add(url)
        wb.close()
        print(f"[Excel] 기존 URL {len(existing)}건 로드")
    except Exception as e:
        print(f"[WARN] Excel URL 로드 실패: {e}")
    return existing


# ── API 호출 ──────────────────────────────────────────────────────────────────

def fetch_articles(api_key, sector, query, from_date, to_date, max_results, credit_counter):
    """NewsData.io Archive API 호출. 크레딧 카운터 갱신 후 반환."""
    results  = []
    page     = None
    fetched  = 0

    while fetched < max_results:
        if credit_counter[0] >= MAX_CREDITS:
            break

        params = {
            "apikey":    api_key,
            "q":         query,
            "from_date": from_date,
            "to_date":   to_date,
            "language":  "en,vi",
            "size":      min(API_SIZE, max_results - fetched),
        }
        if page:
            params["page"] = page

        try:
            resp = requests.get(API_BASE, params=params, timeout=20)
            if resp.status_code == 429:
                print(f"  [LIMIT] API 요청 한도 초과 — 중단")
                credit_counter[0] = MAX_CREDITS   # 강제 중단
                break
            if resp.status_code != 200:
                print(f"  [WARN] HTTP {resp.status_code} — 건너뜀")
                break

            data  = resp.json()
            if data.get("status") != "success":
                print(f"  [WARN] API 오류: {data.get('results', data)}")
                break

            batch = data.get("results", [])
            results.extend(batch)
            fetched          += len(batch)
            credit_counter[0] += len(batch)

            page = data.get("nextPage")
            if not page or not batch:
                break

            time.sleep(0.5)   # API 레이트 리밋 방지

        except requests.RequestException as e:
            print(f"  [WARN] 네트워크 오류: {e} — 건너뜀")
            break

    return results


# ── 가공 ──────────────────────────────────────────────────────────────────────

def detect_province(text):
    low = text.lower()
    for prov in PROVINCE_LIST:
        if prov.lower() in low:
            return prov
    return "Vietnam"


def tag_article(raw, sector):
    """NewsData.io 원본 → 파이프라인 표준 dict 변환."""
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
    api_key = os.environ.get("NEWSDATA_API_KEY", "")
    if not api_key:
        print("[SKIP] NEWSDATA_API_KEY 환경변수가 설정되지 않았습니다.")
        sys.exit(0)

    os.makedirs(AGENT_OUT_DIR, exist_ok=True)

    cursor, min_date = load_cursor()
    existing_urls    = load_existing_urls()

    all_articles   = []
    credit_counter = [0]   # mutable int (함수 간 공유)
    total_raw      = 0
    total_dupes    = 0
    windows_done   = 0

    print(f"\n수집 범위 하한: {min_date}")
    print(f"크레딧 한도: {MAX_CREDITS}건\n")

    while credit_counter[0] < MAX_CREDITS:
        win_to   = cursor["next_to"]
        win_from = cursor["next_from"]

        # 하한 도달 시 종료
        if win_to < min_date:
            print(f"[완료] 설정된 최소 날짜({min_date})에 도달 — 종료")
            cursor["next_to"]   = None
            cursor["next_from"] = None
            break

        print(f"\n[기간] {win_from} ~ {win_to}  "
              f"(크레딧 사용: {credit_counter[0]}/{MAX_CREDITS})")

        window_articles = []

        for sector, query in QUERIES:
            if credit_counter[0] >= MAX_CREDITS:
                print(f"  [LIMIT] 크레딧 소진 — 중단")
                break

            print(f"  [{sector}] 수집 중...", end=" ", flush=True)
            raws = fetch_articles(
                api_key, sector, query,
                win_from, win_to,
                MAX_PER_QUERY, credit_counter,
            )

            tagged  = [tag_article(r, sector) for r in raws]
            new     = [a for a in tagged if a["url"] not in existing_urls]
            dupes   = len(tagged) - len(new)

            total_raw   += len(raws)
            total_dupes += dupes

            for a in new:
                existing_urls.add(a["url"])

            window_articles.extend(new)
            print(f"{len(raws)}건 수집 / {dupes}건 중복 / {len(new)}건 신규")

        all_articles.extend(window_articles)
        windows_done += 1

        # 커서 업데이트 (다음 2주 구간)
        next_to_dt   = datetime.strptime(win_from, "%Y-%m-%d") - timedelta(days=1)
        next_from_dt = next_to_dt - timedelta(days=WINDOW_DAYS - 1)

        cursor["last_completed_to"]   = win_to
        cursor["last_completed_from"] = win_from
        cursor["next_to"]             = next_to_dt.strftime("%Y-%m-%d")
        cursor["next_from"]           = next_from_dt.strftime("%Y-%m-%d")
        cursor["total_collected"]     = cursor.get("total_collected", 0) + len(window_articles)

        save_cursor(cursor)

        if credit_counter[0] >= MAX_CREDITS:
            print(f"\n[LIMIT] 크레딧 한도({MAX_CREDITS}) 도달 — 저장 후 종료")
            break

    # ── 결과 저장 ────────────────────────────────────────────────────────────
    new_count = len(all_articles)
    output    = {
        "run_timestamp":   datetime.utcnow().isoformat() + "Z",
        "windows_done":    windows_done,
        "credits_used":    credit_counter[0],
        "total_raw":       total_raw,
        "total_dupes":     total_dupes,
        "new_articles":    new_count,
        "articles":        all_articles,
        "stats":           {
            "credits_used": credit_counter[0],
            "windows":      windows_done,
        },
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n수집 {total_raw}건 / 중복 제외 {total_dupes}건 / 신규 {new_count}건")
    if cursor.get("next_to"):
        print(f"다음 실행 시작일: {cursor['next_to']} (여기서부터 이어서)")
    print(f"크레딧 사용: {credit_counter[0]}/{MAX_CREDITS}")

    # ── run_excel_updater.py 호출 ─────────────────────────────────────────────
    if new_count > 0:
        print(f"\n[Excel] {new_count}건 추가 중...")

        # backfill_output.json → collector_output.json 형태로 복사
        collector_path = os.path.join(AGENT_OUT_DIR, "collector_output.json")
        collector_data = {
            "run_timestamp":   output["run_timestamp"],
            "hours_back":      WINDOW_DAYS * 24 * windows_done,
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
