#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News - Email Notification
Reads from Excel database
"""

import smtplib
import logging
import os
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import (
    DATA_DIR,
    EMAIL_USERNAME,
    EMAIL_PASSWORD,
    EMAIL_RECIPIENTS,
    EMAIL_SUBJECT,
    EMAIL_FROM_NAME
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

EXCEL_DB_PATH = DATA_DIR / "database" / "Vietnam_Infra_News_Database_Final.xlsx"


class EmailNotifier:
    def __init__(self):
        self.email_username = EMAIL_USERNAME
        self.email_password = EMAIL_PASSWORD
        self.recipients = [r.strip() for r in EMAIL_RECIPIENTS if r.strip()]
        self.articles = []
        self.today = datetime.now().strftime("%Y-%m-%d")
        
        if not self.email_username or not self.email_password:
            raise ValueError("Email credentials not set")
        
        self._load_articles()
        logger.info("Email Notifier initialized")
    
    def _load_articles(self):
        """Load articles from Excel"""
        try:
            import openpyxl
            if not EXCEL_DB_PATH.exists():
                logger.warning(f"Excel not found: {EXCEL_DB_PATH}")
                return
            
            wb = openpyxl.load_workbook(EXCEL_DB_PATH, read_only=True, data_only=True)
            ws = wb.active
            headers = [cell.value for cell in ws[1]]
            
            col_map = {str(h).strip(): i for i, h in enumerate(headers) if h}
            
            for row in ws.iter_rows(min_row=2, values_only=True):
                if not any(row):
                    continue
                
                date_val = row[col_map.get("Date", 4)] if "Date" in col_map else ""
                if date_val:
                    date_str = date_val.strftime("%Y-%m-%d") if hasattr(date_val, 'strftime') else str(date_val)[:10]
                else:
                    date_str = ""
                
                self.articles.append({
                    "title": row[col_map.get("News Tittle", 3)] or "",
                    "sector": row[col_map.get("Business Sector", 1)] or "",
                    "province": row[col_map.get("Province", 2)] or "Vietnam",
                    "source": row[col_map.get("Source", 5)] or "",
                    "url": row[col_map.get("Link", 6)] or "",
                    "summary": row[col_map.get("Short summary", 7)] or "",
                    "date": date_str
                })
            
            wb.close()
            logger.info(f"Loaded {len(self.articles)} articles")
            
        except Exception as e:
            logger.error(f"Load error: {e}")
    
    def get_today_articles(self):
        return [a for a in self.articles if a.get("date") == self.today]
    
    def get_statistics(self):
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        
        return {
            'total': len(self.articles),
            'today': len(self.get_today_articles()),
            'week': sum(1 for a in self.articles if a.get("date", "") >= week_ago),
            'sectors': Counter(a.get("sector", "Unknown") for a in self.articles).most_common(5),
            'sources': Counter(a.get("source", "Unknown") for a in self.articles).most_common(10)
        }
    
    def generate_html(self, articles, stats):
        today_articles = self.get_today_articles()
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #0d9488, #0f766e); color: white; padding: 30px; border-radius: 10px; text-align: center; }}
        .kpi {{ display: flex; gap: 15px; margin: 20px 0; }}
        .kpi-card {{ flex: 1; background: #f8fafc; padding: 15px; border-radius: 8px; text-align: center; border-left: 4px solid #0d9488; }}
        .kpi-value {{ font-size: 28px; font-weight: bold; color: #0d9488; }}
        .kpi-label {{ font-size: 12px; color: #64748b; }}
        .article {{ background: #f8fafc; border-radius: 8px; padding: 15px; margin: 10px 0; border-left: 4px solid #0d9488; }}
        .article.new {{ background: #fef3c7; border-left-color: #f59e0b; }}
        .sector-tag {{ background: #0d9488; color: white; padding: 2px 8px; border-radius: 4px; font-size: 11px; }}
        .source-tag {{ color: #64748b; font-size: 11px; }}
        .footer {{ text-align: center; margin-top: 30px; padding: 20px; background: #f8fafc; border-radius: 8px; }}
        .btn {{ display: inline-block; background: #0d9488; color: white; padding: 12px 30px; border-radius: 6px; text-decoration: none; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🇻🇳 Vietnam Infrastructure News</h1>
        <p>Daily Report - {datetime.now().strftime('%B %d, %Y')}</p>
    </div>
    
    <div class="kpi">
        <div class="kpi-card" style="border-left-color: #f59e0b;">
            <div class="kpi-value">{stats['today']}</div>
            <div class="kpi-label">Today</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-value">{stats['week']}</div>
            <div class="kpi-label">This Week</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-value">{stats['total']:,}</div>
            <div class="kpi-label">Total Database</div>
        </div>
    </div>
    
    <h3>📊 Top Sectors</h3>
    <p>{"  |  ".join([f"{s}: {c}" for s, c in stats['sectors']])}</p>
    
    <h3>📰 Top Sources</h3>
    <p style="font-size: 12px; color: #64748b;">{"  |  ".join([f"{s}: {c}" for s, c in stats['sources']])}</p>
"""
        
        if today_articles:
            html += f"<h3>🆕 Today's Articles ({len(today_articles)})</h3>"
            for a in today_articles[:15]:
                html += f"""
    <div class="article new">
        <span class="sector-tag">{a['sector']}</span>
        <span class="source-tag" style="margin-left: 10px;">{a['source']}</span>
        <h4 style="margin: 10px 0 5px 0;">{a['title'][:100]}</h4>
        <p style="font-size: 13px; color: #475569; margin: 0;">{a['summary'][:150]}...</p>
        <a href="{a['url']}" style="font-size: 12px; color: #0d9488;">Read more →</a>
    </div>
"""
        else:
            html += "<p>No new articles collected today.</p>"
        
        html += """
    <div class="footer">
        <a href="https://hms4792.github.io/vietnam-infra-news/" class="btn">📊 View Full Dashboard</a>
        <p style="margin-top: 15px; font-size: 12px; color: #94a3b8;">Vietnam Infrastructure News Pipeline</p>
    </div>
</body>
</html>"""
        
        return html
    
    def send_email(self, html):
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"{EMAIL_SUBJECT} - {datetime.now().strftime('%Y-%m-%d')}"
            msg['From'] = f"{EMAIL_FROM_NAME} <{self.email_username}>"
            msg['To'] = ', '.join(self.recipients)
            msg.attach(MIMEText(html, 'html'))
            
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(self.email_username, self.email_password)
            server.send_message(msg)
            server.quit()
            
            logger.info("Email sent successfully")
            return True
        except Exception as e:
            logger.error(f"Email error: {e}")
            return False
    
    def run(self):
        try:
            stats = self.get_statistics()
            html = self.generate_html(self.articles, stats)
            success = self.send_email(html)
            
            if success:
                print(f"✓ Email sent to {len(self.recipients)} recipients")
                print(f"  Today: {stats['today']} articles")
                print(f"  Total: {stats['total']} articles")
            return success
        except Exception as e:
            logger.error(f"Error: {e}")
            return False


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', action='store_true')
    args = parser.parse_args()
    
    try:
        notifier = EmailNotifier()
        if args.test:
            stats = notifier.get_statistics()
            print(f"Test mode - Total: {stats['total']}, Today: {stats['today']}")
        else:
            notifier.run()
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
