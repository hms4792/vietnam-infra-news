"""
quality_context_agent.py — v2.1 (2026-04-25 수정)
====================================================
SA-6: 품질검증 + 정책매핑 에이전트

수정 내역 (v2.0 → v2.1):
  1. [BUG FIX] 매칭 대상 필드 수정
     - v2.0: title_ko(한국어)를 영어 키워드와 비교 → 항상 0건
     - v2.1: title_en(영어) AND title_ko(한국어) 모두 검사
  2. [BUG FIX] Excel 컬럼 읽기 헤더 기반으로 변경
     - v2.0: 인덱스 기반 (row[7] 등) → 컬럼 순서 변경 시 오류
     - v2.1: 헤더 이름 기반 → 순서 무관하게 안정적 동작
  3. [BUG FIX] keywords_vi(베트남어) 키워드도 추가 검사
     - 베트남어 기사가 섞인 경우 vi 키워드로도 매칭
  4. [NEW] Matched_Plan 시트에 매칭 결과 직접 기록
     - plan_id, ctx_grade, ctx_stage 컬럼 업데이트
  5. [NEW] 매칭 통계 상세 로그 추가

EXCEL_PATH: data/database/Vietnam_Infra_News_Database_Final.xlsx
KI_PATH:    docs/shared/knowledge_index.json (우선)
"""

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

import openpyxl

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
log = logging.getLogger('quality_context_agent')

# ── 경로 ───────────────────────────────────────────────────────────────────
BASE_DIR  = Path(__file__).parent.parent
DATA_DIR  = BASE_DIR / 'data'
AGENT_OUT = DATA_DIR / 'agent_output'
DOCS_OUT  = BASE_DIR / 'docs' / 'shared'

EXCEL_PATH = DATA_DIR / 'database' / 'Vietnam_Infra_News_Database_Final.xlsx'

KI_PATHS = [
    DOCS_OUT / 'knowledge_index.json',           # 실제 경로 (Genspark 공유)
    DATA_DIR / 'shared' / 'knowledge_index.json',
    DATA_DIR / 'shared' / 'layer1_data.json',
]

# ── 설정 ───────────────────────────────────────────────────────────────────
RECENT_DAYS = 90        # 최근 N일 기사만 정책 매칭 대상
MIN_SCORE   = 35        # 매핑 최소 점수 (0~100)
GRADE_HIGH  = 65        # HIGH 기준 점수
GRADE_MED   = 45        # MEDIUM 기준 점수

# ── Province 정규화 ────────────────────────────────────────────────────────
PROVINCE_MAP = {
    # 영어 → 표준 영어
    'ho chi minh':   'Ho Chi Minh City',
    'hcmc':          'Ho Chi Minh City',
    'saigon':        'Ho Chi Minh City',
    'hà nội':        'Hanoi',
    'ha noi':        'Hanoi',
    'đà nẵng':       'Da Nang',
    'da nang':       'Da Nang',
    'hải phòng':     'Hai Phong',
    'hai phong':     'Hai Phong',
    'cần thơ':       'Can Tho',
    'ninh thuận':    'Ninh Thuan',
    'ninh thuan':    'Ninh Thuan',
    'bình dương':    'Binh Duong',
    'bình định':     'Binh Dinh',
    'long an':       'Long An',
    'đồng nai':      'Dong Nai',
    'dong nai':      'Dong Nai',
    'quảng ninh':    'Quang Ninh',
    'quang ninh':    'Quang Ninh',
}

def normalize_province(text: str) -> str:
    if not text:
        return 'Vietnam'
    low = text.lower().strip()
    return PROVINCE_MAP.get(low, text.strip())


# ══════════════════════════════════════════════════════════════════════════
# 1. knowledge_index 로드
# ══════════════════════════════════════════════════════════════════════════
def load_ki() -> dict:
    for path in KI_PATHS:
        if path.exists():
            with open(path, encoding='utf-8') as f:
                ki = json.load(f)
            plans = ki.get('masterplans', ki)
            log.info(f"knowledge_index 로드: {len(plans)}개 플랜 [{path.name}]")
            return plans
    log.warning("knowledge_index 없음")
    return {}


# ══════════════════════════════════════════════════════════════════════════
# 2. 정책 키워드 딕셔너리 빌드
# ══════════════════════════════════════════════════════════════════════════
def build_keyword_dict(plans: dict) -> list[dict]:
    """
    각 플랜의 keywords_en + keywords_vi + keywords(통합) 를 모아
    [{plan_id, keywords_en, keywords_vi, sector, area, score_base}] 반환
    """
    result = []
    for pid, p in plans.items():
        kw_en = p.get('keywords_en', p.get('keywords', []))
        kw_vi = p.get('keywords_vi', [])
        if not kw_en and not kw_vi:
            continue
        result.append({
            'plan_id':     pid,
            'keywords_en': [k.lower() for k in kw_en if k],
            'keywords_vi': [k.lower() for k in kw_vi if k],
            'sector':      p.get('sector', ''),
            'area':        p.get('area', ''),
            'threshold':   p.get('threshold', MIN_SCORE),
        })
    log.info(f"정책 키워드 딕셔너리: {len(result)}개 플랜")
    return result


