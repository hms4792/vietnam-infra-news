"""
Vietnam Infrastructure News Notifier
"""
import asyncio
import json
import logging
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from typing import Dict, List, Optional
from collections import Counter
import sys
sys.path.append(str(Path(__file__).parent.parent))

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

from config.settings import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    SLACK_WEBHOOK_URL,
    EMAIL_SMTP_SERVER, EMAIL_SMTP_PORT,
    EMAIL_USERNAME, EMAIL_PASSWORD, EMAIL_RECIPIENTS,
    KAKAO_REST_API_KEY, KAKAO_REFRESH_TOKEN,
    DATA_DIR
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DASHBOARD_URL = "https://hms4792.github.io/vietnam-infra-news/"


class KakaoNotifier:
    def __init__(self):
        self.rest_api_key = KAKAO_REST_API_KEY
        self.refresh_token = KAKAO_REFRESH_TOKEN
        self.access_token = None
        self.token_file = DATA_DIR / "kakao_token.json"
    
    def send_message(self, message: str) -> bool:
        if not self.rest_api_key:
            return False
        if not self.access_token:
            self._load_tokens()
        if not self.access_token:
            self.access_token = self.refresh_access_token()
        if not self.access_token or not REQUESTS_AVAILABLE:
            return False
        
        url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/x-www-form-urlencoded"}
        template = {"object_type": "text", "text": message[:1000], "link": {"web_url": DASHBOARD_URL}, "button_title": "View Dashboard"}
        
        try:
            response = requests.post(url, headers=headers, data={"template_object": json.dumps(template)})
            if response.status_code == 200:
                return True
        except:
            pass
        return False
    
    def refresh_access_token(self):
        if not self.refresh_token:
            self._load_tokens()
        if not self.refresh_token or not REQUESTS_AVAILABLE:
            return None
        try:
            response = requests.post("https://kauth.kakao.com/oauth/token", data={
                "grant_type": "refresh_token", "client_id": self.rest_api_key, "refresh_token": self.refresh_token
            })
            if response.status_code == 200:
                tokens = response.json()
                self.access_token = tokens.get("access_token")
                if "refresh_token" in tokens:
                    self.refresh_token = tokens["refresh_token"]
                self._save_tokens(tokens)
                return self.access_token
        except:
            pass
        return None
    
    def _save_tokens(self, tokens):
        try:
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_file, 'w') as f:
                json.dump({"access_token": tokens.get("access_token"), "refresh_token": tokens.get("refresh_token", self.refresh_token)}, f)
        except:
            pass
    
    def _load_tokens(self):
        try:
            if self.token_file.exists():
                with open(self.token_file) as f:
                    data = json.load(f)
                    self.access_token = data.get("access_token")
                    self.refresh_token = data.get("refresh_token")
        except:
            pass


class TelegramNotifier:
    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
    
    async def send_message(self, message: str) -> bool:
        if not self.bot_token or not self.chat_id or not AIOHTTP_AVAILABLE:
            return False
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                                       json={"chat_id": self.chat_id, "text": message}) as resp:
                    return resp.status == 200
        except:
            return False


class SlackNotifier:
    def __init__(self):
        self.webhook_url = SLACK_WEBHOOK_URL
    
    async def send_message(self, message: str) -> bool:
        if not self.webhook_url or not AIOHTTP_AVAILABLE:
            return False
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json={"text": message}) as resp:
                    return resp.status == 200
        except:
            return False


