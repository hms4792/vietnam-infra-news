#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News — Main Pipeline
Version 2.0 — Genspark 에이전트 팀 아키텍처 반영

파이프라인 흐름 (Genspark Leader Agent 스펙):
  Step 1: 기존 DB 로드
  Step 2: 뉴스 수집 (news_collector.py → collect_news())
  Step 3: AI 요약 (ai_summarizer.py → AISummarizer)
  Step 4: Quality Control (오분류율 5% 초과 시 경고)
  Step 5: 대시보드 생성 (dashboard_updater.py)
  Step 6: 이메일 발송 (notifier.py)
  Step 7: 실행 보고서 출력

반영된 개선사항:
  [검증보고서] QC 단계 신설 (특정 섹터 쏠림 5% 임계값 감지)
  [검증보고서] 오분류 자동 감지 및 로그
  [Genspark]  Collector → Classifier → Summarizer → QC → Publisher 순서
  [Genspark]  최종 Execution Report 출력
  [v5.1 fix]  NewsCollector 클래스 → collect_news() 함수 호출로 수정
  [v5.1 fix]  config.settings 의존성 제거
"""

import logging
import sys
import os
import json
from datetime import datetime
from pathlib import Path
from collections import Counter

# ── 경로 설정 ────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR     = PROJECT_ROOT / "data"
OUTPUT_DIR   = PROJECT_ROOT / "outputs"
EXCEL_DB_PATH = DATA_DIR / "database" / "Vietnam_Infra_News_Database_Final.xlsx"

sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ── 환경변수 ─────────────────────────────────────────────────
HOURS_BACK    = int(os.environ.get('HOURS_BACK', 24))
SKIP_SUMMARIZER = os.environ.get('SKIP_SUMMARIZER', 'false').lower() == 'true'
SKIP_NOTIFY   = os.environ.get('SKIP_NOTIFY', 'false').lower() == 'true'

# [Genspark] QC: 단일 섹터가 전체의 이 비율 초과 시 경고
QC_SECTOR_DOMINANCE_THRESHOLD = float(os.environ.get('QC_THRESHOLD', 0.40))
# [Genspark] QC: confidence 낮은 기사 비율이 이 이상이면 재분류 권고
QC_LOW_CONF_THRESHOLD = float(os.environ.get('QC_LOW_CONF', 0.20))


# ============================================================
# STEP 1: LOAD EXISTING ARTICLES FROM EXCEL
# ============================================================

def load_articles_from_excel():
    try:
        import openpyxl
    except ImportError:
        logger.error("openpyxl 미설치")
        return []

    if not EXCEL_DB_PATH.exists():
        logger.warning(f"Excel DB 없음: {EXCEL_DB_PATH}")
        return []

    logger.info(f"Excel 로드: {EXCEL_DB_PATH}")
    try:
        wb = openpyxl.load_workbook(EXCEL_DB_PATH, read_only=True, data_only=True)
        ws = wb.active
        headers = [cell.value for cell in ws[1]]
        col_map = {str(h).strip(): i for i, h in enumerate(headers) if h}

        articles = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not any(row):
                continue
            date_val = row[col_map.get("Date", 4)] if "Date" in col_map else None
            date_str = ""
            if date_val:
                date_str = (date_val.strftime("%Y-%m-%d")
                            if hasattr(date_val, 'strftime') else str(date_val)[:10])

            article = {
                "area":       row[col_map.get("Area", 0)]           or "Environment",
                "sector":     row[col_map.get("Business Sector", 1)] or "",
                "province":   row[col_map.get("Province", 2)]        or "Vietnam",
                "title":      row[col_map.get("News Tittle", 3)]     or "",
                "date":       date_str,
                "source":     row[col_map.get("Source", 5)]          or "",
                "url":        row[col_map.get("Link", 6)]            or "",
                "summary_vi": row[col_map.get("Short summary", 7)]  or "",
            }
            if article["title"] or article["url"]:
                articles.append(article)

        wb.close()
        logger.info(f"Excel 로드 완료: {len(articles)}건")
        return articles

    except Exception as e:
        logger.error(f"Excel 로드 오류: {e}")
        import traceback; traceback.print_exc()
        return []


# ============================================================
# STEP 2: COLLECT NEW ARTICLES
# [v5.1 fix] NewsCollector 클래스 → collect_news() 함수로 변경
# ============================================================

def collect_new_articles():
    logger.info("\n[Step 2] 뉴스 수집 시작...")

    try:
        import importlib.util
        collector_path = SCRIPT_DIR / "news_collector.py"

        if not collector_path.exists():
            logger.error(f"news_collector.py 없음: {collector_path}")
            return [], {}

        spec   = importlib.util.spec_from_file_location("news_collector", collector_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # [v5.1 fix] collect_news() 함수 직접 호출
        count, new_articles, collection_stats = module.collect_news(hours_back=HOURS_BACK)
        logger.info(f"수집 완료: {count}건")

        if new_articles:
            try:
                module.update_excel_database(new_articles, collection_stats)
            except Exception as e:
                logger.warning(f"Excel 저장 오류: {e}")

        return new_articles, collection_stats

    except Exception as e:
        logger.error(f"수집 오류: {e}")
        import traceback; traceback.print_exc()
        return [], {}


# ============================================================
# STEP 3: AI SUMMARIZER
# [검증보고서] API 키 미설정 시 단순 반복 방지 → 구조화 fallback
# ============================================================

def run_summarizer(new_articles):
    if SKIP_SUMMARIZER or not new_articles:
        logger.info("[Step 3] 요약 건너뜀")
        return new_articles

    logger.info(f"\n[Step 3] AI 요약 시작 ({len(new_articles)}건)...")

    try:
        import importlib.util
        summarizer_path = SCRIPT_DIR / "ai_summarizer.py"

        if not summarizer_path.exists():
            logger.warning("ai_summarizer.py 없음 — 요약 건너뜀")
            return new_articles

        spec   = importlib.util.spec_from_file_location("ai_summarizer", summarizer_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        summarizer = module.AISummarizer()
        result     = summarizer.process_articles(new_articles)

        api_ok   = sum(1 for a in result if not a.get('is_fallback'))
        fallback = sum(1 for a in result if a.get('is_fallback'))
        logger.info(f"요약 완료: API={api_ok} | fallback={fallback}")
        return result

    except Exception as e:
        logger.error(f"요약 오류: {e}")
        import traceback; traceback.print_exc()
        return new_articles


# ============================================================
# STEP 4: QUALITY CONTROL
# [검증보고서] 오분류율 5% 초과 감지
# [Genspark]  QC Agent 역할 구현
# ============================================================

def run_quality_control(new_articles, all_articles):
    """
    QC 체크:
    1. 섹터 쏠림 감지 (단일 섹터 40% 초과 → 경고)
    2. confidence 낮은 기사 비율 체크
    3. 비베트남 기사 감지
    4. 오분류 의심 패턴 감지
    """
    logger.info("\n[Step 4] Quality Control...")

    qc_result = {
        "pass": True,
        "warnings": [],
        "errors": [],
        "stats": {},
        "rejected_count": 0,
        "valid_count": len(new_articles),
    }

    if not new_articles:
        logger.info("  검사할 신규 기사 없음")
        return qc_result, new_articles

    total = len(new_articles)

    # ── 1. 섹터 쏠림 감지 ──────────────────────────────────
    sector_counts = Counter(a.get('sector', '') for a in new_articles)
    for sector, cnt in sector_counts.most_common():
        ratio = cnt / total
        if ratio > QC_SECTOR_DOMINANCE_THRESHOLD:
            msg = (f"⚠️  섹터 쏠림 감지: [{sector}] {cnt}/{total} ({ratio:.1%}) "
                   f"— 임계값 {QC_SECTOR_DOMINANCE_THRESHOLD:.0%} 초과")
            logger.warning(msg)
            qc_result["warnings"].append(msg)

    # ── 2. Confidence 낮은 기사 비율 ───────────────────────
    low_conf_arts = [a for a in new_articles if a.get('confidence', 100) < 50]
    low_conf_ratio = len(low_conf_arts) / total if total else 0
    if low_conf_ratio > QC_LOW_CONF_THRESHOLD:
        msg = (f"⚠️  저신뢰도 기사 비율: {len(low_conf_arts)}/{total} ({low_conf_ratio:.1%}) "
               f"— 재분류 권고")
        logger.warning(msg)
        qc_result["warnings"].append(msg)

    # ── 3. 비베트남 기사 감지 ───────────────────────────────
    non_vn_patterns = [
        "in spain", "in china", "in japan", "in india",
        "in korea", "in europe", "in america",
    ]
    rejected = []
    valid    = []
    for art in new_articles:
        text = (art.get('title', '') + ' ' + art.get('summary', '')).lower()
        is_non_vn = any(p in text for p in non_vn_patterns)
        vietnam_mentioned = 'vietnam' in text or 'việt nam' in text

        if is_non_vn and not vietnam_mentioned:
            art['qc_rejected'] = True
            art['qc_reason']   = "Non-Vietnam article"
            rejected.append(art)
            logger.debug(f"  REJECTED (non-VN): {art.get('title','')[:60]}")
        else:
            valid.append(art)

    # ── 4. 오분류 의심 패턴 ────────────────────────────────
    mismatch_patterns = {
        "Waste Water": ["vehicle", "car", "flight", "marry", "wedding",
                        "football", "soccer", "tourism"],
        "Solid Waste": ["vehicle", "flight", "marry", "tourism"],
        "Power":       ["vehicle", "football", "tourism"],
    }
    misclassified = []
    for art in valid:
        sector = art.get('sector', '')
        text   = (art.get('title', '') + ' ' + art.get('summary', '')).lower()
        bad_kws = mismatch_patterns.get(sector, [])
        hits    = [kw for kw in bad_kws if kw in text]
        if hits:
            art['qc_flag']   = True
            art['qc_reason'] = f"Possible misclassification: {hits}"
            misclassified.append(art)

    if misclassified:
        msg = f"⚠️  오분류 의심: {len(misclassified)}건 (QC 플래그 처리)"
        logger.warning(msg)
        qc_result["warnings"].append(msg)

    # ── 결과 집계 ──────────────────────────────────────────
    qc_result["stats"] = {
        "total_new":       total,
        "valid":           len(valid),
        "rejected":        len(rejected),
        "low_confidence":  len(low_conf_arts),
        "qc_flagged":      len(misclassified),
        "sector_counts":   dict(sector_counts),
    }
    qc_result["rejected_count"] = len(rejected)
    qc_result["valid_count"]    = len(valid)

    # ── QC 통과 여부 ───────────────────────────────────────
    if len(rejected) / total > 0.30 if total else False:
        qc_result["pass"]   = False
        qc_result["errors"].append("거부율 30% 초과 — 퍼블리싱 중단 권고")

    logger.info(
        f"  QC 결과: valid={len(valid)} | rejected={len(rejected)} | "
        f"flagged={len(misclassified)} | pass={qc_result['pass']}"
    )
    return qc_result, valid


# ============================================================
# STEP 5: DASHBOARD
# ============================================================

def create_dashboard(all_articles):
    logger.info(f"\n[Step 5] 대시보드 생성 ({len(all_articles)}건)...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        import importlib.util
        dashboard_path = SCRIPT_DIR / "dashboard_updater.py"

        if not dashboard_path.exists():
            logger.error("dashboard_updater.py 없음")
            return _create_minimal_dashboard(all_articles)

        spec   = importlib.util.spec_from_file_location("dashboard_updater", dashboard_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        dashboard = module.DashboardUpdater()
        dashboard.update(all_articles)

        excel_updater = module.ExcelUpdater()
        excel_updater.update(all_articles)

        logger.info("대시보드 생성 완료")
        return True

    except Exception as e:
        logger.error(f"대시보드 오류: {e}")
        import traceback; traceback.print_exc()
        return _create_minimal_dashboard(all_articles)


def _create_minimal_dashboard(articles):
    """Fallback: 최소 대시보드 HTML 생성"""
    try:
        js_data = json.dumps([{
            "id":       i,
            "title":    {"vi": a.get("title",""), "en": a.get("title",""), "ko": a.get("title","")},
            "summary":  {"vi": a.get("summary_vi",""), "en": a.get("summary_en",""),
                         "ko": a.get("summary_ko","")},
            "sector":   a.get("sector","Unknown"),
            "area":     a.get("area","Environment"),
            "province": a.get("province","Vietnam"),
            "source":   a.get("source",""),
            "url":      a.get("url",""),
            "date":     str(a.get("date",""))[:10],
        } for i, a in enumerate(articles, 1)], ensure_ascii=False)

        html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<title>Vietnam Infrastructure News</title>
<script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-slate-100 p-8">
<h1 class="text-2xl font-bold mb-2">🇻🇳 Vietnam Infrastructure News</h1>
<p class="text-slate-500 mb-4">Total: {len(articles)} articles | Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
<div id="list" class="space-y-2"></div>
<script>
const DATA = {js_data};
document.getElementById('list').innerHTML = DATA.slice(0,200).map(a=>`
<div class="bg-white p-3 rounded shadow">
  <span class="text-xs bg-teal-100 px-2 py-1 rounded">${{a.sector}}</span>
  <span class="text-xs text-slate-400 ml-2">${{a.date}}</span>
  <div class="font-medium mt-1"><a href="${{a.url}}" class="hover:underline">${{a.title.vi}}</a></div>
  <div class="text-sm text-slate-500">${{a.source}} | ${{a.province}}</div>
  <div class="text-sm text-slate-600 mt-1">${{a.summary.ko}}</div>
</div>`).join('');
</script>
</body>
</html>"""

        for fname in ['index.html', 'vietnam_dashboard.html']:
            (OUTPUT_DIR / fname).write_text(html, encoding='utf-8')
        logger.info("최소 대시보드 생성 완료")
        return True

    except Exception as e:
        logger.error(f"최소 대시보드 오류: {e}")
        return False


