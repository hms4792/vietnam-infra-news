# Agent 5 — Publisher (발행·배포)

## 역할
생성된 보고서를 대시보드·이메일·GitHub Pages·AI Drive에 발행하고,
Claude SA와의 공유 규칙 파일을 GitHub에 업로드합니다.

## 실행 순서
```
Step 1: dashboard_generator → HTML 대시보드 생성 (159KB)
Step 2: github_uploader     → GitHub Pages 업로드 (docs/index.html)
Step 3: email_sender        → HTML 이메일 발송 (hms4792@gmail.com)
Step 4: github_uploader     → AI Drive 업로드 (Word + PPT + Excel)
Step 5: shared_rules/export_rules → Claude SA 공유 파일 GitHub 업로드
```

## 핵심 파일
| 파일 | 역할 |
|------|------|
| `dashboard_generator.py` | 마스터플랜 탭 대시보드 v4.0 |
| `email_sender.py` | 플랜별 기사 + 보고서 버튼 이메일 v4.0 |
| `github_uploader.py` | GitHub Pages + AI Drive 업로드 |
| `shared_rules/export_rules.py` | Claude SA 공유 규칙 GitHub 업로드 |

## 대시보드 기능 (v4.0)
- 사이드바: 24개 플랜 탭 (그룹별 분류)
- 플랜 클릭 → 연관 기사 리스트 (최신순 30건, KO/EN 요약)
- 각 패널: 📄 Word · 📊 PPT · 📥 Excel 버튼
- 상단: 🗄️ History DB Excel (누적 2,668건+) 다운로드

## 이메일 기능 (v4.0)
- 플랜별 기사 5건 (한국어 요약)
- 각 플랜: 📄 Word · 📊 PPT 보고서 직접 다운로드 링크
- KPI 요약 (수집건/매핑률/QC통과율)

## GitHub 공유 파일 (Claude SA 연동)
| 파일 | GitHub 경로 |
|------|------------|
| `config/masterplan_ids_export.json` | `data/shared/MASTERPLAN_IDS.json` |
| `config/relevance_rules_export.json` | `data/shared/RELEVANCE_RULES.json` |
| `config/sector_to_plan_export.json` | `data/shared/SECTOR_TO_PLAN.json` |

## AI Drive 저장 구조
```
/Vietnam_Infrastructure_News_Pipeline/
├── Vietnam_Infra_History_DB.xlsx     ← 고정 경로 (항상 최신본)
└── weekly-reports/
    └── YYYY-WWW_{MMDD}/
        ├── MI_Reports_v4/            ← Word 보고서 15개
        ├── MI_PPT/                   ← PPT 15개
        └── Vietnam_Infra_History_DB_W{WW}_{MMDD}.xlsx  ← 주차 스냅샷
```

## 발행 대상
| 채널 | URL |
|------|-----|
| GitHub Pages | https://hms4792.github.io/vietnam-infra-news/ |
| GitHub Repo | https://github.com/hms4792/vietnam-infra-news |
| Email | hms4792@gmail.com |
| AI Drive | Genspark AI Drive |

## 관련 에이전트
← **Agent 4** 보고서 수신
→ Claude SA (GitHub 공유 파일)
