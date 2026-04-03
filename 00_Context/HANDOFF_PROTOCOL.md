# 세션 인계 프로토콜
- 매 세션 시작 시 이 폴더 3개 파일 읽기
- SA 출력: data/agent_output/{name}_output.json
- 공유(GitHub Pages): docs/shared/ → GitHub Pages
- 공유(Google Drive): GDRIVE_FOLDER_ID 설정 시 export_shared.py가 자동 동기화

## SA 구성 (SA-1~6 + Export)
| SA | 스크립트 | 출력 |
|----|---------|------|
| SA-1 | news_collector.py | collector_output.json |
| SA-2 | knowledge_agent.py | knowledge_output.json |
| SA-3 | ai_summarizer.py | — |
| SA-4 | excel_updater.py | Excel DB |
| SA-5 | dashboard_updater.py | docs/index.html |
| SA-6 | quality_context_agent.py | quality_report.json |
| — | export_shared.py | docs/shared/ + Drive |

## Google Drive MCP 설정 (최초 1회)
1. GCP 콘솔 → Google Drive API 활성화
2. OAuth 2.0 클라이언트 ID(데스크톱 앱) JSON 다운로드
3. `~/.google/gdrive_oauth.keys.json` 으로 저장
4. `npx @piotr-agier/google-drive-mcp auth` 실행 → 브라우저 인증
5. GitHub Secrets에 `GDRIVE_FOLDER_ID` 추가

## 두 팀 공유 구조
- Data Team: 파이프라인 실행 → Drive 자동 업로드
- MI Reporting Team: Claude Code + .mcp.json → Drive 직접 읽기
