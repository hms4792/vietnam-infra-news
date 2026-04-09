#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quality_context_agent.py  (SA-6)
==================================
Claude Code Agent Team — Sub-Agent 6
역할: 수집 품질 분석 + Master Plan 정책 연계율 계산

[v2.0 주요 변경 2026-04-09]
  knowledge_index.json 기반 정책 연계 매칭 로직 추가
  → Genspark와 동일한 기준으로 정책 연계율 계산
  → 기사 제목/요약의 키워드가 마스터플랜 keywords와 일치하면 매칭

[출력]
  data/agent_output/quality_report.json  → docs/shared/ 로 export
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

# ── 경로 설정 ───────────────────────────────────────────────
BASE_DIR        = Path(__file__).parent.parent
AGENT_OUT       = BASE_DIR / "data" / "agent_output"
SHARED_DOCS     = BASE_DIR / "docs" / "shared"
COLLECTOR_OUT   = AGENT_OUT / "collector_output.json"
QUALITY_REPORT  = AGENT_OUT / "quality_report.json"

# knowledge_index.json 탐색 경로 (Claude 생성 or Genspark 공유)
KNOWLEDGE_INDEX_PATHS = [
    SHARED_DOCS / "knowledge_index.json",          # docs/shared/ (Genspark 공유)
    BASE_DIR / "data" / "shared" / "knowledge_index.json",
    AGENT_OUT / "knowledge_index.json",
]

# ── 전문미디어 소스 목록 ─────────────────────────────────────
SPECIALIST_SOURCES = {
    "The Investor", "Vietnam Investment Review", "Hanoi Times",
    "VIR", "PV-Tech", "Offshore Energy", "Energy Monitor",
    "Nikkei Asia", "Vietnam Energy", "PetroTimes",
    "Tap chi Nang luong", "Moi truong & Cuoc song",
}

# ── 7개 섹터 ─────────────────────────────────────────────────
ALL_SECTORS = [
    "Waste Water", "Water Supply/Drainage", "Solid Waste",
    "Power", "Oil & Gas", "Industrial Parks", "Smart City",
]


# ============================================================
# 1. knowledge_index.json 로드
# ============================================================

def load_knowledge_index():
    """Genspark 공유 knowledge_index.json 로드"""
    for path in KNOWLEDGE_INDEX_PATHS:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                print(f"  [knowledge_index] {len(data)}개 마스터플랜 로드: {path.name}")
                return data
            except Exception as e:
                print(f"  [WARN] knowledge_index 로드 실패 ({path}): {e}")
    print("  [WARN] knowledge_index.json 없음 → 정책 연계율 계산 불가")
    return []


# ============================================================
# 2. 정책 연계 매칭
# ============================================================

def match_article_to_policy(article, knowledge_index):
    """
    기사 1건을 knowledge_index의 마스터플랜과 매칭.
    매칭 기준:
      1) 섹터 일치 (기사 sector ∈ 마스터플랜 sectors)
      2) 키워드 일치 (기사 제목/요약에 마스터플랜 keywords_en/vi 중 하나 포함)
      3) Province 일치 (선택적 — 일치하면 high_relevance)

    반환: {matched: bool, doc_id: str, relevance: "high"/"medium"/None}
    """
    if not knowledge_index:
        return {"matched": False, "doc_id": None, "relevance": None}

    title   = (article.get("title", "") or "").lower()
    summary = (article.get("summary", "") or "").lower()
    text    = f"{title} {summary}"

    art_sector   = article.get("sector", "")
    art_province = article.get("province", "")

    best_match = None
    best_score = 0

    for doc in knowledge_index:
        score = 0

        # 섹터 일치 확인
        doc_sectors = doc.get("sectors", [])
        if art_sector not in doc_sectors:
            continue
        score += 10

        # 키워드 매칭
        kw_en = [k.lower() for k in doc.get("keywords_en", [])]
        kw_vi = [k.lower() for k in doc.get("keywords_vi", [])]
        all_kw = kw_en + kw_vi

        matched_kw = sum(1 for kw in all_kw if kw in text)
        if matched_kw == 0:
            continue
        score += matched_kw * 3

        # Province 일치 (보너스)
        doc_provinces = [p.lower() for p in doc.get("provinces", [])]
        if art_province and art_province.lower() in doc_provinces:
            score += 5

        if score > best_score:
            best_score = score
            best_match = doc

    if best_match and best_score >= 13:  # 섹터+키워드 1개 이상 필수
        # Province까지 일치하면 high_relevance
        doc_provinces = [p.lower() for p in best_match.get("provinces", [])]
        relevance = (
            "high"
            if art_province and art_province.lower() in doc_provinces
            else "medium"
        )
        return {
            "matched":    True,
            "doc_id":     best_match["doc_id"],
            "relevance":  relevance,
            "score":      best_score,
        }

    return {"matched": False, "doc_id": None, "relevance": None}


