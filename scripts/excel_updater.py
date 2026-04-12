"""
excel_updater.py
================
Vietnam Infrastructure News Pipeline - Excel 전체 시트 완전 업데이트 모듈

업데이트 대상 시트 (9개 전체):
  1. News Database      - 번역 완료 기사 원장 데이터
  2. Keywords           - 섹터별 현행 키워드 목록 (정적 참조용)
  3. Keywords History   - 키워드별 매칭 기사 상세 이력
  4. Keyword History    - 키워드별 통계(섹터/횟수/최신일자)
  5. Source             - 뉴스 출처 도메인 목록
  6. RSS_Sources        - RSS 피드별 수집 결과 로그
  7. Collection_Log     - 실행별 수집 통계 로그
  8. Summary            - 전체 요약 + 금주 요약 (분리)
  9. Province_Keywords  - 성/시별 검색어 기록 (신규)

수정 이력:
  2026-04-06 v2.1: Keywords History tuple index 오류 수정 (row 길이 안전 체크)
                   Keyword History pandas 의존성 제거 (collections 모듈로 대체)
"""

import logging
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 엑셀 관련 라이브러리
try:
    import openpyxl
    from openpyxl.styles import (
        Font, PatternFill, Alignment, Border, Side
    )
    from openpyxl.utils import get_column_letter
    OPENPYXL_OK = True
except ImportError:
    OPENPYXL_OK = False
    logger.error("openpyxl 미설치 - pip install openpyxl")

# Province 키워드 사전
try:
    from scripts.province_keywords import (
        PROVINCE_KEYWORDS, get_provinces_for_excel,
        get_province_from_text, normalize_province
    )
    PROVINCE_OK = True
except ImportError:
    PROVINCE_OK = False
    PROVINCE_KEYWORDS = {}

# ── 색상 팔레트 ─────────────────────────────────────────
COLOR = {
    "header_dark":  "1A5276",
    "header_mid":   "2E86C1",
    "header_green": "1E8449",
    "header_gold":  "B7950B",
    "row_even":     "EBF5FB",
    "row_odd":      "FFFFFF",
    "highlight":    "FDFEFE",
    "white":        "FFFFFF",
    "font_white":   "FFFFFF",
    "font_dark":    "1C2833",
}

EXCEL_PATH = Path("data/database/Vietnam_Infra_News_Database_Final.xlsx")


# ════════════════════════════════════════════════════════════
# 스타일 헬퍼
# ════════════════════════════════════════════════════════════

def _hdr(color_hex: str, bold=True, font_color="FFFFFF") -> dict:
    return {
        "fill":   PatternFill("solid", fgColor=color_hex),
        "font":   Font(bold=bold, color=font_color, size=10),
        "align":  Alignment(horizontal="center", vertical="center", wrap_text=True),
        "border": Border(bottom=Side(style="medium", color="AAAAAA")),
    }

def _apply_style(cell, style: dict):
    if "fill"   in style: cell.fill      = style["fill"]
    if "font"   in style: cell.font      = style["font"]
    if "align"  in style: cell.alignment = style["align"]
    if "border" in style: cell.border    = style["border"]

def _set_header_row(ws, headers: list, style_dict: dict, row=1):
    for col, (title, width) in enumerate(headers, 1):
        cell = ws.cell(row=row, column=col, value=title)
        _apply_style(cell, style_dict)
        ws.column_dimensions[get_column_letter(col)].width = width

def _zebra_row(ws, row_idx: int, data: list, font_size=9):
    bg   = COLOR["row_even"] if row_idx % 2 == 0 else COLOR["row_odd"]
    fill = PatternFill("solid", fgColor=bg)
    font = Font(size=font_size, color=COLOR["font_dark"])
    algn = Alignment(wrap_text=True, vertical="top")
    for col, val in enumerate(data, 1):
        cell           = ws.cell(row=row_idx, column=col, value=val)
        cell.fill      = fill
        cell.font      = font
        cell.alignment = algn

def _freeze_and_filter(ws, freeze="A2"):
    ws.freeze_panes = freeze
    if ws.max_row > 1:
        ws.auto_filter.ref = ws.dimensions


# ════════════════════════════════════════════════════════════
# 메인 클래스
# ════════════════════════════════════════════════════════════

