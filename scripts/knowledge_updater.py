import os
import json
from google import genai
from google.genai import types

def update_knowledge_index():
    print("[SA-10] Knowledge Updater Agent 시작...")
    
    # 1. 파일 경로 설정
    json_path = 'docs/shared/knowledge_index.json'
    
    if not os.path.exists(json_path):
        print(f"오류: {json_path} 파일을 찾을 수 없습니다.")
        return
        
    with open(json_path, 'r', encoding='utf-8') as f:
        current_index = json.load(f)
        
    # 2. 환경변수 확인
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("오류: GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
        return
        
    # 3. 최신 구글 공식 SDK 클라이언트 초기화
    client = genai.Client(api_key=api_key)
    
    # 4. 프롬프트 엔지니어링
    prompt = f"""
    당신은 베트남 인프라 마켓 인텔리전스 시스템의 핵심인 'Knowledge Index Manager (SA-10)'입니다.
    현재 베트남 시장은 단순 토목/건설을 넘어 하이테크 FDI(반도체 패키징, 데이터센터, AI, 스마트물류) 중심으로 급변하고 있습니다.
    
    아래 제공된 현재의 knowledge_index.json을 분석하여 다음 작업을 수행하십시오:
    1. 기존 마스터플랜(예: VN-IP-NORTH-2030, VN-SMART-2025 등)의 'keywords' 배열을 검토하십시오.
    2. 최근 누락된 민간 첨단 산업 키워드(Semiconductor, Packaging, FC-BGA, Data Center, AI, Amkor, Samsung Electronics 등)가 적절한 마스터플랜의 키워드 목록에 없다면 논리적으로 추가하십시오.
    3. 기존의 JSON 구조(플랜 ID, 메타데이터 등)와 트리 구조는 절대 훼손하지 마십시오.
    4. 반드시 완벽하고 유효한 JSON 형식으로만 응답해야 합니다. 마크다운 기호도 포함하지 마십시오.
    
    [현재 knowledge_index.json 데이터]:
    {json.dumps(current_index, ensure_ascii=False, indent=2)}
    """
    
    print("[SA-10] Gemini 1.5 Pro에 지식 사전 분석 및 업데이트 요청 중...")
    
    # 5. 모델 호출 (최신 문법 적용 및 JSON 강제 출력)
    response = client.models.generate_content(
        model='gemini-1.5-pro-latest',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        )
    )
    
    # 6. 결과 검증 및 덮어쓰기
    try:
        updated_json = json.loads(response.text)
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(updated_json, f, ensure_ascii=False, indent=4)
        print("[SA-10] knowledge_index.json 업데이트 완료 및 저장 성공.")
    except json.JSONDecodeError:
        print("[SA-10] 치명적 오류: AI가 유효하지 않은 JSON을 반환했습니다. 원본을 유지합니다.")
        print("반환된 텍스트:", response.text)

if __name__ == "__main__":
    update_knowledge_index()
