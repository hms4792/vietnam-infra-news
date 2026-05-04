"""
diagnose_api_key.py — API Key 진단 스크립트
=============================================
GitHub Actions에서 ANTHROPIC_API_KEY가 올바르게
읽히는지 단계별로 검증합니다.

실행 방법:
  python3 scripts/diagnose_api_key.py
"""

import os
import sys
import requests

print("=" * 55)
print("ANTHROPIC_API_KEY 진단 스크립트")
print("=" * 55)

# ── Step 1: 환경변수 존재 여부 ──────────────────────────
raw_key = os.environ.get('ANTHROPIC_API_KEY', None)

if raw_key is None:
    print("[FAIL] Step1: ANTHROPIC_API_KEY 환경변수 자체가 없음")
    print("       → GitHub Secrets에 'ANTHROPIC_API_KEY' 이름으로 등록되어 있는지 확인")
    sys.exit(1)

print(f"[OK]   Step1: 환경변수 존재 확인")

# ── Step 2: 키 값 형태 분석 (값 자체는 출력 안 함) ────────
key_len       = len(raw_key)
has_newline   = '\n' in raw_key
has_return    = '\r' in raw_key
has_space_start = raw_key != raw_key.lstrip()
has_space_end   = raw_key != raw_key.rstrip()
starts_correct  = raw_key.lstrip().startswith('sk-ant-')
stripped_key    = raw_key.strip()
stripped_len    = len(stripped_key)

print(f"\n[진단] Step2: 키 값 형태 분석")
print(f"       키 길이 (raw)     : {key_len}자")
print(f"       키 길이 (stripped): {stripped_len}자")
print(f"       올바른 prefix     : {'✅ sk-ant-' if starts_correct else '❌ sk-ant- 아님 — 잘못된 키'}")
print(f"       줄바꿈(\\n) 포함   : {'❌ 있음 ← 이것이 SA-8 오류 원인!' if has_newline else '✅ 없음'}")
print(f"       캐리지리턴(\\r)    : {'❌ 있음' if has_return else '✅ 없음'}")
print(f"       앞 공백           : {'❌ 있음' if has_space_start else '✅ 없음'}")
print(f"       뒤 공백/줄바꿈    : {'❌ 있음 ← strip() 필요' if has_space_end else '✅ 없음'}")

if has_newline or has_return or has_space_start or has_space_end:
    print(f"\n  ⚠️  키 값에 불필요한 공백/줄바꿈이 포함되어 있습니다.")
    print(f"     GitHub Secret 재등록 시 앞뒤를 완전히 제거해야 합니다.")
else:
    print(f"\n  ✅ 키 값 형태 정상 (공백/줄바꿈 없음)")

# ── Step 3: 실제 API 호출 테스트 (stripped 키 사용) ────────
print(f"\n[진단] Step3: 실제 API 인증 테스트 (stripped 키 사용)")

headers = {
    'Content-Type':      'application/json',
    'x-api-key':         stripped_key,
    'anthropic-version': '2023-06-01',
}
payload = {
    'model':      'claude-haiku-4-5-20251001',
    'max_tokens': 10,
    'messages':   [{'role': 'user', 'content': 'ping'}],
}

try:
    resp = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers=headers,
        json=payload,
        timeout=15
    )

    if resp.status_code == 200:
        print(f"  ✅ API 인증 성공! (HTTP 200)")
        print(f"     → 키 정상 작동 확인됨")

    elif resp.status_code == 401:
        body = resp.json()
        err_type = body.get('error', {}).get('type', '')
        err_msg  = body.get('error', {}).get('message', '')
        print(f"  ❌ 401 Unauthorized")
        print(f"     오류 타입: {err_type}")
        print(f"     오류 메시지: {err_msg}")
        if 'invalid' in err_msg.lower() or 'expired' in err_msg.lower():
            print(f"     → 키 자체가 무효/만료 상태. 새 키 발급 필요.")
        elif 'credit' in err_msg.lower() or 'billing' in err_msg.lower():
            print(f"     → 크레딧/결제 문제. Console에서 크레딧 확인 필요.")
        else:
            print(f"     → 키 값 불일치. GitHub Secret 재등록 필요.")

    elif resp.status_code == 529:
        print(f"  ⚠️  529 API 과부하 — 키는 유효하지만 서버 일시적 과부하")

    else:
        print(f"  ⚠️  HTTP {resp.status_code}: {resp.text[:200]}")

except requests.exceptions.Timeout:
    print(f"  ⚠️  타임아웃 — 네트워크 문제 (키 문제 아님)")
except Exception as e:
    print(f"  ❌ 예외 발생: {e}")

# ── Step 4: raw 키 vs stripped 키 비교 ────────────────────
print(f"\n[진단] Step4: raw vs stripped 비교")
if raw_key == stripped_key:
    print(f"  ✅ raw == stripped (키 값 깨끗함)")
else:
    print(f"  ❌ raw != stripped (키 앞뒤에 불필요한 문자 있음)")
    print(f"     raw 길이: {key_len}  →  stripped 길이: {stripped_len}")
    print(f"     차이 {key_len - stripped_len}자 제거 필요")
    print(f"     → generate_mi_report.py 및 context_analyzer.py에서")
    print(f"        os.getenv('ANTHROPIC_API_KEY', '').strip() 사용 확인 필요")

print("\n" + "=" * 55)
print("진단 완료")
print("=" * 55)
