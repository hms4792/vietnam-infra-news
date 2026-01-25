#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News - Email Notification Sender
Sends email notifications with daily news summary
Works with Excel database
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

# Add project root to path
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

# Excel database path
EXCEL_DB_PATH = DATA_DIR / "database" / "Vietnam_Infra_News_Database_Final.xlsx"


class EmailNotifier:
    """Email notification sender - Excel based"""
    
    def __init__(self):
        self.email_username = EMAIL_USERNAME
        self.email_password = EMAIL_PASSWORD
        self.recipients = [r.strip() for r in EMAIL_RECIPIENTS if r.strip()]
        self.all_articles = []
        self.today = datetime.now().strftime("%Y-%m-%d")
        
        if not self.email_username or not self.email_password:
            raise ValueError("Email credentials not set in environment variables")
        
        if not self.recipients:
            raise ValueError("No email recipients configured")
        
        # Load articles from Excel
        self._load_articles_from_excel()
        
        logger.info("Email Notifier initialized")
    
    def _load_articles_from_excel(self):
        """Load all articles from Excel database"""
        try:
            import openpyxl
        except ImportError:
            logger.error("openpyxl not installed")
            return
        
        if not EXCEL_DB_PATH.exists():
            logger.warning(f"Excel database not found: {EXCEL_DB_PATH}")
            return
        
        try:
            wb = openpyxl.load_workbook(EXCEL_DB_PATH, read_only=True, data_only=True)
            ws = wb.active
            
            headers = [cell.value for cell in ws[1]]
            logger.info(f"Excel headers: {headers}")
            
            for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
                if not any(row):
                    continue
                
                raw = {}
                for i, value in enumerate(row):
                    if i < len(headers) and headers[i]:
                        raw[headers[i]] = value
                
                # Parse date
                date_val = raw.get("Date", "")
                if date_val:
                    if hasattr(date_val, 'strftime'):
                        date_str = date_val.strftime("%Y-%m-%d")
                    else:
                        date_str = str(date_val)[:10]
                else:
                    date_str = ""
                
                article = {
                    "title": raw.get("News Tittle", raw.get("Title", "")),
                    "title_en": raw.get("Summary (EN)", raw.get("Title (EN)", "")),
                    "sector": raw.get("Business Sector", raw.get("Sector", "Infrastructure")),
                    "area": raw.get("Area", "Environment"),
                    "province": raw.get("Province", "Vietnam"),
                    "source": raw.get("Source", raw.get("Source Name", "")),
                    "url": raw.get("Link", raw.get("Source URL", "")),
                    "summary": raw.get("Short summary", raw.get("Summary (EN)", "")),
                    "summary_en": raw.get("Summary (EN)", ""),
                    "summary_ko": raw.get("Summary (KO)", ""),
                    "date": date_str
                }
                
                if article.get("title") or article.get("url"):
                    self.all_articles.append(article)
            
            wb.close()
            logger.info(f"Loaded {len(self.all_articles)} articles from Excel")
            
        except Exception as e:
            logger.error(f"Error loading Excel: {e}")
            import traceback
            traceback.print_exc()
    
    def get_today_articles(self):
        """Get articles collected today"""
        today_articles = [a for a in self.all_articles if a.get("date") == self.today]
        logger.info(f"Found {len(today_articles)} articles from today ({self.today})")
        return today_articles
    
    def get_week_articles(self):
        """Get articles from last 7 days"""
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        week_articles = [a for a in self.all_articles if a.get("date", "") >= week_ago]
        return week_articles
    
    def get_statistics(self):
        """Get database statistics"""
        
        total = len(self.all_articles)
        
        # Articles by sector
        sector_counts = Counter(a.get("sector", "Unknown") for a in self.all_articles)
        top_sectors = sector_counts.most_common(5)
        
        # Articles by province (excluding Vietnam)
        province_counts = Counter(
            a.get("province", "Vietnam") for a in self.all_articles 
            if a.get("province", "Vietnam") != "Vietnam"
        )
        top_provinces = province_counts.most_common(5)
        
        # Recent activity
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        last_7_days = sum(1 for a in self.all_articles if a.get("date", "") >= week_ago)
        
        # Today's count
        today_count = sum(1 for a in self.all_articles if a.get("date") == self.today)
        
        # By area
        area_counts = Counter(a.get("area", "Unknown") for a in self.all_articles)
        
        return {
            'total': total,
            'top_sectors': top_sectors,
            'top_provinces': top_provinces,
            'area_counts': area_counts.most_common(5),
            'last_7_days': last_7_days,
            'today_count': today_count
        }
    
    def generate_html_email(self, articles, stats):
        """Generate HTML email content"""
        
        today_articles = self.get_today_articles()
        week_articles = self.get_week_articles()
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: 'Segoe UI', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .header {{
            background: linear-gradient(135deg, #0d9488 0%, #0f766e 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0;
            font-size: 28px;
        }}
        .header p {{
            margin: 10px 0 0 0;
            opacity: 0.9;
        }}
        .content {{
            padding: 30px;
        }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 15px;
            margin-bottom: 30px;
        }}
        .kpi-card {{
            background: #f8fafc;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
            border-left: 4px solid #0d9488;
        }}
        .kpi-value {{
            font-size: 32px;
            font-weight: bold;
            color: #0d9488;
        }}
        .kpi-label {{
            color: #64748b;
            font-size: 14px;
            margin-top: 5px;
        }}
        .kpi-card.highlight {{
            background: #fef3c7;
            border-left-color: #f59e0b;
        }}
        .kpi-card.highlight .kpi-value {{
            color: #d97706;
        }}
        .section-title {{
            font-size: 20px;
            font-weight: bold;
            color: #1e293b;
            margin: 30px 0 15px 0;
            padding-bottom: 10px;
            border-bottom: 2px solid #e2e8f0;
        }}
        .stats-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 15px 0;
        }}
        .stats-table th, .stats-table td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #e2e8f0;
        }}
        .stats-table th {{
            background: #f8fafc;
            font-weight: 600;
            color: #475569;
        }}
        .article {{
            background: #f8fafc;
            border-radius: 8px;
            padding: 20px;
            margin: 15px 0;
            border-left: 4px solid #0d9488;
        }}
        .article.new {{
            background: #fef3c7;
            border-left-color: #f59e0b;
        }}
        .article-title {{
            font-size: 16px;
            font-weight: bold;
            color: #1e293b;
            margin-bottom: 10px;
        }}
        .article-meta {{
            color: #64748b;
            font-size: 13px;
            margin-bottom: 10px;
        }}
        .sector-tag {{
            display: inline-block;
            background: #0d9488;
            color: white;
            padding: 3px 10px;
            border-radius: 4px;
            font-size: 11px;
            margin-right: 8px;
        }}
        .new-tag {{
            display: inline-block;
            background: #f59e0b;
            color: white;
            padding: 3px 10px;
            border-radius: 4px;
            font-size: 11px;
            margin-right: 8px;
        }}
        .summary {{
            color: #475569;
            line-height: 1.6;
            margin-top: 10px;
            font-size: 14px;
        }}
        .read-more {{
            display: inline-block;
            margin-top: 10px;
            color: #0d9488;
            text-decoration: none;
            font-weight: bold;
            font-size: 14px;
        }}
        .footer {{
            text-align: center;
            color: #64748b;
            padding: 30px;
            background: #f8fafc;
        }}
        .dashboard-button {{
            display: inline-block;
            background: #0d9488;
            color: white;
            padding: 14px 35px;
            border-radius: 8px;
            text-decoration: none;
            margin: 15px 0;
            font-weight: bold;
            font-size: 16px;
        }}
        .province-badge {{
            display: inline-block;
            background: #e0f2fe;
            color: #0369a1;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            margin-left: 5px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🇻🇳 Vietnam Infrastructure News</h1>
            <p>Daily Report - {datetime.now().strftime('%B %d, %Y')}</p>
        </div>
        
        <div class="content">
            <!-- KPI Cards -->
            <div class="kpi-grid">
                <div class="kpi-card highlight">
                    <div class="kpi-value">{stats['today_count']}</div>
                    <div class="kpi-label">Today</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-value">{stats['last_7_days']}</div>
                    <div class="kpi-label">This Week</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-value">{stats['total']:,}</div>
                    <div class="kpi-label">Total Database</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-value">{len(stats['top_sectors'])}</div>
                    <div class="kpi-label">Sectors</div>
                </div>
            </div>
            
            <!-- Statistics Tables -->
            <h3 class="section-title">📊 Statistics Summary</h3>
            
            <table class="stats-table">
                <tr>
                    <th>Sector</th>
                    <th>Articles</th>
                    <th>Area</th>
                </tr>
"""
        
        # Add sector stats
        for sector, count in stats['top_sectors'][:5]:
            area = "Environment" if sector in ["Waste Water", "Solid Waste", "Water Supply/Drainage"] else "Energy/Urban"
            html += f"""
                <tr>
                    <td>{sector}</td>
                    <td><strong>{count}</strong></td>
                    <td>{area}</td>
                </tr>
"""
        
        html += """
            </table>
            
            <table class="stats-table">
                <tr>
                    <th>Province (Top 5)</th>
                    <th>Articles</th>
                </tr>
"""
        
        # Add province stats
        for province, count in stats['top_provinces'][:5]:
            html += f"""
                <tr>
                    <td>{province}</td>
                    <td><strong>{count}</strong></td>
                </tr>
"""
        
        html += """
            </table>
"""
        
        # Today's articles section
        if today_articles:
            html += f"""
            <h3 class="section-title">📰 Today's New Articles ({len(today_articles)})</h3>
"""
            for idx, article in enumerate(today_articles[:10], 1):
                title = article.get('title_en') or article.get('title', 'No title')
                summary = article.get('summary_en') or article.get('summary', '')
                province = article.get('province', 'Vietnam')
                province_badge = f'<span class="province-badge">{province}</span>' if province != "Vietnam" else ""
                
                html += f"""
            <div class="article new">
                <div class="article-title">
                    <span class="new-tag">NEW</span>
                    {idx}. {title[:100]}
                </div>
                <div class="article-meta">
                    <span class="sector-tag">{article.get('sector', 'Infrastructure')}</span>
                    {article.get('source', 'Unknown')} {province_badge}
                </div>
"""
                if summary:
                    html += f'<div class="summary">{summary[:200]}...</div>'
                
                if article.get('url'):
                    html += f"""
                <a href="{article['url']}" class="read-more" target="_blank">Read Full Article →</a>
"""
                html += "</div>"
            
            if len(today_articles) > 10:
                html += f"<p><em>... and {len(today_articles) - 10} more articles today</em></p>"
        
        else:
            html += """
            <h3 class="section-title">📰 Today's Articles</h3>
            <div class="article">
                <p>No new articles collected today. The pipeline ran successfully but found no new content matching our infrastructure criteria.</p>
            </div>
"""
        
        # This week's highlights (if no today articles)
        if not today_articles and week_articles:
            html += f"""
            <h3 class="section-title">📅 This Week's Highlights ({len(week_articles)} articles)</h3>
"""
            for idx, article in enumerate(week_articles[:5], 1):
                title = article.get('title_en') or article.get('title', 'No title')
                html += f"""
            <div class="article">
                <div class="article-title">{idx}. {title[:100]}</div>
                <div class="article-meta">
                    <span class="sector-tag">{article.get('sector', 'Infrastructure')}</span>
                    {article.get('date', '')} | {article.get('source', '')}
                </div>
                <a href="{article.get('url', '#')}" class="read-more" target="_blank">Read More →</a>
            </div>
"""
        
        # Footer
        html += """
        </div>
        
        <div class="footer">
            <a href="https://hms4792.github.io/vietnam-infra-news/" class="dashboard-button">
                📊 View Full Dashboard
            </a>
            <p style="margin-top: 20px;">Vietnam Infrastructure News Pipeline</p>
            <p style="font-size: 12px; color: #94a3b8;">Automated daily collection and analysis</p>
        </div>
    </div>
</body>
</html>
"""
        
        return html
    
    def send_email(self, html_content):
        """Send email notification"""
        
        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = f"{EMAIL_SUBJECT} - {datetime.now().strftime('%Y-%m-%d')}"
            msg['From'] = f"{EMAIL_FROM_NAME} <{self.email_username}>"
            msg['To'] = ', '.join(self.recipients)
            
            # Attach HTML content
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            # Send via Gmail SMTP
            logger.info("Connecting to Gmail SMTP server...")
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            
            logger.info("Logging in...")
            server.login(self.email_username, self.email_password)
            
            logger.info(f"Sending email to {len(self.recipients)} recipients...")
            server.send_message(msg)
            server.quit()
            
            logger.info("✓ Email sent successfully!")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run(self):
        """Main execution"""
        
        try:
            # Get today's articles
            articles = self.get_today_articles()
            
            # Get statistics
            stats = self.get_statistics()
            
            # Generate HTML email
            html_content = self.generate_html_email(articles, stats)
            
            # Send email
            success = self.send_email(html_content)
            
            if success:
                print(f"\n✓ Email notification sent successfully!")
                print(f"  Recipients: {', '.join(self.recipients)}")
                print(f"  Today's Articles: {len(articles)}")
                print(f"  Total in Database: {stats['total']}")
            else:
                print("\n✗ Failed to send email notification")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error in email notification: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    """Main execution"""
    
    import argparse
    
    parser = argparse.ArgumentParser(description='Send email notification for Vietnam Infrastructure News')
    parser.add_argument('--test', action='store_true', help='Test mode - print email instead of sending')
    
    args = parser.parse_args()
    
    try:
        notifier = EmailNotifier()
        
        if args.test:
            articles = notifier.get_today_articles()
            stats = notifier.get_statistics()
            html = notifier.generate_html_email(articles, stats)
            
            print("\n" + "="*80)
            print("EMAIL PREVIEW (Test Mode)")
            print("="*80)
            print(f"To: {', '.join(notifier.recipients)}")
            print(f"Subject: {EMAIL_SUBJECT} - {datetime.now().strftime('%Y-%m-%d')}")
            print(f"Today's Articles: {len(articles)}")
            print(f"Total in Database: {stats['total']}")
            print("="*80)
            
            # Save preview to file
            preview_path = Path("outputs/email_preview.html")
            preview_path.parent.mkdir(parents=True, exist_ok=True)
            with open(preview_path, 'w', encoding='utf-8') as f:
                f.write(html)
            print(f"Preview saved to: {preview_path}")
            
        else:
            success = notifier.run()
            sys.exit(0 if success else 1)
            
    except Exception as e:
        logger.error(f"Error in main: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