# ══════════════════════════════════════════════════════════════════════════
# 3. 단일 기사 ↔ 플랜 매칭 점수 계산
# ══════════════════════════════════════════════════════════════════════════
def score_article(title_en: str, title_ko: str, summary_en: str, summary_ko: str,
                  plan: dict) -> float:
    """
    기사 텍스트와 플랜 키워드를 비교해 0~100 점수 반환.
    - 제목 매칭: 키워드당 25점
    - 요약 매칭: 키워드당 10점
    - 최대 100점 cap
    핵심 수정: title_en + summary_en 를 영어 키워드와 비교
              title_ko + summary_ko 를 베트남/한국어 키워드와 비교
    """
    score = 0.0
    # 검색 대상 텍스트 (소문자)
    en_text  = (title_en  + ' ' + summary_en).lower()
    ko_text  = (title_ko  + ' ' + summary_ko).lower()

    for kw in plan['keywords_en']:
        if kw in en_text:
            # 제목에 있으면 25점, 요약에만 있으면 10점
            if kw in title_en.lower():
                score += 25
            else:
                score += 10

    for kw in plan['keywords_vi']:
        if kw in ko_text:  # title_ko에 베트남어 단어 포함 가능
            if kw in title_ko.lower():
                score += 20
            else:
                score += 8

    return min(score, 100.0)


# ══════════════════════════════════════════════════════════════════════════
# 4. Excel 로드 + 매칭 실행 + 결과 기록
# ══════════════════════════════════════════════════════════════════════════
def run_matching(plans: dict, keyword_dict: list) -> dict:
    if not EXCEL_PATH.exists():
        log.error(f"Excel DB 없음: {EXCEL_PATH}")
        return {'error': 'excel_not_found'}

    log.info(f"Excel 로드: {EXCEL_PATH}")
    wb = openpyxl.load_workbook(EXCEL_PATH, data_only=True)

    if 'News Database' not in wb.sheetnames:
        log.error("'News Database' 시트 없음")
        wb.close()
        return {'error': 'sheet_not_found'}

    ws = wb['News Database']

    # ── 헤더 기반 컬럼 인덱스 찾기 ────────────────────────────────────────
    headers = {}
    for cell in ws[1]:
        if cell.value:
            key = str(cell.value).strip().lower().replace(' ', '_')
            headers[key] = cell.column - 1  # 0-based

    log.info(f"Excel 헤더: {list(headers.keys())}")

    # 컬럼 인덱스 (없으면 -1)
    def col(names):
        for n in names:
            if n in headers:
                return headers[n]
        return -1

    C = {
        'date':       col(['date']),
        'title_en':   col(['title', 'news_title', 'title_en']),
        'title_ko':   col(['tit_ko', 'title_ko']),
        'summary_en': col(['short_summary', 'summary_en', 'sum_en']),
        'summary_ko': col(['sum_ko', 'summary_ko']),
        'province':   col(['province']),
        'plan_id':    col(['plan_id', 'matched_plan']),
        'grade':      col(['grade', 'ctx_grade']),
        'source':     col(['source']),
    }
    log.info(f"컬럼 매핑: {C}")

    cutoff = (datetime.now() - timedelta(days=RECENT_DAYS)).strftime('%Y-%m-%d')

    stats = {
        'total': 0, 'matched': 0, 'high': 0, 'medium': 0, 'low_skip': 0,
        'province_fixed': 0, 'skipped_old': 0,
        'plan_counts': {},
    }

    # ── 행별 처리 ─────────────────────────────────────────────────────────
    matched_rows = []  # (row_num, plan_id, grade, score)

    for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
        if not row or not any(row):
            continue
        stats['total'] += 1

        def rv(idx):
            if idx < 0 or idx >= len(row): return ''
            return str(row[idx] or '').strip()

        date_val    = rv(C['date'])[:10]
        title_en    = rv(C['title_en'])
        title_ko    = rv(C['title_ko'])
        summary_en  = rv(C['summary_en'])
        summary_ko  = rv(C['summary_ko'])
        province    = rv(C['province'])

        # 오래된 기사 스킵
        if date_val and date_val < cutoff:
            stats['skipped_old'] += 1
            continue

        if not title_en and not title_ko:
            continue

        # 최고 점수 플랜 찾기
        best_plan  = None
        best_score = 0.0
        for plan in keyword_dict:
            sc = score_article(title_en, title_ko, summary_en, summary_ko, plan)
            if sc >= plan['threshold'] and sc > best_score:
                best_score = sc
                best_plan  = plan

        if best_plan:
            pid   = best_plan['plan_id']
            grade = 'HIGH' if best_score >= GRADE_HIGH else ('MEDIUM' if best_score >= GRADE_MED else 'LOW')
            stats['matched'] += 1
            stats['plan_counts'][pid] = stats['plan_counts'].get(pid, 0) + 1
            if grade == 'HIGH':   stats['high']   += 1
            elif grade == 'MEDIUM': stats['medium'] += 1
            matched_rows.append((row_num, pid, grade, best_score))

        # Province 정규화
        normed = normalize_province(province)
        if normed != province:
            stats['province_fixed'] += 1

    log.info(f"분류 완료: {stats['total']}건 (최근 {RECENT_DAYS}일 대상)")
    log.info(f"  POLICY_MATCH: {stats['matched']}건")
    log.info(f"  HIGH: {stats['high']}건  MEDIUM: {stats['medium']}건")
    log.info(f"  오래된 기사 스킵: {stats['skipped_old']}건")
    log.info(f"  Province 정규화: {stats['province_fixed']}건")

    # ── Excel Plan_ID·Grade 컬럼 업데이트 ────────────────────────────────
    wb2 = openpyxl.load_workbook(EXCEL_PATH, data_only=False)
    ws2 = wb2['News Database']

    # plan_id, grade 컬럼 확인 (없으면 추가)
    hdr_row = list(ws2[1])
    existing_headers = {str(c.value or '').strip().lower(): c.column for c in hdr_row if c.value}

    def ensure_col(col_name, after_col=8):
        lower = col_name.lower()
        for h, c in existing_headers.items():
            if lower in h:
                return c
        # 없으면 마지막 컬럼 뒤에 추가
        max_col = max(existing_headers.values()) if existing_headers else after_col
        new_col = max_col + 1
        ws2.cell(row=1, column=new_col, value=col_name)
        existing_headers[lower] = new_col
        return new_col

    plan_col  = ensure_col('Plan_ID')
    grade_col = ensure_col('Grade')

    for row_num, pid, grade, score in matched_rows:
        ws2.cell(row=row_num, column=plan_col,  value=pid)
        ws2.cell(row=row_num, column=grade_col, value=grade)

    # Matched_Plan 시트 업데이트
    if 'Matched_Plan' not in wb2.sheetnames:
        ws_mp = wb2.create_sheet('Matched_Plan')
        ws_mp.append(['Plan_ID', 'Date', 'Title_EN', 'Title_KO', 'Grade', 'Score', 'Source'])
    else:
        ws_mp = wb2['Matched_Plan']
        # 헤더만 남기고 초기화
        for r in range(ws_mp.max_row, 1, -1):
            ws_mp.delete_rows(r)

    # 매칭된 기사 Matched_Plan 시트에 기록
    for row_num, pid, grade, score in matched_rows:
        orig_row = list(ws.iter_rows(min_row=row_num, max_row=row_num, values_only=True))[0]
        date_v  = str(orig_row[C['date']] or '')[:10]
        t_en    = str(orig_row[C['title_en']] or '')
        t_ko    = str(orig_row[C['title_ko']] or '')
        src     = str(orig_row[C['source']]   or '')
        ws_mp.append([pid, date_v, t_en, t_ko, grade, round(score, 1), src])

    wb.close()
    wb2.save(EXCEL_PATH)
    wb2.close()
    log.info(f"Excel 업데이트 완료: Plan_ID/Grade 컬럼 기록 + Matched_Plan 시트 {len(matched_rows)}건")

    return stats


