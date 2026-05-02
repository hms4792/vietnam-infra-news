# Agent 3 — Historian (역사 DB 관리)

## 역할
2019~2026년 2,668건+ 기사를 누적 관리하고,
마스터플랜별 히스토리 매핑과 Excel DB를 생성합니다.

## 실행 순서
```
Step 1: history_db_builder → 이번 주 신규 기사 증분 병합
Step 2: history_matcher    → 기존 미매핑 기사 재매핑 시도
Step 3: translate_vi       → 베트남어 기사 EN/KO 번역 (81건)
Step 4: excel_exporter     → 27시트 Excel DB 재생성
```

## 핵심 파일
| 파일 | 역할 |
|------|------|
| `history_db_builder.py` | DB 로드·저장·증분 병합 (`update_weekly`) |
| `history_matcher.py`    | 이중언어(EN+VI) 키워드 심층 매핑 엔진 |
| `excel_exporter.py`     | 27시트 Excel 생성 (노란색 컬러링) |
| `translate_vi_articles.py` | VI→KO/EN 번역 (MyMemory API) |

## DB 통계 (2026-04-14 기준)
- 전체: **2,668건** (2019~2026)
- 매핑됨: **1,433건** (53.7%)
- 연도별: 2019(5) / 2020(222) / 2021(197) / 2022(206) / 2023(541) / 2024(591) / 2025(336) / 2026(416)

## 출력 파일
| 파일 | 경로 |
|------|------|
| History DB (JSON) | `config/history_db.json` |
| Excel 고정 (최신본) | `outputs/reports/Vietnam_Infra_History_DB.xlsx` |
| Excel 스냅샷 | `outputs/reports/Vietnam_Infra_History_DB_W{WW}_{MMDD}.xlsx` |
| AI Drive 고정 경로 | `/Vietnam_Infrastructure_News_Pipeline/Vietnam_Infra_History_DB.xlsx` |

## Excel 시트 구조 (27개)
1. `All_Articles` — 전체 누적 (매핑 기사 🟡 노란색)
2. `Matched_Only` — 매핑 기사만 최신순
3. 플랜별 × 24개 — 각 플랜 연관기사 최신순
4. `Stats` — 플랜별 통계 + 연도별 분포

## 관련 에이전트
← **Agent 2** 분류 결과 수신
→ **Agent 4** 보고서 생성 시 역사 기사 공급
