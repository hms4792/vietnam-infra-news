"""
excel_updater.py — v3.3 (2026-05-01)
====================================================
[영구 제약 — 절대 변경 금지]
  - 클래스명: ExcelUpdater
  - 메서드명: update_all(articles)
  - 신규 기사: insert_rows(2) — 헤더 바로 아래 삽입
  - 날짜 역순 정렬

[v3.2 핵심 변경]
  Fix1 News Database 17컬럼 (v3.3: Area/Sector 맨앞 2열 + Title_EN/Title_VI 분리)
       → 헤더: Area, Sector, No, Date, Title_EN, Title_VI, Tit_ko, Source,
                Src_Type, Province, Plan_ID, Grade, URL, sum_ko, sum_en, sum_vi, QC
       → 변경 이유: 대시보드 컬럼 분류 오류 해결 + 영어/베트남어 언어 구분 명확화
  Fix2 Matched_Plan 17컬럼 (정제후 원본 구조 복원)
       → 헤더: No, ctx_tag, ctx_grade, Plan_ID, Title_EN, Date, Source,
                Province, Sector, title_ko, title_en_orig, title_vi,
                summary_ko, summary_en, summary_vi, short_sum, Link
  Fix3 News Database 일반기사 흰색 (NEW 연노랑 제거)
       → 매칭된 기사만 등급별 색상 (HIGH=노랑, MED=연파랑, POLICY=연녹)
  Fix4 신규기사 표시는 Keywords History에서만 (요청사항)
  Fix5 제목/요약 셀 글자 11pt 굵게 (가독성)
  Fix6 Source 시트 강화 — 기관분류 + RSS접근여부 + 우회필요 추적
  Fix7 일반기사(인프라 무관) 자동 필터링 — 정제 기준 명확화
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


# 베트남어 자동 감지 (영문/베트남어 분리용)
_VI_CHARS = set('ăâđêôơưĂÂĐÊÔƠƯáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ')
def _is_vietnamese(text: str) -> bool:
    """베트남어 특수 문자가 3개 이상 포함되면 베트남어로 판정"""
    if not text: return False
    return sum(1 for c in str(text) if c in _VI_CHARS) > 2

# ─────────────────────────────────────────────────────
# 경로 설정
# ─────────────────────────────────────────────────────
_SCRIPTS_DIR = Path(os.path.dirname(os.path.abspath(__file__)))
_ROOT_DIR    = _SCRIPTS_DIR.parent
EXCEL_PATH   = Path(os.environ.get(
    "EXCEL_PATH",
    str(_ROOT_DIR / "data" / "database" / "Vietnam_Infra_News_Database_Final.xlsx")
))

# ─────────────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────────────
SECTOR_ORDER = ["Waste Water","Water Supply/Drainage","Solid Waste",
                "Power","Oil & Gas","Transport","Industrial Parks",
                "Smart City","Construction"]

PLAN_PREFIX = {
    "VN-WW":"Waste Water","VN-WAT":"Water Supply/Drainage","VN-SWM":"Solid Waste",
    "VN-PWR":"Power","VN-PDP":"Power","VN-OG":"Oil & Gas",
    "VN-TRAN":"Transport","VN-URB":"Transport","VN-METRO":"Transport",
    "VN-IP":"Industrial Parks","VN-MEKONG":"Transport","HN":"Transport",
    "VN-EV":"Transport","VN-ENV":"Environment",
}
AREA_MAP = {
    "Waste Water":"Environment","Water Supply/Drainage":"Environment","Solid Waste":"Environment",
    "Power":"Energy Develop.","Oil & Gas":"Energy Develop.",
    "Transport":"Urban Develop.","Industrial Parks":"Urban Develop.",
    "Smart City":"Urban Develop.","Construction":"Urban Develop.","Environment":"Environment",
}

# 인프라 관련 키워드 (정제 기준)
INFRA_KEYWORDS = {
    'en': ['wastewater','sewage','water supply','drainage','waste management',
           'power','electricity','energy','solar','wind','lng','hydropower',
           'oil','gas','petroleum','pipeline','refinery',
           'transport','highway','airport','railway','metro','bridge','port','seaport',
           'industrial park','industrial zone','smart city','infrastructure',
           'master plan','development plan','construction','urban','wwtp',
           'ring road','expressway','renewable','grid','transmission'],
    'vi': ['nước thải','xử lý nước','cấp nước','thoát nước','chất thải','môi trường',
           'điện','năng lượng','dầu khí','khí đốt','giao thông','đường','cầu',
           'sân bay','metro','khu công nghiệp','khu kinh tế','đô thị thông minh',
           'cơ sở hạ tầng','quy hoạch','xây dựng','cảng','đường sắt'],
    'ko': ['폐수','상수도','하수도','전력','에너지','태양광','풍력','석유','가스',
           '교통','도로','공항','철도','지하철','산업단지','스마트시티','인프라']
}

# 색상 팔레트
def _f(h): return PatternFill("solid", fgColor=h)
FILL = {
    "HIGH":   _f("FFF9C4"),
    "MEDIUM": _f("E8F0FE"),
    "POLICY": _f("E8F5E9"),
    "BOTH":   _f("FFF3E0"),
    "WHITE":  _f("FFFFFF"),
    "EVEN":   _f("F5F9FF"),
    "GRAY":   _f("F2F2F2"),
    "RED":    _f("FFEBEE"),
    "HDR_B":  _f("1F4E78"),
    "HDR_G":  _f("375623"),
    "HDR_N":  _f("17375E"),
    "KH_NEW": _f("FFF9C4"),
}

FONT_HDR        = Font(name="맑은 고딕", bold=True, color="FFFFFF", size=10)
FONT_DATA       = Font(name="맑은 고딕", size=10, color="000000")
FONT_TITLE_BOLD = Font(name="맑은 고딕", bold=True, size=11)
FONT_META       = Font(name="맑은 고딕", bold=True, size=11, color="000000")

# News Database 14컬럼 (Area/Sector 제거)
NEWS_HEADERS = ["Area","Sector","No","Date","Title_EN","Title_VI","Tit_ko",
                "Source","Src_Type","Province","Plan_ID","Grade","URL",
                "sum_ko","sum_en","sum_vi","QC"]
NEWS_WIDTHS  = [16,18,5,12,45,40,30,18,10,15,20,8,40,30,30,30,8]

# Matched_Plan 17컬럼 (정제후 원본)
MP_HEADERS = ["No","ctx_tag","ctx_grade","Plan_ID","Title_EN","Date","Source",
              "Province","Sector","title_ko","title_en_orig","title_vi",
              "summary_ko","summary_en","summary_vi","short_sum","Link"]
MP_WIDTHS  = [5,12,10,22,40,12,18,15,15,30,30,30,40,40,40,40,30]

KH_HEADERS = ["Sector","Province","Date","Title (En)","Title (Ko)","Source","Grade","Plan_ID"]
KH_WIDTHS  = [22,18,12,55,40,18,8,22]

SECT_PRI = {s:i for i,s in enumerate(SECTOR_ORDER)}


# ─────────────────────────────────────────────────────
# 유틸리티
# ─────────────────────────────────────────────────────
def _is_infra_article(title_en: str, title_ko: str, plan_id: str) -> bool:
    """Fix7: 인프라 관련 기사인지 판별 (일반기사 자동 필터링)"""
    if str(plan_id or '').strip():
        return True
    text = (str(title_en or '') + ' ' + str(title_ko or '')).lower()
    if any(kw in text for kw in INFRA_KEYWORDS['en']): return True
    if any(kw in text for kw in INFRA_KEYWORDS['vi']): return True
    if any(kw in text for kw in INFRA_KEYWORDS['ko']): return True
    return False

def _sector_from_plan(plan_id: str) -> str:
    p = str(plan_id or '').upper().strip()
    for pf, s in PLAN_PREFIX.items():
        if p.startswith(pf): return s
    return ''

def _sector_from_text(title_en: str, title_ko: str, plan_id: str) -> str:
    s = _sector_from_plan(plan_id)
    if s: return s
    txt = (str(title_en or '') + ' ' + str(title_ko or '')).lower()
    pri = [
        ("Waste Water",          ["wastewater","sewage","wwtp","nước thải"]),
        ("Water Supply/Drainage",["water supply","drainage","cấp nước"]),
        ("Solid Waste",          ["solid waste","garbage","landfill"]),
        ("Power",                ["power","electricity","solar","wind","lng","điện"]),
        ("Oil & Gas",            ["oil","gas","petroleum","pipeline"]),
        ("Industrial Parks",     ["industrial park","industrial zone","khu công nghiệp"]),
        ("Smart City",           ["smart city","đô thị thông minh"]),
        ("Transport",            ["transport","highway","airport","metro","bridge","đường","cầu"]),
    ]
    for sec, kws in pri:
        if any(k in txt for k in kws):
            return sec
    return ''

def _grade_fill(grade: str, qc: str = '') -> PatternFill:
    """Fix3: 매칭된 기사만 색상 / 일반기사는 흰색"""
    g = str(grade or '').upper().strip()
    q = str(qc    or '').upper().strip()
    p = ('POLICY' in q) or (g == 'POLICY')
    if g == 'HIGH' and p: return FILL['BOTH']
    if g == 'HIGH':       return FILL['HIGH']
    if g == 'MEDIUM':     return FILL['MEDIUM']
    if g == 'POLICY' or p:return FILL['POLICY']
    return FILL['WHITE']

def _hdr(ws, row, col, val, fill_key="HDR_B"):
    c = ws.cell(row, col)
    c.value = val; c.font = FONT_HDR; c.fill = FILL[fill_key]
    c.alignment = Alignment(horizontal="center", vertical="center")


# ─────────────────────────────────────────────────────
# ExcelUpdater 클래스
# ─────────────────────────────────────────────────────
class ExcelUpdater:
    """
    main.py Step3에서 호출:
        updater = ExcelUpdater()
        updater.update_all(articles)
    """

    def __init__(self, excel_path=EXCEL_PATH):
        self.path   = Path(excel_path)
        self.today  = date.today().strftime("%Y-%m-%d")
        self.now    = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.cutoff = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")

    def update_all(self, articles: list) -> None:
        print(f"[ExcelUpdater v3.3] update_all: 신규 {len(articles)}건")

        if not self.path.exists():
            self._create_empty_workbook()

        wb = openpyxl.load_workbook(str(self.path))

        # Step 1: 인프라 기사 필터링 (Fix7) + 보강
        articles = self._filter_and_enrich(articles)
        print(f"  인프라 관련 필터링 후: {len(articles)}건")

        # Step 2: 중복 제거
        new_arts = self._deduplicate(wb, articles)
        print(f"  중복 제거 후 신규: {len(new_arts)}건")

        # Step 3: News Database 업데이트
        if new_arts:
            self._insert_news(wb, new_arts)

        # Step 4: Matched_Plan 전체 재구성 (영구제약: 전체DB 스캔)
        self._rebuild_matched_plan(wb)

        # Step 5: Keywords History
        self._rebuild_keywords_history(wb)

        # Step 6: 통계 시트 갱신
        self._update_summary(wb, len(new_arts))
        self._update_collection_log(wb, len(new_arts))
        self._update_source(wb)
        self._update_stats(wb)
        self._update_context_stats(wb)
        self._update_timeline(wb)
        self._update_province_keywords(wb)

        wb.save(str(self.path))
        print(f"  [완료] 저장: {self.path}")

    # ── Step 1: 필터링 + 보강 ─────────────────────────
    def _filter_and_enrich(self, articles: list) -> list:
        result = []
        for a in articles:
            a = dict(a)
            title    = a.get("title") or a.get("title_en", "")
            title_ko = a.get("title_ko", "")
            plan_id  = a.get("plan_id", "") or a.get("ctx_plans", "")
            
            # Fix7: 인프라 무관 기사 필터링
            if not _is_infra_article(title, title_ko, plan_id):
                continue
            
            if not a.get("sector"):
                a["sector"] = _sector_from_text(title, title_ko, plan_id) or 'Power'
            if not a.get("area"):
                a["area"] = AREA_MAP.get(a["sector"], "Urban Develop.")
            
            # Grade 정규화
            qc = str(a.get("qc","") or "").upper()
            cg = str(a.get("grade","") or a.get("ctx_grade","")).upper()
            if cg in ('HIGH','MEDIUM','POLICY','LOW'):
                a['grade'] = cg
            elif 'SA7+POLICY' in qc:
                a['grade'] = 'HIGH'
            elif 'SA7_MATCH' in qc:
                a['grade'] = 'MEDIUM'
            elif 'POLICY_MATCH' in qc:
                a['grade'] = 'POLICY'
            else:
                a['grade'] = ''
            
            result.append(a)
        return result

    # ── Step 2: 중복 제거 ─────────────────────────────
    def _deduplicate(self, wb, articles):
        if "News Database" not in wb.sheetnames: return articles
        ws = wb["News Database"]
        eu, et = set(), set()
        for r in range(2, ws.max_row+1):
            u = ws.cell(r,13).value  # v3.3: URL은 Col13
            t = ws.cell(r,5).value   # v3.3: Title_EN은 Col5
            t2 = ws.cell(r,6).value  # v3.3: Title_VI는 Col6
            if u: eu.add(str(u).strip())
            if t: et.add(str(t)[:80].strip())
            if t2: et.add(str(t2)[:80].strip())
        return [a for a in articles
                if str(a.get("url","") or "").strip() not in eu
                and str(a.get("title") or a.get("title_en",""))[:80].strip() not in et]

    # ── Step 3: News Database 삽입 ────────────────────
    def _insert_news(self, wb, articles):
        if "News Database" not in wb.sheetnames:
            ws = wb.create_sheet("News Database", 0)
            self._write_news_header(ws)
        else:
            ws = wb["News Database"]
            # 14컬럼 헤더로 강제 정리
            cur_headers = [ws.cell(1,c).value for c in range(1, ws.max_column+1)]
            if cur_headers != NEWS_HEADERS:
                # 헤더 재작성 (기존 데이터는 유지)
                for ci, h in enumerate(NEWS_HEADERS, 1):
                    _hdr(ws, 1, ci, h)

        # 날짜 역순 삽입
        for a in sorted(articles, key=lambda x: str(x.get("date","") or ""), reverse=True):
            ws.insert_rows(2)
            self._write_news_row(ws, 2, a)

        self._renumber(ws)
        print(f"    [News DB] {len(articles)}건 삽입 → 총 {ws.max_row-1}건")

    def _write_news_header(self, ws):
        for ci, (h, w) in enumerate(zip(NEWS_HEADERS, NEWS_WIDTHS), 1):
            _hdr(ws, 1, ci, h)
            ws.column_dimensions[get_column_letter(ci)].width = w
        ws.row_dimensions[1].height = 22
        ws.freeze_panes = "A2"

    def _write_news_row(self, ws, row, a):
        """v3.3: 17컬럼 구조 (Area+Sector 맨앞 + Title_EN/Title_VI 분리)"""
        title = a.get("title") or a.get("title_en", "")
        title_ko = a.get("title_ko", "")
        grade = str(a.get("grade","") or "")
        qc    = str(a.get("qc","") or "")
        plan_id = str(a.get("plan_id","") or a.get("ctx_plans","") or "")
        d = str(a.get("date","") or "")
        sector = a.get("sector", "")
        area = a.get("area", "")
        
        # Title_EN / Title_VI 분리 (자동 감지)
        title_en = a.get("title_en", "")
        title_vi = a.get("title_vi", "")
        if not title_en and not title_vi and title:
            # 자동 감지로 분리
            if _is_vietnamese(title):
                title_vi = title
            else:
                title_en = title
        
        # Fix3: 매칭된 기사만 색상, 일반기사는 흰색
        fill = _grade_fill(grade, qc)
        
        vals = [
            area,                    # Col1: Area
            sector,                  # Col2: Sector
            "",                      # Col3: No (재번호됨)
            d,                       # Col4: Date
            title_en,                # Col5: Title_EN
            title_vi,                # Col6: Title_VI
            title_ko,                # Col7: Tit_ko
            a.get("source",""),     # Col8
            a.get("src_type","News"),# Col9
            a.get("province",""),   # Col10
            plan_id,                 # Col11
            grade,                   # Col12
            a.get("url",""),        # Col13
            a.get("sum_ko","") or a.get("summary_ko",""),  # Col14
            a.get("sum_en","") or a.get("summary_en",""),  # Col15
            a.get("sum_vi","") or a.get("summary_vi",""),  # Col16
            qc,                      # Col17
        ]
        for ci, v in enumerate(vals, 1):
            c = ws.cell(row, ci); c.value = v; c.fill = fill
            # Fix5: 제목/요약 굵게 (Col5,6,7,14,15,16)
            c.font = FONT_TITLE_BOLD if ci in (5,6,7,14,15,16) else FONT_DATA
            c.alignment = Alignment(vertical="top", wrap_text=False)

    def _renumber(self, ws):
        # v3.3: No 컬럼은 Col3로 이동
        for r in range(2, ws.max_row+1):
            try: ws.cell(r,3).value = r-1
            except: pass

    # ── Step 4: Matched_Plan 17컬럼 재구성 (Fix2) ──────
    def _rebuild_matched_plan(self, wb):
        ws_news = wb["News Database"]
        mp_arts = []
        for r in range(2, ws_news.max_row+1):
            plan_id = str(ws_news.cell(r,11).value or '').strip()  # v3.3: Plan_ID Col11
            if not plan_id: continue
            grade = str(ws_news.cell(r,12).value or '').upper()    # v3.3: Grade Col12
            qc    = str(ws_news.cell(r,17).value or '')             # v3.3: QC Col17
            title = ws_news.cell(r,5).value or ws_news.cell(r,6).value  # Title_EN or Title_VI
            sec   = ws_news.cell(r,2).value or _sector_from_plan(plan_id) or _sector_from_text(title, ws_news.cell(r,7).value, plan_id)
            
            # ctx_grade 결정
            ctx_grade = grade
            if not ctx_grade:
                if 'SA7+POLICY' in qc.upper(): ctx_grade = 'HIGH'
                elif 'SA7' in qc.upper():       ctx_grade = 'MEDIUM'
                elif 'POLICY' in qc.upper():    ctx_grade = 'POLICY'
                else: ctx_grade = 'MEDIUM'
            
            mp_arts.append({
                'ctx_tag':    'SA7_MATCH' if 'SA7' in qc.upper() else ('POLICY_MATCH' if 'POLICY' in qc.upper() else 'SA7_MATCH'),
                'ctx_grade':  ctx_grade,
                'plan_id':    plan_id,
                'title_en':   ws_news.cell(r,5).value or ws_news.cell(r,6).value,  # v3.3: EN 우선, 없으면 VI
                'title_vi':   ws_news.cell(r,6).value,                              # v3.3: Col6
                'date':       str(ws_news.cell(r,4).value or '')[:10],              # v3.3: Date Col4
                'source':     ws_news.cell(r,8).value,                              # v3.3: Col8
                'province':   ws_news.cell(r,10).value,                             # v3.3: Col10
                'sector':     sec,
                'title_ko':   ws_news.cell(r,7).value,                              # v3.3: Col7
                'summary_ko': ws_news.cell(r,14).value,                             # v3.3: Col14
                'summary_en': ws_news.cell(r,15).value,                             # v3.3: Col15
                'summary_vi': ws_news.cell(r,16).value,                             # v3.3: Col16
                'link':       ws_news.cell(r,13).value,                             # v3.3: URL Col13
            })
        
        mp_arts.sort(key=lambda x: str(x.get('date','') or ''), reverse=True)
        for i, a in enumerate(mp_arts, 1):
            a['no'] = i
        
        high_c = sum(1 for a in mp_arts if a.get('ctx_grade')=='HIGH')
        med_c  = sum(1 for a in mp_arts if a.get('ctx_grade')=='MEDIUM')
        pol_c  = sum(1 for a in mp_arts if a.get('ctx_grade')=='POLICY')
        
        if "Matched_Plan" in wb.sheetnames: del wb["Matched_Plan"]
        nidx = wb.sheetnames.index("News Database")
        ws_mp = wb.create_sheet("Matched_Plan", nidx+1)
        
        # Row1: 메타
        meta = (f"★ SA-7 맥락 확정 기사 {len(mp_arts)}건 | "
                f"HIGH(노란)={high_c} MEDIUM(연파랑)={med_c} POLICY(연녹)={pol_c}")
        ws_mp.cell(1,1).value = meta
        ws_mp.cell(1,1).font  = FONT_META
        ws_mp.cell(1,1).fill  = FILL['HIGH']
        ws_mp.merge_cells(start_row=1, start_column=1, end_row=1, end_column=17)
        
        # Row2: 헤더
        for ci, (h, w) in enumerate(zip(MP_HEADERS, MP_WIDTHS), 1):
            _hdr(ws_mp, 2, ci, h)
            ws_mp.column_dimensions[get_column_letter(ci)].width = w
        ws_mp.row_dimensions[2].height = 20
        ws_mp.freeze_panes = "A3"
        
        for ri, a in enumerate(mp_arts, 3):
            grade = a.get('ctx_grade','')
            fill  = _grade_fill(grade)
            vals = [a.get('no'), a.get('ctx_tag',''), grade, a.get('plan_id',''),
                    a.get('title_en',''), a.get('date',''), a.get('source',''),
                    a.get('province',''), a.get('sector',''), a.get('title_ko',''),
                    a.get('title_en',''),  # title_en_orig
                    a.get('title_vi',''),  # title_vi (v3.3 분리)
                    a.get('summary_ko',''), a.get('summary_en',''), a.get('summary_vi',''),
                    a.get('short_sum',''), a.get('link','')]
            for ci, v in enumerate(vals, 1):
                c = ws_mp.cell(ri, ci); c.value = v; c.fill = fill
                # Fix5: 제목(5,10) / 요약(13,14) 굵게
                c.font = FONT_TITLE_BOLD if ci in (5,10,13,14) else FONT_DATA
                c.alignment = Alignment(vertical="top", wrap_text=False)
        
        print(f"    [Matched_Plan] {len(mp_arts)}건 (HIGH={high_c} MED={med_c} POL={pol_c})")

    # ── Step 5: Keywords History ──────────────────────
    def _rebuild_keywords_history(self, wb):
        ws_news = wb["News Database"]
        kh = []
        for r in range(2, ws_news.max_row+1):
            pid = str(ws_news.cell(r,11).value or '').strip()  # v3.3: Col11
            title_en = ws_news.cell(r,5).value
            title_vi = ws_news.cell(r,6).value
            title = title_en or title_vi  # 영문 우선
            sec = ws_news.cell(r,2).value or _sector_from_plan(pid) or _sector_from_text(title, ws_news.cell(r,7).value, pid)
            if not sec: continue
            kh.append({
                'sector':   sec,
                'province': str(ws_news.cell(r,10).value or ''),     # v3.3: Col10
                'date':     str(ws_news.cell(r,4).value or '')[:10], # v3.3: Col4
                'title_en': title,
                'title_ko': ws_news.cell(r,7).value,                  # v3.3: Col7
                'source':   ws_news.cell(r,8).value,                  # v3.3: Col8
                'grade':    str(ws_news.cell(r,12).value or ''),     # v3.3: Col12
                'plan_id':  pid,
            })
        
        pre = sorted(kh, key=lambda x: (SECT_PRI.get(x['sector'], 99), str(x.get('province','') or '')))
        result = []
        for (s, p), grp in groupby(pre, key=lambda x: (x['sector'], x['province'])):
            result.extend(sorted(grp, key=lambda x: str(x.get('date','')), reverse=True))
        
        if "Keywords History" in wb.sheetnames: del wb["Keywords History"]
        mp_idx = wb.sheetnames.index("Matched_Plan")
        ws_kh  = wb.create_sheet("Keywords History", mp_idx+1)
        
        for ci, (h, w) in enumerate(zip(KH_HEADERS, KH_WIDTHS), 1):
            _hdr(ws_kh, 1, ci, h, "HDR_G")
            ws_kh.column_dimensions[get_column_letter(ci)].width = w
        ws_kh.row_dimensions[1].height = 22
        ws_kh.freeze_panes = "A2"
        
        for ri, a in enumerate(result, 2):
            d = str(a.get('date',''))
            # Fix4: Keywords History만 신규=노란표시
            is_new = d >= self.cutoff
            fill = FILL['KH_NEW'] if is_new else FILL['WHITE']
            vals = [a.get('sector',''), a.get('province',''), d,
                    str(a.get('title_en','') or '')[:100],
                    str(a.get('title_ko','') or '')[:80],
                    a.get('source',''), a.get('grade',''), a.get('plan_id','')]
            for ci, v in enumerate(vals, 1):
                c = ws_kh.cell(ri, ci); c.value = v; c.fill = fill
                c.font = FONT_TITLE_BOLD if ci in (4,5) else FONT_DATA
                c.alignment = Alignment(vertical="top")
        
        new_c = sum(1 for a in result if str(a.get('date','')) >= self.cutoff)
        print(f"    [Keywords History] {len(result)}건 (신규 {new_c}건 노란표시)")

    # ── Step 6a: Summary ──────────────────────────────
    def _update_summary(self, wb, new_count):
        if "Summary" not in wb.sheetnames: return
        ws_news = wb["News Database"]
        ws_mp   = wb["Matched_Plan"]
        total   = ws_news.max_row - 1
        matched = ws_mp.max_row - 2
        high_c  = sum(1 for r in range(3, ws_mp.max_row+1)
                      if str(ws_mp.cell(r,3).value or '').upper() == 'HIGH')
        ws_sum = wb["Summary"]
        for r in range(1, min(5, ws_sum.max_row+1)):
            v = str(ws_sum.cell(r,1).value or '')
            if 'Updated' in v or 'Total' in v:
                ws_sum.cell(r,1).value = (f"Updated: {self.now} | Total News: {total}건 | "
                                          f"SA-7: {matched}건 | HIGH: {high_c}건")
                break
        print(f"    [Summary] Total={total} SA-7={matched} HIGH={high_c}")

    # ── Step 6b: Collection_Log ───────────────────────
    def _update_collection_log(self, wb, new_count):
        if "Collection_Log" not in wb.sheetnames: return
        ws = wb["Collection_Log"]
        total = wb["News Database"].max_row - 1
        ws.insert_rows(2)
        ws.cell(2,1).value = f"{self.now} KST"
        ws.cell(2,2).value = new_count
        ws.cell(2,3).value = "Daily Automated"
        ws.cell(2,4).value = "✅"
        ws.cell(2,5).value = f"신규 {new_count}건 추가 | 전체 {total}건"
        for c in range(1, 6): ws.cell(2,c).font = FONT_DATA

    # ── Step 6c: Source 시트 (Fix6) ───────────────────
    def _update_source(self, wb):
        if "Source" not in wb.sheetnames: return
        ws_news = wb["News Database"]
        src_cnt = defaultdict(int)
        src_last= defaultdict(str)
        total   = ws_news.max_row - 1
        for r in range(2, ws_news.max_row+1):
            s = str(ws_news.cell(r,8).value or '').strip()  # v3.3: Source Col8
            d = str(ws_news.cell(r,4).value or '')[:10]      # v3.3: Date Col4
            if s:
                src_cnt[s] += 1
                if d > src_last[s]: src_last[s] = d
        
        # Source 시트는 v3.2에서 기관분류 강화 구조 유지
        # 카운트 컬럼만 업데이트 (구조는 변경 안 함)
        ws_src = wb["Source"]
        # 컬럼 매핑 (헤더로 자동 인식)
        headers = {str(ws_src.cell(1,c).value or '').strip().lower(): c 
                   for c in range(1, ws_src.max_column+1)}
        col_name = headers.get('source name', 2)
        col_cnt  = headers.get('건수', 4)
        col_last = headers.get('최근수집일', 6)
        col_stat = headers.get('상태', 7)
        
        for r in range(2, ws_src.max_row+1):
            sn = str(ws_src.cell(r, col_name).value or '').strip()
            if sn in src_cnt:
                ws_src.cell(r, col_cnt).value = src_cnt[sn]
                ws_src.cell(r, col_last).value = src_last[sn]
                ws_src.cell(r, col_stat).value = '✅ 활성' if src_last[sn] >= self.cutoff else '⚠️ 비활성'
        print(f"    [Source] {len(src_cnt)}개 출처 카운트 갱신")

    # ── Step 6d: Stats ────────────────────────────────
    def _update_stats(self, wb):
        if "Stats" not in wb.sheetnames: return
        ws_mp = wb["Matched_Plan"]
        plan_count = defaultdict(int); plan_year = defaultdict(lambda: defaultdict(int))
        plan_latest = defaultdict(str)
        for r in range(3, ws_mp.max_row+1):
            pid = str(ws_mp.cell(r,4).value or '').strip()
            d   = str(ws_mp.cell(r,6).value or '')[:10]
            yr  = d[:4] if len(d)>=4 else ''
            if pid:
                plan_count[pid] += 1
                if yr: plan_year[pid][yr] += 1
                if d > plan_latest[pid]: plan_latest[pid] = d
        
        total_mp = ws_mp.max_row - 2
        ws_st = wb["Stats"]
        ws_st.cell(1,1).value = f"VIETNAM INFRASTRUCTURE NEWS — 플랜별 SA-7 매칭 현황 ({self.now})"
        ws_st.cell(2,1).value = f"전체 SA-7: {total_mp}건"
        # 데이터 행 갱신
        hr = None
        for r in range(1, min(8, ws_st.max_row+1)):
            if ws_st.cell(r,1).value and '플랜' in str(ws_st.cell(r,1).value or ''):
                hr = r; break
        if hr:
            for r in range(hr+1, ws_st.max_row+1):
                pid = str(ws_st.cell(r,1).value or '').strip()
                if not pid or pid.startswith('─'): continue
                tc = plan_count.get(pid, 0)
                if ws_st.max_column >= 7:
                    ws_st.cell(r,3).value = tc
                    ws_st.cell(r,4).value = tc - plan_year[pid].get('2026', 0)
                    ws_st.cell(r,5).value = plan_year[pid].get('2026', 0)
                    ws_st.cell(r,6).value = round(tc/total_mp*100, 2) if total_mp and tc else 0
                    ws_st.cell(r,7).value = plan_latest.get(pid, '')

    # ── Step 6e: Context_Stats ────────────────────────
    def _update_context_stats(self, wb):
        if "Context_Stats" not in wb.sheetnames: return
        total_mp = wb["Matched_Plan"].max_row - 2
        total = wb["News Database"].max_row - 1
        ws_cs = wb["Context_Stats"]
        ws_cs.cell(1,1).value = 'SA-7 + Policy Sentinel Total'
        ws_cs.cell(1,2).value = total_mp
        ws_cs.cell(1,3).value = f'{round(total_mp/total*100,1)}%' if total else '0%'

    # ── Step 6f: Timeline (정제후 형식 유지) ──────────
    def _update_timeline(self, wb):
        if "Timeline" not in wb.sheetnames: return
        ws_mp = wb["Matched_Plan"]
        plan_grade = defaultdict(lambda: defaultdict(int))
        plan_year  = defaultdict(lambda: defaultdict(int))
        plan_latest= defaultdict(str)
        plan_total = defaultdict(int)
        for r in range(3, ws_mp.max_row+1):
            pid = str(ws_mp.cell(r,4).value or '').strip()
            g   = str(ws_mp.cell(r,3).value or '').upper()
            d   = str(ws_mp.cell(r,6).value or '')[:10]
            yr  = d[:4] if len(d)>=4 else ''
            if pid:
                plan_grade[pid][g] += 1
                plan_total[pid] += 1
                if yr: plan_year[pid][yr] += 1
                if d > plan_latest[pid]: plan_latest[pid] = d
        
        ws_tl = wb["Timeline"]
        # Row3부터 데이터
        for r in range(3, ws_tl.max_row+1):
            pid = str(ws_tl.cell(r,2).value or '').strip()
            if not pid: continue
            g = plan_grade.get(pid, {})
            ws_tl.cell(r,4).value = g.get('HIGH',0) or None
            ws_tl.cell(r,5).value = g.get('MEDIUM',0) or None
            ws_tl.cell(r,6).value = g.get('POLICY',0) or None
            ws_tl.cell(r,7).value = plan_total.get(pid,0) or None
            ws_tl.cell(r,8).value = plan_latest.get(pid,'')
            for off, yr in enumerate(['2019','2020','2021','2022','2023','2024','2025','2026']):
                ws_tl.cell(r, 9+off).value = plan_year[pid].get(yr,0) or None

    # ── Step 6g: Province_Keywords ────────────────────
    def _update_province_keywords(self, wb):
        if "Province_Keywords" not in wb.sheetnames: return
        ws_news = wb["News Database"]
        ws_mp   = wb["Matched_Plan"]
        prov_total = defaultdict(int); prov_unmap = defaultdict(int)
        prov_sec   = defaultdict(list); prov_src = defaultdict(list)
        for r in range(2, ws_news.max_row+1):
            pv = str(ws_news.cell(r,10).value or '').strip()  # v3.3: Col10
            if not pv: continue
            prov_total[pv] += 1
            pid = str(ws_news.cell(r,11).value or '').strip()  # v3.3: Col11
            src = str(ws_news.cell(r,8).value or '').strip()   # v3.3: Col8
            if pid: prov_sec[pv].append(_sector_from_plan(pid) or '')
            else: prov_unmap[pv] += 1
            if src: prov_src[pv].append(src)
        prov_sa7 = defaultdict(int)
        for r in range(3, ws_mp.max_row+1):
            pv = str(ws_mp.cell(r,8).value or '').strip()
            if pv: prov_sa7[pv] += 1
        
        ws_pk = wb["Province_Keywords"]
        for r in range(2, ws_pk.max_row+1):
            pv = str(ws_pk.cell(r,1).value or '').strip()
            if not pv: continue
            tot = prov_total.get(pv,0); sa7 = prov_sa7.get(pv,0)
            unm = prov_unmap.get(pv,0)
            rate = round(unm/tot*100,1) if tot else 0
            secs = [s for s in prov_sec.get(pv,[]) if s]
            ms = max(set(secs), key=secs.count) if secs else ''
            srcs = prov_src.get(pv,[])
            mss = max(set(srcs), key=srcs.count) if srcs else ''
            if tot==0:        q = '⚪ 데이터없음'
            elif rate < 20:   q = '🟢 양호'
            elif rate < 40:   q = '🟡 보통'
            elif rate < 60:   q = '🟠 주의'
            else:             q = '🔴 요개선'
            ws_pk.cell(r,2).value = tot
            ws_pk.cell(r,3).value = sa7
            ws_pk.cell(r,4).value = ms
            ws_pk.cell(r,5).value = mss[:30] if mss else ''
            ws_pk.cell(r,6).value = f'{rate}%'
            ws_pk.cell(r,7).value = q

    # ── 보조 ──────────────────────────────────────────
    def _create_empty_workbook(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "News Database"
        self._write_news_header(ws)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(self.path))


if __name__ == "__main__":
    print("ExcelUpdater v3.3 단독 실행")
    updater = ExcelUpdater()
    updater.update_all([])
