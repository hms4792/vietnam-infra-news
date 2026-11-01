import os
import sys
import json
from google import genai
from google.genai import types

def update_knowledge_index():
    print("[SA-10] Knowledge Updater Agent 시작...")
    
    json_path = 'docs/shared/knowledge_index.json'
    
    if not os.path.exists(json_path):
        print(f"[시스템 에러] {json_path} 파일을 찾을 수 없습니다.")
        sys.exit(1)
        
    with open(json_path, 'r', encoding='utf-8') as f:
        try:
            current_index = json.load(f)
        except json.JSONDecodeError:
            print("[시스템 에러] 기존 JSON 파일 형식이 손상되었습니다.")
            sys.exit(1)
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[인증 에러] GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
        sys.exit(1)
        
    # [수정 1] 클라이언트 타임아웃 명시적 연장 (10분 = 600,000ms 설정)
    # 대규모 JSON 처리 시 GitHub Runner 기본 연결 종료 차단
    client = genai.Client(api_key=api_key, http_options={'timeout': 600000})

    # ---------------------------------------------------------
    # 동적 모델 탐색 및 자동 선택 로직
    # ---------------------------------------------------------
    print("[SA-10] 구글 서버에서 접근 가능한 모델 목록을 조회 중입니다...")
    target_model = None
    try:
        available_models = [m.name for m in client.models.list()]
        print(f"-> 접근 가능한 전체 모델: {available_models}")
        
        target_model = next((m for m in available_models if 'flash' in m), None)
        if not target_model:
            target_model = next((m for m in available_models if 'pro' in m), None)
        if not target_model and available_models:
            target_model = available_models[0]
            
        if not target_model:
            raise ValueError("사용 가능한 텍스트 모델이 없습니다.")
            
        target_model = target_model.replace('models/', '')
        print(f"[SA-10] 🚀 자동 선택 및 확정된 모델: {target_model}")
        
    except Exception as e:
        print(f"[API 조회 에러] 모델 목록을 불러오는 중 실패했습니다: {e}")
        sys.exit(1)
    # ---------------------------------------------------------
    
    prompt = f"""
    당신은 베트남 인프라 마켓 인텔리전스 시스템의 핵심인 'Knowledge Index Manager (SA-10)'입니다.
    현재 베트남 시장은 단순 토목/건설을 넘어 하이테크 FDI(반도체 패키징, 데이터센터, AI, 스마트물류) 중심으로 급변하고 있습니다.
    
    아래 제공된 현재의 knowledge_index.json을 분석하여 다음 작업을 수행하십시오:
    1. 기존 마스터플랜의 'keywords' 배열을 검토하십시오.
    2. 최근 누락된 민간 첨단 산업 키워드(Semiconductor, Packaging, FC-BGA, Data Center, AI, Amkor, Samsung Electronics 등)가 적절한 마스터플랜에 없다면 논리적으로 추가하십시오.
    3. 기존의 JSON 구조(플랜 ID, 메타데이터 등)와 트리 구조는 절대 훼손하지 마십시오.
    4. 반드시 완벽하고 유효한 JSON 형식으로만 응답해야 합니다. 마크다운 기호도 포함하지 마십시오.
    5. 키워드 추가가 발생했다면, _meta 객체의 version을 현재 버전에서 0.1 올려서(예: v4.3 -> v4.4) 업데이트하고, last_updated를 오늘 날짜로 변경하십시오.
    
    [현재 knowledge_index.json 데이터]:
    {json.dumps(current_index, ensure_ascii=False)}
    """
    
    print(f"[SA-10] {target_model} 모델에 지식 사전 분석 및 업데이트 요청 중 (스트리밍 수신 시작)...")
    
    # [수정 2] JSON 출력 강제 (토큰 낭비 제거)
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        temperature=0.2
    )
    
    output_text = ""
    try:
        # [수정 3] 스트리밍 통신 (Chunk 단위 실시간 수신으로 Time-out 원천 차단)
        response_stream = client.models.generate_content_stream(
            model=target_model,
            contents=prompt,
            config=config
        )
        
        for chunk in response_stream:
            if chunk.text:
                output_text += chunk.text
                print(".", end="", flush=True) # 네트워크 활성 상태 콘솔 출력
                
        print("\n[SA-10] 데이터 스트리밍 수신 및 병합 완료.")
        
    except Exception as e:
        print(f"\n[API 통신 에러] Gemini API 통신 중 문제가 발생했습니다: {e}")
        sys.exit(1)
    
    # 품질 검증 장치
    try:
        updated_json = json.loads(output_text)
        
        if not updated_json:
            print("[품질 에러] AI가 빈 데이터를 반환했습니다.")
            sys.exit(1)
            
        if type(current_index) != type(updated_json):
            print(f"[품질 에러] JSON 최상위 구조가 변형되었습니다. (기존: {type(current_index)}, 반환: {type(updated_json)})")
            sys.exit(1)
            
        # 데이터 증발 검증 (원본 길이의 80% 미만이면 에러)
        if len(str(updated_json)) < len(str(current_index)) * 0.8:
            print("[품질 에러] 데이터 손실 감지됨. 업데이트된 데이터가 비정상적으로 짧습니다.")
            sys.exit(1)
            
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(updated_json, f, ensure_ascii=False, indent=4)
            
        print("[SA-10] 품질 검증 통과. knowledge_index.json 업데이트 완료.")
        
    except json.JSONDecodeError:
        print("[품질 에러] AI가 유효하지 않은 JSON 형식을 반환하여 파싱할 수 없습니다.")
        sys.exit(1)

if __name__ == "__main__":
    update_knowledge_index()
