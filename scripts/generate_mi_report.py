"""
generate_mi_report.py  ── SA-8 Sub Agent v2.0
=====================================================
역할: 주간 MI 보고서 자동 생성 (Claude Haiku AI 분석 통합)

아키텍처 (2-레이어 설계):
  ┌─────────────────────────────────────────────────────────┐
  │  Layer 1 — 고정 데이터 (knowledge_index.json에서 로드)  │
  │    · 사업 개요 (텍스트)                                 │
  │    · KPI 목표값 테이블                                  │
  │    · 주요 프로젝트 목록                                 │
  │    → 매주 동일하게 유지, 변경 없음                       │
  ├─────────────────────────────────────────────────────────┤
  │  Layer 2 — AI 동적 분석 (Claude Haiku로 매주 생성)      │
  │    · 최신 기사 → Haiku → 사업개요 연계 분석문           │
  │    · KPI 변동 감지 → 노란색 하이라이트 자동 표시         │
  │    · 플랜별 인사이트 + Executive Summary AI 논평         │
  └─────────────────────────────────────────────────────────┘

실행:
  python3 scripts/generate_mi_report.py
  python3 scripts/generate_mi_report.py --send-email
  python3 scripts/generate_mi_report.py --dry-run   # AI 호출 없이 구조만 생성

GitHub Actions: collect_weekly.yml SA-8 단계에서 호출

영구 제약:
  - Anthropic API: GitHub Actions에서 claude-haiku-4-5로만 사용 (연결 오류 방지용 claude-haiku-4-5)
  - Translation: Google Translate만 사용 (ANTHROPIC_API_KEY는 분석에만)
  - 이메일 Secrets: EMAIL_USERNAME / EMAIL_PASSWORD

버전: v3.0 (2026-04-24) — SA-7 context_analyzer 연동 추가
"""

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
# knowledge_index 탐색 경로 (docs/shared 우선 — Genspark 공유 실제 경로)
KI_PATH       = BASE_DIR / 'docs' / 'shared' / 'knowledge_index.json'
KI_PATH_ALT   = SHARED_DIR / 'knowledge_index.json'
KI_PATH_L1    = SHARED_DIR / 'layer1_data.json'
KPI_SNAP_PATH = AGENT_OUT_DIR / 'kpi_snapshot_weekly.json'
JS_BUILDER    = SCRIPTS_DIR / 'build_mi_report_sa8.js'

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

# SA-7 출력 파일 경로
CONTEXT_OUT  = BASE_DIR / 'data' / 'agent_output' / 'context_output.json'
TIMELINE_OUT = BASE_DIR / 'data' / 'agent_output' / 'stage_timeline.json'  # 영구 고정 — 연결 안정성
MAX_TOKENS        = 1500   # 플랜당 분석문 최대 토큰
HAIKU_TIMEOUT     = 45     # 초



# ══════════════════════════════════════════════════════════════════════════
#  SA-7 연동 — context_output.json 로드
# ══════════════════════════════════════════════════════════════════════════
def load_sa7_context() -> dict:
    """
    SA-7 context_analyzer.py가 생성한 context_output.json 로드.

    각 기사에 진행단계(stage), 마일스톤(milestone), 다음 관찰 포인트(next_watch),
    Expert Insight가 포함되어 있습니다.

    SA-7 출력이 없으면 빈 dict 반환 (SA-8은 계속 정상 실행).

    Returns:
        {url: {stage, milestone, next_watch, insight, confidence, haiku_used}}
    """
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
    """
    SA-7 stage_timeline.json 로드.
    플랜별 현재 진행단계 + 히스토리 반환.
    """
    if not TIMELINE_OUT.exists():
        return {}

    with open(TIMELINE_OUT, 'r', encoding='utf-8') as f:
        tl = json.load(f)
    return tl.get('plans', {})


