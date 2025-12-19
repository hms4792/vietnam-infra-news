"""
Vietnam Infrastructure News Notifier
Sends notifications via Telegram, Email, Slack, and KakaoTalk
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
    NOTIFICATION_TEMPLATE, DATA_DIR
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class KakaoNotifier:
    """Send notifications via KakaoTalk"""
    
    def __init__(self, rest_api_key: str = None, refresh_token: str = None):
        self.rest_api_key = rest_api_key or KAKAO_REST_API_KEY
        self.refresh_token = refresh_token or KAKAO_REFRESH_TOKEN
        self.access_token = None
        self.token_file = DATA_DIR / "kakao_token.json"
    
    def get_auth_url(self) -> str:
        """Get Kakao OAuth authorization URL"""
        redirect_uri = "http://localhost:8080/callback"
        return f"https://kauth.kakao.com/oauth/authorize?client_id={self.rest_api_key}&redirect_uri={redirect_uri}&response_type=code&scope=talk_message"
    
    def get_token_from_code(self, auth_code: str) -> Optional[Dict]:
        """Exchange authorization code for tokens"""
        if not REQUESTS_AVAILABLE:
            logger.error("requests library not available")
            return None
        
        url = "https://kauth.kakao.com/oauth/token"
        data = {
            "grant_type": "authorization_code",
            "client_id": self.rest_api_key,
            "redirect_uri": "http://localhost:8080/callback",
            "code": auth_code
        }
        
        try:
            response = requests.post(url, data=data)
            if response.status_code == 200:
                tokens = response.json()
                self._save_tokens(tokens)
                logger.info("Kakao tokens obtained successfully")
                return tokens
            else:
                logger.error(f"Token error: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Kakao token error: {e}")
            return None
    
    def refresh_access_token(self) -> Optional[str]:
        """Refresh access token using refresh token"""
        if not self.refresh_token:
            self._load_tokens()
        
        if not self.refresh_token:
            logger.warning("No refresh token available")
            return None
        
        if not REQUESTS_AVAILABLE:
            logger.error("requests library not available")
            return None
        
        url = "https://kauth.kakao.com/oauth/token"
        data = {
            "grant_type": "refresh_token",
            "client_id": self.rest_api_key,
            "refresh_token": self.refresh_token
        }
        
        try:
            response = requests.post(url, data=data)
            if response.status_code == 200:
                tokens = response.json()
                self.access_token = tokens.get("access_token")
                
                if "refresh_token" in tokens:
                    self.refresh_token = tokens["refresh_token"]
                
                self._save_tokens(tokens)
                logger.info("Kakao access token refreshed")
                return self.access_token
            else:
                logger.error(f"Token refresh error: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Kakao refresh error: {e}")
            return None
    
    def _save_tokens(self, tokens: Dict):
        """Save tokens to file"""
        try:
            self.token_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.token_file, 'w') as f:
                json.dump({
                    "access_token": tokens.get("access_token"),
                    "refresh_token": tokens.get("refresh_token", self.refresh_token),
                    "updated_at": datetime.now().isoformat()
                }, f)
        except Exception as e:
            logger.error(f"Error saving tokens: {e}")
    
    def _load_tokens(self):
        """Load tokens from file"""
        try:
            if self.token_file.exists():
                with open(self.token_file) as f:
                    data = json.load(f)
                    self.access_token = data.get("access_token")
                    self.refresh_token = data.get("refresh_token")
        except Exception as e:
            logger.error(f"Error loading tokens: {e}")
    
    def send_message(self, message: str) -> bool:
        """Send message to KakaoTalk (to myself)"""
        if not self.rest_api_key:
            logger.warning("Kakao API key not configured")
            return False
        
        if not self.access_token:
            self._load_tokens()
        
        if not self.access_token:
            self.access_token = self.refresh_access_token()
        
        if not self.access_token:
            logger.warning("Cannot get Kakao access token")
            return False
        
        if not REQUESTS_AVAILABLE:
            logger.error("requests library not available")
            return False
        
        url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        template = {
            "object_type": "text",
            "text": message[:1000],
            "link": {
                "web_url": "https://github.com",
                "mobile_web_url": "https://github.com"
            },
            "button_title": "대시보드 보기"
        }
        
        data = {"template_object": json.dumps(template)}
        
        try:
            response = requests.post(url, headers=headers, data=data)
            
            if response.status_code == 200:
                logger.info("KakaoTalk message sent successfully")
                return True
            elif response.status_code == 401:
                logger.info("Token expired, refreshing...")
                self.access_token = self.refresh_access_token()
                if self.access_token:
                    return self.send_message(message)
                return False
            else:
                logger.error(f"Kakao send error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Kakao send error: {e}")
            return False


class TelegramNotifier:
    """Send notifications via Telegram"""
    
    def __init__(self, bot_token: str = None, chat_id: str = None):
        self.bot_token = bot_token or TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or TELEGRAM_CHAT_ID
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}"
    
    async def send_message(self, message: str, parse_mode: str = "HTML") -> bool:
        """Send message via Telegram"""
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram credentials not configured")
            return False
        
        if not AIOHTTP_AVAILABLE:
            return False
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.api_url}/sendMessage"
                data = {"chat_id": self.chat_id, "text": message, "parse_mode": parse_mode}
                
                async with session.post(url, json=data) as response:
                    if response.status == 200:
                        logger.info("Telegram message sent successfully")
                        return True
                    return False
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
            return False


class SlackNotifier:
    """Send notifications via Slack webhook"""
    
    def __init__(self, webhook_url: str = None):
        self.webhook_url = webhook_url or SLACK_WEBHOOK_URL
    
    async def send_message(self, message: str, blocks: List[Dict] = None) -> bool:
        """Send message via Slack webhook"""
        if not self.webhook_url:
            logger.warning("Slack webhook not configured")
            return False
        
        if not AIOHTTP_AVAILABLE:
            return False
        
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"text": message}
                if blocks:
                    payload["blocks"] = blocks
                
                async with session.post(self.webhook_url, json=payload) as response:
                    return response.status == 200
        except Exception as e:
            logger.error(f"Slack send error: {e}")
            return False
    
    def create_briefing_blocks(self, briefing_data: Dict) -> List[Dict]:
        """Create Slack blocks for briefing"""
        return [
            {"type": "header", "text": {"type": "plain_text", "text": "🇻🇳 Vietnam Infrastructure News"}},
            {"type": "section", "fields": [
                {"type": "mrkdwn", "text": f"*Total:* {briefing_data.get('total', 0)}"},
                {"type": "mrkdwn", "text": f"*Environment:* {briefing_data.get('env_count', 0)}"},
            ]}
        ]


class EmailNotifier:
    """Send notifications via Email"""
    
    def __init__(self):
        self.smtp_server = EMAIL_SMTP_SERVER
        self.smtp_port = EMAIL_SMTP_PORT
        self.username = EMAIL_USERNAME
        self.password = EMAIL_PASSWORD
        self.recipients = [r.strip() for r in EMAIL_RECIPIENTS if r.strip()]
    
    def send_email(self, subject: str, body: str, html_body: str = None) -> bool:
        """Send email notification"""
        if not self.username or not self.password or not self.recipients:
            logger.warning("Email credentials not configured")
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
            logger.error(f"Email send error: {e}")
            return False
    
    def create_html_briefing(self, briefing_data: Dict) -> str:
        """Create HTML email body"""
        return f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
        .header {{ background: linear-gradient(135deg, #0d9488, #10b981); color: white; padding: 20px; border-radius: 10px 10px 0 0; }}
        .content {{ background: #f8fafc; padding: 20px; border-radius: 0 0 10px 10px; }}
        .stat-box {{ display: inline-block; background: white; padding: 15px; margin: 5px; border-radius: 8px; min-width: 100px; text-align: center; }}
        .stat-number {{ font-size: 24px; font-weight: bold; color: #0d9488; }}
        .news-item {{ background: white; padding: 12px; margin: 8px 0; border-radius: 6px; border-left: 4px solid #0d9488; }}
        .btn {{ display: inline-block; background: #0d9488; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; }}
    </style>
</head>
<body>
    <div style="max-width: 600px; margin: 0 auto;">
        <div class="header">
            <h1 style="margin:0;">🇻🇳 Vietnam Infra News</h1>
            <p style="margin:5px 0 0;">Daily Briefing - {briefing_data.get('date')}</p>
        </div>
        <div class="content">
            <div class="stat-box"><div class="stat-number">{briefing_data.get('total', 0)}</div><div>Total</div></div>
            <div class="stat-box"><div class="stat-number">{briefing_data.get('env_count', 0)}</div><div>Environment</div></div>
            <div class="stat-box"><div class="stat-number">{briefing_data.get('energy_count', 0)}</div><div>Energy</div></div>
            <div class="stat-box"><div class="stat-number">{briefing_data.get('urban_count', 0)}</div><div>Urban</div></div>
            
            <h3>🔥 Top News</h3>
            {briefing_data.get('top_news_html', '')}
            
            <p style="text-align:center; margin-top:30px;">
                <a href="{briefing_data.get('dashboard_url', '#')}" class="btn">📊 View Dashboard</a>
            </p>
        </div>
    </div>
</body>
</html>
"""


