#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quality_context_agent.py  (SA-6)  v3.0
========================================
Claude Code Agent Team — Sub-Agent 6
역할:
  1. 수집 품질 분석 + Master Plan 정책 연계율 계산
  2. Genspark 결과 피드백 반영 → 다음 수집 개선 권고
  3. 정책 매핑된 기사에 policy_highlight 플래그 → 노란색 표시

[v3.0 변경 2026-04-12]
  - genspark_output.json 읽기 → 누락 소스/섹터 자동 파악
  - policy_highlight 플래그 추가 → Excel 노란색 / 대시보드 뱃지
  - genspark_feedback 섹션을 quality_report.json에 추가
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

# ── 경로 ────────────────────────────────────────────────────
BASE_DIR           = Path(__file__).parent.parent
AGENT_OUT          = BASE_DIR / "data" / "agent_output"
SHARED_DOCS        = BASE_DIR / "docs" / "shared"
COLLECTOR_OUT      = AGENT_OUT / "collector_output.json"
QUALITY_REPORT     = AGENT_OUT / "quality_report.json"
GENSPARK_OUTPUT    = SHARED_DOCS / "genspark_output.json"
POLICY_HIGHLIGHTED = AGENT_OUT / "policy_highlighted_articles.json"

KNOWLEDGE_INDEX_PATHS = [
    SHARED_DOCS / "knowledge_index.json",
    BASE_DIR / "data" / "shared" / "knowledge_index.json",
    AGENT_OUT / "knowledge_index.json",
]

SPECIALIST_SOURCES = {
    "The Investor", "Vietnam Investment Review", "Hanoi Times",
    "VIR", "PV-Tech", "Offshore Energy", "Energy Monitor",
    "Nikkei Asia", "Vietnam Energy", "PetroTimes",
    "Tap chi Nang luong", "Moi truong & Cuoc song",
}

ALL_SECTORS = [
    "Waste Water", "Water Supply/Drainage", "Solid Waste",
    "Power", "Oil & Gas", "Industrial Parks", "Smart City",
]


# ============================================================
# 1. 데이터 로드
# ============================================================

def load_knowledge_index():
    for path in KNOWLEDGE_INDEX_PATHS:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                print(f"  [knowledge_index] {len(data)}개 마스터플랜 로드: {path.name}")
                return data
            except Exception as e:
                print(f"  [WARN] knowledge_index 로드 실패 ({path}): {e}")
    print("  [WARN] knowledge_index.json 없음")
    return []


def load_genspark_output():
    """Genspark 피드백 로드 — 없으면 None 반환"""
    if not GENSPARK_OUTPUT.exists():
        print("  [INFO] genspark_output.json 없음 — 피드백 없이 진행")
        return None
    try:
        with open(GENSPARK_OUTPUT, "r", encoding="utf-8") as f:
            data = json.load(f)
        week = data.get("week", "unknown")
        total = data.get("total_collected", 0)
        print(f"  [genspark] 피드백 로드: {week} | {total}건")
        return data
    except Exception as e:
        print(f"  [WARN] genspark_output.json 로드 실패: {e}")
        return None


# ============================================================
# 2. 정책 매핑
# ============================================================

def match_article_to_policy(article, knowledge_index):
    if not knowledge_index:
        return {"matched": False, "doc_id": None, "relevance": None}

    title   = (article.get("title", "") or "").lower()
    summary = (article.get("summary", "") or "").lower()
    text    = f"{title} {summary}"
    art_sector   = article.get("sector", "")
    art_province = article.get("province", "")

    best_match, best_score = None, 0

    for doc in knowledge_index:
        if art_sector not in doc.get("sectors", []):
            continue
        score = 10
        kw_en = [k.lower() for k in doc.get("keywords_en", [])]
        kw_vi = [k.lower() for k in doc.get("keywords_vi", [])]
        matched_kw = sum(1 for kw in kw_en + kw_vi if kw in text)
        if matched_kw == 0:
            continue
        score += matched_kw * 3
        doc_provinces = [p.lower() for p in doc.get("provinces", [])]
        if art_province and art_province.lower() in doc_provinces:
            score += 5
        if score > best_score:
            best_score, best_match = score, doc

    if best_match and best_score >= 13:
        doc_provinces = [p.lower() for p in best_match.get("provinces", [])]
        relevance = (
            "high" if art_province and art_province.lower() in doc_provinces
            else "medium"
        )
        return {
            "matched":   True,
            "doc_id":    best_match["doc_id"],
            "relevance": relevance,
            "score":     best_score,
            "plan_name": best_match.get("title", ""),
        }
    return {"matched": False, "doc_id": None, "relevance": None}


