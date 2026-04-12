#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
send_email.py  v2.0
====================
[변경 2026-04-12]
  일일 워크플로우: 오늘 수집 기사 중 정책 연계 기사만 본문에 표시
  토요일 주간 워크플로우: 금주 전체 수집 현황 표시
  구분 기준: today is Saturday → weekly 모드, otherwise → daily 모드

[이메일 구조]
  Daily 모드:
    - 일일 KPI (오늘 수집 / 정책매핑 / 누적 DB)
    - 정책 연계 기사 리스트 (노란색 배경, 기사별 Master Plan 표시)
    - 대시보드 링크

  Weekly 모드 (토요일):
    - 주간 KPI (금주 수집 / 섹터별 분포)
    - Top 5 기사
    - 대시보드 링크
"""

import os
import json
import smtplib
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# ── 환경 변수 ─────────────────────────────────────────────────
EMAIL_USERNAME = os.environ.get("EMAIL_USERNAME", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD", "")
EXCEL_PATH     = os.environ.get("EXCEL_PATH", "data/database/Vietnam_Infra_News_Database_Final.xlsx")

BASE_DIR       = Path(__file__).parent.parent
AGENT_OUT      = BASE_DIR / "data" / "agent_output"
COLLECTOR_JSON = AGENT_OUT / "collector_output.json"
QUALITY_JSON   = AGENT_OUT / "quality_report.json"
POLICY_JSON    = AGENT_OUT / "policy_highlighted_articles.json"

DASHBOARD_URL  = "https://hms4792.github.io/vietnam-infra-news/"
RECIPIENTS     = [EMAIL_USERNAME] if EMAIL_USERNAME else []

# ── 색상 팔레트 ───────────────────────────────────────────────
TEAL    = "#0d9488"
TEAL_LT = "#e6faf8"
YELLOW  = "#FFFDE7"
YELLOW_B= "#F9A825"
GRAY    = "#f8f9fa"
DARK    = "#1a1a2e"

# ── 모드 결정 ─────────────────────────────────────────────────
def is_saturday():
    return datetime.datetime.now().weekday() == 5

# ── 데이터 로드 ───────────────────────────────────────────────
def load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def load_excel_stats():
    """Excel DB에서 누적 건수와 금주 건수 집계"""
    try:
        import openpyxl
        wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True, data_only=True)
        ws = wb["News Database"]
        total = ws.max_row - 1  # 헤더 제외

        # 금주 기준 (7일)
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        week_count = 0
        sector_cnt = {}
        for row in ws.iter_rows(min_row=2, values_only=True):
            date_val = str(row[4] or "")[:10]
            sector   = str(row[1] or "")
            if date_val >= cutoff:
                week_count += 1
                sector_cnt[sector] = sector_cnt.get(sector, 0) + 1
        wb.close()
        return total, week_count, sector_cnt
    except Exception as e:
        print(f"[WARN] Excel 읽기 실패: {e}")
        return 0, 0, {}

# ── HTML 컴포넌트 ─────────────────────────────────────────────
def kpi_card(label, value, color=TEAL):
    return f"""
    <td style="width:25%;padding:12px;text-align:center">
      <div style="background:#fff;border-radius:8px;padding:14px 10px;
                  border:1px solid #e0e0e0">
        <div style="font-size:22px;font-weight:700;color:{color};margin-bottom:4px">{value}</div>
        <div style="font-size:11px;color:#888">{label}</div>
      </div>
    </td>"""

def policy_article_row(article, idx):
    """정책 연계 기사 한 행 (노란색 배경)"""
    title    = article.get("title_ko") or article.get("title", "")[:60]
    title_en = (article.get("title_en") or article.get("title", ""))[:60]
    sector   = article.get("sector", "")
    province = article.get("province", "")
    source   = article.get("source", "")
    url      = article.get("url", "#")
    doc_id   = article.get("policy_doc_id", "")
    plan     = article.get("policy_plan_name", doc_id)
    relevance= article.get("policy_relevance", "")
    rel_color= "#E65100" if relevance == "high" else "#F57C00"

    sector_colors = {
        "Waste Water": "#1565C0", "Water Supply/Drainage": "#0277BD",
        "Solid Waste": "#2E7D32", "Power": "#F57F17",
        "Oil & Gas": "#4A148C", "Industrial Parks": "#00695C",
        "Smart City": "#1A237E",
    }
    sc = sector_colors.get(sector, TEAL)

    return f"""
    <tr style="background:{'#FFFDE7' if idx % 2 == 0 else '#FFF8E1'}">
      <td style="padding:10px 12px;border-bottom:1px solid #FFE082;vertical-align:top">
        <div style="font-size:13px;font-weight:600;margin-bottom:3px">
          <a href="{url}" style="color:{DARK};text-decoration:none">{title or title_en}</a>
        </div>
        <div style="font-size:11px;color:#666;margin-bottom:4px">{title_en}</div>
        <div style="display:flex;gap:6px;flex-wrap:wrap">
          <span style="background:{sc};color:#fff;padding:2px 7px;
                        border-radius:3px;font-size:10px">{sector}</span>
          <span style="background:#E3F2FD;color:#0D47A1;padding:2px 7px;
                        border-radius:3px;font-size:10px">{province}</span>
          <span style="background:{rel_color};color:#fff;padding:2px 7px;
                        border-radius:3px;font-size:10px">{plan}</span>
          <span style="color:#999;font-size:10px;padding:2px 0">{source}</span>
        </div>
      </td>
    </tr>"""

def top5_article_row(article, idx):
    """주간 Top5 기사 행"""
    title    = article.get("title_ko") or article.get("title", "")[:60]
    sector   = article.get("sector", "")
    province = article.get("province", "")
    source   = article.get("source", "")
    url      = article.get("url", "#")
    date     = str(article.get("date") or article.get("published_date", ""))[:10]
    bg = "#f8f9fa" if idx % 2 == 0 else "#fff"
    return f"""
    <tr style="background:{bg}">
      <td style="padding:10px 12px;border-bottom:1px solid #eee">
        <div style="font-size:13px;font-weight:600;margin-bottom:2px">
          <a href="{url}" style="color:{DARK};text-decoration:none">{title}</a>
        </div>
        <div style="font-size:11px;color:#888">{sector} | {province} | {source} | {date}</div>
      </td>
    </tr>"""

# ── 일일 이메일 HTML ──────────────────────────────────────────
def build_daily_email(policy_data, collector_data, quality_data, total_db, week_count):
    today        = datetime.datetime.now().strftime("%Y-%m-%d")
    today_count  = len(collector_data.get("articles", []))
    highlight_n  = policy_data.get("highlight_count", 0)
    highlight_r  = f"{policy_data.get('highlight_ratio', 0):.0%}"
    grade        = quality_data.get("quality_grade", "C")
    grade_color  = {"A":"#2E7D32","B":"#388E3C","C":"#F57F17","D":"#C62828"}.get(grade, TEAL)

    # 정책 연계 기사만 추출
    articles     = policy_data.get("articles", [])
    policy_arts  = [a for a in articles if a.get("policy_highlight")][:15]

    # 섹터별 카운트
    sector_cnt = {}
    for a in articles:
        s = a.get("sector", "")
        sector_cnt[s] = sector_cnt.get(s, 0) + 1

    sector_rows = ""
    for sector, cnt in sorted(sector_cnt.items(), key=lambda x: -x[1])[:7]:
        bar_w = min(int(cnt / max(today_count, 1) * 100), 100)
        sector_rows += f"""
        <tr>
          <td style="padding:5px 10px;font-size:12px;color:{DARK}">{sector}</td>
          <td style="padding:5px 10px">
            <div style="background:#e0e0e0;border-radius:3px;height:8px;width:100%">
              <div style="background:{TEAL};height:8px;border-radius:3px;width:{bar_w}%"></div>
            </div>
          </td>
          <td style="padding:5px 10px;font-size:12px;font-weight:600;color:{TEAL}">{cnt}건</td>
        </tr>"""

    policy_rows = "".join(policy_article_row(a, i) for i, a in enumerate(policy_arts))
    no_policy   = f"""<tr><td style="padding:20px;text-align:center;color:#888;font-size:13px">
                      정책 연계 기사가 없습니다</td></tr>""" if not policy_arts else ""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:0;background:#f0f4f8;font-family:Arial,sans-serif">
<table width="100%" style="max-width:680px;margin:0 auto;background:#f0f4f8">
<tr><td style="padding:20px">

  <!-- 헤더 -->
  <table width="100%" style="background:{TEAL};border-radius:12px 12px 0 0;padding:0">
  <tr><td style="padding:24px 28px">
    <div style="color:#fff;font-size:18px;font-weight:700">
      🇻🇳 베트남 인프라 뉴스 — 일일 리포트
    </div>
    <div style="color:#b2dfdb;font-size:13px;margin-top:4px">
      {today} | 정책 연계 기사 우선 표시
    </div>
  </td></tr>
  </table>

  <!-- KPI -->
  <table width="100%" style="background:#fff;padding:0">
  <tr>
    {kpi_card("오늘 수집", f"{today_count}건")}
    {kpi_card("정책 매핑", f"{highlight_n}건 ({highlight_r})", YELLOW_B)}
    {kpi_card("품질 등급", grade, grade_color)}
    {kpi_card("누적 DB", f"{total_db:,}건", "#455a64")}
  </tr>
  </table>

  <!-- 섹터별 분포 -->
  <table width="100%" style="background:#fff;margin-top:2px;padding:16px 20px">
  <tr><td>
    <div style="font-size:13px;font-weight:700;color:{TEAL};margin-bottom:10px">
      오늘 섹터별 수집 현황
    </div>
    <table width="100%">{sector_rows}</table>
  </td></tr>
  </table>

  <!-- 정책 연계 기사 -->
  <table width="100%" style="background:#fff;margin-top:2px">
  <tr><td style="padding:16px 20px 8px">
    <div style="font-size:14px;font-weight:700;color:{DARK};display:flex;align-items:center;gap:8px">
      <span style="background:{YELLOW_B};color:#fff;padding:3px 8px;border-radius:4px;font-size:12px">
        Master Plan 연계
      </span>
      오늘 정책 연계 기사 ({len(policy_arts)}건)
    </div>
    <div style="font-size:11px;color:#888;margin-top:4px">
      아래 기사는 베트남 인프라 마스터플랜 프로젝트와 연계된 기사입니다
    </div>
  </td></tr>
  </table>
  <table width="100%" style="background:{YELLOW};border-top:3px solid {YELLOW_B}">
    {policy_rows}{no_policy}
  </table>

  <!-- 대시보드 링크 -->
  <table width="100%" style="background:#fff;margin-top:2px;border-radius:0 0 12px 12px">
  <tr><td style="padding:20px;text-align:center">
    <a href="{DASHBOARD_URL}"
       style="background:{TEAL};color:#fff;padding:12px 28px;border-radius:6px;
              text-decoration:none;font-size:14px;font-weight:600">
      전체 대시보드 보기
    </a>
    <div style="margin-top:10px;font-size:11px;color:#888">
      전체 기사는 대시보드 Database 탭에서 확인하세요
    </div>
  </td></tr>
  </table>

</td></tr>
</table>
</body></html>"""