class NotificationManager:
    """Manages all notification channels"""
    
    def __init__(self):
        self.telegram = TelegramNotifier()
        self.slack = SlackNotifier()
        self.email = EmailNotifier()
        self.kakao = KakaoNotifier()
    
    def prepare_briefing_data(self, articles: List[Dict], dashboard_url: str = "") -> Dict:
        """Prepare briefing data from articles"""
        area_counts = {"Environment": 0, "Energy Develop.": 0, "Urban Develop.": 0}
        
        for article in articles:
            area = article.get("area", "")
            if area in area_counts:
                area_counts[area] += 1
        
        top_articles = articles[:5]
        top_news_text = "\n".join([
            f"• {a.get('title', '')[:60]}... ({a.get('source', '')})"
            for a in top_articles
        ])
        
        top_news_html = "\n".join([
            f'<div class="news-item"><strong>{a.get("title", "")[:80]}</strong><br><small>{a.get("source", "")} | {a.get("published", "")}</small></div>'
            for a in top_articles
        ])
        
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "total": len(articles),
            "env_count": area_counts["Environment"],
            "energy_count": area_counts["Energy Develop."],
            "urban_count": area_counts["Urban Develop."],
            "top_news": top_news_text,
            "top_news_html": top_news_html,
            "dashboard_url": dashboard_url
        }
    
    async def send_all(self, articles: List[Dict], dashboard_url: str = "", lang: str = "ko") -> Dict[str, bool]:
        """Send notifications to all channels"""
        results = {}
        
        briefing_data = self.prepare_briefing_data(articles, dashboard_url)
        
        template = NOTIFICATION_TEMPLATE.get(lang, NOTIFICATION_TEMPLATE["ko"])
        message = template.format(**briefing_data)
        
        # Send Telegram
        results["telegram"] = await self.telegram.send_message(message)
        
        # Send Slack
        blocks = self.slack.create_briefing_blocks(briefing_data)
        results["slack"] = await self.slack.send_message(message, blocks)
        
        # Send Email
        html_body = self.email.create_html_briefing(briefing_data)
        results["email"] = self.email.send_email(
            subject=f"🇻🇳 Vietnam Infra News - {briefing_data['date']}",
            body=message,
            html_body=html_body
        )
        
        # Send KakaoTalk
        kakao_message = f"""🇻🇳 베트남 인프라 뉴스
📅 {briefing_data['date']}

📊 총 {briefing_data['total']}건
• 환경: {briefing_data['env_count']}건
• 에너지: {briefing_data['energy_count']}건
• 도시: {briefing_data['urban_count']}건

{briefing_data['top_news'][:300]}"""
        results["kakao"] = self.kakao.send_message(kakao_message)
        
        logger.info(f"Notification results: {results}")
        return results


