# Agent 2 — Classifier (분류·관련성 필터)

## 역할
Agent 1이 수집한 기사를 24개 마스터플랜과 정밀 매핑하고,
노이즈 기사를 차단하는 관련성 필터를 실행합니다.

## 실행 순서
```
Step 1: PLAN_RULES 기반 must_any / boost / conflict 점수 계산
Step 2: min_score 미달 기사 → rejected_plan_links 분리
Step 3: Feedback Blocklist 갱신 (반복 저품질 도메인 차단)
Step 4: 관련성 통과 기사 → matched_plans 필드 확정
```

## 핵심 파일
| 파일 | 역할 |
|------|------|
| `relevance_filter.py` | 24개 플랜 × PLAN_RULES 정의 + 필터 로직 |

## PLAN_RULES 구조 (플랜당)
```python
{
  "must_any":  [...],   # 이 중 하나라도 있어야 통과
  "boost":     [...],   # 가중치 +2
  "conflict":  [...],   # 있으면 감점 / 제외
  "min_score": 2,       # 최소 점수 임계값
}
```

## 공유 규칙 파일 (GitHub 자동 업로드)
- `config/relevance_rules_export.json` → GitHub `data/shared/RELEVANCE_RULES.json`
- `config/sector_to_plan_export.json`  → GitHub `data/shared/SECTOR_TO_PLAN.json`

## Feedback Blocklist
- `config/FEEDBACK_BLOCKLIST.json` — 반복 차단 도메인 누적 관리
- 매주 실행 후 자동 갱신됨

## 관련 에이전트
← **Agent 1** 출력 수신
→ **Agent 3** 역사 DB 병합, **Agent 4** 보고서 생성에 전달