class ExcelUpdater:
    def __init__(self, excel_path: Path = EXCEL_PATH):
        self.path = excel_path
        self.wb   = None
        self.now  = datetime.now()
        self.period_end   = self._get_this_saturday_6pm()
        self.period_start = self.period_end - timedelta(days=7)

    def _get_this_saturday_6pm(self) -> datetime:
        today = self.now
        days_until_sat = (5 - today.weekday()) % 7
        if days_until_sat == 0 and today.hour < 18:
            days_until_sat = 0
        sat = today + timedelta(days=days_until_sat)
        return sat.replace(hour=18, minute=0, second=0, microsecond=0)

    # ── 메인 진입점 ─────────────────────────────────────────

    def update_all(
        self,
        articles:    list,
        run_stats:   dict = None,
        rss_results: list = None,
        keyword_map: dict = None,
    ) -> str:
        if not OPENPYXL_OK:
            raise RuntimeError("openpyxl 미설치")

        self.path.parent.mkdir(parents=True, exist_ok=True)

        if self.path.exists():
            self.wb = openpyxl.load_workbook(self.path)
            logger.info(f"[Excel] 기존 파일 로드: {self.path}")
            for old_sheet in ["Keywords_History"]:
                if old_sheet in self.wb.sheetnames:
                    del self.wb[old_sheet]
        else:
            self.wb = openpyxl.Workbook()
            logger.info("[Excel] 신규 파일 생성")

        results = {}
        tasks = [
            ("News Database",     lambda: self._update_news_database(articles)),
            ("Keywords",          lambda: self._update_keywords()),
            ("Keywords History",  lambda: self._update_keywords_history(articles, keyword_map)),
            ("Keyword History",   lambda: self._update_keyword_history(articles)),
            ("Source",            lambda: self._update_source()),
            ("RSS_Sources",       lambda: self._update_rss_sources(rss_results or [])),
            ("Collection_Log",    lambda: self._update_collection_log(articles, run_stats or {})),
            ("Summary",           lambda: self._update_summary(articles)),
            ("Province_Keywords", lambda: self._update_province_keywords()),
        ]

        for sheet_name, update_fn in tasks:
            try:
                update_fn()
                results[sheet_name] = "✓"
                logger.info(f"[Excel] 시트 업데이트 완료: {sheet_name}")
            except Exception as e:
                results[sheet_name] = f"✗ {e}"
                logger.error(
                    f"[Excel] 시트 업데이트 실패: {sheet_name} - {e}",
                    exc_info=True,
                )

        self.wb.save(self.path)
        logger.info(f"[Excel] 저장 완료: {self.path}")

        ok_count = sum(1 for v in results.values() if v == "✓")
        logger.info(f"[OK] ExcelUpdater 완료: {len(articles)}건 | 시트 {ok_count}/{len(tasks)} 성공")
        for name, status in results.items():
            logger.info(f"  [{status}] {name}")

        return str(self.path)

    # ────────────────────────────────────────────────────────
    # 시트 1: News Database
    # ────────────────────────────────────────────────────────

    def _update_news_database(self, articles: list):
        ws        = self._get_or_create_sheet("News Database", 0)
        HDR_STYLE = _hdr(COLOR["header_dark"])

        COLS = [
            ("Area", 18), ("Business Sector", 22), ("Province", 18),
            ("News Title", 55), ("Date", 13), ("Source", 22),
            ("Link", 45), ("Short Summary", 55), ("title_ko", 45),
            ("title_en", 45), ("title_vi", 45), ("summary_ko", 55),
            ("summary_en", 55), ("summary_vi", 55),
        ]

        current_header_count = sum(1 for c in range(1, 15) if ws.cell(1, c).value)
        if ws.max_row == 0 or ws.cell(1, 1).value is None or current_header_count < 14:
            _set_header_row(ws, COLS, HDR_STYLE)
            ws.row_dimensions[1].height = 22

        existing_urls = set()
        link_col = 7
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[link_col - 1]:
                existing_urls.add(str(row[link_col - 1]).strip())

        added = 0
        for article in articles:
            url = str(article.get("url", "")).strip()
            if url and url in existing_urls:
                continue

            row_data = [
                article.get("area", ""),
                article.get("sector", ""),
                article.get("province", "") or (
                    get_province_from_text(article.get("title", ""))
                    if PROVINCE_OK else article.get("province", "")
                ),
                article.get("title_en") or article.get("title", ""),
                str(article.get("date") or article.get("published_date", ""))[:10],
                article.get("source", ""),
                url,
                article.get("summary_en", "")[:200],
                article.get("title_ko", ""),
                article.get("title_en") or article.get("title", ""),
                article.get("title_vi") or article.get("title", ""),
                article.get("summary_ko", ""),
                article.get("summary_en", ""),
                article.get("summary_vi", ""),
            ]
            ws.insert_rows(2)
            for col_idx, val in enumerate(row_data, 1):
                ws.cell(row=2, column=col_idx, value=val)
            existing_urls.add(url)
            added += 1

            # [v2.3] 정책 매핑 기사 노란색 하이라이트 (policy_highlight=True)
            if article.get("policy_highlight"):
                POLICY_FILL = PatternFill(
                    start_color="FFF176",   # 밝은 노란색 (정책 매핑)
                    end_color="FFF176",
                    fill_type="solid"
                )
                for col_idx in range(1, 15):
                    ws.cell(row=2, column=col_idx).fill = POLICY_FILL

        _freeze_and_filter(ws)
        logger.info(f"  News Database: {added}건 추가 (누적 {ws.max_row - 1}건)")

    # ────────────────────────────────────────────────────────
    # 시트 2: Keywords
    # ────────────────────────────────────────────────────────

    def _update_keywords(self):
        ws = self._get_or_create_sheet("Keywords")
        ws.delete_rows(1, ws.max_row + 1)

        HDR_STYLE = _hdr(COLOR["header_dark"])
        COLS = [
            ("Business Sector", 22), ("Area", 18), ("Keywords", 80),
            ("Keyword Count", 15), ("Last Updated", 18),
        ]
        _set_header_row(ws, COLS, HDR_STYLE)

        SECTOR_KEYWORDS = {
            "Waste Water":           ("Environment", [
                "wastewater", "waste water", "wastewater treatment", "wwtp",
                "sewage", "sewage treatment", "sewer", "sewerage",
                "wastewater plant", "effluent treatment",
                "nuoc thai", "xu ly nuoc thai", "he thong thoat nuoc",
            ]),
            "Water Supply/Drainage": ("Environment", [
                "water supply", "clean water", "drinking water", "tap water",
                "potable water", "water infrastructure", "water pipeline",
                "drainage system", "flood drainage", "stormwater",
                "water plant", "water treatment plant", "water network",
                "cap nuoc", "thoat nuoc", "nuoc sach",
            ]),
            "Solid Waste":           ("Environment", [
                "solid waste", "garbage", "trash", "landfill",
                "waste management", "recycling", "incineration",
                "waste-to-energy", "wte", "municipal waste",
                "circular economy", "compost", "hazardous waste",
                "rac thai", "xu ly rac", "bai rac", "dot rac",
            ]),
            "Power":                 ("Energy", [
                "power plant", "power station", "electricity", "power generation",
                "thermal power", "coal power", "gas power", "lng power",
                "solar power", "wind power", "renewable energy",
                "transmission line", "grid", "substation", "lng terminal",
                "dien", "nha may dien", "nang luong tai tao",
            ]),
            "Oil & Gas":             ("Energy", [
                "oil and gas", "oil & gas", "petroleum", "refinery",
                "oil field", "gas field", "offshore oil", "lpg",
                "lng", "gas pipeline", "oil terminal", "petrochemical",
                "dau khi", "loc hoa dau", "khi dot",
            ]),
            "Industrial Parks":      ("Urban Development", [
                "industrial park", "industrial zone", "industrial complex",
                "economic zone", "export processing zone", "epz",
                "special economic zone", "sez", "vsip",
                "fdi", "foreign direct investment", "manufacturing hub",
                "khu cong nghiep", "khu kinh te", "khu che xuat",
            ]),
            "Smart City":            ("Urban Development", [
                "smart city", "smart urban", "digital city",
                "intelligent transport", "smart traffic", "iot city",
                "digital transformation", "e-government",
                "thanh pho thong minh", "do thi thong minh",
            ]),
            "Transport":             ("Urban Development", [
                "metro", "metro line", "subway", "urban rail", "light rail",
                "railway", "high-speed rail", "expressway", "highway",
                "airport", "seaport", "port", "bridge", "tunnel",
                "long thanh", "north-south railway",
                "duong sat", "san bay", "cang bien", "cao toc",
            ]),
            "Construction":          ("Urban Development", [
                "real estate", "building", "property", "cement", "housing",
                "steel", "construction project", "new urban area",
                "bat dong san", "xay dung", "nha o",
            ]),
        }

        today_str = self.now.strftime("%Y-%m-%d")
        for row_idx, (sector, (area, kws)) in enumerate(SECTOR_KEYWORDS.items(), 2):
            _zebra_row(ws, row_idx, [
                sector, area, ", ".join(kws), len(kws), today_str,
            ])

        _freeze_and_filter(ws)

    # ────────────────────────────────────────────────────────
    # 시트 3: Keywords History
    # [수정 v2.1] row 길이 안전 체크 → tuple index out of range 해결
    # ────────────────────────────────────────────────────────

    def _update_keywords_history(self, articles: list, keyword_map: dict = None):
        """
        Keywords History 시트
        [메모리 규칙] 컬럼 순서: No, Area, Sector, Keyword, Province, Date, Title, Source, URL, Summary
        [메모리 규칙] 1순위: Sector(우선순위), 2순위: Province(알파벳), 3순위: Date(최신→오래된)
        [메모리 규칙] 신규 기사: 노란색(#FFF9C4) 하이라이트
        [v2.3 수정] Keyword 컬럼 복원 (기존에 누락됨)
        [v2.3 수정] nan 값 방지 (None → '' 안전 변환)
        [v2.3 수정] 기존 시트 컬럼 구조 불일치 시 헤더 재설정
        """
        ws        = self._get_or_create_sheet("Keywords History")
        HDR_STYLE = _hdr(COLOR["header_dark"])

        # [메모리 규칙] 정확한 컬럼 순서: No, Area, Sector, Keyword, Province, Date, Title, Source, URL, Summary
        COLS = [
            ("No",       6), ("Area",     18), ("Sector",   22),
            ("Keyword", 25), ("Province", 20), ("Date",     13),
            ("Title",   60), ("Source",   22), ("URL",      45),
            ("Summary", 55),
        ]

        # 헤더 검증 — 컬럼4가 Keyword인지 확인 (구버전은 Province가 있음)
        current_col4 = ws.cell(1, 4).value
        if ws.cell(1, 1).value != "No" or current_col4 != "Keyword":
            # 헤더 재설정 필요
            _set_header_row(ws, COLS, HDR_STYLE)
            logger.info(f"  Keywords History 헤더 재설정 (기존 col4={current_col4} → Keyword)")

        # 기존 URL 수집 — URL은 9번째 컬럼(인덱스8)
        existing_urls = set()
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not row or not any(row):
                continue
            r = list(row) + [""] * max(0, 10 - len(row))
            if r[8]:
                existing_urls.add(str(r[8]).strip())

        NEW_FILL = PatternFill(start_color="FFF9C4", end_color="FFF9C4", fill_type="solid")
        NEW_FONT = Font(bold=True, size=9, color="1A1A1A")

        SECTOR_ORDER = [
            "Waste Water", "Water Supply/Drainage", "Solid Waste",
            "Power", "Oil & Gas",
            "Transport", "Industrial Parks", "Smart City", "Construction",
        ]

        added    = 0
        new_rows = []

        for article in articles:
            url = str(article.get("url") or "").strip()
            if not url or url in existing_urls:
                continue

            province   = str(article.get("province") or "") or (
                get_province_from_text(article.get("title", ""))
                if PROVINCE_OK else "Vietnam"
            )
            matched_kw = str(
                article.get("matched_keyword") or
                article.get("keyword") or ""
            )
            date_val   = str(
                article.get("date") or article.get("published_date") or ""
            )[:10]
            sector     = str(article.get("sector") or "")
            # title: 영문 우선, 없으면 원문
            title_val  = str(
                article.get("title_en") or article.get("title") or ""
            )
            # summary: nan 방지 — None이면 빈 문자열
            summary_val = str(article.get("summary_en") or "")[:200]
            if summary_val.lower() in ("nan", "none"):
                summary_val = ""

            new_rows.append({
                "area":       str(article.get("area") or ""),
                "sector":     sector,
                "keyword":    matched_kw,
                "province":   province,
                "date":       date_val,
                "title":      title_val,
                "source":     str(article.get("source") or ""),
                "url":        url,
                "summary":    summary_val,
                "sector_idx": SECTOR_ORDER.index(sector)
                               if sector in SECTOR_ORDER else 99,
                "is_new":     True,
            })
            existing_urls.add(url)
            added += 1

        if new_rows:
            # 기존 데이터 읽기
            # [v2.3] 컬럼 구조: No(0), Area(1), Sector(2), Keyword(3), Province(4),
            #                    Date(5), Title(6), Source(7), URL(8), Summary(9)
            existing_rows = []
            for row in ws.iter_rows(min_row=2, values_only=True):
                if not row or not any(row):
                    continue
                r = list(row) + [""] * max(0, 10 - len(row))

                # URL은 인덱스 8
                row_url = str(r[8] or "").strip()
                sector_val = str(r[2] or "")

                # summary nan 방지
                summary_raw = str(r[9] or "")
                if summary_raw.lower() in ("nan", "none"):
                    summary_raw = ""

                existing_rows.append({
                    "no":         r[0],
                    "area":       str(r[1] or ""),
                    "sector":     sector_val,
                    "keyword":    str(r[3] or ""),
                    "province":   str(r[4] or ""),
                    "date":       str(r[5] or "")[:10],
                    "title":      str(r[6] or ""),
                    "source":     str(r[7] or ""),
                    "url":        row_url,
                    "summary":    summary_raw,
                    "sector_idx": SECTOR_ORDER.index(sector_val)
                                  if sector_val in SECTOR_ORDER else 99,
                    "is_new":     False,
                })

            all_rows = existing_rows + new_rows

            # [메모리 규칙] 1순위: Sector 우선순위, 2순위: Province 알파벳, 3순위: Date 내림차순
            all_rows.sort(key=lambda r: (
                r["sector_idx"],
                str(r["province"]),
                # Date 내림차순: 문자열 앞에 - 붙이면 역순
                "".join(chr(0x10FFFF - ord(c)) if c.isdigit() else c
                        for c in str(r["date"]).ljust(10)),
            ))

            # 시트 재작성
            ws.delete_rows(2, ws.max_row + 1)
            for i, r in enumerate(all_rows, 1):
                row_data = [
                    i,
                    r["area"], r["sector"], r["keyword"], r["province"],
                    r["date"], r["title"], r["source"], r["url"], r["summary"],
                ]
                row_idx = i + 1
                for col_idx, val in enumerate(row_data, 1):
                    cell = ws.cell(row=row_idx, column=col_idx, value=val)
                    if r.get("is_new"):
                        cell.fill = NEW_FILL
                        cell.font = NEW_FONT
                    else:
                        cell.font = Font(size=9)

        _freeze_and_filter(ws)
        logger.info(f"  Keywords History: {added}건 추가 (총 {ws.max_row - 1}건)")

    # ────────────────────────────────────────────────────────
    # 시트 4: Keyword History
    # [수정 v2.1] pandas 제거 → collections 모듈로 대체
    # ────────────────────────────────────────────────────────

    def _update_keyword_history(self, articles: list):
        ws        = self._get_or_create_sheet("Keyword History")
        HDR_STYLE = _hdr(COLOR["header_mid"])
        COLS = [
            ("Sector/Category", 22), ("Keyword",          25),
            ("Total Articles",  15), ("2024 Count",       12),
            ("2025 Count",      12), ("2026 Count",       12),
            ("Last Article Date", 16), ("Top Province",   20),
            ("Sample Title",    55),
        ]

        # [수정] pandas 제거 — collections.defaultdict + Counter 사용
        stats = defaultdict(lambda: {
            "total": 0, "2024": 0, "2025": 0, "2026": 0,
            "last_date": "", "provinces": Counter(), "sample": "",
        })

        sector_kw_map = {
            "Waste Water":           ["wastewater", "wwtp", "sewage",
                                      "wastewater treatment", "nuoc thai"],
            "Water Supply/Drainage": ["water supply", "clean water",
                                      "drinking water", "drainage",
                                      "cap nuoc", "thoat nuoc"],
            "Solid Waste":           ["solid waste", "landfill", "recycling",
                                      "waste-to-energy", "garbage",
                                      "incineration", "circular economy",
                                      "rac thai"],
            "Power":                 ["power plant", "electricity",
                                      "solar power", "wind power",
                                      "lng terminal", "dien",
                                      "nang luong tai tao"],
            "Oil & Gas":             ["oil and gas", "petroleum", "lng",
                                      "refinery", "gas pipeline", "dau khi"],
            "Industrial Parks":      ["industrial park", "economic zone",
                                      "vsip", "fdi", "khu cong nghiep"],
            "Smart City":            ["smart city", "digital city",
                                      "thanh pho thong minh"],
            "Transport":             ["metro", "railway", "expressway",
                                      "airport", "seaport", "long thanh",
                                      "cao toc", "duong sat"],
            "Construction":          ["real estate", "housing",
                                      "construction project", "bat dong san"],
        }

        for article in articles:
            sector   = str(article.get("sector") or "")
            title    = str(
                article.get("title_en") or article.get("title") or ""
            ).lower()
            date_s   = str(
                article.get("date") or article.get("published_date") or ""
            )[:10]
            year     = date_s[:4] if date_s else ""
            province = str(article.get("province") or "Vietnam")

            matched_kws = [
                kw for kw in sector_kw_map.get(sector, [])
                if kw.lower() in title
            ]
            if not matched_kws:
                matched_kws = [sector.lower() or "unknown"]

            for kw in matched_kws:
                key = (sector, kw)
                s   = stats[key]
                s["total"] += 1
                if year in ("2024", "2025", "2026"):
                    s[year] += 1
                if date_s > s["last_date"]:
                    s["last_date"] = date_s
                    # nan 방지
                    raw_sample = str(
                        article.get("title_en") or article.get("title") or ""
                    )[:80]
                    s["sample"] = raw_sample if raw_sample.lower() not in ("nan","none","") else ""
                s["provinces"][province] += 1

        # 시트 재작성
        ws.delete_rows(1, ws.max_row + 1)
        _set_header_row(ws, COLS, HDR_STYLE)

        row_idx = 2
        for (sector, kw), s in sorted(stats.items()):
            top_prov = (
                s["provinces"].most_common(1)[0][0]
                if s["provinces"] else "Vietnam"
            )
            _zebra_row(ws, row_idx, [
                sector, kw,
                s["total"], s["2024"], s["2025"], s["2026"],
                s["last_date"], top_prov, s["sample"],
            ])
            row_idx += 1

        _freeze_and_filter(ws)
        logger.info(f"  Keyword History: {row_idx - 2}개 키워드 집계")

    # ────────────────────────────────────────────────────────
    # 시트 5: Source
    # ────────────────────────────────────────────────────────

    def _update_source(self):
        ws = self._get_or_create_sheet("Source")
        if ws.max_row > 0 and ws.cell(1, 1).value == "Domain":
            return

        HDR_STYLE = _hdr(COLOR["header_dark"])
        COLS = [
            ("Domain", 30), ("URL", 45), ("Type", 20),
            ("Status", 15), ("Last Checked", 18),
            ("Check Result", 20), ("Articles Found", 15), ("Note", 30),
        ]
        ws.delete_rows(1, ws.max_row + 1)
        _set_header_row(ws, COLS, HDR_STYLE)

        SOURCES = [
            ("vietnamnews.vn",   "https://vietnamnews.vn",   "Media/News"),
            ("e.vnexpress.net",  "https://e.vnexpress.net",  "Media/News"),
            ("tuoitre.vn",       "https://tuoitre.vn",       "Media/News"),
            ("theleader.vn",     "https://theleader.vn",     "Business News"),
            ("vir.com.vn",       "https://vir.com.vn",       "Business News"),
            ("thanhnien.vn",     "https://thanhnien.vn",     "Media/News"),
            ("nhandan.vn",       "https://nhandan.vn",       "Official"),
            ("baodautu.vn",      "https://baodautu.vn",      "Business News"),
            ("bnews.vn",         "https://bnews.vn",         "Official"),
            ("construction.gov.vn","https://www.construction.gov.vn","Ministry"),
        ]
        for i, (domain, url, stype) in enumerate(SOURCES, 2):
            _zebra_row(ws, i, [domain, url, stype, "Active", "", "", "", ""])

    # ────────────────────────────────────────────────────────
    # 시트 6: RSS_Sources
    # ────────────────────────────────────────────────────────

    def _update_rss_sources(self, rss_results: list):
        ws        = self._get_or_create_sheet("RSS_Sources")
        HDR_STYLE = _hdr(COLOR["header_dark"])
        COLS = [
            ("Source",     30), ("URL",      55), ("Status",   12),
            ("Last Check", 20), ("Entries",  10), ("Collected", 12),
            ("New Added",  12), ("Error",    40),
        ]

        # [v2.4 수정] rss_results가 비어있으면 기존 데이터 유지 (삭제 금지)
        if not rss_results:
            if ws.max_row <= 1:
                # 헤더만 설정
                ws.delete_rows(1, ws.max_row + 1)
                _set_header_row(ws, COLS, HDR_STYLE)
            logger.info("  RSS_Sources: rss_results 없음 — 기존 데이터 유지")
            return

        ws.delete_rows(1, ws.max_row + 1)
        _set_header_row(ws, COLS, HDR_STYLE)

        now_str = self.now.strftime("%Y-%m-%d %H:%M:%S")
        for i, r in enumerate(rss_results, 2):
            _zebra_row(ws, i, [
                r.get("source",     ""),
                r.get("url",        ""),
                r.get("status",     "Unknown"),
                r.get("last_check", now_str),
                r.get("entries",    0),
                r.get("collected",  0),
                r.get("new_added",  0),
                r.get("error",      ""),
            ])

        _freeze_and_filter(ws)
        logger.info(f"  RSS_Sources: {len(rss_results)}개 피드 기록")

    # ────────────────────────────────────────────────────────
    # 시트 7: Collection_Log
    # ────────────────────────────────────────────────────────

    def _update_collection_log(self, articles: list, run_stats: dict):
        """
        파이프라인 실행 로그 추가
        [v2.3 수정] RSS Entries, New Added, Total DB 공백 문제 해결
                    run_stats 키 이름 통일
        """
        ws        = self._get_or_create_sheet("Collection_Log")
        HDR_STYLE = _hdr(COLOR["header_dark"])
        COLS = [
            ("Date",              13), ("Time",              10),
            ("Period Start",      20), ("Period End",        20),
            ("RSS Entries",       12), ("Articles Collected", 16),
            ("New Added",         12), ("Total DB",          10),
            ("Translation OK",    14), ("Translation Fail",  14),
            ("Sectors Found",     40), ("Run Mode",          15),
        ]

        current_cols = sum(1 for c in range(1, 20) if ws.cell(1, c).value)
        if ws.max_row == 0 or ws.cell(1, 1).value != "Date" or current_cols < len(COLS):
            _set_header_row(ws, COLS, HDR_STYLE)

        trans_ok   = sum(
            1 for a in articles
            if a.get("title_ko") and str(a["title_ko"]).strip()
        )
        trans_fail = len(articles) - trans_ok

        sector_cnt  = Counter(a.get("sector", "Unknown") for a in articles)
        sectors_str = ", ".join(
            f"{k}:{v}" for k, v in sector_cnt.most_common()
        )

        # [v2.3] run_stats 키 이름 통일 — 여러 키 이름 모두 지원
        rss_entries = (run_stats.get("rss_entries") or
                       run_stats.get("total_entries") or
                       run_stats.get("entries", 0) or 0)
        new_added   = (run_stats.get("new_added") or
                       run_stats.get("added") or
                       run_stats.get("new", 0) or 0)
        # [v2.4 수정] Total DB: run_stats에 없으면 News Database 실제 행 수 계산
        total_db    = (run_stats.get("total_db") or
                       run_stats.get("total", 0) or 0)
        if not total_db:
            try:
                ws_db = self.wb["News Database"]
                total_db = ws_db.max_row - 1  # 헤더 제외
            except Exception:
                total_db = 0
        collected   = (run_stats.get("collected") or
                       run_stats.get("total_collected") or
                       len(articles))

        ws.insert_rows(2)
        log_data = [
            self.now.strftime("%Y-%m-%d"),
            self.now.strftime("%H:%M:%S"),
            self.period_start.strftime("%Y-%m-%d %H:%M"),
            self.period_end.strftime("%Y-%m-%d %H:%M"),
            int(rss_entries),
            int(collected),
            int(new_added),
            int(total_db),
            trans_ok,
            trans_fail,
            sectors_str,
            run_stats.get("mode", "full"),
        ]
        for col_idx, val in enumerate(log_data, 1):
            ws.cell(row=2, column=col_idx, value=val)

        _freeze_and_filter(ws)
        logger.info("  Collection_Log: 1건 추가")

    # ────────────────────────────────────────────────────────
    # 시트 8: Summary
    # ────────────────────────────────────────────────────────

    def _update_summary(self, articles: list):
        ws = self._get_or_create_sheet("Summary")
        ws.delete_rows(1, ws.max_row + 1)

        ws_db        = self._get_or_create_sheet("News Database", 0)
        all_articles = []
        for row in ws_db.iter_rows(min_row=2, values_only=True):
            if not any(row):
                continue
            # 안전하게 컬럼 접근
            r = list(row) + [""] * max(0, 5 - len(row))
            all_articles.append({
                "area":     str(r[0] or ""),
                "sector":   str(r[1] or ""),
                "province": str(r[2] or ""),
                "date":     str(r[4] or "")[:10],
            })

        def is_this_week(article):
            d = str(
                article.get("date", "") or article.get("published_date", "")
            )[:10]
            if not d:
                return False
            try:
                dt = datetime.strptime(d, "%Y-%m-%d")
                return self.period_start <= dt <= self.period_end
            except ValueError:
                return False

        week_articles = [a for a in articles if is_this_week(a)]
        week_db_cnt   = sum(1 for a in all_articles if is_this_week(a))

        title_cell = ws.cell(
            row=1, column=1,
            value="Vietnam Infrastructure News — Summary",
        )
        title_cell.font = Font(bold=True, size=14, color=COLOR["header_dark"])
        ws.merge_cells("A1:H1")

        ws.cell(
            row=2, column=1,
            value=(
                f"Updated: {self.now.strftime('%Y-%m-%d %H:%M')}  |  "
                f"Total: {len(all_articles):,} articles  |  "
                f"This week: {week_db_cnt} articles "
                f"({self.period_start.strftime('%m/%d')}~"
                f"{self.period_end.strftime('%m/%d')})"
            ),
        )
        ws.merge_cells("A2:H2")

        row = 4

        def _section_title(text, color):
            nonlocal row
            cell = ws.cell(row=row, column=1, value=text)
            cell.fill = PatternFill("solid", fgColor=color)
            cell.font = Font(bold=True, size=11, color="FFFFFF")
            ws.merge_cells(f"A{row}:H{row}")
            row += 1

        _section_title(
            f"THIS WEEK  ({self.period_start.strftime('%Y-%m-%d')} ~ "
            f"{self.period_end.strftime('%Y-%m-%d')})",
            COLOR["header_green"],
        )
        ws.cell(row=row, column=1, value="Business Sector").font = Font(bold=True)
        ws.cell(row=row, column=2, value="Articles").font        = Font(bold=True)
        ws.cell(row=row, column=3, value="Share").font           = Font(bold=True)
        ws.cell(row=row, column=4, value="Top Province").font    = Font(bold=True)
        row += 1

        week_sectors   = Counter(a.get("sector",   "Unknown") for a in week_articles)
        for sector, cnt in week_sectors.most_common():
            prov_by_sector = Counter(
                a.get("province", "Vietnam")
                for a in week_articles if a.get("sector") == sector
            )
            top_prov = prov_by_sector.most_common(1)[0][0] if prov_by_sector else "—"
            pct = f"{cnt/len(week_articles)*100:.1f}%" if week_articles else "0%"
            _zebra_row(ws, row, [sector, cnt, pct, top_prov, "", "", "", ""])
            row += 1

        row += 1

        _section_title("ALL-TIME STATISTICS BY SECTOR", COLOR["header_dark"])
        ws.cell(row=row, column=1, value="Business Sector").font = Font(bold=True)
        ws.cell(row=row, column=2, value="Articles").font        = Font(bold=True)
        ws.cell(row=row, column=3, value="Share").font           = Font(bold=True)
        row += 1

        all_sectors = Counter(a.get("sector", "Unknown") for a in all_articles)
        for sector, cnt in all_sectors.most_common():
            pct = f"{cnt/len(all_articles)*100:.1f}%" if all_articles else "0%"
            _zebra_row(ws, row, [sector, cnt, pct, "", "", "", "", ""])
            row += 1

        row += 1

        _section_title("TOP 20 PROVINCES (ALL-TIME)", COLOR["header_mid"])
        ws.cell(row=row, column=1, value="Province").font  = Font(bold=True)
        ws.cell(row=row, column=2, value="Articles").font  = Font(bold=True)
        ws.cell(row=row, column=3, value="Share").font     = Font(bold=True)
        row += 1

        all_provs = Counter(a.get("province", "Vietnam") for a in all_articles)
        for prov, cnt in all_provs.most_common(20):
            pct = f"{cnt/len(all_articles)*100:.1f}%" if all_articles else "0%"
            _zebra_row(ws, row, [prov, cnt, pct, "", "", "", "", ""])
            row += 1

        row += 1

        _section_title("TRANSLATION QUALITY CHECK", COLOR["header_green"])
        trans_ok   = sum(
            1 for a in week_articles
            if a.get("title_en") and a["title_en"] != a.get("title", "")
        )
        trans_fail = len(week_articles) - trans_ok
        trans_pct  = (
            f"{trans_ok/len(week_articles)*100:.1f}%"
            if week_articles else "N/A"
        )
        ws.cell(row=row, column=1, value="Translation Success (this week):")
        ws.cell(row=row, column=2, value=f"{trans_ok} / {len(week_articles)} ({trans_pct})")
        row += 1
        ws.cell(row=row, column=1, value="Translation Failed:")
        ws.cell(row=row, column=2, value=trans_fail)
        row += 1
        has_ko = sum(1 for a in week_articles if a.get("summary_ko", "").strip())
        ws.cell(row=row, column=1, value="Korean Summary Available:")
        ws.cell(row=row, column=2, value=f"{has_ko} / {len(week_articles)}")

        ws.column_dimensions["A"].width = 38
        ws.column_dimensions["B"].width = 15
        ws.column_dimensions["C"].width = 12
        ws.column_dimensions["D"].width = 22
        ws.freeze_panes = "A3"

        logger.info(
            f"  Summary: 전체 {len(all_articles)}건 / 금주 {len(week_articles)}건"
        )

    # ────────────────────────────────────────────────────────
    # 시트 9: Province_Keywords
    # ────────────────────────────────────────────────────────

    def _update_province_keywords(self):
        ws = self._get_or_create_sheet("Province_Keywords")
        HDR_STYLE = _hdr(COLOR["header_gold"], font_color="1C2833")
        COLS = [
            ("Province (Standard)", 28), ("Region Category",  22),
            ("Keywords",            80), ("Keyword Count",    14),
            ("Old Province Names",  35), ("Updated",          16),
        ]

        # [v2.4 수정] PROVINCE_OK=False 일 때 기존 데이터 유지 (삭제 금지)
        if not PROVINCE_OK:
            if ws.max_row <= 1:
                ws.delete_rows(1, ws.max_row + 1)
                _set_header_row(ws, COLS, HDR_STYLE)
            logger.info("  Province_Keywords: province_keywords 모듈 없음 — 기존 데이터 유지")
            return

        old_names_map = defaultdict(list)
        try:
            from scripts.province_keywords import PROVINCE_ALIAS_MAP
            for old, new in PROVINCE_ALIAS_MAP.items():
                old_names_map[new].append(old)
        except ImportError:
            pass

        today_str  = self.now.strftime("%Y-%m-%d")
        prov_data  = get_provinces_for_excel()

        if not prov_data:
            # 데이터 없으면 기존 유지
            logger.info("  Province_Keywords: prov_data 없음 — 기존 데이터 유지")
            return

        ws.delete_rows(1, ws.max_row + 1)
        _set_header_row(ws, COLS, HDR_STYLE)

        for i, prow in enumerate(prov_data, 2):
            province  = prow["Province"]
            old_names = ", ".join(old_names_map.get(province, []))
            _zebra_row(ws, i, [
                province,
                prow["Category"],
                prow["Keywords"],
                prow["Keyword_Count"],
                old_names,
                today_str,
            ])

        _freeze_and_filter(ws)
        logger.info(f"  Province_Keywords: {len(prov_data)}개 성/시 기록")

    # ────────────────────────────────────────────────────────
    # 유틸리티
    # ────────────────────────────────────────────────────────

    def _get_or_create_sheet(self, name: str, position: int = None):
        if name in self.wb.sheetnames:
            return self.wb[name]
        if position is not None:
            ws = self.wb.create_sheet(name, position)
        else:
            ws = self.wb.create_sheet(name)
        return ws
