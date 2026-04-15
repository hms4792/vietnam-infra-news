"""
Relevance Filter & Feedback Loop — Vietnam Infrastructure Pipeline
============================================================
두 가지 역할:
  1. run_relevance_rerank(articles)
     - 각 마스터플랜의 실제 목적을 기준으로 기사 관련성 재평가
     - 필수(MUST) 키워드 미포함 기사 제거
     - 경쟁(CONFLICT) 키워드 포함 기사 강등
     - 관련성 점수 재산출 후 threshold 이상만 유지

  2. build_feedback_blocklist(rejected_articles)
     - 제거된 기사의 패턴을 분석해 FEEDBACK_BLOCKLIST.json에 저장
     - agent_pipeline.py의 수집 단계에서 이 파일을 참조해 미리 걸러냄

사용:
    from relevance_filter import run_relevance_rerank, build_feedback_blocklist
"""

import json, re
from datetime import datetime
from pathlib import Path
from collections import Counter

BASE_DIR = Path(__file__).resolve().parent.parent

# ══════════════════════════════════════════════════════════════════
# 마스터플랜 관련성 룰셋 (엄격 버전)
# 각 플랜별:
#   must_any  : 이 중 최소 1개 포함 (없으면 즉시 제거)
#   must_n    : must_keywords에서 최소 N개 포함
#   must_keywords: 핵심 키워드 리스트
#   boost     : 있으면 점수 +2 (강한 연관)
#   conflict  : 있으면 점수 -3 (다른 플랜 기사일 가능성 높음)
#   min_score : 최종 점수 미달 시 제거
# ══════════════════════════════════════════════════════════════════
PLAN_RULES = {
    "VN-PDP8-RENEWABLE": {
        "desc": "베트남 전력 발전원 및 송전 인프라 계획 (PDP8). 발전소 신설·확장, 재생에너지 용량, 전력망이 핵심.",
        "must_any": ["pdp8", "pdp 8", "power development plan", "electricity generation",
                     "power plant", "wind farm", "solar farm", "power capacity",
                     "발전소", "전력개발계획", "재생에너지 발전", "풍력단지", "태양광단지"],
        "boost":    ["pdp8", "power development plan", "gw", "mw capacity", "offshore wind",
                     "solar capacity", "transmission line", "500kv", "grid expansion"],
        "conflict": ["electric vehicle", "ev charger", "charging station", "vinfast",
                     "wastewater", "sewage", "highway", "expressway", "metro", "subway",
                     "nuclear plant", "oil field", "crude oil"],
        "min_score": 3,
    },
    "VN-ENV-IND-1894": {
        "desc": "환경산업 발전 프로그램 — 폐기물 처리, 오염 제어, 환경 모니터링 산업화.",
        "must_any": ["decision 1894", "1894", "environmental industry", "pollution control",
                     "solid waste management", "industrial waste", "환경산업", "폐기물관리",
                     "waste-to-energy", "wte plant", "epr", "extended producer"],
        "boost":    ["decision 1894", "waste to energy", "air quality monitoring",
                     "industrial pollution", "circular economy"],
        "conflict": ["wastewater treatment", "sewage plant", "wwtp", "water supply",
                     "electric vehicle", "ev", "power plant"],
        "min_score": 2,
    },
    "VN-TRAN-2055": {
        "desc": "국가 교통인프라 마스터플랜 2055 — 고속도로, 철도, 항만, 공항 건설.",
        "must_any": ["highway", "expressway", "high-speed rail", "railway", "port", "airport",
                     "bridge construction", "road project", "transport infrastructure",
                     "고속도로", "고속철도", "철도", "항만", "공항", "교통인프라",
                     "ring road", "north-south expressway", "long thanh"],
        "boost":    ["expressway km", "ring road", "long thanh airport", "lach huyen",
                     "high-speed rail", "north-south railway", "moc bai", "cau"],
        "conflict": ["electric vehicle", "ev charging", "power plant", "solar farm",
                     "wastewater", "nuclear", "smart city digital"],
        "min_score": 2,
    },
    "VN-URB-METRO-2030": {
        "desc": "도시철도·메트로 개발계획 — 하노이·호치민 지하철, LRT 노선.",
        "must_any": ["metro", "subway", "urban rail", "mrt", "tram line", "light rail",
                     "metro line", "지하철", "도시철도", "메트로", "경전철"],
        "boost":    ["metro line", "hanoi metro", "hcmc metro", "ben thanh",
                     "nhon ga ha noi", "cat linh"],
        "conflict": ["highway", "airport", "seaport", "electric vehicle", "power plant"],
        "min_score": 2,
    },
    "VN-PDP8-LNG": {
        "desc": "LNG 가스 인프라 — 수입 터미널, 파이프라인, LNG 복합화력 발전소.",
        "must_any": ["lng", "liquefied natural gas", "gas terminal", "gas pipeline",
                     "regasification", "fsru", "gas power plant", "lng power",
                     "가스 터미널", "lng 터미널", "천연가스", "가스복합화력"],
        "boost":    ["lng terminal", "lng import", "fsru", "regasification",
                     "mtpa", "ca mau lng", "son my", "thi vai"],
        "conflict": ["electric vehicle", "ev", "solar farm", "wind farm",
                     "wastewater", "highway", "metro", "crude oil", "oil field"],
        "min_score": 2,
    },
    "VN-WAT-RESOURCES": {
        "desc": "수자원 개발 마스터플랜 — 댐, 저수지, 홍수 관리, 농업 관개.",
        "must_any": ["reservoir", "dam construction", "irrigation", "flood control",
                     "drought", "water resource", "hydropower dam", "river basin",
                     "저수지", "댐", "홍수", "관개", "수자원", "하천유역"],
        "boost":    ["mekong river", "red river", "dam project", "irrigation canal",
                     "flood season", "drought relief"],
        "conflict": ["wastewater treatment", "sewage", "water supply plant",
                     "electric vehicle", "power plant", "lng"],
        "min_score": 2,
    },
    "VN-PDP8-NUCLEAR": {
        "desc": "원자력·신에너지 개발계획 — 원전 재추진(닌투안), SMR, 그린수소.",
        "must_any": ["nuclear", "nuclear power plant", "npp", "ninh thuan",
                     "green hydrogen", "smr", "small modular reactor",
                     "원자력", "원전", "핵발전소", "닌투안", "수소", "그린수소"],
        "boost":    ["ninh thuan", "nuclear revival", "smr pilot",
                     "hydrogen production", "green ammonia"],
        "conflict": ["solar farm", "wind farm", "coal plant", "lng power",
                     "electric vehicle", "highway", "wastewater"],
        "min_score": 2,
    },
    "VN-PDP8-COAL": {
        "desc": "석탄화력 단계적 폐지 — JETP, 공정에너지전환, 노후 석탄발전 조기 폐쇄.",
        "must_any": ["coal phase", "coal retirement", "coal plant closure", "jetp",
                     "just energy transition", "coal power decommission",
                     "탈석탄", "석탄발전 폐지", "에너지전환파트너십", "석탄 조기폐쇄"],
        "boost":    ["jetp", "coal phase-out", "just transition", "early retirement coal"],
        "conflict": ["electric vehicle", "lng terminal", "solar farm",
                     "wastewater", "highway"],
        "min_score": 2,
    },
    "VN-PDP8-GRID": {
        "desc": "스마트그리드 고도화 — 송전망 확충, 변전소, 전력 디지털화.",
        "must_any": ["smart grid", "transmission grid", "power grid", "substation",
                     "500kv", "grid upgrade", "power network", "transmission line",
                     "스마트그리드", "송전망", "변전소", "전력망 고도화"],
        "boost":    ["500kv line", "grid digitization", "smart meter",
                     "transmission expansion", "substation upgrade"],
        "conflict": ["electric vehicle", "ev charging", "wastewater", "highway",
                     "nuclear", "coal plant", "solar farm capacity"],
        "min_score": 2,
    },
    "VN-EV-2030": {
        "desc": "전기차·친환경 모빌리티 2030 — VinFast, EV 충전소, 전기버스 전환.",
        "must_any": ["electric vehicle", "ev ", "vinfast", "e-mobility",
                     "charging station", "electric bus", "ev charger",
                     "전기차", "ev충전", "vinfast", "전기버스", "전동킥보드"],
        "boost":    ["vinfast", "ev sales", "charging infrastructure",
                     "electric motorcycle", "ev subsidy", "battery swap"],
        "conflict": ["power plant", "solar farm", "wind energy", "pdp8",
                     "lng terminal", "wastewater", "highway km", "nuclear power",
                     "oil field", "coal plant"],
        "min_score": 3,
    },
    # ── 하노이 도시개발 그룹 (Decision 1668/QD-TTg 2024.12.27) ──────────
    "HN-URBAN-NORTH": {
        "desc": "하노이 북부 신도시 — 동아인·BRG스마트시티·노이바이공항.",
        "must_any": ["dong anh","me linh","soc son","brg smart city","brg sumitomo",
                     "north hanoi smart city","nhat tan noi bai","co loa urban",
                     "đông anh","mê linh","sóc sơn","thành phố thông minh đông anh",
                     "đô thị phía bắc hà nội"],
        "boost":    ["brg smart city","north hanoi","noi bai expansion","co loa"],
        "conflict": ["mekong delta","ho chi minh city development","da nang",
                     "wastewater plant","power plant mw"],
        "min_score": 1,
    },
    "HN-URBAN-WEST": {
        "desc": "하노이 서부 과학기술도시 — 호아락 하이테크파크·선따이.",
        "must_any": ["hoa lac","hoa lac hi-tech","hoa lac high tech",
                     "western hanoi","xuan mai","son tay hanoi","thach that",
                     "tien xuan","sj group hanoi","hòa lạc","khu công nghệ cao hòa lạc",
                     "xuân mai","sơn tây","đô thị tây hà nội"],
        "boost":    ["hoa lac hi-tech","hoa lac park","western hanoi city"],
        "conflict": ["mekong delta","ho chi minh","wastewater treatment plant"],
        "min_score": 1,
    },
    "HN-URBAN-INFRA": {
        "desc": "하노이 도시 인프라 — 메트로·링로드·홍강·도심재개발.",
        "must_any": ["hanoi metro","hanoi ring road","ring road 4 hanoi","ring road 3.5",
                     "red river corridor hanoi","to lich river","hanoi bridge",
                     "hanoi master plan","decision 1668",
                     "metro hà nội","vành đai 4 hà nội","sông hồng hà nội",
                     "quy hoạch hà nội","sông tô lịch"],
        "boost":    ["ring road 4","red river hanoi","hanoi 2030 plan"],
        "conflict": ["ho chi minh metro","mekong","wastewater treatment plant mw"],
        "min_score": 1,
    },
    # ── 홍강 델타 지역 개발 ──────────────────────────────────────────────
    "VN-RED-RIVER-2030": {
        "desc": "홍강 델타 — 11개 성시 종합 지역개발 마스터플랜.",
        "must_any": ["red river delta","red river region","hung yen","bac ninh development",
                     "thai nguyen development","vinh phuc development","ha nam development",
                     "northern vietnam development","hanoi ha phong economic corridor",
                     "vùng đồng bằng sông hồng","kinh tế vùng bắc bộ","hưng yên","bắc ninh"],
        "boost":    ["red river delta","hung yen industrial","bac ninh samsung"],
        "conflict": ["mekong delta","southern vietnam","wastewater treatment"],
        "min_score": 1,
    },
    # ── 농촌 상수도·위생 ──────────────────────────────────────────────────
    "VN-WAT-RURAL": {
        "desc": "농촌 상수도·위생 국가전략 — 6,200만 농촌 인구.",
        "must_any": ["rural water supply","rural water","rural sanitation",
                     "rural clean water","rural drinking water","nước sạch nông thôn",
                     "vệ sinh nông thôn","cấp nước nông thôn","mard water"],
        "boost":    ["rural water program","nrwss","mard water supply"],
        "conflict": ["urban water supply","city water treatment plant",
                     "municipal wastewater","industrial"],
        "min_score": 1,
    },
    "VN-CARBON-2050": {
        "desc": "탄소중립 2050 — NDC, 탄소크레딧, 온실가스 감축, 기후금융.",
        "must_any": ["carbon neutral", "net zero", "carbon credit", "ndc",
                     "greenhouse gas reduction", "carbon market", "climate finance",
                     "탄소중립", "넷제로", "탄소크레딧", "온실가스", "기후금융"],
        "boost":    ["carbon credit trading", "ndc target", "climate finance",
                     "emission reduction", "paris agreement"],
        "conflict": ["electric vehicle model", "lng import", "coal power",
                     "wastewater plant", "highway project"],
        "min_score": 2,
    },
    "VN-PDP8-HYDROGEN": {
        "desc": "베트남 LNG 허브 전략 — LNG 수입 다각화, FSRU, 허브 포지셔닝.",
        "must_any": ["lng hub", "lng import", "fsru", "floating storage",
                     "lng bunkering", "lng trade", "lng supply chain",
                     "lng허브", "lng 수입", "부유식lng"],
        "boost":    ["lng hub", "regional lng", "fsru vessel", "lng bunkering port"],
        "conflict": ["electric vehicle", "highway", "metro", "wastewater",
                     "nuclear", "solar capacity"],
        "min_score": 2,
    },
    "VN-WW-2030": {
        "desc": "국가 수처리 마스터플랜 — WWTP 신설·확장, 하수관로, 슬러지 처리.",
        "must_any": ["wastewater treatment", "wwtp", "sewage treatment", "sewage plant",
                     "wastewater plant", "sewer", "sanitation plant",
                     "하수처리", "폐수처리", "하수도", "wwtp", "정화조"],
        "boost":    ["yen xa", "binh tan", "wwtp capacity", "sewerage network",
                     "sludge treatment", "jica wastewater"],
        "conflict": ["water supply", "dam", "irrigation", "electric vehicle",
                     "power plant", "highway", "industrial waste"],
        "min_score": 2,
    },
    "VN-WAT-URBAN": {
        "desc": "북부 상수도 인프라 — 정수장, 상수관망, 클린워터 공급.",
        "must_any": ["water supply", "clean water supply", "drinking water",
                     "water treatment plant", "tap water network", "water utility",
                     "상수도", "정수장", "수돗물", "급수"],
        "boost":    ["water supply plant", "clean water project", "nrw reduction"],
        "conflict": ["wastewater", "sewage", "irrigation", "electric vehicle",
                     "power plant"],
        "min_score": 2,
    },
    "VN-MEKONG-DELTA-2030": {
        "desc": "메콩델타 지역개발 마스터플랜 — Decision 287/616. 농업경제, 교통, 기후변화적응, 도시개발.",
        "must_any": ["mekong delta", "đồng bằng sông cửu long", "đbscl",
                     "can tho", "dong thap", "an giang", "kien giang", "ca mau",
                     "soc trang", "bac lieu", "hau giang", "vinh long",
                     "long an mekong", "tien giang", "ben tre",
                     "메콩델타", "메콩강 삼각주", "껀터 개발"],
        "boost":    ["mekong delta development plan", "decision 287", "decision 616 mekong",
                     "quy hoach vung dbscl", "mekong delta expressway", "mekong delta logistics"],
        "conflict": ["mekong river dam china", "upper mekong laos",
                     "wastewater plant contract bid", "solid waste bid"],
        "min_score": 2,
    },
    "VN-SWM-NATIONAL-2030": {
        "desc": "전국 고형폐기물 통합관리 전략 — Decision 491/2018. WtE·매립·재활용·산업/의료폐기물.",
        "must_any": ["solid waste", "municipal waste", "waste-to-energy", "wte plant",
                     "incineration plant", "landfill vietnam", "composting plant",
                     "hazardous waste", "medical waste", "waste collection rate",
                     "garbage treatment", "recycling plant", "plastic waste",
                     "waste sorting", "chất thải rắn", "rác thải", "xử lý rác",
                     "đốt rác", "bãi chôn lấp", "고형폐기물", "쓰레기 처리",
                     "WtE 발전소", "매립지 폐쇄", "소각로"],
        "boost":    ["decision 491 solid waste", "national solid waste strategy",
                     "wte capacity mw", "landfill closure", "epr plastic"],
        "conflict": ["wastewater treatment plant", "sewage plant",
                     "water supply pipeline", "environmental technology industry",
                     "environmental equipment manufacturing"],
        "min_score": 2,
    },
    "VN-SC-2030": {
        "desc": "스마트시티 국가전략 — IoT 도시인프라, 전자정부, AI 교통관제, 5G.",
        "must_any": ["smart city", "digital city", "smart infrastructure",
                     "e-government", "iot city", "ai traffic", "5g network",
                     "스마트시티", "디지털시티", "스마트인프라", "전자정부"],
        "boost":    ["thu duc smart city", "uocc", "smart traffic", "digital twin city"],
        "conflict": ["electric vehicle sales", "power plant", "lng terminal",
                     "wastewater plant", "highway construction"],
        "min_score": 2,
    },
    "VN-IP-NORTH-2030": {
        "desc": "북부 산업단지 개발 — VSIP, 하이퐁·빈즈엉·꽝닌 경제특구, FDI 유치.",
        "must_any": ["industrial park", "industrial zone", "economic zone", "vsip",
                     "fdi park", "manufacturing zone", "industrial estate",
                     "산업단지", "경제특구", "공업단지", "vsip"],
        "boost":    ["vsip", "hai phong industrial", "quang ninh industrial",
                     "north vietnam factory", "fdi manufacturing"],
        "conflict": ["wastewater", "power plant", "electric vehicle",
                     "smart city", "highway km"],
        "min_score": 2,
    },
    "VN-OG-2030": {
        "desc": "석유가스 개발 계획 — 해상유전, 원유 생산, 정유 시설.",
        "must_any": ["oil field", "crude oil", "petroleum", "oil exploration",
                     "oil refinery", "offshore oil", "petrovietnam",
                     "석유", "원유", "유전", "해상유전", "정유", "페트로베트남"],
        "boost":    ["petrovietnam", "block oil", "offshore exploration",
                     "crude production", "oil refinery expansion"],
        "conflict": ["electric vehicle", "lng terminal", "wastewater",
                     "solar farm", "wind farm", "highway"],
        "min_score": 2,
    },
}