# ============================================================
# STEP 6: NOTIFICATIONS
# ============================================================

def send_notifications(all_articles, new_articles, qc_result):
    if SKIP_NOTIFY:
        logger.info("[Step 6] 알림 건너뜀 (SKIP_NOTIFY=true)")
        return False

    logger.info("\n[Step 6] 알림 발송...")
    try:
        import importlib.util
        notifier_path = SCRIPT_DIR / "notifier.py"

        if not notifier_path.exists():
            logger.warning("notifier.py 없음")
            return False

        spec   = importlib.util.spec_from_file_location("notifier", notifier_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        manager = module.NotificationManager()
        data    = manager.prepare_briefing_data(new_articles)
        result  = manager.send_all(data)
        logger.info(f"알림 결과: {result}")
        return True

    except Exception as e:
        logger.error(f"알림 오류: {e}")
        return False


# ============================================================
# MAIN
# ============================================================

def main():
    start_time = datetime.now()

    print("=" * 70)
    print("VIETNAM INFRASTRUCTURE NEWS PIPELINE  v2.0")
    print(f"Started: {start_time}")
    print(f"Hours back: {HOURS_BACK} | Summarizer: {'OFF' if SKIP_SUMMARIZER else 'ON'}")
    print("=" * 70)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Step 1: 기존 DB 로드 ─────────────────────────────────
    print("\n[Step 1] 기존 DB 로드...")
    existing_articles = load_articles_from_excel()
    print(f"기존 기사: {len(existing_articles)}건")

    # ── Step 2: 신규 수집 ────────────────────────────────────
    new_articles, collection_stats = collect_new_articles()
    print(f"신규 수집: {len(new_articles)}건")

    # ── Step 3: AI 요약 ──────────────────────────────────────
    new_articles = run_summarizer(new_articles)

    # ── Step 4: QC ──────────────────────────────────────────
    qc_result, valid_articles = run_quality_control(new_articles, existing_articles)

    # ── Step 5: 대시보드 ─────────────────────────────────────
    all_articles  = existing_articles + valid_articles
    dashboard_ok  = create_dashboard(all_articles)

    # ── Step 6: 알림 ─────────────────────────────────────────
    notify_ok = send_notifications(all_articles, valid_articles, qc_result)

    # ── Step 7: 출력 검증 ────────────────────────────────────
    index_ok     = (OUTPUT_DIR / "index.html").exists()
    dashboard_f  = (OUTPUT_DIR / "vietnam_dashboard.html").exists()

    elapsed = (datetime.now() - start_time).seconds

    # ── 최종 실행 보고서 (Genspark Leader Agent 형식) ─────────
    print("\n" + "=" * 70)
    print("📊 FINAL EXECUTION REPORT")
    print("=" * 70)
    print(f"Pipeline run:       {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Duration:           {elapsed}초")
    print()
    print(f"Articles collected: {len(new_articles)}")

    if collection_stats:
        success_src = sum(1 for s in collection_stats.values() if s.get('status') == 'Success')
        failed_src  = sum(1 for s in collection_stats.values() if s.get('status') == 'Failed')
        print(f"RSS sources:        {success_src} success / {failed_src} failed")

    print()
    print(f"QC pass:            {'✓ PASS' if qc_result['pass'] else '✗ FAIL'}")
    print(f"  valid:            {qc_result['valid_count']}")
    print(f"  rejected:         {qc_result['rejected_count']}")
    if qc_result['warnings']:
        print("  QC warnings:")
        for w in qc_result['warnings']:
            print(f"    {w}")

    # 섹터 분포
    if qc_result['stats'].get('sector_counts'):
        print("\nSector breakdown (new):")
        total_new = qc_result['stats']['total_new'] or 1
        for s, c in sorted(qc_result['stats']['sector_counts'].items(),
                           key=lambda x: -x[1]):
            print(f"  {s:<28} {c:3d}  ({c/total_new:.1%})")

    print()
    print(f"Total DB:           {len(all_articles)}건")
    print(f"Dashboard:          {'✓' if dashboard_ok else '✗'}")
    print(f"  index.html:       {'✓' if index_ok else '✗'}")
    print(f"Notifications:      {'✓' if notify_ok else '건너뜀'}")

    # 전체 상태
    if qc_result['pass'] and dashboard_ok and index_ok:
        overall = "✅ SUCCESS"
    elif dashboard_ok:
        overall = "⚠️  PARTIAL"
    else:
        overall = "❌ FAILED"

    print(f"\nOverall status:     {overall}")
    print("=" * 70)

    return 0 if overall != "❌ FAILED" else 1


if __name__ == "__main__":
    sys.exit(main())
