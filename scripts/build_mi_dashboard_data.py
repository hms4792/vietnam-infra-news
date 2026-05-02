"""
build_mi_dashboard_data.py
===========================
역할: MI Dashboard에 필요한 모든 데이터를 JSON으로 생성

입력:
  - data/database/Vietnam_Infra_News_Database_Final.xlsx  (News Database + Matched_Plan 시트)
  - data/agent_output/context_output.json                 (SA-7 맥락분석 결과)
  - data/agent_output/stage_timeline.json                 (SA-7 진행단계 타임라인)
  - data/agent_output/mi_daily_*.json                     (SA-8 일일 분석 결과)
  - docs/shared/knowledge_index.json                      (마스터플랜 메타데이터)

출력:
  - docs/shared/mi_dashboard_data.json  ← mi_dashboard.html이 fetch로 로드

실행:
  python3 scripts/build_mi_dashboard_data.py

GitHub Actions 연동:
  daily_pipeline.yml  — SA-8 직후 실행 (매일 KST 20:00)
  collect_weekly.yml  — SA-8 주간 보고서 생성 후 실행 (토 KST 22:00)

영구 제약:
  - EXCEL_PATH: data/database/Vietnam_Infra_News_Database_Final.xlsx
  - KI_PATH: docs/shared/knowledge_index.json 우선 탐색
  - date 키: article.get('date') or article.get('published_date')

버전: v1.0 (2026-04-25)
"""

import json
import logging
import os
import glob
from datetime import datetime, timedelta
from pathlib import Path

import openpyxl

# ── 경로 ──────────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent.parent
DATA_DIR      = BASE_DIR / 'data'
AGENT_OUT_DIR = DATA_DIR / 'agent_output'
DOCS_SHARED   = BASE_DIR / 'docs' / 'shared'
REPORTS_DIR   = BASE_DIR / 'docs' / 'reports'

EXCEL_PATH    = DATA_DIR / 'database' / 'Vietnam_Infra_News_Database_Final.xlsx'
CONTEXT_OUT   = AGENT_OUT_DIR / 'context_output.json'
TIMELINE_OUT  = AGENT_OUT_DIR / 'stage_timeline.json'
OUTPUT_PATH   = DOCS_SHARED / 'mi_dashboard_data.json'

KI_PATHS = [
    DOCS_SHARED / 'knowledge_index.json',
    DATA_DIR / 'shared' / 'knowledge_index.json',
    DATA_DIR / 'shared' / 'layer1_data.json',
]

# ── 로깅 ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='[DashData %(asctime)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('DashData')

# ── 진행단계 한국어 매핑 ──────────────────────────────────────────────────
STAGE_LABEL = {
    'PLANNING':     {'ko': '계획·승인',  'en': 'Planning',     'vi': 'Lập kế hoạch'},
    'TENDERING':    {'ko': '입찰·계약',  'en': 'Tendering',    'vi': 'Đấu thầu'},
    'CONSTRUCTION': {'ko': '건설·시공',  'en': 'Construction', 'vi': 'Xây dựng'},
    'COMPLETION':   {'ko': '준공·개통',  'en': 'Completion',   'vi': 'Hoàn thành'},
    'OPERATION':    {'ko': '운영·확장',  'en': 'Operation',    'vi': 'Vận hành'},
    'UNKNOWN':      {'ko': '미확정',     'en': 'Unknown',      'vi': 'Chưa xác định'},
}


# ══════════════════════════════════════════════════════════════════════════
#  Step 1: knowledge_index 로드
# ══════════════════════════════════════════════════════════════════════════
def load_knowledge_index() -> dict:
    for path in KI_PATHS:
        if path.exists():
            with open(path, 'r', encoding='utf-8') as f:
                ki = json.load(f)
            plans = ki.get('masterplans', ki)
            for pid, p in plans.items():
                p['plan_id'] = pid
            log.info(f"knowledge_index 로드: {len(plans)}개 플랜 [{path.name}]")
            return plans
    log.warning("knowledge_index 없음 — 빈 플랜 사용")
    return {}