def calculate_policy_alignment(articles, knowledge_index):
    if not articles or not knowledge_index:
        return {
            "matched_ratio": 0.0, "high_relevance_ratio": 0.0,
            "matched_count": 0, "high_relevance_count": 0,
            "matched_articles": [],
        }
    matched, high_rel = [], []
    for art in articles:
        result = match_article_to_policy(art, knowledge_index)
        if result["matched"]:
            matched.append({
                "title":     art.get("title", "")[:60],
                "sector":    art.get("sector", ""),
                "province":  art.get("province", ""),
                "doc_id":    result["doc_id"],
                "plan_name": result.get("plan_name", ""),
                "relevance": result["relevance"],
                "url":       art.get("url", ""),
            })
            if result["relevance"] == "high":
                high_rel.append(result["doc_id"])

    total = len(articles)
    return {
        "matched_ratio":        round(len(matched) / total, 3) if total else 0.0,
        "high_relevance_ratio": round(len(high_rel) / total, 3) if total else 0.0,
        "matched_count":        len(matched),
        "high_relevance_count": len(high_rel),
        "matched_articles":     matched[:20],
    }


# ============================================================
# 3. 정책 하이라이트 플래그 + JSON 저장
# ============================================================

def tag_policy_highlights(articles, knowledge_index):
    """
    매핑된 기사에 policy_highlight=True 플래그 추가.
    → Excel 업데이터가 이 플래그를 읽어 노란색 처리
    → 대시보드가 이 플래그로 뱃지 표시
    반환: (플래그 추가된 articles, 하이라이트 건수)
    """
    tagged = []
    highlight_count = 0
    for art in articles:
        result = match_article_to_policy(art, knowledge_index)
        if result["matched"]:
            art = dict(art)          # 원본 훼손 방지
            art["policy_highlight"] = True
            art["policy_doc_id"]    = result["doc_id"]
            art["policy_plan_name"] = result.get("plan_name", "")
            art["policy_relevance"] = result["relevance"]
            highlight_count += 1
        else:
            art = dict(art)
            art["policy_highlight"] = False
            art["policy_doc_id"]    = None
            art["policy_plan_name"] = ""
            art["policy_relevance"] = None
        tagged.append(art)
    return tagged, highlight_count


def save_policy_highlighted(tagged_articles, highlight_count):
    """policy_highlighted_articles.json 저장 — Excel 업데이터가 읽음"""
    AGENT_OUT.mkdir(parents=True, exist_ok=True)
    data = {
        "generated_at":    datetime.utcnow().isoformat() + "Z",
        "total_articles":  len(tagged_articles),
        "highlight_count": highlight_count,
        "highlight_ratio": round(highlight_count / max(len(tagged_articles), 1), 3),
        "articles":        tagged_articles,
    }
    with open(POLICY_HIGHLIGHTED, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"  [OK] policy_highlighted_articles.json 저장 ({highlight_count}건 하이라이트)")
    # docs/shared/에도 복사
    try:
        SHARED_DOCS.mkdir(parents=True, exist_ok=True)
        shutil.copy2(POLICY_HIGHLIGHTED, SHARED_DOCS / "policy_highlighted_articles.json")
        print(f"  [OK] docs/shared/policy_highlighted_articles.json 배포")
    except Exception as e:
        print(f"  [WARN] shared 복사 실패: {e}")


