"""
Email Sender — Vietnam Infrastructure Intelligence Hub v5.0
디자인 철학: 세련된 뉴스레터 스타일
- 첫 화면: 이번 주 매핑 기사 요약 테이블 (플랜명/날짜/제목/출처)
- 상단 단일 버튼 바: 플랜 선택 → Excel/Word/PPT 바로 접근
"""
import os, sys, smtplib, json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, List
from urllib.parse import urlparse
from pathlib import Path
from collections import defaultdict

# ── 플랜 메타데이터 (24개) ─────────────────────────────────────────────────
PLAN_META = {
    "VN-PDP8-RENEWABLE":    {"name": "PDP8 재생에너지",    "icon": "☀️", "color": "#F59E0B", "group": "⚡ PDP8 에너지"},
    "VN-PDP8-LNG":          {"name": "PDP8 LNG",           "icon": "🔥", "color": "#D97706", "group": "⚡ PDP8 에너지"},
    "VN-PDP8-NUCLEAR":      {"name": "PDP8 원자력",         "icon": "⚛️", "color": "#B45309", "group": "⚡ PDP8 에너지"},
    "VN-PDP8-COAL":         {"name": "PDP8 석탄전환",       "icon": "🏭", "color": "#92400E", "group": "⚡ PDP8 에너지"},
    "VN-PDP8-GRID":         {"name": "PDP8 전력망",         "icon": "⚡", "color": "#78350F", "group": "⚡ PDP8 에너지"},
    "VN-PDP8-HYDROGEN":     {"name": "PDP8 수소",           "icon": "💨", "color": "#FBBF24", "group": "⚡ PDP8 에너지"},
    "VN-WAT-RESOURCES":     {"name": "수자원 관리",          "icon": "🌊", "color": "#0EA5E9", "group": "💧 수자원"},
    "VN-WAT-URBAN":         {"name": "도시 상수도",          "icon": "🚰", "color": "#0284C7", "group": "💧 수자원"},
    "VN-WAT-RURAL":         {"name": "농촌 급수",            "icon": "🏡", "color": "#0369A1", "group": "💧 수자원"},
    "HN-URBAN-INFRA":       {"name": "하노이 인프라",        "icon": "🏗️", "color": "#DC2626", "group": "🏙️ 하노이"},
    "HN-URBAN-NORTH":       {"name": "하노이 북부 신도시",   "icon": "🌆", "color": "#B91C1C", "group": "🏙️ 하노이"},
    "HN-URBAN-WEST":        {"name": "하노이 서부 첨단",     "icon": "🔬", "color": "#991B1B", "group": "🏙️ 하노이"},
    "VN-TRAN-2055":         {"name": "교통 마스터플랜 2055", "icon": "🛣️", "color": "#EA580C", "group": "🛣️ 교통·도시"},
    "VN-URB-METRO-2030":    {"name": "도시 메트로 2030",     "icon": "🚇", "color": "#C2410C", "group": "🛣️ 교통·도시"},
    "VN-MEKONG-DELTA-2030": {"name": "메콩 델타 2030",       "icon": "🌾", "color": "#0D9488", "group": "🌏 지역개발"},
    "VN-RED-RIVER-2030":    {"name": "홍강 델타 2030",       "icon": "🏔️", "color": "#BE123C", "group": "🌏 지역개발"},
    "VN-IP-NORTH-2030":     {"name": "북부 산업단지 2030",   "icon": "🏭", "color": "#7C3AED", "group": "🌏 지역개발"},
    "VN-ENV-IND-1894":      {"name": "환경산업 D1894",       "icon": "🌿", "color": "#15803D", "group": "🌿 환경·탄소"},
    "VN-WW-2030":           {"name": "폐수처리 2030",         "icon": "💧", "color": "#0891B2", "group": "🌿 환경·탄소"},
    "VN-SWM-NATIONAL-2030": {"name": "고형폐기물 2030",       "icon": "♻️", "color": "#16A34A", "group": "🌿 환경·탄소"},
    "VN-SC-2030":           {"name": "스마트 시티 2030",      "icon": "🏙️", "color": "#6D28D9", "group": "🌿 환경·탄소"},
    "VN-OG-2030":           {"name": "석유가스 2030",         "icon": "⛽", "color": "#D97706", "group": "🌿 환경·탄소"},
    "VN-EV-2030":           {"name": "전기차 2030",           "icon": "🚗", "color": "#0D9488", "group": "🌿 환경·탄소"},
    "VN-CARBON-2050":       {"name": "탄소중립 2050",         "icon": "🌍", "color": "#166534", "group": "🌿 환경·탄소"},
    # legacy 매핑
    "VN-PWR-PDP8":          {"name": "PDP8 전력",            "icon": "⚡", "color": "#F59E0B", "group": "⚡ PDP8 에너지"},
    "VN-GAS-PDP8":          {"name": "PDP8 가스",            "icon": "🔥", "color": "#D97706", "group": "⚡ PDP8 에너지"},
    "VN-WAT-2050":          {"name": "수자원 2050",           "icon": "💧", "color": "#0EA5E9", "group": "💧 수자원"},
    "VN-WS-NORTH-2030":     {"name": "북부 상수도",           "icon": "🚰", "color": "#0284C7", "group": "💧 수자원"},
    "VN-SW-MEKONG-2030":    {"name": "메콩 폐수",             "icon": "🌊", "color": "#0D9488", "group": "🌏 지역개발"},
    "VN-SWM-NATIONAL-2030": {"name": "고형폐기물",            "icon": "♻️", "color": "#16A34A", "group": "🌿 환경·탄소"},
    "VN-GRID-SMART":        {"name": "스마트 그리드",         "icon": "⚡", "color": "#78350F", "group": "⚡ PDP8 에너지"},
    "VN-COAL-RETIRE":       {"name": "석탄 폐지",             "icon": "🏭", "color": "#92400E", "group": "⚡ PDP8 에너지"},
    "VN-REN-NPP-2050":      {"name": "원자력 2050",           "icon": "⚛️", "color": "#B45309", "group": "⚡ PDP8 에너지"},
    "VN-LNG-HUB":           {"name": "LNG 허브",              "icon": "🛢️", "color": "#D97706", "group": "⚡ PDP8 에너지"},
}

