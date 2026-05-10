"""
send_email_only.py
==================
기존 sa8_report_payload.json을 읽어 이메일만 즉시 재발송.

사용법:
  python3 scripts/send_email_only.py

조건:
  - data/agent_output/sa8_report_payload.json 존재
  - docs/reports/ 에 최신 docx/pptx 존재
  - EMAIL_USERNAME / EMAIL_PASSWORD 환경변수 설정
"""

import glob as _glob
import json
import logging
import os
import smtplib
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s', datefmt='%H:%M:%S')
log = logging.getLogger('send_email_only')

# ── 경로 설정 ──────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent.parent
DOCS_DIR      = BASE_DIR / 'docs'
AGENT_OUT_DIR = BASE_DIR / 'data' / 'agent_output'
PAYLOAD_PATH  = AGENT_OUT_DIR / 'sa8_report_payload.json'

DASHBOARD_URL    = "https://hms4792.github.io/vietnam-infra-news/"
MI_DASHBOARD_URL = "https://hms4792.github.io/vietnam-infra-news/mi_dashboard.html"


def find_latest_report(ext: str) -> Path | None:
    """docs/reports/ 또는 docs/ 에서 가장 최신 보고서 탐색."""
    candidates = sorted(
        _glob.glob(str(DOCS_DIR / 'reports' / f'*.{ext}')), reverse=True
    ) + sorted(
        _glob.glob(str(DOCS_DIR / f'VN_Infra_MI_Weekly_Report_*.{ext}')), reverse=True
    )
    return Path(candidates[0]) if candidates else None


def send_email(payload: dict, docx_path: Path | None, pptx_path: Path | None) -> bool:
    username = os.getenv('EMAIL_USERNAME')
    password = os.getenv('EMAIL_PASSWORD')
    if not username or not password:
        log.error("EMAIL_USERNAME / EMAIL_PASSWORD 환경변수 없음")
        return False

    today      = datetime.now().strftime('%Y년 %m월 %d일')
    week_label = payload.get('report_week', '')
    total_arts = payload.get('total_articles', 0)
    new_count  = payload.get('new_articles_count', 0)
    kpi_count  = payload.get('kpi_changes_count', 0)
    exec_summ  = payload.get('executive_summary', '')

    body_lines = [
        f"베트남 인프라 MI 주간 보고서 ({week_label})",
        f"발행일: {today}  [재발송]",
        f"생성: SA-8 자동 파이프라인 (Claude Haiku 분석 통합)",
        "",
        "=" * 55,
        "【 대시보드 바로가기 】",
        f"  ▶ News Dashboard    : {DASHBOARD_URL}",
        f"  ▶ MI Dashboard      : {MI_DASHBOARD_URL}",
        "=" * 55,
        "",
        f"▶ 전체 누적 기사: {total_arts}건",
        f"▶ 이번 주 신규:   {new_count}건  ← 노란색 마킹",
        f"▶ 분석 플랜:      {payload.get('plan_count', 0)}개",
        f"▶ KPI 변동:       {kpi_count}개 플랜",
        "=" * 55,
        "",
        "【Executive Summary — AI 분석 (Claude Haiku)】",
        "─" * 55,
        exec_summ or "(Executive Summary 없음)",
        "",
        "─" * 55,
        "★ 노란색 강조 = 이번 주 신규 기사",
        "★ 회색 = 기존 누적 기사 (내용 유지)",
        "★ KPI 변동 플랜은 ⚠ 아이콘으로 강조",
        "",
    ]

    # 플랜별 수집 현황
    plan_sections = payload.get('plan_sections', [])
    if plan_sections:
        body_lines.append("【플랜별 기사 현황】")
        for sec in plan_sections:
            new_c = sec.get('new_count', 0)
            old_c = sec.get('old_count', 0)
            total = new_c + old_c
            if total == 0:
                continue
            kpi_flag = "⚠ " if sec.get('has_kpi_change') else "  "
            new_flag = f"신규{new_c}건" if new_c > 0 else "신규없음"
            body_lines.append(
                f"  {kpi_flag}{sec.get('plan_id','')}: 총{total}건 ({new_flag} / 기존{old_c}건)"
            )

    body_lines += [
        "",
        "─" * 55,
        f"  ▶ News Dashboard    : {DASHBOARD_URL}",
        f"  ▶ MI Dashboard      : {MI_DASHBOARD_URL}",
        "─" * 55,
    ]

    body = "\n".join(body_lines)

    msg = MIMEMultipart()
    msg['From']    = username
    msg['To']      = username
    msg['Subject'] = f"[VN Infra MI] 주간 보고서 {today} — 신규 {new_count}건 [재발송]"
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    attached = []

    # docx 첨부
    if docx_path and docx_path.exists():
        with open(docx_path, 'rb') as f:
            att = MIMEApplication(f.read(), Name=docx_path.name)
        att['Content-Disposition'] = f'attachment; filename="{docx_path.name}"'
        msg.attach(att)
        attached.append(docx_path.name)

    # pptx 첨부
    if pptx_path and pptx_path.exists():
        with open(pptx_path, 'rb') as f:
            att2 = MIMEApplication(f.read(), Name=pptx_path.name)
        att2['Content-Disposition'] = f'attachment; filename="{pptx_path.name}"'
        msg.attach(att2)
        attached.append(pptx_path.name)

    if attached:
        log.info(f"첨부: {' + '.join(attached)}")
    else:
        log.warning("첨부 파일 없음 — 본문만 발송")

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as srv:
            srv.login(username, password)
            srv.sendmail(username, [username], msg.as_string())
        log.info(f"✅ 이메일 발송 완료: {username}")
        return True
    except smtplib.SMTPAuthenticationError:
        log.error("이메일 인증 실패 — Gmail App Password 확인")
        return False
    except Exception as e:
        log.error(f"이메일 발송 오류: {e}")
        return False


def main():
    log.info("=" * 50)
    log.info("이메일 재발송 스크립트")
    log.info("=" * 50)

    # 페이로드 로드
    if not PAYLOAD_PATH.exists():
        log.error(f"페이로드 없음: {PAYLOAD_PATH}")
        return
    with open(PAYLOAD_PATH, encoding='utf-8') as f:
        payload = json.load(f)
    log.info(f"페이로드 로드: {PAYLOAD_PATH.name} ({payload.get('report_week','')})")

    # 최신 보고서 탐색
    docx_path = find_latest_report('docx')
    pptx_path = find_latest_report('pptx')
    log.info(f"Word: {docx_path.name if docx_path else '없음'}")
    log.info(f"PPT:  {pptx_path.name if pptx_path else '없음'}")

    send_email(payload, docx_path, pptx_path)


if __name__ == '__main__':
    main()
