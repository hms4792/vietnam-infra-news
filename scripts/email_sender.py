"""
Email Sender — Vietnam Infrastructure Intelligence Hub v6.0
──────────────────────────────────────────────────────────────
모바일 퍼스트 · Bloomberg/Morning Brew 스타일 뉴스레터
- 첫 화면: 매핑 기사 테이블 ONLY (플랜 배지 + 날짜 + 제목 + 출처)
- 보고서: 대시보드 링크 1개 (드릴다운)
- Gmail 호환: inline style only, table layout, no CSS class
"""
import os, sys, smtplib, json, ast
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, List
from urllib.parse import urlparse
from pathlib import Path
from collections import defaultdict

# ── 플랜 메타 ────────────────────────────────────────────────────────────
PLAN_META = {
    "VN-PDP8-RENEWABLE":    {"name": "PDP8 재생에너지",  "color": "#D97706", "group": "⚡ PDP8"},
    "VN-PDP8-LNG":          {"name": "PDP8 LNG",         "color": "#D97706", "group": "⚡ PDP8"},
    "VN-PDP8-NUCLEAR":      {"name": "PDP8 원자력",       "color": "#D97706", "group": "⚡ PDP8"},
    "VN-PDP8-COAL":         {"name": "PDP8 석탄전환",     "color": "#D97706", "group": "⚡ PDP8"},
    "VN-PDP8-GRID":         {"name": "PDP8 전력망",       "color": "#D97706", "group": "⚡ PDP8"},
    "VN-PDP8-HYDROGEN":     {"name": "PDP8 수소",         "color": "#D97706", "group": "⚡ PDP8"},
    "VN-PWR-PDP8":          {"name": "PDP8 전력",         "color": "#D97706", "group": "⚡ PDP8"},
    "VN-PWR-PDP8-RENEWABLE":{"name": "PDP8 재생에너지",  "color": "#D97706", "group": "⚡ PDP8"},
    "VN-PWR-PDP8-LNG":     {"name": "PDP8 LNG",         "color": "#D97706", "group": "⚡ PDP8"},
    "VN-PWR-PDP8-NUCLEAR":  {"name": "PDP8 원자력·수소", "color": "#D97706", "group": "⚡ PDP8"},
    "VN-PWR-PDP8-COAL":    {"name": "PDP8 석탄전환",     "color": "#D97706", "group": "⚡ PDP8"},
    "VN-PWR-PDP8-GRID":    {"name": "PDP8 전력망",       "color": "#D97706", "group": "⚡ PDP8"},
    "VN-WAT-RESOURCES":     {"name": "수자원 관리",       "color": "#0284C7", "group": "💧 수자원"},
    "VN-WAT-URBAN":         {"name": "도시 상수도",       "color": "#0284C7", "group": "💧 수자원"},
    "VN-WAT-RURAL":         {"name": "농촌 급수",         "color": "#0284C7", "group": "💧 수자원"},
    "HN-URBAN-INFRA":       {"name": "하노이 인프라",     "color": "#DC2626", "group": "🏙️ 하노이"},
    "HN-URBAN-NORTH":       {"name": "하노이 북부",       "color": "#DC2626", "group": "🏙️ 하노이"},
    "HN-URBAN-WEST":        {"name": "하노이 서부",       "color": "#DC2626", "group": "🏙️ 하노이"},
    "VN-TRAN-2055":         {"name": "교통 2055",         "color": "#EA580C", "group": "🛣️ 교통"},
    "VN-URB-METRO-2030":    {"name": "메트로 2030",       "color": "#C2410C", "group": "🛣️ 교통"},
    "VN-MEKONG-DELTA-2030": {"name": "메콩 델타",         "color": "#0D9488", "group": "🌏 지역"},
    "VN-RED-RIVER-2030":    {"name": "홍강 델타",         "color": "#BE123C", "group": "🌏 지역"},
    "VN-IP-NORTH-2030":     {"name": "북부 산업단지",     "color": "#7C3AED", "group": "🌏 지역"},
    "VN-ENV-IND-1894":      {"name": "환경산업 D1894",    "color": "#15803D", "group": "🌿 환경"},
    "VN-WW-2030":           {"name": "폐수처리 2030",     "color": "#0891B2", "group": "🌿 환경"},
    "VN-SWM-NATIONAL-2030": {"name": "고형폐기물",        "color": "#16A34A", "group": "🌿 환경"},
    "VN-SC-2030":           {"name": "스마트시티",         "color": "#6D28D9", "group": "🌿 환경"},
    "VN-OG-2030":           {"name": "석유가스 2030",      "color": "#D97706", "group": "🌿 환경"},
    "VN-EV-2030":           {"name": "전기차 2030",        "color": "#0D9488", "group": "🌿 환경"},
    "VN-CARBON-2050":       {"name": "탄소중립 2050",      "color": "#166534", "group": "🌿 환경"},
}

