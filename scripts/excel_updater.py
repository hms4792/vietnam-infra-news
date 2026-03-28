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

설계 원칙:
  - 각 시트는 독립적으로 업데이트 (하나 실패해도 나머지 계속)
  - 중복 방지: URL 기준 중복 체크
  - 검증용 데이터: 날짜/출처/키워드 매칭근거 모두 기록
"""

import logging
import os
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
    "header_dark":  "1A5276",   # 헤더 진한 파란색
    "header_mid":   "2E86C1",   # 헤더 중간 파란색
    "header_green": "1E8449",   # 헤더 녹색 (Summary)
    "header_gold":  "B7950B",   # 헤더 금색 (Province)
    "row_even":     "EBF5FB",   # 짝수행 배경
    "row_odd":      "FFFFFF",   # 홀수행 배경
    "highlight":    "FDFEFE",   # 강조 배경
    "white":        "FFFFFF",
    "font_white":   "FFFFFF",
    "font_dark":    "1C2833",
}

EXCEL_PATH = Path("data/database/Vietnam_Infra_News_Database_Final.xlsx")


# ════════════════════════════════════════════════════════════
# 스타일 헬퍼
# ════════════════════════════════════════════════════════════

def _hdr(color_hex: str, bold=True, font_color="FFFFFF") -> dict:
    """헤더 스타일 dict 반환"""
    return {
        "fill": PatternFill("solid", fgColor=color_hex),
        "font": Font(bold=bold, color=font_color, size=10),
        "align": Alignment(horizontal="center", vertical="center", wrap_text=True),
        "border": Border(
            bottom=Side(style="medium", color="AAAAAA"),
        ),
    }

def _apply_style(cell, style: dict):
    """셀에 스타일 dict 적용"""
    if "fill"   in style: cell.fill      = style["fill"]
    if "font"   in style: cell.font      = style["font"]
    if "align"  in style: cell.alignment = style["align"]
    if "border" in style: cell.border   = style["border"]

def _set_header_row(ws, headers: list, style_dict: dict, row=1):
    """헤더 행 일괄 스타일 적용"""
    for col, (title, width) in enumerate(headers, 1):
        cell = ws.cell(row=row, column=col, value=title)
        _apply_style(cell, style_dict)
        ws.column_dimensions[get_column_letter(col)].width = width

def _zebra_row(ws, row_idx: int, data: list, font_size=9):
    """얼룩말 줄무늬 스타일로 데이터 행 삽입"""
    bg = COLOR["row_even"] if row_idx % 2 == 0 else COLOR["row_odd"]
    fill = PatternFill("solid", fgColor=bg)
    font = Font(size=font_size, color=COLOR["font_dark"])
    align = Alignment(wrap_text=True, vertical="top")

    for col, val in enumerate(data, 1):
        cell = ws.cell(row=row_idx, column=col, value=val)
        cell.fill      = fill
        cell.font      = font
        cell.alignment = align

def _freeze_and_filter(ws, freeze="A2"):
    """고정 행 + 자동 필터 설정"""
    ws.freeze_panes = freeze
    if ws.max_row > 1:
        ws.auto_filter.ref = ws.dimensions


# ════════════════════════════════════════════════════════════
# 메인 클래스
# ════════════════════════════════════════════════════════════

class ExcelUpdater:
    """
    9개 시트 전체를 목적에 맞게 업데이트하는 클래스
    
    사용법:
        updater = ExcelUpdater()
        updater.update_all(
            articles=processed_articles,
            run_stats=stats_dict,
            rss_results=rss_list,
        )
    """

    def __init__(self, excel_path: Path = EXCEL_PATH):
        self.path = excel_path
        self.wb   = None
        self.now  = datetime.now()

        # 금주 수집 기간 계산 (토~토, 한국 시간 기준)
        # 이번 주 토요일 18:00 = 수집 마감
        # 지난 주 토요일 18:00 = 수집 시작
        self.period_end   = self._get_this_saturday_6pm()
        self.period_start = self.period_end - timedelta(days=7)

    def _get_this_saturday_6pm(self) -> datetime:
        """이번 주 토요일 18:00 (KST) 계산"""
        today = self.now
        days_until_sat = (5 - today.weekday()) % 7   # 0=Mon … 5=Sat
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
        """
        9개 시트 전체 업데이트

        Args:
            articles:    처리 완료 기사 리스트 (번역 포함)
            run_stats:   수집 통계 dict
            rss_results: RSS 피드별 결과 리스트
            keyword_map: 키워드별 매칭 기사 dict
        Returns:
            저장된 파일 경로
        """
        if not OPENPYXL_OK:
            raise RuntimeError("openpyxl 미설치")

        self.path.parent.mkdir(parents=True, exist_ok=True)

        # 기존 파일 로드 또는 신규 생성
        if self.path.exists():
            self.wb = openpyxl.load_workbook(self.path)
            logger.info(f"[Excel] 기존 파일 로드: {self.path}")
            # 구버전 중복 시트 자동 제거
            for old_sheet in ["Keywords_History"]:
                if old_sheet in self.wb.sheetnames:
                    del self.wb[old_sheet]
                    logger.info(f"[Excel] 구버전 시트 제거: {old_sheet}")
        else:
            self.wb = openpyxl.Workbook()
            logger.info("[Excel] 신규 파일 생성")

        # 시트 업데이트 (실패해도 계속)
        results = {}
        tasks = [
            ("News Database",    lambda: self._update_news_database(articles)),
            ("Keywords",         lambda: self._update_keywords()),
            ("Keywords History", lambda: self._update_keywords_history(articles, keyword_map)),
            # Keywords_History(구버전) 시트가 있으면 제거
            ("Keyword History",  lambda: self._update_keyword_history(articles)),
            ("Source",           lambda: self._update_source()),
            ("RSS_Sources",      lambda: self._update_rss_sources(rss_results or [])),
            ("Collection_Log",   lambda: self._update_collection_log(articles, run_stats or {})),
            ("Summary",          lambda: self._update_summary(articles)),
            ("Province_Keywords",lambda: self._update_province_keywords()),
        ]

        for sheet_name, update_fn in tasks:
            try:
                update_fn()
                results[sheet_name] = "✓"
                logger.info(f"[Excel] 시트 업데이트 완료: {sheet_name}")
            except Exception as e:
                results[sheet_name] = f"✗ {e}"
                logger.error(f"[Excel] 시트 업데이트 실패: {sheet_name} - {e}", exc_info=True)

        self.wb.save(self.path)
        logger.info(f"[Excel] 저장 완료: {self.path}")

        # 결과 요약 로그
        for name, status in results.items():
            logger.info(f"  [{status}] {name}")

        return str(self.path)

    # ────────────────────────────────────────────────────────
    # 시트 1: News Database (기사 원장)
    # ────────────────────────────────────────────────────────

    def _update_news_database(self, articles: list):
        """번역 완료 기사 추가 (중복 URL 제외)"""
        ws = self._get_or_create_sheet("News Database", 0)
        HDR_STYLE = _hdr(COLOR["header_dark"])

        COLS = [
            ("Area",          18), ("Business Sector", 22), ("Province",       18),
            ("News Title",    55), ("Date",             13), ("Source",          22),
            ("Link",          45), ("Short Summary",   55), ("title_ko",        45),
            ("title_en",      45), ("title_vi",        45), ("summary_ko",      55),
            ("summary_en",    55), ("summary_vi",      55),
        ]

        # 헤더 설정 (비어있거나 구버전 8컬럼이면 14컬럼으로 업그레이드)
        current_header_count = sum(1 for c in range(1, 15) if ws.cell(1, c).value)
        if ws.max_row == 0 or ws.cell(1, 1).value is None or current_header_count < 14:
            _set_header_row(ws, COLS, HDR_STYLE)
            ws.row_dimensions[1].height = 22
            logger.info(f"  News Database 헤더 업그레이드: {current_header_count}→14컬럼")

        # 기존 URL 수집 (중복 방지)
        existing_urls = set()
        link_col = 7  # Link 컬럼 인덱스
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[link_col - 1]:
                existing_urls.add(str(row[link_col - 1]).strip())

        # 신규 기사 추가
        added = 0
        for article in articles:
            url = str(article.get("url", "")).strip()
            if url and url in existing_urls:
                continue

            row_data = [
                article.get("area", ""),
                article.get("sector", ""),
                article.get("province", "") or get_province_from_text(
                    article.get("title", "")) if PROVINCE_OK else article.get("province", ""),
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
            # 최상단(2행)에 삽입 - 최신 기사가 항상 맨 위에
            ws.insert_rows(2)
            for col_idx, val in enumerate(row_data, 1):
                ws.cell(row=2, column=col_idx, value=val)
            existing_urls.add(url)
            added += 1

        _freeze_and_filter(ws)
        logger.info(f"  News Database: {added}건 추가 (누적 {ws.max_row - 1}건)")

    # ────────────────────────────────────────────────────────
    # 시트 2: Keywords (섹터별 현행 키워드 참조표)
    # ────────────────────────────────────────────────────────

    def _update_keywords(self):
        """섹터별 키워드 목록 현행화 (덮어쓰기)"""
        ws = self._get_or_create_sheet("Keywords")
        ws.delete_rows(1, ws.max_row + 1)   # 전체 초기화

        HDR_STYLE = _hdr(COLOR["header_dark"])
        COLS = [
            ("Business Sector", 22), ("Area", 18), ("Keywords", 80),
            ("Keyword Count", 15), ("Last Updated", 18),
        ]
        _set_header_row(ws, COLS, HDR_STYLE)

        # 섹터 키워드 데이터 (기존 파이프라인 키워드 + 업데이트)
        SECTOR_KEYWORDS = {
            "Waste Water":        ("Environment", [
                "wastewater", "waste water", "wastewater treatment", "wwtp",
                "sewage", "sewage treatment", "sewer", "sewerage",
                "wastewater plant", "effluent treatment",
                "nước thải", "xử lý nước thải", "hệ thống thoát nước",
            ]),
            "Water Supply/Drainage": ("Environment", [
                "water supply", "clean water", "drinking water", "tap water",
                "potable water", "water infrastructure", "water pipeline",
                "drainage system", "flood drainage", "stormwater",
                "water plant", "water treatment plant", "water network",
                "cấp nước", "thoát nước", "nước sạch",
            ]),
            "Solid Waste":        ("Environment", [
                "solid waste", "garbage", "trash", "landfill",
                "waste management", "recycling", "incineration",
                "waste-to-energy", "wte", "municipal waste",
                "circular economy", "compost", "hazardous waste",
                "rác thải", "xử lý rác", "bãi rác", "đốt rác",
            ]),
            "Power":              ("Energy", [
                "power plant", "power station", "electricity", "power generation",
                "thermal power", "coal power", "gas power", "lng power",
                "solar power", "wind power", "renewable energy",
                "transmission line", "grid", "substation", "lng terminal",
                "điện", "nhà máy điện", "năng lượng tái tạo",
            ]),
            "Oil & Gas":          ("Energy", [
                "oil and gas", "oil & gas", "petroleum", "refinery",
                "oil field", "gas field", "offshore oil", "lpg",
                "lng", "gas pipeline", "oil terminal", "petrochemical",
                "dầu khí", "lọc hóa dầu", "khí đốt",
            ]),
            "Industrial Parks":   ("Urban Development", [
                "industrial park", "industrial zone", "industrial complex",
                "economic zone", "export processing zone", "epz",
                "special economic zone", "sez", "vsip",
                "fdi", "foreign direct investment", "manufacturing hub",
                "khu công nghiệp", "khu kinh tế", "khu chế xuất",
            ]),
            "Smart City":         ("Urban Development", [
                "smart city", "smart urban", "digital city",
                "intelligent transport", "smart traffic", "iot city",
                "digital transformation", "e-government",
                "thành phố thông minh", "đô thị thông minh",
            ]),
            "Transport":          ("Urban Development", [
                "metro", "metro line", "subway", "urban rail", "light rail",
                "railway", "high-speed rail", "expressway", "highway",
                "airport", "seaport", "port", "bridge", "tunnel",
                "long thanh", "north-south railway",
                "đường sắt", "sân bay", "cảng biển", "cao tốc",
            ]),
            "Construction":       ("Urban Development", [
                "real estate", "building", "property", "cement", "housing",
                "steel", "construction project", "new urban area",
                "bất động sản", "xây dựng", "nhà ở",
            ]),
        }

        today_str = self.now.strftime("%Y-%m-%d")
        for row_idx, (sector, (area, kws)) in enumerate(SECTOR_KEYWORDS.items(), 2):
            _zebra_row(ws, row_idx, [
                sector, area, ", ".join(kws), len(kws), today_str,
            ])

        _freeze_and_filter(ws)

    # ────────────────────────────────────────────────────────
    # 시트 3: Keywords History (키워드별 매칭 기사 상세 이력)
    # ────────────────────────────────────────────────────────

    def _update_keywords_history(self, articles: list, keyword_map: dict = None):
        """
        Keywords History 시트 - 핵심 설계 원칙:
          1순위 정렬: Sector (우선순위 순서: Waste Water → Water Supply → Solid Waste → Power → Oil&Gas → Transport → Industrial Parks → Smart City)
          2순위 정렬: Province (알파벳순)
          3순위 정렬: Date 내림차순 (최신이 맨 위)
          신규 기사: 노란색(#FFF9C4) 하이라이트로 구분
        """
        ws = self._get_or_create_sheet("Keywords History")
        HDR_STYLE = _hdr(COLOR["header_dark"])
        COLS = [
            ("No",       6), ("Area",          18), ("Sector",         22),
            ("Keyword", 25), ("Province",       20), ("Date",           13),
            ("Title",   60), ("Source",         22), ("URL",            45),
            ("Summary", 55),
        ]

        # 헤더 설정 (없거나 구버전이면 업그레이드)
        if ws.max_row == 0 or ws.cell(1, 1).value not in ("No", None):
            pass
        if ws.cell(1, 1).value != "No":
            _set_header_row(ws, COLS, HDR_STYLE)

        # 기존 URL 수집 (중복 방지)
        existing_urls = set()
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row and row[8]:
                existing_urls.add(str(row[8]).strip())

        # ── 신규 기사 추가 ─────────────────────────────────────
        NEW_FILL  = PatternFill(start_color="FFF9C4", end_color="FFF9C4", fill_type="solid")
        NEW_FONT  = Font(bold=True, size=9, color="1A1A1A")

        # 섹터 우선순위 정의
        SECTOR_ORDER = [
            "Waste Water", "Water Supply/Drainage", "Solid Waste",
            "Power", "Oil & Gas",
            "Transport", "Industrial Parks", "Smart City", "Construction"
        ]

        added = 0
        new_rows = []  # 신규 기사 임시 저장

        for article in articles:
            url = str(article.get("url", "")).strip()
            if url in existing_urls:
                continue

            province = article.get("province", "") or (
                get_province_from_text(article.get("title", ""))
                if PROVINCE_OK else "Vietnam"
            )
            matched_kw = article.get("matched_keyword", "") or article.get("keyword", "") or ""
            date_val = str(article.get("date") or article.get("published_date", ""))[:10]
            sector = article.get("sector", "")

            new_rows.append({
                "area":     article.get("area", ""),
                "sector":   sector,
                "keyword":  matched_kw,
                "province": province,
                "date":     date_val,
                "title":    article.get("title_en") or article.get("title", ""),
                "source":   article.get("source", ""),
                "url":      url,
                "summary":  article.get("summary_en", "")[:200],
                "sector_idx": SECTOR_ORDER.index(sector) if sector in SECTOR_ORDER else 99,
            })
            existing_urls.add(url)
            added += 1

        if new_rows:
            # ── 전체 시트 데이터 + 신규 합쳐서 재정렬 ──────────────
            # 기존 데이터 읽기
            existing_rows = []
            for row in ws.iter_rows(min_row=2, values_only=True):
                if not any(row): continue
                sector = str(row[2] or '')
                existing_rows.append({
                    "no":       row[0],
                    "area":     str(row[1] or ''),
                    "sector":   sector,
                    "keyword":  str(row[3] or ''),
                    "province": str(row[4] or ''),
                    "date":     str(row[5] or '')[:10],
                    "title":    str(row[6] or ''),
                    "source":   str(row[7] or ''),
                    "url":      str(row[8] or ''),
                    "summary":  str(row[9] or ''),
                    "sector_idx": SECTOR_ORDER.index(sector) if sector in SECTOR_ORDER else 99,
                    "is_new":   False,
                })

            # 신규 기사에 is_new 플래그
            for r in new_rows:
                r["is_new"] = True

            # 전체 합치기
            all_rows = existing_rows + new_rows

            # 1순위: Sector(우선순위), 2순위: Province(알파벳), 3순위: Date(최신→오래된)
            all_rows.sort(key=lambda r: (
                r["sector_idx"],
                r["province"],
                r["date"]  # 내림차순은 아래서 역순
            ))
            # Date만 역순 적용
            # sector/province 같은 그룹 내에서 최신이 맨 위
            all_rows.sort(key=lambda r: (
                r["sector_idx"],
                r["province"],
                tuple(-ord(c) for c in r["date"].ljust(10))
            ))

            # 번호 재부여 & 시트 재작성
            ws.delete_rows(2, ws.max_row + 1)

            for i, r in enumerate(all_rows, 1):
                row_data = [
                    i,
                    r["area"], r["sector"], r["keyword"], r["province"],
                    r["date"], r["title"], r["source"], r["url"], r["summary"]
                ]
                row_idx = i + 1  # 헤더 다음부터
                for col_idx, val in enumerate(row_data, 1):
                    cell = ws.cell(row=row_idx, column=col_idx, value=val)
                    if r.get("is_new"):
                        cell.fill = NEW_FILL
                        cell.font = NEW_FONT
                    else:
                        cell.font = Font(size=9)

        _freeze_and_filter(ws)
        logger.info(f"  Keywords History: {added}건 추가")

    # ────────────────────────────────────────────────────────
    # 시트 4: Keyword History (키워드별 통계 집계)
    # ────────────────────────────────────────────────────────

    def _update_keyword_history(self, articles: list):
        """
        키워드별 총 기사 수, 연도별 카운트, 최신 기사 등 통계 갱신
        """
        ws = self._get_or_create_sheet("Keyword History")

        HDR_STYLE = _hdr(COLOR["header_mid"])
        COLS = [
            ("Sector/Category", 22), ("Keyword",         25),
            ("Total Articles",  15), ("2024 Count",      12),
            ("2025 Count",      12), ("2026 Count",      12),
            ("Last Article Date", 16), ("Top Province",  20),
            ("Sample Title",    55),
        ]

        # 통계 집계
        from collections import defaultdict, Counter
        import pandas as pd

        stats = defaultdict(lambda: {
            "total": 0, "2024": 0, "2025": 0, "2026": 0,
            "last_date": "", "provinces": Counter(), "sample": "",
        })

        # 섹터 → 키워드 역매핑
        sector_kw_map = {
            "Waste Water": ["wastewater", "wwtp", "sewage", "wastewater treatment",
                            "nước thải"],
            "Water Supply/Drainage": ["water supply", "clean water", "drinking water",
                                      "drainage", "cấp nước", "thoát nước"],
            "Solid Waste": ["solid waste", "landfill", "recycling", "waste-to-energy",
                            "garbage", "incineration", "circular economy", "rác thải"],
            "Power": ["power plant", "electricity", "solar power", "wind power",
                      "lng terminal", "điện", "năng lượng tái tạo"],
            "Oil & Gas": ["oil and gas", "petroleum", "lng", "refinery",
                          "gas pipeline", "dầu khí"],
            "Industrial Parks": ["industrial park", "economic zone", "vsip", "fdi",
                                 "khu công nghiệp"],
            "Smart City": ["smart city", "digital city", "thành phố thông minh"],
            "Transport": ["metro", "railway", "expressway", "airport", "seaport",
                          "long thanh", "cao tốc", "đường sắt"],
            "Construction": ["real estate", "housing", "construction project",
                             "bất động sản"],
        }

        for article in articles:
            sector  = article.get("sector", "")
            title   = (article.get("title_en") or article.get("title", "")).lower()
            date_s  = str(article.get("date", ""))[:10]
            year    = date_s[:4] if date_s else ""
            province = article.get("province", "Vietnam")

            # 해당 섹터의 키워드 중 제목에 포함된 것 찾기
            matched_kws = []
            for kw in sector_kw_map.get(sector, []):
                if kw.lower() in title:
                    matched_kws.append(kw)
            if not matched_kws:
                matched_kws = [sector.lower()]  # 키워드 미매칭 시 섹터명 사용

            for kw in matched_kws:
                key = (sector, kw)
                s   = stats[key]
                s["total"] += 1
                if year in ("2024", "2025", "2026"):
                    s[year] += 1
                if date_s > s["last_date"]:
                    s["last_date"] = date_s
                    s["sample"]    = (article.get("title_en") or
                                      article.get("title", ""))[:80]
                s["provinces"][province] += 1

        # 시트 재작성
        ws.delete_rows(1, ws.max_row + 1)
        _set_header_row(ws, COLS, HDR_STYLE)

        row_idx = 2
        for (sector, kw), s in sorted(stats.items()):
            top_prov = s["provinces"].most_common(1)[0][0] if s["provinces"] else "Vietnam"
            _zebra_row(ws, row_idx, [
                sector, kw,
                s["total"], s["2024"], s["2025"], s["2026"],
                s["last_date"], top_prov, s["sample"],
            ])
            row_idx += 1

        _freeze_and_filter(ws)
        logger.info(f"  Keyword History: {row_idx - 2}개 키워드 집계")

    # ────────────────────────────────────────────────────────
    # 시트 5: Source (출처 도메인 목록)
    # ────────────────────────────────────────────────────────

    def _update_source(self):
        """수집 대상 뉴스 출처 목록 (정적 참조, 헤더만 유지)"""
        ws = self._get_or_create_sheet("Source")
        if ws.max_row > 0 and ws.cell(1, 1).value == "Domain":
            return   # 이미 존재하면 변경 없음

        HDR_STYLE = _hdr(COLOR["header_dark"])
        COLS = [
            ("Domain", 30), ("URL", 45), ("Type", 20),
            ("Status", 15), ("Last Checked", 18),
            ("Check Result", 20), ("Articles Found", 15), ("Note", 30),
        ]
        ws.delete_rows(1, ws.max_row + 1)
        _set_header_row(ws, COLS, HDR_STYLE)

        SOURCES = [
            ("vietnamnews.vn", "https://vietnamnews.vn", "Media/News"),
            ("e.vnexpress.net", "https://e.vnexpress.net", "Media/News"),
            ("tuoitre.vn", "https://tuoitre.vn", "Media/News"),
            ("theleader.vn", "https://theleader.vn", "Business News"),
            ("vir.com.vn", "https://vir.com.vn", "Business News"),
            ("thanhnien.vn", "https://thanhnien.vn", "Media/News"),
            ("nhandan.vn", "https://nhandan.vn", "Official"),
            ("baodautu.vn", "https://baodautu.vn", "Business News"),
            ("bnews.vn", "https://bnews.vn", "Official"),
            ("construction.gov.vn", "https://www.construction.gov.vn", "Ministry"),
        ]
        for i, (domain, url, stype) in enumerate(SOURCES, 2):
            _zebra_row(ws, i, [domain, url, stype, "Active", "", "", "", ""])

    # ────────────────────────────────────────────────────────
    # 시트 6: RSS_Sources (RSS 피드 수집 결과 로그)
    # ────────────────────────────────────────────────────────

    def _update_rss_sources(self, rss_results: list):
        """RSS 피드별 수집 결과 기록"""
        ws = self._get_or_create_sheet("RSS_Sources")

        HDR_STYLE = _hdr(COLOR["header_dark"])
        COLS = [
            ("Source",     30), ("URL",         55), ("Status",  12),
            ("Last Check", 20), ("Entries",     10), ("Collected", 12),
            ("New Added",  12), ("Error",       40),
        ]

        # 전체 초기화 후 재작성
        ws.delete_rows(1, ws.max_row + 1)
        _set_header_row(ws, COLS, HDR_STYLE)

        now_str = self.now.strftime("%Y-%m-%d %H:%M:%S")
        for i, r in enumerate(rss_results, 2):
            _zebra_row(ws, i, [
                r.get("source", ""),
                r.get("url", ""),
                r.get("status", "Unknown"),
                r.get("last_check", now_str),
                r.get("entries", 0),
                r.get("collected", 0),
                r.get("new_added", 0),
                r.get("error", ""),
            ])

        _freeze_and_filter(ws)
        logger.info(f"  RSS_Sources: {len(rss_results)}개 피드 기록")

    # ────────────────────────────────────────────────────────
    # 시트 7: Collection_Log (실행별 수집 통계)
    # ────────────────────────────────────────────────────────

    def _update_collection_log(self, articles: list, run_stats: dict):
        """파이프라인 실행 로그 추가"""
        ws = self._get_or_create_sheet("Collection_Log")

        HDR_STYLE = _hdr(COLOR["header_dark"])
        COLS = [
            ("Date",              13), ("Time",            10),
            ("Period Start",      20), ("Period End",       20),
            ("RSS Entries",       12), ("Articles Collected", 16),
            ("New Added",         12), ("Total DB",         10),
            ("Translation OK",    14), ("Translation Fail", 14),
            ("Sectors Found",     40), ("Run Mode",         15),
        ]

        # 헤더가 없거나 컬럼 수가 다르면 업그레이드
        current_cols = sum(1 for c in range(1, 20) if ws.cell(1, c).value)
        if ws.max_row == 0 or ws.cell(1, 1).value != "Date" or current_cols < len(COLS):
            _set_header_row(ws, COLS, HDR_STYLE)
            logger.info(f"  Collection_Log 헤더 업그레이드: {current_cols}→{len(COLS)}컬럼")

        # 번역 성공/실패 집계
        trans_ok   = sum(1 for a in articles
                         if a.get("title_en") and
                         a["title_en"] != a.get("title", ""))
        trans_fail = len(articles) - trans_ok

        # 섹터별 집계
        from collections import Counter
        sector_cnt = Counter(a.get("sector", "Unknown") for a in articles)
        sectors_str = ", ".join(f"{k}:{v}" for k, v in sector_cnt.most_common())

        # 최상단 삽입 (최신 실행 기록이 맨 위)
        ws.insert_rows(2)
        log_data = [
            self.now.strftime("%Y-%m-%d"),
            self.now.strftime("%H:%M:%S"),
            self.period_start.strftime("%Y-%m-%d %H:%M"),
            self.period_end.strftime("%Y-%m-%d %H:%M"),
            run_stats.get("rss_entries", 0),
            run_stats.get("collected", len(articles)),
            run_stats.get("new_added", 0),
            run_stats.get("total_db", 0),
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
    # 시트 8: Summary (전체 요약 + 금주 요약 분리)
    # ────────────────────────────────────────────────────────

    def _update_summary(self, articles: list):
        """
        전체 누적 통계 + 금주(토~토) 수집 분리 요약
        전체 통계는 News Database 시트 전체 데이터 기준
        금주 통계는 금번 수집된 articles 기준
        """
        ws = self._get_or_create_sheet("Summary")
        ws.delete_rows(1, ws.max_row + 1)

        from collections import Counter

        # 전체 누적 데이터는 News Database 시트에서 직접 읽기
        ws_db = self._get_or_create_sheet("News Database", 0)
        all_articles = []
        for row in ws_db.iter_rows(min_row=2, values_only=True):
            if not any(row): continue
            all_articles.append({
                'area':     str(row[0] or ''),
                'sector':   str(row[1] or ''),
                'province': str(row[2] or ''),
                'date':     str(row[4] or '')[:10],
            })

        # 금주 기사 필터 (금번 수집된 articles 기준)
        def is_this_week(article):
            d = str(article.get("date", "") or article.get("published_date", ""))[:10]
            if not d:
                return False
            try:
                dt = datetime.strptime(d, "%Y-%m-%d")
                return self.period_start <= dt <= self.period_end
            except ValueError:
                return False

        week_articles = [a for a in articles if is_this_week(a)]
        # 전체 DB에서도 금주 기사 카운트
        week_db_cnt = sum(1 for a in all_articles if is_this_week(a))

        # ── 헤더 ─────────────────────────────────────────────
        title_cell = ws.cell(row=1, column=1,
                             value="🇻🇳 Vietnam Infrastructure News — Summary")
        title_cell.font = Font(bold=True, size=14, color=COLOR["header_dark"])
        ws.merge_cells("A1:H1")

        ws.cell(row=2, column=1,
                value=f"Updated: {self.now.strftime('%Y-%m-%d %H:%M')}  |  "
                      f"Total: {len(all_articles):,} articles  |  "
                      f"This week: {week_db_cnt} articles "
                      f"({self.period_start.strftime('%m/%d')}~"
                      f"{self.period_end.strftime('%m/%d')})")
        ws.merge_cells("A2:H2")

        row = 4

        def _section_title(text, color):
            cell = ws.cell(row=row, column=1, value=text)
            cell.fill = PatternFill("solid", fgColor=color)
            cell.font = Font(bold=True, size=11, color="FFFFFF")
            ws.merge_cells(f"A{row}:H{row}")

        # ── 섹션 A: 금주 수집 요약 ────────────────────────────
        _section_title(
            f"📅 THIS WEEK  ({self.period_start.strftime('%Y-%m-%d')} ~ "
            f"{self.period_end.strftime('%Y-%m-%d')})", COLOR["header_green"]
        )
        row += 1
        ws.cell(row=row, column=1, value="Business Sector").font = Font(bold=True)
        ws.cell(row=row, column=2, value="Articles").font       = Font(bold=True)
        ws.cell(row=row, column=3, value="Share").font          = Font(bold=True)
        ws.cell(row=row, column=4, value="Top Province").font   = Font(bold=True)
        row += 1

        week_sectors = Counter(a.get("sector", "Unknown") for a in week_articles)
        week_provinces = Counter(a.get("province", "Vietnam") for a in week_articles)
        for sector, cnt in week_sectors.most_common():
            top_prov = "—"
            prov_by_sector = Counter(
                a.get("province", "Vietnam")
                for a in week_articles if a.get("sector") == sector
            )
            if prov_by_sector:
                top_prov = prov_by_sector.most_common(1)[0][0]
            pct = f"{cnt/len(week_articles)*100:.1f}%" if week_articles else "0%"
            _zebra_row(ws, row, [sector, cnt, pct, top_prov, "", "", "", ""])
            row += 1

        row += 1  # 빈 줄

        # ── 섹션 B: 전체 누적 섹터 통계 ──────────────────────
        _section_title("📊 ALL-TIME STATISTICS BY SECTOR", COLOR["header_dark"])
        row += 1
        ws.cell(row=row, column=1, value="Business Sector").font = Font(bold=True)
        ws.cell(row=row, column=2, value="Articles").font       = Font(bold=True)
        ws.cell(row=row, column=3, value="Share").font          = Font(bold=True)
        row += 1

        all_sectors = Counter(a.get("sector", "Unknown") for a in all_articles)
        for sector, cnt in all_sectors.most_common():
            pct = f"{cnt/len(all_articles)*100:.1f}%" if all_articles else "0%"
            _zebra_row(ws, row, [sector, cnt, pct, "", "", "", "", ""])
            row += 1

        row += 1

        # ── 섹션 C: 전체 Province TOP 20 ─────────────────────
        _section_title("📍 TOP 20 PROVINCES (ALL-TIME)", COLOR["header_mid"])
        row += 1
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

        # ── 섹션 D: 번역 품질 지표 ────────────────────────────
        _section_title("🔍 TRANSLATION QUALITY CHECK", COLOR["header_green"])
        row += 1
        trans_ok   = sum(1 for a in week_articles
                         if a.get("title_en") and
                         a["title_en"] != a.get("title", ""))
        trans_fail = len(week_articles) - trans_ok
        trans_pct  = f"{trans_ok/len(week_articles)*100:.1f}%" if week_articles else "N/A"

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

        logger.info(f"  Summary: 전체 {len(all_articles)}건 / 금주 {len(week_articles)}건")

    # ────────────────────────────────────────────────────────
    # 시트 9: Province_Keywords (Province 검색어 기록 - 신규)
    # ────────────────────────────────────────────────────────

    def _update_province_keywords(self):
        """
        2026년 행정개편 반영 Province 검색어 기록
        - 검색 품질 검증: 어떤 키워드로 어떤 Province를 탐색하는지 투명하게 기록
        """
        ws = self._get_or_create_sheet("Province_Keywords")
        ws.delete_rows(1, ws.max_row + 1)

        HDR_STYLE = _hdr(COLOR["header_gold"], font_color="1C2833")
        COLS = [
            ("Province (Standard)", 28), ("Region Category",  22),
            ("Keywords",            80), ("Keyword Count",    14),
            ("Old Province Names",  35), ("Updated",          16),
        ]
        _set_header_row(ws, COLS, HDR_STYLE)

        # 구 성명 역매핑 (Province → 구 성명 리스트)
        from collections import defaultdict
        old_names_map = defaultdict(list)
        if PROVINCE_OK:
            from scripts.province_keywords import PROVINCE_ALIAS_MAP
            for old, new in PROVINCE_ALIAS_MAP.items():
                old_names_map[new].append(old)

        today_str = self.now.strftime("%Y-%m-%d")
        prov_data = get_provinces_for_excel() if PROVINCE_OK else []

        for i, prow in enumerate(prov_data, 2):
            province = prow["Province"]
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
        """시트가 없으면 생성, 있으면 반환"""
        if name in self.wb.sheetnames:
            return self.wb[name]
        if position is not None:
            ws = self.wb.create_sheet(name, position)
        else:
            ws = self.wb.create_sheet(name)
        return ws