# ══════════════════════════════════════════════════════════════════════════
#  [STEP 1] Layer 1 데이터: knowledge_index.json 로드
#           → 사업 개요 / KPI 목표값 / 프로젝트 목록 (고정)
# ══════════════════════════════════════════════════════════════════════════
def load_knowledge_index() -> dict:
    """
    knowledge_index.json v2.1에서 마스터플랜 고정 데이터 로드.
    
    구조 (v2.1):
      masterplans: {
        "VN-WW-2030": {
          "title_ko": "...",
          "decision": "...",
          "description_ko": "...",   ← 사업 개요 (Layer 1 고정)
          "kpi_targets": [...],      ← KPI 목표값 (Layer 1 고정)
          "key_projects": [...],     ← 주요 프로젝트 목록 (Layer 1 고정)
          "sectors": [...],
          "keywords_en": [...],
          "keywords_vi": [...],
          "match_threshold": 45,
        },
        ...
      }
    
    knowledge_index가 없으면 최소한의 기본 구조 반환.
    """
    # 순서대로 탐색: docs/shared → data/shared → layer1_data
    ki_file = None
    for candidate in [KI_PATH, KI_PATH_ALT, KI_PATH_L1]:
        if candidate.exists():
            ki_file = candidate
            break

    if not ki_file:
        log.warning(f"knowledge_index.json 없음 — 기본 플랜 구조 사용")
        return _default_knowledge_index()

    log.info(f"knowledge_index 로드: {ki_file}")
    with open(ki_file, 'r', encoding='utf-8') as f:
        ki = json.load(f)

    plans = ki.get('masterplans', {})
    log.info(f"knowledge_index 로드: {len(plans)}개 마스터플랜")
    return plans


def _default_knowledge_index() -> dict:
    """knowledge_index.json 없을 때 사용하는 최소 기본 구조."""
    return {
        "VN-WW-2030": {
            "title_ko": "폐수처리 인프라 국가 마스터플랜 2021~2030",
            "decision": "Decision 1354/QD-TTg",
            "description_ko": "국가 폐수처리 마스터플랜(2021~2030)은 도시 폐수처리율을 2025년 50%, 2030년 85%로 끌어올리는 것을 목표로 한다.",
            "kpi_targets": [
                {"indicator": "도시 폐수처리율", "target_2030": "85%", "current": "~29% (하노이)"},
                {"indicator": "신규 WWTP 용량", "target_2030": "2,900,000 m³/일", "current": "약 800,000 m³/일"},
                {"indicator": "ODA 연계 투자", "target_2030": "$2.5B+", "current": "JICA $690M"},
            ],
            "key_projects": [
                {"name": "옌짜 (Yen Xa)", "location": "하노이", "capacity": "270,000 m³/일", "note": "2025.8 준공"},
                {"name": "투득시 (Thu Duc)", "location": "호치민", "capacity": "1,100,000 m³/일", "note": "동남아 최대"},
            ],
            "sectors": ["Waste Water"],
            "area": "Environment",
        },
    }


# ══════════════════════════════════════════════════════════════════════════
#  [STEP 2] Excel DB에서 최신 기사 추출 (Layer 2 입력)
# ══════════════════════════════════════════════════════════════════════════
def _sector_to_area(sector: str) -> str:
    """src_type(섹터)에서 area를 계산 — build_dashboard와 동일 로직."""
    ENV = {'Waste Water', 'Water Supply/Drainage', 'Solid Waste', 'Environment'}
    ENG = {'Power', 'Oil & Gas'}
    if sector in ENV: return 'Environment'
    if sector in ENG: return 'Energy Develop.'
    if sector: return 'Urban Develop.'
    return 'Environment'


def extract_weekly_articles(days_back: int = 7) -> list[dict]:
    """
    Excel DB → 최근 N일 기사 추출.
    ctx_plans 컬럼으로 플랜별 그룹핑 가능하도록 반환.
    """
    if not EXCEL_PATH.exists():
        log.warning(f"Excel DB 없음: {EXCEL_PATH}")
        return []

    wb  = openpyxl.load_workbook(EXCEL_PATH, read_only=True, data_only=True)
    
    if 'News Database' not in wb.sheetnames:
        log.warning("'News Database' 시트 없음")
        wb.close()
        return []

    ws      = wb['News Database']
    headers = [str(c.value or '').strip().lower().replace(' ', '_')
               for c in next(ws.iter_rows(min_row=1, max_row=1))]

    # 컬럼 인덱스 동적 맵핑
    def col_idx(keys: list[str]) -> int | None:
        for k in keys:
            for i, h in enumerate(headers):
                if k in h:
                    return i
        return None

    ci = {
        'date':       col_idx(['date']),
        'sector':     col_idx(['business_sector', 'sector', 'src_type']),   # src_type 별칭 추가
        'area':       col_idx(['area']),                                      # area 없으면 None
        'province':   col_idx(['province']),
        'title_ko':   col_idx(['title_ko', 'tit_ko']),                       # tit_ko 별칭 추가
        'title_en':   col_idx(['title_en', 'title_(en/vi)', 'title', 'news_title']),
        'summary_ko': col_idx(['summary_ko', 'sum_ko']),                     # sum_ko 별칭
        'summary_en': col_idx(['summary_en', 'short_summary', 'sum_en']),    # sum_en 별칭
        'source':     col_idx(['source']),
        'url':        col_idx(['link', 'url']),
        'ctx_grade':  col_idx(['ctx_grade', 'grade']),                       # grade 별칭
        'ctx_plans':  col_idx(['ctx_plans', 'plan_id']),                     # plan_id 별칭
    }

    cutoff   = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    articles = []

    for row in ws.iter_rows(min_row=2, values_only=True):
        # date 필드 — date/published_date 모두 지원
        date_val = str(row[ci['date']] if ci['date'] is not None else '').strip()[:10]
        if not date_val or date_val < cutoff:
            continue

        title_ko = str(row[ci['title_ko']] if ci['title_ko'] is not None else '').strip()
        if not title_ko:
            continue

        articles.append({
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
        })

    wb.close()
    articles.sort(key=lambda x: x['date'], reverse=True)
    log.info(f"Excel DB 추출: {len(articles)}건 (최근 {days_back}일)")
    return articles