def _score_article(article: dict, plan_id: str) -> dict:
    """
    기사 관련성 점수 산출
    반환: {"score": int, "pass": bool, "reason": str}
    """
    rules = PLAN_RULES.get(plan_id)
    if not rules:
        return {"score": 0, "pass": False, "reason": "no_rules"}

    # 텍스트 조합 (소문자)
    text = " ".join([
        article.get("title", ""),
        article.get("content", "")[:800],
        article.get("summary_ko", "") or "",
        article.get("summary_en", "") or "",
        article.get("sector", ""),
        article.get("area", ""),
    ]).lower()

    # 1) MUST_ANY 체크 — 없으면 즉시 실패
    must_any_hit = any(kw.lower() in text for kw in rules["must_any"])
    if not must_any_hit:
        return {"score": 0, "pass": False, "reason": "missing_must_any"}

    # 2) BOOST 점수
    score = 1  # must_any 통과 기본점
    boost_hits = [kw for kw in rules["boost"] if kw.lower() in text]
    score += len(boost_hits)

    # 3) CONFLICT 감점
    conflict_hits = [kw for kw in rules["conflict"] if kw.lower() in text]
    score -= len(conflict_hits) * 1  # 충돌 키워드당 -1

    # 4) 임계값 판정
    passed = score >= rules["min_score"]
    reason = "ok" if passed else f"low_score({score}<{rules['min_score']})"
    if conflict_hits and not passed:
        reason = f"conflict_dominant({','.join(conflict_hits[:2])})"

    return {
        "score": score,
        "pass": passed,
        "reason": reason,
        "boost_hits": boost_hits,
        "conflict_hits": conflict_hits,
    }


