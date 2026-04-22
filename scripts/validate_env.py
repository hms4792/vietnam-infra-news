"""
validate_env.py
GitHub Actions Step — 환경변수 검증
위치: scripts/validate_env.py
"""
import os, sys, logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
log = logging.getLogger('validate_env')
ok = True

if os.getenv('GMAIL_ADDRESS'):
    log.error("GMAIL_ADDRESS 감지 → EMAIL_USERNAME 으로 변경 필요")
    ok = False
if os.getenv('GMAIL_APP_PASSWORD'):
    log.error("GMAIL_APP_PASSWORD 감지 → EMAIL_PASSWORD 로 변경 필요")
    ok = False
if os.getenv('ANTHROPIC_API_KEY'):
    log.warning("ANTHROPIC_API_KEY 감지 — GitHub Actions에서 사용 금지 (번역은 Google Translate만)")

eu = os.getenv('EMAIL_USERNAME', '')
ep = os.getenv('EMAIL_PASSWORD', '')
log.info(f"EMAIL_USERNAME: {'✅ 설정됨' if eu else '⚠️ 미설정(이메일알림 비활성)'}")
log.info(f"EMAIL_PASSWORD: {'✅ 설정됨' if ep else '⚠️ 미설정(이메일알림 비활성)'}")

nk = os.getenv('NEWSDATA_API_KEY', '')
log.info(f"NEWSDATA_API_KEY: {'✅ '+nk[:4]+chr(42)*3 if nk else '⚠️ 미설정(NewsData 수집 건너뜀)'}")

if ok:
    log.info("✅ 환경변수 검증 통과")
else:
    log.error("❌ 시크릿 오류 확인 필요")
    sys.exit(1)