# 보고서 키 매핑
PLAN_TO_REPORT_KEY = {
    "VN-PDP8-RENEWABLE": "PDP8-INTEGRATED", "VN-PDP8-LNG": "PDP8-INTEGRATED",
    "VN-PDP8-NUCLEAR":   "PDP8-INTEGRATED", "VN-PDP8-COAL": "PDP8-INTEGRATED",
    "VN-PDP8-GRID":      "PDP8-INTEGRATED", "VN-PDP8-HYDROGEN": "PDP8-INTEGRATED",
    "VN-WAT-RESOURCES":  "WATER-INTEGRATED","VN-WAT-URBAN": "WATER-INTEGRATED",
    "VN-WAT-RURAL":      "WATER-INTEGRATED",
    "HN-URBAN-INFRA":    "HANOI-INTEGRATED","HN-URBAN-NORTH": "HANOI-INTEGRATED",
    "HN-URBAN-WEST":     "HANOI-INTEGRATED",
    # legacy
    "VN-PWR-PDP8": "PDP8-INTEGRATED", "VN-GAS-PDP8": "PDP8-INTEGRATED",
    "VN-GRID-SMART": "PDP8-INTEGRATED", "VN-COAL-RETIRE": "PDP8-INTEGRATED",
    "VN-REN-NPP-2050": "PDP8-INTEGRATED", "VN-LNG-HUB": "PDP8-INTEGRATED",
    "VN-WAT-2050": "WATER-INTEGRATED", "VN-WS-NORTH-2030": "WATER-INTEGRATED",
    "VN-SW-MEKONG-2030": "VN-MEKONG-DELTA-2030",
}
# 개별 플랜은 ID가 곧 report key
for pid in ["VN-TRAN-2055","VN-URB-METRO-2030","VN-MEKONG-DELTA-2030","VN-RED-RIVER-2030",
            "VN-IP-NORTH-2030","VN-ENV-IND-1894","VN-WW-2030","VN-SWM-NATIONAL-2030",
            "VN-SC-2030","VN-OG-2030","VN-EV-2030","VN-CARBON-2050"]:
    PLAN_TO_REPORT_KEY[pid] = pid


