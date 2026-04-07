# RSS_SOURCE_STATUS.md
# Vietnam Infrastructure News — RSS 소스 현황 및 대책
# 최종 검증일: 2026-04-07
# 목적: Claude Code Agent + Genspark Agent 공유 — 동일 문제 반복 방지

---

## ⚠️ 핵심 원칙

> **RSS 접근 실패 소스는 절대 복구되지 않습니다.**
> 아래 목록의 소스를 다시 추가하거나, 다른 URL로 재시도하는 것은
> 시간 낭비입니다. 검증된 대체 수단을 사용하세요.

---

## 1. 영구 폐쇄 확인 소스 (RSS 없음)

| 소스 | 오류 | 원인 |
|---|---|---|
| theinvestor.vn | 404 | RSS 완전 폐쇄 |
| vir.com.vn | 410 Gone | RSS 완전 폐쇄 |
| constructionvietnam.net | DNS 없음 | 사이트 폐쇄 |
| monre.gov.vn | SSL 오류 | 자체 서명 인증서 |
| vea.gov.vn | DNS 없음 | 도메인 없음 |
| mic.gov.vn | DNS 없음 | 도메인 없음 |
| smartcity.mobi | SSL 만료 | 인증서 만료 |

---

## 2. 봇 차단 / SSL 만료 소스

| 소스 | 오류 | 비고 |
|---|---|---|
| baotintuc.vn (2개) | SSL UNSAFE_LEGACY | 구식 SSL 설정 |
| kinhtemoitruong.vn | 403 Forbidden | 봇 차단 |
| hanoimoi.vn | 403 Forbidden | 봇 차단 |
| en.baobacgiang.vn | SSL 인증서 만료 | |
| moitruong.com.vn | SSL 인증서 만료 | |
| ictvietnam.vn | SSL 인증서 만료 | |

---

## 3. RSS 검증 완료 대체 소스 (2026-04-07, 52개 테스트)

```
52개 후보 테스트 → 6개 정상 확인
```

| 소스명 | RSS URL | 건수/회 | 역할 |
|---|---|---|---|
| Hanoi Times | https://hanoitimes.vn/rss/home.rss | 20건 | 전문미디어 하노이 인프라 |
| PV-Tech | https://www.pv-tech.org/feed/ | 50건 | 국제 태양광/재생에너지 |
| Energy Monitor | https://www.energymonitor.ai/rss | 10건 | 국제 에너지전환 |
| Nikkei Asia | https://asia.nikkei.com/rss/feed/nar | 50건 | 아시아 비즈니스 |
| Moi truong & CS | https://moitruong.net.vn/rss/home.rss | 30건 | 환경/폐기물 베트남어 |
| VietnamNet ICT | https://vietnamnet.vn/rss/cong-nghe.rss | 36건 | 스마트시티/ICT |

---

## 4. 전문미디어 HTML 크롤링 대체 (specialist_crawler.py v4.0)

RSS가 폐쇄된 전문미디어는 HTML 직접 크롤링으로 수집.

### theinvestor.vn

```
카테고리 URL:
  https://theinvestor.vn/infrastructure/
  https://theinvestor.vn/energy/
  https://theinvestor.vn/industrial-real-estate/
  https://theinvestor.vn/real-estate/
  https://theinvestor.vn/environment/

기사 URL 패턴 (정규식):
  /[a-z0-9-]+-d\d+\.html
  예) /ree-targets-record-revenue-d18743.html
```

### vir.com.vn

```
카테고리 URL:
  https://vir.com.vn/infrastructure.html
  https://vir.com.vn/energy.html
  https://vir.com.vn/industrial-zones.html

기사 URL 패턴 (정규식):
  /[a-z0-9-]+-\d+\.html
  예) /when-infrastructure-shapes-142390.html

페이지네이션: ?start=10, ?start=20, ...
```

---

## 5. NewsData.io Free 플랜 제약 사항

### 422 오류 유발 파라미터 — 절대 사용 금지

| 파라미터 | 오류 | 대체 방법 |
|---|---|---|
| `domain=theinvestor.vn` | 422 | 쿼리에 키워드 포함 |
| `site:theinvestor.vn` | 422 | Free 플랜 미지원 |
| `from_date=2026-04-05` | 422 | /latest API 미지원 |
| `category` + `domain` 조합 | 422 | category 또는 domain 하나만 |

### 정상 작동 조합

```python
params = {
    'apikey':   NEWSDATA_API_KEY,
    'q':        'Vietnam wastewater OR "nuoc thai"',  # 키워드만
    'country':  'vn',
    'language': 'en',
    'size':     10,
    # category는 domain 없을 때만
}
# 엔드포인트: /api/1/latest (not /news)
```

### 422 자동 재시도 로직

```python
resp = requests.get('https://newsdata.io/api/1/latest', params=params)
if resp.status_code == 422:
    params.pop('category', None)   # category 제거 후 재시도
    resp = requests.get('https://newsdata.io/api/1/latest', params=params)
```

---

## 6. 현재 운영 중인 워크플로 스케줄

| 워크플로 | 실행 시각 (KST) | concurrency group | 역할 |
|---|---|---|---|
| daily_pipeline.yml | 매일 20:00 | news-collection | 24시간 RSS 수집 |
| weekly_backfill.yml | 수·일 10:00 | backfill | NewsData 섹터 보완 |
| vietnam-infra-news.yml | 토 22:00 | weekly-collection | 7일치 + specialist_crawler |

**충돌 방지:** 3개 워크플로가 서로 다른 concurrency group 사용.
토요일: daily(20:00 완료) → vietnam-infra-news(22:00 시작) 순서로 충돌 없음.

---

## 7. DeepL 번역 API 설정

```
DeepL API Free 플랜:
  월 500,000자 무료
  키 형식: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx:fx ← :fx 필수
  엔드포인트: https://api-free.deepl.com/v2/translate
  GitHub Secret: DEEPL_API_KEY

번역 폴백 체인 (news_collector.py v5.9):
  1순위: DeepL API Free
  2순위: MyMemory (일 5,000자, WARNING 필터)
  3순위: deep-translator (Google)
```

---

## 8. 품질 목표 및 현재 상태 (2026-04-07)

| 지표 | 현재 | 목표 |
|---|---|---|
| 품질 등급 | D | B 이상 |
| Province 미분류율 | 0% | ≤25% ✅ |
| 전문미디어 비율 | ~9% | ≥30% |
| 섹터 커버리지 | 3~5/7 | 7/7 |
| 정책 연계율 | 0% | ≥30% |

**전문미디어 30% 달성 경로:**
- specialist_crawler.py v4.0 (주 1회 토요일 실행)
- Hanoi Times RSS (매일 20건 수집)
- The Investor + VIR HTML 크롤링

---

*이 파일은 Claude Code Agent와 Genspark Agent가 공유하는 시스템 지식 문서입니다.*
*동일한 RSS 접근 문제가 발생하면 반드시 이 문서를 먼저 확인하세요.*