# ============================================================
# 4. Genspark 피드백 분석 → 개선 권고
# ============================================================

def analyze_genspark_feedback(claude_articles, genspark_data):
    """
    Genspark 결과와 비교하여 Claude 개선 권고 생성
    반환: feedback dict
    """
    if not genspark_data:
        return {"available": False}

    gs_articles  = genspark_data.get("articles", [])
    gs_week      = genspark_data.get("week", "")
    gs_matching  = genspark_data.get("matching_summary", {})
    gs_quality   = genspark_data.get("quality_summary", {})

    # Claude URL 집합
    claude_urls = {a.get("url", "") for a in claude_articles}

    # Genspark만 수집한 기사 (Claude 미수집)
    gs_only = [a for a in gs_articles if a.get("url", "") not in claude_urls]

    # Genspark만 수집 소스 파악
    gs_only_sources = {}
    for a in gs_only:
        src = a.get("source", "unknown")
        gs_only_sources[src] = gs_only_sources.get(src, 0) + 1

    # Genspark가 커버한 섹터 중 Claude 미수집
    claude_sectors = {a.get("sector", "") for a in claude_articles}
    gs_sectors     = {a.get("sector", "") for a in gs_articles}
    gs_only_sectors = list(gs_sectors - claude_sectors - {""})

    # 정책 연계율 비교
    claude_policy_rate = 0.0   # 현재 실행에서 계산됨
    gs_policy_rate     = gs_matching.get("matched_ratio", 0.0)
    if isinstance(gs_policy_rate, str):
        gs_policy_rate = float(gs_policy_rate.replace("%", "")) / 100

    # 개선 권고 생성
    improvements = []

    if gs_only_sectors:
        improvements.append({
            "priority": "HIGH",
            "type":     "missing_sector",
            "message":  f"Genspark 수집 섹터 중 Claude 미수집: {gs_only_sectors}",
            "action":   f"news_collector.py SECTOR_KEYWORDS에 해당 섹터 키워드 보강 필요",
        })

    top_gs_sources = sorted(gs_only_sources.items(), key=lambda x: -x[1])[:5]
    if top_gs_sources:
        source_names = [s for s, _ in top_gs_sources]
        improvements.append({
            "priority": "MEDIUM",
            "type":     "missing_source",
            "message":  f"Genspark만 수집한 소스 상위 5개: {source_names}",
            "action":   "RSS_FEEDS 또는 specialist_crawler 대상에 추가 검토",
        })

    if gs_policy_rate > claude_policy_rate + 0.1:
        improvements.append({
            "priority": "MEDIUM",
            "type":     "policy_gap",
            "message":  f"정책연계율 차이: Claude {claude_policy_rate:.1%} vs Genspark {gs_policy_rate:.1%}",
            "action":   "knowledge_index.json 키워드 보완 또는 SA-6 매칭 임계값 조정",
        })

    print(f"\n  [Genspark 피드백] 주차: {gs_week}")
    print(f"    Genspark 수집: {len(gs_articles)}건 | Claude 미수집: {len(gs_only)}건")
    print(f"    미수집 섹터: {gs_only_sectors}")
    print(f"    정책연계: Claude {claude_policy_rate:.1%} → Genspark {gs_policy_rate:.1%}")
    for imp in improvements:
        print(f"    [{imp['priority']}] {imp['message']}")

    return {
        "available":           True,
        "week":                gs_week,
        "genspark_total":      len(gs_articles),
        "claude_only_count":   len(claude_urls) - len(claude_urls & {a.get("url","") for a in gs_articles}),
        "genspark_only_count": len(gs_only),
        "genspark_only_sources": dict(top_gs_sources),
        "missing_sectors_in_claude": gs_only_sectors,
        "policy_rate_comparison": {
            "claude":   claude_policy_rate,
            "genspark": gs_policy_rate,
            "gap":      round(gs_policy_rate - claude_policy_rate, 3),
        },
        "improvement_recommendations": improvements,
    }