# Legacy alias
_ALIAS = {
    "VN-PWR-PDP8":"VN-PWR-PDP8","VN-GAS-PDP8":"VN-PWR-PDP8-LNG",
    "VN-GRID-SMART":"VN-PWR-PDP8-GRID","VN-COAL-RETIRE":"VN-PWR-PDP8-COAL",
    "VN-REN-NPP-2050":"VN-PWR-PDP8-NUCLEAR","VN-LNG-HUB":"VN-PWR-PDP8-LNG",
    "VN-WAT-2050":"VN-WAT-RESOURCES","VN-WS-NORTH-2030":"VN-WAT-URBAN",
    "VN-SW-MEKONG-2030":"VN-MEKONG-DELTA-2030",
    "VN-PDP8-RENEWABLE":"VN-PWR-PDP8-RENEWABLE","VN-PDP8-LNG":"VN-PWR-PDP8-LNG",
    "VN-PDP8-NUCLEAR":"VN-PWR-PDP8-NUCLEAR","VN-PDP8-COAL":"VN-PWR-PDP8-COAL",
    "VN-PDP8-GRID":"VN-PWR-PDP8-GRID","VN-PDP8-HYDROGEN":"VN-PWR-PDP8-NUCLEAR",
}

# Report key mapping
PLAN_TO_REPORT_KEY = {
    "VN-PWR-PDP8":"PDP8-INTEGRATED",
    "VN-PWR-PDP8-RENEWABLE":"PDP8-INTEGRATED","VN-PWR-PDP8-LNG":"PDP8-INTEGRATED",
    "VN-PWR-PDP8-NUCLEAR":"PDP8-INTEGRATED","VN-PWR-PDP8-COAL":"PDP8-INTEGRATED",
    "VN-PWR-PDP8-GRID":"PDP8-INTEGRATED",
    "VN-WAT-RESOURCES":"WATER-INTEGRATED","VN-WAT-URBAN":"WATER-INTEGRATED",
    "VN-WAT-RURAL":"WATER-INTEGRATED",
    "HN-URBAN-INFRA":"HANOI-INTEGRATED","HN-URBAN-NORTH":"HANOI-INTEGRATED",
    "HN-URBAN-WEST":"HANOI-INTEGRATED",
}
for _pid in ["VN-TRAN-2055","VN-URB-METRO-2030","VN-MEKONG-DELTA-2030","VN-RED-RIVER-2030",
             "VN-IP-NORTH-2030","VN-ENV-IND-1894","VN-WW-2030","VN-SWM-NATIONAL-2030",
             "VN-SC-2030","VN-OG-2030","VN-EV-2030","VN-CARBON-2050"]:
    PLAN_TO_REPORT_KEY[_pid] = _pid

# Group border colors
_GROUP_BORDER = {
    "⚡ PDP8": "#F59E0B", "💧 수자원": "#0EA5E9", "🏙️ 하노이": "#EF4444",
    "🛣️ 교통": "#F97316", "🌏 지역": "#14B8A6", "🌿 환경": "#22C55E",
}


def _domain(url: str) -> str:
    try:
        d = urlparse(url).netloc.replace("www.", "").replace("m.", "")
        return d.split(".")[0].capitalize() if d else "—"
    except:
        return "—"


def _normalise_date(raw: str) -> str:
    if not raw: return "—"
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%d %b %Y"):
        try: return datetime.strptime(raw, fmt).strftime("%m/%d")
        except: pass
    if "ago" in raw.lower():
        return datetime.now().strftime("%m/%d")
    return raw[:5]


def _normalise_date_full(raw: str) -> str:
    if not raw: return "—"
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%B %d, %Y", "%d %b %Y"):
        try: return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except: pass
    return raw[:10]


def _is_vi(text: str) -> bool:
    vi = set("ăâêôơưđáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ")
    return any(c.lower() in vi for c in (text or ""))


