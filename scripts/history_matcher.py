"""
History Matcher — 역사 기사 전용 심층 매칭 엔진
============================================================
역사 DB (주로 베트남어 + 영어) 기사에 특화된 매칭.

주요 차이점 vs agent_pipeline MASTERPLANS:
  - 베트남어 키워드 풍부 (실제 기사에서 추출)
  - 단어 단위(단일 키워드) 매칭 허용 (복합어 요구하지 않음)
  - 섹터 기반 강화 매칭 (섹터 + 키워드 조합)
  - exclude_if는 정확한 패턴만 (오탐 최소화)
  - threshold를 섹터 매칭 여부에 따라 동적으로 낮춤
"""

from collections import Counter

# ══════════════════════════════════════════════════════════════════
# 플랜별 매칭 룰 — 역사 기사 전용 (영어 + 베트남어 + 한국어)
# ══════════════════════════════════════════════════════════════════
HISTORY_PLAN_RULES = {

    "VN-PDP8-RENEWABLE": {
        "sector_tags": ["Power", "Power & Energy", "Energy Develop."],
        "keywords": [
            # 영어
            "pdp8", "pdp 8", "power development plan", "electricity generation",
            "power plant", "solar farm", "wind farm", "wind energy", "solar energy",
            "renewable energy", "offshore wind", "hydropower", "power capacity",
            "power grid", "transmission", "evn ", "electricity vietnam",
            # 베트남어
            "quy hoạch điện", "phát triển điện", "nhà máy điện", "điện gió",
            "điện mặt trời", "năng lượng tái tạo", "lưới điện", "truyền tải điện",
            "tua bin gió", "điện lực", "evn", "tập đoàn điện",
        ],
        "hard_exclude": ["xe điện", "vinfast ev", "electric vehicle", "trạm sạc"],
        "sector_boost": True,
        "min_score": 1,
    },

    "VN-ENV-IND-1894": {
        "sector_tags": ["Solid Waste", "Environment"],
        "keywords": [
            # 영어
            "solid waste", "waste management", "waste treatment", "waste-to-energy",
            "wte", "incineration", "landfill", "garbage", "municipal waste",
            "industrial waste", "pollution control", "air quality", "emission",
            "circular economy", "epr", "recycling facility", "environmental",
            "decision 1894", "1894",
            # 베트남어
            "rác thải", "xử lý rác", "chất thải rắn", "bãi rác", "đốt rác",
            "nhà máy xử lý rác", "ô nhiễm", "chất lượng không khí", "khí thải",
            "kinh tế tuần hoàn", "tái chế", "rác sinh hoạt", "chất thải công nghiệp",
            "môi trường", "xử lý chất thải", "lò đốt", "phân loại rác",
        ],
        "hard_exclude": ["nước thải", "wastewater plant", "cấp nước", "water supply plant"],
        "sector_boost": True,
        "min_score": 1,
    },

    # ── 하노이 도시개발 그룹 (Decision 1668/QD-TTg 2024.12.27) ──────
    "HN-URBAN-NORTH": {
        "sector_tags": ["Urban Development"],
        "keywords": [
            "dong anh", "me linh", "soc son", "noi bai airport", "brg smart city",
            "brg sumitomo", "north hanoi smart city", "co loa urban", "nhat tan noi bai",
            "northern city hanoi", "hanoi northern district",
            "đông anh", "mê linh", "sóc sơn", "nội bài mở rộng",
            "thành phố thông minh đông anh", "đô thị phía bắc hà nội",
            "khu đô thị bắc hà nội", "thành phố phía bắc hà nội",
        ],
        "hard_exclude": ["mekong", "ho chi minh", "da nang", "wastewater"],
        "sector_boost": False, "min_score": 1,
    },
    "HN-URBAN-WEST": {
        "sector_tags": ["Urban Development"],
        "keywords": [
            "hoa lac", "hoa lac hi-tech", "hoa lac high tech", "western hanoi",
            "xuan mai", "son tay hanoi", "thach that", "quoc oai",
            "lang hoa lac", "tien xuan", "sj group hanoi", "hanoi western city",
            "hòa lạc", "khu công nghệ cao hòa lạc", "xuân mai", "sơn tây",
            "thạch thất", "quốc oai", "đô thị tây hà nội", "thành phố phía tây",
        ],
        "hard_exclude": ["mekong", "ho chi minh", "da nang", "wastewater"],
        "sector_boost": False, "min_score": 1,
    },
    "HN-URBAN-INFRA": {
        "sector_tags": ["Urban Development", "Transport"],
        "keywords": [
            "hanoi metro", "hanoi urban rail", "hanoi ring road", "ring road 4 hanoi",
            "ring road 3.5", "red river hanoi", "red river corridor",
            "to lich river", "hanoi bridge", "hanoi master plan",
            "hanoi flooding", "hanoi traffic", "hanoi urban development",
            "decision 1668", "hanoi general planning",
            "metro hà nội", "đường sắt đô thị hà nội", "vành đai 4 hà nội",
            "vành đai 3.5 hà nội", "sông hồng hà nội", "sông tô lịch",
            "quy hoạch hà nội", "cầu qua sông hồng", "ùn tắc hà nội",
            "ngập lụt hà nội", "quy hoạch thủ đô",
        ],
        "hard_exclude": ["ho chi minh metro", "mekong", "wastewater treatment plant"],
        "sector_boost": False, "min_score": 1,
    },

    "VN-TRAN-2055": {
        "sector_tags": ["Transport", "Urban Development"],
        "keywords": [
            # 영어
            "highway", "expressway", "road construction", "bridge", "airport",
            "seaport", "railway", "high-speed rail", "transport infrastructure",
            "ring road", "national road", "freeway", "toll road", "overpass",
            "long thanh", "lach huyen", "north-south",
            # 베트남어
            "đường cao tốc", "cầu", "sân bay", "cảng biển", "đường sắt",
            "hạ tầng giao thông", "đường quốc lộ", "khởi công", "thông xe",
            "xây dựng cầu", "nút giao", "đường vành đai", "long thành",
            "tuyến đường", "giao thông", "hầm", "cảng hàng không",
        ],
        "hard_exclude": ["tàu điện ngầm", "metro line", "xe điện"],
        "sector_boost": True,
        "min_score": 1,
    },

    "VN-URB-METRO-2030": {
        "sector_tags": ["Smart City", "Urban Development"],
        "keywords": [
            "metro", "subway", "urban rail", "mrt", "light rail", "tram",
            "tàu điện ngầm", "đường sắt đô thị", "metro hà nội", "metro hcm",
            "cát linh", "nhổn", "bến thành", "ben thanh",
        ],
        "hard_exclude": ["highway km", "đường cao tốc km"],
        "sector_boost": False,
        "min_score": 1,
    },

    "VN-PDP8-LNG": {
        "sector_tags": ["Oil & Gas", "Power"],
        "keywords": [
            # 영어
            "lng", "liquefied natural gas", "gas pipeline", "gas terminal",
            "gas-fired", "gas power", "natural gas", "regasification", "fsru",
            "gas infrastructure", "lng terminal", "gas import",
            # 베트남어
            "khí lng", "khí thiên nhiên", "đường ống khí", "kho cảng lng",
            "nhà máy điện khí", "nhập khẩu lng", "tái hóa khí", "pvgas",
            "khí đốt", "xây dựng cảng lng",
        ],
        "hard_exclude": ["xe điện", "điện mặt trời gw", "điện gió gw"],
        "sector_boost": True,
        "min_score": 1,
    },

    "VN-WAT-RESOURCES": {
        "sector_tags": ["Water Supply", "Water Supply/Drainage"],
        "keywords": [
            # 영어 — 수자원 관리·유역·수안보
            "water resources", "river basin", "water security", "water resource management",
            "dam", "reservoir", "irrigation", "flood control", "drought relief",
            "saltwater intrusion", "hydropower dam", "dike", "embankment", "canal",
            "groundwater depletion", "water distribution", "water resource plan",
            "decision 1622", "mekong water", "red river basin",
            # 베트남어
            "tài nguyên nước", "lưu vực sông", "an ninh nguồn nước",
            "đập", "hồ chứa", "thủy lợi", "lũ lụt", "hạn hán", "đê",
            "kênh tưới", "lưu vực", "công trình thủy lợi",
            "nước ngầm", "xâm nhập mặn", "ngập", "quy hoạch tài nguyên nước",
        ],
        "hard_exclude": ["nước thải", "wastewater treatment plant", "cấp nước đô thị"],
        "sector_boost": True,
        "min_score": 1,
    },

    "VN-PDP8-NUCLEAR": {
        "sector_tags": ["Power"],
        "keywords": [
            "nuclear", "nuclear power", "ninh thuan", "hạt nhân", "điện hạt nhân",
            "nhà máy điện hạt nhân", "smr", "small modular reactor",
            "hydrogen", "green hydrogen", "hydro xanh", "năng lượng hydrogen",
            "tái khởi động điện hạt nhân",
        ],
        "hard_exclude": ["coal", "solar only", "wind only"],
        "sector_boost": False,
        "min_score": 1,
    },

    "VN-PDP8-COAL": {
        "sector_tags": ["Power"],
        "keywords": [
            # 영어
            "coal phase", "coal retirement", "jetp", "coal closure",
            "coal transition", "coal to biomass", "biomass cofiring",
            "ammonia cofiring", "coal plant decommission", "coal fired power",
            "coal power station", "coal plant age", "coal phase-out",
            "fair energy transition", "just energy transition",
            # 베트남어
            "nhiệt điện than", "đóng cửa nhà máy than", "chuyển đổi năng lượng công bằng",
            "than đá", "điện than", "chuyển đổi than", "nhà máy than", "phát thải than",
        ],
        "hard_exclude": ["electric vehicle", "wastewater", "solar farm", "wind farm"],
        "sector_boost": True,
        "min_score": 1,
    },

    "VN-PDP8-GRID": {
        "sector_tags": ["Power"],
        "keywords": [
            # 영어
            "smart grid", "transmission line", "500kv", "220kv", "substation",
            "power grid upgrade", "hvdc", "high voltage", "grid expansion",
            "direct power purchase", "dppa", "electricity market reform",
            "power grid investment", "evn transmission", "north-south 500kv",
            # 베트남어
            "lưới điện thông minh", "đường dây 500kv", "đường dây 220kv",
            "trạm biến áp", "hệ thống truyền tải", "lưới điện quốc gia",
            "thị trường điện", "truyền tải điện", "nâng cấp lưới điện",
        ],
        "hard_exclude": ["electric vehicle", "wastewater", "highway"],
        "sector_boost": True,
        "min_score": 1,
    },

    "VN-EV-2030": {
        "sector_tags": ["Industrial Parks"],   # VinFast 관련 기사가 Industrial Parks로 분류됨
        "keywords": [
            "electric vehicle", "vinfast", "ev ", " ev,", "ev sales",
            "charging station", "electric bus", "electric motorcycle",
            "xe điện", "vinfast", "trạm sạc", "xe buýt điện", "xe máy điện",
            "ô tô điện", "phương tiện điện",
        ],
        "hard_exclude": [
            "power development plan", "pdp8", "solar farm gw",
            "lng terminal", "wastewater plant", "highway expressway",
        ],
        "sector_boost": False,
        "min_score": 1,
    },

    "VN-CARBON-2050": {
        "sector_tags": ["Carbon & Climate"],
        "keywords": [
            "carbon neutral", "net zero", "carbon credit", "ndc",
            "greenhouse gas", "carbon market", "climate finance",
            "trung hòa carbon", "tín chỉ carbon", "phát thải ròng",
            "biến đổi khí hậu", "giảm phát thải", "carbon",
        ],
        "hard_exclude": ["electric vehicle model launch"],
        "sector_boost": True,
        "min_score": 1,
    },

    "VN-PDP8-HYDROGEN": {
        "sector_tags": ["Power", "Oil & Gas"],
        "keywords": [
            # 영어
            "green hydrogen", "hydrogen energy", "hydrogen power", "hydrogen fuel",
            "hydrogen ready", "hydrogen-ready lng", "ammonia fuel", "ammonia power",
            "renewable energy export", "re export", "energy export singapore",
            "energy export malaysia", "new energy export", "inter-regional re center",
            "offshore wind export", "re industrial hub",
            # 베트남어
            "hydro xanh", "năng lượng hydrogen", "xuất khẩu điện tái tạo",
            "trung tâm năng lượng tái tạo", "xuất khẩu điện", "điện tái tạo xuất",
        ],
        "hard_exclude": ["electric vehicle", "wastewater", "lng import terminal only"],
        "sector_boost": False,
        "min_score": 1,
    },

    "VN-WW-2030": {
        "sector_tags": ["Waste Water"],
        "keywords": [
            # 영어
            "wastewater", "waste water", "wwtp", "sewage", "sewer",
            "wastewater treatment", "effluent", "sanitation",
            # 베트남어
            "nước thải", "xử lý nước thải", "nhà máy xử lý nước thải",
            "hệ thống thoát nước", "cống thoát", "trạm xử lý nước thải",
            "thoát nước", "bùn thải", "yen xa", "yên xá",
        ],
        "hard_exclude": ["water supply only", "cấp nước sạch only"],
        "sector_boost": True,
        "min_score": 1,
    },

    "VN-WAT-URBAN": {
        "sector_tags": ["Water Supply", "Water Supply/Drainage"],
        "keywords": [
            # 영어 — 도시 상수도 인프라
            "water supply plant", "water treatment plant", "clean water supply",
            "water supply system", "water pipeline", "water network", "drinking water",
            "water loss reduction", "non-revenue water", "safe water program",
            "urban water supply", "water supply coverage", "water meter",
            "smart water", "water tariff reform", "water utility",
            "decision 1566 water", "decision 1929 water",
            # 베트남어
            "nhà máy nước", "nhà máy xử lý nước", "cấp nước đô thị",
            "mạng lưới cấp nước", "thất thoát nước", "nước sạch đô thị",
            "cấp nước an toàn", "đường ống cấp nước", "nước máy",
            "công ty cấp nước", "hệ thống cấp nước đô thị",
        ],
        "hard_exclude": ["nước thải", "wastewater treatment", "irrigation dam",
                         "water resources basin management"],
        "sector_boost": True,
        "min_score": 1,
    },
    "VN-WAT-RURAL": {
        "sector_tags": ["Water Supply", "Water Supply/Drainage"],
        "keywords": [
            # 영어 — 농촌 상수도·위생
            "rural water supply", "rural sanitation", "rural clean water",
            "commune water supply", "ethnic minority water", "highland water supply",
            "village water system", "rural waterworks", "rural wash",
            "decision 1978", "mard water supply", "rural drinking water",
            # 베트남어
            "cấp nước nông thôn", "vệ sinh nông thôn", "nước sạch nông thôn",
            "cấp nước vùng cao", "cấp nước miền núi", "nước sinh hoạt nông thôn",
            "hệ thống cấp nước nông thôn", "vệ sinh môi trường nông thôn",
        ],
        "hard_exclude": ["urban water supply plant", "wastewater treatment plant"],
        "sector_boost": True,
        "min_score": 1,
    },

    "VN-MEKONG-DELTA-2030": {
        "sector_tags": ["Water Supply", "Transport", "Environment"],
        "keywords": [
            # English
            "mekong delta", "mekong delta development", "mekong delta planning",
            "mekong delta infrastructure", "mekong delta agriculture",
            "mekong delta transport", "mekong delta flood", "mekong delta climate",
            "mekong delta saltwater intrusion", "mekong delta expressway",
            "mekong delta logistics", "mekong delta urban", "can tho development",
            "dong thap", "an giang", "kien giang", "ca mau", "soc trang",
            "bac lieu", "hau giang", "vinh long", "long an delta", "tien giang",
            "ben tre", "tra vinh", "decision 287",
            # Vietnamese
            "đồng bằng sông cửu long", "quy hoạch vùng đbscl", "phát triển đbscl",
            "hạ tầng đồng bằng", "giao thông đồng bằng sông cửu long",
            "nông nghiệp đồng bằng", "cần thơ phát triển",
            "đồng tháp", "an giang", "kiên giang", "cà mau", "sóc trăng",
            "hậu giang", "vĩnh long", "tiền giang", "bến tre", "trà vinh",
        ],
        "hard_exclude": ["wastewater treatment plant bid", "solid waste tender",
                         "upper mekong dam", "mekong river dam china"],
        "sector_boost": False,
        "min_score": 1,
    },
    "VN-SWM-NATIONAL-2030": {
        "sector_tags": ["Solid Waste"],
        "keywords": [
            # English
            "solid waste", "municipal solid waste", "msw", "waste-to-energy", "wte",
            "incineration plant", "landfill", "composting", "hazardous waste",
            "medical waste", "industrial solid waste", "construction waste",
            "recycling plant", "plastic waste", "waste sorting", "waste collection",
            "garbage treatment", "waste disposal", "solid waste management",
            "epr extended producer", "waste processing facility",
            # Vietnamese
            "chất thải rắn", "rác thải", "xử lý rác", "đốt rác phát điện",
            "bãi chôn lấp", "phân loại rác", "thu gom rác", "tái chế",
            "rác thải công nghiệp", "rác thải y tế", "rác thải nguy hại",
            "nhà máy xử lý rác", "lò đốt rác", "rác thải nhựa",
        ],
        "hard_exclude": ["nước thải", "wastewater treatment plant",
                         "water supply pipeline", "environmental technology industry",
                         "environmental equipment"],
        "sector_boost": True,
        "min_score": 1,
    },

    "VN-SC-2030": {
        "sector_tags": ["Smart City"],
        "keywords": [
            "smart city", "digital city", "iot", "e-government", "smart urban",
            "thành phố thông minh", "đô thị thông minh", "chuyển đổi số",
            "chính phủ điện tử", "thành phố số", "smart traffic",
            "digital transformation", "5g vietnam",
        ],
        "hard_exclude": ["power plant construction", "lng terminal deal"],
        "sector_boost": True,
        "min_score": 1,
    },

    "VN-IP-NORTH-2030": {
        "sector_tags": ["Industrial Parks"],
        "keywords": [
            "industrial park", "industrial zone", "vsip", "economic zone",
            "fdi zone", "manufacturing hub", "industrial cluster",
            "khu công nghiệp", "khu kinh tế", "khu chế xuất",
            "vsip", "khu công nghiệp mới", "đầu tư fdi",
            "khởi công khu công nghiệp",
        ],
        "hard_exclude": ["wastewater only", "power plant only"],
        "sector_boost": True,
        "min_score": 1,
    },

    "VN-OG-2030": {
        "sector_tags": ["Oil & Gas"],
        "keywords": [
            "oil field", "crude oil", "petroleum", "oil exploration",
            "oil refinery", "offshore oil", "petrovietnam", "pvn",
            "dầu khí", "khai thác dầu", "lọc dầu", "dung quất",
            "petrovietnam", "mỏ dầu", "thăm dò dầu khí",
        ],
        "hard_exclude": ["lng only", "gas power only"],
        "sector_boost": True,
        "min_score": 1,
    },
}