def run_relevance_rerank(articles: list) -> dict:
    """
    모든 기사의 matched_plans를 재평가.
    - 관련성 낮은 플랜은 matched_plans에서 제거
    - relevance_score 필드 추가
    - 각 플랜 내에서 발행일 최신순 정렬

    반환: {
        "articles": [...],          # 재평가된 전체 기사
        "rejected_plan_links": [...], # 제거된 (article_id, plan_id, reason)
        "stats": {...}
    }
    """
    import ast

    rejected_links = []
    reranked = []
    plan_buckets = {pid: [] for pid in PLAN_RULES}

    for art in articles:
        # matched_plans 파싱
        mp = art.get("matched_plans", [])
        if isinstance(mp, str):
            try: mp = ast.literal_eval(mp)
            except: mp = []

        new_mp = []
        plan_scores = {}

        for plan_id in mp:
            result = _score_article(art, plan_id)
            if result["pass"]:
                new_mp.append(plan_id)
                plan_scores[plan_id] = result["score"]
            else:
                rejected_links.append({
                    "article_id": art.get("id", art.get("url","")),
                    "title": art.get("title","")[:80],
                    "plan_id": plan_id,
                    "reason": result["reason"],
                    "conflict_hits": result.get("conflict_hits", []),
                    "sector": art.get("sector",""),
                })

        art["matched_plans"] = new_mp
        art["relevance_scores"] = plan_scores
        reranked.append(art)

        for pid in new_mp:
            plan_buckets[pid].append(art)

    # 플랜별 최신순 정렬 (발행일 내림차순)
    def _date_key(a):
        d = (a.get("published_date") or "")[:10]
        return d if d else "1900-01-01"

    for pid in plan_buckets:
        plan_buckets[pid].sort(key=_date_key, reverse=True)

    stats = {
        "total_articles": len(reranked),
        "total_matched_before": sum(len(a.get("matched_plans",[])) + len(a.get("relevance_scores",{})) for a in articles),
        "total_matched_after": sum(len(a["matched_plans"]) for a in reranked),
        "total_rejected_links": len(rejected_links),
        "per_plan": {
            pid: len(plan_buckets[pid]) for pid in plan_buckets
        }
    }

    return {
        "articles": reranked,
        "plan_buckets": plan_buckets,
        "rejected_plan_links": rejected_links,
        "stats": stats,
    }


