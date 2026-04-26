"""
excel_updater.py  v3.0  2026-04-26
===========================================
[영구 제약 — 절대 변경 금지]
  - 클래스명:  ExcelUpdater  (ExcelManager 사용 금지)
  - 메서드명:  update_all(articles)   (update() 사용 금지)
  - 신규 기사: insert_rows(2) — 헤더 바로 아래 최상단 삽입
  - 날짜 역순 정렬 유지
  - News Database: 16컬럼 (Col15=Area, Col16=Sector 포함)
  - Matched_Plan: 전체 News Database 스캔 (당일 기사만 금지)
  - Backup: 매 실행 시 전체 현재 DB로 갱신

[버그 수정 v3.0]
  Fix1: News Database 16컬럼 구조 — Area(Col15), Sector(Col16) 추가
        14컬럼 기존 파일 자동 감지 후 15·16번 컬럼 확장
  Fix2: Matched_Plan 재구성 시 전체 News Database 스캔
        (당일 수집 기사만이 아닌 전체 DB 기준 → 과거 매칭 기사 손실 방지)
  Fix3: Grade/색상 결정 = ctx_grade 텍스트 값으로만 판단
        (배경 RGB 값 참조 완전 제거 — openpyxl 색상 비교 오류 방지)
  Fix4: 일반 기사는 흰색, 이번주 신규+미매핑만 NEW(연노랑) 적용
        (전체가 노란색으로 표시되는 현상 수정)
  Fix5: News Database_Backup 매 실행 시 전체 DB로 갱신

[영구 제약 — 번역 / 경로]
  - 번역: Google Translate (MyMemory API primary + deep-translator secondary)
  - Anthropic API: GitHub Actions 연결 오류로 ai_summarizer.py에서 절대 금지
  - EXCEL_PATH: data/database/Vietnam_Infra_News_Database_Final.xlsx
  - 이메일 시크릿: EMAIL_USERNAME / EMAIL_PASSWORD (GMAIL_* 사용 금지)
  - GitHub Pages: main 브랜치 /docs 폴더, gh-pages 브랜치 금지
"""

import os
import re
from datetime import datetime, date, timedelta
from collections import defaultdict
from pathlib import Path
from itertools import groupby

import openpyxl
from openpyxl.styles import PatternFill, Font, Alignment
from openpyxl.utils import get_column_letter

# ─────────────────────────────────────────────────────────────────
# 경로 설정
# ─────────────────────────────────────────────────────────────────
_SCRIPTS_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
_ROOT_DIR    = _SCRIPTS_DIR.parent   # scripts/ 의 상위 = 저장소 루트

EXCEL_PATH = Path(os.environ.get(
    "EXCEL_PATH",
    str(_ROOT_DIR / "data" / "database" / "Vietnam_Infra_News_Database_Final.xlsx")
))

# ─────────────────────────────────────────────────────────────────
# 상수 정의
# ─────────────────────────────────────────────────────────────────
SECTOR_ORDER = [
    "Waste Water", "Water Supply/Drainage", "Solid Waste",
    "Power", "Oil & Gas", "Transport",
    "Industrial Parks", "Smart City", "Construction",
]

AREA_MAP = {
    "Waste Water":           "Environment",
    "Water Supply/Drainage": "Environment",
    "Solid Waste":           "Environment",
    "Power":                 "Energy Develop.",
    "Oil & Gas":             "Energy Develop.",
    "Transport":             "Urban Develop.",
    "Industrial Parks":      "Urban Develop.",
    "Smart City":            "Urban Develop.",
    "Construction":          "Urban Develop.",
    "Environment":           "Environment",
}

PLAN_PREFIX = {
    "VN-WW":    "Waste Water",
    "VN-WAT":   "Water Supply/Drainage",
    "VN-SWM":   "Solid Waste",
    "VN-PWR":   "Power",
    "VN-PDP":   "Power",
    "VN-OG":    "Oil & Gas",
    "VN-TRAN":  "Transport",
    "VN-URB":   "Transport",
    "VN-METRO": "Transport",
    "VN-IP":    "Industrial Parks",
    "VN-MEKONG":"Transport",
    "HN":       "Transport",
    "VN-ENV":   "Environment",
}