def match_history_article(article: dict) -> list:
    """
    역사 기사 1건에 대해 매칭 플랜 ID 리스트 반환.
    섹터 태그 + 키워드 조합으로 매칭.
    """
    text = (
        article.get("title", "") + " " +
        article.get("content", "")[:500] + " " +
        article.get("summary_en", "") + " " +
        article.get("summary_ko", "")
    ).lower()

    sector = article.get("sector", "")
    matched = []

    for plan_id, rules in HISTORY_PLAN_RULES.items():
        # 1) hard_exclude 체크 (정확한 패턴)
        excluded = False
        for ex in rules.get("hard_exclude", []):
            # "only" 접미사는 단독 매칭을 의미 (무시)
            if ex.endswith(" only"):
                continue
            if ex.lower() in text:
                excluded = True
                break
        if excluded:
            continue

        # 2) 키워드 점수
        kw_score = sum(1 for kw in rules["keywords"] if kw.lower() in text)

        # 3) 섹터 매칭 보너스
        sector_match = sector in rules.get("sector_tags", [])
        if rules.get("sector_boost") and sector_match:
            # 섹터 일치 + 키워드 1개 이상 → 통과
            if kw_score >= 1:
                matched.append(plan_id)
                continue
        elif sector_match and not rules.get("sector_boost"):
            # 섹터만 일치해도 키워드 1개 충족 시 통과
            if kw_score >= 1:
                matched.append(plan_id)
                continue

        # 4) 섹터 무관, 키워드만으로 매칭
        if kw_score >= rules.get("min_score", 1) + 1:  # 섹터 없으면 +1 요구
            matched.append(plan_id)

    return matched