# ============================================================
# 5. 품질 분석
# ============================================================

def analyze_quality(articles, knowledge_index):
    total = len(articles)
    print(f"[SA-6] 분석 대상 기사: {total}건")

    unclassified = sum(
        1 for a in articles
        if not a.get("province") or a.get("province") in ("Vietnam", "")
    )
    province_rate = round(unclassified / total, 3) if total else 0.0

    specialist_cnt = sum(1 for a in articles if a.get("source", "") in SPECIALIST_SOURCES)
    specialist_ratio = round(specialist_cnt / total, 3) if total else 0.0

    covered_sectors = set(a.get("sector", "") for a in articles if a.get("sector", "") in ALL_SECTORS)
    missing_sectors = [s for s in ALL_SECTORS if s not in covered_sectors]
    sector_ratio    = round(len(covered_sectors) / len(ALL_SECTORS), 3)

    policy = calculate_policy_alignment(articles, knowledge_index)
    grade  = _calc_grade(province_rate, specialist_ratio, sector_ratio, policy["matched_ratio"])

    return {
        "province_unclassified_rate": province_rate,
        "specialist_media_ratio":     specialist_ratio,
        "specialist_count":           specialist_cnt,
        "sector_coverage": {
            "covered": sorted(list(covered_sectors)),
            "missing": missing_sectors,
            "ratio":   sector_ratio,
        },
        "policy_alignment": policy,
        "grade":            grade,
    }


def _calc_grade(province_rate, specialist_ratio, sector_ratio, policy_ratio):
    score = 0
    if province_rate    <= 0.25: score += 1
    if specialist_ratio >= 0.30: score += 1
    if sector_ratio     >= 1.0:  score += 1
    if policy_ratio     >= 0.30: score += 1
    return {4: "A", 3: "B", 2: "C"}.get(score, "D")


def generate_recommendations(metrics):
    recs = []
    if metrics["specialist_media_ratio"] < 0.30:
        recs.append({
            "priority": "HIGH", "metric": "specialist_media_ratio",
            "current": metrics["specialist_media_ratio"], "target": 0.3,
            "action": "전문 RSS 소스 추가 또는 specialist_crawler 정상화 필요",
        })
    missing = metrics["sector_coverage"]["missing"]
    if missing:
        recs.append({
            "priority": "MEDIUM", "metric": "sector_coverage",
            "missing": missing,
            "action": f"{', '.join(missing)} 섹터 RSS/키워드 보강 필요",
        })
    if metrics["policy_alignment"]["matched_ratio"] < 0.30:
        recs.append({
            "priority": "LOW", "metric": "policy_alignment",
            "current": metrics["policy_alignment"]["matched_ratio"],
            "action": "knowledge_index.json 키워드 보강으로 정책 연계율 개선 가능",
        })
    return recs


# ============================================================
# 6. 리포트 저장
# ============================================================