# ══════════════════════════════════════════════════════════════════════════
#  Step 2: Excel에서 Matched_Plan 기사 추출
# ══════════════════════════════════════════════════════════════════════════
def load_matched_articles() -> tuple[list[dict], dict]:
    """
    Excel Matched_Plan 시트 또는 News Database에서 플랜 매핑 기사 추출.

    Returns:
        (matched_articles, stats)
        matched_articles: plan_id별 기사 목록
        stats: 전체 통계 (total_articles, matched_count, updated_at)
    """
    if not EXCEL_PATH.exists():
        log.warning(f"Excel DB 없음: {EXCEL_PATH}")
        return [], {'total_articles': 0, 'matched_count': 0, 'updated_at': ''}

    wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True, data_only=True)

    # 전체 기사 수
    total = 0
    if 'News Database' in wb.sheetnames:
        ws_nd = wb['News Database']
        total = ws_nd.max_row - 1  # 헤더 제외

    matched_articles = []
    matched_count    = 0

    # Matched_Plan 시트 우선 시도
    if 'Matched_Plan' in wb.sheetnames:
        ws = wb['Matched_Plan']
        headers = [str(c.value or '').strip().lower().replace(' ', '_')
                   for c in next(ws.iter_rows(min_row=1, max_row=1))]

        def ci(keys):
            for k in keys:
                for i, h in enumerate(headers):
                    if k in h:
                        return i
            return None

        COL = {
            'plan_id':   ci(['plan_id', 'matched_plan']),
            'date':      ci(['date']),
            'title_ko':  ci(['title_ko']),
            'title_en':  ci(['title_en', 'title_(en/vi)', 'title', 'news_title']),
            'title_vi':  ci(['title_vi']),
            'summary_ko': ci(['summary_ko']),
            'summary_en': ci(['summary_en', 'short_summary']),
            'source':    ci(['source']),
            'url':       ci(['link', 'url']),
            'ctx_grade': ci(['ctx_grade']),
            'stage':     ci(['stage', 'ctx_stage']),
            'milestone': ci(['milestone']),
        }

        for row in ws.iter_rows(min_row=2, values_only=True):
            plan_id  = str(row[COL['plan_id']] if COL['plan_id'] is not None else '').strip()
            date_val = str(row[COL['date']] if COL['date'] is not None else '').strip()[:10]
            title_ko = str(row[COL['title_ko']] if COL['title_ko'] is not None else '').strip()
            title_en = str(row[COL['title_en']] if COL['title_en'] is not None else '').strip()

            if not plan_id or not date_val:
                continue

            matched_articles.append({
                'plan_id':    plan_id,
                'date':       date_val,
                'title_ko':   title_ko or title_en,
                'title_en':   title_en or title_ko,
                'title_vi':   str(row[COL['title_vi']] if COL['title_vi'] is not None else '').strip(),
                'summary_ko': str(row[COL['summary_ko']] if COL['summary_ko'] is not None else '').strip()[:200],
                'summary_en': str(row[COL['summary_en']] if COL['summary_en'] is not None else '').strip()[:200],
                'source':     (row[COL['source']] if COL['source'] is not None else None) or 'Unknown',
                'url':        str(row[COL['url']] if COL['url'] is not None else '').strip(),
                'grade':      str(row[COL['ctx_grade']] if COL['ctx_grade'] is not None else 'MEDIUM').strip() or 'MEDIUM',
                'stage':      str(row[COL['stage']] if COL['stage'] is not None else 'UNKNOWN').strip() or 'UNKNOWN',
                'milestone':  str(row[COL['milestone']] if COL['milestone'] is not None else '').strip(),
            })
            matched_count += 1

        log.info(f"Matched_Plan 시트: {matched_count}건")

    else:
        # News Database에서 ctx_plans 있는 것만 추출
        log.warning("Matched_Plan 시트 없음 — News Database에서 추출")
        if 'News Database' in wb.sheetnames:
            ws = wb['News Database']
            headers = [str(c.value or '').strip().lower().replace(' ', '_')
                       for c in next(ws.iter_rows(min_row=1, max_row=1))]

            def ci2(keys):
                for k in keys:
                    for i, h in enumerate(headers):
                        if k in h:
                            return i
                return None

            COL2 = {
                'ctx_plans': ci2(['ctx_plans', 'matched_plan']),
                'date':      ci2(['date']),
                'title_ko':  ci2(['title_ko']),
                'title_en':  ci2(['title_en', 'news_title']),
                'summary_ko': ci2(['summary_ko']),
                'summary_en': ci2(['summary_en', 'short_summary']),
                'source':    ci2(['source']),
                'url':       ci2(['link', 'url']),
                'ctx_grade': ci2(['ctx_grade']),
            }

            cutoff = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')
            for row in ws.iter_rows(min_row=2, values_only=True):
                ctx_plans = str(row[COL2['ctx_plans']] if COL2['ctx_plans'] is not None else '').strip()
                if not ctx_plans:
                    continue
                date_val = str(row[COL2['date']] if COL2['date'] is not None else '').strip()[:10]
                if date_val < cutoff:
                    continue

                for pid in [p.strip() for p in ctx_plans.split(',') if p.strip()]:
                    title_ko = str(row[COL2['title_ko']] if COL2['title_ko'] is not None else '').strip()
                    title_en = str(row[COL2['title_en']] if COL2['title_en'] is not None else '').strip()
                    matched_articles.append({
                        'plan_id':    pid,
                        'date':       date_val,
                        'title_ko':   title_ko or title_en,
                        'title_en':   title_en or title_ko,
                        'title_vi':   '',
                        'summary_ko': str(row[COL2['summary_ko']] if COL2['summary_ko'] is not None else '').strip()[:200],
                        'summary_en': str(row[COL2['summary_en']] if COL2['summary_en'] is not None else '').strip()[:200],
                        'source':     (row[COL2['source']] if COL2['source'] is not None else None) or 'Unknown',
                        'url':        str(row[COL2['url']] if COL2['url'] is not None else '').strip(),
                        'grade':      str(row[COL2['ctx_grade']] if COL2['ctx_grade'] is not None else 'MEDIUM').strip() or 'MEDIUM',
                        'stage':      'UNKNOWN',
                        'milestone':  '',
                    })
                    matched_count += 1

    wb.close()

    # 날짜 기준 정렬
    matched_articles.sort(key=lambda x: x.get('date', ''), reverse=True)

    stats = {
        'total_articles': total,
        'matched_count':  matched_count,
        'updated_at':     datetime.now().strftime('%Y-%m-%d %H:%M'),
    }
    return matched_articles, stats


