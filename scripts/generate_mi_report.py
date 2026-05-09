"""
generate_mi_report.py  ── SA-8 Sub Agent v4.0
=====================================================
역할: 주간 MI 보고서 자동 생성 (Claude Haiku AI 분석 통합)

v4.0 주요 변경 (2026-05-09):
  1. 과거 기사 누적 유지
     - days_back=90 (기존 7일 → 90일치 기사 전체 유지)
     - 각 기사에 is_new 태그: 최근 7일 = True, 그 이전 = False
     - JS 빌더에서 is_new=True인 기사만 노란색 하이라이트
  2. 이메일 발송 조건 수정
     - 기존: KPI 변동 있을 때만 발송 → 사실상 미발송
     - 수정: 신규 기사(is_new=True) 1건 이상이면 항상 발송
     - 신규 기사 없어도 KPI 변동 있으면 발송
  3. 이메일 본문 강화
     - 기사 수, 플랜 수, AI Executive Summary 본문 포함
     - 첨부 실패 시에도 텍스트 요약만이라도 발송

아키텍처 (2-레이어 설계):
  Layer 1 — 고정 데이터 (knowledge_index.json에서 로드)
    · 사업 개요, KPI 목표값, 주요 프로젝트 목록
  Layer 2 — AI 동적 분석 (Claude Haiku로 매주 생성)
    · 최신 기사 → Haiku → 사업개요 연계 분석문
    · 신규 기사 → 노란색 하이라이트
    · 플랜별 인사이트 + Executive Summary AI 논평

영구 제약:
  - Anthropic API: claude-haiku-4-5-20251001 (번역 금지, 분석에만)
  - Translation: Google Translate만 사용
  - 이메일 Secrets: EMAIL_USERNAME / EMAIL_PASSWORD
  - GitHub Pages: main 브랜치 /docs (gh-pages 금지)
"""

import glob as _glob
import json
import logging
import os
import re
import smtplib
import subprocess
import sys
import time
from datetime import datetime, timedelta
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import openpyxl
import requests

# ── 경로 설정 ──────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent.parent
SCRIPTS_DIR   = BASE_DIR / 'scripts'
DATA_DIR      = BASE_DIR / 'data'
DOCS_DIR      = BASE_DIR / 'docs'
AGENT_OUT_DIR = DATA_DIR / 'agent_output'
SHARED_DIR    = DATA_DIR / 'shared'

EXCEL_PATH    = DATA_DIR / 'database' / 'Vietnam_Infra_News_Database_Final.xlsx'
KI_PATH       = BASE_DIR / 'docs' / 'shared' / 'knowledge_index.json'
KI_PATH_ALT   = SHARED_DIR / 'knowledge_index.json'
KI_PATH_L1    = SHARED_DIR / 'layer1_data.json'
KPI_SNAP_PATH = AGENT_OUT_DIR / 'kpi_snapshot_weekly.json'
JS_BUILDER    = SCRIPTS_DIR / 'build_mi_report_sa8.js'

# SA-7 출력 파일 경로
CONTEXT_OUT  = BASE_DIR / 'data' / 'agent_output' / 'context_output.json'
TIMELINE_OUT = BASE_DIR / 'data' / 'agent_output' / 'stage_timeline.json'

# ── 로깅 ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='[SA-8 %(asctime)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger('SA-8')

# ── Anthropic API 설정 ────────────────────────────────────────────────────
ANTHROPIC_API_URL = 'https://api.anthropic.com/v1/messages'
HAIKU_MODEL       = 'claude-haiku-4-5-20251001'
MAX_TOKENS        = 1500
HAIKU_TIMEOUT     = 45

# v4.0: 기사 수집 기간 설정
DAYS_TOTAL  = 90   # 전체 유지 기간 (기존 기사 포함)
DAYS_NEW    = 7    # 신규 기사 기준 (노란 마킹 대상)


# ══════════════════════════════════════════════════════════════════════════
#  SA-7 연동
# ══════════════════════════════════════════════════════════════════════════
def load_sa7_context() -> dict:
    if not CONTEXT_OUT.exists():
        log.info("SA-7 context_output.json 없음 — 진행단계 데이터 없이 실행")
        return {}
    with open(CONTEXT_OUT, 'r', encoding='utf-8') as f:
        ctx = json.load(f)
    ctx_by_url = {}
    for art in ctx.get('articles', []):
        url = art.get('url', '')
        if url:
            ctx_by_url[url] = {
                'stage':      art.get('stage', 'UNKNOWN'),
                'milestone':  art.get('milestone', ''),
                'next_watch': art.get('next_watch', ''),
                'insight':    art.get('insight', ''),
                'confidence': art.get('confidence', 0.0),
                'haiku_used': art.get('haiku_used', False),
                'plan_id':    art.get('plan_id', ''),
            }
    log.info(f"SA-7 context_output 로드: {len(ctx_by_url)}건")
    return ctx_by_url


def load_sa7_timeline() -> dict:
    if not TIMELINE_OUT.exists():
        return {}
    with open(TIMELINE_OUT, 'r', encoding='utf-8') as f:
        tl = json.load(f)
    return tl.get('plans', {})


# ══════════════════════════════════════════════════════════════════════════
#  [STEP 1] knowledge_index.json 로드
# ══════════════════════════════════════════════════════════════════════════
def load_knowledge_index() -> dict:
    ki_file = None
    for candidate in [KI_PATH, KI_PATH_ALT, KI_PATH_L1]:
        if candidate.exists():
            ki_file = candidate
            break

    if not ki_file:
        log.warning("knowledge_index.json 없음 — 기본 플랜 구조 사용")
        return _default_knowledge_index()

    log.info(f"knowledge_index 로드: {ki_file}")
    with open(ki_file, 'r', encoding='utf-8') as f:
        ki = json.load(f)

    plans = ki.get('masterplans', {})
    log.info(f"knowledge_index 로드: {len(plans)}개 마스터플랜")
    return plans


