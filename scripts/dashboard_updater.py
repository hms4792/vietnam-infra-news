"""
dashboard_updater.py
====================
기존 templates/dashboard_template.html을 사용하여 docs/index.html 생성

핵심 변경:
  - 기존 템플릿의 /*__BACKEND_DATA__*/[] 플레이스홀더에 데이터 주입
  - 기존 대시보드 기능(AI브리핑, 차트, 검색, 2649건) 완전 유지
  - 기사 데이터를 {title:{ko,en,vi}, summary:{ko,en,vi}} 형식으로 변환
  - 기존 setLang('ko'/'en'/'vi') JavaScript가 그대로 작동

데이터 구조 (템플릿 JS가 기대하는 형식):
  {
    id: 1,
    title: { ko: "...", en: "...", vi: "..." },
    summary: { ko: "...", en: "...", vi: "..." },
    sector: "Transport",
    area: "Urban Develop.",
    province: "Hanoi",
    source: "VnExpress",
    date: "2026-03-28",
    url: "https://..."
  }
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# ── 경로 설정 ──────────────────────────────────────────────
TEMPLATE_PATH = Path("templates/dashboard_template.html")
OUTPUT_PATH   = Path("docs/index.html")
EXCEL_PATH    = Path("data/database/Vietnam_Infra_News_Database_Final.xlsx")

# ── 섹터 → Area 매핑 (템플릿 SECTOR_CONFIG와 일치) ──────────
SECTOR_TO_AREA = {
    "Waste Water":           "Environment",
    "Solid Waste":           "Environment",
    "Water Supply/Drainage": "Environment",
    "Power":                 "Energy Develop.",
    "Oil & Gas":             "Energy Develop.",
    "Smart City":            "Urban Develop.",
    "Industrial Parks":      "Urban Develop.",
    "Transport":             "Urban Develop.",
    "Construction":          "Urban Develop.",
}


def _normalize_area(sector: str, area: str) -> str:
    """
    기존 데이터의 area 값을 템플릿 SECTOR_CONFIG 키와 일치시킴
    기존: 'Environment', 'Energy', 'Urban Development'
    템플릿: 'Environment', 'Energy Develop.', 'Urban Develop.'
    """
    area_lower = str(area).lower()
    if 'environment' in area_lower:
        return 'Environment'
    if 'energy' in area_lower:
        return 'Energy Develop.'
    if 'urban' in area_lower:
        return 'Urban Develop.'
    # sector로 역추적
    return SECTOR_TO_AREA.get(sector, 'Urban Develop.')


def _build_backend_data(articles: list) -> str:
    """
    기사 리스트를 템플릿 JS가 기대하는 BACKEND_DATA JSON 문자열로 변환

    템플릿 JS 사용 패턴:
      const title = typeof n.title === 'object' ? (n.title[lang] || n.title.en) : n.title;
      const summary = typeof n.summary === 'object' ? (n.summary[lang] || n.summary.en) : n.summary;
    """
    data = []
    for i, art in enumerate(articles):
        # 제목: title_ko/en/vi 또는 title (문자열)
        raw_title = art.get('title', '')
        if isinstance(raw_title, dict):
            title_ko = raw_title.get('ko', '') or raw_title.get('en', '') or ''
            title_en = raw_title.get('en', '') or raw_title.get('ko', '') or ''
            title_vi = raw_title.get('vi', '') or raw_title.get('en', '') or ''
        else:
            title_ko = art.get('title_ko') or art.get('title_en') or str(raw_title)
            title_en = art.get('title_en') or str(raw_title)
            title_vi = art.get('title_vi') or art.get('title_en') or str(raw_title)

        # 요약: summary_ko/en/vi 또는 summary (문자열)
        raw_summary = art.get('summary', '')
        if isinstance(raw_summary, dict):
            summary_ko = raw_summary.get('ko', '') or raw_summary.get('en', '') or ''
            summary_en = raw_summary.get('en', '') or ''
            summary_vi = raw_summary.get('vi', '') or raw_summary.get('en', '') or ''
        else:
            summary_ko = art.get('summary_ko') or art.get('summary_en') or str(raw_summary)
            summary_en = art.get('summary_en') or str(raw_summary)
            summary_vi = art.get('summary_vi') or art.get('summary_en') or str(raw_summary)

        sector   = art.get('sector', 'General')
        area_raw = art.get('area', '')
        area     = _normalize_area(sector, area_raw)
        province = art.get('province', 'Vietnam')
        source   = art.get('source', '')
        date_val = str(art.get('published_date', art.get('date', '')))[:10]
        url      = art.get('url', '#')

        entry = {
            "id":      i + 1,
            "title":   {"ko": title_ko, "en": title_en, "vi": title_vi},
            "summary": {"ko": summary_ko, "en": summary_en, "vi": summary_vi},
            "sector":  sector,
            "area":    area,
            "province": province,
            "source":  source,
            "date":    date_val,
            "url":     url,
        }
        data.append(entry)

    return json.dumps(data, ensure_ascii=False, indent=2)


def _load_all_articles_from_excel() -> list:
    """
    Excel DB에서 전체 기사 로드 (누적 2,649건+)
    새로 수집된 기사와 합쳐서 전체 데이터를 반환
    """
    articles = []
    if not EXCEL_PATH.exists():
        logger.warning(f"Excel not found: {EXCEL_PATH}")
        return articles

    try:
        import openpyxl
        wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True)
        ws = wb.active

        # 헤더 행 파악
        headers = [str(c.value or '').strip().lower()
                   for c in next(ws.iter_rows(min_row=1, max_row=1, values_only=False))]

        # 컬럼 인덱스 매핑
        def col(name_candidates):
            for name in name_candidates:
                if name in headers:
                    return headers.index(name)
            return None

        idx_area     = col(['area'])
        idx_sector   = col(['sector', 'business sector'])
        idx_province = col(['province', 'region'])
        idx_title    = col(['title', 'news tittle', 'news title'])
        idx_title_ko = col(['title_ko', 'title ko'])
        idx_title_en = col(['title_en', 'title en'])
        idx_title_vi = col(['title_vi', 'title vi'])
        idx_date     = col(['date', 'published_date', 'published date'])
        idx_source   = col(['source'])
        idx_url      = col(['url', 'link'])
        idx_sum_ko   = col(['summary_ko', 'summary ko', 'korean summary'])
        idx_sum_en   = col(['summary_en', 'summary en', 'english summary'])
        idx_sum_vi   = col(['summary_vi', 'summary vi'])

        for row in ws.iter_rows(min_row=2, values_only=True):
            if not any(row):
                continue

            def get(idx):
                if idx is None or idx >= len(row):
                    return ''
                return str(row[idx] or '').strip()

            title_raw = get(idx_title)
            title_ko  = get(idx_title_ko) or title_raw
            title_en  = get(idx_title_en) or title_raw
            title_vi  = get(idx_title_vi) or title_raw

            articles.append({
                'area':     get(idx_area),
                'sector':   get(idx_sector),
                'province': get(idx_province),
                'title_ko': title_ko,
                'title_en': title_en,
                'title_vi': title_vi,
                'title':    title_raw,
                'date':     get(idx_date)[:10],
                'source':   get(idx_source),
                'url':      get(idx_url),
                'summary_ko': get(idx_sum_ko),
                'summary_en': get(idx_sum_en),
                'summary_vi': get(idx_sum_vi),
                'summary':    get(idx_sum_en) or get(idx_sum_ko),
            })

        wb.close()

        # 날짜 내림차순 정렬 (최신 기사가 앞으로)
        articles.sort(key=lambda x: x.get('date', '') or '', reverse=True)
        logger.info(f"[Dashboard] Excel에서 {len(articles)}건 로드")

    except Exception as e:
        logger.error(f"[Dashboard] Excel 로드 실패: {e}")
        import traceback; traceback.print_exc()

    return articles


class DashboardUpdater:
    """
    기존 dashboard_template.html 템플릿을 사용하여 docs/index.html 생성
    - /*__BACKEND_DATA__*/[] 플레이스홀더에 전체 데이터 주입
    - 기존 기능(AI브리핑, 차트, 검색, 3개국어) 완전 유지
    """

    def generate(self, new_articles: list) -> bool:
        """
        대시보드 HTML 생성

        Args:
            new_articles: 금번 수집된 새 기사 (번역 완료)
        Returns:
            True if success
        """
        # ── 1. 템플릿 로드 ────────────────────────────────────
        if not TEMPLATE_PATH.exists():
            logger.error(f"[Dashboard] 템플릿 없음: {TEMPLATE_PATH}")
            return False

        with open(TEMPLATE_PATH, 'r', encoding='utf-8') as f:
            template = f.read()

        if '/*__BACKEND_DATA__*/' not in template:
            logger.error("[Dashboard] 플레이스홀더 /*__BACKEND_DATA__*/ 없음")
            return False

        # ── 2. 전체 기사 로드 (Excel DB) ──────────────────────
        all_articles = _load_all_articles_from_excel()

        # Excel이 비어있으면 새 기사만 사용
        if not all_articles:
            logger.warning("[Dashboard] Excel 비어있음 - 새 기사만 사용")
            all_articles = new_articles

        logger.info(f"[Dashboard] 전체 기사: {len(all_articles)}건으로 대시보드 생성")

        # ── 3. BACKEND_DATA JSON 생성 ─────────────────────────
        backend_json = _build_backend_data(all_articles)

        # ── 4. 플레이스홀더 교체 ──────────────────────────────
        html_out = template.replace(
            '/*__BACKEND_DATA__*/[]',
            backend_json
        )

        # ── 5. 날짜 업데이트 ──────────────────────────────────
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
        html_out = html_out.replace(
            'id="header-date"></p>',
            f'id="header-date">{datetime.now().strftime("%Y년 %#m월 %#d일" if os.name=="nt" else "%Y년 %-m월 %-d일")}</p>'
        )

        # ── 6. 저장 ───────────────────────────────────────────
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
            f.write(html_out)

        logger.info(f"[DashboardUpdater] 저장 완료: {OUTPUT_PATH} ({len(all_articles)}건)")
        return True
