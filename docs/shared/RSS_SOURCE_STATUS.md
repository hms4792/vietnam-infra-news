# RSS Source Status — Vietnam Infrastructure News
# 최종 업데이트: 2026-04-11
# Claude Code + Genspark Agent Team 공유 지식 문서

---

## 검증 완료 RSS 소스 (6개 — 2026-04-07 확인)

| 소스 | URL | 항목 수 | 비고 |
|---|---|---|---|
| Hanoi Times | https://hanoitimes.vn/rss/home.rss | 20건 | ✅ 정상 |
| PV-Tech | https://www.pv-tech.org/feed/ | 50건 | ✅ 정상 |
| Energy Monitor | https://www.energymonitor.ai/rss | 10건 | ✅ 정상 |
| Nikkei Asia | https://asia.nikkei.com/rss/feed/nar | 50건 | ✅ 정상 |
| Moi truong & Cuoc song | https://moitruong.net.vn/rss/home.rss | 30건 | ✅ 정상 |
| VietnamNet ICT | https://vietnamnet.vn/rss/cong-nghe.rss | 36건 | ✅ 정상 |

---

## 전문미디어 직접 크롤링 (specialist_crawler.py v4.0)

| 사이트 | 카테고리 URL | URL 패턴 | 상태 |
|---|---|---|---|
| theinvestor.vn | /infrastructure/, /energy/, /industrial-real-estate/ | `-d\d+\.html` | ✅ 크롤링 |
| vir.com.vn | /infrastructure.html | `-\d+\.html` | ✅ 크롤링 |

---

## 영구 폐쇄 소스 (절대 재추가 금지)

| 소스 | 이유 |
|---|---|
| theinvestor.vn RSS | 404 Not Found |
| vir.com.vn RSS | 410 Gone |
| constructionvietnam.net | DNS 오류 |
| monre.gov.vn | SSL 오류 |
| vea.gov.vn | DNS 오류 |
| mic.gov.vn | DNS 오류 |
| smartcity.mobi | SSL 만료 |
| petrotimes.vn | 404 Not Found |

---

## 봇 차단 소스 (재시도 금지)

| 소스 | 이유 |
|---|---|
| baotintuc.vn | SSL Legacy |
| kinhtemoitruong.vn | 403 Forbidden |
| hanoimoi.vn | 403 Forbidden |
| baobacgiang.vn | SSL 만료 |
| moitruong.com.vn | SSL 만료 |
| ictvietnam.vn | SSL 만료 |

---

## NewsData.io 제약 사항 (Free Plan)

- 사용 금지 파라미터: `domain`, `site:`, `from_date`, `category+domain` 조합
- 유효 조합: `country=vn + language=en/vi + q` (키워드만)
- 엔드포인트: `/api/1/latest`
- 일일 한도: 약 200 크레딧
- 422 오류 시: category 파라미터 제거 후 재시도

---

## Genspark Agent Team 참고사항

- 위 영구 폐쇄/봇 차단 소스는 절대 추가 시도 금지
- 전문 크롤링은 specialist_crawler.py가 담당 (토요일 22:00 자동)
- Claude 수집 결과: https://hms4792.github.io/vietnam-infra-news/shared/collector_output.json
