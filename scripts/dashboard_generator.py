"""
dashboard_generator.py v5.0
────────────────────────────
전문 디자인 리뉴얼:
- 상단 고정 헤더 + 보고서 버튼 바 (플랜 선택 → Word/PPT/Excel)
- 메인 영역: 최신뉴스 중심 기사 피드 (날짜/제목/출처/원문링크)
- 우측 사이드바: 24개 플랜 탭 (기사 수 배지)
- 반응형 레이아웃
"""
import os, sys, json
from datetime import datetime
from pathlib import Path
from collections import defaultdict
from urllib.parse import urlparse

# ── 플랜 메타 ──────────────────────────────────────────────────────────────
PLAN_META = {
    "VN-PWR-PDP8":          {"name": "PDP8 전력 (상위)",     "icon": "⚡", "color": "#F59E0B", "group": "⚡ PDP8 에너지"},
    "VN-PWR-PDP8-RENEWABLE":{"name": "PDP8 재생에너지",     "icon": "☀️", "color": "#F59E0B", "group": "⚡ PDP8 에너지"},
    "VN-PWR-PDP8-LNG":     {"name": "PDP8 LNG",            "icon": "🔥", "color": "#D97706", "group": "⚡ PDP8 에너지"},
    "VN-PWR-PDP8-NUCLEAR":  {"name": "PDP8 원자력·수소",     "icon": "⚛️", "color": "#B45309", "group": "⚡ PDP8 에너지"},
    "VN-PWR-PDP8-COAL":    {"name": "PDP8 석탄전환",        "icon": "🏭", "color": "#92400E", "group": "⚡ PDP8 에너지"},
    "VN-PWR-PDP8-GRID":    {"name": "PDP8 전력망",          "icon": "⚡", "color": "#78350F", "group": "⚡ PDP8 에너지"},
    "VN-WAT-RESOURCES":     {"name": "수자원 관리",           "icon": "🌊", "color": "#0EA5E9", "group": "💧 수자원"},
    "VN-WAT-URBAN":         {"name": "도시 상수도",           "icon": "🚰", "color": "#0284C7", "group": "💧 수자원"},
    "VN-WAT-RURAL":         {"name": "농촌 급수",             "icon": "🏡", "color": "#0369A1", "group": "💧 수자원"},
    "HN-URBAN-INFRA":       {"name": "하노이 인프라",         "icon": "🏗️", "color": "#DC2626", "group": "🏙️ 하노이"},
    "HN-URBAN-NORTH":       {"name": "하노이 북부 신도시",    "icon": "🌆", "color": "#B91C1C", "group": "🏙️ 하노이"},
    "HN-URBAN-WEST":        {"name": "하노이 서부 첨단",      "icon": "🔬", "color": "#991B1B", "group": "🏙️ 하노이"},
    "VN-TRAN-2055":         {"name": "교통 마스터플랜 2055",  "icon": "🛣️", "color": "#EA580C", "group": "🛣️ 교통·도시"},
    "VN-URB-METRO-2030":    {"name": "도시 메트로 2030",      "icon": "🚇", "color": "#C2410C", "group": "🛣️ 교통·도시"},
    "VN-MEKONG-DELTA-2030": {"name": "메콩 델타 2030",        "icon": "🌾", "color": "#0D9488", "group": "🌏 지역개발"},
    "VN-RED-RIVER-2030":    {"name": "홍강 델타 2030",        "icon": "🏔️", "color": "#BE123C", "group": "🌏 지역개발"},
    "VN-IP-NORTH-2030":     {"name": "북부 산업단지 2030",    "icon": "🏭", "color": "#7C3AED", "group": "🌏 지역개발"},
    "VN-ENV-IND-1894":      {"name": "환경산업 D1894",        "icon": "🌿", "color": "#15803D", "group": "🌿 환경·탄소"},
    "VN-WW-2030":           {"name": "폐수처리 2030",          "icon": "💧", "color": "#0891B2", "group": "🌿 환경·탄소"},
    "VN-SWM-NATIONAL-2030": {"name": "고형폐기물 2030",        "icon": "♻️", "color": "#16A34A", "group": "🌿 환경·탄소"},
    "VN-SC-2030":           {"name": "스마트 시티 2030",       "icon": "🏙️", "color": "#6D28D9", "group": "🌿 환경·탄소"},
    "VN-OG-2030":           {"name": "석유가스 2030",          "icon": "⛽", "color": "#D97706", "group": "🌿 환경·탄소"},
    "VN-EV-2030":           {"name": "전기차 2030",            "icon": "🚗", "color": "#0D9488", "group": "🌿 환경·탄소"},
    "VN-CARBON-2050":       {"name": "탄소중립 2050",          "icon": "🌍", "color": "#166534", "group": "🌿 환경·탄소"},
    # legacy
    "VN-PWR-PDP8":   {"name": "PDP8 전력",      "icon": "⚡", "color": "#F59E0B", "group": "⚡ PDP8 에너지"},
    "VN-GAS-PDP8":   {"name": "PDP8 가스",      "icon": "🔥", "color": "#D97706", "group": "⚡ PDP8 에너지"},
    "VN-WAT-2050":   {"name": "수자원 2050",     "icon": "💧", "color": "#0EA5E9", "group": "💧 수자원"},
    "VN-WS-NORTH-2030":{"name":"북부 상수도",   "icon": "🚰", "color": "#0284C7", "group": "💧 수자원"},
    "VN-SW-MEKONG-2030":{"name":"메콩 폐수",    "icon": "🌊", "color": "#0D9488", "group": "🌏 지역개발"},
    "VN-GRID-SMART": {"name": "스마트 그리드",   "icon": "⚡", "color": "#78350F", "group": "⚡ PDP8 에너지"},
    "VN-COAL-RETIRE":{"name": "석탄 폐지",       "icon": "🏭", "color": "#92400E", "group": "⚡ PDP8 에너지"},
    "VN-REN-NPP-2050":{"name":"원자력 2050",    "icon": "⚛️", "color": "#B45309", "group": "⚡ PDP8 에너지"},
    "VN-LNG-HUB":    {"name": "LNG 허브",        "icon": "🛢️", "color": "#D97706", "group": "⚡ PDP8 에너지"},
}