def _default_knowledge_index() -> dict:
    return {
        "VN-WW-2030": {
            "title_ko": "폐수처리 인프라 국가 마스터플랜 2021~2030",
            "decision": "Decision 1354/QD-TTg",
            "description_ko": "국가 폐수처리 마스터플랜(2021~2030)은 도시 폐수처리율을 2025년 50%, 2030년 85%로 끌어올리는 것을 목표로 한다.",
            "kpi_targets": [
                {"indicator": "도시 폐수처리율", "target_2030": "85%", "current": "~29% (하노이)"},
                {"indicator": "신규 WWTP 용량",  "target_2030": "2,900,000 m³/일", "current": "약 800,000 m³/일"},
            ],
            "key_projects": [],
            "sectors": ["Waste Water"],
            "area": "Environment",
        },
    }


# ══════════════════════════════════════════════════════════════════════════
#  [STEP 2] Excel DB에서 기사 추출
#  v4.0: days_back=90으로 확장, 각 기사에 is_new 태그 부착
# ══════════════════════════════════════════════════════════════════════════
def _sector_to_area(sector: str) -> str:
    ENV = {'Waste Water', 'Water Supply/Drainage', 'Solid Waste', 'Environment'}
    ENG = {'Power', 'Oil & Gas'}
    if sector in ENV: return 'Environment'
    if sector in ENG: return 'Energy Develop.'
    if sector: return 'Urban Develop.'
    return 'Environment'


def extract_articles(days_back: int = DAYS_TOTAL) -> tuple[list[dict], list[dict]]:
    """
    Excel DB → 최근 days_back일 기사 추출.

    v4.0 변경:
      - days_back 기본값 90일 (기존 기사 누적 유지)
      - 각 기사에 is_new 태그 부착
        · is_new=True  : 최근 DAYS_NEW(7)일 이내 → 노란색 마킹 대상
        · is_new=False : 그 이전 → 회색 (기존 기사)

    Returns:
        (all_articles, new_articles)
        all_articles: 전체 기사 (is_new 태그 포함)
        new_articles: 신규 기사만 (이메일 발송 조건 판단용)
    """
    if not EXCEL_PATH.exists():
        log.warning(f"Excel DB 없음: {EXCEL_PATH}")
        return [], []

    wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True, data_only=True)
    if 'News Database' not in wb.sheetnames:
        log.warning("'News Database' 시트 없음")
        wb.close()
        return [], []

    ws      = wb['News Database']
    headers = [str(c.value or '').strip().lower().replace(' ', '_')
               for c in next(ws.iter_rows(min_row=1, max_row=1))]

    def col_idx(keys):
        for k in keys:
            for i, h in enumerate(headers):
                if k in h:
                    return i
        return None

    ci = {
        'date':       col_idx(['date']),
        'sector':     col_idx(['business_sector', 'sector', 'src_type']),
        'area':       col_idx(['area']),
        'province':   col_idx(['province']),
        'title_ko':   col_idx(['title_ko', 'tit_ko']),
        'title_en':   col_idx(['title_en', 'title_(en/vi)', 'title', 'news_title']),
        'summary_ko': col_idx(['summary_ko', 'sum_ko']),
        'summary_en': col_idx(['summary_en', 'short_summary', 'sum_en']),
        'source':     col_idx(['source']),
        'url':        col_idx(['link', 'url']),
        'ctx_grade':  col_idx(['ctx_grade', 'grade']),
        'ctx_plans':  col_idx(['ctx_plans', 'plan_id']),
    }

    today_str  = datetime.now().strftime('%Y-%m-%d')
    cutoff_all = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    cutoff_new = (datetime.now() - timedelta(days=DAYS_NEW)).strftime('%Y-%m-%d')

    all_articles = []
    new_articles = []

    for row in ws.iter_rows(min_row=2, values_only=True):
        date_val = str(row[ci['date']] if ci['date'] is not None else '').strip()[:10]
        if not date_val or date_val < cutoff_all:
            continue

        title_ko = str(row[ci['title_ko']] if ci['title_ko'] is not None else '').strip()
        if not title_ko:
            continue

        # ★ v4.0: is_new 태그 — 최근 7일 이내면 True
        is_new = (date_val >= cutoff_new)

        art = {
            'date':       date_val,
            'sector':     str(row[ci['sector']]    if ci['sector']    is not None else ''),
            'area':       (str(row[ci['area']] if ci['area'] is not None else '')
                           or _sector_to_area(str(row[ci['sector']] if ci['sector'] is not None else ''))),
            'province':   str(row[ci['province']]  if ci['province']  is not None else ''),
            'title_ko':   title_ko,
            'title_en':   str(row[ci['title_en']]  if ci['title_en']  is not None else ''),
            'summary_ko': str(row[ci['summary_ko']] if ci['summary_ko'] is not None else ''),
            'summary_en': str(row[ci['summary_en']] if ci['summary_en'] is not None else ''),
            'source':     str(row[ci['source']]    if ci['source']    is not None else ''),
            'url':        str(row[ci['url']]        if ci['url']        is not None else ''),
            'ctx_grade':  str(row[ci['ctx_grade']] if ci['ctx_grade'] is not None else 'MEDIUM'),
            'ctx_plans':  str(row[ci['ctx_plans']] if ci['ctx_plans'] is not None else ''),
            'is_new':     is_new,   # ★ v4.0 신규 태그
        }
        all_articles.append(art)
        if is_new:
            new_articles.append(art)

    wb.close()
    all_articles.sort(key=lambda x: x['date'], reverse=True)
    log.info(f"Excel DB 추출: 전체 {len(all_articles)}건 (신규 {len(new_articles)}건 / 기존 {len(all_articles)-len(new_articles)}건)")
    return all_articles, new_articles


