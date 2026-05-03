#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
send_email.py — v3.2
일일/주간 뉴스 통계 이메일 발송

목적:
  - Excel 데이터베이스 읽음
  - 일일 리포트 또는 주간 리포트 생성
  - HTML 이메일로 발송
  
특징:
  ✓ 일일/주간 자동 선택 (요일 기반)
  ✓ 마스터플랜 연계 기사 강조
  ✓ 섹터별 통계
  ✓ 소스별 분석
  ✓ 반응형 HTML 이메일
  
사용법:
  python3 scripts/send_email.py
  
일정:
  daily_pipeline.yml → 매일 KST 20:00 (정책 연계 기사 중심)
"""

import os
import sys
import json
import smtplib
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ═══════════════════════════════════════════════════════════════════════════
#  설정 (Configuration)
# ═══════════════════════════════════════════════════════════════════════════

SCRIPT_DIR = Path(__file__).parent
ROOT_DIR = SCRIPT_DIR.parent

EXCEL_PATH = ROOT_DIR / "data" / "database" / "Vietnam_Infra_News_Database_Final.xlsx"

# 이메일 설정 (환경변수에서 읽음)
EMAIL_USERNAME = os.environ.get('EMAIL_USERNAME', '')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD', '')
EMAIL_SMTP_SERVER = 'smtp.gmail.com'
EMAIL_SMTP_PORT = 587

RECIPIENTS = [
    EMAIL_USERNAME  # 자신에게 발송
]

# 로깅
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
#  데이터 로드
# ═══════════════════════════════════════════════════════════════════════════

def load_excel_data() -> List[Dict[str, Any]]:
    """
    Excel 파일에서 기사 데이터 로드
    """
    try:
        import openpyxl
    except ImportError:
        os.system("pip install openpyxl --break-system-packages")
        import openpyxl
    
    if not EXCEL_PATH.exists():
        logger.error(f"Excel file not found: {EXCEL_PATH}")
        return []
    
    try:
        wb = openpyxl.load_workbook(EXCEL_PATH)
        ws = wb['News Database']
        
        articles = []
        for row_idx, row in enumerate(ws.iter_rows(values_only=True), 1):
            if row_idx == 1:  # 헤더 행 스킵
                continue
            
            if not row or not row[0]:  # 빈 행 스킵
                continue
            
            try:
                article = {
                    'area': str(row[0] or 'Unknown').strip(),
                    'sector': str(row[1] or 'Unknown').strip(),
                    'date': str(row[3] or '').strip() if row[3] else '',
                    'title_en': str(row[4] or 'Untitled').strip(),
                    'title_vi': str(row[5] or '').strip(),
                    'title_ko': str(row[6] or '').strip(),
                    'source': str(row[7] or 'Unknown').strip(),
                    'province': str(row[9] or 'Vietnam').strip(),
                    'plan_id': str(row[10] or '').strip() if len(row) > 10 else '',
                    'grade': str(row[11] or '').strip() if len(row) > 11 else '',
                    'url': str(row[12] or '').strip() if len(row) > 12 else '',
                    'summary_ko': str(row[13] or '').strip() if len(row) > 13 else '',
                    'summary_en': str(row[14] or '').strip() if len(row) > 14 else '',
                    'summary_vi': str(row[15] or '').strip() if len(row) > 15 else ''
                }
                articles.append(article)
            except Exception as e:
                logger.warning(f"Row {row_idx}: {e}")
                continue
        
        logger.info(f"✓ Loaded {len(articles)} articles")
        return articles
    
    except Exception as e:
        logger.error(f"Error loading Excel: {e}")
        return []

# ═══════════════════════════════════════════════════════════════════════════
#  통계 계산
# ═══════════════════════════════════════════════════════════════════════════

def calculate_stats(articles: List[Dict], period: str = 'daily') -> Dict[str, Any]:
    """
    기사 통계 계산
    
    Args:
        articles: 기사 목록
        period: 'daily' 또는 'weekly'
    
    Returns:
        dict: 통계 정보
    """
    today = datetime.now().strftime("%Y-%m-%d")
    
    if period == 'daily':
        # 오늘 기사만
        filtered = [a for a in articles if a['date'] == today]
    else:  # weekly
        # 지난 7일 기사
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        filtered = [a for a in articles if a['date'] >= start_date]
    
    # 섹터별 집계
    sector_count = {}
    for article in filtered:
        sector = article['sector']
        sector_count[sector] = sector_count.get(sector, 0) + 1
    
    # 소스별 집계
    source_count = {}
    for article in filtered:
        source = article['source']
        source_count[source] = source_count.get(source, 0) + 1
    
    # 마스터플랜 연계 기사
    matched = [a for a in filtered if a['plan_id']]
    
    return {
        'total': len(filtered),
        'matched': len(matched),
        'sector_count': sorted(sector_count.items(), key=lambda x: x[1], reverse=True),
        'source_count': sorted(source_count.items(), key=lambda x: x[1], reverse=True)[:10],
        'matched_articles': matched[:5]  # Top 5
    }

# ═══════════════════════════════════════════════════════════════════════════
#  HTML 이메일 생성
# ═══════════════════════════════════════════════════════════════════════════

def generate_email_html(articles: List[Dict], stats: Dict, period: str = 'daily') -> str:
    """
    HTML 이메일 본문 생성
    """
    today_str = datetime.now().strftime("%Y년 %m월 %d일")
    
    # 섹터별 통계 HTML
    sector_html = ""
    for sector, count in stats['sector_count']:
        sector_html += f"""
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #eee;">{sector}</td>
            <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: right;">
                <strong>{count}</strong>건
            </td>
        </tr>
        """
    
    # 마스터플랜 연계 기사 HTML
    matched_html = ""
    for article in stats['matched_articles']:
        matched_html += f"""
        <div style="
            background: #f0f8f5;
            border-left: 4px solid #28a745;
            padding: 15px;
            margin-bottom: 15px;
            border-radius: 4px;
        ">
            <div style="
                font-size: 14px;
                color: #666;
                margin-bottom: 8px;
            ">
                <strong>🎯 마스터플랜 연계</strong> | 
                {article['date']} | 
                {article['sector']} | 
                <strong>{article['grade']}</strong>
            </div>
            <div style="
                font-size: 15px;
                font-weight: 600;
                color: #333;
                margin-bottom: 8px;
            ">
                {article['title_ko']}
            </div>
            <div style="
                font-size: 13px;
                color: #555;
                line-height: 1.6;
                margin-bottom: 10px;
            ">
                {article['summary_ko']}
            </div>
            <div style="text-align: right;">
                <a href="{article['url']}" style="
                    display: inline-block;
                    padding: 6px 12px;
                    background: #28a745;
                    color: white;
                    text-decoration: none;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: 600;
                ">
                    기사 보기 →
                </a>
            </div>
        </div>
        """
    
    # 소스별 통계 HTML
    source_html = ""
    for source, count in stats['source_count']:
        source_html += f"""
        <tr>
            <td style="padding: 8px;">{source}</td>
            <td style="padding: 8px; text-align: right;">{count}</td>
        </tr>
        """
    
    # 최종 HTML
    if period == 'daily':
        title = f"[베트남 인프라 뉴스] 일일 리포트"
        subtitle = f"정책 연계 {stats['matched']}건 포함 ({today_str})"
    else:
        title = f"[베트남 인프라 뉴스] 주간 리포트"
        subtitle = f"지난 7일간 {stats['total']}건 수집 ({today_str})"
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; }}
            .container {{ max-width: 600px; margin: 20px auto; background: white; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
            .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; text-align: center; }}
            .header h1 {{ margin: 0; font-size: 24px; }}
            .header p {{ margin: 8px 0 0 0; font-size: 14px; opacity: 0.9; }}
            .content {{ padding: 30px; }}
            .stats-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 30px; }}
            .stat-card {{ background: #f8f9fa; padding: 15px; border-radius: 8px; border-left: 4px solid #667eea; }}
            .stat-card .number {{ font-size: 28px; font-weight: bold; color: #667eea; }}
            .stat-card .label {{ font-size: 12px; color: #666; margin-top: 5px; }}
            .section-title {{ font-size: 18px; font-weight: 600; color: #333; margin: 25px 0 15px 0; border-bottom: 2px solid #667eea; padding-bottom: 10px; }}
            .table-basic {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
            .table-basic th {{ background: #667eea; color: white; padding: 12px; text-align: left; }}
            .footer {{ background: #f8f9fa; padding: 20px; text-align: center; color: #666; font-size: 12px; border-top: 1px solid #eee; }}
            a {{ color: #667eea; text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🇻🇳 {title}</h1>
                <p>{subtitle}</p>
            </div>
            
            <div class="content">
                <!-- 통계 카드 -->
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="number">{stats['total']}</div>
                        <div class="label">{'오늘 기사' if period == 'daily' else '주간 기사'}</div>
                    </div>
                    <div class="stat-card">
                        <div class="number">{stats['matched']}</div>
                        <div class="label">마스터플랜 연계</div>
                    </div>
                </div>
                
                <!-- 마스터플랜 연계 기사 -->
                {f'''
                <div class="section-title">🎯 마스터플랜 연계 기사 TOP 5</div>
                {matched_html}
                ''' if matched_html else ''}
                
                <!-- 섹터별 통계 -->
                <div class="section-title">📊 섹터별 통계</div>
                <table class="table-basic">
                    <thead>
                        <tr>
                            <th>섹터</th>
                            <th style="text-align: right;">기사 수</th>
                        </tr>
                    </thead>
                    <tbody>
                        {sector_html}
                    </tbody>
                </table>
                
                <!-- 소스별 Top 10 -->
                <div class="section-title">📰 소스별 TOP 10</div>
                <table class="table-basic">
                    <thead>
                        <tr>
                            <th>소스</th>
                            <th style="text-align: right;">기사 수</th>
                        </tr>
                    </thead>
                    <tbody>
                        {source_html}
                    </tbody>
                </table>
                
                <!-- 대시보드 링크 -->
                <div style="
                    background: #f0f8f5;
                    padding: 15px;
                    border-radius: 8px;
                    text-align: center;
                    margin-top: 30px;
                ">
                    <p style="margin: 0 0 10px 0; color: #666;">
                        더 자세한 내용은 대시보드에서 확인하세요:
                    </p>
                    <a href="https://hms4792.github.io/vietnam-infra-news/" style="
                        display: inline-block;
                        padding: 10px 20px;
                        background: #667eea;
                        color: white;
                        border-radius: 6px;
                        font-weight: 600;
                    ">
                        📊 대시보드 보기
                    </a>
                    <p style="margin: 10px 0 0 0; font-size: 12px;">
                        또는 <a href="https://hms4792.github.io/vietnam-infra-news/mi_dashboard.html">MI Dashboard 보기</a>
                    </p>
                </div>
            </div>
            
            <div class="footer">
                <p>
                    © 2025 Vietnam Infrastructure News Pipeline<br>
                    Powered by Claude AI | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S KST')}
                </p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html

# ═══════════════════════════════════════════════════════════════════════════
#  이메일 발송
# ═══════════════════════════════════════════════════════════════════════════

def send_email(subject: str, html_body: str) -> bool:
    """
    이메일 발송
    
    Args:
        subject: 이메일 제목
        html_body: HTML 본문
    
    Returns:
        bool: 성공 여부
    """
    if not EMAIL_USERNAME or not EMAIL_PASSWORD:
        logger.warning("EMAIL_USERNAME or EMAIL_PASSWORD not set. Skipping email.")
        return False
    
    try:
        logger.info(f"Sending email to {len(RECIPIENTS)} recipient(s)...")
        
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = EMAIL_USERNAME
        msg['To'] = ', '.join(RECIPIENTS)
        
        msg.attach(MIMEText(html_body, 'html', 'utf-8'))
        
        with smtplib.SMTP(EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(EMAIL_USERNAME, EMAIL_PASSWORD)
            server.send_message(msg)
        
        logger.info(f"✓ Email sent: {subject}")
        return True
    
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"Authentication failed: {e}")
        logger.error("TIP: Use Gmail App Password (not regular password)")
        return False
    except Exception as e:
        logger.error(f"Email error: {type(e).__name__}: {e}")
        return False

# ═══════════════════════════════════════════════════════════════════════════
#  메인 함수
# ═══════════════════════════════════════════════════════════════════════════

def is_saturday() -> bool:
    """토요일 여부 확인 (한국 시간)"""
    from datetime import datetime, timezone, timedelta
    kst = timezone(timedelta(hours=9))
    today = datetime.now(kst).weekday()
    return today == 5  # 5 = Saturday

def main():
    """메인 실행 함수"""
    logger.info("=" * 60)
    logger.info("EMAIL NOTIFICATION v3.2")
    logger.info("=" * 60)
    
    # 1️⃣ Excel 데이터 로드
    logger.info(f"Loading Excel: {EXCEL_PATH}")
    articles = load_excel_data()
    
    if not articles:
        logger.error("No articles loaded")
        return False
    
    # 2️⃣ 일일/주간 모드 결정
    is_weekly = is_saturday()
    period = 'weekly' if is_weekly else 'daily'
    logger.info(f"Mode: {period.upper()}")
    
    # 3️⃣ 통계 계산
    stats = calculate_stats(articles, period)
    logger.info(f"  - Total: {stats['total']} articles")
    logger.info(f"  - Matched: {stats['matched']} articles")
    
    # 4️⃣ 이메일 생성
    today_str = datetime.now().strftime("%m/%d")
    if is_weekly:
        subject = f"[베트남 인프라 뉴스] 주간 리포트 - {stats['total']}건 ({today_str})"
    else:
        subject = f"[베트남 인프라 뉴스] 일일 리포트 - 정책 연계 {stats['matched']}건 ({today_str})"
    
    html = generate_email_html(articles, stats, period)
    
    # 5️⃣ 이메일 발송
    success = send_email(subject, html)
    
    logger.info("=" * 60)
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
