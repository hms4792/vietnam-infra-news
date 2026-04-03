# Vietnam Infra News Pipeline
- GitHub: hms4792/vietnam-infra-news
- 목적: 베트남 7개 인프라 섹터 자동 뉴스 수집 → MI Reporting Agent Team 확장
- 절대 불변 제약:
  - 번역: MyMemory API만 (Anthropic API 번역 금지)
  - ExcelUpdater.update_all(articles) 만 사용
  - main.py 순서: Step1→2→3→4 고정
  - YML 인라인 python3 -c 코드 금지
  - GitHub Pages: main브랜치 /docs 폴더만
  - Email: EMAIL_USERNAME / EMAIL_PASSWORD

## Google Drive MCP (임시 보류)
- 상태: 코드 완성, GCP 서비스 계정 설정 완료
- 보류 이유: Gmail 무료 계정 저장용량 부족 (92% 사용)
- 재개 조건: Google Drive 저장공간 확보 후
- 필요 작업: 공유 드라이브 생성 또는 용량 확보
- 관련 파일:
  - scripts/gdrive_upload.py (완성본 보존)
  - .mcp.json.backup (MCP 서버 설정)
  - C:/Users/hms47/.google/gdrive_service_account.json (키 파일)
  - 서비스 계정: vietnam-infra-drive@vietnam-infra-mcp.iam.gserviceaccount.com
- 현재 공유 레이어: GitHub Pages URL 방식으로 대체 운영 중