def group_articles_by_plan(articles: list[dict], plans: dict) -> dict:
    """기사를 ctx_plans 기준으로 플랜별 그룹핑."""
    SECTOR_TO_PLAN = {
        'Waste Water':           ['VN-WW-2030'],
        'Water Supply/Drainage': ['VN-WAT-URBAN', 'VN-WAT-RESOURCES'],
        'Solid Waste':           ['VN-SWM-NATIONAL-2030'],
        'Power':                 ['VN-PWR-PDP8', 'VN-PWR-PDP8-RENEWABLE', 'VN-PWR-PDP8-LNG'],
        'Oil & Gas':             ['VN-OG-2030'],
        'Industrial Parks':      ['VN-IND-2030', 'VN-ENV-IND-1894'],
        'Smart City':            ['VN-URB-METRO-2030', 'VN-SMART-2025'],
        'Transport':             ['VN-TRAN-2055'],
    }

    grouped = {plan_id: [] for plan_id in plans}

    for art in articles:
        plan_ids = [p.strip() for p in art['ctx_plans'].split(',')
                    if p.strip() and p.strip() in plans]

        if not plan_ids:
            plan_ids = [p for p in SECTOR_TO_PLAN.get(art['sector'], [])
                        if p in plans]

        for pid in plan_ids:
            grouped.setdefault(pid, []).append(art)

    return grouped


# ══════════════════════════════════════════════════════════════════════════
#  [STEP 3] KPI 변동 감지
# ══════════════════════════════════════════════════════════════════════════
def detect_kpi_changes(plans: dict) -> dict:
    current_snap = {}
    for pid, plan in plans.items():
        current_snap[pid] = {
            'threshold':   plan.get('match_threshold', plan.get('threshold', 50)),
            'kw_en_count': len(plan.get('keywords_en', [])),
            'kw_vi_count': len(plan.get('keywords_vi', [])),
            'kpi_count':   len(plan.get('kpi_targets', [])),
        }

    AGENT_OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not KPI_SNAP_PATH.exists():
        log.info("KPI 스냅샷 없음 (초회 실행) — 이번 주 저장")
        with open(KPI_SNAP_PATH, 'w', encoding='utf-8') as f:
            json.dump(current_snap, f, ensure_ascii=False, indent=2)
        return {}

    with open(KPI_SNAP_PATH, 'r', encoding='utf-8') as f:
        prev_snap = json.load(f)

    changes = {}
    for pid, curr in current_snap.items():
        prev = prev_snap.get(pid, {})
        plan_changes = []

        if curr['threshold'] != prev.get('threshold', curr['threshold']):
            plan_changes.append(f"매칭 임계값 변동: {prev.get('threshold','?')} → {curr['threshold']}")

        diff_en = curr['kw_en_count'] - prev.get('kw_en_count', curr['kw_en_count'])
        diff_vi = curr['kw_vi_count'] - prev.get('kw_vi_count', curr['kw_vi_count'])
        if diff_en != 0:
            plan_changes.append(f"영문 키워드 {'+' if diff_en>0 else ''}{diff_en}개 변동")
        if diff_vi != 0:
            plan_changes.append(f"베트남어 키워드 {'+' if diff_vi>0 else ''}{diff_vi}개 변동")

        if plan_changes:
            changes[pid] = plan_changes

    with open(KPI_SNAP_PATH, 'w', encoding='utf-8') as f:
        json.dump(current_snap, f, ensure_ascii=False, indent=2)

    log.info(f"KPI 변동 감지: {len(changes)}개 플랜에서 변동")
    return changes