PLAN_ORDER = [
    "VN-PWR-PDP8","VN-PWR-PDP8-RENEWABLE","VN-PWR-PDP8-LNG","VN-PWR-PDP8-NUCLEAR","VN-PWR-PDP8-COAL","VN-PWR-PDP8-GRID",
    "VN-WAT-RESOURCES","VN-WAT-URBAN","VN-WAT-RURAL",
    "HN-URBAN-INFRA","HN-URBAN-NORTH","HN-URBAN-WEST",
    "VN-TRAN-2055","VN-URB-METRO-2030",
    "VN-MEKONG-DELTA-2030","VN-RED-RIVER-2030","VN-IP-NORTH-2030",
    "VN-ENV-IND-1894","VN-WW-2030","VN-SWM-NATIONAL-2030",
    "VN-SC-2030","VN-OG-2030","VN-EV-2030","VN-CARBON-2050",
]

PLAN_TO_REPORT_KEY = {
    # New Claude-aligned IDs
    "VN-PWR-PDP8":"PDP8-INTEGRATED",
    "VN-PWR-PDP8-RENEWABLE":"PDP8-INTEGRATED","VN-PWR-PDP8-LNG":"PDP8-INTEGRATED",
    "VN-PWR-PDP8-NUCLEAR":"PDP8-INTEGRATED","VN-PWR-PDP8-COAL":"PDP8-INTEGRATED",
    "VN-PWR-PDP8-GRID":"PDP8-INTEGRATED",
    "VN-WAT-RESOURCES":"WATER-INTEGRATED","VN-WAT-URBAN":"WATER-INTEGRATED",
    "VN-WAT-RURAL":"WATER-INTEGRATED",
    "HN-URBAN-INFRA":"HANOI-INTEGRATED","HN-URBAN-NORTH":"HANOI-INTEGRATED",
    "HN-URBAN-WEST":"HANOI-INTEGRATED",
    # Legacy IDs (backwards compat)
    "VN-PDP8-RENEWABLE":"PDP8-INTEGRATED","VN-PDP8-LNG":"PDP8-INTEGRATED",
    "VN-PDP8-NUCLEAR":"PDP8-INTEGRATED","VN-PDP8-COAL":"PDP8-INTEGRATED",
    "VN-PDP8-GRID":"PDP8-INTEGRATED","VN-PDP8-HYDROGEN":"PDP8-INTEGRATED",
    "VN-GAS-PDP8":"PDP8-INTEGRATED","VN-GRID-SMART":"PDP8-INTEGRATED",
    "VN-COAL-RETIRE":"PDP8-INTEGRATED","VN-REN-NPP-2050":"PDP8-INTEGRATED",
    "VN-LNG-HUB":"PDP8-INTEGRATED",
    "VN-WAT-2050":"WATER-INTEGRATED","VN-WS-NORTH-2030":"WATER-INTEGRATED",
    "VN-SW-MEKONG-2030":"VN-MEKONG-DELTA-2030",
}
for _pid in ["VN-TRAN-2055","VN-URB-METRO-2030","VN-MEKONG-DELTA-2030","VN-RED-RIVER-2030",
             "VN-IP-NORTH-2030","VN-ENV-IND-1894","VN-WW-2030","VN-SWM-NATIONAL-2030",
             "VN-SC-2030","VN-OG-2030","VN-EV-2030","VN-CARBON-2050"]:
    PLAN_TO_REPORT_KEY[_pid] = _pid


