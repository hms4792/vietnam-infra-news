"""
send_email.py
=============
Vietnam Infrastructure News - 주간 이메일 알림 발송
yml 인라인 python3 -c 방식 대신 독립 스크립트로 분리
"""
import smtplib
import os
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from pathlib import Path


def get_stats():
    """Excel에서 수집 통계 읽기"""
    total  = 0
    weekly = 0
    try:
        import openpyxl
        excel_path = Path("data/database/Vietnam_Infra_News_Database_Final.xlsx")
        if not excel_path.exists():
            print(f"[Email] Excel 파일 없음: {excel_path}")
            return total, weekly

        wb     = openpyxl.load_workbook(excel_path, read_only=True)
        ws     = wb.active
        cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

        for row in ws.iter_rows(min_row=2, values_only=True):
            if not any(v for v in row):
                continue
            total += 1
            date_val = str(row[4] or "")[:10]
            if date_val >= cutoff:
                weekly += 1

        wb.close()
        print(f"[Email] 통계 읽기 완료 - 전체: {total}건, 금주: {weekly}건")

    except Exception as e:
        print(f"[Email] Excel 읽기 오류: {e}")

    return total, weekly


def build_html(total, weekly):
    """이메일 HTML 본문 생성"""
    now      = datetime.now().strftime("%Y-%m-%d %H:%M")
    today_d  = datetime.now().strftime("%m/%d")
    cutoff_d = (datetime.now() - timedelta(days=7)).strftime("%m/%d")
    dashboard_url = "https://hms4792.github.io/vietnam-infra-news/"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;background:#f0f2f5;">

<div style="background:#1a5276;color:white;padding:24px;border-radius:10px 10px 0 0;">
  <h2 style="margin:0;font-size:20px;">Vietnam Infrastructure News</h2>
  <p style="margin:6px 0 0;opacity:0.85;font-size:13px;">
    Weekly Pipeline Report &mdash; {now} KST
  </p>
</div>

<div style="background:white;padding:24px;border-radius:0 0 10px 10px;box-shadow:0 2px 8px rgba(0,0,0,0.08);">

  <h3 style="color:#1a5276;margin-top:0;">수집 결과</h3>
  <table style="width:100%;border-collapse:collapse;margin-bottom:20px;">
    <tr style="background:#2e86c1;color:white;">
      <th style="padding:10px 14px;text-align:left;border-radius:4px 0 0 0;">항목</th>
      <th style="padding:10px 14px;text-align:center;border-radius:0 4px 0 0;">건수</th>
    </tr>
    <tr style="border-bottom:1px solid #eee;">
      <td style="padding:12px 14px;">금주 신규 기사 ({cutoff_d}~{today_d})</td>
      <td style="padding:12px 14px;text-align:center;font-weight:bold;
                 color:#1e8449;font-size:18px;">{weekly}건</td>
    </tr>
    <tr style="background:#f8fafc;">
      <td style="padding:12px 14px;">전체 누적 기사</td>
      <td style="padding:12px 14px;text-align:center;font-weight:bold;
                 font-size:16px;">{total:,}건</td>
    </tr>
  </table>

  <div style="text-align:center;margin:24px 0;">
    <a href="{dashboard_url}"
       style="background:#2e86c1;color:white;padding:14px 32px;
              border-radius:6px;text-decoration:none;font-weight:bold;
              font-size:15px;display:inline-block;">
      대시보드 바로가기
    </a>
  </div>

  <p style="color:#999;font-size:11px;text-align:center;margin-bottom:0;">
    Vietnam Infrastructure News Pipeline &mdash; 자동 발송
  </p>

</div>
</body>
</html>"""


def send_email():
    """이메일 발송 메인 함수"""
# 환경변수 여러 이름으로 시도 (yml env 전달 방식 차이 대응)
    gmail_user = (
    os.environ.get("GMAIL_ADDRESS") or
    os.environ.get("gmail_address") or
    ""
    ).strip()

    gmail_pw = (
    os.environ.get("GMAIL_APP_PASSWORD") or
    os.environ.get("gmail_app_password") or
    ""
    ).strip()

# 디버그: 어떤 환경변수가 있는지 확인 (비밀값은 출력 안 함)
    print(f"[Email] 환경변수 확인:")
    print(f"  GMAIL_ADDRESS 있음: {bool(gmail_user)}")
    print(f"  GMAIL_APP_PASSWORD 있음: {bool(gmail_pw)}")
    gmail_keys = [k for k in os.environ.keys() if 'GMAIL' in k.upper()]
    print(f"  GMAIL 관련 키 목록: {gmail_keys}")
    if not gmail_user or not gmail_pw:
        print("[Email] GMAIL_ADDRESS 또는 GMAIL_APP_PASSWORD Secret 미설정")
        sys.exit(0)

    total, weekly = get_stats()

    today_d = datetime.now().strftime("%m/%d")
    subject = f"[베트남 인프라 뉴스] 주간 리포트 - 금주 {weekly}건 수집 ({today_d})"
    html    = build_html(total, weekly)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Vietnam Infra News <{gmail_user}>"
    msg["To"]      = gmail_user
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        print(f"[Email] SMTP 연결 중... → {gmail_user}")
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(gmail_user, gmail_pw)
            smtp.send_message(msg)
        print(f"[Email] 발송 완료 → {gmail_user}")
        print(f"[Email] 제목: {subject}")

    except smtplib.SMTPAuthenticationError:
        print("[Email] 인증 실패 - GMAIL_APP_PASSWORD를 확인하세요")
        sys.exit(0)
    except Exception as e:
        print(f"[Email] 발송 실패: {e}")
        sys.exit(0)


if __name__ == "__main__":
    send_email()