def rematch_history_db(history_db_path: str) -> dict:
    """
    history_db.json 전체를 재매칭하여 저장.
    반환: 업데이트된 db
    """
    import json
    from pathlib import Path

    with open(history_db_path, encoding="utf-8") as f:
        db = json.load(f)

    articles = db.get("articles", {})
    matched_count = 0
    plan_counter = Counter()

    for uid, art in articles.items():
        new_mp = match_history_article(art)
        art["matched_plans"] = new_mp
        if new_mp:
            matched_count += 1
            for pid in new_mp:
                plan_counter[pid] += 1
            best = new_mp[0]
            art["policy_context"] = {
                "plan_id": best,
                "plan_name": best,
                "score": sum(1 for kw in HISTORY_PLAN_RULES[best]["keywords"]
                             if kw.lower() in (art.get("title","") + " " + art.get("content","")[:300]).lower())
            }
        else:
            art["policy_context"] = None

    db["articles"] = articles
    db["last_updated"] = __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M")

    with open(history_db_path, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

    total = len(articles)
    print(f"\n📊 재매칭 결과:")
    print(f"  전체: {total}건")
    print(f"  매칭됨: {matched_count}건 ({matched_count/total*100:.1f}%)")
    print(f"\n  플랜별:")
    for pid, cnt in plan_counter.most_common():
        print(f"    {pid:25s}: {cnt:4d}건")

    return db


if __name__ == "__main__":
    import sys
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/home/work/claw/config/history_db.json"
    print(f"역사 DB 재매칭: {db_path}")
    rematch_history_db(db_path)
