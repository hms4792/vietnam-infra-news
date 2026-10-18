import os
import sys
import json
from google import genai
from google.genai import types

def update_knowledge_index():
    print("[SA-10] Knowledge Updater Agent 시작...")
    
    # 1. 파일 경로 설정
    json_path = 'docs/shared/knowledge_index.json'
    
    if not os.path.exists(json_path):
        print(f"[시스템 에러] {json_path} 파일을 찾을 수 없습니다. 작업을 중단합니다.")
        sys.exit(1)
        
    with open(json_path, 'r', encoding='utf-8') as f:
        current_index = json.load(f)
        
    # 2. 환경변수 확인
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[인증 에러] GEMINI_API_KEY 환경변수가 설정되지 않았습니다. 작업을 중단합니다.")
        sys.exit(1)
        
    client = genai.Client(api_key=api_key)
    
    # 3. 프롬프트 엔지니어링
    prompt = f"""
    당신은 베트남 인프라 마켓 인텔리전스 시스템의 핵심인 'Knowledge Index Manager (SA-10)'입니다.
    현재 베트남 시장은 단순 토목/건설을 넘어 하이테크 FDI(반도체 패키징, 데이터센터, AI, 스마트물류) 중심으로 급변하고 있습니다.
    
    아래 제공된 현재의 knowledge_index.json을 분석하여 다음 작업을 수행하십시오:
    1. 기존 마스터플랜의 'keywords' 배열을 검토하십시오.
    2. 최근 누락된 민간 첨단 산업 키워드(Semiconductor, Packaging, FC-BGA, Data Center, AI, Amkor, Samsung Electronics 등)가 적절한 마스터플랜에 없다면 논리적으로 추가하십시오.
    3. 기존의 JSON 구조(플랜 ID, 메타데이터 등)와 트리 구조는 절대 훼손하지 마십시오.
    4. 반드시 완벽하고 유효한 JSON 형식으로만 응답해야 합니다. 마크다운 기호도 포함하지 마십시오.
    
    [현재 knowledge_index.json 데이터]:
    {json.dumps(current_index, ensure_ascii=False, indent=2)}
    """
    
    print("[SA-10] Gemini Pro 모델에 지식 사전 분석 및 업데이트 요청 중...")
    
    # 4. 모델 호출 (gemini-pro로 롤백 및 예외 처리)
    try:
        response = client.models.generate_content(
            model='gemini-1.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
            )
        )
    except Exception as e:
        print(f"[API 호출 에러] Gemini API 통신 중 문제가 발생했습니다: {e}")
        sys.exit(1) # 강제 종료
    
    # 5. 결과물 3단계 품질 검증 (Quality Assurance)
    try:
        updated_json = json.loads(response.text)
        
        # [검증 1] 데이터가 비어있는지 확인
        if not updated_json:
            print("[품질 에러] AI가 빈 데이터를 반환했습니다. 파이프라인을 중단합니다.")
            sys.exit(1)
            
        # [검증 2] 데이터 구조 훼손 확인 (기존과 동일한 자료형인지)
        if type(current_index) != type(updated_json):
            print(f"[품질 에러] JSON 최상위 구조가 변형되었습니다. (기존: {type(current_index)}, 반환: {type(updated_json)})")
            sys.exit(1)
            
        # [검증 3] 데이터 유실 확인 (플랜 개수가 기존보다 줄어들었는지 방어)
        if len(updated_json) < len(current_index):
            print(f"[품질 에러] 데이터 손실 감지됨. 기존 플랜 수({len(current_index)}개)보다 반환된 플랜 수({len(updated_json)}개)가 적습니다.")
            sys.exit(1)
            
        # 모든 검증 통과 시 파일 덮어쓰기
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(updated_json, f, ensure_ascii=False, indent=4)
        print("[SA-10] 품질 검증 통과. knowledge_index.json 업데이트 완료.")
        
    except json.JSONDecodeError:
        print("[품질 에러] AI가 유효하지 않은 JSON 형식을 반환하여 파싱할 수 없습니다.")
        print(f"--- [AI 반환 텍스트 원본] ---\n{response.text}\n-----------------------------")
        sys.exit(1) # 강제 종료

if __name__ == "__main__":
    update_knowledge_index()
