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