# ── 주간 이메일 HTML ──────────────────────────────────────────
def build_weekly_email(collector_data, quality_data, total_db, week_count, sector_cnt):
    today        = datetime.datetime.now().strftime("%Y-%m-%d")
    grade        = quality_data.get("quality_grade", "C")
    grade_color  = {"A":"#2E7D32","B":"#388E3C","C":"#F57F17","D":"#C62828"}.get(grade, TEAL)
    articles     = collector_data.get("articles", [])[:5]

    # 섹터 분포 행
    sector_rows = ""
    for sector, cnt in sorted(sector_cnt.items(), key=lambda x: -x[1])[:7]:
        bar_w = min(int(cnt / max(week_count, 1) * 100), 100)
        sector_rows += f"""
        <tr>
          <td style="padding:5px 10px;font-size:12px">{sector}</td>
          <td style="padding:5px 10px">
            <div style="background:#e0e0e0;border-radius:3px;height:8px">
              <div style="background:{TEAL};height:8px;border-radius:3px;width:{bar_w}%"></div>
            </div>
          </td>
          <td style="padding:5px 10px;font-size:12px;font-weight:600;color:{TEAL}">{cnt}건</td>
        </tr>"""

    top5_rows = "".join(top5_article_row(a, i) for i, a in enumerate(articles))

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
</head>
<body style="margin:0;padding:0;background:#f0f4f8;font-family:Arial,sans-serif">
<table width="100%" style="max-width:680px;margin:0 auto;background:#f0f4f8">
<tr><td style="padding:20px">

  <!-- 헤더 -->
  <table width="100%" style="background:{TEAL};border-radius:12px 12px 0 0">
  <tr><td style="padding:24px 28px">
    <div style="color:#fff;font-size:18px;font-weight:700">
      🇻🇳 베트남 인프라 뉴스 — 주간 리포트
    </div>
    <div style="color:#b2dfdb;font-size:13px;margin-top:4px">
      {today} | 금주 수집 현황 요약
    </div>
  </td></tr>
  </table>

  <!-- KPI -->
  <table width="100%" style="background:#fff">
  <tr>
    {kpi_card("금주 수집", f"{week_count}건")}
    {kpi_card("품질 등급", grade, grade_color)}
    {kpi_card("누적 DB", f"{total_db:,}건", "#455a64")}
    {kpi_card("섹터 커버", f"{len(sector_cnt)}/7", "#7B1FA2")}
  </tr>
  </table>

  <!-- 섹터 분포 -->
  <table width="100%" style="background:#fff;margin-top:2px;padding:16px 20px">
  <tr><td>
    <div style="font-size:13px;font-weight:700;color:{TEAL};margin-bottom:10px">금주 섹터별 분포</div>
    <table width="100%">{sector_rows}</table>
  </td></tr>
  </table>

  <!-- Top 5 기사 -->
  <table width="100%" style="background:#fff;margin-top:2px">
  <tr><td style="padding:16px 20px 8px">
    <div style="font-size:14px;font-weight:700;color:{DARK}">Top 5 기사</div>
  </td></tr>
  </table>
  <table width="100%" style="background:#fff">{top5_rows}</table>

  <!-- 대시보드 링크 -->
  <table width="100%" style="background:#fff;margin-top:2px;border-radius:0 0 12px 12px">
  <tr><td style="padding:20px;text-align:center">
    <a href="{DASHBOARD_URL}"
       style="background:{TEAL};color:#fff;padding:12px 28px;border-radius:6px;
              text-decoration:none;font-size:14px;font-weight:600">
      전체 대시보드 보기
    </a>
  </td></tr>
  </table>