SECTOR_KEYWORDS = {
    "Waste Water":           ["wastewater", "sewage", "wwtp", "nước thải", "xử lý nước"],
    "Water Supply/Drainage": ["water supply", "drainage", "cấp nước", "thoát nước", "drinking water"],
    "Solid Waste":           ["solid waste", "garbage", "landfill", "waste management", "chất thải rắn"],
    "Power":                 ["power", "electricity", "energy", "solar", "wind", "hydro",
                              "lng", "nuclear", "điện", "năng lượng", "pdp8"],
    "Oil & Gas":             ["oil", "gas", "petroleum", "pipeline", "refinery", "dầu khí"],
    "Transport":             ["transport", "highway", "road", "airport", "railway",
                              "metro", "bridge", "giao thông", "đường", "cầu"],
    "Industrial Parks":      ["industrial park", "industrial zone", "khu công nghiệp", "khu kinh tế"],
    "Smart City":            ["smart city", "digital", "ict", "đô thị thông minh"],
    "Construction":          ["construction", "building", "xây dựng"],
}

# 색상 팔레트 (Fix3: RGB 문자열 기반으로 통일)
def _f(hex6: str) -> PatternFill:
    return PatternFill("solid", fgColor=hex6)

FILL = {
    "HIGH":   _f("FFF9C4"),   # 🟡 노란   — SA-7 HIGH (≥65점)
    "MEDIUM": _f("E8F0FE"),   # 🔵 연파랑 — SA-7 MEDIUM
    "POLICY": _f("E8F5E9"),   # 🟢 연녹   — POLICY_MATCH
    "BOTH":   _f("FFF3E0"),   # 🟠 연주황 — SA7+POLICY
    "NEW":    _f("FFFDE7"),   # 🔆 연노랑 — 이번 주 신규 + 미매핑
    "WHITE":  _f("FFFFFF"),   # ⬜ 흰색   — 일반 기사
    "EVEN":   _f("F5F9FF"),   # Source 짝수행
    "HDR_B":  _f("1F4E78"),   # 헤더 파랑
    "HDR_G":  _f("375623"),   # 헤더 녹색 (Keywords History)
    "HDR_N":  _f("17375E"),   # 헤더 네이비 (Backup)
}

FONT_HDR  = Font(name="맑은 고딕", bold=True, color="FFFFFF", size=10)
FONT_DATA = Font(name="맑은 고딕", size=10,   color="000000")
FONT_META = Font(name="맑은 고딕", bold=True, size=11,  color="000000")
FONT_TTL  = Font(name="맑은 고딕", bold=True, size=14,  color="1F4E78")

# News Database 16컬럼 정의 (Fix1)
NEWS_HEADERS = [
    "No", "Date", "Title (En/Vi)", "Tit_ko",
    "Source", "Src_Type", "Province", "Plan_ID", "Grade", "URL",
    "sum_ko", "sum_en", "sum_vi", "QC",
    "Area",    # Col15 ← Fix1
    "Sector",  # Col16 ← Fix1
]
NEWS_WIDTHS = [6, 12, 45, 20, 20, 10, 15, 20, 8, 45, 20, 20, 20, 8, 16, 18]

MP_HEADERS = [
    "Plan_ID", "Date", "Title_En", "Tit_ko", "Grade", "Score", "Source",
    "Province", "Area", "Sector", "URL", "sum_ko", "sum_en", "QC", "Src_Type",
]
MP_WIDTHS = [20, 12, 40, 20, 8, 6, 20, 15, 14, 18, 40, 20, 20, 10, 12]

KH_HEADERS = ["Sector", "Province", "Date", "Title (En)", "Title (Ko)", "Source", "Grade", "Plan_ID"]
KH_WIDTHS  = [22, 18, 12, 60, 50, 20, 8, 20]

BK_HEADERS = [
    "Area", "Business Sector", "Province", "News Title", "Date",
    "Source", "Link", "Short Summary", "title_ko", "title_en", "title_vi",
    "summary_ko", "summary_en", "summary_vi", "QC", "ctx_tag", "ctx_grade", "ctx_plans",
]

SECT_PRI = {s: i for i, s in enumerate(SECTOR_ORDER)}


# ─────────────────────────────────────────────────────────────────
# 유틸리티 함수
# ─────────────────────────────────────────────────────────────────
def _sector_from_plan(plan_id: str) -> str | None:
    """Plan_ID 접두사로 Sector 추정"""
    pid = str(plan_id or "").upper().strip()
    for prefix, sector in PLAN_PREFIX.items():
        if pid.startswith(prefix):
            return sector
    return None


def _sector_from_text(title_en: str, title_ko: str, plan_id: str) -> str:
    """Plan_ID → 키워드 매칭 순으로 Sector 추정"""
    s = _sector_from_plan(plan_id)
    if s:
        return s
    text = (str(title_en or "") + " " + str(title_ko or "")).lower()
    best, best_score = "Power", 0
    for sector, kws in SECTOR_KEYWORDS.items():
        score = sum(1 for kw in kws if kw in text)
        if score > best_score:
            best, best_score = sector, score
    return best


