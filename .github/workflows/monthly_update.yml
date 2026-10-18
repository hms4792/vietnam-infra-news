name: SA-10 Monthly Knowledge Index Update

on:
  schedule:
    - cron: '0 0 1 * *'
  workflow_dispatch:

jobs:
  agent-update:
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
      
    steps:
      - name: 1. 저장소 체크아웃
        uses: actions/checkout@v4
        
      - name: 2. Python 환경 구축
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
          
      - name: 3. 의존성 패키지 설치 (최신 라이브러리 반영)
        run: pip install google-genai
        
      - name: 4. SA-10 에이전트 실행 (JSON 업데이트)
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }} # 👈 Anthropic 키에서 Gemini 키로 수정됨
        run: python scripts/knowledge_updater.py
        
      - name: 5. Pull Request 생성 (관리자 검토용)
        uses: peter-evans/create-pull-request@v6
        with:
          token: ${{ secrets.GITHUB_TOKEN }}
          commit-message: "chore: SA-10 AI Agent 업데이트 제안"
          title: "🤖 [SA-10] 이번 달 Knowledge Index 업데이트 제안"
          body: |
            ## SA-10 Knowledge Updater Agent 보고서
            최신 베트남 하이테크 인프라 및 FDI 동향을 반영하여 `knowledge_index.json` 업데이트를 제안합니다.
            
            **[관리자 조치 사항]**
            1. 'Files changed' 탭을 눌러 추가된 키워드를 확인하십시오.
            2. 이상이 없다면 아래 `Merge pull request` 버튼을 눌러 승인하십시오.
          branch: "sa-10-knowledge-update"
          delete-branch: true
