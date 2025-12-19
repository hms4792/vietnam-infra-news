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
            logger.warning("Kakao API key not configured")
            return False
        if not self.access_token:
            self._load_tokens()
        if not self.access_token:
            self.access_token = self.refresh_access_token()
        if not self.access_token or not REQUESTS_AVAILABLE:
            logger.warning("Cannot get Kakao access token")
            return False
        
        url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
        headers = {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/x-www-form-urlencoded"}
        template = {"object_type": "text", "text": message[:1000], "link": {"web_url": DASHBOARD_URL}, "button_title": "View Dashboard"}
        
        try:
            response = requests.post(url, headers=headers, data={"template_object": json.dumps(template)})
            if response.status_code == 200:
                logger.info("KakaoTalk message sent")
                return True
            return False
        except Exception as e:
            logger.error(f"Kakao error: {e}")
            return False
    
    def refresh_access_token(self) -> Optional[str]:
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
    
    def _save_tokens(self, tokens: Dict):
        try:
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_file, 'w') as f:
                json.dump({"access_token": tokens.get("access_token"), "refresh_token": tokens.get("refresh_token", self.refresh_token)}, f)
        except: pass
    
    def _load_tokens(self):
        try:
            if self.token_file.exists():
                with open(self.token_file) as f:
                    data = json.load(f)
                    self.access_token = data.get("access_token")
                    self.refresh_token = data.get("refresh_token")
        except: pass