def _grade_from_fields(ctx_grade: str, qc: str) -> str:
    """
    Fix3: Grade 결정 (텍스트 값 기반, RGB 색상 참조 제거)
    우선순위:
      1. ctx_grade 필드값: HIGH / MEDIUM / POLICY / LOW
      2. QC 필드 패턴:
         SA7+POLICY → HIGH
         POLICY_MATCH → POLICY
         SA7_MATCH → MEDIUM
    """
    g = str(ctx_grade or "").strip().upper()
    if g in ("HIGH", "MEDIUM", "POLICY", "LOW"):
        return g
    q = str(qc or "").upper()
    if "SA7+POLICY" in q:
        return "HIGH"
    if "POLICY_MATCH" in q and "SA7" not in q:
        return "POLICY"
    if "SA7_MATCH" in q:
        return "MEDIUM"
    return ""


def _row_fill(grade: str, qc: str, is_new_unmatched: bool = False) -> PatternFill:
    """
    Fix3+Fix4: 배경색 결정
    - 일반 기사 (Plan_ID 없음) → 흰색
    - 이번 주 신규 + 미매핑 → NEW 연노랑
    - 매칭 기사 → grade/qc 기준
    """
    g = str(grade or "").strip().upper()
    q = str(qc    or "").strip().upper()
    has_policy = "POLICY" in q

    if g == "HIGH" and has_policy:              return FILL["BOTH"]
    if g == "HIGH":                             return FILL["HIGH"]
    if has_policy and "SA7" not in q:           return FILL["POLICY"]
    if "SA7" in q and has_policy:               return FILL["BOTH"]
    if "SA7" in q:                              return FILL["MEDIUM"]
    if g == "MEDIUM":                           return FILL["MEDIUM"]
    if is_new_unmatched:                        return FILL["NEW"]
    return FILL["WHITE"]


def _hdr(ws, row: int, col: int, val: str, fill_key: str = "HDR_B") -> None:
    """헤더 셀 스타일 적용"""
    c = ws.cell(row, col)
    c.value = val
    c.font  = FONT_HDR
    c.fill  = FILL[fill_key]
    c.alignment = Alignment(horizontal="center", vertical="center")


def _dat(ws, row: int, col: int, val) -> None:
    """데이터 셀 스타일 적용"""
    c = ws.cell(row, col)
    c.value = val
    c.font  = FONT_DATA
    c.alignment = Alignment(vertical="top", wrap_text=False)