# ══════════════════════════════════════════════════════════════════════════
#  Step 3: SA-7 컨텍스트 + 타임라인 로드
# ══════════════════════════════════════════════════════════════════════════
def load_sa7_data() -> tuple[dict, dict]:
    ctx_by_plan:  dict[str, dict] = {}
    timeline:     dict[str, dict] = {}

    if CONTEXT_OUT.exists():
        with open(CONTEXT_OUT, 'r', encoding='utf-8') as f:
            ctx = json.load(f)
        for art in ctx.get('articles', []):
            pid = art.get('plan_id', '')
            if not pid:
                continue
            # 가장 최신 + 신뢰도 높은 기사 기준
            existing = ctx_by_plan.get(pid)
            if not existing or art.get('confidence', 0) > existing.get('confidence', 0):
                ctx_by_plan[pid] = {
                    'stage':      art.get('stage', 'UNKNOWN'),
                    'confidence': art.get('confidence', 0.0),
                    'milestone':  art.get('milestone', ''),
                    'next_watch': art.get('next_watch', ''),
                    'insight':    art.get('insight', ''),
                    'haiku_used': art.get('haiku_used', False),
                }
        log.info(f"SA-7 context: {len(ctx_by_plan)}개 플랜")

    if TIMELINE_OUT.exists():
        with open(TIMELINE_OUT, 'r', encoding='utf-8') as f:
            tl = json.load(f)
        timeline = tl.get('plans', {})
        log.info(f"SA-7 timeline: {len(timeline)}개 플랜")

    return ctx_by_plan, timeline


# ══════════════════════════════════════════════════════════════════════════
#  Step 4: SA-8 일일 분석 JSON 로드 (최신 파일)
# ══════════════════════════════════════════════════════════════════════════
def load_sa8_daily() -> dict:
    pattern = str(AGENT_OUT_DIR / 'mi_daily_*.json')
    files   = sorted(glob.glob(pattern), reverse=True)
    if not files:
        log.info("SA-8 daily JSON 없음")
        return {}
    latest = files[0]
    with open(latest, 'r', encoding='utf-8') as f:
        data = json.load(f)
    log.info(f"SA-8 daily 로드: {Path(latest).name}")
    return data


