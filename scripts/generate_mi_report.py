#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_mi_report.py  ── SA-8 보고서 생성기 v3.0
===================================================
역할: knowledge_index.json + news_database.xlsx → PPT + Word 보고서 생성

v3.0 핵심 수정 (2026-05-10):
  1. 전체 플랜 포함 보장 — 기사 없는 플랜도 반드시 payload에 포함
  2. Layer1 필드 완전 매핑:
       description_ko, kpi_targets, key_projects → 절대 삭제 금지
  3. PPT 페이로드 구조 확장:
       kpi_dashboard, kpi_changes, kpi_achievement, areas 추가
  4. 신규/기존 기사 구분 (isNew 플래그) — 직전 실행 DB 비교
  5. 이메일 발송 조건 개선: KPI 변동 OR 기사 변동 시 발송

영구 제약:
  - Anthropic API: GitHub Actions에서 사용 불가 → 번역은 Google/MyMemory만
  - EMAIL_USERNAME / EMAIL_PASSWORD 시크릿 유지
  - ExcelUpdater.update_all() 메서드명 유지
"""

import json
import logging
import os
import subprocess
import sys
import smtplib
from datetime import datetime, timedelta
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

log = logging.getLogger('generate_mi_report')
logging.basicConfig(level=logging.INFO, format='%(asctime)s [SA-8] %(message)s')

# ── 경로 설정 ────────────────────────────────────────────────────────────
BASE_DIR     = Path(__file__).parent.parent
SCRIPTS_DIR  = BASE_DIR / 'scripts'
DATA_DIR     = BASE_DIR / 'data'
AGENT_OUT    = DATA_DIR / 'agent_output'
SHARED_DOCS  = BASE_DIR / 'docs' / 'shared'
DOCS_DIR     = BASE_DIR / 'docs'

KNOWLEDGE_INDEX_PATHS = [
    SHARED_DOCS / 'knowledge_index.json',
    DATA_DIR / 'shared' / 'knowledge_index.json',
    AGENT_OUT / 'knowledge_index.json',
]
COLLECTOR_OUT  = AGENT_OUT / 'collector_output.json'
PAYLOAD_FILE   = AGENT_OUT / 'sa8_report_payload.json'

PPT_BUILDER    = SCRIPTS_DIR / 'build_mi_ppt.js'
DOCX_BUILDER   = SCRIPTS_DIR / 'build_mi_report_sa8.js'

# ── 영역 정의 (knowledge_index에 없을 경우 기본값) ──────────────────────
DEFAULT_AREAS = [
    {
        'name_ko': '환경 인프라',
        'name_en': 'Environment Infrastructure',
        'sector_keywords': ['Waste Water', 'Wastewater', 'Water Supply', 'Drainage',
                            'Solid Waste', 'Environment'],
    },
    {
        'name_ko': '에너지·전력',
        'name_en': 'Energy & Power',
        'sector_keywords': ['Power', 'Oil', 'Gas', 'Energy', 'LNG', 'Nuclear',
                            'Renewable', 'Hydrogen'],
    },
    {
        'name_ko': '도시·교통·산업',
        'name_en': 'Urban & Transport',
        'sector_keywords': ['Smart City', 'Industrial', 'Transport', 'Urban',
                            'Metro', 'Road', 'Airport'],
    },
]

# ══════════════════════════════════════════════════════════════════════════
# 1. knowledge_index.json 로드
# ══════════════════════════════════════════════════════════════════════════
def load_knowledge_index():
    for kpath in KNOWLEDGE_INDEX_PATHS:
        if kpath.exists():
            log.info(f'knowledge_index 로드: {kpath}')
            with open(kpath, encoding='utf-8') as f:
                ki = json.load(f)
            # v2.x 구조 확인
            plans = ki.get('masterplans', {})
            if isinstance(plans, list):
                # 구버전 list → dict 변환
                plans = {p.get('id', f'PLAN_{i}'): p for i, p in enumerate(plans)}
            return ki, plans
    log.warning('knowledge_index.json 없음 — 빈 플랜으로 진행')
    return {}, {}

# ══════════════════════════════════════════════════════════════════════════
# 2. 수집 기사 로드 (collector_output.json 또는 Excel)
# ══════════════════════════════════════════════════════════════════════════
def load_articles(days_back=14):
    """
    collector_output.json 우선 → 없으면 Excel DB에서 직접 읽기.
    days_back 기간 내 기사만 반환.
    """
    articles = []
    cutoff = datetime.now() - timedelta(days=days_back)

    # 1순위: collector_output.json
    if COLLECTOR_OUT.exists():
        try:
            with open(COLLECTOR_OUT, encoding='utf-8') as f:
                raw = json.load(f)
            if isinstance(raw, list):
                articles = raw
            elif isinstance(raw, dict):
                articles = raw.get('articles', raw.get('items', []))
            log.info(f'collector_output.json에서 {len(articles)}건 로드')
        except Exception as e:
            log.warning(f'collector_output.json 읽기 실패: {e}')

    # 2순위: Excel DB 직접 읽기
    if not articles:
        try:
            import openpyxl
            excel_paths = list((DATA_DIR).glob('*.xlsx')) + \
                          list((DATA_DIR / 'database').glob('*.xlsx'))
            if excel_paths:
                wb = openpyxl.load_workbook(excel_paths[0], read_only=True, data_only=True)
                ws = wb.active
                headers = [str(cell.value or '').strip() for cell in next(ws.iter_rows(max_row=1))]
                for row in ws.iter_rows(min_row=2, values_only=True):
                    if not row or not row[0]:
                        continue
                    art = dict(zip(headers, row))
                    articles.append(art)
                wb.close()
                log.info(f'Excel DB에서 {len(articles)}건 로드')
        except Exception as e:
            log.warning(f'Excel 읽기 실패: {e}')

    # 날짜 필터
    filtered = []
    for art in articles:
        date_str = (art.get('date') or art.get('published_date') or
                    art.get('Date') or art.get('Published_Date') or '')
        try:
            if isinstance(date_str, datetime):
                art_date = date_str
            else:
                art_date = datetime.strptime(str(date_str)[:10], '%Y-%m-%d')
            if art_date >= cutoff:
                filtered.append(art)
        except Exception:
            pass  # 날짜 없는 기사는 스킵

    log.info(f'최근 {days_back}일 기사: {len(filtered)}건 / 전체 {len(articles)}건')
    return filtered

# ══════════════════════════════════════════════════════════════════════════
# 3. 기사 ↔ 플랜 매핑
# ══════════════════════════════════════════════════════════════════════════
def match_articles_to_plans(articles, plans):
    """
    knowledge_index의 keywords_en/keywords_vi/keywords로 기사를 플랜에 매핑.
    기사가 없는 플랜도 빈 리스트로 반드시 포함 (Layer1 보존 목적).
    """
    grouped = {pid: [] for pid in plans}  # 모든 플랜 초기화

    for art in articles:
        text = ' '.join([
            str(art.get('title_ko', '')),
            str(art.get('title_en', '') or art.get('title', '')),
            str(art.get('summary_ko', '') or art.get('Summary_KO', '')),
            str(art.get('matched_plan', '') or art.get('Matched_Plan', '')),
        ]).lower()

        matched_plan = (art.get('matched_plan') or art.get('Matched_Plan') or '').strip()

        for pid, pdata in plans.items():
            # 1. matched_plan 직접 매칭
            if matched_plan and matched_plan == pid:
                grouped[pid].append(art)
                break

            # 2. 키워드 매칭
            kws = (pdata.get('keywords_en', []) or
                   pdata.get('keywords', []) or
                   pdata.get('keywords_vi', []))
            if isinstance(kws, str):
                kws = [kws]
            if any(kw.lower() in text for kw in kws if kw):
                grouped[pid].append(art)
                break

    total_matched = sum(len(v) for v in grouped.values())
    log.info(f'기사 매핑 완료: {total_matched}건 매핑 / {len(articles)}건 전체')
    return grouped

# ══════════════════════════════════════════════════════════════════════════
# 4. 신규/기존 기사 구분
# ══════════════════════════════════════════════════════════════════════════
def mark_new_articles(articles, prev_payload_path=None):
    """
    이전 payload의 URL 목록과 비교하여 isNew 플래그 설정.
    """
    prev_urls = set()
    if prev_payload_path and Path(prev_payload_path).exists():
        try:
            with open(prev_payload_path, encoding='utf-8') as f:
                prev = json.load(f)
            for pdata in prev.get('plans', {}).values():
                for art in pdata.get('articles', []):
                    if art.get('url'):
                        prev_urls.add(art['url'])
        except Exception:
            pass

    for art in articles:
        url = art.get('url') or art.get('URL') or ''
        art['isNew'] = url not in prev_urls if prev_urls else True

    new_cnt = sum(1 for a in articles if a.get('isNew'))
    log.info(f'신규 기사: {new_cnt}건 / 전체 {len(articles)}건')
    return articles

# ══════════════════════════════════════════════════════════════════════════
# 5. KPI 변동 감지
# ══════════════════════════════════════════════════════════════════════════
def detect_kpi_changes(plans, prev_payload_path=None):
    """
    이전 payload의 kpi_targets와 현재 비교.
    changed=True 항목을 kpi_changes 리스트로 반환.
    """
    kpi_changes = []
    if not prev_payload_path or not Path(prev_payload_path).exists():
        return kpi_changes

    try:
        with open(prev_payload_path, encoding='utf-8') as f:
            prev = json.load(f)
        prev_plans = prev.get('plans', {})

        for pid, pdata in plans.items():
            prev_pdata = prev_plans.get(pid, {})
            curr_kpis = {k.get('label', k.get('indicator', '')): k
                         for k in pdata.get('kpi_targets', [])}
            prev_kpis = {k.get('label', k.get('indicator', '')): k
                         for k in prev_pdata.get('kpi_targets', [])}

            for label, curr in curr_kpis.items():
                prev_kpi = prev_kpis.get(label)
                if not prev_kpi:
                    # 신규 KPI 추가
                    kpi_changes.append({
                        'plan_id': pid,
                        'indicator': label,
                        'from': '미포함',
                        'to': str(curr.get('target', '')),
                        'reason': f'{pid} — 신규 KPI 추가',
                    })
                    curr['changed'] = True
                elif str(curr.get('target', '')) != str(prev_kpi.get('target', '')):
                    kpi_changes.append({
                        'plan_id': pid,
                        'indicator': label,
                        'from': str(prev_kpi.get('target', '')),
                        'to': str(curr.get('target', '')),
                        'reason': f'{pid} — {label} 목표값 변경',
                    })
                    curr['changed'] = True
    except Exception as e:
        log.warning(f'KPI 변동 감지 실패: {e}')

    log.info(f'KPI 변동: {len(kpi_changes)}건')
    return kpi_changes

# ══════════════════════════════════════════════════════════════════════════
# 6. 페이로드 조립
# ══════════════════════════════════════════════════════════════════════════
def assemble_payload(ki, plans, grouped_arts, all_articles, kpi_changes):
    today_str = datetime.now().strftime('%Y-%m-%d')
    period_start = (datetime.now() - timedelta(days=13)).strftime('%Y-%m-%d')

    # ── KPI 대시보드 (전체 플랜의 주요 KPI 집계) ────────────────────────
    kpi_dashboard = []
    kpi_labels_seen = set()
    for pdata in plans.values():
        for kpi in pdata.get('kpi_targets', []):
            label = kpi.get('label') or kpi.get('indicator') or ''
            if label and label not in kpi_labels_seen:
                kpi_labels_seen.add(label)
                kpi_dashboard.append({
                    'label':   label,
                    'target':  kpi.get('target', ''),
                    'current': kpi.get('current', ''),
                    'changed': kpi.get('changed', False),
                })
            if len(kpi_dashboard) >= 12:
                break
        if len(kpi_dashboard) >= 12:
            break

    # ── KPI 달성률 (kpi_achievement) ────────────────────────────────────
    kpi_achievement = []
    for kpi in kpi_dashboard[:8]:
        # current에서 숫자 파싱 시도
        import re
        nums = re.findall(r'[\d.]+', str(kpi.get('current', '')))
        target_nums = re.findall(r'[\d.]+', str(kpi.get('target', '')))
        try:
            curr_n = float(nums[0]) if nums else 0
            tgt_n  = float(target_nums[0]) if target_nums else 100
            pct = min(int(curr_n / tgt_n * 100), 100) if tgt_n else 0
        except Exception:
            pct = 0
        kpi_achievement.append({'label': kpi['label'], 'current_pct': pct})

    # ── 영역별 플랜 분류 ─────────────────────────────────────────────────
    areas = []
    for area_def in DEFAULT_AREAS:
        matched_ids = []
        for pid, pdata in plans.items():
            sector = pdata.get('sector', '') or pdata.get('sectors', [''])[0] if isinstance(pdata.get('sectors'), list) else ''
            area_f  = pdata.get('area', '')
            for kw in area_def['sector_keywords']:
                if kw.lower() in sector.lower() or kw.lower() in area_f.lower():
                    matched_ids.append(pid)
                    break
        if matched_ids:
            areas.append({
                'name_ko':  area_def['name_ko'],
                'name_en':  area_def['name_en'],
                'plan_ids': matched_ids,
            })

    # ── 플랜별 데이터 조립 ──────────────────────────────────────────────
    plans_payload = {}
    for pid, pdata in plans.items():
        arts = grouped_arts.get(pid, [])
        arts_payload = []
        for a in arts:
            arts_payload.append({
                'title_ko':   str(a.get('title_ko') or a.get('Title_KO') or a.get('title') or ''),
                'summary_ko': str(a.get('summary_ko') or a.get('Summary_KO') or '')[:200],
                'source':     str(a.get('source') or a.get('Source') or ''),
                'date':       str(a.get('date') or a.get('published_date') or a.get('Date') or '')[:10],
                'url':        str(a.get('url') or a.get('URL') or ''),
                'isNew':      bool(a.get('isNew', False)),
            })

        # Layer1 필드 직접 매핑 (절대 삭제 금지)
        kpi_targets = pdata.get('kpi_targets', [])
        # kpi_targets 구조 정규화
        normalized_kpis = []
        for k in kpi_targets:
            if isinstance(k, dict):
                normalized_kpis.append({
                    'label':    k.get('label') or k.get('indicator') or k.get('indicator_ko') or '',
                    'target':   str(k.get('target', '')),
                    'current':  str(k.get('current') or k.get('current_value') or k.get('baseline') or ''),
                    'changed':  bool(k.get('changed', False)),
                })

        key_projects = pdata.get('key_projects', [])
        normalized_projs = []
        for p in key_projects:
            if isinstance(p, dict):
                normalized_projs.append({
                    'name_ko':  p.get('name_ko') or p.get('name') or '',
                    'location': p.get('location') or p.get('province') or '',
                    'capacity': p.get('capacity') or p.get('size') or '',
                    'note':     p.get('note') or p.get('description') or '',
                    'status':   p.get('status') or '',
                })

        plans_payload[pid] = {
            'plan_name_ko':  pdata.get('name_ko') or pdata.get('plan_name_ko') or pid,
            'sector':        pdata.get('sector') or (pdata.get('sectors', [''])[0] if pdata.get('sectors') else ''),
            'area':          pdata.get('area') or '',
            'decision':      pdata.get('decision') or pdata.get('legal_basis') or '',
            # ★ Layer1 필수 필드 (절대 삭제 금지)
            'description_ko': pdata.get('description_ko') or pdata.get('description') or '',
            'kpi_targets':    normalized_kpis,
            'key_projects':   normalized_projs,
            # Layer2 (AI 분석)
            'analysis_ko':   pdata.get('analysis_ko') or '',
            'kpi_changes':   [c for c in kpi_changes if c.get('plan_id') == pid],
            'articles':      arts_payload,
        }

    new_count = sum(1 for a in all_articles if a.get('isNew'))

    payload = {
        'report_date':        today_str,
        'report_period':      f'{period_start} ~ {today_str}',
        'knowledge_version':  ki.get('version', 'v2.3'),
        'total_articles':     len(all_articles),
        'new_articles_count': new_count,
        'executive_summary_ko': '',   # generate_mi_report.py에서는 빈 값, Haiku가 채움
        'kpi_dashboard':      kpi_dashboard,
        'kpi_changes':        kpi_changes,
        'kpi_achievement':    kpi_achievement,
        'areas':              areas,
        'plans':              plans_payload,
    }

    return payload

# ══════════════════════════════════════════════════════════════════════════
# 7. PPT / Word 빌더 실행
# ══════════════════════════════════════════════════════════════════════════
def run_ppt_builder(payload_path, output_path):
    if not PPT_BUILDER.exists():
        log.warning(f'PPT 빌더 없음: {PPT_BUILDER}')
        return False
    env = os.environ.copy()
    env['SA8_DATA_FILE']    = str(payload_path)
    env['SA8_OUTPUT_PATH']  = str(output_path)
    result = subprocess.run(['node', str(PPT_BUILDER)], env=env,
                            capture_output=True, text=True)
    if result.returncode != 0:
        log.error(f'PPT 빌더 실패:\n{result.stderr}')
        return False
    log.info(f'PPT 생성: {output_path}')
    return True

def run_docx_builder(payload_path, output_path):
    if not DOCX_BUILDER.exists():
        log.warning(f'Word 빌더 없음: {DOCX_BUILDER}')
        return False
    result = subprocess.run(
        ['node', str(DOCX_BUILDER), str(payload_path), str(output_path)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        log.error(f'Word 빌더 실패:\n{result.stderr}')
        return False
    log.info(f'Word 생성: {output_path}')
    return True

# ══════════════════════════════════════════════════════════════════════════
# 8. 이메일 발송
# ══════════════════════════════════════════════════════════════════════════
def send_email(pptx_path, docx_path, payload, kpi_changes):
    """
    발송 조건: KPI 변동 OR 신규 기사 존재.
    """
    has_kpi_changes  = len(kpi_changes) > 0
    has_new_articles = payload.get('new_articles_count', 0) > 0

    if not has_kpi_changes and not has_new_articles:
        log.info('이메일 발송 조건 미충족 (KPI 변동 없음 + 신규 기사 없음)')
        return False

    username = os.environ.get('EMAIL_USERNAME')
    password = os.environ.get('EMAIL_PASSWORD')
    if not username or not password:
        log.warning('EMAIL_USERNAME / EMAIL_PASSWORD 미설정')
        return False

    today_str = payload.get('report_date', datetime.now().strftime('%Y-%m-%d'))
    subject   = f'[베트남 인프라 MI] 주간 보고서 — {today_str}'
    if has_kpi_changes:
        subject += f' ★ KPI 변동 {len(kpi_changes)}건'

    body_parts = [
        f'안녕하세요,\n\n베트남 인프라 MI 주간 보고서({today_str})를 첨부합니다.\n',
        f'■ 수집 기간: {payload.get("report_period", "")}',
        f'■ 전체 기사: {payload.get("total_articles", 0)}건 (신규 {payload.get("new_articles_count", 0)}건)',
        f'■ 마스터플랜: {len(payload.get("plans", {}))}개',
    ]
    if has_kpi_changes:
        body_parts.append(f'\n★ KPI 변동사항 ({len(kpi_changes)}건):')
        for ch in kpi_changes:
            body_parts.append(f'  - {ch.get("plan_id")}: {ch.get("indicator")} '
                              f'{ch.get("from")} → {ch.get("to")}')

    body_parts.append('\n대시보드: https://hms4792.github.io/vietnam-infra-news/')
    body = '\n'.join(body_parts)

    msg = MIMEMultipart()
    msg['Subject'] = subject
    msg['From']    = username
    msg['To']      = username
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    for fpath, fname in [(pptx_path, 'pptx'), (docx_path, 'docx')]:
        if fpath and Path(fpath).exists():
            with open(fpath, 'rb') as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', 'attachment',
                            filename=Path(fpath).name)
            msg.attach(part)

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(username, password)
            smtp.send_message(msg)
        log.info(f'이메일 발송 완료: {username}')
        return True
    except Exception as e:
        log.error(f'이메일 발송 실패: {e}')
        return False

# ══════════════════════════════════════════════════════════════════════════
# 9. 메인
# ══════════════════════════════════════════════════════════════════════════
def main():
    import argparse
    parser = argparse.ArgumentParser(description='SA-8 MI 보고서 생성기')
    parser.add_argument('--days-back',   type=int,  default=14,    help='기사 수집 기간(일)')
    parser.add_argument('--send-email',  action='store_true',       help='이메일 발송')
    parser.add_argument('--dry-run',     action='store_true',       help='페이로드만 생성 (빌더 미실행)')
    parser.add_argument('--output-dir',  default=str(DOCS_DIR),     help='출력 디렉토리')
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    AGENT_OUT.mkdir(parents=True, exist_ok=True)

    today_tag  = datetime.now().strftime('%Y%m%d')
    pptx_path  = output_dir / f'VN_Infra_MI_Weekly_Report_{today_tag}.pptx'
    docx_path  = AGENT_OUT  / f'VN_Infra_MI_Report_{today_tag}.docx'
    prev_payload = AGENT_OUT / 'sa8_report_payload_prev.json'

    log.info('=' * 60)
    log.info('SA-8 MI 보고서 생성기 v3.0 시작')
    log.info('=' * 60)

    # Step 1: knowledge_index 로드
    ki, plans = load_knowledge_index()
    if not plans:
        log.error('마스터플랜 데이터 없음. knowledge_index.json을 확인하세요.')
        sys.exit(1)
    log.info(f'마스터플랜: {len(plans)}개')

    # Step 2: 기사 로드
    all_articles = load_articles(days_back=args.days_back)

    # Step 3: 신규/기존 구분
    all_articles = mark_new_articles(all_articles, prev_payload)

    # Step 4: 기사 ↔ 플랜 매핑
    grouped_arts = match_articles_to_plans(all_articles, plans)

    # Step 5: KPI 변동 감지
    kpi_changes = detect_kpi_changes(plans, prev_payload)

    # Step 6: 페이로드 조립
    payload = assemble_payload(ki, plans, grouped_arts, all_articles, kpi_changes)

    # 이전 payload 백업
    if PAYLOAD_FILE.exists():
        import shutil
        shutil.copy(PAYLOAD_FILE, prev_payload)

    # 페이로드 저장
    with open(PAYLOAD_FILE, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    log.info(f'페이로드 저장: {PAYLOAD_FILE}')
    log.info(f'  플랜: {len(payload["plans"])}개 | 기사: {payload["total_articles"]}건')

    if args.dry_run:
        log.info('DRY-RUN 모드 — 빌더 실행 생략')
        return

    # Step 7: PPT 생성
    ppt_ok = run_ppt_builder(PAYLOAD_FILE, pptx_path)

    # Step 8: Word 생성
    docx_ok = run_docx_builder(PAYLOAD_FILE, docx_path)

    # Step 9: 이메일 발송
    if args.send_email and (ppt_ok or docx_ok):
        send_email(
            pptx_path if ppt_ok else None,
            docx_path if docx_ok else None,
            payload,
            kpi_changes,
        )

    log.info('=' * 60)
    log.info(f'SA-8 완료: PPT={ppt_ok} | Word={docx_ok}')
    log.info('=' * 60)


if __name__ == '__main__':
    main()