def _best_title(a: dict) -> str:
    t = a.get("title") or ""
    if not _is_vi(t): return t[:100]
    en = a.get("title_en") or a.get("summary_en") or ""
    if en and not _is_vi(en): return en[:100]
    return t[:100]


def _resolve_plans(plans_raw) -> list:
    if isinstance(plans_raw, str):
        try: plans_raw = ast.literal_eval(plans_raw)
        except: plans_raw = [plans_raw]
    return list(dict.fromkeys(_ALIAS.get(p, p) for p in (plans_raw or [])))


class EmailSender:
    def __init__(self, username: str, password: str, recipient: str,
                 smtp_server: str = "smtp.gmail.com", smtp_port: int = 587):
        self.username    = username
        self.password    = password
        self.recipient   = recipient
        self.smtp_server = smtp_server
        self.smtp_port   = smtp_port

    def create_kpi_email(self, stats: Dict, articles: List[Dict] = None) -> str:
        """v6.0 — Mobile-first professional newsletter"""
        now      = datetime.now()
        week     = now.isocalendar()[1]
        date_str = now.strftime("%Y.%m.%d")
        total    = stats.get("total_articles", 0)
        matched  = stats.get("plan_matched", 0)
        rate     = stats.get("qc_rate", 0)
        dash_url = stats.get("dashboard_url",
                             "https://hms4792.github.io/vietnam-infra-news/genspark/")
        gh_url   = stats.get("github_url",
                             "https://github.com/hms4792/vietnam-infra-news")

        # Report URLs
        report_urls: dict = {}
        try:
            p = Path(__file__).parent.parent / "config/report_urls.json"
            if p.exists(): report_urls = json.loads(p.read_text())
        except: pass
        excel_db_url = report_urls.get("_excel_db", "")

        # Collect mapped articles
        arts = articles or []
        seen: set = set()
        mapped = []
        for a in arts:
            plans = _resolve_plans(a.get("matched_plans"))
            if not plans: continue
            url = a.get("url", "#")
            if url in seen: continue
            seen.add(url)
            mapped.append({**a, "_plans": plans})
        mapped.sort(key=lambda a: _normalise_date_full(a.get("published_date", "")), reverse=True)

        # Group articles by plan group for visual sectioning
        plan_groups: dict = defaultdict(list)
        for a in mapped:
            first_plan = a["_plans"][0]
            m = PLAN_META.get(first_plan, {})
            group = m.get("group", "기타")
            plan_groups[group].append(a)

        # ── Article rows ──────────────────────────────────────────────
        art_rows = ""
        for i, a in enumerate(mapped):
            plans = a["_plans"]
            url   = a.get("url", "#")
            title = _best_title(a)
            date  = _normalise_date(a.get("published_date", ""))
            src   = _domain(url)
            first_plan = plans[0]
            m = PLAN_META.get(first_plan, {})
            border_color = _GROUP_BORDER.get(m.get("group", ""), "#64748B")
            plan_name = m.get("name", first_plan)
            plan_color = m.get("color", "#64748B")

            # Extra plans badge
            extra = ""
            if len(plans) > 1:
                extra = f' <span style="color:#94A3B8;font-size:11px">+{len(plans)-1}</span>'

            bg = "#FFFFFF" if i % 2 == 0 else "#F9FAFB"

            art_rows += f'''<tr style="background:{bg}">
  <td style="padding:14px 16px;border-bottom:1px solid #F1F5F9;border-left:4px solid {border_color};vertical-align:top;width:1%">
    <span style="display:inline-block;background:{plan_color};color:#fff;font-size:11px;font-weight:700;padding:2px 8px;border-radius:4px;white-space:nowrap;line-height:1.4">{plan_name}</span>{extra}
  </td>
  <td style="padding:14px 12px;border-bottom:1px solid #F1F5F9;vertical-align:top">
    <a href="{url}" style="color:#111827;font-size:14px;font-weight:600;text-decoration:none;line-height:1.5;display:block">{title}</a>
    <span style="color:#9CA3AF;font-size:12px">{date} · {src}</span>
  </td>
</tr>'''

        if not art_rows:
            art_rows = '''<tr><td colspan="2" style="padding:40px 16px;text-align:center;color:#9CA3AF;font-size:14px">이번 주 매핑된 기사가 없습니다</td></tr>'''

        # ── Build HTML ────────────────────────────────────────────────
        html = f'''<!DOCTYPE html>
<html lang="ko">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#F3F4F6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;-webkit-text-size-adjust:100%">

<table width="100%" cellpadding="0" cellspacing="0" style="background:#F3F4F6;padding:16px 8px">
<tr><td align="center">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#FFFFFF;border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08)">

  <!-- ── HEADER ── -->
  <tr><td style="background:#0F172A;padding:24px 20px 20px">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td style="vertical-align:top">
        <div style="color:#FFFFFF;font-size:18px;font-weight:800;line-height:1.3;margin-bottom:4px">🇻🇳 Vietnam Infra Weekly</div>
        <div style="color:#94A3B8;font-size:13px;font-weight:500">W{week:02d} · {date_str}</div>
      </td>
      <td style="text-align:right;vertical-align:top">
        <div style="color:#FCD34D;font-size:24px;font-weight:900;line-height:1">{matched}</div>
        <div style="color:#94A3B8;font-size:11px;margin-top:2px">신규 매핑</div>
      </td>
    </tr></table>
  </td></tr>

  <!-- ── STATS BAR ── -->
  <tr><td style="background:#1E293B;padding:12px 20px">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td style="color:#CBD5E1;font-size:13px">
        수집 <span style="color:#FFFFFF;font-weight:700">{total}</span>건 &nbsp;·&nbsp;
        매핑 <span style="color:#FCD34D;font-weight:700">{matched}</span>건 &nbsp;·&nbsp;
        QC <span style="color:#4ADE80;font-weight:700">{rate}%</span>
      </td>
    </tr></table>
  </td></tr>

  <!-- ── SECTION LABEL ── -->
  <tr><td style="padding:20px 20px 10px">
    <div style="font-size:15px;font-weight:800;color:#111827;margin-bottom:2px">📌 이번 주 마스터플랜 매핑 기사</div>
    <div style="font-size:12px;color:#9CA3AF">최신순 · 제목 클릭 시 원문 이동</div>
  </td></tr>

  <!-- ── ARTICLE TABLE ── -->
  <tr><td style="padding:0 12px">
    <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">
      {art_rows}
    </table>
  </td></tr>

  <!-- ── ACTION BUTTONS ── -->
  <tr><td style="padding:24px 20px 16px">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td style="text-align:center;padding-bottom:8px">
        <a href="{dash_url}" style="display:inline-block;background:#2563EB;color:#FFFFFF;font-size:14px;font-weight:700;padding:12px 28px;border-radius:8px;text-decoration:none">📊 대시보드에서 보고서 열기</a>
      </td>
    </tr>
    <tr><td style="text-align:center;padding-top:8px">
      {f'<a href="{excel_db_url}" style="color:#6B7280;font-size:12px;font-weight:600;text-decoration:none;margin-right:16px">🗄️ History DB</a>' if excel_db_url else ''}
      <a href="{gh_url}" style="color:#6B7280;font-size:12px;font-weight:600;text-decoration:none">⚙️ GitHub</a>
    </td></tr></table>
  </td></tr>

  <!-- ── FOOTER ── -->
  <tr><td style="background:#F9FAFB;padding:16px 20px;border-top:1px solid #F1F5F9">
    <div style="color:#9CA3AF;font-size:11px;text-align:center;line-height:1.6">
      Vietnam Infrastructure Intelligence Hub · Pipeline v6.0 · 매주 토 23:30 KST 자동 실행
    </div>
  </td></tr>

</table>
</td></tr></table>
</body></html>'''
        return html

    def send_email(self, subject: str, html_body: str):
        # 1st: SMTP
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
            print("  → gsk vm_email fallback...")

        # 2nd: gsk vm_email
        try:
            import subprocess
            vm_name = os.environ.get("OPENCLAW_VM_NAME", "")
            cmd = ["gsk", "vm_email", "send", self.recipient,
                   "-s", subject, "-b", html_body[:4000]]
            if vm_name: cmd += ["-f", vm_name]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and "ok" in result.stdout.lower():
                print(f"✓ Email sent via gsk vm_email to {self.recipient}")
            else:
                raise RuntimeError(f"gsk vm_email failed: {result.stderr or result.stdout}")
        except Exception as e2:
            print(f"✗ All email methods failed: {e2}")
            raise