def _domain(url: str) -> str:
    try:
        d = urlparse(url).netloc.replace("www.", "").replace("m.", "")
        return d.split(".")[0].capitalize() if d else "—"
    except:
        return "—"


def _normalise_date(raw: str) -> str:
    """다양한 날짜 포맷 → YYYY-MM-DD 또는 원본 유지"""
    if not raw:
        return "—"
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%d %b %Y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except:
            pass
    # "N days ago" 등
    if "ago" in raw.lower() or "day" in raw.lower():
        return datetime.now().strftime("%Y-%m-%d")
    return raw[:10]


def _is_vi(text: str) -> bool:
    vi = set("ăâêôơưđáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ")
    return any(c.lower() in vi for c in (text or ""))


def _best_title(a: dict) -> str:
    t = a.get("title") or ""
    if not _is_vi(t):
        return t[:110]
    en = a.get("title_en") or a.get("summary_en") or ""
    if en and not _is_vi(en):
        return f"[EN] {en[:104]}"
    return t[:110]


class EmailSender:
    def __init__(self, username: str, password: str, recipient: str,
                 smtp_server: str = "smtp.gmail.com", smtp_port: int = 587):
        self.username    = username
        self.password    = password
        self.recipient   = recipient
        self.smtp_server = smtp_server
        self.smtp_port   = smtp_port

    # ─────────────────────────────────────────────────────────────────────────
    # PUBLIC: create_kpi_email
    # ─────────────────────────────────────────────────────────────────────────
    def create_kpi_email(self, stats: Dict, articles: List[Dict] = None) -> str:
        """v5.1 — Gmail 최적화 뉴스레터
        • 첫 화면: 헤더 + KPI 4개 + 보고서 버튼 바
        • 본문: 이번 주 매핑 기사 테이블 (날짜/플랜/제목/출처)
        """
        import ast, json as _json
        from pathlib import Path

        now      = datetime.now()
        week     = now.isocalendar()[1]
        week_str = f"W{week:02d} · {now.strftime('%Y-%m-%d')}"
        now_kst  = now.strftime("%Y년 %m월 %d일 %H:%M KST")
        total    = stats.get("total_articles", 0)
        qc_pass  = stats.get("qc_passed", 0)
        matched  = stats.get("plan_matched", 0)
        rate     = stats.get("qc_rate", 0)
        dash_url = stats.get("dashboard_url", "https://hms4792.github.io/vietnam-infra-news/genspark/")
        gh_url   = stats.get("github_url", "https://github.com/hms4792/vietnam-infra-news")
        matched_pct = round(matched / total * 100) if total else 0

        # 보고서 URL
        report_urls: dict = {}
        try:
            p = Path(__file__).parent.parent / "config/report_urls.json"
            if p.exists():
                report_urls = _json.loads(p.read_text())
        except: pass
        excel_db_url = report_urls.get("_excel_db", "")

        # legacy alias
        _ALIAS = {
            "VN-PWR-PDP8":"VN-PDP8-RENEWABLE","VN-GAS-PDP8":"VN-PDP8-LNG",
            "VN-GRID-SMART":"VN-PDP8-GRID","VN-COAL-RETIRE":"VN-PDP8-COAL",
            "VN-REN-NPP-2050":"VN-PDP8-NUCLEAR","VN-LNG-HUB":"VN-PDP8-HYDROGEN",
            "VN-WAT-2050":"VN-WAT-RESOURCES","VN-WS-NORTH-2030":"VN-WAT-URBAN",
            "VN-SW-MEKONG-2030":"VN-MEKONG-DELTA-2030",
        }

        # 매핑 기사 수집 + 최신순 정렬
        arts = articles or []
        seen_urls: set = set()
        mapped_arts = []
        for a in arts:
            plans = a.get("matched_plans") or []
            if not plans: continue
            url = a.get("url", "#")
            if url in seen_urls: continue
            seen_urls.add(url)
            if isinstance(plans, str):
                try: plans = ast.literal_eval(plans)
                except: plans = [plans]
            plans = list(dict.fromkeys(_ALIAS.get(p, p) for p in plans))
            mapped_arts.append({**a, "_plans_canonical": plans})

        def _skey(a):
            d = _normalise_date(a.get("published_date", ""))
            return d if d and d != "—" else "0000-00-00"
        mapped_arts.sort(key=_skey, reverse=True)

        # ── 보고서 버튼 바 ───────────────────────────────────────────────
        REPORT_DEFS = [
            ("PDP8-INTEGRATED",    "⚡ PDP8 에너지",  "#B45309"),
            ("WATER-INTEGRATED",   "💧 수자원",        "#0369A1"),
            ("HANOI-INTEGRATED",   "🏙️ 하노이",        "#B91C1C"),
            ("VN-TRAN-2055",       "🛣️ 교통 2055",     "#EA580C"),
            ("VN-URB-METRO-2030",  "🚇 메트로",        "#C2410C"),
            ("VN-MEKONG-DELTA-2030","🌾 메콩 델타",    "#0D9488"),
            ("VN-RED-RIVER-2030",  "🏔️ 홍강",          "#BE123C"),
            ("VN-IP-NORTH-2030",   "🏭 산업단지",      "#7C3AED"),
            ("VN-ENV-IND-1894",    "🌿 D1894",          "#15803D"),
            ("VN-WW-2030",         "💧 폐수",           "#0891B2"),
            ("VN-SWM-NATIONAL-2030","♻️ 고형폐기물",   "#16A34A"),
            ("VN-SC-2030",         "🏙️ 스마트시티",    "#6D28D9"),
            ("VN-OG-2030",         "⛽ 석유가스",       "#D97706"),
            ("VN-EV-2030",         "🚗 전기차",         "#0D9488"),
            ("VN-CARBON-2050",     "🌍 탄소중립",       "#166534"),
        ]
        rpt_cells = ""
        for rk, lbl, color in REPORT_DEFS:
            ru = report_urls.get(rk, {})
            if not isinstance(ru, dict): continue
            word_url = ru.get("word", "")
            ppt_url  = ru.get("ppt", "")
            if not word_url and not ppt_url: continue
            sub_btns = ""
            if word_url:
                sub_btns += f'<a href="{word_url}" style="color:#fff;background:rgba(0,0,0,.2);border-radius:3px;padding:1px 6px;font-size:9px;font-weight:800;text-decoration:none;margin-left:3px">Word</a>'
            if ppt_url:
                sub_btns += f'<a href="{ppt_url}"  style="color:#fff;background:rgba(0,0,0,.2);border-radius:3px;padding:1px 6px;font-size:9px;font-weight:800;text-decoration:none;margin-left:3px">PPT</a>'
            rpt_cells += f'''<td style="padding:2px 3px">
              <span style="display:inline-flex;align-items:center;background:{color};border-radius:6px;padding:5px 8px;white-space:nowrap">
                <span style="color:#fff;font-size:10px;font-weight:700">{lbl}</span>{sub_btns}
              </span>
            </td>'''

        # ── 기사 테이블 행 ────────────────────────────────────────────────
        art_rows = ""
        for i, a in enumerate(mapped_arts):
            plans    = a["_plans_canonical"]
            url      = a.get("url", "#")
            title    = _best_title(a)[:95]
            date     = _normalise_date(a.get("published_date", ""))
            src      = _domain(url)
            bg       = "#FFFFFF" if i % 2 == 0 else "#F8FAFC"

            # 플랜 배지 (최대 2개)
            badges = ""
            for pid in plans[:2]:
                m = PLAN_META.get(pid, {})
                c = m.get("color", "#64748B")
                n = m.get("name", pid)
                ic= m.get("icon", "")
                badges += f'<span style="display:inline-block;background:{c};color:#fff;font-size:8px;font-weight:800;padding:1px 6px;border-radius:8px;margin:0 2px 2px 0;white-space:nowrap">{ic} {n}</span>'
            if len(plans) > 2:
                badges += f'<span style="display:inline-block;background:#94A3B8;color:#fff;font-size:8px;padding:1px 5px;border-radius:8px">+{len(plans)-2}</span>'

            art_rows += f'''
            <tr style="background:{bg}">
              <td style="padding:10px 12px;border-bottom:1px solid #EEF2F7;
                         font-size:11px;color:#64748B;white-space:nowrap;
                         vertical-align:top;width:82px">
                📅 {date}
              </td>
              <td style="padding:10px 12px;border-bottom:1px solid #EEF2F7;vertical-align:top">
                <div style="margin-bottom:4px">{badges}</div>
                <a href="{url}" style="color:#1E293B;font-size:12px;font-weight:700;
                   line-height:1.4;text-decoration:none">{title}</a>
              </td>
              <td style="padding:10px 12px;border-bottom:1px solid #EEF2F7;
                         text-align:right;vertical-align:top;width:80px">
                <a href="{url}" style="color:#3B82F6;font-size:10px;
                   font-weight:700;text-decoration:none;white-space:nowrap">{src} ↗</a>
              </td>
            </tr>'''

        if not art_rows:
            art_rows = '<tr><td colspan="3" style="padding:32px;text-align:center;color:#94A3B8;font-size:13px">이번 주 매핑된 기사가 없습니다</td></tr>'

        qc_ok = rate >= 95
        badge_bg = "#DCFCE7" if qc_ok else "#FEF3C7"
        badge_c  = "#166534" if qc_ok else "#92400E"
        badge_t  = "✅ 정상" if qc_ok else "⚠️ 점검"

        html = f"""<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vietnam Infra Intelligence {week_str}</title>
</head>
<body style="margin:0;padding:0;background:#EEF2F7;font-family:'Segoe UI',Arial,sans-serif">

<!-- OUTER WRAPPER -->
<table width="100%" cellpadding="0" cellspacing="0"
       style="background:#EEF2F7;padding:28px 0">
<tr><td align="center">
<table width="660" cellpadding="0" cellspacing="0"
       style="max-width:660px;width:100%;background:#fff;
              border-radius:14px;box-shadow:0 4px 24px rgba(0,0,0,.10)">

  <!-- ── HEADER ───────────────────────────────────────────────── -->
  <tr><td style="background:linear-gradient(135deg,#0F172A 0%,#1D4ED8 100%);
                 border-radius:14px 14px 0 0;padding:30px 32px 24px">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td>
        <div style="color:#93C5FD;font-size:9px;font-weight:800;letter-spacing:3px;
                    text-transform:uppercase;margin-bottom:7px">Weekly Intelligence Report</div>
        <div style="color:#fff;font-size:20px;font-weight:900;line-height:1.2;margin-bottom:5px">
          🇻🇳 Vietnam Infrastructure Hub</div>
        <div style="color:#BFDBFE;font-size:11px">{week_str} &nbsp;·&nbsp; {now_kst}</div>
      </td>
      <td style="text-align:right;vertical-align:middle">
        <div style="background:rgba(255,255,255,.12);border-radius:10px;
                    padding:12px 18px;display:inline-block;text-align:center">
          <div style="color:#FCD34D;font-size:28px;font-weight:900;line-height:1">{len(mapped_arts)}</div>
          <div style="color:#BFDBFE;font-size:9px;margin-top:3px;font-weight:700">매핑 기사</div>
        </div>
      </td>
    </tr></table>
  </td></tr>

  <!-- ── KPI 4개 ───────────────────────────────────────────────── -->
  <tr><td style="background:#1E293B;padding:0">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td width="25%" style="padding:16px 0;text-align:center;
                              border-right:1px solid rgba(255,255,255,.08)">
        <div style="color:#fff;font-size:22px;font-weight:900">{total}</div>
        <div style="color:#94A3B8;font-size:9px;margin-top:3px;font-weight:600">수집 기사</div>
      </td>
      <td width="25%" style="padding:16px 0;text-align:center;
                              border-right:1px solid rgba(255,255,255,.08)">
        <div style="color:#4ADE80;font-size:22px;font-weight:900">{matched}</div>
        <div style="color:#94A3B8;font-size:9px;margin-top:3px;font-weight:600">플랜 매핑</div>
      </td>
      <td width="25%" style="padding:16px 0;text-align:center;
                              border-right:1px solid rgba(255,255,255,.08)">
        <div style="color:#FCD34D;font-size:22px;font-weight:900">{matched_pct}%</div>
        <div style="color:#94A3B8;font-size:9px;margin-top:3px;font-weight:600">매핑률</div>
      </td>
      <td width="25%" style="padding:16px 0;text-align:center">
        <div style="display:inline-block;background:{badge_bg};color:{badge_c};
                    font-size:11px;font-weight:800;padding:4px 10px;border-radius:8px">
          {badge_t}</div>
        <div style="color:#94A3B8;font-size:9px;margin-top:5px;font-weight:600">QC {rate}%</div>
      </td>
    </tr></table>
  </td></tr>

  <!-- ── 보고서 버튼 바 ─────────────────────────────────────────── -->
  <tr><td style="background:#F8FAFC;border-bottom:2px solid #EEF2F7;padding:14px 20px">
    <div style="color:#64748B;font-size:9px;font-weight:800;letter-spacing:1.5px;
                text-transform:uppercase;margin-bottom:10px">📁 보고서 다운로드 — Word · PPT</div>
    <div style="overflow-x:auto">
    <table cellpadding="0" cellspacing="0"><tr>
      {rpt_cells if rpt_cells else '<td><span style="color:#94A3B8;font-size:11px">5월 2일 첫 자동 실행 후 보고서 링크가 등록됩니다</span></td>'}
    </tr></table>
    </div>
    <!-- 버튼 -->
    <table cellpadding="0" cellspacing="0" style="margin-top:12px"><tr>
      <td style="padding-right:8px">
        <a href="{dash_url}" style="display:inline-block;background:#1D4ED8;color:#fff;
           padding:8px 16px;border-radius:7px;font-size:11px;font-weight:700;
           text-decoration:none">📊 대시보드</a>
      </td>
      {"<td style=\"padding-right:8px\"><a href=\"" + excel_db_url + "\" style=\"display:inline-block;background:#7C3AED;color:#fff;padding:8px 16px;border-radius:7px;font-size:11px;font-weight:700;text-decoration:none\">🗄️ History DB Excel</a></td>" if excel_db_url else ""}
      <td>
        <a href="{gh_url}" style="display:inline-block;background:#F1F5F9;color:#475569;
           padding:8px 14px;border-radius:7px;font-size:11px;font-weight:700;
           text-decoration:none;border:1px solid #E2E8F0">⚙️ GitHub</a>
      </td>
    </tr></table>
  </td></tr>

  <!-- ── 기사 섹션 헤더 ─────────────────────────────────────────── -->
  <tr><td style="padding:18px 20px 8px">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td>
        <span style="font-size:13px;font-weight:800;color:#0F172A">
          이번 주 마스터플랜 매핑 기사</span>
        <span style="font-size:10px;color:#94A3B8;margin-left:8px">
          최신순 · 원문 링크 포함</span>
      </td>
      <td style="text-align:right">
        <span style="background:#EFF6FF;color:#1D4ED8;font-size:10px;
               font-weight:800;padding:3px 10px;border-radius:8px">
          총 {len(mapped_arts)}건</span>
      </td>
    </tr></table>
  </td></tr>

  <!-- ── 기사 테이블 ────────────────────────────────────────────── -->
  <tr><td style="padding:0 0 8px">
    <!-- 컬럼 헤더 -->
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr style="background:#F8FAFC">
        <td style="padding:7px 12px;font-size:9px;font-weight:800;color:#94A3B8;
                   letter-spacing:1px;text-transform:uppercase;width:82px;
                   border-bottom:2px solid #EEF2F7">날짜</td>
        <td style="padding:7px 12px;font-size:9px;font-weight:800;color:#94A3B8;
                   letter-spacing:1px;text-transform:uppercase;
                   border-bottom:2px solid #EEF2F7">플랜 &amp; 기사 제목</td>
        <td style="padding:7px 12px;font-size:9px;font-weight:800;color:#94A3B8;
                   letter-spacing:1px;text-transform:uppercase;width:80px;
                   text-align:right;border-bottom:2px solid #EEF2F7">출처</td>
      </tr>
      {art_rows}
    </table>
  </td></tr>

  <!-- ── FOOTER ────────────────────────────────────────────────── -->
  <tr><td style="background:#0F172A;border-radius:0 0 14px 14px;padding:16px 24px">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td>
        <div style="color:#475569;font-size:10px;line-height:1.7">
          Vietnam Infrastructure Intelligence Hub &nbsp;·&nbsp; Pipeline v5.0<br>
          매주 토요일 23:30 KST 자동 실행 · 24개 마스터플랜 추적
        </div>
      </td>
      <td style="text-align:right">
        <a href="{dash_url}" style="color:#60A5FA;font-size:11px;
           text-decoration:none;font-weight:700">대시보드 →</a>
      </td>
    </tr></table>
  </td></tr>

</table><!-- /inner -->
</td></tr>
</table><!-- /outer -->
</body>
</html>"""
        return html

    def send_email(self, subject: str, html_body: str):
        # 1차: SMTP 시도
        try:
            msg = MIMEMultipart("alternative")
            msg["From"]    = self.username
            msg["To"]      = self.recipient
            msg["Subject"] = subject
            msg.attach(MIMEText(html_body, "html"))
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as s:
                s.starttls()
                s.login(self.username, self.password)
                s.send_message(msg)
            print(f"✓ Email sent via SMTP to {self.recipient}")
            return
        except Exception as e:
            print(f"⚠ SMTP failed: {e}")
            print("  → gsk vm_email 폴백 시도...")

        # 2차: gsk vm_email 폴백
        try:
            import subprocess, os
            vm_name = os.environ.get("OPENCLAW_VM_NAME", "")
            # HTML을 임시 파일로 저장 후 -b @file 로 전달
            tmp = "/tmp/_email_body.html"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(html_body)
            cmd = [
                "gsk", "vm_email", "send", self.recipient,
                "-s", subject,
                "-b", html_body[:4000],  # gsk 길이 제한
            ]
            if vm_name:
                cmd += ["-f", vm_name]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and "ok" in result.stdout.lower():
                print(f"✓ Email sent via gsk vm_email to {self.recipient}")
            else:
                print(f"✗ gsk vm_email also failed: {result.stderr or result.stdout}")
                raise RuntimeError(f"Both SMTP and gsk vm_email failed")
        except Exception as e2:
            print(f"✗ All email methods failed: {e2}")
            raise
