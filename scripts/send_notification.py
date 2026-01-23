#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News - Email Notification Sender
Sends email notifications with daily news summary
"""

import smtplib
import sqlite3
import logging
import os
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import (
    DATABASE_PATH,
    EMAIL_USERNAME,
    EMAIL_PASSWORD,
    EMAIL_RECIPIENTS,
    EMAIL_SUBJECT,
    EMAIL_FROM_NAME
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EmailNotifier:
    """Email notification sender"""
    
    def __init__(self, db_path=DATABASE_PATH):
        self.db_path = db_path
        self.email_username = EMAIL_USERNAME
        self.email_password = EMAIL_PASSWORD
        self.recipients = EMAIL_RECIPIENTS
        
        if not self.email_username or not self.email_password:
            raise ValueError("Email credentials not set in environment variables")
        
        logger.info("Email Notifier initialized")
    
    def get_today_articles(self):
        """Get articles collected today"""
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        today = datetime.now().date()
        today_str = today.isoformat()
        
        cursor.execute("""
            SELECT 
                title, title_en, sector, province, 
                source_url, source_name, summary_en,
                article_date
            FROM news_articles
            WHERE DATE(collection_date) = ?
            ORDER BY article_date DESC
        """, (today_str,))
        
        articles = []
        for row in cursor.fetchall():
            article = {
                'title': row[1] or row[0],  # title_en or title
                'sector': row[2],
                'province': row[3],
                'url': row[4],
                'source': row[5],
                'summary': row[6],
                'date': row[7]
            }
            articles.append(article)
        
        conn.close()
        logger.info(f"Found {len(articles)} articles from today")
        return articles
    
    def get_statistics(self):
        """Get database statistics"""
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Total articles
        cursor.execute("SELECT COUNT(*) FROM news_articles")
        total = cursor.fetchone()[0]
        
        # Articles by sector
        cursor.execute("""
            SELECT sector, COUNT(*) as count 
            FROM news_articles 
            GROUP BY sector 
            ORDER BY count DESC
            LIMIT 5
        """)
        top_sectors = cursor.fetchall()
        
        # Recent activity (last 7 days)
        cursor.execute("""
            SELECT COUNT(*) 
            FROM news_articles 
            WHERE DATE(collection_date) >= DATE('now', '-7 days')
        """)
        last_7_days = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'total': total,
            'top_sectors': top_sectors,
            'last_7_days': last_7_days
        }
    
    def generate_html_email(self, articles, stats):
        """Generate HTML email content"""
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px 10px 0 0;
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
        .stats {{
            background: #f8f9fa;
            padding: 20px;
            border-left: 4px solid #667eea;
            margin: 20px 0;
        }}
        .stats h3 {{
            margin-top: 0;
            color: #667eea;
        }}
        .article {{
            background: white;
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            padding: 20px;
            margin: 15px 0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .article-title {{
            font-size: 18px;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 10px;
        }}
        .article-meta {{
            color: #7f8c8d;
            font-size: 14px;
            margin-bottom: 10px;
        }}
        .sector-tag {{
            display: inline-block;
            background: #3498db;
            color: white;
            padding: 4px 12px;
            border-radius: 4px;
            font-size: 12px;
            margin-right: 8px;
        }}
        .summary {{
            color: #555;
            line-height: 1.6;
            margin-top: 10px;
        }}
        .read-more {{
            display: inline-block;
            margin-top: 10px;
            color: #3498db;
            text-decoration: none;
            font-weight: bold;
        }}
        .footer {{
            text-align: center;
            color: #7f8c8d;
            margin-top: 30px;
            padding-top: 20px;
            border-top: 2px solid #e0e0e0;
        }}
        .dashboard-button {{
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 12px 30px;
            border-radius: 6px;
            text-decoration: none;
            margin: 20px 0;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🏗️ Vietnam Infrastructure News</h1>
        <p>Daily Update - {datetime.now().strftime('%B %d, %Y')}</p>
    </div>
    
    <div class="stats">
        <h3>📊 Database Statistics</h3>
        <p><strong>Total Articles:</strong> {stats['total']:,}</p>
        <p><strong>Last 7 Days:</strong> {stats['last_7_days']} articles</p>
        <p><strong>Today's Collection:</strong> {len(articles)} new articles</p>
"""
        
        if stats['top_sectors']:
            html += "<p><strong>Top Sectors:</strong> "
            html += ", ".join([f"{sector} ({count})" for sector, count in stats['top_sectors']])
            html += "</p>"
        
        html += "</div>"
        
        # Articles section
        if articles:
            html += f"<h2>📰 Today's Articles ({len(articles)})</h2>"
            
            for idx, article in enumerate(articles[:20], 1):  # Show first 20
                html += f"""
    <div class="article">
        <div class="article-title">{idx}. {article['title']}</div>
        <div class="article-meta">
            <span class="sector-tag">{article['sector']}</span>
            <span>{article['province']}</span> | 
            <span>{article['source']}</span>
        </div>
"""
                if article.get('summary'):
                    html += f'<div class="summary">{article["summary"][:200]}...</div>'
                
                html += f"""
        <a href="{article['url']}" class="read-more" target="_blank">Read Full Article →</a>
    </div>
"""
            
            if len(articles) > 20:
                html += f"<p><em>... and {len(articles) - 20} more articles</em></p>"
        
        else:
            html += """
    <div class="article">
        <p>No new articles collected today. The system ran successfully but found no new content matching our criteria.</p>
    </div>
"""
        
        # Footer
        html += """
    <div class="footer">
        <a href="https://github.com/yourusername/vietnam-infra-news" class="dashboard-button">
            📊 View Full Dashboard
        </a>
        <p>Vietnam Infrastructure News Pipeline</p>
        <p>Automated daily collection and analysis of infrastructure news</p>
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
                print(f"  Articles: {len(articles)}")
                print(f"  Total in DB: {stats['total']}")
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
            print(f"Subject: {EMAIL_SUBJECT}")
            print("="*80)
            print(html[:500] + "...")
            print("="*80)
        else:
            success = notifier.run()
            sys.exit(0 if success else 1)
            
    except Exception as e:
        logger.error(f"Error in main: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