def group_articles_by_plan(articles: list[dict], plans: dict) -> dict:
    """
    기사를 ctx_plans 기준으로 플랜별 그룹핑.
    ctx_plans가 비어 있으면 sector 기반으로 fallback 매핑.
    """
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

    grouped: dict[str, list] = {plan_id: [] for plan_id in plans}

    for art in articles:
        # 1순위: ctx_plans 컬럼 (SA-6/SA-7이 매핑한 값)
        plan_ids = [p.strip() for p in art['ctx_plans'].split(',')
                    if p.strip() and p.strip() in plans]

        # 2순위: sector → 플랜 fallback
        if not plan_ids:
            plan_ids = [p for p in SECTOR_TO_PLAN.get(art['sector'], [])
                        if p in plans]

        for pid in plan_ids:
            grouped.setdefault(pid, []).append(art)

    return grouped


# ══════════════════════════════════════════════════════════════════════════
#  [STEP 3] KPI 변동 감지
# ══════════════════════════════════════════════════════════════════════════
def detect_kpi_changes(plans: dict) -> dict[str, list[str]]:
    """
    직전 주 KPI 스냅샷과 비교하여 변동 항목 목록 반환.
    변동 있으면 → 보고서에서 노란색 하이라이트 처리.

    Returns:
        { plan_id: ["변동 설명 문자열", ...] }
    """
    # 현재 스냅샷 생성 (threshold + 키워드 수)
    current_snap = {}
    for pid, plan in plans.items():
        current_snap[pid] = {
            'threshold':    plan.get('match_threshold', plan.get('threshold', 50)),
            'kw_en_count':  len(plan.get('keywords_en', [])),
            'kw_vi_count':  len(plan.get('keywords_vi', [])),
            'kpi_count':    len(plan.get('kpi_targets', [])),
        }

    AGENT_OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not KPI_SNAP_PATH.exists():
        log.info("KPI 스냅샷 없음 (초회 실행) — 이번 주 저장")
        with open(KPI_SNAP_PATH, 'w', encoding='utf-8') as f:
            json.dump(current_snap, f, ensure_ascii=False, indent=2)
        return {}

    with open(KPI_SNAP_PATH, 'r', encoding='utf-8') as f:
        prev_snap = json.load(f)

    changes: dict[str, list[str]] = {}
    for pid, curr in current_snap.items():
        prev = prev_snap.get(pid, {})
        plan_changes = []

        if curr['threshold'] != prev.get('threshold', curr['threshold']):
            plan_changes.append(
                f"매칭 임계값 변동: {prev.get('threshold','?')} → {curr['threshold']}"
            )
        diff_en = curr['kw_en_count'] - prev.get('kw_en_count', curr['kw_en_count'])
        diff_vi = curr['kw_vi_count'] - prev.get('kw_vi_count', curr['kw_vi_count'])
        if diff_en != 0:
            sign = '+' if diff_en > 0 else ''
            plan_changes.append(f"영문 키워드 {sign}{diff_en}개 변동")
        if diff_vi != 0:
            sign = '+' if diff_vi > 0 else ''
            plan_changes.append(f"베트남어 키워드 {sign}{diff_vi}개 변동")

        if plan_changes:
            changes[pid] = plan_changes

    # 스냅샷 갱신
    with open(KPI_SNAP_PATH, 'w', encoding='utf-8') as f:
        json.dump(current_snap, f, ensure_ascii=False, indent=2)

    log.info(f"KPI 변동 감지: {len(changes)}개 플랜에서 변동")
    return changes