# ─────────────────────────────────────────────────────────────────
# ExcelUpdater 클래스
# ─────────────────────────────────────────────────────────────────
class ExcelUpdater:
    """
    Vietnam Infrastructure News Database 업데이트 클래스

    사용법 (main.py Step3):
        updater = ExcelUpdater()
        updater.update_all(articles)   # articles = 당일 수집 기사 리스트

    articles 딕셔너리 필드:
        date, title (또는 title_en), title_ko,
        source, province, plan_id, grade, url,
        sum_ko, sum_en, sum_vi, qc,
        sector (선택), area (선택)
    """

    def __init__(self, excel_path: str | Path = EXCEL_PATH):
        self.path   = Path(excel_path)
        self.today  = date.today().strftime("%Y-%m-%d")
        self.now    = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.cutoff = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")

    # ─── 공개 메서드 ─────────────────────────────────────────────
    def update_all(self, articles: list) -> None:
        """
        영구 제약 준수:
          ① 신규 기사만 추가 (과거 데이터 삭제 절대 금지)
          ② insert_rows(2) 방식으로 최상단 삽입
          ③ 날짜 역순 정렬 유지
          ④ Matched_Plan = 전체 DB 기준 재구성 (Fix2)
          ⑤ News Database_Backup 매 실행 갱신 (Fix5)
        """
        print(f"[ExcelUpdater v3.0] update_all 시작: 신규 {len(articles)}건")

        if not self.path.exists():
            print(f"  [경고] Excel 파일 없음 → 새로 생성: {self.path}")
            self._create_empty_workbook()

        wb = openpyxl.load_workbook(str(self.path))

        # Step 1: Sector/Area 자동 보완
        articles = self._enrich(articles)

        # Step 2: 중복 제거 (URL + 제목 기준)
        new_arts = self._deduplicate(wb, articles)
        print(f"  중복 제거 후 신규: {len(new_arts)}건")

        if new_arts:
            # Step 3: News Database 업데이트 (Fix1 — 16컬럼 보장)
            self._insert_news(wb, new_arts)

        # Step 4: Matched_Plan 전체 재구성 (Fix2)
        self._rebuild_matched_plan(wb)

        # Step 5: Keywords History 재구성
        self._rebuild_keywords_history(wb)

        # Step 6: 통계 시트 업데이트
        self._update_summary(wb, len(new_arts))
        self._update_collection_log(wb, len(new_arts))
        self._update_source(wb)

        # Step 7: Backup 갱신 (Fix5)
        self._refresh_backup(wb)

        wb.save(str(self.path))
        print(f"  [완료] 저장: {self.path}")

    # ─── Step 1: 기사 전처리 ─────────────────────────────────────
    def _enrich(self, articles: list) -> list:
        """sector / area 자동 보완 + grade 정규화 (Fix3)"""
        enriched = []
        for a in articles:
            a = dict(a)
            title    = a.get("title") or a.get("title_en", "")
            title_ko = a.get("title_ko", "")
            plan_id  = a.get("plan_id", "") or a.get("ctx_plans", "")

            if not a.get("sector"):
                a["sector"] = _sector_from_text(title, title_ko, plan_id)
            if not a.get("area"):
                a["area"] = AREA_MAP.get(a["sector"], "Urban Develop.")

            # Grade 정규화 (Fix3)
            raw_grade = a.get("grade", "") or a.get("ctx_grade", "")
            raw_qc    = a.get("qc", "")
            a["grade"] = _grade_from_fields(raw_grade, raw_qc)

            enriched.append(a)
        return enriched

    # ─── Step 2: 중복 제거 ───────────────────────────────────────
    def _deduplicate(self, wb: openpyxl.Workbook, articles: list) -> list:
        """기존 News Database의 URL(Col10) + 제목(Col3) 기준 중복 제거"""
        if "News Database" not in wb.sheetnames:
            return articles
        ws = wb["News Database"]
        existing_urls   = set()
        existing_titles = set()
        for r in range(2, ws.max_row + 1):
            url   = ws.cell(r, 10).value
            title = ws.cell(r, 3).value
            if url:   existing_urls.add(str(url).strip())
            if title: existing_titles.add(str(title)[:80].strip())
        return [
            a for a in articles
            if str(a.get("url", "") or "").strip() not in existing_urls
            and str(a.get("title") or a.get("title_en", ""))[:80].strip() not in existing_titles
        ]

    # ─── Step 3: News Database 업데이트 ──────────────────────────
    def _insert_news(self, wb: openpyxl.Workbook, articles: list) -> None:
        """
        Fix1: 16컬럼 구조 보장 + insert_rows(2) 삽입
        Fix3: Grade는 텍스트 값으로 결정
        Fix4: 색상은 grade/qc 기준, 일반 기사는 흰색
        """
        if "News Database" not in wb.sheetnames:
            ws = wb.create_sheet("News Database", 0)
            self._write_news_header(ws)
        else:
            ws = wb["News Database"]
            self._ensure_16_columns(ws)   # Fix1: 14 → 16컬럼 자동 확장

        # 날짜 역순으로 정렬 후 insert_rows(2) 삽입 (영구 제약)
        for a in sorted(articles, key=lambda x: str(x.get("date", "") or ""), reverse=True):
            ws.insert_rows(2)
            self._write_news_row(ws, 2, a, is_new=True)

        self._renumber(ws)
        print(f"    [News DB] {len(articles)}건 삽입 → 총 {ws.max_row - 1}건")

    def _ensure_16_columns(self, ws) -> None:
        """
        Fix1 핵심: 기존 14컬럼 파일에 Area(Col15)·Sector(Col16) 자동 추가
        기존 데이터 행에도 소급 적용
        """
        headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]

        if "Area" not in headers:
            _hdr(ws, 1, 15, "Area")
            ws.column_dimensions[get_column_letter(15)].width = 16
            for r in range(2, ws.max_row + 1):
                sec = str(ws.cell(r, 16).value or "").strip()
                if not ws.cell(r, 15).value:
                    ws.cell(r, 15).value = AREA_MAP.get(sec, "")
                    ws.cell(r, 15).font  = FONT_DATA

        if "Sector" not in headers:
            _hdr(ws, 1, 16, "Sector")
            ws.column_dimensions[get_column_letter(16)].width = 18
            for r in range(2, ws.max_row + 1):
                if not ws.cell(r, 16).value:
                    plan_id  = str(ws.cell(r, 8).value  or "")
                    title_en = str(ws.cell(r, 3).value  or "")
                    title_ko = str(ws.cell(r, 4).value  or "")
                    ws.cell(r, 16).value = _sector_from_text(title_en, title_ko, plan_id)
                    ws.cell(r, 16).font  = FONT_DATA

    def _write_news_header(self, ws) -> None:
        """16컬럼 헤더 초기 작성"""
        for ci, (h, w) in enumerate(zip(NEWS_HEADERS, NEWS_WIDTHS), 1):
            _hdr(ws, 1, ci, h)
            ws.column_dimensions[get_column_letter(ci)].width = w
        ws.row_dimensions[1].height = 22
        ws.freeze_panes = "A2"

    def _write_news_row(self, ws, row: int, a: dict, is_new: bool = False) -> None:
        """단일 기사를 16컬럼 형식으로 작성 (Fix3+Fix4)"""
        title   = a.get("title") or a.get("title_en", "")
        grade   = str(a.get("grade", "") or "")
        qc      = str(a.get("qc", "")    or "")
        plan_id = str(a.get("plan_id", "") or a.get("ctx_plans", "") or "")
        d       = str(a.get("date", "") or "")

        # Fix4: 색상 결정 — 이번 주 신규 + 미매핑만 NEW
        is_new_unmatched = is_new and (not plan_id) and (d >= self.cutoff)
        fill = _row_fill(grade, qc, is_new_unmatched)

        vals = [
            "",             # Col1: No (나중에 재번호)
            d,              # Col2: Date
            title,          # Col3: Title (En/Vi)
            a.get("title_ko", ""),   # Col4
            a.get("source", ""),     # Col5
            a.get("src_type", "News"),  # Col6
            a.get("province", ""),   # Col7
            plan_id,        # Col8: Plan_ID
            grade,          # Col9: Grade
            a.get("url", ""),        # Col10
            a.get("sum_ko", "") or a.get("summary_ko", ""),   # Col11
            a.get("sum_en", "") or a.get("summary_en", ""),   # Col12
            a.get("sum_vi", "") or a.get("summary_vi", ""),   # Col13
            qc,             # Col14: QC
            a.get("area", ""),       # Col15: Area   ← Fix1
            a.get("sector", ""),     # Col16: Sector ← Fix1
        ]
        for ci, v in enumerate(vals, 1):
            c = ws.cell(row, ci)
            c.value = v
            c.font  = FONT_DATA
            c.fill  = fill
            c.alignment = Alignment(vertical="top", wrap_text=False)

    def _renumber(self, ws) -> None:
        """No 컬럼(Col1) 전체 재번호"""
        for r in range(2, ws.max_row + 1):
            try:
                ws.cell(r, 1).value = r - 1
            except Exception:
                pass

    # ─── Step 4: Matched_Plan 완전 재구성 ────────────────────────
    def _rebuild_matched_plan(self, wb: openpyxl.Workbook) -> None:
        """
        Fix2 핵심: 전체 News Database(모든 행)를 스캔하여 Plan_ID가 있는 기사를 모두 포함.
        당일 기사만 스캔하던 기존 버그 제거 → 과거 매칭 기사 손실 방지.
        """
        ws_news = wb["News Database"]
        mp_arts = []

        for r in range(2, ws_news.max_row + 1):
            plan_id = str(ws_news.cell(r, 8).value or "").strip()
            if not plan_id:
                continue
            grade = str(ws_news.cell(r, 9).value  or "")
            qc    = str(ws_news.cell(r, 14).value or "")
            mp_arts.append({
                "plan_id":  plan_id,
                "date":     str(ws_news.cell(r, 2).value  or "")[:10],
                "title_en": ws_news.cell(r, 3).value,
                "title_ko": ws_news.cell(r, 4).value,
                "source":   ws_news.cell(r, 5).value,
                "province": ws_news.cell(r, 7).value,
                "grade":    grade,
                "url":      ws_news.cell(r, 10).value,
                "sum_ko":   ws_news.cell(r, 11).value,
                "sum_en":   ws_news.cell(r, 12).value,
                "qc":       qc,
                "area":     ws_news.cell(r, 15).value,
                "sector":   ws_news.cell(r, 16).value,
            })

        mp_arts.sort(key=lambda x: str(x.get("date", "") or ""), reverse=True)
        total   = len(mp_arts)
        high_c  = sum(1 for a in mp_arts if str(a.get("grade", "")).upper() == "HIGH")
        med_c   = sum(1 for a in mp_arts if str(a.get("grade", "")).upper() == "MEDIUM")
        pol_c   = sum(1 for a in mp_arts if "POLICY" in str(a.get("qc", "")).upper())

        # 시트 재생성
        if "Matched_Plan" in wb.sheetnames:
            del wb["Matched_Plan"]
        news_idx = wb.sheetnames.index("News Database")
        ws_mp = wb.create_sheet("Matched_Plan", news_idx + 1)

        # Row1: 메타 헤더
        meta = (f"★ SA-7 맥락 확정 기사 {total}건 | "
                f"HIGH(노란)={high_c} MEDIUM(연파랑)={med_c} POLICY(연녹)={pol_c}")
        ws_mp.cell(1, 1).value = meta
        ws_mp.cell(1, 1).font  = FONT_META
        ws_mp.cell(1, 1).fill  = FILL["HIGH"]
        ws_mp.merge_cells(start_row=1, start_column=1, end_row=1, end_column=15)

        # Row2: 컬럼 헤더
        for ci, (h, w) in enumerate(zip(MP_HEADERS, MP_WIDTHS), 1):
            _hdr(ws_mp, 2, ci, h)
            ws_mp.column_dimensions[get_column_letter(ci)].width = w
        ws_mp.row_dimensions[2].height = 20
        ws_mp.freeze_panes = "A3"

        # Row3~: 데이터
        for ri, a in enumerate(mp_arts, 3):
            grade = str(a.get("grade", "") or "")
            qc    = str(a.get("qc", "")    or "")
            fill  = _row_fill(grade, qc, False)
            vals  = [
                a.get("plan_id", ""), a.get("date", ""),
                a.get("title_en", ""), a.get("title_ko", ""),
                grade, "",
                a.get("source", ""), a.get("province", ""),
                a.get("area", ""), a.get("sector", ""),
                a.get("url", ""), a.get("sum_ko", ""), a.get("sum_en", ""),
                qc, "News",
            ]
            for ci, v in enumerate(vals, 1):
                c = ws_mp.cell(ri, ci)
                c.value = v; c.font = FONT_DATA; c.fill = fill
                c.alignment = Alignment(vertical="top", wrap_text=False)

        print(f"    [Matched_Plan] 재구성: {total}건 (HIGH={high_c}🟡 MED={med_c} POL={pol_c})")

    # ─── Step 5: Keywords History 재구성 ─────────────────────────
    def _rebuild_keywords_history(self, wb: openpyxl.Workbook) -> None:
        """
        정렬: Sector 우선순위 → Province 알파벳 → Date 내림차순
        이번 주 신규 기사: 노란색 하이라이트
        """
        ws_news = wb["News Database"]
        kh_data = []
        for r in range(2, ws_news.max_row + 1):
            sector = str(ws_news.cell(r, 16).value or "").strip()
            if not sector:
                continue
            kh_data.append({
                "sector":   sector,
                "province": str(ws_news.cell(r, 7).value  or ""),
                "date":     str(ws_news.cell(r, 2).value  or "")[:10],
                "title_en": ws_news.cell(r, 3).value,
                "title_ko": ws_news.cell(r, 4).value,
                "source":   ws_news.cell(r, 5).value,
                "grade":    str(ws_news.cell(r, 9).value  or ""),
                "plan_id":  str(ws_news.cell(r, 8).value  or ""),
            })

        # 정렬: Sector 우선순위 → Province → (그룹 내) Date 내림차순
        presorted = sorted(kh_data, key=lambda x: (
            SECT_PRI.get(x["sector"], 99),
            str(x.get("province", "") or ""),
        ))
        result = []
        for (sec, prov), grp in groupby(presorted, key=lambda x: (x["sector"], x["province"])):
            result.extend(sorted(grp, key=lambda x: str(x.get("date", "")), reverse=True))

        # 시트 재생성
        if "Keywords History" in wb.sheetnames:
            del wb["Keywords History"]
        mp_idx = wb.sheetnames.index("Matched_Plan")
        ws_kh  = wb.create_sheet("Keywords History", mp_idx + 1)

        for ci, (h, w) in enumerate(zip(KH_HEADERS, KH_WIDTHS), 1):
            _hdr(ws_kh, 1, ci, h, "HDR_G")
            ws_kh.column_dimensions[get_column_letter(ci)].width = w
        ws_kh.row_dimensions[1].height = 22
        ws_kh.freeze_panes = "A2"

        for ri, a in enumerate(result, 2):
            d      = str(a.get("date", ""))
            is_new = d >= self.cutoff
            fill   = FILL["HIGH"] if is_new else FILL["WHITE"]
            vals   = [
                a.get("sector", ""), a.get("province", ""), d,
                str(a.get("title_en", "") or "")[:100],
                str(a.get("title_ko", "") or "")[:80],
                a.get("source", ""), a.get("grade", ""), a.get("plan_id", ""),
            ]
            for ci, v in enumerate(vals, 1):
                c = ws_kh.cell(ri, ci)
                c.value = v; c.font = FONT_DATA; c.fill = fill
                c.alignment = Alignment(vertical="top", wrap_text=False)

        new_cnt = sum(1 for a in result if str(a.get("date", "")) >= self.cutoff)
        print(f"    [Keywords History] {len(result)}건 (신규 {new_cnt}건 노란색)")

    # ─── Step 6a: Summary 업데이트 ───────────────────────────────
    def _update_summary(self, wb: openpyxl.Workbook, new_count: int) -> None:
        ws_news = wb["News Database"]
        ws_mp   = wb.get("Matched_Plan") if hasattr(wb, 'get') else (wb["Matched_Plan"] if "Matched_Plan" in wb.sheetnames else None)
        total   = ws_news.max_row - 1
        matched = (ws_mp.max_row - 2) if ws_mp else 0
        high_c  = 0
        if ws_mp:
            for r in range(3, ws_mp.max_row + 1):
                if str(ws_mp.cell(r, 5).value or "").upper() == "HIGH":
                    high_c += 1

        if "Summary" not in wb.sheetnames:
            return
        ws_sum = wb["Summary"]

        for r in range(1, min(10, ws_sum.max_row + 1)):
            v = str(ws_sum.cell(r, 1).value or "")
            if "Updated" in v or "Total" in v or "updated" in v.lower():
                try:
                    ws_sum.cell(r, 1).value = (
                        f"Updated: {self.now}  |  Total: {total}건 (정제완료) | "
                        f"SA-7: {matched}건 | HIGH: {high_c}건"
                    )
                except Exception:
                    pass
                break
        print(f"    [Summary] Total={total}, SA-7={matched}, HIGH={high_c}")

    # ─── Step 6b: Collection_Log 업데이트 ────────────────────────
    def _update_collection_log(self, wb: openpyxl.Workbook, new_count: int) -> None:
        if "Collection_Log" not in wb.sheetnames:
            return
        ws_news = wb["News Database"]
        total   = ws_news.max_row - 1
        ws_cl   = wb["Collection_Log"]
        ws_cl.insert_rows(2)
        try:
            ws_cl.cell(2, 1).value = f"{self.now} KST"
            ws_cl.cell(2, 2).value = new_count
            ws_cl.cell(2, 3).value = "Daily Automated"
            ws_cl.cell(2, 4).value = "✅"
            ws_cl.cell(2, 5).value = f"신규 {new_count}건 추가 | 전체 {total}건"
            for c in range(1, 6):
                ws_cl.cell(2, c).font = FONT_DATA
        except Exception:
            pass

    # ─── Step 6c: Source 시트 업데이트 ───────────────────────────
    def _update_source(self, wb: openpyxl.Workbook) -> None:
        if "Source" not in wb.sheetnames:
            return
        ws_news  = wb["News Database"]
        src_cnt  = defaultdict(int)
        src_last = defaultdict(str)
        total    = ws_news.max_row - 1

        for r in range(2, ws_news.max_row + 1):
            src = str(ws_news.cell(r, 5).value or "").strip()
            d   = str(ws_news.cell(r, 2).value or "")[:10]
            if src:
                src_cnt[src]  += 1
                if d > src_last[src]:
                    src_last[src] = d

        ws_src = wb["Source"]
        for mc in list(ws_src.merged_cells.ranges):
            ws_src.unmerge_cells(str(mc))
        for r in range(2, ws_src.max_row + 1):
            for c in range(1, ws_src.max_column + 1):
                try:
                    ws_src.cell(r, c).value = None
                    ws_src.cell(r, c).fill  = FILL["WHITE"]
                except Exception:
                    pass

        for ri, (sname, cnt) in enumerate(
            sorted(src_cnt.items(), key=lambda x: x[1], reverse=True), 2
        ):
            ratio  = round(cnt / total * 100, 1) if total else 0
            latest = src_last.get(sname, "")
            status = "✅ 활성" if latest >= self.cutoff else "⚠️ 비활성"
            fill   = FILL["EVEN"] if ri % 2 == 0 else FILL["WHITE"]
            for ci, v in enumerate([sname, "News", cnt, f"{ratio}%", latest, status, ""], 1):
                try:
                    ws_src.cell(ri, ci).value = v
                    ws_src.cell(ri, ci).font  = FONT_DATA
                    ws_src.cell(ri, ci).fill  = fill
                except Exception:
                    pass

        print(f"    [Source] {len(src_cnt)}개 출처 업데이트")

    # ─── Step 7: News Database_Backup 갱신 ───────────────────────
    def _refresh_backup(self, wb: openpyxl.Workbook) -> None:
        """
        Fix5: 매 실행 시 현재 News Database 전체를 Backup으로 갱신.
        Row1 = 범례, Row2 = 헤더, Row3~ = 현재 DB 복사.
        """
        ws_news = wb["News Database"]
        total   = ws_news.max_row - 1

        if "News Database_Backup" in wb.sheetnames:
            del wb["News Database_Backup"]
        ws_bk = wb.create_sheet("News Database_Backup")

        # Row1: 범례
        meta = (
            f"★ 컬러 범례: ■ 노란(FFF9C4)=SA7 HIGH  ■ 연파랑(E8F0FE)=SA7 MEDIUM  "
            f"■ 연녹(E8F5E9)=POLICY  ■ 연주황(FFF3E0)=SA7+POLICY  ■ 흰색=미매핑  "
            f"| 총 {total}건 | Backup: {self.now}"
        )
        ws_bk.cell(1, 1).value = meta
        ws_bk.cell(1, 1).font  = Font(name="맑은 고딕", bold=True, size=9, color="000000")
        ws_bk.cell(1, 1).fill  = PatternFill("solid", fgColor="F2F2F2")
        ws_bk.merge_cells(start_row=1, start_column=1, end_row=1, end_column=18)

        # Row2: 헤더
        for ci, h in enumerate(BK_HEADERS, 1):
            c = ws_bk.cell(2, ci)
            c.value = h
            c.font  = FONT_HDR
            c.fill  = FILL["HDR_N"]
            c.alignment = Alignment(horizontal="center", vertical="center")
        ws_bk.row_dimensions[2].height = 18

        # Row3~: News Database 데이터 매핑 (16컬럼 → 18컬럼)
        # Area=Col15, Sector=Col16, Province=Col7, Title=Col3, Date=Col2
        # Source=Col5, Link=Col10, SumEN=Col12, TitleKO=Col4, TitleEN=Col3
        # SumKO=Col11, SumEN=Col12, SumVI=Col13, QC=Col14, Grade=Col9, PlanID=Col8
        for r in range(2, ws_news.max_row + 1):
            ri   = r + 1  # Backup Row3~
            grade = str(ws_news.cell(r, 9).value  or "")
            qc    = str(ws_news.cell(r, 14).value or "")
            fill  = _row_fill(grade, qc, False)

            bk_vals = [
                ws_news.cell(r, 15).value,  # Area
                ws_news.cell(r, 16).value,  # Business Sector
                ws_news.cell(r,  7).value,  # Province
                ws_news.cell(r,  3).value,  # News Title
                ws_news.cell(r,  2).value,  # Date
                ws_news.cell(r,  5).value,  # Source
                ws_news.cell(r, 10).value,  # Link
                ws_news.cell(r, 12).value,  # Short Summary (sum_en)
                ws_news.cell(r,  4).value,  # title_ko
                ws_news.cell(r,  3).value,  # title_en
                None,                        # title_vi
                ws_news.cell(r, 11).value,  # summary_ko
                ws_news.cell(r, 12).value,  # summary_en
                ws_news.cell(r, 13).value,  # summary_vi
                ws_news.cell(r, 14).value,  # QC
                None,                        # ctx_tag
                ws_news.cell(r,  9).value,  # ctx_grade
                ws_news.cell(r,  8).value,  # ctx_plans
            ]
            for ci, v in enumerate(bk_vals, 1):
                try:
                    c = ws_bk.cell(ri, ci)
                    c.value = v
                    c.font  = Font(name="맑은 고딕", size=9, color="000000")
                    c.fill  = fill
                except Exception:
                    pass

        print(f"    [Backup] 갱신 완료: {total}건")

    # ─── 보조: 빈 워크북 생성 ─────────────────────────────────────
    def _create_empty_workbook(self) -> None:
        """Excel 파일이 없을 때 최소 구조로 생성"""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "News Database"
        self._write_news_header(ws)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(self.path))
        print(f"  [ExcelUpdater] 새 파일 생성: {self.path}")


# ─────────────────────────────────────────────────────────────────
# 단독 실행 테스트 (main.py에서는 사용하지 않음)
# ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("ExcelUpdater v3.0 단독 테스트")
    updater = ExcelUpdater()
    updater.update_all([])   # 빈 기사 → 시트 동기화만 실행
    print("완료")