# ══════════════════════════════════════════════════════════════════════════
#  Step 5: 보고서 파일 목록 스캔
# ══════════════════════════════════════════════════════════════════════════
def scan_reports() -> list[dict]:
    """
    docs/reports/ 폴더에서 실제 존재하는 Word/PPT 파일을 스캔.
    파일명 패턴: VN_Infra_MI_Weekly_Report_*YYYYMMDD*.docx / *.pptx
    """
    reports_dir = REPORTS_DIR
    report_map  = {}

    if reports_dir.exists():
        # docx 파일
        for f in sorted(reports_dir.glob('VN_Infra_MI_Weekly_Report_*.docx'), reverse=True):
            key = f.stem.replace('_Full', '')
            report_map.setdefault(key, {})['word_url'] = f'reports/{f.name}'
            report_map[key]['word_exists'] = True

        # pptx 파일
        for f in sorted(reports_dir.glob('VN_Infra_MI_Weekly_Report_*.pptx'), reverse=True):
            key = f.stem
            report_map.setdefault(key, {})['pptx_url'] = f'reports/{f.name}'
            report_map[key]['pptx_exists'] = True

    reports = []
    for key, info in sorted(report_map.items(), reverse=True):
        # 날짜 추출 (마지막 8자리 숫자)
        import re
        m = re.search(r'(\d{8})', key)
        date_str = ''
        week_str = ''
        if m:
            d = m.group(1)
            try:
                dt = datetime.strptime(d, '%Y%m%d')
                date_str = dt.strftime('%Y-%m-%d')
                # ISO 주차
                iso = dt.isocalendar()
                week_str = f'{iso[0]}-W{iso[1]:02d}'
            except ValueError:
                date_str = d

        reports.append({
            'week':       week_str or key,
            'date':       date_str,
            'word_url':   info.get('word_url', ''),
            'pptx_url':   info.get('pptx_url', ''),
            'word_exists': info.get('word_exists', False),
            'pptx_exists': info.get('pptx_exists', False),
        })

    log.info(f"보고서 파일 스캔: {len(reports)}개")
    return reports


