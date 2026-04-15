# 🇻🇳 Vietnam Infrastructure Intelligence Pipeline v4.0

## Agent Team 구조

```
┌─────────────────────────────────────────────────────────────────┐
│                    main_complete.py (오케스트레이터)               │
│              매주 토요일 23:30 KST 자동 실행 (Cron)               │
└───────────┬────────────────────────────────────────────────────┘
            │
   ┌────────▼────────┐
   │  AGENT 1        │  agents/agent1_collector/
   │  News Collector │  news_collector.py
   │                 │
   │  • RSS + gsk search (35개 쿼리)
   │  • KO/EN/VI 3개국어 AI 요약
   │  • QC 검증 (출처·날짜·중복)
   │  • 출력: genspark_output.json (~157건/주)
   └────────┬────────┘
            │
   ┌────────▼────────┐
   │  AGENT 2        │  agents/agent2_classifier/
   │  Classifier     │  relevance_filter.py
   │                 │
   │  • 24개 플랜 × PLAN_RULES 정밀 매핑
   │  • must_any / boost / conflict 점수
   │  • Feedback Blocklist 노이즈 차단
   │  • GitHub 공유 규칙 자동 업데이트
   └────────┬────────┘
            │
   ┌────────▼────────┐
   │  AGENT 3        │  agents/agent3_historian/
   │  Historian      │  history_db_builder.py
   │                 │  history_matcher.py
   │  • 누적 DB 증분 병합 (현재 2,668건)
   │  • 역사 기사 심층 재매핑
   │  • 베트남어 → KO/EN 번역
   │  • Excel DB 27시트 재생성
   └────────┬────────┘
            │
   ┌────────▼────────┐
   │  AGENT 4        │  agents/agent4_reporter/
   │  Reporter       │  report_orchestrator.py
   │                 │  templates/ (5개 템플릿)
   │  • Word MI 보고서 × 15개
   │    ├─ 지역성형 7개 (지도+Province)
   │    ├─ KPI형 5개 (목표/달성률)
   │    └─ 통합형 3개 (PDP8/Water/Hanoi)
   │  • PPT Executive Summary × 15개
   │  • 7슬라이드/플랜 (KPI·뉴스·지역·기회)
   └────────┬────────┘
            │
   ┌────────▼────────┐
   │  AGENT 5        │  agents/agent5_publisher/
   │  Publisher      │  dashboard_generator.py
   │                 │  email_sender.py
   │                 │  github_uploader.py
   │  • HTML 대시보드 → GitHub Pages
   │  • 이메일 (플랜별 기사 + 보고서 링크)
   │  • AI Drive (Word + PPT + Excel)
   │  • Claude SA 공유 규칙 GitHub 업로드
   └─────────────────┘
```

## 디렉토리 구조

