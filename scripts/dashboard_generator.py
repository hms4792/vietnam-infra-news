"""
dashboard_generator.py v6.0
────────────────────────────
모바일 반응형 · 매핑 기사 중심 · 드릴다운 보고서
- 첫 화면: 📌 매핑 기사 (매핑된 최신 기사 only)
- 사이드바: All / 📌 Mapped / 플랜 그룹
- 플랜 선택 시 해당 플랜 기사 + Word/PPT 다운로드 버튼
- 모바일: 햄버거 메뉴
"""
import os, sys, json, ast
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
    "VN-PWR-PDP8":"PDP8-INTEGRATED",
    "VN-PWR-PDP8-RENEWABLE":"PDP8-INTEGRATED","VN-PWR-PDP8-LNG":"PDP8-INTEGRATED",
    "VN-PWR-PDP8-NUCLEAR":"PDP8-INTEGRATED","VN-PWR-PDP8-COAL":"PDP8-INTEGRATED",
    "VN-PWR-PDP8-GRID":"PDP8-INTEGRATED",
    "VN-WAT-RESOURCES":"WATER-INTEGRATED","VN-WAT-URBAN":"WATER-INTEGRATED",
    "VN-WAT-RURAL":"WATER-INTEGRATED",
    "HN-URBAN-INFRA":"HANOI-INTEGRATED","HN-URBAN-NORTH":"HANOI-INTEGRATED",
    "HN-URBAN-WEST":"HANOI-INTEGRATED",
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

LEGACY_ALIAS = {
    "VN-PDP8-RENEWABLE":"VN-PWR-PDP8-RENEWABLE","VN-PDP8-LNG":"VN-PWR-PDP8-LNG",
    "VN-PDP8-GRID":"VN-PWR-PDP8-GRID","VN-PDP8-COAL":"VN-PWR-PDP8-COAL",
    "VN-PDP8-NUCLEAR":"VN-PWR-PDP8-NUCLEAR","VN-PDP8-HYDROGEN":"VN-PWR-PDP8-NUCLEAR",
    "VN-GAS-PDP8":"VN-PWR-PDP8-LNG","VN-GRID-SMART":"VN-PWR-PDP8-GRID",
    "VN-COAL-RETIRE":"VN-PWR-PDP8-COAL","VN-REN-NPP-2050":"VN-PWR-PDP8-NUCLEAR",
    "VN-LNG-HUB":"VN-PWR-PDP8-LNG",
    "VN-WAT-2050":"VN-WAT-RESOURCES","VN-WS-NORTH-2030":"VN-WAT-URBAN",
    "VN-SW-MEKONG-2030":"VN-MEKONG-DELTA-2030",
}

REPORT_DEFS = [
    {"key":"PDP8-INTEGRATED",    "label":"⚡ PDP8 에너지",   "color":"#B45309"},
    {"key":"WATER-INTEGRATED",   "label":"💧 수자원",         "color":"#0369A1"},
    {"key":"HANOI-INTEGRATED",   "label":"🏙️ 하노이",         "color":"#B91C1C"},
    {"key":"VN-TRAN-2055",       "label":"🛣️ 교통 2055",      "color":"#EA580C"},
    {"key":"VN-URB-METRO-2030",  "label":"🚇 메트로",         "color":"#C2410C"},
    {"key":"VN-MEKONG-DELTA-2030","label":"🌾 메콩 델타",     "color":"#0D9488"},
    {"key":"VN-RED-RIVER-2030",  "label":"🏔️ 홍강",           "color":"#BE123C"},
    {"key":"VN-IP-NORTH-2030",   "label":"🏭 산업단지",       "color":"#7C3AED"},
    {"key":"VN-ENV-IND-1894",    "label":"🌿 D1894",          "color":"#15803D"},
    {"key":"VN-WW-2030",         "label":"💧 폐수",           "color":"#0891B2"},
    {"key":"VN-SWM-NATIONAL-2030","label":"♻️ 고형폐기물",    "color":"#16A34A"},
    {"key":"VN-SC-2030",         "label":"🏙️ 스마트시티",     "color":"#6D28D9"},
    {"key":"VN-OG-2030",         "label":"⛽ 석유가스",       "color":"#D97706"},
    {"key":"VN-EV-2030",         "label":"🚗 전기차",         "color":"#0D9488"},
    {"key":"VN-CARBON-2050",     "label":"🌍 탄소중립",       "color":"#166534"},
]


