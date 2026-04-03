"""
SA-6: Quality Context Agent
수집된 기사의 품질 지표를 측정하고 MI Reporting Team 공유용 리포트를 생성한다.

입력: data/agent_output/collector_output.json
      data/agent_output/knowledge_output.json  (없으면 건너뜀)
출력: data/agent_output/quality_report.json
"""

import os
import json
from datetime import datetime, timezone

BASE_DIR        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENT_OUT_DIR   = os.path.join(BASE_DIR, "data", "agent_output")
COLLECTOR_JSON  = os.path.join(AGENT_OUT_DIR, "collector_output.json")
KNOWLEDGE_JSON  = os.path.join(AGENT_OUT_DIR, "knowledge_output.json")
QUALITY_JSON    = os.path.join(AGENT_OUT_DIR, "quality_report.json")

# ── 목표 기준 (WHAT_I_NEED.md) ───────────────────────────────────────────────
TARGET_PROVINCE_UNCLASSIFIED_MAX = 0.25   # 미분류율 25% 이하
TARGET_SPECIALIST_MEDIA_MIN      = 0.30   # 전문미디어 비율 30% 이상

# 7개 대상 섹터 (WHO_I_AM.md)
TARGET_SECTORS = [
    "Waste Water",
    "Water Supply/Drainage",
    "Solid Waste",
    "Power",
    "Oil & Gas",
    "Industrial Parks",
    "Smart City",
]

# Area 매핑
SECTOR_AREA = {
    "Waste Water":           "Environment",
    "Water Supply/Drainage": "Environment",
    "Solid Waste":           "Environment",
    "Power":                 "Energy Develop.",
    "Oil & Gas":             "Energy Develop.",
    "Industrial Parks":      "Urban Develop.",
    "Smart City":            "Urban Develop.",
}

# 전문미디어 판별 — RSS 소스명 기반 (news_collector.py RSS_FEEDS 기준)
SPECIALIST_SOURCES = {
    # 에너지 전문
    "PV-Tech",
    "Bao Dau Tu - Energy",
    "Vietnam Energy alt",
    # 환경 전문
    "VietnamPlus - Moi truong",
    "Nhandan - Moi truong",
    "Kinhtemoitruong",
    "Baotainguyenmoitruong",
    "Moitruong Net",
    "Congnghiepmoitruong",
    # 건설/도시 전문
    "Bao Xay Dung",
    "Tap chi Xay dung",
    # 산업단지 전문
    "Baobacgiang English",
}


# ── 지표 계산 ─────────────────────────────────────────────────────────────────

def calc_province_unclassified(articles):
    """Province 미분류율: 비어 있는 province 비율."""
    if not articles:
        return 0.0
    missing = sum(1 for a in articles if not a.get("province"))
    return round(missing / len(articles), 3)


def calc_specialist_ratio(articles):
    """전문미디어 비율: SPECIALIST_SOURCES에 속하는 기사 비율."""
    if not articles:
        return 0.0
    specialist = sum(1 for a in articles if a.get("source", "") in SPECIALIST_SOURCES)
    return round(specialist / len(articles), 3)


def calc_sector_coverage(articles):
    """7개 목표 섹터 커버리지."""
    found = {a.get("sector") for a in articles if a.get("sector") in TARGET_SECTORS}
    missing = [s for s in TARGET_SECTORS if s not in found]
    return {
        "covered":  sorted(found),
        "missing":  missing,
        "ratio":    round(len(found) / len(TARGET_SECTORS), 3),
    }


def calc_area_distribution(articles):
    """Area별 기사 분포."""
    counts = {"Environment": 0, "Energy Develop.": 0, "Urban Develop.": 0, "Other": 0}
    for a in articles:
        area = SECTOR_AREA.get(a.get("sector", ""), "Other")
        counts[area] += 1
    return counts


def calc_policy_alignment(knowledge_data, total_articles):
    """지식베이스 매칭률 (knowledge_agent 결과 활용)."""
    if not knowledge_data or total_articles == 0:
        return {"matched_ratio": 0.0, "high_relevance_ratio": 0.0}
    matched       = knowledge_data.get("matched_count", 0)
    high_rel      = knowledge_data.get("high_relevance_count", 0)
    return {
        "matched_ratio":       round(matched / total_articles, 3),
        "high_relevance_ratio": round(high_rel / total_articles, 3),
    }


def make_recommendations(metrics):
    """품질 지표를 바탕으로 개선 권고사항 생성."""
    recs = []

    prov_rate = metrics["province_unclassified_rate"]
    if prov_rate > TARGET_PROVINCE_UNCLASSIFIED_MAX:
        recs.append({
            "priority": "HIGH",
            "metric":   "province_unclassified_rate",
            "current":  prov_rate,
            "target":   TARGET_PROVINCE_UNCLASSIFIED_MAX,
            "action":   "province_keywords.py 보강 또는 뉴스 본문 스캔 확대 필요",
        })

    spec_rate = metrics["specialist_media_ratio"]
    if spec_rate < TARGET_SPECIALIST_MEDIA_MIN:
        recs.append({
            "priority": "HIGH",
            "metric":   "specialist_media_ratio",
            "current":  spec_rate,
            "target":   TARGET_SPECIALIST_MEDIA_MIN,
            "action":   "전문 RSS 소스 추가 또는 Google News 전문 쿼리 확대 필요",
        })

    missing_sectors = metrics["sector_coverage"]["missing"]
    if missing_sectors:
        recs.append({
            "priority": "MEDIUM",
            "metric":   "sector_coverage",
            "missing":  missing_sectors,
            "action":   f"{', '.join(missing_sectors)} 섹터 RSS/키워드 보강 필요",
        })

    alignment = metrics["policy_alignment"]
    if alignment["matched_ratio"] < 0.30:
        recs.append({
            "priority": "LOW",
            "metric":   "policy_alignment",
            "current":  alignment["matched_ratio"],
            "action":   "knowledge_index.json 확장으로 정책 연계율 개선 가능",
        })

    return recs