# ══════════════════════════════════════════════════════════════════════════
#  [STEP 4] Layer 2: Claude Haiku로 플랜별 분석문 생성
#           입력: 사업 개요(Layer 1) + 최신 기사 목록
#           출력: 사업개요와 연계된 분석 인사이트 텍스트
# ══════════════════════════════════════════════════════════════════════════
def call_haiku(system_prompt: str, user_prompt: str, api_key: str) -> str:
    """
    Claude Haiku API 단일 호출.
    연결 실패 시 빈 문자열 반환 (보고서 생성은 계속 진행).
    """
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
        # content 블록에서 text 추출
        for block in data.get('content', []):
            if block.get('type') == 'text':
                return block['text'].strip()
    except requests.exceptions.Timeout:
        log.warning("Haiku API 타임아웃 — 분석문 생략")
    except Exception as e:
        log.warning(f"Haiku API 오류: {e}")
    return ''


def generate_plan_analysis(
    plan_id:     str,
    plan_data:   dict,
    articles:    list[dict],
    kpi_changes: list[str],
    api_key:     str,
    dry_run:     bool = False,
) -> dict:
    """
    플랜 1개에 대한 Haiku 분석 실행.

    Returns:
        {
          'news_analysis':  str,   # 최신 기사 → 사업개요 연계 분석 (한국어)
          'insight':        str,   # Expert Insight (2~3문장)
          'kpi_status':     str,   # KPI 현황 요약 (1문장)
          'articles_used':  int,   # 분석에 사용된 기사 수
        }
    """
    if not articles:
        return {
            'news_analysis':  f"이번 주 {plan_id} 관련 신규 기사가 수집되지 않았습니다.",
            'insight':        '',
            'kpi_status':     '',
            'articles_used':  0,
        }

    if dry_run or not api_key:
        # ── v3.1: API 없으면 이전 논평 재사용 (DRY-RUN 텍스트 금지) ──
        # prev_analysis는 caller(main)에서 주입 — 없으면 '' 유지
        prev = getattr(generate_plan_analysis, '_prev_analyses', {}).get(plan_id, {})
        prev_news = prev.get('news_analysis', '')
        prev_ins  = prev.get('insight', '')
        return {
            # 이전 논평이 있으면 재사용, 없으면 중립적 안내문
            'news_analysis':  prev_news if prev_news else f"이번 주 수집 기사 {len(articles)}건. AI 분석은 API 재활성화 후 업데이트됩니다.",
            'insight':        prev_ins  if prev_ins  else '',
            'kpi_status':     '',
            'articles_used':  len(articles),
            # ★ v3.2: 새 AI 논평 여부 플래그 (False = 이전 논평 재사용)
            'analysis_is_new': False,
        }

    # ── 시스템 프롬프트 (Layer 1 고정 데이터 포함) ─────────────────────
    description = plan_data.get('description_ko', plan_data.get('description', ''))
    kpi_list    = plan_data.get('kpi_targets', [])
    kpi_text    = '\n'.join(
        f"  - {k.get('indicator','')}: 목표 {k.get('target_2030','?')} / 현황 {k.get('current','?')}"
        for k in kpi_list
    ) or '  (KPI 정보 없음)'

    system_prompt = f"""당신은 베트남 인프라 시장 전문 분석가입니다.
아래 마스터플랜의 사업 개요와 KPI를 숙지한 후, 제공된 최신 기사들을 분석하여
사업 진행현황과의 연계 인사이트를 제공하세요.

【마스터플랜: {plan_id}】
제목: {plan_data.get('title_ko', plan_id)}
근거: {plan_data.get('decision', '')}

사업 개요:
{description}

KPI 목표:
{kpi_text}

분석 원칙:
1. 기사 내용을 사업 개요 및 KPI와 반드시 연계하여 해석
2. 수치와 근거를 명시 (날짜, 규모, 기관명 포함)
3. 투자자/사업개발자 관점의 실무적 인사이트 제공
4. 한국어로 작성, 전문적이고 간결하게
5. 전체 분량: 200~350자 이내
"""

    # ── 기사 목록 구성 (최대 8건, HIGH 우선) ─────────────────────────
    sorted_arts = sorted(articles,
                         key=lambda x: (0 if x['ctx_grade'] == 'HIGH' else 1, x['date']),
                         reverse=False)[:8]

    arts_text = ''
    for i, a in enumerate(sorted_arts, 1):
        title = a.get('title_ko') or a.get('title_en', '')
        summ  = a.get('summary_ko') or a.get('summary_en', '')
        arts_text += f"\n[{i}] {a['date']} | {a['source']} | {a['ctx_grade']}\n"
        arts_text += f"    제목: {title[:80]}\n"
        if summ:
            arts_text += f"    요약: {summ[:150]}\n"

    # KPI 변동 정보 추가
    change_note = ''
    if kpi_changes:
        change_note = '\n\n【이번 주 변동 사항】\n' + '\n'.join(f'  ★ {c}' for c in kpi_changes)

    user_prompt = f"""아래 최신 기사 {len(sorted_arts)}건을 분석하여 사업 개요와 KPI에 연계된
진행현황 분석문을 작성하세요.{change_note}

【최신 기사 목록】
{arts_text}

【요청】
다음 두 항목을 구분하여 답변하세요:

1. [최신 뉴스 분석] (150~250자)
   - 기사들이 보여주는 이번 주 핵심 동향
   - 사업 개요/KPI와의 연계 해석
   - 변동사항이 있으면 ★ 표시 후 강조

2. [Expert Insight] (50~100자)
   - 사업개발자/투자자를 위한 핵심 시사점 1~2문장
"""

    raw = call_haiku(system_prompt, user_prompt, api_key)

    # ── 응답 파싱 ───────────────────────────────────────────────────────
    news_analysis = ''
    insight       = ''

    if '[최신 뉴스 분석]' in raw:
        news_analysis = raw.split('[최신 뉴스 분석]')[1].split('[Expert Insight]')[0].strip()
    if '[Expert Insight]' in raw:
        insight = raw.split('[Expert Insight]')[1].strip()

    # 파싱 실패 시 전체 텍스트를 news_analysis로 사용
    if not news_analysis and raw:
        news_analysis = raw[:400]

    return {
        'news_analysis':   news_analysis,
        'insight':         insight,
        'kpi_status':      '',
        'articles_used':   len(sorted_arts),
        # ★ v3.2: 새 AI 논평 여부 플래그 (True = 이번 주 새로 생성)
        'analysis_is_new': True,
    }