def _domain(url: str) -> str:
    try:
        d = urlparse(url).netloc.replace("www.", "").replace("m.", "")
        parts = d.split(".")
        return parts[-2].capitalize() if len(parts) >= 2 else parts[0].capitalize()
    except:
        return "Link"

def _normalise_date(raw: str) -> str:
    if not raw: return ""
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%d %b %Y"):
        try: return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except: pass
    if "ago" in raw.lower(): return datetime.now().strftime("%Y-%m-%d")
    return raw[:10]

def _is_vi(text: str) -> bool:
    vi = set("ăâêôơưđáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ")
    return any(c.lower() in vi for c in (text or ""))

def _best_title(a: dict) -> str:
    t = (a.get("title") or "")
    if not _is_vi(t): return t
    en = a.get("title_en") or a.get("summary_en") or ""
    if en and not _is_vi(en): return f"[EN] {en}"
    return t

def _best_ko(a: dict, maxlen: int = 160) -> str:
    ko = a.get("summary_ko") or a.get("summary") or ""
    if ko and not _is_vi(ko): return ko[:maxlen]
    en = a.get("summary_en") or ""
    return f"[EN] {en[:maxlen-5]}" if en and not _is_vi(en) else ""

def _sort_key(a: dict) -> str:
    d = _normalise_date(a.get("published_date", ""))
    return d if d else "0000-00-00"