def setup_kakao_auth():
    """Interactive setup for Kakao authentication"""
    print("\n" + "="*50)
    print("🔐 카카오톡 알림 설정")
    print("="*50)
    
    kakao = KakaoNotifier()
    
    if not kakao.rest_api_key:
        print("❌ KAKAO_REST_API_KEY가 설정되지 않았습니다.")
        return
    
    print("\n1️⃣  아래 URL을 브라우저에서 열어주세요:\n")
    print(f"   {kakao.get_auth_url()}\n")
    
    print("2️⃣  카카오 로그인 후 '동의하고 계속하기' 클릭")
    print("3️⃣  리다이렉트된 URL에서 'code=' 뒤의 값을 복사")
    print("   예: http://localhost:8080/callback?code=XXXXX\n")
    
    auth_code = input("인증 코드를 입력하세요: ").strip()
    
    if auth_code:
        tokens = kakao.get_token_from_code(auth_code)
        if tokens:
            print("\n✅ 카카오톡 인증 완료!")
            print(f"   토큰이 {kakao.token_file}에 저장되었습니다.")
            
            test = input("\n테스트 메시지를 보내시겠습니까? (y/n): ").strip().lower()
            if test == 'y':
                kakao.access_token = tokens.get('access_token')
                if kakao.send_message("🎉 베트남 인프라 뉴스 카카오톡 알림 설정 완료!"):
                    print("✅ 테스트 메시지 전송 성공!")
                else:
                    print("❌ 테스트 메시지 전송 실패")
        else:
            print("\n❌ 토큰 발급 실패")
    else:
        print("취소되었습니다.")


