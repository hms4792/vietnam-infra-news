# Agent 1 — News Collector (뉴스 수집)

## 역할
베트남 인프라 관련 뉴스를 RSS + gsk search로 수집하고,
AI(gsk summarize) 기반 3개 국어(KO/EN/VI) 요약을 생성합니다.

## 실행 순서
```
Step 1: RSS 피드 35개 쿼리 → 원문 기사 수집
Step 2: 키워드 기반 1차 분류 (24개 마스터플랜 매핑)
Step 3: gsk summarize → KO/EN/VI 3개 국어 요약
Step 4: QC 검증 (출처 신뢰도, 날짜, 중복 제거)
Step 5: genspark_output.json 출력
```

## 출력 파일
- `outputs/genspark_output.json` — 수집 기사 전체 (QC 결과 포함)
- `outputs/genspark_qc_report.json` — QC 상세 리포트

## 핵심 파일
| 파일 | 역할 |
|------|------|
| `news_collector.py` | 메인 파이프라인 (Agent 1~4 통합 실행) |

## 입력 설정
- `config/masterplans.json` → 24개 마스터플랜 정의
- 환경변수: `ANTHROPIC_API_KEY` (요약), `PIPELINE_OUTPUT_DIR`

## 관련 에이전트
→ **Agent 2** (분류·필터링)가 이 출력을 받아 관련성 재검증