```
/home/work/claw/
│
├── main_complete.py          ← 파이프라인 오케스트레이터 (진입점)
├── PIPELINE.md               ← 이 파일 (구조 설명)
├── .env                      ← API 키 / 환경변수
├── requirements_complete.txt
│
├── agents/                   ← ★ Agent Team (핵심)
│   ├── agent1_collector/     ← 뉴스 수집
│   │   ├── README.md
│   │   └── news_collector.py
│   │
│   ├── agent2_classifier/    ← 분류·필터링
│   │   ├── README.md
│   │   └── relevance_filter.py
│   │
│   ├── agent3_historian/     ← 역사 DB 관리
│   │   ├── README.md
│   │   ├── history_db_builder.py
│   │   ├── history_matcher.py
│   │   ├── excel_exporter.py
│   │   └── translate_vi_articles.py
│   │
│   ├── agent4_reporter/      ← 보고서 생성
│   │   ├── README.md
│   │   ├── report_orchestrator.py
│   │   ├── ppt_generator.py
│   │   ├── map_generator.py
│   │   └── templates/
│   │       ├── report_lib.py        ← 공유 라이브러리
│   │       ├── report_regional.py   ← 지역성형 7개 플랜
│   │       ├── report_kpi.py        ← KPI형 5개 플랜
│   │       ├── mi_pdp8_report.py    ← PDP8 통합
│   │       ├── mi_water_report.py   ← Water 통합
│   │       ├── mi_hanoi_report.py   ← Hanoi 통합
│   │       └── report_d1894_deep.py ← D1894 심층
│   │
│   └── agent5_publisher/     ← 발행·배포
│       ├── README.md
│       ├── dashboard_generator.py
│       ├── email_sender.py
│       ├── github_uploader.py
│       └── shared_rules/
│           └── export_rules.py  ← Claude SA 공유 규칙
│
├── config/                   ← 설정·DB·규칙 파일
│   ├── masterplans.json         ← 24개 마스터플랜 정의
│   ├── history_db.json          ← 역사 기사 누적 DB (2,668건)
│   ├── province_project_kpi.json← Province×Project KPI DB
│   ├── pdp8_structure.json      ← PDP8 6 sub-tracks 구조
│   ├── water_structure.json     ← Water 3 sub-tracks 구조
│   ├── hanoi_urban_structure.json← Hanoi 3 sub-tracks 구조
│   ├── d1894_program_structure.json← D1894 프로그램 구조
│   ├── report_urls.json         ← AI Drive 보고서 URL 캐시
│   ├── FEEDBACK_BLOCKLIST.json  ← 차단 도메인 목록
│   ├── masterplan_ids_export.json   ↗ GitHub 공유
│   ├── relevance_rules_export.json  ↗ GitHub 공유
│   └── sector_to_plan_export.json   ↗ GitHub 공유
│
├── assets/
│   └── maps/                 ← 플랜별 지도 이미지 (OSM 타일)
│
├── outputs/                  ← 실행 결과물
│   ├── genspark_output.json  ← 이번 주 수집 기사
│   ├── genspark_qc_report.json
│   ├── dashboard/index.html  ← 대시보드 HTML
│   └── reports/
│       ├── MI_Reports/       ← Word 보고서 15개
│       ├── MI_PPT/           ← PPT 15개
│       ├── Vietnam_Infra_History_DB.xlsx      ← 고정 (최신본)
│       └── Vietnam_Infra_History_DB_W{WW}_*.xlsx ← 주차 스냅샷
│
└── scripts/                  ← 원본 (하위호환 유지, deprecated)
    └── *.py                  ← agents/ 로 이전 완료
```

## 24개 마스터플랜 ID

| 그룹 | 플랜 ID | 보고서 |
|------|---------|--------|
| ⚡ PDP8 전력 | VN-PDP8-RENEWABLE, VN-PDP8-LNG, VN-PDP8-NUCLEAR | PDP8 통합 |
| ⚡ PDP8 전력 | VN-PDP8-COAL, VN-PDP8-GRID, VN-PDP8-HYDROGEN | PDP8 통합 |
| 💧 수자원 | VN-WAT-RESOURCES, VN-WAT-URBAN, VN-WAT-RURAL | Water 통합 |
| 🏙️ 하노이 | HN-URBAN-INFRA, HN-URBAN-NORTH, HN-URBAN-WEST | Hanoi 통합 |
| 🛣️ 개별 | VN-TRAN-2055, VN-URB-METRO-2030 | 지역성형 |
| 🛣️ 개별 | VN-MEKONG-DELTA-2030, VN-RED-RIVER-2030, VN-IP-NORTH-2030 | 지역성형 |
| 🌿 환경탄소 | VN-ENV-IND-1894, VN-WW-2030, VN-SWM-NATIONAL-2030 | KPI형/지역성형 |
| 🌿 환경탄소 | VN-SC-2030, VN-OG-2030, VN-EV-2030, VN-CARBON-2050 | KPI형 |

## 스케줄
- **실행**: 매주 토요일 23:30 KST (= UTC 14:30)
- **Cron Job ID**: `f5cff2f9-7ce0-49d8-aa02-858c02e99013`
- **최초 자동 실행**: 2026-05-02 (W18)

## 데이터 흐름 요약
```
gsk search → 수집(157건/주) → 분류(matched_plans) 
→ history_db.json(누적 2,668건+) 
→ Word 보고서(15개) + PPT(15개) + Excel(27시트)
→ GitHub Pages + AI Drive + Email
→ Claude SA (공유 규칙 3개 파일)
```
