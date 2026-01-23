#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News - Dashboard Updater
Generates HTML dashboard from database
"""

import sqlite3
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import (
    DATABASE_PATH,
    OUTPUT_DIR,
    TEMPLATE_DIR,
    DASHBOARD_TITLE,
    DASHBOARD_SUBTITLE
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DashboardUpdater:
    """Dashboard generator for infrastructure news"""
    
    def __init__(self, db_path=DATABASE_PATH, output_dir=OUTPUT_DIR, template_dir=TEMPLATE_DIR):
        self.db_path = db_path
        self.output_dir = Path(output_dir)
        self.template_dir = Path(template_dir)
        
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Dashboard Updater initialized")
        logger.info(f"Database: {self.db_path}")
        logger.info(f"Output: {self.output_dir}")
        logger.info(f"Template: {self.template_dir}")
    
    def load_articles_from_db(self):
        """Load articles from database"""
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                id, title, title_ko, title_en, title_vi,
                source_url, source_name, sector, area, province,
                article_date, collection_date,
                summary_ko, summary_en, summary_vi
            FROM news_articles
            ORDER BY article_date DESC
        """)
        
        articles = []
        for row in cursor.fetchall():
            article = {
                'id': row[0],
                'title': row[2] or row[3] or row[1],  # title_ko or title_en or title
                'title_ko': row[2] or row[1],
                'title_en': row[3] or row[1],
                'title_vi': row[4] or row[1],
                'source_url': row[5],
                'source_name': row[6],
                'sector': row[7],
                'area': row[8],
                'province': row[9] or 'Vietnam',
                'article_date': row[10],
                'collection_date': row[11],
                'summary_ko': row[12],
                'summary_en': row[13],
                'summary_vi': row[14]
            }
            articles.append(article)
        
        conn.close()
        logger.info(f"Loaded {len(articles)} articles from database")
        return articles
    
    def generate_dashboard_data(self, articles):
        """Generate JSON data for dashboard"""
        
        dashboard_data = []
        
        for article in articles:
            # Parse date
            try:
                if article['article_date']:
                    date_obj = datetime.fromisoformat(article['article_date'])
                    date_str = date_obj.strftime('%Y-%m-%d')
                else:
                    date_str = datetime.now().strftime('%Y-%m-%d')
            except:
                date_str = datetime.now().strftime('%Y-%m-%d')
            
            item = {
                'date': date_str,
                'title': article['title_en'] or article['title'],
                'title_ko': article['title_ko'] or article['title'],
                'title_en': article['title_en'] or article['title'],
                'title_vi': article['title_vi'] or article['title'],
                'sector': article['sector'] or 'Unknown',
                'area': article['area'] or 'Environment',
                'province': article['province'],
                'source': article['source_name'] or 'Unknown',
                'url': article['source_url'],
                'summary_ko': article['summary_ko'] or '',
                'summary_en': article['summary_en'] or '',
                'summary_vi': article['summary_vi'] or ''
            }
            
            dashboard_data.append(item)
        
        logger.info(f"Generated dashboard data: {len(dashboard_data)} items")
        return dashboard_data
    
    def generate_html(self, dashboard_data):
        """Generate HTML dashboard"""
        
        # Load template
        template_path = self.template_dir / "dashboard_template.html"
        
        if not template_path.exists():
            logger.error(f"Template not found: {template_path}")
            # Create basic template
            html_content = self._create_basic_template(dashboard_data)
        else:
            with open(template_path, 'r', encoding='utf-8') as f:
                template = f.read()
            
            # Replace placeholders
            html_content = template.replace(
                '{{DASHBOARD_DATA}}',
                json.dumps(dashboard_data, ensure_ascii=False, indent=2)
            )
            html_content = html_content.replace('{{TITLE}}', DASHBOARD_TITLE)
            html_content = html_content.replace('{{SUBTITLE}}', DASHBOARD_SUBTITLE)
            html_content = html_content.replace(
                '{{LAST_UPDATED}}',
                datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            )
        
        # Save to output directory
        output_path = self.output_dir / "index.html"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info(f"Dashboard saved to: {output_path}")
        return output_path
    
    def _create_basic_template(self, data):
        """Create basic HTML template if template file not found"""
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{DASHBOARD_TITLE}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        .article {{
            border-bottom: 1px solid #eee;
            padding: 15px 0;
        }}
        .article:last-child {{
            border-bottom: none;
        }}
        .title {{
            font-size: 18px;
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 8px;
        }}
        .meta {{
            color: #7f8c8d;
            font-size: 14px;
            margin-bottom: 8px;
        }}
        .summary {{
            color: #34495e;
            line-height: 1.6;
        }}
        .sector {{
            display: inline-block;
            background: #3498db;
            color: white;
            padding: 3px 10px;
            border-radius: 3px;
            font-size: 12px;
            margin-right: 5px;
        }}
        a {{
            color: #3498db;
            text-decoration: none;
        }}
        a:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{DASHBOARD_TITLE}</h1>
        <p><strong>{DASHBOARD_SUBTITLE}</strong></p>
        <p>Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <hr>
"""
        
        for article in data[:50]:  # Show first 50 articles
            html += f"""
        <div class="article">
            <div class="title">{article['title_en']}</div>
            <div class="meta">
                <span class="sector">{article['sector']}</span>
                <span>{article['date']}</span> | 
                <span>{article['province']}</span> | 
                <a href="{article['url']}" target="_blank">Source: {article['source']}</a>
            </div>
            <div class="summary">{article['summary_en'][:200]}...</div>
        </div>
"""
        
        html += """
    </div>
</body>
</html>
"""
        
        return html
    
    def generate_statistics(self, articles):
        """Generate statistics"""
        
        stats = {
            'total': len(articles),
            'by_sector': {},
            'by_province': {},
            'by_source': {}
        }
        
        for article in articles:
            sector = article['sector'] or 'Unknown'
            province = article['province'] or 'Vietnam'
            source = article['source_name'] or 'Unknown'
            
            stats['by_sector'][sector] = stats['by_sector'].get(sector, 0) + 1
            stats['by_province'][province] = stats['by_province'].get(province, 0) + 1
            stats['by_source'][source] = stats['by_source'].get(source, 0) + 1
        
        logger.info(f"Statistics generated: {stats['total']} articles")
        return stats


def main():
    """Main execution"""
    
    import argparse
    
    parser = argparse.ArgumentParser(description='Dashboard Updater for Vietnam Infrastructure News')
    parser.add_argument('--output', type=str, help='Output directory')
    
    args = parser.parse_args()
    
    try:
        # Initialize updater
        updater = DashboardUpdater()
        
        # Load articles
        articles = updater.load_articles_from_db()
        
        if not articles:
            logger.warning("No articles found in database")
            print("Warning: No articles found. Creating empty dashboard.")
            articles = []
        
        # Generate dashboard data
        dashboard_data = updater.generate_dashboard_data(articles)
        
        # Generate HTML
        output_path = updater.generate_html(dashboard_data)
        
        # Generate statistics
        stats = updater.generate_statistics(articles)
        
        print(f"\n✓ Dashboard generated successfully!")
        print(f"  Output: {output_path}")
        print(f"  Total articles: {stats['total']}")
        print(f"  Sectors: {len(stats['by_sector'])}")
        print(f"  Provinces: {len(stats['by_province'])}")
        
    except Exception as e:
        logger.error(f"Error in main: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
