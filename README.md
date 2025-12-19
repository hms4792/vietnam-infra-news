# 🇻🇳 Vietnam Infrastructure News Pipeline

베트남 인프라 뉴스를 자동으로 수집, AI 요약, 대시보드 업데이트 및 알림 발송하는 완전 자동화 파이프라인입니다.

## 📋 주요 기능

| 기능 | 설명 |
|------|------|
| 🔍 **뉴스 수집** | 베트남 주요 뉴스 소스에서 인프라 관련 기사 자동 수집 |
| 🤖 **AI 요약** | Claude API를 통한 한국어/영어/베트남어 3개국어 요약 |
| 📊 **대시보드** | 실시간 업데이트되는 인터랙티브 HTML 대시보드 |
| 📱 **알림** | Telegram, Slack, Email을 통한 일일 브리핑 발송 |
| 📅 **자동화** | GitHub Actions를 통한 매일 3회 자동 실행 |

## 🏗️ 프로젝트 구조

```
vietnam-infra-pipeline/
├── 📁 .github/workflows/    # GitHub Actions 자동화
│   └── daily_pipeline.yml   # 일일 파이프라인 워크플로우
├── 📁 config/               # 설정 파일
│   └── settings.py          # 파이프라인 설정
├── 📁 scripts/              # 핵심 스크립트
│   ├── main.py              # 메인 실행 파일
│   ├── news_collector.py    # 뉴스 수집
│   ├── ai_summarizer.py     # AI 요약 생성
│   ├── dashboard_updater.py # 대시보드/Excel 업데이트
│   └── notifier.py          # 알림 발송
├── 📁 data/                 # 수집된 데이터 (JSON)
├── 📁 outputs/              # 생성된 산출물
│   ├── vietnam_dashboard.html
│   └── vietnam_infra_news_database.xlsx
├── 📁 templates/            # HTML 템플릿
├── 📁 logs/                 # 실행 로그
├── .env.example             # 환경변수 템플릿
├── requirements.txt         # Python 의존성
└── README.md
```

## 🚀 빠른 시작

### 1. 저장소 클론

```bash
git clone https://github.com/YOUR_USERNAME/vietnam-infra-pipeline.git
cd vietnam-infra-pipeline
```

### 2. 환경 설정

```bash
# 가상환경 생성
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
# .env 파일을 편집하여 API 키 입력
```

### 3. 파이프라인 실행

```bash
# 전체 파이프라인 실행
python scripts/main.py --full

# 개별 단계 실행
python scripts/main.py --collect      # 뉴스 수집만
python scripts/main.py --summarize    # AI 요약만
python scripts/main.py --output       # 출력 생성만
python scripts/main.py --notify       # 알림 발송만
```

## ⚙️ 설정

### 환경 변수

| 변수 | 설명 | 필수 |
|------|------|:----:|
| `ANTHROPIC_API_KEY` | Claude API 키 | ✅ |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot 토큰 | ⭕ |
| `TELEGRAM_CHAT_ID` | Telegram 채팅 ID | ⭕ |
| `SLACK_WEBHOOK_URL` | Slack Webhook URL | ⭕ |
| `EMAIL_USERNAME` | 이메일 계정 | ⭕ |
| `EMAIL_PASSWORD` | 이메일 앱 비밀번호 | ⭕ |
| `EMAIL_RECIPIENTS` | 수신자 목록 (콤마 구분) | ⭕ |

### GitHub Secrets 설정 (자동화용)

1. Repository → Settings → Secrets and variables → Actions
2. 위 환경 변수들을 Repository secrets로 추가

## 📅 자동화 스케줄

GitHub Actions를 통해 다음 시간에 자동 실행됩니다:

| 시간 (베트남) | UTC | 설명 |
|--------------|-----|------|
| 06:00 AM | 23:00 | 아침 브리핑 |
| 12:00 PM | 05:00 | 점심 업데이트 |
| 06:00 PM | 11:00 | 저녁 업데이트 |

수동 실행: Actions → Daily News Pipeline → Run workflow

## 📱 알림 설정

### Telegram 설정

1. [@BotFather](https://t.me/BotFather)에서 봇 생성
2. 봇 토큰 저장
3. [@userinfobot](https://t.me/userinfobot)에서 Chat ID 확인
4. 환경변수에 설정

### Slack 설정

1. [Slack API](https://api.slack.com/messaging/webhooks)에서 Incoming Webhook 생성
2. Webhook URL 저장
3. 환경변수에 설정

### Email 설정 (Gmail)

1. Google 계정 → 보안 → 2단계 인증 활성화
2. [앱 비밀번호](https://myaccount.google.com/apppasswords) 생성
3. 환경변수에 설정

## 📊 산출물

### 1. HTML 대시보드
- 인터랙티브 뉴스 목록
- AI 브리핑 (음성 지원)
- KPI 및 차트
- 3개국어 지원

### 2. Excel 데이터베이스
- 전체 기사 데이터
- 요약 통계
- 연도별/섹터별 분류

### 3. JSON 데이터
- API 연동용 구조화된 데이터
- 일일 수집 로그

## 🔧 개발

### 테스트 실행

```bash
pytest tests/
```

### 코드 포맷팅

```bash
black scripts/
flake8 scripts/
```

## 📈 뉴스 소스

| 소스 | 유형 | URL |
|------|------|-----|
| VnExpress | RSS + 검색 | vnexpress.net |
| VietnamNews | RSS + 검색 | vietnamnews.vn |
| VnEconomy | 검색 | vneconomy.vn |
| Tuoi Tre | RSS | tuoitre.vn |
| Thanh Nien | 검색 | thanhnien.vn |

## 📝 라이선스

MIT License

## 🤝 기여

이슈 및 PR 환영합니다!

---

**문의**: [GitHub Issues](https://github.com/YOUR_USERNAME/vietnam-infra-pipeline/issues)