def load_latest_articles() -> List[Dict]:
    """Load latest processed articles"""
    processed_files = sorted(DATA_DIR.glob("processed_*.json"), reverse=True)
    
    if not processed_files:
        news_files = sorted(DATA_DIR.glob("news_*.json"), reverse=True)
        if not news_files:
            return []
        processed_files = news_files
    
    try:
        with open(processed_files[0], 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("articles", [])
    except Exception as e:
        logger.error(f"Error loading articles: {e}")
        return []


async def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Send notifications")
    parser.add_argument('--setup-kakao', action='store_true', help='Setup Kakao authentication')
    parser.add_argument('--test-email', action='store_true', help='Test email sending')
    parser.add_argument('--test-kakao', action='store_true', help='Test KakaoTalk sending')
    args = parser.parse_args()
    
    if args.setup_kakao:
        setup_kakao_auth()
        return
    
    if args.test_email:
        email = EmailNotifier()
        if email.send_email(
            subject="🧪 테스트: Vietnam Infra News",
            body="이메일 알림 테스트입니다.",
            html_body="<h1>테스트</h1><p>이메일 알림이 정상적으로 작동합니다.</p>"
        ):
            print("✅ 이메일 테스트 성공!")
        else:
            print("❌ 이메일 테스트 실패")
        return
    
    if args.test_kakao:
        kakao = KakaoNotifier()
        if kakao.send_message("🧪 테스트: 베트남 인프라 뉴스"):
            print("✅ 카카오톡 테스트 성공!")
        else:
            print("❌ 카카오톡 테스트 실패")
        return
    
    articles = load_latest_articles()
    
    if not articles:
        print("No articles found.")
        return
    
    manager = NotificationManager()
    results = await manager.send_all(articles, "", "ko")
    
    print(f"\n{'='*50}")
    print("Notification Results")
    print(f"{'='*50}")
    for channel, success in results.items():
        status = "✅ Sent" if success else "❌ Failed"
        print(f"{channel.capitalize()}: {status}")


if __name__ == "__main__":
    asyncio.run(main())