def _domain(url: str) -> str:
    try:
        d = urlparse(url).netloc.replace("www.", "").replace("m.", "")
        parts = d.split(".")
        return parts[-2].capitalize() if len(parts) >= 2 else parts[0].capitalize()
    except:
        return "Link"


def _normalise_date(raw: str) -> str:
    if not raw:
        return ""
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%d %b %Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except:
            pass
    if "ago" in raw.lower():
        return datetime.now().strftime("%Y-%m-%d")
    return raw[:10]


def _is_vi(text: str) -> bool:
    vi = set("ăâêôơưđáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ")
    return any(c.lower() in vi for c in (text or ""))


def _best_title(a: dict) -> str:
    t = (a.get("title") or "")
    if not _is_vi(t):
        return t
    en = a.get("title_en") or a.get("summary_en") or ""
    if en and not _is_vi(en):
        return f"[EN] {en}"
    return t


def _best_ko(a: dict, maxlen: int = 160) -> str:
    ko = a.get("summary_ko") or a.get("summary") or ""
    if ko and not _is_vi(ko):
        return ko[:maxlen]
    en = a.get("summary_en") or ""
    return f"[EN] {en[:maxlen-5]}" if en and not _is_vi(en) else ""


def _sort_key(a: dict) -> str:
    d = _normalise_date(a.get("published_date", ""))
    return d if d else "0000-00-00"