def calculate_policy_alignment(articles, knowledge_index):
    """전체 기사에 대한 정책 연계율 계산"""
    if not articles or not knowledge_index:
        return {
            "matched_ratio":       0.0,
            "high_relevance_ratio": 0.0,
            "matched_count":       0,
            "high_relevance_count": 0,
            "matched_articles":    [],
        }

    matched      = []
    high_rel     = []

    for art in articles:
        result = match_article_to_policy(art, knowledge_index)
        if result["matched"]:
            matched.append({
                "title":     art.get("title", "")[:60],
                "sector":    art.get("sector", ""),
                "province":  art.get("province", ""),
                "doc_id":    result["doc_id"],
                "relevance": result["relevance"],
            })
            if result["relevance"] == "high":
                high_rel.append(result["doc_id"])

    total = len(articles)
    return {
        "matched_ratio":        round(len(matched) / total, 3) if total else 0.0,
        "high_relevance_ratio": round(len(high_rel) / total, 3) if total else 0.0,
        "matched_count":        len(matched),
        "high_relevance_count": len(high_rel),
        "matched_articles":     matched[:10],  # 상위 10건만 저장
    }


# ============================================================
# 3. 품질 분석
# ============================================================

def analyze_quality(articles, knowledge_index):
    """수집 기사 품질 분석 + 정책 연계율 계산"""
    total = len(articles)
    print(f"[SA-6] 분석 대상 기사: {total}건")

    # Province 미분류율
    unclassified = sum(
        1 for a in articles
        if not a.get("province") or a.get("province") in ("Vietnam", "")
    )
    province_rate = round(unclassified / total, 3) if total else 0.0

    # 전문미디어 비율
    specialist_cnt = sum(
        1 for a in articles
        if a.get("source", "") in SPECIALIST_SOURCES
    )
    specialist_ratio = round(specialist_cnt / total, 3) if total else 0.0

    # 섹터 커버리지
    covered_sectors = set(
        a.get("sector", "") for a in articles
        if a.get("sector", "") in ALL_SECTORS
    )
    missing_sectors = [s for s in ALL_SECTORS if s not in covered_sectors]
    sector_ratio    = round(len(covered_sectors) / len(ALL_SECTORS), 3)

    # 정책 연계율 (knowledge_index 매칭)
    policy = calculate_policy_alignment(articles, knowledge_index)

    # 품질 등급 결정
    grade = _calc_grade(
        province_rate, specialist_ratio, sector_ratio, policy["matched_ratio"]
    )

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
    """
    품질 등급 계산
    A: 모든 목표 달성
    B: 3개 달성
    C: 2개 달성
    D: 1개 이하 달성
    """
    score = 0
    if province_rate   <= 0.25: score += 1
    if specialist_ratio >= 0.30: score += 1
    if sector_ratio    >= 1.0:  score += 1
    if policy_ratio    >= 0.30: score += 1

    return {4: "A", 3: "B", 2: "C"}.get(score, "D")


# ============================================================
# 4. 권고사항
# ============================================================

def generate_recommendations(metrics):
    recs = []

    if metrics["specialist_media_ratio"] < 0.30:
        recs.append({
            "priority": "HIGH",
            "metric":   "specialist_media_ratio",
            "current":  metrics["specialist_media_ratio"],
            "target":   0.3,
            "action":   "전문 RSS 소스 추가 또는 specialist_crawler 정상화 필요"
                        " (theinvestor.vn, vir.com.vn HTML 크롤링)",
        })

    missing = metrics["sector_coverage"]["missing"]
    if missing:
        recs.append({
            "priority": "MEDIUM",
            "metric":   "sector_coverage",
            "missing":  missing,
            "action":   f"{', '.join(missing)} 섹터 RSS/키워드 보강 필요",
        })

    if metrics["policy_alignment"]["matched_ratio"] < 0.30:
        recs.append({
            "priority": "LOW",
            "metric":   "policy_alignment",
            "current":  metrics["policy_alignment"]["matched_ratio"],
            "action":   "knowledge_index.json 확장 또는 키워드 보강으로 정책 연계율 개선 가능",
        })

    return recs