def build_feedback_blocklist(rejected_links: list, output_path: str = None) -> dict:
    """
    제거된 기사 패턴 분석 → FEEDBACK_BLOCKLIST.json 생성/업데이트
    이 파일을 agent_pipeline.py 수집 단계에서 참조해 미리 필터링.
    """
    if output_path is None:
        output_path = str(BASE_DIR / "config" / "FEEDBACK_BLOCKLIST.json")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # 기존 blocklist 로드
    existing = {}
    if Path(output_path).exists():
        with open(output_path) as f:
            existing = json.load(f)

    # 패턴 분석: 어떤 플랜에서 어떤 conflict 키워드가 많이 나왔나
    plan_conflicts = {}
    for r in rejected_links:
        pid = r["plan_id"]
        if pid not in plan_conflicts:
            plan_conflicts[pid] = Counter()
        for kw in r.get("conflict_hits", []):
            plan_conflicts[pid][kw] += 1

    # URL 패턴 (반복 제거 대상 도메인)
    rejected_urls = [r.get("article_id","") for r in rejected_links if r.get("article_id","").startswith("http")]
    domain_counter = Counter()
    for url in rejected_urls:
        m = re.match(r"https?://([^/]+)", url)
        if m: domain_counter[m.group(1)] += 1

    # 자주 제거되는 도메인 (3회 이상 → 블록 후보)
    block_domains = {d: c for d, c in domain_counter.items() if c >= 3}

    # 자주 제거되는 제목 패턴
    title_words = Counter()
    for r in rejected_links:
        words = re.findall(r'\b[a-zA-Z]{4,}\b', r.get("title","").lower())
        title_words.update(words)

    # 제거된 기사 제목 전체 목록 (추후 수동 검토용)
    rejected_titles = list({r["title"] for r in rejected_links})[:50]

    # blocklist 구조
    new_entry = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M KST"),
        "rejected_count": len(rejected_links),
        "block_domains": block_domains,
        "per_plan_conflict_patterns": {
            pid: dict(cnt.most_common(10))
            for pid, cnt in plan_conflicts.items()
        },
        "frequent_noise_words": dict(title_words.most_common(20)),
        "rejected_titles_sample": rejected_titles,
    }

    # 기존 기록과 병합 (히스토리 유지)
    history = existing.get("history", [])
    history.append(new_entry)
    history = history[-8:]  # 최근 8주치만 유지

    blocklist = {
        "schema_version": "1.0",
        "last_updated": new_entry["updated_at"],
        "history": history,
        # 누적 블록 도메인 (전체 히스토리 기준 2회 이상)
        "cumulative_block_domains": _aggregate_domains(history),
        # 각 플랜별 누적 conflict 패턴
        "cumulative_plan_conflicts": _aggregate_plan_conflicts(history),
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(blocklist, f, ensure_ascii=False, indent=2)

    return blocklist


def _aggregate_domains(history):
    total = Counter()
    for h in history:
        total.update(h.get("block_domains", {}))
    return {d: c for d, c in total.most_common() if c >= 2}


def _aggregate_plan_conflicts(history):
    result = {}
    for h in history:
        for pid, kws in h.get("per_plan_conflict_patterns", {}).items():
            if pid not in result:
                result[pid] = Counter()
            result[pid].update(kws)
    return {pid: dict(cnt.most_common(8)) for pid, cnt in result.items()}


# ── 수집 단계 필터 (agent_pipeline.py에서 import) ───────────────────────
def apply_collection_filter(articles: list, blocklist_path: str = None) -> list:
    """
    수집된 기사를 FEEDBACK_BLOCKLIST.json 기준으로 1차 필터링.
    agent_pipeline.py의 run_agent1_collection() 직후 호출.
    """
    if blocklist_path is None:
        blocklist_path = str(BASE_DIR / "config" / "FEEDBACK_BLOCKLIST.json")

    if not Path(blocklist_path).exists():
        return articles  # blocklist 없으면 패스

    with open(blocklist_path) as f:
        bl = json.load(f)

    block_domains = set(bl.get("cumulative_block_domains", {}).keys())
    before = len(articles)
    filtered = []

    for art in articles:
        url = art.get("url", "")
        m = re.match(r"https?://([^/]+)", url)
        domain = m.group(1) if m else ""
        if domain in block_domains:
            continue  # 블록 도메인 제거
        filtered.append(art)

    removed = before - len(filtered)
    if removed > 0:
        print(f"  🔇 컬렉션 피드백 필터: {removed}건 제거 (블록 도메인 {len(block_domains)}개 기준)")

    return filtered


# ── CLI 직접 실행 ─────────────────────────────────────────────────────
if __name__ == "__main__":
    import ast

    data_path = BASE_DIR / "genspark_output.json"
    if not data_path.exists():
        data_path = BASE_DIR / "outputs" / "genspark_output.json"

    print("="*60)
    print("관련성 재평가 & 피드백 루프 실행")
    print("="*60)

    with open(data_path) as f:
        articles = json.load(f)
    if not isinstance(articles, list):
        articles = articles.get("articles", [])

    for a in articles:
        mp = a.get("matched_plans", [])
        if isinstance(mp, str):
            try: a["matched_plans"] = ast.literal_eval(mp)
            except: a["matched_plans"] = []

    print(f"✓ 기사 로드: {len(articles)}건")
    print("\n▶ 관련성 재평가 중...")
    result = run_relevance_rerank(articles)

    stats = result["stats"]
    print(f"\n📊 결과 요약:")
    print(f"  전체 기사: {stats['total_articles']}건")
    print(f"  제거된 플랜-기사 링크: {stats['total_rejected_links']}건")
    print()
    print(f"{'플랜 ID':25s} {'재평가 후':>8s}")
    print("-"*35)
    for pid, cnt in sorted(stats["per_plan"].items(), key=lambda x:-x[1]):
        print(f"  {pid:25s} {cnt:>5d}건")

    # 피드백 blocklist 생성
    print("\n▶ 피드백 blocklist 생성 중...")
    bl = build_feedback_blocklist(result["rejected_plan_links"])
    print(f"✅ FEEDBACK_BLOCKLIST.json 저장")
    print(f"   블록 도메인: {len(bl.get('cumulative_block_domains',{}))}개")

    # 재평가된 결과 저장
    out_path = BASE_DIR / "genspark_output.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result["articles"], f, ensure_ascii=False, indent=2)
    print(f"\n✅ 재평가 결과 저장: {out_path}")

    # 제거 샘플 출력
    print("\n📋 제거된 기사 샘플 (상위 15건):")
    for r in result["rejected_plan_links"][:15]:
        print(f"  [{r['plan_id']:15s}] {r['reason']:30s} | {r['title'][:55]}")