class TelegramNotifier:
    def __init__(self):
        self.bot_token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
    
    async def send_message(self, message: str) -> bool:
        if not self.bot_token or not self.chat_id or not AIOHTTP_AVAILABLE:
            logger.warning("Telegram not configured")
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
            logger.warning("Slack not configured")
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
            logger.warning("Email not configured")
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
        # Top news with [Province] prefix
        top_news_html = ""
        for article in data.get("top_articles", [])[:5]:
            province = article.get("province", "Vietnam")
            title = article.get("summary_en", article.get("title", ""))[:80]
            source = article.get("source", "")
            date = article.get("published", "")
            top_news_html += f'''<div style="background:#f8fafc;padding:12px;margin:8px 0;border-radius:6px;border-left:4px solid #0d9488;">
                <strong>[{province}]</strong> {title}<br>
                <small style="color:#666;">{source} | {date}</small>
            </div>'''
        
        # Sector stats
        sector_html = ""
        for sector, count in data.get("sector_counts", {}).items():
            if count > 0:
                sector_html += f'<div style="display:inline-block;background:#f0fdfa;padding:8px 12px;margin:4px;border-radius:6px;"><strong>{count}</strong> <span style="color:#666;font-size:12px;">{sector}</span></div>'
        
        # Province stats (top 5)
        province_html = ""
        for province, count in list(data.get("province_counts", {}).items())[:5]:
            if count > 0:
                province_html += f'<div style="display:inline-block;background:#ede9fe;padding:8px 12px;margin:4px;border-radius:6px;"><strong>{count}</strong> <span style="color:#666;font-size:12px;">{province}</span></div>'
        
        return f'''<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5;">
    <div style="max-width: 650px; margin: 0 auto;">
        <div style="background: linear-gradient(135deg, #0d9488, #10b981); color: white; padding: 25px; border-radius: 12px 12px 0 0;">
            <h1 style="margin:0; font-size: 24px;">🇻🇳 Vietnam Infrastructure News</h1>
            <p style="margin:8px 0 0; opacity: 0.9;">Daily Briefing Report - {data.get('date', '')}</p>
        </div>
        
        <div style="background: white; padding: 25px; border-radius: 0 0 12px 12px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            
            <!-- Summary Section -->
            <h2 style="color: #333; margin-top: 0; border-bottom: 2px solid #0d9488; padding-bottom: 10px;">📊 Summary</h2>
            
            <!-- Total -->
            <div style="text-align:center; margin: 20px 0;">
                <div style="display:inline-block; background:linear-gradient(135deg, #0d9488, #10b981); color:white; padding:20px 40px; border-radius:12px;">
                    <div style="font-size:48px; font-weight:bold;">{data.get('total', 0)}</div>
                    <div style="font-size:14px; opacity:0.9;">Total Articles Collected</div>
                </div>
            </div>
            
            <!-- By Area -->
            <h3 style="color: #555; margin-top: 25px;">📁 By Area</h3>
            <div style="display: flex; flex-wrap: wrap; gap: 10px; margin: 15px 0;">
                <div style="flex:1; min-width:120px; background:#ecfdf5; padding:15px; border-radius:8px; text-align:center;">
                    <div style="font-size:28px; font-weight:bold; color:#059669;">{data.get('env_count', 0)}</div>
                    <div style="font-size:12px; color:#666;">Environment</div>
                </div>
                <div style="flex:1; min-width:120px; background:#fef3c7; padding:15px; border-radius:8px; text-align:center;">
                    <div style="font-size:28px; font-weight:bold; color:#d97706;">{data.get('energy_count', 0)}</div>
                    <div style="font-size:12px; color:#666;">Energy</div>
                </div>
                <div style="flex:1; min-width:120px; background:#ede9fe; padding:15px; border-radius:8px; text-align:center;">
                    <div style="font-size:28px; font-weight:bold; color:#7c3aed;">{data.get('urban_count', 0)}</div>
                    <div style="font-size:12px; color:#666;">Urban Dev</div>
                </div>
            </div>
            
            <!-- By Sector -->
            <h3 style="color: #555; margin-top: 25px;">🏭 By Sector</h3>
            <div style="margin: 10px 0;">{sector_html if sector_html else '<span style="color:#999;">No data</span>'}</div>
            
            <!-- By Province -->
            <h3 style="color: #555; margin-top: 25px;">📍 Top Provinces</h3>
            <div style="margin: 10px 0;">{province_html if province_html else '<span style="color:#999;">No data</span>'}</div>
            
            <!-- Top News -->
            <h2 style="color: #333; margin-top: 30px; border-bottom: 2px solid #0d9488; padding-bottom: 10px;">🔥 Top News</h2>
            {top_news_html if top_news_html else '<p style="color:#666;">No articles collected today.</p>'}
            
            <!-- Dashboard Button -->
            <div style="text-align: center; margin-top: 30px;">
                <a href="{DASHBOARD_URL}" style="display:inline-block; background:#0d9488; color:white; padding:14px 28px; text-decoration:none; border-radius:8px; font-weight:bold;">📊 View Full Dashboard</a>
            </div>
            
            <p style="text-align:center; margin-top:20px; font-size:12px; color:#999;">
                Automated report from Vietnam Infrastructure News Pipeline
            </p>
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
        # Area counts
        area_counts = {"Environment": 0, "Energy Develop.": 0, "Urban Develop.": 0}
        sector_counts = Counter()
        province_counts = Counter()
        
        for article in articles:
            area = article.get("area", "")
            if area in area_counts:
                area_counts[area] += 1
            
            sector = article.get("sector", "Unknown")
            sector_counts[sector] += 1
            
            province = article.get("province", "Unknown")
            province_counts[province] += 1
        
        # Sort by count descending
        sector_counts = dict(sector_counts.most_common(10))
        province_counts = dict(province_counts.most_common(10))
        
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "total": len(articles),
            "total_articles": len(articles),
            "env_count": area_counts["Environment"],
            "energy_count": area_counts["Energy Develop."],
            "urban_count": area_counts["Urban Develop."],
            "sector_counts": sector_counts,
            "province_counts": province_counts,
            "top_articles": articles[:5],
            "dashboard_url": DASHBOARD_URL
        }
    
    async def send_all(self, articles: List[Dict], dashboard_url: str = "", lang: str = "en") -> Dict[str, bool]:
        results = {}
        data = self.prepare_briefing_data(articles)
        
        # Plain text message
        message = f"""🇻🇳 Vietnam Infrastructure News
📅 {data['date']}

📊 Summary:
- Total: {data['total']} articles
- Environment: {data['env_count']}
- Energy: {data['energy_count']}
- Urban: {data['urban_count']}

🔗 Dashboard: {DASHBOARD_URL}"""
        
        results["telegram"] = await self.telegram.send_message(message)
        results["slack"] = await self.slack.send_message(message)
        
        # Email
        html_body = self.email.create_html_briefing(data)
        results["email"] = self.email.send_email(
            subject=f"🇻🇳 Vietnam Infra News - {data['date']} ({data['total']} articles)",
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
        print(f"  {channel}: {'✅' if success else '❌'}")


if __name__ == "__main__":
    asyncio.run(main())