def generate_html_dashboard(articles: list, output_path: str = None) -> str:
    now_str  = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    week     = datetime.now().isocalendar()[1]
    week_str = f"W{week:02d} / {datetime.now().strftime('%Y-%m-%d')}"

    # 보고서 URL 로드
    report_urls: dict = {}
    try:
        p = Path(__file__).parent.parent / "config/report_urls.json"
        if p.exists():
            report_urls = json.loads(p.read_text())
    except:
        pass
    excel_db_url = report_urls.get("_excel_db", "")

    # legacy ID → 신규 ID 통합 매핑
    LEGACY_ALIAS = {
        # Old Genspark IDs → New Claude-aligned IDs
        "VN-PDP8-RENEWABLE":  "VN-PWR-PDP8-RENEWABLE",
        "VN-PDP8-LNG":        "VN-PWR-PDP8-LNG",
        "VN-PDP8-GRID":       "VN-PWR-PDP8-GRID",
        "VN-PDP8-COAL":       "VN-PWR-PDP8-COAL",
        "VN-PDP8-NUCLEAR":    "VN-PWR-PDP8-NUCLEAR",
        "VN-PDP8-HYDROGEN":   "VN-PWR-PDP8-NUCLEAR",  # 수소→원자력·수소 통합
        # Old Claude legacy IDs
        "VN-PWR-PDP8":        "VN-PWR-PDP8",           # 상위 그대로
        "VN-GAS-PDP8":        "VN-PWR-PDP8-LNG",
        "VN-GRID-SMART":      "VN-PWR-PDP8-GRID",
        "VN-COAL-RETIRE":     "VN-PWR-PDP8-COAL",
        "VN-REN-NPP-2050":    "VN-PWR-PDP8-NUCLEAR",
        "VN-LNG-HUB":         "VN-PWR-PDP8-LNG",
        # Water / Mekong
        "VN-WAT-2050":        "VN-WAT-RESOURCES",
        "VN-WS-NORTH-2030":   "VN-WAT-URBAN",
        "VN-SW-MEKONG-2030":  "VN-MEKONG-DELTA-2030",
    }

    # 기사 정렬 + 플랜별 버킷
    import ast
    all_arts = sorted(articles, key=_sort_key, reverse=True)
    plan_buckets: dict = defaultdict(list)
    for a in all_arts:
        plans = a.get("matched_plans") or []
        if isinstance(plans, str):
            try: plans = ast.literal_eval(plans)
            except: plans = [plans]
        for p in plans:
            # legacy ID는 신규 ID로 통합
            canonical = LEGACY_ALIAS.get(p, p)
            plan_buckets[canonical].append(a)

    # 통계
    total_arts   = len(articles)
    mapped_arts  = [a for a in articles if a.get("matched_plans")]
    total_mapped = len(mapped_arts)
    qc_pass      = sum(1 for a in articles if a.get("qc_status") == "PASS")

    # ── 사이드바 플랜 탭 JS 데이터 ────────────────────────────────────────
    plan_data_js = {}
    for pid in PLAN_ORDER:
        arts = sorted(plan_buckets.get(pid, []), key=_sort_key, reverse=True)
        plan_data_js[pid] = []
        for a in arts:
            en_s = a.get("summary_en") or ""
            if _is_vi(en_s): en_s = ""
            vi_s = a.get("summary_vi") or ""
            plan_data_js[pid].append({
                "title": _best_title(a),
                "url":   a.get("url", "#"),
                "date":  _normalise_date(a.get("published_date", "")),
                "src":   _domain(a.get("url", "")),
                "ko":    _best_ko(a, 140),
                "en":    en_s[:140] if en_s else "",
                "vi":    vi_s[:140] if vi_s and _is_vi(vi_s) else "",
                "qc":    a.get("qc_status", ""),
            })

    plan_data_json = json.dumps(plan_data_js, ensure_ascii=False)

    # ── 전체 피드 기사 JS 데이터 ─────────────────────────────────────────
    feed_arts = []
    seen_urls: set = set()
    for a in all_arts:
        url = a.get("url", "#")
        if url in seen_urls:
            continue
        seen_urls.add(url)
        plans = a.get("matched_plans") or []
        if isinstance(plans, str):
            try: plans = ast.literal_eval(plans)
            except: plans = [plans]
        # legacy → canonical
        plans = [LEGACY_ALIAS.get(p, p) for p in plans]
        # EN/VI 요약 (TTS용)
        en_sum = a.get("summary_en") or ""
        if _is_vi(en_sum): en_sum = ""
        vi_sum = a.get("summary_vi") or ""
        feed_arts.append({
            "title":  _best_title(a),
            "url":    url,
            "date":   _normalise_date(a.get("published_date", "")),
            "src":    _domain(url),
            "ko":     _best_ko(a, 140),
            "en":     en_sum[:140] if en_sum else "",
            "vi":     vi_sum[:140] if vi_sum and _is_vi(vi_sum) else "",
            "plans":  plans,
            "qc":     a.get("qc_status", ""),
        })
    feed_json = json.dumps(feed_arts, ensure_ascii=False)

    # ── 보고서 버튼 데이터 ────────────────────────────────────────────────
    REPORT_DEFS = [
        {"key": "PDP8-INTEGRATED",    "label": "⚡ PDP8 에너지",    "color": "#B45309"},
        {"key": "WATER-INTEGRATED",   "label": "💧 수자원",          "color": "#0369A1"},
        {"key": "HANOI-INTEGRATED",   "label": "🏙️ 하노이",          "color": "#B91C1C"},
        {"key": "VN-TRAN-2055",       "label": "🛣️ 교통 2055",       "color": "#EA580C"},
        {"key": "VN-URB-METRO-2030",  "label": "🚇 메트로",          "color": "#C2410C"},
        {"key": "VN-MEKONG-DELTA-2030","label":"🌾 메콩 델타",        "color": "#0D9488"},
        {"key": "VN-RED-RIVER-2030",  "label": "🏔️ 홍강",            "color": "#BE123C"},
        {"key": "VN-IP-NORTH-2030",   "label": "🏭 산업단지",        "color": "#7C3AED"},
        {"key": "VN-ENV-IND-1894",    "label": "🌿 D1894",           "color": "#15803D"},
        {"key": "VN-WW-2030",         "label": "💧 폐수",            "color": "#0891B2"},
        {"key": "VN-SWM-NATIONAL-2030","label":"♻️ 고형폐기물",      "color": "#16A34A"},
        {"key": "VN-SC-2030",         "label": "🏙️ 스마트시티",      "color": "#6D28D9"},
        {"key": "VN-OG-2030",         "label": "⛽ 석유가스",        "color": "#D97706"},
        {"key": "VN-EV-2030",         "label": "🚗 전기차",          "color": "#0D9488"},
        {"key": "VN-CARBON-2050",     "label": "🌍 탄소중립",        "color": "#166534"},
    ]
    report_defs_json = json.dumps(REPORT_DEFS, ensure_ascii=False)
    report_urls_json = json.dumps(report_urls, ensure_ascii=False)

    # ── 플랜 메타 JS ──────────────────────────────────────────────────────
    plan_meta_js = {
        pid: {"name": m["name"], "icon": m["icon"], "color": m["color"]}
        for pid, m in PLAN_META.items()
    }
    plan_meta_json  = json.dumps(plan_meta_js, ensure_ascii=False)
    plan_order_json = json.dumps(PLAN_ORDER, ensure_ascii=False)
    plan_to_rk_json = json.dumps(PLAN_TO_REPORT_KEY, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>🇻🇳 Vietnam Infrastructure Intelligence Hub</title>
<script src="https://cdn.sheetjs.com/xlsx-0.20.3/package/dist/xlsx.full.min.js"></script>
<style>
  :root {{
    --bg: #0F172A;
    --surface: #1E293B;
    --surface2: #293548;
    --border: rgba(255,255,255,.08);
    --text: #F1F5F9;
    --muted: #94A3B8;
    --accent: #3B82F6;
    --sidebar-w: 248px;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ height: 100%; }}
  body {{ background: var(--bg); color: var(--text);
          font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
          font-size: 13px; line-height: 1.55; }}

  /* ── TOPBAR ── */
  #topbar {{
    position: fixed; top: 0; left: 0; right: 0; z-index: 100;
    background: linear-gradient(90deg, #0F172A 0%, #1E3A8A 100%);
    border-bottom: 1px solid var(--border);
    height: 52px; display: flex; align-items: center; padding: 0 20px; gap: 20px;
    box-shadow: 0 2px 16px rgba(0,0,0,.4);
  }}
  #topbar .brand {{ color: #fff; font-weight: 800; font-size: 15px; white-space: nowrap; }}
  #topbar .brand span {{ color: #93C5FD; font-size: 11px; font-weight: 600; margin-left: 8px; }}
  #topbar .stats {{
    display: flex; gap: 14px; flex: 1;
    color: var(--muted); font-size: 11px;
  }}
  #topbar .stats b {{ color: #FCD34D; }}
  #topbar .topbtns {{ display: flex; gap: 8px; flex-shrink: 0; }}
  .tbtn {{
    padding: 6px 14px; border-radius: 7px; font-size: 11px; font-weight: 700;
    text-decoration: none; cursor: pointer; border: none; white-space: nowrap;
  }}
  .tbtn-primary {{ background: var(--accent); color: #fff; }}
  .tbtn-secondary {{ background: rgba(255,255,255,.1); color: #CBD5E1;
                     border: 1px solid var(--border); }}

  /* ── REPORT STRIP ── */
  #report-strip {{
    position: fixed; top: 52px; left: 0; right: 0; z-index: 99;
    background: var(--surface); border-bottom: 1px solid var(--border);
    padding: 8px 20px; overflow-x: auto; white-space: nowrap;
    scrollbar-width: none;
  }}
  #report-strip::-webkit-scrollbar {{ display: none; }}
  #report-strip .strip-label {{
    display: inline-block; color: var(--muted); font-size: 10px;
    font-weight: 700; letter-spacing: 1.2px; text-transform: uppercase;
    vertical-align: middle; margin-right: 12px;
  }}
  .rpt-pill {{
    display: inline-flex; align-items: center; gap: 5px;
    border-radius: 7px; padding: 5px 10px; margin-right: 6px;
    vertical-align: middle; cursor: default;
  }}
  .rpt-pill .pill-label {{
    color: #fff; font-size: 11px; font-weight: 700;
  }}
  .rpt-pill-btn {{
    color: rgba(255,255,255,.85); background: rgba(0,0,0,.25);
    border-radius: 4px; padding: 2px 8px; font-size: 10px; font-weight: 700;
    text-decoration: none; border: none; cursor: pointer;
    transition: background .15s;
  }}
  .rpt-pill-btn:hover {{ background: rgba(0,0,0,.45); }}

  /* ── LAYOUT ── */
  #layout {{
    display: flex;
    margin-top: 96px; /* topbar(52) + strip(44) */
    height: calc(100vh - 96px);
  }}

  /* ── SIDEBAR ── */
  #sidebar {{
    width: var(--sidebar-w); flex-shrink: 0;
    background: var(--surface);
    border-right: 1px solid var(--border);
    overflow-y: auto; padding: 12px 0;
    scrollbar-width: thin;
    scrollbar-color: var(--surface2) transparent;
  }}
  .sidebar-group {{
    padding: 8px 16px 3px;
    color: var(--muted); font-size: 9px; font-weight: 800;
    letter-spacing: 1.5px; text-transform: uppercase;
  }}
  .plan-tab {{
    display: flex; align-items: center; gap: 8px;
    padding: 7px 16px; cursor: pointer;
    border-left: 3px solid transparent;
    transition: all .15s; color: #94A3B8; font-size: 12px;
  }}
  .plan-tab:hover {{ background: var(--surface2); color: var(--text); }}
  .plan-tab.active {{
    color: #fff; font-weight: 700;
    background: rgba(255,255,255,.06);
  }}
  .plan-tab .tab-icon {{ font-size: 14px; flex-shrink: 0; }}
  .plan-tab .tab-name {{ flex: 1; line-height: 1.3; }}
  .plan-tab .tab-badge {{
    background: rgba(255,255,255,.15); color: #fff;
    border-radius: 9px; padding: 1px 7px; font-size: 10px; font-weight: 700;
    flex-shrink: 0;
  }}
  .plan-tab.active .tab-badge {{ background: rgba(255,255,255,.3); }}

  /* ── MAIN ── */
  #main {{
    flex: 1; overflow-y: auto; padding: 20px 24px;
    scrollbar-width: thin; scrollbar-color: var(--surface2) transparent;
  }}

  /* ── FEED HEADER ── */
  .feed-header {{
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 16px; padding-bottom: 12px;
    border-bottom: 1px solid var(--border);
  }}
  .feed-title {{ font-size: 15px; font-weight: 800; color: #fff; }}
  .feed-meta {{ font-size: 11px; color: var(--muted); }}
  .feed-count {{
    background: var(--accent); color: #fff;
    border-radius: 9px; padding: 2px 10px; font-size: 11px; font-weight: 700;
  }}

  /* ── ARTICLE CARD ── */
  .art-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px; padding: 14px 16px;
    margin-bottom: 8px; transition: border-color .15s, transform .1s;
  }}
  .art-card:hover {{
    border-color: rgba(59,130,246,.5);
    transform: translateY(-1px);
  }}
  .art-card.mapped {{ border-left: 3px solid #FBBF24; }}
  .art-meta {{
    display: flex; align-items: center; gap: 10px;
    margin-bottom: 7px; flex-wrap: wrap;
  }}
  .art-date {{ color: var(--muted); font-size: 11px; font-weight: 600; }}
  .art-src {{
    color: var(--accent); font-size: 11px; font-weight: 700;
    text-decoration: none;
  }}
  .art-src:hover {{ text-decoration: underline; }}
  .art-badge {{
    display: inline-block; border-radius: 8px; padding: 1px 8px;
    font-size: 9px; font-weight: 800; color: #fff; white-space: nowrap;
  }}
  .art-title {{
    font-size: 13px; font-weight: 700; color: #E2E8F0;
    line-height: 1.45; margin-bottom: 5px; text-decoration: none;
    display: block;
  }}
  .art-title:hover {{ color: #93C5FD; }}
  .art-ko {{
    font-size: 11px; color: #94A3B8; line-height: 1.6;
    border-top: 1px solid var(--border); padding-top: 6px; margin-top: 6px;
  }}

  /* ── TTS BUTTONS ── */
  .tts-row {{
    display: flex; gap: 5px; margin-top: 6px; padding-top: 6px;
    border-top: 1px solid var(--border);
  }}
  .tts-btn {{
    background: var(--surface2); color: var(--muted); border: 1px solid var(--border);
    border-radius: 6px; padding: 3px 10px; font-size: 10px; font-weight: 700;
    cursor: pointer; transition: all .15s;
  }}
  .tts-btn:hover {{ background: var(--accent); color: #fff; border-color: var(--accent); }}

  /* ── EMPTY STATE ── */
  .empty-state {{
    text-align: center; padding: 60px 20px; color: var(--muted);
  }}
  .empty-state .big {{ font-size: 40px; margin-bottom: 12px; }}

  /* ── SEARCH ── */
  #search-wrap {{ margin-bottom: 14px; }}
  #search-input {{
    width: 100%; background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 9px 14px; color: var(--text);
    font-size: 13px; outline: none;
    transition: border-color .15s;
  }}
  #search-input:focus {{ border-color: var(--accent); }}
  #search-input::placeholder {{ color: var(--muted); }}

  /* ── SCROLLBAR ── */
  ::-webkit-scrollbar {{ width: 4px; height: 4px; }}
  ::-webkit-scrollbar-track {{ background: transparent; }}
  ::-webkit-scrollbar-thumb {{ background: var(--surface2); border-radius: 4px; }}
</style>
</head>
<body>

<!-- ── TOP BAR ─────────────────────────────────────────────────────────── -->
<div id="topbar">
  <div class="brand">🇻🇳 Vietnam Infra Hub <span>{week_str}</span></div>
  <div class="stats">
    <span>수집 <b>{total_arts}</b>건</span>
    <span>매핑 <b>{total_mapped}</b>건</span>
    <span>QC <b>{qc_pass}</b>건</span>
    <span style="color:#94A3B8;font-size:10px">{now_str}</span>
  </div>
  <div class="topbtns">
    {'<a href="' + excel_db_url + '" class="tbtn tbtn-primary" target="_blank">🗄️ History DB Excel</a>' if excel_db_url else ''}
    <button class="tbtn tbtn-secondary" onclick="downloadAllExcel()">📥 전체 Excel</button>
  </div>
</div>

<!-- ── REPORT STRIP ────────────────────────────────────────────────────── -->
<div id="report-strip">
  <span class="strip-label">📁 보고서</span>
  <span id="strip-content">
    <span style="color:#64748B;font-size:11px">로딩 중...</span>
  </span>
</div>

<!-- ── LAYOUT ─────────────────────────────────────────────────────────── -->
<div id="layout">

  <!-- SIDEBAR -->
  <div id="sidebar">
    <div id="sidebar-content"></div>
  </div>

  <!-- MAIN FEED -->
  <div id="main">
    <div id="search-wrap">
      <input id="search-input" type="text" placeholder="🔍 기사 제목 / 출처 / 플랜 검색...">
    </div>
    <div class="feed-header">
      <div>
        <span class="feed-title" id="feed-title">전체 뉴스 피드</span>
        <span class="feed-meta" id="feed-subtitle"> · 최신순</span>
      </div>
      <span class="feed-count" id="feed-count">0</span>
    </div>
    <div id="feed"></div>
  </div>

</div>

<script>
// ── DATA ─────────────────────────────────────────────────────────────────
const PLAN_DATA     = {plan_data_json};
const FEED_ARTS     = {feed_json};
const PLAN_META     = {plan_meta_json};
const PLAN_ORDER    = {plan_order_json};
const PLAN_TO_RK    = {plan_to_rk_json};
const REPORT_DEFS   = {report_defs_json};
const REPORT_URLS   = {report_urls_json};
const EXCEL_DB_URL  = {json.dumps(excel_db_url)};

// ── STATE ─────────────────────────────────────────────────────────────────
let currentPlan  = null;  // null = all-feed
let searchTerm   = "";

// ── REPORT STRIP ─────────────────────────────────────────────────────────
function buildStrip() {{
  const wrap = document.getElementById('strip-content');
  let html = '';
  REPORT_DEFS.forEach(def => {{
    const ru = REPORT_URLS[def.key] || {{}};
    const wordUrl = (typeof ru === 'object') ? (ru.word || '') : '';
    const pptUrl  = (typeof ru === 'object') ? (ru.ppt  || '') : '';
    if (!wordUrl && !pptUrl) return;
    const exUrl = EXCEL_DB_URL || '';
    html += `<span class="rpt-pill" style="background:${{def.color}}">
      <span class="pill-label">${{def.label}}</span>
      ${{wordUrl ? `<a href="${{wordUrl}}" class="rpt-pill-btn" target="_blank">Word</a>` : ''}}
      ${{pptUrl  ? `<a href="${{pptUrl}}"  class="rpt-pill-btn" target="_blank">PPT</a>`  : ''}}
      ${{exUrl   ? `<a href="${{exUrl}}"   class="rpt-pill-btn" target="_blank">Excel</a>` : ''}}
    </span>`;
  }});
  wrap.innerHTML = html || '<span style="color:#64748B;font-size:11px">보고서 URL 미등록 — AI Drive 업로드 후 갱신됩니다</span>';
}}

// ── SIDEBAR ───────────────────────────────────────────────────────────────
function buildSidebar() {{
  const groups = {{}};
  PLAN_ORDER.forEach(pid => {{
    const m = PLAN_META[pid];
    if (!m) return;
    const g = m.group || '기타';
    if (!groups[g]) groups[g] = [];
    groups[g].push(pid);
  }});

  let html = `
    <div class="plan-tab ${{currentPlan === null ? 'active' : ''}}"
         style="border-left-color:${{currentPlan === null ? '#3B82F6' : 'transparent'}};margin-bottom:4px"
         onclick="selectPlan(null)">
      <span class="tab-icon">📰</span>
      <span class="tab-name" style="font-weight:700">전체 피드</span>
      <span class="tab-badge">${{FEED_ARTS.length}}</span>
    </div>`;

  Object.entries(groups).forEach(([gName, pids]) => {{
    html += `<div class="sidebar-group">${{gName}}</div>`;
    pids.forEach(pid => {{
      const m   = PLAN_META[pid] || {{}};
      const cnt = (PLAN_DATA[pid] || []).length;
      if (cnt === 0) return;
      const active = currentPlan === pid;
      html += `<div class="plan-tab ${{active ? 'active' : ''}}"
                    style="border-left-color:${{active ? m.color : 'transparent'}}"
                    onclick="selectPlan('${{pid}}')">
        <span class="tab-icon">${{m.icon || '📋'}}</span>
        <span class="tab-name">${{m.name || pid}}</span>
        <span class="tab-badge">${{cnt}}</span>
      </div>`;
    }});
  }});

  document.getElementById('sidebar-content').innerHTML = html;
}}

// ── ARTICLE CARD ──────────────────────────────────────────────────────────
function artCard(a, showPlanBadges) {{
  const isMapped = (a.plans && a.plans.length > 0) || false;
  let badges = '';
  if (showPlanBadges && a.plans) {{
    a.plans.slice(0, 2).forEach(pid => {{
      const m = PLAN_META[pid] || {{}};
      badges += `<span class="art-badge" style="background:${{m.color || '#64748B'}}">${{m.icon||''}} ${{m.name||pid}}</span>`;
    }});
    if (a.plans.length > 2)
      badges += `<span class="art-badge" style="background:#475569">+${{a.plans.length-2}}</span>`;
  }}
  const koBlock = a.ko
    ? `<div class="art-ko">🇰🇷 ${{a.ko}}</div>` : '';
  // TTS 버튼 (3개국어)
  const ttsTexts = [];
  if (a.ko) ttsTexts.push({{lang:'ko-KR', label:'🇰🇷 KO', text: a.ko}});
  if (a.en) ttsTexts.push({{lang:'en-US', label:'🇺🇸 EN', text: a.en}});
  if (a.vi) ttsTexts.push({{lang:'vi-VN', label:'🇻🇳 VI', text: a.vi}});
  const ttsBlock = ttsTexts.length > 0
    ? `<div class="tts-row">${{ttsTexts.map(t =>
        `<button class="tts-btn" onclick="speakText('${{t.text.replace(/'/g,"\\\\'")}}',' ${{t.lang}}')" title="TTS ${{t.label}}">${{t.label}} 🔊</button>`
      ).join('')}}</div>` : '';
  return `
  <div class="art-card ${{isMapped ? 'mapped' : ''}}">
    <div class="art-meta">
      <span class="art-date">📅 ${{a.date || '—'}}</span>
      <a href="${{a.url}}" class="art-src" target="_blank" rel="noopener">${{a.src}} ↗</a>
      ${{badges}}
    </div>
    <a href="${{a.url}}" class="art-title" target="_blank" rel="noopener">${{a.title || '(제목 없음)'}}</a>
    ${{koBlock}}
    ${{ttsBlock}}
  </div>`;
}}

// ── RENDER FEED ───────────────────────────────────────────────────────────
function renderFeed() {{
  const feed      = document.getElementById('feed');
  const countEl   = document.getElementById('feed-count');
  const titleEl   = document.getElementById('feed-title');
  const subEl     = document.getElementById('feed-subtitle');
  const q         = searchTerm.toLowerCase();

  let arts, showBadges, titleText;
  if (currentPlan === null) {{
    arts      = FEED_ARTS;
    showBadges = true;
    titleText  = '전체 뉴스 피드';
  }} else {{
    arts      = PLAN_DATA[currentPlan] || [];
    showBadges = false;
    const m    = PLAN_META[currentPlan] || {{}};
    titleText  = `${{m.icon||''}} ${{m.name||currentPlan}}`;
  }}

  // 검색 필터
  if (q) {{
    arts = arts.filter(a =>
      (a.title||'').toLowerCase().includes(q) ||
      (a.src||'').toLowerCase().includes(q) ||
      (a.ko||'').toLowerCase().includes(q) ||
      (a.plans||[]).some(p => (PLAN_META[p]?.name||'').toLowerCase().includes(q))
    );
  }}

  titleEl.textContent = titleText;
  subEl.textContent   = ' · 최신순' + (q ? ' · "' + searchTerm + '" 검색' : '');
  countEl.textContent = arts.length + '건';

  if (arts.length === 0) {{
    feed.innerHTML = `<div class="empty-state">
      <div class="big">🔍</div>
      <div>기사가 없습니다</div>
    </div>`;
    return;
  }}

  feed.innerHTML = arts.map(a => artCard(a, showBadges)).join('');
}}

// ── SELECT PLAN ───────────────────────────────────────────────────────────
function selectPlan(pid) {{
  currentPlan = pid;
  buildSidebar();
  renderFeed();
  document.getElementById('main').scrollTop = 0;
}}

// ── SEARCH ────────────────────────────────────────────────────────────────
document.getElementById('search-input').addEventListener('input', function() {{
  searchTerm = this.value.trim();
  renderFeed();
}});

// ── EXCEL DOWNLOAD ────────────────────────────────────────────────────────
function downloadAllExcel() {{
  if (typeof XLSX === 'undefined') {{
    alert('SheetJS 로딩 중... 잠시 후 다시 시도하세요');
    return;
  }}
  const wb = XLSX.utils.book_new();

  // 전체 피드 시트
  const allRows = FEED_ARTS.map(a => ({{
    날짜: a.date, 플랜: (a.plans||[]).join(' | '), 제목: a.title, 출처: a.src, URL: a.url, 요약KO: a.ko
  }}));
  XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(allRows), 'All_Articles');

  // 플랜별 시트
  PLAN_ORDER.forEach(pid => {{
    const arts = PLAN_DATA[pid] || [];
    if (arts.length === 0) return;
    const m = PLAN_META[pid] || {{}};
    const rows = arts.map(a => ({{ 날짜:a.date, 제목:a.title, 출처:a.src, URL:a.url, 요약KO:a.ko }}));
    const sheetName = (m.name || pid).replace(/[^a-zA-Z가-힣0-9 ]/g,'').substring(0,28);
    XLSX.utils.book_append_sheet(wb, XLSX.utils.json_to_sheet(rows), sheetName);
  }});

  const today = new Date().toISOString().slice(0,10);
  XLSX.writeFile(wb, `Vietnam_Infra_Dashboard_${{today}}.xlsx`);
}}

// ── TTS (Web Speech API) ──────────────────────────────────────────────────
function speakText(text, lang) {{
  if (!window.speechSynthesis) {{ alert('이 브라우저에서 TTS를 지원하지 않습니다'); return; }}
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = lang.trim();
  u.rate = 0.95;
  window.speechSynthesis.speak(u);
}}

// ── INIT ──────────────────────────────────────────────────────────────────
buildStrip();
buildSidebar();
renderFeed();
</script>
</body>
</html>"""

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  ✓ Dashboard v5.0: {output_path} ({len(html)//1024}KB)")

    return html


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    try:
        with open("genspark_output.json", encoding="utf-8") as f:
            data = json.load(f)
        articles = data if isinstance(data, list) else data.get("articles", [])
    except:
        articles = []
    generate_html_dashboard(articles, "outputs/dashboard/index.html")