def generate_executive_summary(
    all_articles: list[dict],
    kpi_changes:  dict,
    api_key:      str,
    dry_run:      bool = False,
) -> str:
    """
    전체 기사를 종합한 Executive Summary AI 논평 생성.
    보고서 첫 페이지에 삽입.
    """
    if dry_run or not api_key:
        return '[DRY-RUN] Executive Summary AI 논평 자리.'

    high_arts = [a for a in all_articles if a.get('ctx_grade') == 'HIGH'][:5]
    if not high_arts:
        high_arts = all_articles[:5]

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

    user_prompt = f"""이번 주 주요 기사:
{arts_text}

KPI 변동 플랜: {change_summary}

위 정보를 바탕으로 Executive Summary를 작성하세요.
변동사항이 있는 플랜은 ★ 표시하여 강조하세요."""

    return call_haiku(system_prompt, user_prompt, api_key)


# ══════════════════════════════════════════════════════════════════════════
#  [STEP 5] 보고서 데이터 조립 → JS 빌더 호출
# ══════════════════════════════════════════════════════════════════════════
def assemble_report_payload(
    plans:         dict,
    grouped_arts:  dict,
    all_articles:  list,
    analyses:      dict,
    exec_summary:  str,
    kpi_changes:   dict,
    sa7_context:   dict | None = None,   # SA-7 기사별 진행단계 데이터
    sa7_timeline:  dict | None = None,   # SA-7 플랜별 타임라인
) -> dict:
    """
    Node.js docx 빌더에 전달할 최종 JSON 페이로드 구성.
    Layer 1 (고정) + Layer 2 (AI 동적) 결합.
    """
    today      = datetime.now().strftime('%Y-%m-%d')
    week_label = datetime.now().strftime('%Y-W%V')

    plan_sections = []
    for plan_id, plan_data in plans.items():
        arts      = grouped_arts.get(plan_id, [])
        analysis  = analyses.get(plan_id, {})
        changes   = kpi_changes.get(plan_id, [])

        # ── SA-7 진행단계 데이터 읽기 ─────────────────────────────────
        tl_data    = (sa7_timeline or {}).get(plan_id, {})
        cur_stage  = tl_data.get('current_stage', 'UNKNOWN')
        stage_hist = tl_data.get('stage_history', [])
        next_watch = tl_data.get('next_watch', '')

        plan_sections.append({
            # ── Layer 1: 고정 데이터 ──────────────────────────────────
            'plan_id':       plan_id,
            'title_ko':      plan_data.get('title_ko', plan_id),
            'decision':      plan_data.get('decision', ''),
            'sector':        ', '.join(plan_data.get('sectors', [])),
            'area':          plan_data.get('area', ''),
            'description_ko': plan_data.get('description_ko', plan_data.get('description', '')),
            'kpi_targets':   plan_data.get('kpi_targets', []),     # KPI 목표값 테이블
            'key_projects':  plan_data.get('key_projects', []),    # 주요 프로젝트 목록

            # ── Layer 2: AI 동적 데이터 ───────────────────────────────
            'articles':         arts[:8],                             # 최신 기사 카드
            'news_analysis':    analysis.get('news_analysis', ''),   # AI 분석문
            'insight':          analysis.get('insight', ''),          # Expert Insight
            'articles_used':    analysis.get('articles_used', 0),
            # ★ v3.2: 새 AI 논평 여부 → JS 빌더에서 노란색 하이라이트 처리
            'analysis_is_new':  analysis.get('analysis_is_new', False),

            # ── KPI 변동 (노란색 하이라이트) ─────────────────────────
            'kpi_changes':    changes,
            'has_kpi_change': len(changes) > 0,

            # ── SA-7 진행단계 데이터 ──────────────────────────────────
            'current_stage':  cur_stage,
            'stage_history':  stage_hist[:5],   # 최근 5개 이정표
            'next_watch':     next_watch,
        })

    # exec_summary_is_new: plan_sections 중 하나라도 analysis_is_new=True이면 True
    any_new = any(s.get('analysis_is_new', False) for s in plan_sections)

    return {
        'report_date':       today,
        'report_week':       week_label,
        'total_articles':    len(all_articles),
        'plan_count':        len(plan_sections),
        'executive_summary': exec_summary,
        'kpi_changes_count': sum(len(v) for v in kpi_changes.values()),
        'plan_sections':     plan_sections,
        # ★ v3.2: Executive Summary도 새로 생성됐는지 여부
        'exec_summary_is_new': any_new,
    }