# ============================================================
# 5. 리포트 저장
# ============================================================

def save_report(report):
    AGENT_OUT.mkdir(parents=True, exist_ok=True)
    with open(QUALITY_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[OK] quality_report.json 저장 완료")

    # docs/shared/ 로 즉시 복사
    try:
        SHARED_DOCS.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(QUALITY_REPORT, SHARED_DOCS / "quality_report.json")
        print(f"[OK] docs/shared/quality_report.json 업데이트")
    except Exception as e:
        print(f"[WARN] shared 복사 실패: {e}")


# ============================================================
# 6. MAIN
# ============================================================

def main():
    # collector_output.json 로드
    articles = []
    if COLLECTOR_OUT.exists():
        try:
            with open(COLLECTOR_OUT, "r", encoding="utf-8") as f:
                data = json.load(f)
            articles = data.get("articles", [])
        except Exception as e:
            print(f"[WARN] collector_output.json 로드 실패: {e}")

    # knowledge_index.json 로드 (Genspark 공유)
    knowledge_index = load_knowledge_index()

    # 품질 분석
    metrics = analyze_quality(articles, knowledge_index)
    recommendations = generate_recommendations(metrics)

    # 등급 출력
    grade = metrics["grade"]
    print()
    print("=" * 50)
    print(f"  품질 등급: {grade}")
    print(f"  Province 미분류율:  "
          f"{metrics['province_unclassified_rate']:.1%}"
          f"  (목표 ≤25%: {'OK' if metrics['province_unclassified_rate'] <= 0.25 else 'NG'})")
    print(f"  전문미디어 비율:    "
          f"{metrics['specialist_media_ratio']:.1%}"
          f"  (목표 ≥30%: {'OK' if metrics['specialist_media_ratio'] >= 0.30 else 'NG'})")
    print(f"  섹터 커버리지:      "
          f"{len(metrics['sector_coverage']['covered'])}/7"
          f"  (미커버: {metrics['sector_coverage']['missing']})")
    print(f"  정책 연계율:        "
          f"{metrics['policy_alignment']['matched_ratio']:.1%}"
          f"  (매칭 {metrics['policy_alignment']['matched_count']}건"
          f" / 고연관 {metrics['policy_alignment']['high_relevance_count']}건)")
    print("=" * 50)

    if metrics["policy_alignment"]["matched_articles"]:
        print("\n  정책 연계 기사 (상위):")
        for m in metrics["policy_alignment"]["matched_articles"][:5]:
            print(f"    [{m['doc_id']}|{m['relevance']}] "
                  f"[{m['sector']}|{m['province']}] {m['title']}")

    if recommendations:
        print(f"\n  권고사항 {len(recommendations)}건:")
        for r in recommendations:
            print(f"  [{r['priority']}] {r['action']}")

    # 리포트 저장
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
            "province_unclassified_rate":
                metrics["province_unclassified_rate"],
            "specialist_media_ratio":
                metrics["specialist_media_ratio"],
            "sector_coverage":
                metrics["sector_coverage"],
            "area_distribution":
                _count_area(articles),
            "policy_alignment":
                metrics["policy_alignment"],
            "collector_flags": {
                "vietnam_ratio": _calc_vietnam_ratio(articles),
                "missing_provinces": [],
            },
        },
        "knowledge_index_loaded": len(knowledge_index),
        "recommendations": recommendations,
    }
    save_report(report)


def _count_area(articles):
    counts = {}
    for a in articles:
        area = a.get("area", "Other") or "Other"
        counts[area] = counts.get(area, 0) + 1
    return counts


def _calc_vietnam_ratio(articles):
    if not articles:
        return 0.0
    vn = sum(
        1 for a in articles
        if a.get("province", "") in ("Vietnam", "") or not a.get("province")
    )
    return round(vn / len(articles), 3)


if __name__ == "__main__":
    main()
