# 📱 카카오톡 알림 설정 가이드

## 1단계: 카카오 개발자 앱 설정

### 1.1 Kakao Developers 접속
- https://developers.kakao.com 접속
- 로그인

### 1.2 애플리케이션 추가
1. **내 애플리케이션** → **애플리케이션 추가하기**
2. 앱 이름: `Vietnam Infra News`
3. 사업자명: 본인 이름

### 1.3 플랫폼 등록
1. **앱 설정** → **플랫폼**
2. **Web 플랫폼 등록**
3. 사이트 도메인: `http://localhost:8080`

### 1.4 카카오 로그인 활성화
1. **제품 설정** → **카카오 로그인**
2. **활성화 설정**: ON
3. **Redirect URI 등록**: `http://localhost:8080/callback`

### 1.5 동의항목 설정
1. **제품 설정** → **카카오 로그인** → **동의항목**
2. **카카오톡 메시지 전송** 권한 활성화

---

## 2단계: 인증 토큰 발급

### 2.1 인증 스크립트 실행

```bash
cd vietnam-infra-pipeline
python scripts/notifier.py --setup-kakao
```

### 2.2 브라우저에서 인증
1. 출력된 URL을 브라우저에 복사하여 접속
2. 카카오 로그인
3. **동의하고 계속하기** 클릭
4. 리다이렉트된 URL에서 `code=` 뒤의 값 복사

예시:
```
http://localhost:8080/callback?code=AbCdEfGhIjKlMnOpQrStUvWxYz
                                    ↑ 이 값을 복사
```

### 2.3 코드 입력
- 터미널에 복사한 코드 붙여넣기
- Enter

### 2.4 완료 확인
```
✅ 카카오톡 인증 완료!
   토큰이 data/kakao_token.json에 저장되었습니다.
```

---

## 3단계: 테스트

### 3.1 테스트 메시지 발송
```bash
python scripts/notifier.py --test-kakao
```

### 3.2 카카오톡에서 확인
- **나와의 채팅**에서 메시지 확인

---

## 토큰 관리

### 토큰 파일 위치
```
data/kakao_token.json
```

### 토큰 갱신
- Access Token: 6시간 유효
- Refresh Token: 2개월 유효
- **자동 갱신**: 파이프라인 실행 시 자동으로 토큰 갱신

### 토큰 만료 시
```bash
python scripts/notifier.py --setup-kakao
```
위 명령어로 재인증

---

## 문제 해결

### "redirect_uri mismatch" 오류
- **원인**: Redirect URI가 일치하지 않음
- **해결**: Kakao Developers → 카카오 로그인 → Redirect URI 확인
  - 정확히 `http://localhost:8080/callback` 입력

### "talk_message scope required" 오류
- **원인**: 메시지 권한 미설정
- **해결**: 동의항목에서 "카카오톡 메시지 전송" 활성화

### "invalid_grant" 오류
- **원인**: 인증 코드 만료 (5분)
- **해결**: `--setup-kakao` 재실행

---

## REST API Key 확인

현재 설정된 REST API Key:
```
425df4a600e63dc205777f5bd7474b12
```

Kakao Developers → 앱 설정 → 앱 키에서 확인 가능
