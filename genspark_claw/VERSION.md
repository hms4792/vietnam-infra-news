# Vietnam Infrastructure News Pipeline — Genspark Claw

## Version History

### v5.3.0 — 2026-04-15 (최초 완성 버전)
**"Production-Ready Release"**

#### 핵심 스펙
- 24 마스터플랜 → 15 통합 보고서 (PDP8 통합 1 + Water 통합 1 + Hanoi 통합 1 + 개별 12)
- PDP8 계층 구조: VN-PWR-PDP8 (상위) + 5개 하위 (Claude 체계 통일)
- 3개국어 요약 (KO/EN/VI) — gsk summarize 1-call
- 매핑률 100% (키워드 직접 13건 + Sector fallback 31건)
- QC 통과율 100%
- 수집 7일 제한 + 정부·연구기관 도메인 면제 (25개)
- Province 63개 키워드 DB + "Vietnam" 전국 분류
- Excel History DB: 37시트 (2,713건 누적)
  - REF 참조시트 4개: Plan Keywords, Sources, Provinces, Search Queries
  - 변경이력(audit trail) 자동 추적
- 대시보드: Dark SPA, TTS 3개국어, 검색, SheetJS Excel
- 이메일: Gmail-optimized newsletter, KPI boxes, report pills
- GitHub 경로 분리: Claude ↔ Genspark 충돌 방지

#### 산출물 (1회 실행)
| 유형 | 수량 | 크기 |
|------|:----:|:----:|
| MI Word 보고서 | 15 | 2,637KB |
| MI PPT Executive Summary | 15 | ~580KB |
| Excel History DB | 37시트 | 1,045KB |
| HTML 대시보드 | 1 | 120KB |
| GitHub 업로드 | 83+ | - |

#### 실행 환경
- Genspark Claw VM (Korea Central)
- Cron: 매주 토요일 23:30 KST (14:30 UTC)
- 소요시간: ~17분
- 예상 크레딧: ~220/회

#### 주요 파일
```
/home/work/claw/
├── main_complete.py              — 메인 오케스트레이터
├── run_pipeline.sh               — tmux 래퍼
├── VERSION.md                    — 이 파일
├── scripts/
│   ├── agent_pipeline.py         — Agent 1-5 (수집→QC)
│   ├── relevance_filter.py       — 관련성 필터
│   ├── mi_report_v4.py           — MI 보고서 오케스트레이터
│   ├── mi_pdp8_report_v4.py      — PDP8 통합 보고서
│   ├── mi_water_report_v4.py     — Water 통합 보고서
│   ├── report_lib.py             — Word 보고서 공통 라이브러리
│   ├── report_regional.py        — 지역성 보고서 템플릿
│   ├── report_kpi.py             — KPI 보고서 템플릿
│   ├── mi_ppt_generator.py       — PPT Executive Summary
│   ├── excel_history_exporter.py — Excel DB + REF 시트
│   ├── dashboard_generator.py    — HTML 대시보드
│   ├── email_sender.py           — 이메일 발송
│   ├── github_uploader.py        — GitHub 업로드
│   ├── history_matcher.py        — 역사 DB 매칭
│   └── history_db_builder.py     — 역사 DB 빌더
├── config/
│   ├── history_db.json           — 누적 기사 DB (2,713건)
│   ├── province_keywords.json    — 63개 Province 키워드
│   ├── province_project_kpi.json — KPI 데이터베이스
│   ├── pdp8_structure.json       — PDP8 6-track 구조
│   ├── water_structure.json      — Water 3-track 구조
│   ├── d1894_program_structure.json
│   ├── report_urls.json          — Word/PPT 다운로드 URL
│   ├── ref_change_log.json       — 참조시트 변경이력
│   └── masterplans.json          — 24 마스터플랜 정의
└── outputs/
    ├── dashboard/index.html
    ├── reports/MI_Reports/        — Word 15개
    ├── reports/MI_PPT/            — PPT 15개
    └── reports/Vietnam_Infra_History_DB.xlsx
```
