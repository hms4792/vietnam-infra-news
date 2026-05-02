# Agent 4 — Reporter (보고서 생성)

## 역할
24개 마스터플랜에 대해 MI Word 보고서(15개) + PPT Executive Summary(15개)를
주간 기사 + 역사 기사를 결합하여 생성합니다.

## 실행 순서
```
report_orchestrator
├── templates/report_regional.py  → 7개 지역성 플랜 (지도+사업목록+Province)
├── templates/report_kpi.py       → 5개 KPI형 플랜 (목표치/현재값/달성률)
├── templates/mi_pdp8_report.py   → PDP8 통합 1개 (6 sub-tracks)
├── templates/mi_water_report.py  → Water 통합 1개 (3 sub-tracks)
└── templates/mi_hanoi_report.py  → Hanoi 통합 1개 (3 sub-tracks)

ppt_generator.py                  → 15개 플랜 × 7슬라이드 PPT
map_generator.py                  → OSM 타일 기반 지도 이미지
```

## 보고서 유형 (v4.0 확정)

### 🗺️ 지역성 프로젝트형 (7개 플랜)
```
표지 → 마스터플랜개요+지도 → 핵심사업 조감표 → 하부프로젝트별 상세
(개요박스+지도+추진경위+최신기사+역사타임라인) → Province 활동현황
→ 한국기업 기회 → Appendix
```
대상: `VN-TRAN-2055`, `VN-IP-NORTH-2030`, `VN-URB-METRO-2030`,
      `VN-MEKONG-DELTA-2030`, `VN-RED-RIVER-2030`, `VN-WW-2030`, `VN-SC-2030`

### 📊 단위상품형 KPI (5개 플랜)
```
표지 → 프로그램/시장개요 → KPI현황표★(목표치/현재값/달성률)
→ 하부트래킹 진행현황(KPI박스+기사) → 시장동향분석 → 한국기업 기회
```
대상: `VN-ENV-IND-1894`, `VN-SWM-NATIONAL-2030`, `VN-OG-2030`,
      `VN-EV-2030`, `VN-CARBON-2050`

### ⚡ 통합형 (3개 보고서)
- **PDP8 통합** — Decision 768 기반, 6 sub-tracks
- **Water 통합** — RESOURCES/URBAN/RURAL 3 sub-tracks
- **Hanoi 통합** — INFRA/NORTH/WEST 3 sub-tracks

## PPT 구조 (플랜당 7슬라이드)
1. 표지 (플랜명 / 날짜 / CONFIDENTIAL)
2. KPI 대시보드 (핵심 4개 지표)
3. 프로젝트 진행현황 (최신 기사 5건)
4. 뉴스 하이라이트 (6개 카드 그리드)
5. Province 활동 현황 (바차트)
6. 한국 기업 기회 (HIGH/MEDIUM/LOW)
7. 결론 및 다음 단계

## 출력 경로
| 유형 | 경로 |
|------|------|
| Word 보고서 (15개) | `outputs/reports/MI_Reports/` |
| PPT (15개) | `outputs/reports/MI_PPT/` |
| AI Drive | `weekly-reports/YYYY-WWW_{MMDD}/MI_Reports_v4/` |
| AI Drive | `weekly-reports/YYYY-WWW_{MMDD}/MI_PPT/` |

## 공유 라이브러리
| 파일 | 역할 |
|------|------|
| `templates/report_lib.py` | 색상팔레트, 테이블빌더, 기사렌더러, 표지빌더 등 |

## 관련 에이전트
← **Agent 3** 역사 기사 수신
→ **Agent 5** 생성된 보고서 파일 전달