def save_report(report):
    AGENT_OUT.mkdir(parents=True, exist_ok=True)
    with open(QUALITY_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[OK] quality_report.json 저장 완료")
    try:
        SHARED_DOCS.mkdir(parents=True, exist_ok=True)
        shutil.copy2(QUALITY_REPORT, SHARED_DOCS / "quality_report.json")
        print(f"[OK] docs/shared/quality_report.json 업데이트")
    except Exception as e:
        print(f"[WARN] shared 복사 실패: {e}")


def _count_area(articles):
    counts = {}
    for a in articles:
        area = a.get("area", "Other") or "Other"
        counts[area] = counts.get(area, 0) + 1
    return counts


def _calc_vietnam_ratio(articles):
    if not articles:
        return 0.0
    vn = sum(1 for a in articles
             if a.get("province", "") in ("Vietnam", "") or not a.get("province"))
    return round(vn / len(articles), 3)


# ============================================================
# 7. MAIN
# ============================================================

def main():
    # ① collector_output.json 로드
    articles = []
    if COLLECTOR_OUT.exists():
        try:
            with open(COLLECTOR_OUT, "r", encoding="utf-8") as f:
                data = json.load(f)
            articles = data.get("articles", [])
        except Exception as e:
            print(f"[WARN] collector_output.json 로드 실패: {e}")

    # ② knowledge_index.json 로드
    knowledge_index = load_knowledge_index()

    # ③ Genspark 피드백 로드
    genspark_data = load_genspark_output()

    # ④ 품질 분석
    metrics = analyze_quality(articles, knowledge_index)
    recommendations = generate_recommendations(metrics)

    # ⑤ 정책 하이라이트 플래그 추가 + 저장 (노란색 표시용)
    tagged_articles, highlight_count = tag_policy_highlights(articles, knowledge_index)
    save_policy_highlighted(tagged_articles, highlight_count)

    # ⑥ Genspark 피드백 분석
    gs_feedback = analyze_genspark_feedback(articles, genspark_data)

    # ⑦ 출력
    grade = metrics["grade"]
    print()
    print("=" * 55)
    print(f"  품질 등급: {grade}")
    print(f"  Province 미분류율:  {metrics['province_unclassified_rate']:.1%}"
          f"  (목표 ≤25%: {'OK' if metrics['province_unclassified_rate'] <= 0.25 else 'NG'})")
    print(f"  전문미디어 비율:    {metrics['specialist_media_ratio']:.1%}"
          f"  (목표 ≥30%: {'OK' if metrics['specialist_media_ratio'] >= 0.30 else 'NG'})")
    print(f"  섹터 커버리지:      {len(metrics['sector_coverage']['covered'])}/7"
          f"  (미커버: {metrics['sector_coverage']['missing']})")
    print(f"  정책 연계율:        {metrics['policy_alignment']['matched_ratio']:.1%}"
          f"  ({metrics['policy_alignment']['matched_count']}건 / "
          f"고연관 {metrics['policy_alignment']['high_relevance_count']}건)")
    print(f"  정책 하이라이트:    {highlight_count}건 (노란색 표시 대상)")
    print("=" * 55)

    if metrics["policy_alignment"]["matched_articles"]:
        print("\n  정책 연계 기사 (노란색 표시):")
        for m in metrics["policy_alignment"]["matched_articles"][:5]:
            print(f"    [{m['doc_id']}|{m['relevance']}]"
                  f" [{m['sector']}|{m['province']}] {m['title']}")

    if recommendations:
        print(f"\n  자체 권고사항 {len(recommendations)}건:")
        for r in recommendations:
            print(f"  [{r['priority']}] {r['action']}")

    # ⑧ quality_report.json 저장
    report = {
        "generated_at":   datetime.utcnow().isoformat() + "+00:00",
        "total_articles": len(articles),
        "quality_grade":  grade,
        "targets_met": {
            "province_unclassified_le_25pct":
                metrics["province_unclassified_rate"] <= 0.25,
            "specialist_media_ge_30pct":
                metrics["specialist_media_ratio"] >= 0.30,
            "all_7_sectors_covered":
                len(metrics["sector_coverage"]["missing"]) == 0,
            "policy_alignment_ge_30pct":
                metrics["policy_alignment"]["matched_ratio"] >= 0.30,
        },
        "metrics": {
            "province_unclassified_rate":  metrics["province_unclassified_rate"],
            "specialist_media_ratio":      metrics["specialist_media_ratio"],
            "sector_coverage":             metrics["sector_coverage"],
            "area_distribution":           _count_area(articles),
            "policy_alignment":            metrics["policy_alignment"],
            "policy_highlight_count":      highlight_count,
            "collector_flags": {
                "vietnam_ratio":    _calc_vietnam_ratio(articles),
                "missing_provinces": [],
            },
        },
        "knowledge_index_loaded": len(knowledge_index),
        "recommendations":        recommendations,
        "genspark_feedback":      gs_feedback,   # ← Genspark 비교 결과 추가
    }
    save_report(report)


if __name__ == "__main__":
    main()