class EmailNotifier:
    def __init__(self):
        self.smtp_server = EMAIL_SMTP_SERVER
        self.smtp_port = EMAIL_SMTP_PORT
        self.username = EMAIL_USERNAME
        self.password = EMAIL_PASSWORD
        self.recipients = [r.strip() for r in EMAIL_RECIPIENTS if r.strip()]
    
    def send_email(self, subject: str, body: str, html_body: str = None) -> bool:
        if not self.username or not self.password or not self.recipients:
            return False
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.username
            msg['To'] = ', '.join(self.recipients)
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            if html_body:
                msg.attach(MIMEText(html_body, 'html', 'utf-8'))
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)
            
            logger.info(f"Email sent to {len(self.recipients)} recipients")
            return True
        except Exception as e:
            logger.error(f"Email error: {e}")
            return False
    
    def create_html_briefing(self, data: Dict) -> str:
        today_str = data.get("today_str", datetime.now().strftime("%Y-%m-%d"))
        
        area_sector_rows = ""
        for area_name, area_data in data.get("area_sector_breakdown", {}).items():
            sector_list = ", ".join([f"{s}: {c}" for s, c in area_data["sectors"].items()])
            area_sector_rows += f'''<tr>
                <td style="padding:8px;border-bottom:1px solid #e5e7eb;">{area_name}</td>
                <td style="padding:8px;border-bottom:1px solid #e5e7eb;text-align:center;font-weight:bold;">{area_data["total"]}</td>
                <td style="padding:8px;border-bottom:1px solid #e5e7eb;font-size:12px;color:#666;">{sector_list}</td>
            </tr>'''
        
        province_rows = ""
        for province, count in data.get("top_provinces", []):
            province_rows += f'''<tr>
                <td style="padding:6px 8px;border-bottom:1px solid #e5e7eb;">{province}</td>
                <td style="padding:6px 8px;border-bottom:1px solid #e5e7eb;text-align:center;font-weight:bold;">{count}</td>
            </tr>'''
        
        vietnam_count = data.get("vietnam_count", 0)
        
        top_news_html = ""
        for article in data.get("today_articles", [])[:5]:
            province = article.get("province", "Vietnam")
            title = article.get("summary_en", article.get("title", ""))[:80]
            source = article.get("source", "")
            date = str(article.get("published", article.get("date", "")))[:10]
            top_news_html += f'''<div style="background:#f8fafc;padding:10px 12px;margin:6px 0;border-radius:6px;border-left:4px solid #0d9488;font-size:13px;">
                <strong style="color:#0d9488;">[{province}]</strong> {title}<br>
                <small style="color:#888;">{date} | {source}</small>
            </div>'''
        
        if not top_news_html:
            top_news_html = '<p style="color:#666;font-size:13px;">No articles collected today.</p>'
        
        return f'''<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5;">
    <div style="max-width: 600px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, #0d9488, #10b981); color: white; padding: 20px; border-radius: 12px 12px 0 0;">
            <h1 style="margin:0; font-size: 22px;">🇻🇳 Vietnam Infrastructure News</h1>
            <p style="margin:5px 0 0; opacity: 0.9; font-size:14px;">Daily Briefing - {data.get('date', '')}</p>
        </div>
        
        <div style="background: white; padding: 20px; border-radius: 0 0 12px 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            
            <div style="background:#f0fdfa; border:1px solid #99f6e4; border-radius:10px; padding:15px; margin-bottom:20px;">
                <h2 style="margin:0 0 15px 0; font-size:16px; color:#0d9488;">📊 Daily Summary ({today_str})</h2>
                
                <table style="width:100%; margin-bottom:15px;">
                    <tr>
                        <td style="font-size:14px; color:#333;">Today's Articles</td>
                        <td style="text-align:right; font-size:28px; font-weight:bold; color:#0d9488;">{data.get('today_count', 0)}</td>
                    </tr>
                    <tr>
                        <td style="font-size:12px; color:#888;">Total Database</td>
                        <td style="text-align:right; font-size:14px; color:#888;">{data.get('total', 0)}</td>
                    </tr>
                </table>
                
                <div style="font-size:13px; font-weight:bold; color:#555; margin:10px 0 5px;">📁 By Area / Sector (Today)</div>
                <table style="width:100%; border-collapse:collapse; font-size:13px;">
                    <tr style="background:#e6fffa;">
                        <th style="padding:8px;text-align:left;border-bottom:2px solid #0d9488;">Area</th>
                        <th style="padding:8px;text-align:center;border-bottom:2px solid #0d9488;">Count</th>
                        <th style="padding:8px;text-align:left;border-bottom:2px solid #0d9488;">Sectors</th>
                    </tr>
                    {area_sector_rows if area_sector_rows else '<tr><td colspan="3" style="padding:8px;color:#999;">No data</td></tr>'}
                </table>
                
                <div style="font-size:13px; font-weight:bold; color:#555; margin:15px 0 5px;">📍 Top Provinces (Today)</div>
                <table style="width:100%; border-collapse:collapse; font-size:13px;">
                    {province_rows if province_rows else '<tr><td colspan="2" style="padding:6px 8px;color:#999;">No specific province</td></tr>'}
                    <tr style="background:#f5f5f5;">
                        <td style="padding:6px 8px;color:#888;">Vietnam (Common)</td>
                        <td style="padding:6px 8px;text-align:center;color:#888;">{vietnam_count}</td>
                    </tr>
                </table>
            </div>
            
            <h3 style="color:#333; margin:20px 0 10px; font-size:15px;">🔥 Today's Top News</h3>
            {top_news_html}
            
            <div style="text-align: center; margin-top: 25px;">
                <a href="{DASHBOARD_URL}" style="display:inline-block; background:#0d9488; color:white; padding:12px 24px; text-decoration:none; border-radius:8px; font-weight:bold; font-size:14px;">📊 View Dashboard</a>
            </div>
        </div>
    </div>
</body>
</html>'''