# ══════════════════════════════════════════════════════════════════════════
# 5. quality_report.json 저장
# ══════════════════════════════════════════════════════════════════════════
def save_report(stats: dict):
    AGENT_OUT.mkdir(parents=True, exist_ok=True)
    DOCS_OUT.mkdir(parents=True, exist_ok=True)

    report = {
        'generated_at':   datetime.now().strftime('%Y-%m-%d %H:%M'),
        'total_articles':  stats.get('total', 0),
        'matched_count':   stats.get('matched', 0),
        'match_rate_pct':  round(stats.get('matched', 0) / max(stats.get('total', 1), 1) * 100, 1),
        'grade_high':      stats.get('high', 0),
        'grade_medium':    stats.get('medium', 0),
        'province_fixed':  stats.get('province_fixed', 0),
        'plan_counts':     stats.get('plan_counts', {}),
        'skipped_old':     stats.get('skipped_old', 0),
    }

    out = DOCS_OUT / 'quality_report.json'
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    log.info(f"quality_report.json 저장: {out}")


# ══════════════════════════════════════════════════════════════════════════
# 메인
# ══════════════════════════════════════════════════════════════════════════
def main():
    log.info("=" * 58)
    log.info(f"quality_context_agent v2.1 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log.info("=" * 58)

    plans       = load_ki()
    if not plans:
        log.error("플랜 데이터 없음 — 종료")
        return

    keyword_dict = build_keyword_dict(plans)
    stats        = run_matching(plans, keyword_dict)
    save_report(stats)

    log.info("━" * 58)
    log.info(f"SA-6 v2.1 완료: {stats.get('matched', 0)}건 매칭 / {stats.get('total', 0)}건 전체")
    log.info(f"  매칭률: {round(stats.get('matched',0)/max(stats.get('total',1),1)*100,1)}%")
    log.info("━" * 58)


if __name__ == '__main__':
    main()
