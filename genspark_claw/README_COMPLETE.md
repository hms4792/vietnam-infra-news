# Vietnam Infrastructure News Pipeline - Claw 완전 전환 버전

> SA-Sub_AGENT_v2.1 모든 기능 100% 재현  
> **상태: 설치 완료 / API 재개 대기 중 (2026-05-01)**

---

## 현재 상태

| 구성 요소 | 상태 |
|-----------|------|
| 환경 설정 (.env) | ✅ 완료 |
| Python venv + 패키지 | ✅ 완료 |
| Agent 1~5 (수집→QC) | ✅ 구현 완료 (API 재개 후 full 실행) |
| Step 5-A 보고서 생성 | ✅ 테스트 완료 |
| Step 5-B 대시보드 | ✅ 테스트 완료 |
| Step 5-C GitHub 업로드 | ✅ 테스트 완료 |
| Step 5-D 이메일 발송 | ✅ 테스트 완료 |
| Anthropic API | ⏳ 2026-05-01 재개 예정 |
| 자동 실행 Cron | ✅ 2026-05-01 11:00 UTC 등록 완료 |

---

## 빠른 실행

```bash
cd /home/work/claw
source venv/bin/activate
python main_complete.py
```

---

## 파일 구조

```
/home/work/claw/
├── main_complete.py               # 메인 실행 (전체 파이프라인)
├── requirements_complete.txt
├── .env                           # API 키 (ANTHROPIC / GITHUB / EMAIL)
├── scripts/
│   ├── agent_pipeline.py          # Agent 1-5 (수집→분류→매칭→요약→QC)
│   ├── publishing_agent_step5a_integrated.py  # Excel + Word 보고서
│   ├── dashboard_generator.py     # HTML 대시보드
│   ├── github_uploader.py         # GitHub Pages 업로드
│   └── email_sender.py            # Gmail KPI 이메일
└── outputs/
    ├── processed_articles.json    # 수집·분류된 기사
    ├── qc_report.json             # QC 결과
    ├── dashboard/index.html       # 대시보드
    └── reports/                   # Excel + Word 보고서
```

---

## API 재시도 로직

`agent_pipeline.py`에 Anthropic API 500/529 오류 자동 재시도 내장:
- 최대 4회 재시도
- 지수 백오프: 5초 → 10초 → 20초 → 40초

---

## 산출물

- **대시보드**: https://hms4792.github.io/vietnam-infra-news/
- **GitHub**: https://github.com/hms4792/vietnam-infra-news
- **이메일**: hms4792@gmail.com (실행 후 자동 발송)

---

## 스케줄링 (운영 전환 후)

평일 18:00 KST (= 09:00 UTC) 자동 실행:

```bash
crontab -e
# 추가:
0 9 * * 1-5 cd /home/work/claw && source venv/bin/activate && python main_complete.py >> outputs/logs/cron.log 2>&1
```

