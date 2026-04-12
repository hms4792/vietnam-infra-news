#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
new_masterplans_patch.py
========================
신규 마스터플랜 2건 추가 패치 스크립트
  - VN-PWR-PDP8 (베트남 국가전력개발계획 8차)
  - VN-ENV-IND-1894 (베트남 환경산업 발전 프로그램)

실행: python3 scripts/new_masterplans_patch.py
"""

import json
from pathlib import Path

BASE = Path(__file__).parent.parent

# ── 신규 마스터플랜 2건 정의 ──────────────────────────────────

NEW_PLANS = {
    "VN-PWR-PDP8": {
        "name_ko": "베트남 국가전력개발계획 8차 (PDP8) 2021-2030",
        "name_en": "Vietnam National Power Development Plan 8 (PDP8) 2021-2030",
        "sector": "Power",
        "area": "Energy Develop.",
        "match_threshold": 60,
        "target_2030": "120 GW 총 발전설비 용량",
        "budget_usd": "약 134.7십억달러",
        "keywords": [
            "power development plan", "pdp8", "electricity grid",
            "renewable energy", "wind power", "solar power",
            "lng terminal", "lng power plant", "transmission line",
            "quy hoach dien", "nang luong tai tao", "phong dien",
            "dien mat troi", "duong day dien"
        ],
        "provinces": [
            "Quang Ninh", "Gia Lai", "Binh Thuan", "Ninh Thuan",
            "Ca Mau", "Khanh Hoa", "Binh Dinh", "Quang Binh",
            "Vietnam"
        ],
        "key_projects": [
            "하이퐁 LNG 발전소 1.2GW",
            "Ninh Thuan 풍력단지 3.5GW",
            "Gia Lai 태양광 군집",
            "남북 500kV 송전선 확충"
        ],
        "business_opportunity": "LNG 터미널 EPC, 풍력 터빈 공급, 송전 인프라, 스마트그리드"
    },
    "VN-ENV-IND-1894": {
        "name_ko": "베트남 환경산업 발전 프로그램 (Decision 1894/QĐ-TTg)",
        "name_en": "Vietnam Environmental Industry Development Program (Decision 1894)",
        "sector": "Solid Waste",
        "area": "Environment",
        "match_threshold": 35,
        "target_2030": "환경산업 GDP 대비 1.5% 달성",
        "budget_usd": "약 2.5억달러",
        "keywords": [
            "environmental industry", "waste treatment", "waste-to-energy",
            "solid waste management", "recycling plant", "circular economy",
            "pollution control", "environmental services", "hazardous waste",
            "cong nghiep moi truong", "xu ly chat thai", "rac thai",
            "tai che", "kinh te tuan hoan", "lo dot rac"
        ],
        "provinces": [
            "Ho Chi Minh City", "Hanoi", "Da Nang", "Hue",
            "Binh Duong", "Dong Nai", "Hai Phong", "Vietnam"
        ],
        "key_projects": [
            "TP.HCM 폐기물 에너지화 플랜트 1,000톤/일",
            "하노이 Nam Son 매립지 현대화",
            "Da Nang 재활용 산업단지",
            "Binh Duong 유해폐기물 처리센터"
        ],
        "business_opportunity": "WtE(폐기물 에너지화) EPC, 재활용 설비, 유해폐기물 처리 기술"
    }
}


def patch_knowledge_index():
    """docs/shared/knowledge_index.json에 신규 마스터플랜 추가"""
    path = BASE / "docs" / "shared" / "knowledge_index.json"
    
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"version": "2.0", "masterplans": {}, "sectors": []}
    
    masterplans = data.get("masterplans", {})
    added = []
    
    for plan_id, plan_data in NEW_PLANS.items():
        if plan_id not in masterplans:
            masterplans[plan_id] = {
                "id": plan_id,
                "name_ko": plan_data["name_ko"],
                "name_en": plan_data["name_en"],
                "sector": plan_data["sector"],
                "area": plan_data["area"],
                "match_threshold": plan_data["match_threshold"],
                "target_2030": plan_data["target_2030"],
                "budget": plan_data["budget_usd"],
                "keywords": plan_data["keywords"],
                "provinces": plan_data["provinces"],
                "key_projects": plan_data["key_projects"],
                "business_opportunity": plan_data["business_opportunity"]
            }
            added.append(plan_id)
            print(f"  [추가] {plan_id}: {plan_data['name_ko']}")
        else:
            print(f"  [스킵] {plan_id}: 이미 존재")
    
    # 버전 업
    old_version = data.get("version", "2.0")
    data["version"] = "2.1"
    data["masterplans"] = masterplans
    data["total_masterplans"] = len(masterplans)
    
    from datetime import datetime
    data["updated_at"] = datetime.now().strftime("%Y-%m-%d")
    
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"  [OK] knowledge_index.json v{old_version} → v2.1 ({len(masterplans)}개 마스터플랜)")
    return added


def patch_master_rules():
    """docs/shared/MASTER_RULES.json에 신규 마스터플랜 추가"""
    path = BASE / "docs" / "shared" / "MASTER_RULES.json"
    
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"master_plans": [], "sectors_priority": [], "updated_at": ""}
    
    existing_ids = {p["id"] for p in data.get("master_plans", [])}
    added = []
    
    for plan_id, plan_data in NEW_PLANS.items():
        if plan_id not in existing_ids:
            data["master_plans"].append({
                "id": plan_id,
                "name_ko": plan_data["name_ko"],
                "sector": plan_data["sector"],
                "search_keywords": plan_data["keywords"][:6],  # 상위 6개만
                "target_provinces": plan_data["provinces"]
            })
            added.append(plan_id)
            print(f"  [추가] MASTER_RULES: {plan_id}")
    
    from datetime import datetime
    data["updated_at"] = datetime.now().strftime("%Y-%m-%d")
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"  [OK] MASTER_RULES.json 업데이트 완료")
    return added


if __name__ == "__main__":
    print("=== 신규 마스터플랜 패치 시작 ===\n")
    print("[1] knowledge_index.json 패치")
    patch_knowledge_index()
    print("\n[2] MASTER_RULES.json 패치")
    patch_master_rules()
    print("\n=== 패치 완료 ===")
    print("다음 단계: quality_context_agent.py와 news_collector.py도 수정 필요")