# ══════════════════════════════════════════════════════════════════════════
#  [STEP 4] Claude Haiku AI 분석
# ══════════════════════════════════════════════════════════════════════════
def call_haiku(system_prompt: str, user_prompt: str, api_key: str) -> str:
    headers = {
        'Content-Type':      'application/json',
        'x-api-key':         api_key,
        'anthropic-version': '2023-06-01',
    }
    payload = {
        'model':      HAIKU_MODEL,
        'max_tokens': MAX_TOKENS,
        'system':     system_prompt,
        'messages':   [{'role': 'user', 'content': user_prompt}],
    }
    try:
        resp = requests.post(ANTHROPIC_API_URL, headers=headers,
                             json=payload, timeout=HAIKU_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        for block in data.get('content', []):
            if block.get('type') == 'text':
                return block['text'].strip()
    except requests.exceptions.Timeout:
        log.warning("Haiku API 타임아웃 — 분석문 생략")
    except Exception as e:
        log.warning(f"Haiku API 오류: {e}")
    return ''


def _build_collection_quality_eval(
    plan_id: str,
    plan_data: dict,
    all_articles: list[dict],
    new_articles: list[dict],
) -> dict:
    """
    v5.0 신규: 수집기사 품질 평가 (Haiku 호출 없이 규칙 기반)

    평가 항목:
      - 수집 충분성: 플랜 중요도 대비 기사 수
      - 소스 다양성: 단일 출처 편중 여부
      - 신규 비율: 이번 주 신규 기사 비율
      - 고등급 비율: HIGH 기사 비율
      - 공백 탐지: 최근 30일 내 기사 없는 구간
      - 누락 가능성: KPI 관련 핵심 이벤트 미수집 경고

    Returns:
        {
          'coverage_score': 0~100,
          'quality_grade':  'A'/'B'/'C'/'D',
          'issues':         [문제점 리스트],
          'missing_signals': [누락 가능 이벤트],
          'source_diversity': N,
        }
    """
    issues         = []
    missing_signals = []

    total     = len(all_articles)
    new_count = len(new_articles)
    high_count = sum(1 for a in all_articles if a.get('ctx_grade') == 'HIGH')
    sources    = list({a.get('source', '') for a in all_articles if a.get('source')})

    # 1. 수집 충분성
    if total == 0:
        issues.append('⚠ 수집 기사 없음 — 키워드 매핑 재검토 필요')
        missing_signals.append('전체 기사 누락 — 섹터 키워드 또는 NewsData 쿼리 점검')
    elif total < 3:
        issues.append(f'⚠ 수집 기사 부족 ({total}건) — 최소 5건 권장')
    elif total < 8:
        issues.append(f'△ 기사 수 보통 ({total}건) — 전문미디어 보완 권장')

    # 2. 신규 기사 비율
    new_ratio = new_count / max(total, 1)
    if new_ratio == 0:
        issues.append('⚠ 이번 주 신규 기사 없음 — 파이프라인 또는 키워드 점검')
    elif new_ratio < 0.1:
        issues.append(f'△ 신규 기사 비율 낮음 ({new_count}/{total}건)')

    # 3. 소스 다양성
    src_count = len(sources)
    if src_count == 1:
        issues.append(f'⚠ 단일 출처 편중 ({sources[0]}) — 다변화 필요')
    elif src_count < 3:
        issues.append(f'△ 출처 다양성 부족 ({src_count}개)')

    # 4. 고등급 비율
    high_ratio = high_count / max(total, 1)
    if total > 3 and high_ratio == 0:
        issues.append('△ HIGH 등급 기사 없음 — 핵심 정책/사업 기사 미수집 가능')

    # 5. 날짜 공백 탐지 (최근 30일)
    from datetime import datetime as _dt, timedelta as _td
    today = _dt.now().date()
    recent_dates = set()
    for a in all_articles:
        try:
            d = _dt.strptime(a['date'][:10], '%Y-%m-%d').date()
            if (today - d).days <= 30:
                recent_dates.add(d)
        except Exception:
            pass
    if total > 0 and len(recent_dates) < 2:
        issues.append('△ 최근 30일 기사 날짜 분산 부족 — 수집 주기 점검')

    # 6. KPI 기반 누락 가능 이벤트 탐지
    kpi_targets = plan_data.get('kpi_targets', [])
    key_projects = plan_data.get('key_projects', [])
    all_text = ' '.join([
        a.get('title_ko', '') + ' ' + a.get('title_en', '') + ' ' + a.get('summary_ko', '')
        for a in all_articles
    ]).lower()

    for kpi in kpi_targets:
        indicator = kpi.get('indicator', '')
        target    = kpi.get('target_2030', '')
        # 수치가 있는 KPI인데 관련 기사가 없으면 경고
        if target and '%' in target or 'MW' in target or '$' in target or 'km' in target:
            kw = indicator.lower().replace(' ', '')[:6]
            if kw and kw not in all_text:
                missing_signals.append(f"KPI '{indicator}' 관련 기사 미수집 가능")

    for proj in key_projects[:3]:
        proj_name = proj.get('name', '')
        if proj_name and proj_name.lower()[:8] not in all_text:
            missing_signals.append(f"주요 프로젝트 '{proj_name}' 관련 기사 미수집 가능")

    # 7. 종합 점수 계산
    score = 100
    score -= min(30, (3 - min(total, 3)) * 10)       # 기사 수
    score -= min(20, (3 - min(src_count, 3)) * 7)    # 소스 다양성
    score -= (20 if new_count == 0 else 0)            # 신규 없음
    score -= (10 if high_count == 0 and total > 3 else 0)  # HIGH 없음
    score -= min(20, len(missing_signals) * 5)        # 누락 경고
    score  = max(0, score)

    if score >= 80:   grade = 'A'
    elif score >= 60: grade = 'B'
    elif score >= 40: grade = 'C'
    else:             grade = 'D'

    return {
        'coverage_score':   score,
        'quality_grade':    grade,
        'issues':           issues,
        'missing_signals':  missing_signals[:5],   # 최대 5개
        'source_diversity': src_count,
        'high_ratio_pct':   round(high_ratio * 100, 1),
        'new_ratio_pct':    round(new_ratio * 100, 1),
    }


def generate_plan_analysis(
    plan_id:      str,
    plan_data:    dict,
    new_articles: list[dict],   # 신규 기사 (is_new=True)
    all_articles: list[dict],   # 전체 누적 기사
    kpi_changes:  list[str],
    api_key:      str,
    dry_run:      bool = False,
) -> dict:
    """
    v5.0: 맥락 기반 진행현황 분석 + 수집품질 평가 통합

    분석 구조 (3계층):
      Layer 1 — 수집품질 평가 (규칙 기반, API 불필요)
        · 기사 수/소스 다양성/신규 비율/HIGH 비율/공백 탐지
        · KPI 기반 누락 가능 이벤트 탐지

      Layer 2 — 맥락 기반 진행현황 분석 (Haiku)
        · 히스토리 기사(전체) + 신규 기사 통합 분석
        · KPI 목표 대비 현재 진행단계 평가
        · 마스터플랜 사업 개요와 연계한 맥락 해석

      Layer 3 — Expert Insight + 품질 평가 요약
        · 사업개발자/투자자 시사점
        · 수집품질 등급 + 보완 권고사항
    """

    # ── 수집품질 평가 (API 불필요, 항상 실행) ──────────────────────────
    quality_eval = _build_collection_quality_eval(
        plan_id, plan_data, all_articles, new_articles
    )

    # ── 기본 반환 구조 ──────────────────────────────────────────────────
    base_result = {
        'news_analysis':    '',
        'insight':          '',
        'kpi_status':       '',
        'articles_used':    len(new_articles),
        'analysis_is_new':  False,
        'quality_eval':     quality_eval,   # ★ v5.0 신규
    }

    if not new_articles and not all_articles:
        base_result['news_analysis'] = f"이번 주 {plan_id} 관련 기사가 없습니다."
        return base_result

    if dry_run or not api_key:
        prev = getattr(generate_plan_analysis, '_prev_analyses', {}).get(plan_id, {})
        base_result.update({
            'news_analysis': prev.get('news_analysis', '') or (
                f"신규 기사 {len(new_articles)}건 수집. AI 분석은 API 재활성화 후 업데이트됩니다."
                if new_articles else "이번 주 신규 기사 없음 — 기존 분석 유지."
            ),
            'insight':    prev.get('insight', ''),
        })
        return base_result

    # 신규 기사 없으면 이전 분석 재사용
    if not new_articles:
        prev = getattr(generate_plan_analysis, '_prev_analyses', {}).get(plan_id, {})
        if prev.get('news_analysis'):
            log.info(f"    {plan_id}: 신규 기사 없음 → 이전 분석 재사용")
            base_result.update({
                'news_analysis': prev.get('news_analysis', ''),
                'insight':       prev.get('insight', ''),
            })
            return base_result

    # ── 시스템 프롬프트 (v5.0 — 맥락+품질 통합) ────────────────────────
    description  = plan_data.get('description_ko', plan_data.get('description', ''))
    kpi_list     = plan_data.get('kpi_targets', [])
    kpi_text     = '\n'.join(
        f"  - {k.get('indicator','')}: 목표 {k.get('target_2030','?')} / 현황 {k.get('current','?')}"
        for k in kpi_list
    ) or '  (KPI 정보 없음)'

    # 히스토리 기사 요약 (최대 5건, 가장 최근)
    hist_arts = [a for a in all_articles if not a.get('is_new')][:5]
    hist_text = ''
    for a in hist_arts:
        t = a.get('title_ko') or a.get('title_en', '')
        hist_text += f"  [{a['date']}] {t[:60]}\n"

    # 수집품질 이슈 요약
    quality_issues_text = '\n'.join(f"  {iss}" for iss in quality_eval['issues']) or '  없음'
    missing_text = '\n'.join(f"  {m}" for m in quality_eval['missing_signals']) or '  없음'

    system_prompt = f"""당신은 베트남 인프라 시장 전문 분석가입니다.
아래 마스터플랜의 사업 개요, KPI, 히스토리 기사를 종합하여
현재 진행현황을 맥락 기반으로 분석하고 수집품질을 평가합니다.

【마스터플랜: {plan_id}】
제목: {plan_data.get('title_ko', plan_id)}
근거: {plan_data.get('decision', '')}

사업 개요:
{description}

KPI 목표:
{kpi_text}

히스토리 기사 (최근 누적):
{hist_text or '  (없음)'}

수집품질 사전 평가:
  · 품질등급: {quality_eval['quality_grade']} (점수: {quality_eval['coverage_score']}/100)
  · 감지된 이슈: {quality_issues_text}
  · 누락 가능 이벤트: {missing_text}

분석 원칙:
1. 히스토리 + 신규 기사를 함께 보며 사업의 전체 맥락(진행단계, 추세, 변화) 파악
2. KPI 목표 대비 현재 진행 수준을 정량적으로 평가 (수치 명시)
3. 수집기사의 품질과 누락 가능성을 언급하고 보완 방향 제시
4. 투자자/사업개발자 관점의 실무적 인사이트 제공
5. 한국어, 전문적이고 간결하게"""

    # 신규 기사 최대 8건 (HIGH 우선)
    sorted_new = sorted(new_articles,
                        key=lambda x: (0 if x['ctx_grade'] == 'HIGH' else 1, x['date']),
                        reverse=False)[:8]

    arts_text = ''
    for i, a in enumerate(sorted_new, 1):
        title = a.get('title_ko') or a.get('title_en', '')
        summ  = a.get('summary_ko') or a.get('summary_en', '')
        arts_text += f"\n[{i}] {a['date']} | {a['source']} | {a['ctx_grade']}\n"
        arts_text += f"    제목: {title[:80]}\n"
        if summ:
            arts_text += f"    요약: {summ[:150]}\n"

    change_note = ''
    if kpi_changes:
        change_note = '\n\n【이번 주 변동 사항】\n' + '\n'.join(f'  ★ {c}' for c in kpi_changes)

    user_prompt = f"""아래 이번 주 신규 기사 {len(sorted_new)}건을 히스토리 맥락과 함께 분석하여
진행현황 분석문과 수집품질 평가를 작성하세요.{change_note}

【이번 주 신규 기사 목록】
{arts_text}

【요청】
다음 세 항목을 구분하여 답변하세요:

1. [최신 뉴스 분석] (180~280자)
   - 히스토리 기사와 신규 기사를 종합한 사업 진행단계 맥락 평가
   - KPI 목표 대비 현재 달성 수준 (수치 명시)
   - 이번 주 핵심 동향 및 변화 포인트 (★ 강조)

2. [Expert Insight] (60~100자)
   - 사업개발자/투자자를 위한 핵심 시사점 1~2문장

3. [수집품질 평가] (60~100자)
   - 이번 주 수집기사의 충분성/다양성 평가
   - 누락 가능한 이벤트나 보완 필요 소스 제안 (있으면)
"""

    raw = call_haiku(system_prompt, user_prompt, api_key)

    news_analysis    = ''
    insight          = ''
    quality_comment  = ''

    if '[최신 뉴스 분석]' in raw:
        news_analysis = raw.split('[최신 뉴스 분석]')[1].split('[Expert Insight]')[0].strip()
    if '[Expert Insight]' in raw:
        insight = raw.split('[Expert Insight]')[1].split('[수집품질 평가]')[0].strip()
    if '[수집품질 평가]' in raw:
        quality_comment = raw.split('[수집품질 평가]')[1].strip()
    if not news_analysis and raw:
        news_analysis = raw[:400]

    # quality_eval에 AI 코멘트 추가
    quality_eval['ai_comment'] = quality_comment

    base_result.update({
        'news_analysis':   news_analysis,
        'insight':         insight,
        'kpi_status':      '',
        'articles_used':   len(sorted_new),
        'analysis_is_new': True,
        'quality_eval':    quality_eval,
    })
    return base_result


def generate_executive_summary(
    new_articles: list[dict],
    kpi_changes:  dict,
    api_key:      str,
    dry_run:      bool = False,
    prev_exec:    str = '',
) -> str:
    """전체 기사를 종합한 Executive Summary."""
    if dry_run or not api_key:
        return prev_exec if prev_exec else '이번 주 AI Executive Summary (API 비활성 — 이전 내용 유지).'

    if not new_articles:
        return prev_exec if prev_exec else '이번 주 신규 기사가 없습니다. 기존 분석을 유지합니다.'

    high_arts = [a for a in new_articles if a.get('ctx_grade') == 'HIGH'][:5]
    if not high_arts:
        high_arts = new_articles[:5]

    arts_text = '\n'.join(
        f"- [{a['date']}] {a.get('title_ko', a.get('title_en',''))[:80]} ({a['sector']})"
        for a in high_arts
    )
    change_summary = ', '.join(
        f"{pid}({', '.join(v)})" for pid, v in kpi_changes.items()
    ) if kpi_changes else '없음'

    system_prompt = """당신은 베트남 인프라 시장 수석 애널리스트입니다.
이번 주 수집된 기사들을 종합하여 시장 전체를 아우르는 Executive Summary를 작성합니다.
환경/에너지/교통/도시개발 4개 영역을 균형 있게 다루며,
사업개발자와 투자자에게 실질적인 시사점을 제공하는 전문적 분석문을 작성하세요.
분량: 300~450자, 한국어"""

    user_prompt = f"""이번 주 주요 신규 기사:
{arts_text}

KPI 변동 플랜: {change_summary}

위 정보를 바탕으로 Executive Summary를 작성하세요.
변동사항이 있는 플랜은 ★ 표시하여 강조하세요."""

    return call_haiku(system_prompt, user_prompt, api_key)


# ══════════════════════════════════════════════════════════════════════════
#  [STEP 5] 페이로드 조립 → JS 빌더 호출
# ══════════════════════════════════════════════════════════════════════════
def assemble_report_payload(
    plans:        dict,
    grouped_arts: dict,        # 전체 기사 (is_new 태그 포함)
    all_articles: list[dict],
    new_articles: list[dict],
    analyses:     dict,
    exec_summary: str,
    kpi_changes:  dict,
    sa7_context:  dict = None,
    sa7_timeline: dict = None,
) -> dict:
    """
    v4.0: 플랜별 articles에 전체 기사 포함, is_new 태그로 노란 마킹 구분
    """
    today      = datetime.now().strftime('%Y-%m-%d')
    week_label = datetime.now().strftime('%Y-W%V')

    plan_sections = []
    for plan_id, plan_data in plans.items():
        arts     = grouped_arts.get(plan_id, [])
        analysis = analyses.get(plan_id, {})
        changes  = kpi_changes.get(plan_id, [])

        tl_data    = (sa7_timeline or {}).get(plan_id, {})
        cur_stage  = tl_data.get('current_stage', 'UNKNOWN')
        stage_hist = tl_data.get('stage_history', [])
        next_watch = tl_data.get('next_watch', '')

        # 기사 정렬: 신규 우선, 동일 날짜면 HIGH 우선
        arts_sorted = sorted(arts,
                             key=lambda x: (0 if x.get('is_new') else 1,
                                            0 if x.get('ctx_grade') == 'HIGH' else 1,
                                            x['date']),
                             reverse=False)

        plan_sections.append({
            # Layer 1: 고정 데이터
            'plan_id':        plan_id,
            'title_ko':       plan_data.get('title_ko', plan_id),
            'decision':       plan_data.get('decision', ''),
            'sector':         ', '.join(plan_data.get('sectors', [])),
            'area':           plan_data.get('area', ''),
            'description_ko': plan_data.get('description_ko', plan_data.get('description', '')),
            'kpi_targets':    plan_data.get('kpi_targets', []),
            'key_projects':   plan_data.get('key_projects', []),

            # Layer 2: AI 동적 데이터
            'articles':        arts_sorted[:20],  # 최대 20건 (신규+기존 혼합)
            'new_count':       sum(1 for a in arts_sorted if a.get('is_new')),
            'old_count':       sum(1 for a in arts_sorted if not a.get('is_new')),
            'news_analysis':   analysis.get('news_analysis', ''),
            'insight':         analysis.get('insight', ''),
            'articles_used':   analysis.get('articles_used', 0),
            'analysis_is_new': analysis.get('analysis_is_new', False),
            # ★ v5.0: 수집품질 평가
            'quality_eval':    analysis.get('quality_eval', {
                'coverage_score': 0, 'quality_grade': 'D',
                'issues': [], 'missing_signals': [],
                'source_diversity': 0, 'high_ratio_pct': 0.0,
                'new_ratio_pct': 0.0, 'ai_comment': '',
            }),

            # KPI 변동
            'kpi_changes':    changes,
            'has_kpi_change': len(changes) > 0,

            # SA-7 진행단계
            'current_stage':  cur_stage,
            'stage_history':  stage_hist[:5],
            'next_watch':     next_watch,
        })

    any_new = any(s.get('analysis_is_new', False) for s in plan_sections)
    new_art_count = len(new_articles)

    return {
        'report_date':         today,
        'report_week':         week_label,
        'total_articles':      len(all_articles),
        'new_articles_count':  new_art_count,   # ★ v4.0 신규 기사 수
        'plan_count':          len(plan_sections),
        'executive_summary':   exec_summary,
        'kpi_changes_count':   sum(len(v) for v in kpi_changes.values()),
        'plan_sections':       plan_sections,
        'exec_summary_is_new': any_new,
    }


def run_js_builder(payload: dict, output_path: Path) -> bool:
    """Node.js docx 빌더 호출."""
    AGENT_OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp_json = AGENT_OUT_DIR / 'sa8_report_payload.json'

    with open(tmp_json, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    is_new_exec = payload.get('exec_summary_is_new', False)

    if JS_BUILDER.exists():
        js_src = JS_BUILDER.read_text(encoding='utf-8')
        js_src = js_src.replace(
            'const EXEC_SUMMARY_IS_NEW = false;  // Python이 동적으로 교체',
            f'const EXEC_SUMMARY_IS_NEW = {str(is_new_exec).lower()};  // Python 자동 설정'
        )
        tmp_js = AGENT_OUT_DIR / 'build_mi_report_tmp.js'
        tmp_js.write_text(js_src, encoding='utf-8')
        actual_builder = tmp_js
    else:
        log.error(f"JS 빌더 없음: {JS_BUILDER}")
        return False

    env = os.environ.copy()
    env['SA8_DATA_FILE']   = str(tmp_json)
    env['SA8_OUTPUT_PATH'] = str(output_path)

    log.info(f"Node.js 빌더 호출: {actual_builder.name} (exec_is_new={is_new_exec})")
    result = subprocess.run(
        ['node', str(actual_builder)],
        capture_output=True, text=True, timeout=180, env=env,
        cwd=str(SCRIPTS_DIR)   # ★ v4.1: scripts/ 에서 실행 → node_modules/docx 경로 정상 인식
    )

    if result.returncode != 0:
        log.error(f"빌더 오류:\n{result.stderr[:800]}")
        return False

    if result.stdout:
        log.info(result.stdout.strip())
    return True


# ══════════════════════════════════════════════════════════════════════════
#  [STEP 6] 이메일 발송 (v4.0: 발송 조건 수정 + 본문 강화)
# ══════════════════════════════════════════════════════════════════════════
def send_email(report_path, payload: dict) -> bool:
    """
    v4.0 이메일 발송.

    발송 조건 (OR 조건):
      - 신규 기사(is_new=True) 1건 이상
      - KPI 변동 1건 이상

    본문 내용:
      - 수집 기사 수, 신규 기사 수, 플랜 수
      - AI Executive Summary 전문
      - 플랜별 신규/기존 기사 수 요약
    """
    username = os.getenv('EMAIL_USERNAME')
    password = os.getenv('EMAIL_PASSWORD')
    if not username or not password:
        log.warning("EMAIL_USERNAME/PASSWORD 없음 — 이메일 건너뜀")
        return False

    today      = datetime.now().strftime('%Y년 %m월 %d일')
    week_label = payload.get('report_week', '')
    total_arts = payload.get('total_articles', 0)
    new_count  = payload.get('new_articles_count', 0)
    kpi_count  = payload.get('kpi_changes_count', 0)
    exec_summ  = payload.get('executive_summary', '')

    body_lines = [
        f"베트남 인프라 MI 주간 보고서 ({week_label})",
        f"발행일: {today}",
        f"생성: SA-8 자동 파이프라인 (Claude Haiku 분석 통합)",
        "",
        "=" * 55,
        f"▶ 전체 누적 기사: {total_arts}건",
        f"▶ 이번 주 신규:   {new_count}건  ← 노란색 마킹",
        f"▶ 분석 플랜:      {payload.get('plan_count', 0)}개",
        f"▶ KPI 변동:       {kpi_count}개 플랜",
        "=" * 55,
        "",
        "【Executive Summary — AI 분석 (Claude Haiku)】",
        "─" * 55,
        exec_summ or "(이번 주 신규 기사 없음 — 기존 분석 유지)",
        "",
        "─" * 55,
        "★ 노란색 강조 = 이번 주 신규 기사",
        "★ 회색 = 기존 누적 기사 (내용 유지)",
        "★ KPI 변동 플랜은 ⚠ 아이콘으로 강조",
        "",
    ]

    # 플랜별 수집 현황
    plan_sections = payload.get('plan_sections', [])
    if plan_sections:
        body_lines.append("【플랜별 기사 현황】")
        for sec in plan_sections:
            new_c  = sec.get('new_count', 0)
            old_c  = sec.get('old_count', 0)
            total  = new_c + old_c
            if total == 0:
                continue
            kpi_flag = "⚠ " if sec.get('has_kpi_change') else "  "
            new_flag = f"신규{new_c}건" if new_c > 0 else "신규없음"
            body_lines.append(
                f"  {kpi_flag}{sec.get('plan_id','')}: 총{total}건 ({new_flag} / 기존{old_c}건)"
            )

    body = "\n".join(body_lines)

    msg = MIMEMultipart()
    msg['From']    = username
    msg['To']      = username
    msg['Subject'] = f"[VN Infra MI] 주간 보고서 {today} — 신규 {new_count}건"
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    # 첨부 파일 (존재 시)
    if report_path and Path(str(report_path)).exists():
        with open(report_path, 'rb') as f:
            att = MIMEApplication(f.read(), Name=Path(str(report_path)).name)
        att['Content-Disposition'] = f'attachment; filename="{Path(str(report_path)).name}"'
        msg.attach(att)
        log.info(f"이메일 첨부: {Path(str(report_path)).name}")
    else:
        log.warning("첨부 파일 없음 — 텍스트 요약만 발송")

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as srv:
            srv.login(username, password)
            srv.sendmail(username, [username], msg.as_string())
        log.info(f"✅ 이메일 발송 완료: {username}")
        return True
    except smtplib.SMTPAuthenticationError:
        log.error("이메일 인증 실패 — Gmail App Password 확인 필요")
    except smtplib.SMTPException as e:
        log.error(f"SMTP 오류: {e}")
    except Exception as e:
        log.error(f"이메일 발송 실패: {e}")
    return False


# ══════════════════════════════════════════════════════════════════════════
#  이전 보고서 페이로드 로드 (AI 논평 보존용)
# ══════════════════════════════════════════════════════════════════════════
def load_previous_report_payload():
    payload_path = AGENT_OUT_DIR / 'sa8_report_payload.json'
    if payload_path.exists():
        try:
            with open(payload_path, encoding='utf-8') as f:
                data = json.load(f)
            log.info(f"이전 보고서 페이로드 로드: {payload_path.name}")
            return data
        except Exception as e:
            log.warning(f"이전 페이로드 로드 실패: {e}")

    daily_files = sorted(
        _glob.glob(str(AGENT_OUT_DIR / 'mi_daily_*.json')),
        reverse=True
    )
    if daily_files:
        try:
            with open(daily_files[0], encoding='utf-8') as f:
                data = json.load(f)
            log.info(f"이전 daily 페이로드 로드: {Path(daily_files[0]).name}")
            return data
        except Exception as e:
            log.warning(f"daily 페이로드 로드 실패: {e}")

    log.info("이전 보고서 없음 — 최초 실행으로 처리")
    return None


# ══════════════════════════════════════════════════════════════════════════
#  main()
# ══════════════════════════════════════════════════════════════════════════
def main():
    dry_run    = '--dry-run'    in sys.argv
    send_mail  = '--send-email' in sys.argv
    daily_only = '--daily-only' in sys.argv

    api_key = os.getenv('ANTHROPIC_API_KEY', '')
    if not api_key and not dry_run:
        log.warning("ANTHROPIC_API_KEY 없음 — AI 분석 건너뜀 (dry-run 모드로 전환)")
        dry_run = True

    today_str   = datetime.now().strftime('%Y%m%d')
    output_path = DOCS_DIR / f'VN_Infra_MI_Weekly_Report_{today_str}.docx'
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    log.info("=" * 65)
    log.info(f"SA-8 MI Report Generator v4.0 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log.info(f"모드: {'DRY-RUN' if dry_run else 'LIVE'} | AI 모델: {HAIKU_MODEL}")
    log.info(f"기사 수집: 전체 {DAYS_TOTAL}일 / 신규 기준 {DAYS_NEW}일 (노란 마킹)")
    log.info("=" * 65)

    # ── Step 0: 이전 보고서 로드 ────────────────────────────────────────
    prev_payload = load_previous_report_payload()
    prev_exec_summary = prev_payload.get('executive_summary', '') if prev_payload else ''

    generate_plan_analysis._prev_analyses = {}
    if prev_payload:
        for sec in prev_payload.get('plan_sections', []):
            pid = sec.get('plan_id', '')
            if pid:
                generate_plan_analysis._prev_analyses[pid] = {
                    'news_analysis': sec.get('news_analysis', ''),
                    'insight':       sec.get('insight', ''),
                }

    # ── Step 1: Layer 1 고정 데이터 로드 ────────────────────────────────
    plans = load_knowledge_index()
    if not plans:
        log.error("마스터플랜 데이터 없음 — 종료")
        sys.exit(1)

    # ── Step 2: 기사 추출 (전체 90일 + 신규 태그) ───────────────────────
    all_articles, new_articles = extract_articles(DAYS_TOTAL)
    grouped_arts = group_articles_by_plan(all_articles, plans)

    # ── Step 3: SA-7 데이터 로드 ──────────────────────────────────────
    log.info("SA-7 context 로드 중...")
    sa7_context  = load_sa7_context()
    sa7_timeline = load_sa7_timeline()

    # ── Step 3b: KPI 변동 감지 ─────────────────────────────────────────
    kpi_changes = detect_kpi_changes(plans)

    # ── Step 4: Haiku AI 분석 (플랜별, 신규 기사 기반) ─────────────────
    analyses   = {}
    total_plans = len(plans)
    for i, (plan_id, plan_data) in enumerate(plans.items(), 1):
        all_arts = grouped_arts.get(plan_id, [])
        new_arts = [a for a in all_arts if a.get('is_new')]

        if dry_run:
            log.info(f"  [{i}/{total_plans}] {plan_id}: 신규{len(new_arts)}건 / 전체{len(all_arts)}건 → 이전 분석 재사용")
        else:
            log.info(f"  [{i}/{total_plans}] {plan_id}: 신규{len(new_arts)}건 / 전체{len(all_arts)}건 → Haiku 분석")

        analyses[plan_id] = generate_plan_analysis(
            plan_id      = plan_id,
            plan_data    = plan_data,
            new_articles = new_arts,
            all_articles = all_arts,
            kpi_changes  = kpi_changes.get(plan_id, []),
            api_key      = api_key,
            dry_run      = dry_run,
        )
        if not dry_run and api_key:
            time.sleep(0.5)

    # ── Step 4b: Executive Summary ────────────────────────────────────
    log.info("Executive Summary 생성 중...")
    exec_summary = generate_executive_summary(
        new_articles, kpi_changes, api_key, dry_run, prev_exec_summary
    )

    # ── Step 5: 페이로드 조립 → JS 빌더 ──────────────────────────────
    payload = assemble_report_payload(
        plans, grouped_arts, all_articles, new_articles,
        analyses, exec_summary, kpi_changes,
        sa7_context=sa7_context,
        sa7_timeline=sa7_timeline,
    )

    if daily_only:
        AGENT_OUT_DIR.mkdir(parents=True, exist_ok=True)
        daily_json = AGENT_OUT_DIR / f'mi_daily_{datetime.now().strftime("%Y%m%d")}.json'
        with open(daily_json, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        log.info(f"✅ SA-8 daily-only 완료: {daily_json}")
        return

    success = run_js_builder(payload, output_path)

    if not success:
        log.warning("신규 docx 생성 실패 — 이전 보고서 확인 중...")
        candidates = sorted(
            _glob.glob(str(DOCS_DIR / 'reports' / '*.docx')), reverse=True
        ) + sorted(
            _glob.glob(str(DOCS_DIR / 'VN_Infra_MI_Weekly_Report_*.docx')), reverse=True
        )
        if candidates:
            log.info(f"이전 보고서 유지: {Path(candidates[0]).name}")

    # ── Step 6: 이메일 발송 ──────────────────────────────────────────
    # v4.0: 신규 기사 ≥ 1건 OR KPI 변동 ≥ 1건이면 발송
    should_send = send_mail and (len(new_articles) > 0 or len(kpi_changes) > 0)

    if should_send:
        email_target = None
        if output_path.exists():
            email_target = output_path
        else:
            # 탐색: docs/reports/*.pptx → docs/reports/*.docx → docs/*.docx
            candidates = (
                sorted(_glob.glob(str(DOCS_DIR / 'reports' / '*.pptx')), reverse=True)
                + sorted(_glob.glob(str(DOCS_DIR / 'reports' / '*.docx')), reverse=True)
                + sorted(_glob.glob(str(DOCS_DIR / 'VN_Infra_MI_Weekly_Report_*.docx')), reverse=True)
            )
            if candidates:
                email_target = Path(candidates[0])
                log.info(f"신규 docx 없음 — 최신 보고서 첨부: {email_target.name}")

        send_email(email_target, payload)

    elif send_mail:
        log.info("발송 조건 미충족 (신규 기사 없음 + KPI 변동 없음) — 이메일 건너뜀")

    # ── 결과 요약 ───────────────────────────────────────────────────
    log.info("")
    log.info("━" * 65)
    log.info(f"✅ SA-8 v4.0 완료")
    log.info(f"   출력: {output_path}")
    log.info(f"   기사: 전체 {len(all_articles)}건 | 신규 {len(new_articles)}건")
    log.info(f"   플랜: {len(plans)}개")
    log.info(f"   AI 분석: {'LIVE (Claude Haiku)' if not dry_run and api_key else '이전 논평 재사용'}")
    log.info(f"   KPI 변동: {len(kpi_changes)}개 플랜")
    log.info(f"   이메일: {'발송' if should_send else '미발송 (조건 미충족)' if send_mail else '옵션 없음'}")
    log.info("━" * 65)


if __name__ == '__main__':
    main()