# ══════════════════════════════════════════════════════════════════════════
#  Step 6: 플랜별 데이터 조립
# ══════════════════════════════════════════════════════════════════════════
def assemble_plan_data(
    plans:           dict,
    matched_articles: list[dict],
    ctx_by_plan:     dict,
    timeline:        dict,
    sa8_daily:       dict,
) -> dict:
    """
    플랜별로 기사·진행단계·AI 분석·타임라인을 조립.

    Returns:
        {plan_id: {meta, articles, stage, insight, next_watch, timeline_items}}
    """
    # 기사를 플랜별로 그룹핑
    art_by_plan: dict[str, list] = {}
    for art in matched_articles:
        pid = art.get('plan_id', '')
        if pid:
            art_by_plan.setdefault(pid, []).append(art)

    result = {}

    # knowledge_index에 있는 플랜 + 기사가 있는 플랜 모두 처리
    all_pids = set(plans.keys()) | set(art_by_plan.keys())

    for pid in all_pids:
        plan_meta = plans.get(pid, {})
        arts      = art_by_plan.get(pid, [])
        ctx       = ctx_by_plan.get(pid, {})
        tl        = timeline.get(pid, {})

        # SA-7 진행단계 (없으면 knowledge_index의 stage, 없으면 UNKNOWN)
        stage = (
            ctx.get('stage')
            or tl.get('current_stage')
            or plan_meta.get('stage')
            or 'UNKNOWN'
        )

        # SA-8 daily에서 플랜별 분석 찾기
        sa8_plan = {}
        if sa8_daily:
            for sec in sa8_daily.get('plan_sections', []):
                if sec.get('plan_id') == pid:
                    sa8_plan = sec
                    break

        # 타임라인 이력
        tl_history = tl.get('stage_history', [])

        result[pid] = {
            'plan_id':    pid,
            'stage':      stage,
            'stage_label': STAGE_LABEL.get(stage, STAGE_LABEL['UNKNOWN']),
            'confidence': ctx.get('confidence', 0.0),
            'haiku_used': ctx.get('haiku_used', False),

            # Layer1 메타 (knowledge_index에서)
            'title_ko':       plan_meta.get('title_ko', pid),
            'description_ko': plan_meta.get('description_ko', ''),
            'decision':       plan_meta.get('decision', ''),
            'sector':         plan_meta.get('sector', ''),
            'area':           plan_meta.get('area', ''),
            'kpi_targets':    plan_meta.get('kpi_targets', []),
            'key_projects':   plan_meta.get('key_projects', []),

            # 기사 (최신 8건)
            'articles': [
                {
                    'date':      a.get('date', ''),
                    'title_ko':  a.get('title_ko', ''),
                    'title_en':  a.get('title_en', ''),
                    'title_vi':  a.get('title_vi', ''),
                    'summary_ko': a.get('summary_ko', ''),
                    'summary_en': a.get('summary_en', ''),
                    'grade':     a.get('grade', 'MEDIUM'),
                    'stage':     a.get('stage', 'UNKNOWN'),
                    'source':    a.get('source', ''),
                    'url':       a.get('url', ''),
                    'milestone': a.get('milestone', ''),
                }
                for a in arts[:8]
            ],
            'article_count': len(arts),

            # AI 분석
            'insight':    ctx.get('insight', '') or sa8_plan.get('insight_ko', ''),
            'next_watch': (
                ctx.get('next_watch', '')
                or tl.get('next_watch', '')
                or sa8_plan.get('next_watch_ko', '')
            ),
            'milestone': ctx.get('milestone', ''),

            # 타임라인 이정표
            'timeline': [
                {
                    'date':      item.get('date', ''),
                    'stage':     item.get('stage', 'UNKNOWN'),
                    'milestone_ko': item.get('milestone', ''),
                    'source':    item.get('source', ''),
                }
                for item in tl_history[:10]
            ],
        }

    log.info(f"플랜 데이터 조립: {len(result)}개")
    return result


# ══════════════════════════════════════════════════════════════════════════
#  메인
# ══════════════════════════════════════════════════════════════════════════
def main():
    log.info("=" * 58)
    log.info(f"MI Dashboard Data Builder v1.0 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log.info("=" * 58)

    # Step 1: 마스터플랜 메타
    plans = load_knowledge_index()

    # Step 2: 매핑 기사 (Excel)
    matched_articles, stats = load_matched_articles()

    # Step 3: SA-7 맥락분석
    ctx_by_plan, timeline = load_sa7_data()

    # Step 4: SA-8 daily
    sa8_daily = load_sa8_daily()

    # Step 5: 보고서 파일 스캔
    reports = scan_reports()

    # Step 6: 플랜 데이터 조립
    plan_data = assemble_plan_data(
        plans, matched_articles, ctx_by_plan, timeline, sa8_daily
    )

    # ── 최종 JSON 구성 ───────────────────────────────────────────────────
    output = {
        'generated_at':   datetime.now().strftime('%Y-%m-%d %H:%M'),
        'generated_date': datetime.now().strftime('%Y-%m-%d'),
        'stats': {
            'total_articles':  stats.get('total_articles', 0),
            'matched_count':   stats.get('matched_count', 0),
            'plan_count':      len(plan_data),
            'ki_plan_count':   len(plans),
            'report_count':    len(reports),
        },
        'reports':     reports,       # 보고서 다운로드 목록
        'plans':       plan_data,     # 플랜별 전체 데이터
    }

    # ── 저장 ─────────────────────────────────────────────────────────────
    DOCS_SHARED.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    size_kb = OUTPUT_PATH.stat().st_size // 1024
    log.info("")
    log.info("━" * 58)
    log.info(f"✅ MI Dashboard 데이터 빌드 완료")
    log.info(f"   출력: {OUTPUT_PATH}")
    log.info(f"   크기: {size_kb} KB")
    log.info(f"   플랜: {len(plan_data)}개")
    log.info(f"   기사: {stats.get('matched_count', 0)}건 (매핑)")
    log.info(f"   보고서: {len(reports)}개")
    log.info("━" * 58)


if __name__ == '__main__':
    main()
