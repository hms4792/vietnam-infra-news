"""
send_weekly_email.py — v1.0 (2026-05-16)
==========================================
주간 MI 보고서 이메일 단독 발송 스크립트

용도:
  - 워크플로우 재실행 없이 이메일만 발송할 때 사용
  - generate_mi_report.py SameFileError로 이메일이 막혔을 때 수동 복구용
  - docs/reports/ 에서 최신 PPT/Word 파일 자동 탐색 후 첨부

실행:
  python3 scripts/send_weekly_email.py

환경변수:
  EMAIL_USERNAME  — Gmail 주소
  EMAIL_PASSWORD  — Gmail 앱 비밀번호
"""

import json
import logging
import os
import smtplib
import sys
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('send_weekly_email')

# ── 경로 설정 ──────────────────────────────────────────────────────────────
_SCRIPTS_DIR = Path(__file__).parent
_ROOT_DIR    = _SCRIPTS_DIR.parent
REPORTS_DIR  = _ROOT_DIR / 'docs' / 'reports'
PAYLOAD_FILE = _ROOT_DIR / 'data' / 'agent_output' / 'sa8_report_payload.json'


def find_latest_report(ext: str) -> Path | None:
    """docs/reports/ 에서 가장 최신 보고서 파일 탐색"""
    pattern = f'VN_Infra_MI_Weekly_Report_*.{ext}'
    files = sorted(REPORTS_DIR.glob(pattern))
    return files[-1] if files else None


def load_payload() -> dict:
    """sa8_report_payload.json 로드 (없으면 기본값 사용)"""
    if PAYLOAD_FILE.exists():
        with open(PAYLOAD_FILE, encoding='utf-8') as f:
            return json.load(f)
    log.warning(f'payload 파일 없음: {PAYLOAD_FILE} — 기본값 사용')
    return {
        'report_date':        datetime.now().strftime('%Y-%m-%d'),
        'report_period':      '최근 14일',
        'total_articles':     0,
        'new_articles_count': 0,
        'plans':              {},
        'kpi_dashboard':      [],
    }


def send_email(pptx_path: Path | None, docx_path: Path | None,
               payload: dict, kpi_changes: list) -> bool:
    """이메일 발송 (generate_mi_report.py send_email() 동일 로직)"""
    username = os.environ.get('EMAIL_USERNAME')
    password = os.environ.get('EMAIL_PASSWORD')
    if not username or not password:
        log.warning('EMAIL_USERNAME / EMAIL_PASSWORD 미설정 — 이메일 건너뜀')
        return False

    today_str  = payload.get('report_date', datetime.now().strftime('%Y-%m-%d'))
    plan_count = len(payload.get('plans', {}))
    art_count  = payload.get('total_articles', 0)
    new_count  = payload.get('new_articles_count', 0)

    subject = f'[베트남 인프라 MI] 주간 보고서 — {today_str}'
    if kpi_changes:
        subject += f' ★ KPI 변동 {len(kpi_changes)}건'

    body_lines = [
        f'안녕하세요,\n\n베트남 인프라 MI 주간 보고서({today_str})를 첨부합니다.\n',
        f'■ 수집 기간: {payload.get("report_period", "")}',
        f'■ 전체 기사: {art_count}건 (신규 {new_count}건)',
        f'■ 마스터플랜: {plan_count}개 전체 포함',
    ]
    if kpi_changes:
        body_lines.append(f'\n★ KPI 변동사항 ({len(kpi_changes)}건):')
        for ch in kpi_changes:
            body_lines.append(
                f'  - {ch.get("plan_id")}: {ch.get("indicator")} '
                f'{ch.get("from")} → {ch.get("to")}'
            )
    body_lines += [
        '\n■ 첨부 파일:',
        '  • PPT: 경영진 보고용 슬라이드 (21개 플랜 전체)',
        '  • Word: 상세 분석 보고서 (Layer1 사업개요 + Layer2 AI분석)',
        '\n대시보드: https://hms4792.github.io/vietnam-infra-news/',
        '\n본 메일은 Claude SA-8이 자동 생성하였습니다.',
    ]
    body = '\n'.join(body_lines)

    msg = MIMEMultipart()
    msg['Subject'] = subject
    msg['From']    = username
    msg['To']      = username
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    attached = []
    for fpath in [pptx_path, docx_path]:
        if fpath and Path(fpath).exists():
            with open(fpath, 'rb') as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', 'attachment',
                            filename=Path(fpath).name)
            msg.attach(part)
            attached.append(Path(fpath).name)

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(username, password)
            smtp.send_message(msg)
        log.info(f'✅ 이메일 발송 완료 → {username}')
        log.info(f'   첨부: {attached}')
        return True
    except Exception as e:
        log.error(f'❌ 이메일 발송 실패: {e}')
        return False


def main():
    log.info('=' * 55)
    log.info(f'send_weekly_email v1.0 — {datetime.now().strftime("%Y-%m-%d %H:%M")}')
    log.info('=' * 55)

    # 최신 보고서 파일 탐색
    pptx_path = find_latest_report('pptx')
    docx_path = find_latest_report('docx')

    log.info(f'PPT 파일: {pptx_path or "없음"}')
    log.info(f'Word 파일: {docx_path or "없음"}')

    if not pptx_path and not docx_path:
        log.error(f'첨부 파일 없음 — {REPORTS_DIR} 확인 필요')
        sys.exit(1)

    # payload 로드
    payload     = load_payload()
    kpi_changes = payload.get('kpi_changes', [])

    log.info(f'payload: {payload.get("report_date")} / '
             f'기사 {payload.get("total_articles")}건 / '
             f'플랜 {len(payload.get("plans", {}))}개')

    # 이메일 발송
    ok = send_email(pptx_path, docx_path, payload, kpi_changes)

    log.info('=' * 55)
    log.info(f'완료: {"✅ 성공" if ok else "❌ 실패"}')
    log.info('=' * 55)

    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