class NotificationManager:
    def __init__(self):
        self.telegram = TelegramNotifier()
        self.slack = SlackNotifier()
        self.email = EmailNotifier()
        self.kakao = KakaoNotifier()
    
    def prepare_briefing_data(self, articles: List[Dict]) -> Dict:
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        today_articles = []
        for article in articles:
            article_date = str(article.get("published", article.get("date", article.get("Date", ""))))[:10]
            if article_date == today_str:
                today_articles.append(article)
        
        area_sector = {
            "Environment": {"total": 0, "sectors": Counter()},
            "Energy Develop.": {"total": 0, "sectors": Counter()},
            "Urban Develop.": {"total": 0, "sectors": Counter()}
        }
        
        province_counts = Counter()
        vietnam_count = 0
        
        for article in today_articles:
            area = article.get("area", article.get("Area", ""))
            sector = article.get("sector", article.get("Business Sector", "Unknown"))
            province = article.get("province", article.get("Province", "Vietnam"))
            
            if area in area_sector:
                area_sector[area]["total"] += 1
                area_sector[area]["sectors"][sector] += 1
            
            if province == "Vietnam":
                vietnam_count += 1
            else:
                province_counts[province] += 1
        
        top_provinces = province_counts.most_common(3)
        
        area_sector_breakdown = {}
        for area, data in area_sector.items():
            if data["total"] > 0:
                area_sector_breakdown[area] = {
                    "total": data["total"],
                    "sectors": dict(data["sectors"].most_common(5))
                }
        
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "today_str": today_str,
            "total": len(articles),
            "today_count": len(today_articles),
            "today_articles": today_articles,
            "area_sector_breakdown": area_sector_breakdown,
            "top_provinces": top_provinces,
            "vietnam_count": vietnam_count,
            "dashboard_url": DASHBOARD_URL
        }
    
    async def send_all(self, articles: List[Dict], dashboard_url: str = "", lang: str = "en") -> Dict[str, bool]:
        results = {}
        data = self.prepare_briefing_data(articles)
        
        message = f"""Vietnam Infrastructure News
{data['date']}

Today: {data['today_count']} articles
Total: {data['total']} articles

Dashboard: {DASHBOARD_URL}"""
        
        results["telegram"] = await self.telegram.send_message(message)
        results["slack"] = await self.slack.send_message(message)
        
        html_body = self.email.create_html_briefing(data)
        results["email"] = self.email.send_email(
            subject=f"Vietnam Infra News - {data['date']} ({data['today_count']} new articles)",
            body=message,
            html_body=html_body
        )
        
        results["kakao"] = self.kakao.send_message(message)
        
        logger.info(f"Notification results: {results}")
        return results


def load_latest_articles() -> List[Dict]:
    processed_files = sorted(DATA_DIR.glob("processed_*.json"), reverse=True)
    if not processed_files:
        news_files = sorted(DATA_DIR.glob("news_*.json"), reverse=True)
        if not news_files:
            return []
        processed_files = news_files
    
    try:
        with open(processed_files[0], 'r', encoding='utf-8') as f:
            return json.load(f).get("articles", [])
    except:
        return []


async def main():
    articles = load_latest_articles()
    if not articles:
        print("No articles found.")
        return
    
    manager = NotificationManager()
    results = await manager.send_all(articles)
    
    print(f"\nResults:")
    for channel, success in results.items():
        print(f"  {channel}: {'OK' if success else 'FAIL'}")


if __name__ == "__main__":
    asyncio.run(main())
