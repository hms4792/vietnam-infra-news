# 🚀 Vietnam Infra News Pipeline - 빠른 배포 가이드

## 📦 포함된 파일

```
vietnam-infra-pipeline.zip
├── config/settings.py         # 설정 파일
├── scripts/
│   ├── main.py               # 메인 실행
│   ├── news_collector.py     # 뉴스 수집
│   ├── ai_summarizer.py      # AI 요약
│   ├── dashboard_updater.py  # 대시보드/Excel 생성
│   └── notifier.py           # 알림 발송
├── .github/workflows/
│   └── daily_pipeline.yml    # 자동화 워크플로우
├── templates/
│   └── dashboard_template.html
├── .env.example
├── requirements.txt
└── README.md
```

---

## 🔧 1단계: GitHub 저장소 생성

1. GitHub에서 새 저장소 생성: `vietnam-infra-news`
2. 압축 파일 내용을 저장소에 업로드

```bash
# 로컬에서
unzip vietnam-infra-pipeline.zip
cd vietnam-infra-pipeline
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/vietnam-infra-news.git
git push -u origin main
```

---

## 🔑 2단계: API 키 설정

### Anthropic API (필수)
1. https://console.anthropic.com/ 가입
2. API Keys → Create Key
3. `sk-ant-xxx...` 형태의 키 저장

### Telegram Bot (선택)
1. Telegram에서 @BotFather 검색
2. `/newbot` 명령으로 봇 생성
3. Bot Token 저장 (예: `1234567890:ABC...`)
4. @userinfobot에서 Chat ID 확인

### Slack Webhook (선택)
1. https://api.slack.com/apps 접속
2. Create New App → From scratch
3. Incoming Webhooks 활성화
4. Webhook URL 복사

### Gmail App Password (선택)
1. Google 계정 → 보안 → 2단계 인증 활성화
2. https://myaccount.google.com/apppasswords
3. 앱 선택 → 기타 → 이름 입력
4. 생성된 16자리 비밀번호 저장

---

## ⚙️ 3단계: GitHub Secrets 설정

Repository → Settings → Secrets and variables → Actions → New repository secret

| Secret Name | 값 | 필수 |
|------------|---|:---:|
| `ANTHROPIC_API_KEY` | `sk-ant-xxx...` | ✅ |
| `TELEGRAM_BOT_TOKEN` | `1234567890:ABC...` | ⭕ |
| `TELEGRAM_CHAT_ID` | `123456789` | ⭕ |
| `SLACK_WEBHOOK_URL` | `https://hooks.slack.com/...` | ⭕ |
| `EMAIL_USERNAME` | `your@gmail.com` | ⭕ |
| `EMAIL_PASSWORD` | `xxxx xxxx xxxx xxxx` | ⭕ |
| `EMAIL_RECIPIENTS` | `user1@email.com,user2@email.com` | ⭕ |

---

## 🌐 4단계: GitHub Pages 활성화

1. Repository → Settings → Pages
2. Source: Deploy from a branch
3. Branch: `gh-pages` / `root`
4. Save

대시보드 URL: `https://YOUR_USERNAME.github.io/vietnam-infra-news/`

---

## ▶️ 5단계: 파이프라인 실행

### 수동 실행
1. Repository → Actions
2. "Daily News Pipeline" 선택
3. "Run workflow" 클릭
4. Run type 선택 (full/collect/summarize/output/notify)

### 자동 실행 스케줄
- 06:00 AM (베트남) - 아침 브리핑
- 12:00 PM (베트남) - 점심 업데이트
- 06:00 PM (베트남) - 저녁 업데이트

---

## 📱 알림 예시

### Telegram
```
🇻🇳 베트남 인프라 뉴스 일일 브리핑
📅 2025-12-19

📊 오늘의 요약:
• 총 수집 기사: 25건
• 환경 인프라: 12건
• 에너지 개발: 8건
• 도시 개발: 5건

🔥 주요 뉴스:
• Hanoi 폐수처리시설 확장 착공... (VnExpress)
• Binh Duong 태양광 발전소 상업운전... (Tuoi Tre)

🔗 대시보드: https://your-site.github.io/vietnam-infra-news/
```

---

## 🔍 로컬 테스트

```bash
# 1. 환경 설정
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. 환경변수 설정
cp .env.example .env
# .env 편집하여 API 키 입력

# 3. 실행
python scripts/main.py --full
```

---

## ❓ 문제 해결

### Actions 실패 시
1. Actions → 실패한 workflow 클릭
2. 로그 확인
3. Secrets 설정 확인

### 알림 미수신 시
- Telegram: Bot이 채팅방에 추가되었는지 확인
- Email: App Password가 정확한지 확인
- Slack: Webhook URL이 활성 상태인지 확인

### 대시보드 미표시 시
- GitHub Pages가 활성화되었는지 확인
- `gh-pages` 브랜치 존재 확인

---

## 📞 지원

- GitHub Issues: 버그 리포트 및 기능 요청
- README.md: 상세 문서

---

**🎉 파이프라인 구축 완료! 이제 베트남 인프라 뉴스를 자동으로 받아보세요.**