def grade(metrics):
    """전체 품질 등급 산출: A/B/C/D."""
    score = 0

    # Province 미분류율 (30점)
    prov = metrics["province_unclassified_rate"]
    if prov <= 0.15:
        score += 30
    elif prov <= 0.25:
        score += 20
    elif prov <= 0.40:
        score += 10

    # 전문미디어 비율 (30점)
    spec = metrics["specialist_media_ratio"]
    if spec >= 0.50:
        score += 30
    elif spec >= 0.30:
        score += 20
    elif spec >= 0.15:
        score += 10

    # 섹터 커버리지 (25점)
    cov = metrics["sector_coverage"]["ratio"]
    score += int(cov * 25)

    # 정책 연계율 (15점)
    pol = metrics["policy_alignment"]["matched_ratio"]
    if pol >= 0.60:
        score += 15
    elif pol >= 0.30:
        score += 10
    elif pol >= 0.10:
        score += 5

    if score >= 85:
        return "A"
    elif score >= 70:
        return "B"
    elif score >= 50:
        return "C"
    else:
        return "D"


# ── 메인 ─────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(AGENT_OUT_DIR, exist_ok=True)

    # 1. collector_output.json 읽기
    if not os.path.exists(COLLECTOR_JSON):
        print("[WARN] collector_output.json 없음 — news_collector.py 먼저 실행하세요.")
        articles     = []
        quality_flags = {}
    else:
        with open(COLLECTOR_JSON, "r", encoding="utf-8") as f:
            collector_data = json.load(f)
        articles      = collector_data.get("articles", [])
        quality_flags = collector_data.get("quality_flags", {})

    # 2. knowledge_output.json 읽기 (선택)
    knowledge_data = None
    if os.path.exists(KNOWLEDGE_JSON):
        with open(KNOWLEDGE_JSON, "r", encoding="utf-8") as f:
            knowledge_data = json.load(f)

    total = len(articles)
    print(f"[SA-6] 분석 대상 기사: {total}건")

    # 3. 지표 계산
    metrics = {
        "province_unclassified_rate": calc_province_unclassified(articles),
        "specialist_media_ratio":     calc_specialist_ratio(articles),
        "sector_coverage":            calc_sector_coverage(articles),
        "area_distribution":          calc_area_distribution(articles),
        "policy_alignment":           calc_policy_alignment(knowledge_data, total),
        # collector_output의 quality_flags를 그대로 포함
        "collector_flags": quality_flags,
    }

    # 4. 품질 등급 + 권고사항
    quality_grade   = grade(metrics)
    recommendations = make_recommendations(metrics)

    # 5. 목표 달성 여부 요약
    targets_met = {
        "province_unclassified_le_25pct": (
            metrics["province_unclassified_rate"] <= TARGET_PROVINCE_UNCLASSIFIED_MAX
        ),
        "specialist_media_ge_30pct": (
            metrics["specialist_media_ratio"] >= TARGET_SPECIALIST_MEDIA_MIN
        ),
        "all_7_sectors_covered": (
            len(metrics["sector_coverage"]["missing"]) == 0
        ),
    }

    # 6. 결과 저장
    report = {
        "generated_at":    datetime.now(timezone.utc).isoformat(),
        "total_articles":  total,
        "quality_grade":   quality_grade,
        "targets_met":     targets_met,
        "metrics":         metrics,
        "recommendations": recommendations,
    }

    with open(QUALITY_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # 7. 콘솔 요약
    print(f"\n{'='*50}")
    print(f"  품질 등급: {quality_grade}")
    print(f"  Province 미분류율: {metrics['province_unclassified_rate']:.1%}"
          f"  (목표 ≤25%: {'OK' if targets_met['province_unclassified_le_25pct'] else 'NG'})")
    print(f"  전문미디어 비율:   {metrics['specialist_media_ratio']:.1%}"
          f"  (목표 ≥30%: {'OK' if targets_met['specialist_media_ge_30pct'] else 'NG'})")
    cov = metrics["sector_coverage"]
    print(f"  섹터 커버리지:     {len(cov['covered'])}/7"
          f"  (미커버: {cov['missing'] or '없음'})")
    print(f"  정책 연계율:       {metrics['policy_alignment']['matched_ratio']:.1%}")
    print(f"{'='*50}")

    if recommendations:
        print(f"\n  권고사항 {len(recommendations)}건:")
        for r in recommendations:
            print(f"  [{r['priority']}] {r['action']}")

    print(f"\n[OK] quality_report.json 저장 완료")


if __name__ == "__main__":
    main()
