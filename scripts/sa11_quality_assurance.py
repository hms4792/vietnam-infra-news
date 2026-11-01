import os
import sys
import json
from google import genai

def generate_quality_report():
    print("[SA-11] Quality Assurance Agent 시작: 품질 향상 델타(Delta) 분석 중...")
    
    old_json_path = 'docs/shared/knowledge_index_old.json'
    new_json_path = 'docs/shared/knowledge_index.json'
    output_md_path = 'docs/shared/sa11_pr_body.md'
    
    # 1. 파일 검증
    if not os.path.exists(old_json_path) or not os.path.exists(new_json_path):
        print("[시스템 에러] 비교할 JSON 파일이 없습니다. SA-10이 정상 실행되었는지 확인하십시오.")
        sys.exit(1)
        
    with open(old_json_path, 'r', encoding='utf-8') as f:
        old_data = json.load(f)
    with open(new_json_path, 'r', encoding='utf-8') as f:
        new_data = json.load(f)
        
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[인증 에러] GEMINI_API_KEY 환경변수 누락.")
        sys.exit(1)
        
    client = genai.Client(api_key=api_key)
    
    # 2. 동적 모델 탐색 (SA-10과 동일한 안정성 보장)
    try:
        available_models = [m.name for m in client.models.list()]
        target_model = next((m for m in available_models if 'flash' in m), None)
        if not target_model:
            target_model = next((m for m in available_models if 'pro' in m), None)
        if not target_model and available_models:
            target_model = available_models[0]
            
        target_model = target_model.replace('models/', '')
        print(f"[SA-11] 확정된 분석 모델: {target_model}")
    except Exception as e:
        print(f"[API 조회 에러] {e}")
        sys.exit(1)
        
    # 3. 품질 평가 프롬프트 엔지니어링
    prompt = f"""
    당신은 베트남 인프라 마켓 인텔리전스 파이프라인의 최고 품질 책임자 'SA-11 (Quality Assurance Agent)'입니다.
    SA-10 에이전트가 방금 지식 사전(knowledge_index.json)을 업데이트했습니다. 
    당신의 임무는 구버전과 신버전의 데이터를 비교하여, 이번 업데이트가 파이프라인의 '정보 품질'에 미치는 파급 효과를 분석하고 GitHub PR 본문용 마크다운 보고서를 작성하는 것입니다.
    
    [작성 규칙]
    1. 전문적이고 분석적인 전문가 톤을 유지하십시오.
    2. 아래의 마크다운 템플릿 구조를 반드시 엄수하십시오.
    
    [마크다운 템플릿]
    ## 🤖 [SA-10 & SA-11] 월간 Knowledge Index 업데이트 및 품질 평가 보고서
    
    최신 베트남 하이테크 인프라 및 FDI 동향을 반영하여 지식 사전 업데이트를 제안합니다. SA-11 에이전트의 품질 검증 결과는 다음과 같습니다.
    
    ### 📊 1. 변경 사항 요약 (델타 분석)
    - (어떤 마스터플랜에 어떤 키워드들이 추가되었는지 비교하여 팩트 위주로 요약)
    
    ### 📈 2. 정량적 기대 효과 (Quantitative Impact)
    - (키워드 추가로 인해 뉴스 수집망의 필터링 매핑률이 얼마나 향상될 것인지, 어느 섹터의 정보 획득량이 증가할 것인지 예측)
    
    ### 💎 3. 정보 품질 및 맥락 개선 효과 (Qualitative Improvements)
    - (단순 수집을 넘어, SA-8 MI 리포트 생성기가 하이테크 FDI와 전통 인프라 간의 인과관계를 어떻게 더 깊이 있게 추론할 수 있게 되었는지 맥락적 관점에서 평가)
    
    ---
    **[관리자 조치 사항]**
    1. `Files changed` 탭에서 추가된 키워드의 위치를 검증하십시오.
    2. 이상이 없다면 아래 `Merge pull request` 버튼을 눌러 승인하십시오. 승인 즉시 일일/주간 파이프라인에 반영됩니다.
    
    [데이터 제공]
    - 구버전 데이터: {json.dumps(old_data, ensure_ascii=False)}
    - 신버전 데이터: {json.dumps(new_data, ensure_ascii=False)}
    """
    
    print("[SA-11] 품질 보증 리포트 생성 중...")
    
    try:
        response = client.models.generate_content(
            model=target_model,
            contents=prompt
        )
        
        # 4. 마크다운 파일로 저장 (GitHub Actions에서 PR body로 읽어들일 용도)
        with open(output_md_path, 'w', encoding='utf-8') as f:
            f.write(response.text)
        print(f"[SA-11] 품질 보증 리포트 생성 완료: {output_md_path}")
        
    except Exception as e:
        print(f"[API 호출 에러] {e}")
        sys.exit(1)

if __name__ == "__main__":
    generate_quality_report()