def generate_html_dashboard(articles: list, output_path: str = None) -> str:
    now_str  = datetime.now().strftime("%Y-%m-%d %H:%M")
    week     = datetime.now().isocalendar()[1]
    week_str = f"W{week:02d} · {datetime.now().strftime('%Y-%m-%d')}"

    # Report URLs
    report_urls: dict = {}
    try:
        p = Path(__file__).parent.parent / "config/report_urls.json"
        if p.exists(): report_urls = json.loads(p.read_text())
    except: pass
    excel_db_url = report_urls.get("_excel_db", "")
    weekly_excel_url = report_urls.get("_weekly_excel", "")

    # Process articles
    all_arts = sorted(articles, key=_sort_key, reverse=True)
    plan_buckets: dict = defaultdict(list)
    for a in all_arts:
        plans = a.get("matched_plans") or []
        if isinstance(plans, str):
            try: plans = ast.literal_eval(plans)
            except: plans = [plans]
        for p in plans:
            canonical = LEGACY_ALIAS.get(p, p)
            plan_buckets[canonical].append(a)

    total_arts   = len(articles)
    mapped_arts  = [a for a in articles if a.get("matched_plans")]
    total_mapped = len(mapped_arts)
    qc_pass      = sum(1 for a in articles if a.get("qc_status") == "PASS")

    # Plan data for JS
    plan_data_js = {}
    for pid in PLAN_ORDER:
        arts = sorted(plan_buckets.get(pid, []), key=_sort_key, reverse=True)
        plan_data_js[pid] = []
        for a in arts:
            en_s = a.get("summary_en") or ""
            if _is_vi(en_s): en_s = ""
            plan_data_js[pid].append({
                "title": _best_title(a), "url": a.get("url","#"),
                "date": _normalise_date(a.get("published_date","")),
                "src": _domain(a.get("url","")),
                "ko": _best_ko(a, 160),
                "en": en_s[:160] if en_s else "",
                "vi": (a.get("summary_vi") or "")[:160],
                "qc": a.get("qc_status", ""),
            })

    # Feed data for JS
    feed_arts = []
    seen_urls: set = set()
    for a in all_arts:
        url = a.get("url", "#")
        if url in seen_urls: continue
        seen_urls.add(url)
        plans = a.get("matched_plans") or []
        if isinstance(plans, str):
            try: plans = ast.literal_eval(plans)
            except: plans = [plans]
        plans = [LEGACY_ALIAS.get(p, p) for p in plans]
        en_sum = a.get("summary_en") or ""
        if _is_vi(en_sum): en_sum = ""
        feed_arts.append({
            "title": _best_title(a), "url": url,
            "date": _normalise_date(a.get("published_date","")),
            "src": _domain(url),
            "ko": _best_ko(a, 160),
            "en": en_sum[:160] if en_sum else "",
            "vi": (a.get("summary_vi") or "")[:160],
            "plans": plans, "qc": a.get("qc_status",""),
        })

    # JSON embeds
    plan_data_json   = json.dumps(plan_data_js, ensure_ascii=False)
    feed_json        = json.dumps(feed_arts, ensure_ascii=False)
    plan_meta_js     = {pid: {"name":m["name"],"icon":m["icon"],"color":m["color"]} for pid, m in PLAN_META.items()}
    plan_meta_json   = json.dumps(plan_meta_js, ensure_ascii=False)
    plan_order_json  = json.dumps(PLAN_ORDER, ensure_ascii=False)
    plan_to_rk_json  = json.dumps(PLAN_TO_REPORT_KEY, ensure_ascii=False)
    report_defs_json = json.dumps(REPORT_DEFS, ensure_ascii=False)
    report_urls_json = json.dumps(report_urls, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>🇻🇳 Vietnam Infrastructure Intelligence Hub</title>
<script src="https://cdn.sheetjs.com/xlsx-0.20.3/package/dist/xlsx.full.min.js"></script>
<style>
  :root {{
    --bg: #0B1120; --surface: #151D2E; --surface2: #1C2740;
    --border: rgba(148,163,184,.1); --text: #E2E8F0; --muted: #64748B;
    --accent: #3B82F6; --gold: #F59E0B; --sidebar-w: 260px;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  html, body {{ height: 100%; }}
  body {{ background: var(--bg); color: var(--text);
          font-family: 'Inter',-apple-system,'Segoe UI',sans-serif;
          font-size: 13px; line-height: 1.5; }}

  /* ── TOPBAR ── */
  .topbar {{
    position: fixed; top: 0; left: 0; right: 0; z-index: 200;
    background: rgba(11,17,32,.92); backdrop-filter: blur(16px);
    border-bottom: 1px solid var(--border);
    height: 56px; display: flex; align-items: center; padding: 0 20px; gap: 16px;
  }}
  .hamburger {{
    display: none; background: none; border: none; color: var(--text);
    font-size: 22px; cursor: pointer; padding: 4px 8px;
  }}
  .brand {{ color: #fff; font-weight: 800; font-size: 16px; white-space: nowrap; flex-shrink: 0; }}
  .brand small {{ color: var(--muted); font-size: 11px; font-weight: 500; margin-left: 8px; }}
  .topbar-stats {{
    display: flex; gap: 16px; color: var(--muted); font-size: 12px;
    flex: 1; min-width: 0;
  }}
  .topbar-stats b {{ color: #FCD34D; font-weight: 700; }}
  .topbar-stats .qc {{ color: #4ADE80; }}
  .search-box {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 7px 12px; color: var(--text);
    font-size: 13px; width: 220px; outline: none;
    transition: border-color .2s;
  }}
  .search-box:focus {{ border-color: var(--accent); }}
  .search-box::placeholder {{ color: var(--muted); }}
  .top-btn {{
    padding: 7px 14px; border-radius: 8px; font-size: 12px; font-weight: 700;
    border: none; cursor: pointer; text-decoration: none; white-space: nowrap;
    transition: all .2s;
  }}
  .top-btn-primary {{ background: var(--accent); color: #fff; }}
  .top-btn-primary:hover {{ background: #2563EB; }}
  .top-btn-ghost {{ background: transparent; color: var(--muted); border: 1px solid var(--border); }}
  .top-btn-ghost:hover {{ color: var(--text); border-color: var(--muted); }}

  /* ── LAYOUT ── */
  .layout {{ display: flex; margin-top: 56px; height: calc(100vh - 56px); }}

  /* ── SIDEBAR ── */
  .sidebar {{
    width: var(--sidebar-w); flex-shrink: 0;
    background: var(--surface); border-right: 1px solid var(--border);
    overflow-y: auto; padding: 8px 0;
    scrollbar-width: thin; scrollbar-color: var(--surface2) transparent;
  }}
  .nav-item {{
    display: flex; align-items: center; gap: 10px;
    padding: 9px 16px; cursor: pointer;
    border-left: 3px solid transparent;
    transition: all .15s; color: var(--muted); font-size: 13px;
  }}
  .nav-item:hover {{ background: var(--surface2); color: var(--text); }}
  .nav-item.active {{ color: #fff; font-weight: 700; background: rgba(59,130,246,.08); }}
  .nav-item .nav-icon {{ font-size: 15px; flex-shrink: 0; width: 20px; text-align: center; }}
  .nav-item .nav-name {{ flex: 1; }}
  .nav-item .nav-count {{
    background: rgba(255,255,255,.08); color: var(--muted);
    border-radius: 10px; padding: 1px 8px; font-size: 11px; font-weight: 700;
  }}
  .nav-item.active .nav-count {{ background: rgba(59,130,246,.2); color: var(--accent); }}
  .nav-group {{
    padding: 14px 16px 4px; color: var(--muted);
    font-size: 10px; font-weight: 800; letter-spacing: 1.5px; text-transform: uppercase;
  }}
  .nav-divider {{ height: 1px; background: var(--border); margin: 8px 16px; }}

  /* ── MAIN ── */
  .main {{
    flex: 1; overflow-y: auto; padding: 20px;
    scrollbar-width: thin; scrollbar-color: var(--surface2) transparent;
  }}

  /* ── REPORT BAR (shown in plan view) ── */
  .report-bar {{
    display: none; background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 14px 18px; margin-bottom: 16px;
    align-items: center; gap: 12px; flex-wrap: wrap;
  }}
  .report-bar.visible {{ display: flex; }}
  .report-bar .rb-label {{ color: var(--muted); font-size: 11px; font-weight: 700; }}
  .report-bar .rb-btn {{
    padding: 6px 14px; border-radius: 7px; font-size: 12px; font-weight: 700;
    text-decoration: none; color: #fff; transition: opacity .2s;
  }}
  .report-bar .rb-btn:hover {{ opacity: .85; }}

  /* ── FEED HEADER ── */
  .feed-hdr {{
    display: flex; align-items: center; justify-content: space-between;
    margin-bottom: 14px; padding-bottom: 12px; border-bottom: 1px solid var(--border);
  }}
  .feed-hdr h2 {{ font-size: 16px; font-weight: 800; color: #fff; }}
  .feed-hdr .sub {{ color: var(--muted); font-size: 12px; margin-left: 8px; font-weight: 400; }}
  .feed-count {{
    background: var(--accent); color: #fff;
    border-radius: 10px; padding: 2px 12px; font-size: 12px; font-weight: 700;
  }}

  /* ── ARTICLE CARD ── */
  .card {{
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 16px; margin-bottom: 8px;
    transition: border-color .2s, transform .15s;
    border-left: 3px solid transparent;
  }}
  .card:hover {{ border-color: rgba(59,130,246,.4); transform: translateY(-1px); }}
  .card.mapped {{ border-left-color: var(--gold); }}
  .card-top {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }}
  .card-date {{ color: var(--muted); font-size: 12px; font-weight: 600; }}
  .card-src {{ color: var(--accent); font-size: 12px; font-weight: 700; text-decoration: none; }}
  .card-src:hover {{ text-decoration: underline; }}
  .badge {{
    display: inline-block; border-radius: 5px; padding: 2px 8px;
    font-size: 10px; font-weight: 800; color: #fff; white-space: nowrap;
  }}
  .card-title {{
    font-size: 14px; font-weight: 700; color: #F1F5F9; line-height: 1.5;
    text-decoration: none; display: block; margin-bottom: 6px;
  }}
  .card-title:hover {{ color: #93C5FD; }}
  .card-summary {{
    font-size: 12px; color: var(--muted); line-height: 1.7;
    padding-top: 8px; border-top: 1px solid var(--border);
  }}
  .tts-row {{ display: flex; gap: 6px; margin-top: 8px; }}
  .tts-btn {{
    background: var(--surface2); color: var(--muted); border: 1px solid var(--border);
    border-radius: 6px; padding: 4px 10px; font-size: 11px; font-weight: 700;
    cursor: pointer; transition: all .15s;
  }}
  .tts-btn:hover {{ background: var(--accent); color: #fff; border-color: var(--accent); }}

  /* ── EMPTY ── */
  .empty {{ text-align: center; padding: 60px 20px; color: var(--muted); }}
  .empty .icon {{ font-size: 40px; margin-bottom: 12px; }}

  /* ── MOBILE ── */
  @media (max-width: 768px) {{
    .hamburger {{ display: block; }}
    .topbar-stats {{ display: none; }}
    .search-box {{ width: 120px; }}
    .sidebar {{
      position: fixed; top: 56px; left: 0; bottom: 0;
      z-index: 150; transform: translateX(-100%);
      transition: transform .25s ease;
      box-shadow: 4px 0 24px rgba(0,0,0,.5);
    }}
    .sidebar.open {{ transform: translateX(0); }}
    .overlay {{
      display: none; position: fixed; inset: 0; top: 56px;
      background: rgba(0,0,0,.5); z-index: 140;
    }}
    .overlay.open {{ display: block; }}
    .main {{ padding: 14px; }}
    .card {{ padding: 12px; }}
    .card-title {{ font-size: 13px; }}
  }}

  /* scrollbar */
  ::-webkit-scrollbar {{ width: 5px; }}
  ::-webkit-scrollbar-track {{ background: transparent; }}
  ::-webkit-scrollbar-thumb {{ background: var(--surface2); border-radius: 4px; }}
</style>
</head>
<body>

<!-- ── TOPBAR ── -->
<div class="topbar">
  <button class="hamburger" onclick="toggleSidebar()" aria-label="Menu">☰</button>
  <div class="brand">🇻🇳 Vietnam Infra Hub <small>{week_str}</small></div>
  <div class="topbar-stats">
    <span>수집 <b>{total_arts}</b></span>
    <span>매핑 <b>{total_mapped}</b></span>
    <span>QC <b class="qc">{qc_pass}</b></span>
  </div>
  <input class="search-box" id="searchInput" type="text" placeholder="🔍 검색...">
  <button class="top-btn top-btn-primary" onclick="downloadAllExcel()">📥 Excel</button>
  {'<a href="' + excel_db_url + '" class="top-btn top-btn-ghost" target="_blank">🗄️ DB</a>' if excel_db_url else ''}
</div>

<div class="overlay" id="overlay" onclick="toggleSidebar()"></div>

<!-- ── LAYOUT ── -->
<div class="layout">
  <div class="sidebar" id="sidebar"></div>
  <div class="main" id="main">
    <div class="report-bar" id="reportBar"></div>
    <div class="feed-hdr">
      <div><h2 id="feedTitle">📌 매핑 기사</h2><span class="sub" id="feedSub">최신순</span></div>
      <span class="feed-count" id="feedCount">0</span>
    </div>
    <div id="feed"></div>
  </div>
</div>

<script>
const PLAN_DATA   = {plan_data_json};
const FEED_ARTS   = {feed_json};
const PLAN_META   = {plan_meta_json};
const PLAN_ORDER  = {plan_order_json};
const PLAN_TO_RK  = {plan_to_rk_json};
const REPORT_DEFS = {report_defs_json};
const REPORT_URLS = {report_urls_json};
const EXCEL_DB    = {json.dumps(excel_db_url)};
const WEEKLY_XL   = {json.dumps(weekly_excel_url)};

let currentView = 'mapped';  // 'all' | 'mapped' | plan_id
let searchTerm  = '';

// ── SIDEBAR ──
function buildSidebar() {{
  const sb = document.getElementById('sidebar');
  const mappedCount = FEED_ARTS.filter(a => a.plans && a.plans.length > 0).length;

  let html = '';
  // Top-level views
  html += navItem('📌', '매핑 기사', mappedCount, 'mapped');
  html += navItem('📰', '전체 기사', FEED_ARTS.length, 'all');
  html += '<div class="nav-divider"></div>';

  // Plan groups
  const groups = {{}};
  PLAN_ORDER.forEach(pid => {{
    const m = PLAN_META[pid];
    if (!m) return;
    const g = m.group || '기타';
    if (!groups[g]) groups[g] = [];
    groups[g].push(pid);
  }});

  Object.entries(groups).forEach(([gName, pids]) => {{
    const groupTotal = pids.reduce((s, pid) => s + (PLAN_DATA[pid] || []).length, 0);
    if (groupTotal === 0) return;
    html += `<div class="nav-group">${{gName}}</div>`;
    pids.forEach(pid => {{
      const m = PLAN_META[pid] || {{}};
      const cnt = (PLAN_DATA[pid] || []).length;
      if (cnt === 0) return;
      html += navItem(m.icon || '📋', m.name || pid, cnt, pid);
    }});
  }});
  sb.innerHTML = html;
}}

function navItem(icon, name, count, viewId) {{
  const active = currentView === viewId ? 'active' : '';
  const bc = (currentView === viewId && PLAN_META[viewId]) ?
    `border-left-color:${{PLAN_META[viewId].color}}` : '';
  return `<div class="nav-item ${{active}}" style="${{bc}}" onclick="setView('${{viewId}}')">
    <span class="nav-icon">${{icon}}</span>
    <span class="nav-name">${{name}}</span>
    <span class="nav-count">${{count}}</span>
  </div>`;
}}

// ── REPORT BAR ──
function updateReportBar() {{
  const bar = document.getElementById('reportBar');
  if (!PLAN_META[currentView]) {{
    bar.className = 'report-bar';
    return;
  }}
  const rk = PLAN_TO_RK[currentView] || currentView;
  const ru = REPORT_URLS[rk] || {{}};
  const wordUrl = (typeof ru === 'object') ? (ru.word || '') : '';
  const pptUrl  = (typeof ru === 'object') ? (ru.ppt  || '') : '';
  const xlUrl   = (typeof ru === 'object') ? (ru.excel || '') : '';
  if (!wordUrl && !pptUrl && !xlUrl) {{
    bar.className = 'report-bar';
    return;
  }}
  const m = PLAN_META[currentView] || {{}};
  let html = `<span class="rb-label">${{m.icon||''}} ${{m.name||currentView}} 보고서</span>`;
  if (wordUrl) html += `<a href="${{wordUrl}}" class="rb-btn" style="background:#2563EB" target="_blank">📄 Word</a>`;
  if (pptUrl)  html += `<a href="${{pptUrl}}"  class="rb-btn" style="background:#7C3AED" target="_blank">📊 PPT</a>`;
  if (xlUrl)   html += `<a href="${{xlUrl}}"   class="rb-btn" style="background:#059669" target="_blank">📗 Excel</a>`;
  else if (EXCEL_DB) html += `<a href="${{EXCEL_DB}}" class="rb-btn" style="background:#059669" target="_blank">📗 Excel DB</a>`;
  bar.innerHTML = html;
  bar.className = 'report-bar visible';
}}

// ── RENDER FEED ──
function renderFeed() {{
  const feed    = document.getElementById('feed');
  const countEl = document.getElementById('feedCount');
  const titleEl = document.getElementById('feedTitle');
  const subEl   = document.getElementById('feedSub');
  const q       = searchTerm.toLowerCase();

  let arts, showBadges, title;
  if (currentView === 'mapped') {{
    arts = FEED_ARTS.filter(a => a.plans && a.plans.length > 0);
    showBadges = true;
    title = '📌 매핑 기사';
  }} else if (currentView === 'all') {{
    arts = FEED_ARTS;
    showBadges = true;
    title = '📰 전체 기사';
  }} else {{
    arts = (PLAN_DATA[currentView] || []);
    showBadges = false;
    const m = PLAN_META[currentView] || {{}};
    title = `${{m.icon||''}} ${{m.name||currentView}}`;
  }}

  if (q) {{
    arts = arts.filter(a =>
      (a.title||'').toLowerCase().includes(q) ||
      (a.src||'').toLowerCase().includes(q) ||
      (a.ko||'').toLowerCase().includes(q) ||
      (a.plans||[]).some(p => (PLAN_META[p]?.name||'').toLowerCase().includes(q))
    );
  }}

  titleEl.textContent = title;
  subEl.textContent   = '최신순' + (q ? ` · "${{searchTerm}}"` : '');
  countEl.textContent = arts.length + '건';
  updateReportBar();

  if (arts.length === 0) {{
    feed.innerHTML = '<div class="empty"><div class="icon">🔍</div><div>기사가 없습니다</div></div>';
    return;
  }}

  feed.innerHTML = arts.map(a => cardHTML(a, showBadges)).join('');
}}

function cardHTML(a, showBadges) {{
  const isMapped = a.plans && a.plans.length > 0;
  let badges = '';
  if (showBadges && a.plans) {{
    a.plans.slice(0, 3).forEach(pid => {{
      const m = PLAN_META[pid] || {{}};
      badges += `<span class="badge" style="background:${{m.color||'#475569'}}">${{m.icon||''}} ${{m.name||pid}}</span> `;
    }});
    if (a.plans.length > 3) badges += `<span class="badge" style="background:#475569">+${{a.plans.length-3}}</span>`;
  }}

  const koBlock = a.ko ? `<div class="card-summary">🇰🇷 ${{a.ko}}</div>` : '';

  // TTS buttons
  const tts = [];
  if (a.ko) tts.push({{lang:'ko-KR',label:'🇰🇷 KO',text:a.ko}});
  if (a.en) tts.push({{lang:'en-US',label:'🇺🇸 EN',text:a.en}});
  if (a.vi) tts.push({{lang:'vi-VN',label:'🇻🇳 VI',text:a.vi}});
  const ttsBlock = tts.length > 0 ? `<div class="tts-row">${{tts.map(t =>
    `<button class="tts-btn" onclick="speakText(decodeURIComponent('${{encodeURIComponent(t.text)}}'),'${{t.lang}}')">${{t.label}} 🔊</button>`
  ).join('')}}</div>` : '';

  return `<div class="card ${{isMapped ? 'mapped' : ''}}">
    <div class="card-top">
      <span class="card-date">${{a.date || '—'}}</span>
      <a href="${{a.url}}" class="card-src" target="_blank" rel="noopener">${{a.src}} ↗</a>
      ${{badges}}
    </div>
    <a href="${{a.url}}" class="card-title" target="_blank" rel="noopener">${{a.title || '(제목 없음)'}}</a>
    ${{koBlock}}
    ${{ttsBlock}}
  </div>`;
}}

// ── VIEW SWITCH ──
function setView(v) {{
  currentView = v;
  buildSidebar();
  renderFeed();
  document.getElementById('main').scrollTop = 0;
  // Close mobile sidebar
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('overlay').classList.remove('open');
}}

// ── SEARCH ──
document.getElementById('searchInput').addEventListener('input', function() {{
  searchTerm = this.value.trim();
  renderFeed();
}});

// ── MOBILE SIDEBAR ──
function toggleSidebar() {{
  document.getElementById('sidebar').classList.toggle('open');
  document.getElementById('overlay').classList.toggle('open');
}}

// ── TTS ──
function speakText(text, lang) {{
  if (!window.speechSynthesis) {{ alert('TTS 미지원 브라우저'); return; }}
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = lang;
  u.rate = 0.95;
  window.speechSynthesis.speak(u);
}}

// ── EXCEL ──
function downloadAllExcel() {{
  // 서버 생성 Excel (History DB 동일 양식) 우선 사용
  if (WEEKLY_XL) {{ window.open(WEEKLY_XL, '_blank'); return; }}
  if (typeof XLSX === 'undefined') {{ alert('SheetJS 로딩 중... 잠시 후 다시 시도'); return; }}
  const wb = XLSX.utils.book_new();

  // 스타일 헬퍼 — History DB와 동일한 양식
  function styleSheet(ws, rows) {{
    // 열 너비
    ws['!cols'] = [
      {{wch:12}},  // 날짜
      {{wch:25}},  // 플랜
      {{wch:60}},  // 제목
      {{wch:15}},  // 출처
      {{wch:50}},  // URL
      {{wch:80}},  // 요약
    ];
    // 행 높이
    ws['!rows'] = [{{hpt:24}}]; // 헤더 높이
    for (let i = 0; i < rows.length; i++) {{
      ws['!rows'].push({{hpt:32}}); // 데이터 행 높이
    }}
    // 헤더 스타일 (노란 배경)
    const range = XLSX.utils.decode_range(ws['!ref']);
    for (let c = range.s.c; c <= range.e.c; c++) {{
      const addr = XLSX.utils.encode_cell({{r:0, c:c}});
      if (!ws[addr]) continue;
      ws[addr].s = {{
        fill: {{fgColor: {{rgb: "1E40AF"}}}},
        font: {{bold: true, color: {{rgb: "FFFFFF"}}, sz: 11}},
        alignment: {{vertical: "center", wrapText: true}},
        border: {{bottom: {{style: "thin", color: {{rgb: "000000"}}}}}}
      }};
    }}
    // 데이터 행 — 줄무늬
    for (let r = 1; r <= range.e.r; r++) {{
      for (let c = range.s.c; c <= range.e.c; c++) {{
        const addr = XLSX.utils.encode_cell({{r:r, c:c}});
        if (!ws[addr]) continue;
        ws[addr].s = {{
          fill: {{fgColor: {{rgb: r % 2 === 0 ? "F8FAFC" : "FFFFFF"}}}},
          font: {{sz: 10}},
          alignment: {{vertical: "center", wrapText: true}},
          border: {{bottom: {{style: "hair", color: {{rgb: "E2E8F0"}}}}}}
        }};
      }}
    }}
    // 매핑 기사 행 — 노란 하이라이트
    for (let r = 1; r <= range.e.r; r++) {{
      const planCell = XLSX.utils.encode_cell({{r:r, c:1}});
      if (ws[planCell] && ws[planCell].v && ws[planCell].v.length > 0) {{
        for (let c = range.s.c; c <= range.e.c; c++) {{
          const addr = XLSX.utils.encode_cell({{r:r, c:c}});
          if (!ws[addr]) continue;
          ws[addr].s = {{
            ...ws[addr].s,
            fill: {{fgColor: {{rgb: "FFFDE7"}}}}
          }};
        }}
      }}
    }}
  }}

  // 전체 피드 시트
  const allRows = FEED_ARTS.map(a => ({{
    날짜: a.date, 플랜: (a.plans||[]).join(' | '), 제목: a.title, 출처: a.src, URL: a.url, 요약KO: a.ko
  }}));
  const ws1 = XLSX.utils.json_to_sheet(allRows);
  styleSheet(ws1, allRows);
  XLSX.utils.book_append_sheet(wb, ws1, 'All_Articles');

  // 플랜별 시트
  PLAN_ORDER.forEach(pid => {{
    const arts = PLAN_DATA[pid] || [];
    if (arts.length === 0) return;
    const m = PLAN_META[pid] || {{}};
    const rows = arts.map(a => ({{ 날짜:a.date, 제목:a.title, 출처:a.src, URL:a.url, 요약KO:a.ko }}));
    const ws = XLSX.utils.json_to_sheet(rows);
    ws['!cols'] = [{{wch:12}},{{wch:60}},{{wch:15}},{{wch:50}},{{wch:80}}];
    const name = (m.name || pid).replace(/[^a-zA-Z가-힣0-9 ]/g,'').substring(0,28);
    XLSX.utils.book_append_sheet(wb, ws, name);
  }});

  XLSX.writeFile(wb, `Vietnam_Infra_${{new Date().toISOString().slice(0,10)}}.xlsx`);
}}

// ── INIT ──
buildSidebar();
renderFeed();
</script>
</body>
</html>"""

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  ✓ Dashboard v6.0: {output_path} ({len(html)//1024}KB)")

    return html


if __name__ == "__main__":
    try:
        with open("genspark_output.json", encoding="utf-8") as f:
            data = json.load(f)
        articles = data if isinstance(data, list) else data.get("articles", [])
    except:
        articles = []
    generate_html_dashboard(articles, "output/genspark_dashboard.html")