</td></tr>
</table>
</body></html>"""

# ── 이메일 발송 ───────────────────────────────────────────────
def send_email(subject, html_body):
    if not EMAIL_USERNAME or not EMAIL_PASSWORD:
        print(f"[Email] EMAIL_USERNAME 있음: {bool(EMAIL_USERNAME)}")
        print(f"[Email] EMAIL_PASSWORD 있음: {bool(EMAIL_PASSWORD)}")
        print("[Email] 인증 정보 없음 — 발송 건너뜀")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_USERNAME
    msg["To"]      = ", ".join(RECIPIENTS)
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        print(f"[Email] SMTP 연결 중 → ***")
        with smtplib.SMTP("smtp.gmail.com", 587) as s:
            s.starttls()
            s.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            s.sendmail(EMAIL_USERNAME, RECIPIENTS, msg.as_string())
        print(f"[Email] 발송 완료 → ***")
        print(f"[Email] 제목: {subject}")
        return True
    except Exception as e:
        print(f"[Email] 발송 실패: {e}")
        return False

# ── MAIN ─────────────────────────────────────────────────────
def main():
    today_str    = datetime.datetime.now().strftime("%m/%d")
    weekly_mode  = is_saturday()

    # 데이터 로드
    policy_data    = load_json(POLICY_JSON)
    collector_data = load_json(COLLECTOR_JSON)
    quality_data   = load_json(QUALITY_JSON)
    total_db, week_count, sector_cnt = load_excel_stats()

    print(f"[Email] 통계: 전체 {total_db}건, 금주 {week_count}건")

    if weekly_mode:
        # 토요일: 주간 리포트
        subject = f"[베트남 인프라 뉴스] 주간 리포트 - 금주 {week_count}건 수집 ({today_str})"
        html    = build_weekly_email(collector_data, quality_data, total_db, week_count, sector_cnt)
    else:
        # 평일: 일일 리포트 (정책 연계 기사 중심)
        today_count = len(collector_data.get("articles", []))
        highlight_n = policy_data.get("highlight_count", 0)
        subject = (f"[베트남 인프라 뉴스] 일일 리포트"
                   f" - 정책연계 {highlight_n}건 ({today_str})")
        html = build_daily_email(
            policy_data, collector_data, quality_data, total_db, week_count
        )

    send_email(subject, html)


if __name__ == "__main__":
    main()