def run_js_builder(payload: dict, output_path: Path) -> bool:
    """
    Node.js docx 빌더 호출.
    페이로드를 임시 JSON으로 저장 후 환경변수로 경로 전달.
    v3.2: EXEC_SUMMARY_IS_NEW 값을 JS 소스에 동적 교체
    """
    AGENT_OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp_json = AGENT_OUT_DIR / 'sa8_report_payload.json'

    with open(tmp_json, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # ── v3.2: JS 파일의 EXEC_SUMMARY_IS_NEW 값 동적 교체 ──────────────
    # exec_summary_is_new: 이번 주 Executive Summary가 새로 생성됐는지 여부
    is_new_exec = payload.get('exec_summary_is_new', False)
    if JS_BUILDER.exists():
        js_src = JS_BUILDER.read_text(encoding='utf-8')
        js_src = js_src.replace(
            'const EXEC_SUMMARY_IS_NEW = false;  // Python이 동적으로 교체',
            f'const EXEC_SUMMARY_IS_NEW = {str(is_new_exec).lower()};  // Python 자동 설정'
        )
        # 임시 JS 파일에 저장 후 빌더로 사용
        tmp_js = AGENT_OUT_DIR / 'build_mi_report_tmp.js'
        tmp_js.write_text(js_src, encoding='utf-8')
        actual_builder = tmp_js
    else:
        actual_builder = JS_BUILDER

    if not JS_BUILDER.exists():
        log.error(f"JS 빌더 없음: {JS_BUILDER}")
        return False

    env = os.environ.copy()
    env['SA8_DATA_FILE']   = str(tmp_json)
    env['SA8_OUTPUT_PATH'] = str(output_path)

    builder_to_use = actual_builder if 'actual_builder' in dir() else JS_BUILDER
    log.info(f"Node.js 빌더 호출: {builder_to_use.name} (exec_is_new={is_new_exec})")
    result = subprocess.run(
        ['node', str(JS_BUILDER)],
        capture_output=True, text=True, timeout=180, env=env
    )

    if result.returncode != 0:
        log.error(f"빌더 오류:\n{result.stderr[:500]}")
        return False

    if result.stdout:
        log.info(result.stdout.strip())
    return True


# ══════════════════════════════════════════════════════════════════════════
#  [STEP 6] 이메일 발송
# ══════════════════════════════════════════════════════════════════════════
def send_email(report_path: Path) -> bool:
    username = os.getenv('EMAIL_USERNAME')
    password = os.getenv('EMAIL_PASSWORD')
    if not username or not password:
        log.warning("EMAIL_USERNAME/PASSWORD 없음 — 이메일 건너뜀")
        return False

    today = datetime.now().strftime('%Y년 %m월 %d일')
    msg   = MIMEMultipart()
    msg['From']    = username
    msg['To']      = username
    msg['Subject'] = f"[VN Infra MI] 주간 보고서 — {today}"

    body = (f"베트남 인프라 MI 주간 보고서 (첨부)\n\n"
            f"발행일: {today}\n"
            f"생성: SA-8 자동 파이프라인 (Claude Haiku 분석)\n\n"
            f"★ 노란색 강조 = 직전 주 대비 KPI 변동사항\n"
            f"★ AI 논평 = Layer 2 Claude Haiku 생성 (사업 개요 연계)\n")
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    with open(report_path, 'rb') as f:
        att = MIMEApplication(f.read(), Name=report_path.name)
    att['Content-Disposition'] = f'attachment; filename="{report_path.name}"'
    msg.attach(att)

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as srv:
            srv.login(username, password)
            srv.sendmail(username, [username], msg.as_string())
        log.info(f"이메일 발송 완료: {username}")
        return True
    except Exception as e:
        log.error(f"이메일 오류: {e}")
        return False



# ══════════════════════════════════════════════════════════════════════════
#  v3.1 신규: 이전 보고서 페이로드 로드 (AI 논평 보존용)
# ══════════════════════════════════════════════════════════════════════════
def load_previous_report_payload() -> dict | None:
    """
    직전 주 sa8_report_payload.json을 로드.
    API 차단 시 이전 AI 논평(news_analysis, insight, exec_summary)을
    그대로 재사용하기 위함.

    탐색 순서:
      1. data/agent_output/sa8_report_payload.json  (가장 최근 페이로드)
      2. data/agent_output/mi_daily_*.json           (최근 daily 파일)
    """
    # 1순위: 직전 주간 페이로드
    payload_path = AGENT_OUT_DIR / 'sa8_report_payload.json'
    if payload_path.exists():
        try:
            with open(payload_path, encoding='utf-8') as f:
                data = json.load(f)
            log.info(f"이전 보고서 페이로드 로드: {payload_path.name}")
            return data
        except Exception as e:
            log.warning(f"이전 페이로드 로드 실패: {e}")

    # 2순위: 가장 최근 daily JSON
    import glob
    daily_files = sorted(
        glob.glob(str(AGENT_OUT_DIR / 'mi_daily_*.json')),
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


def get_previous_plan_analysis(prev_payload: dict | None, plan_id: str) -> dict:
    """
    이전 보고서에서 특정 plan_id의 AI 논평을 추출.
    없으면 빈 dict 반환.
    """
    if not prev_payload:
        return {}
    for section in prev_payload.get('plan_sections', []):
        if section.get('plan_id') == plan_id:
            return {
                'news_analysis': section.get('news_analysis', ''),
                'insight':       section.get('insight', ''),
                'kpi_status':    section.get('kpi_status', ''),
                'articles_used': section.get('articles_used', 0),
            }
    return {}

# ══════════════════════════════════════════════════════════════════════════
#  main()
# ══════════════════════════════════════════════════════════════════════════
def main():
    dry_run    = '--dry-run'    in sys.argv
    send_mail  = '--send-email' in sys.argv
    daily_only = '--daily-only' in sys.argv   # SA-7 결과 JSON만 저장, docx 미생성
    days_back  = 7

    api_key = os.getenv('ANTHROPIC_API_KEY', '')
    if not api_key and not dry_run:
        log.warning("ANTHROPIC_API_KEY 없음 — AI 분석 건너뜀 (dry-run 모드로 전환)")
        dry_run = True

    today_str   = datetime.now().strftime('%Y%m%d')
    output_path = DOCS_DIR / f'VN_Infra_MI_Weekly_Report_{today_str}.docx'
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    log.info("=" * 65)
    log.info(f"SA-8 MI Report Generator v3.2 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    log.info(f"모드: {'DRY-RUN' if dry_run else 'LIVE'} | AI 모델: {HAIKU_MODEL}")
    log.info("=" * 65)

    # ── Step 0: v3.1 이전 보고서 로드 (AI 논평 보존) ───────────────────
    prev_payload = load_previous_report_payload()
    if dry_run and prev_payload:
        log.info("API 차단 중 → 이전 AI 논평 보존 모드 활성화")
        prev_exec_summary = prev_payload.get('executive_summary', '')
    else:
        prev_exec_summary = ''

    # 이전 논평을 함수 속성으로 주입 (클로저 대신 간단한 방법)
    generate_plan_analysis._prev_analyses = {}
    if prev_payload:
        for sec in prev_payload.get('plan_sections', []):
            pid = sec.get('plan_id', '')
            if pid:
                generate_plan_analysis._prev_analyses[pid] = {
                    'news_analysis': sec.get('news_analysis', ''),
                    'insight':       sec.get('insight', ''),
                }
    generate_executive_summary._prev_exec = prev_exec_summary

    # ── Step 1: Layer 1 고정 데이터 로드 ────────────────────────────────
    plans = load_knowledge_index()
    if not plans:
        log.error("마스터플랜 데이터 없음 — 종료")
        sys.exit(1)

    # ── Step 2: 최신 기사 추출 ──────────────────────────────────────────
    all_articles  = extract_weekly_articles(days_back)
    grouped_arts  = group_articles_by_plan(all_articles, plans)

    # ── Step 3: SA-7 진행단계 데이터 로드 ─────────────────────────────────
    log.info("SA-7 context 로드 중...")
    sa7_context  = load_sa7_context()
    sa7_timeline = load_sa7_timeline()

    # ── Step 3b: KPI 변동 감지 ──────────────────────────────────────────
    kpi_changes = detect_kpi_changes(plans)

    # ── Step 4: Layer 2 — Haiku AI 분석 (플랜별) ────────────────────────
    analyses: dict[str, dict] = {}
    total_plans = len(plans)
    for i, (plan_id, plan_data) in enumerate(plans.items(), 1):
        arts = grouped_arts.get(plan_id, [])
        if dry_run:
            log.info(f"  [{i}/{total_plans}] {plan_id}: {len(arts)}건 기사 → 이전 논평 재사용")
        else:
            log.info(f"  [{i}/{total_plans}] {plan_id}: {len(arts)}건 기사 → Haiku 분석 중...")

        analyses[plan_id] = generate_plan_analysis(
            plan_id     = plan_id,
            plan_data   = plan_data,
            articles    = arts,
            kpi_changes = kpi_changes.get(plan_id, []),
            api_key     = api_key,
            dry_run     = dry_run,
        )
        # API rate limit 방지
        if not dry_run and api_key:
            time.sleep(0.5)

    # ── Step 4b: Executive Summary AI 논평 ──────────────────────────────
    log.info("Executive Summary 생성 중...")
    exec_summary = generate_executive_summary(all_articles, kpi_changes, api_key, dry_run)

    # ── Step 5: 페이로드 조립 → Node.js 빌더 호출 ───────────────────────
    payload = assemble_report_payload(
        plans, grouped_arts, all_articles, analyses, exec_summary, kpi_changes,
        sa7_context=sa7_context,
        sa7_timeline=sa7_timeline,
    )
    # daily-only 모드: JSON 페이로드만 저장 (docx 미생성)
    if daily_only:
        AGENT_OUT_DIR.mkdir(parents=True, exist_ok=True)
        daily_json = AGENT_OUT_DIR / f'mi_daily_{datetime.now().strftime("%Y%m%d")}.json'
        with open(daily_json, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        log.info(f"✅ SA-8 daily-only 완료: {daily_json}")
        return

    success = run_js_builder(payload, output_path)

    if not success:
        log.error("보고서 생성 실패")
        sys.exit(1)

    # ── Step 6: 이메일 발송 (선택) ──────────────────────────────────────
    if send_mail:
        send_email(output_path)

    # ── 결과 요약 ───────────────────────────────────────────────────────
    log.info("")
    log.info("━" * 65)
    log.info(f"✅ SA-8 완료")
    log.info(f"   출력: {output_path}")
    log.info(f"   기사: {len(all_articles)}건 | 플랜: {len(plans)}개")
    if dry_run and prev_payload:
        log.info("   AI 분석: 이전 논평 보존 (API 비활성 — 기존 인사이트 유지)")
    elif dry_run:
        log.info("   AI 분석: 비활성 (이전 논평 없음 — 빈칸 처리)")
    else:
        log.info("   AI 분석: LIVE (Claude Haiku)")
    log.info(f"   KPI 변동: {len(kpi_changes)}개 플랜 (노란색 표시)")
    log.info("━" * 65)


if __name__ == '__main__':
    main()
