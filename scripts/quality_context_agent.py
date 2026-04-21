#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quality_context_agent.py  v2.0
SA-7 맥락 기반 + Policy Sentinel 통합 뉴스 분류 에이전트

변경사항 (v2.0):
  - Policy Sentinel 레이어 추가
    · Gate P1: 공통 정책 신호어 (59개) 탐지
    · Gate P2: 플랜 특화 앵커어 (22개 플랜 × 평균 13개) 매칭
    · 태그: POLICY_MATCH (SA7_MATCH와 독립)
  - knowledge_index.json에서 sentinel 정의 자동 로드
  - 결과 태그: SA7_MATCH | POLICY_MATCH | SA7+POLICY | NONE

실행:
  python3 scripts/quality_context_agent.py
  python3 scripts/quality_context_agent.py --dry-run
  python3 scripts/quality_context_agent.py --mode policy   # Policy Sentinel만
  python3 scripts/quality_context_agent.py --mode sa7      # SA-7만
  python3 scripts/quality_context_agent.py --mode all      # 전체 (기본값)
"""

import os, sys, re, json, logging, argparse
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter
from typing import Optional

# ── 경로 설정 ─────────────────────────────────────────────
import os as _os
BASE_DIR    = Path(__file__).parent.parent
DATA_DIR    = BASE_DIR / 'data'
DOCS_DIR    = BASE_DIR / 'docs'
SHARED_DIR  = DOCS_DIR / 'shared'

# knowledge_index: 환경변수 우선, 없으면 기본 경로
_ki_env = _os.environ.get('KNOWLEDGE_INDEX_PATH', '')
KI_PATH = Path(_ki_env) if _ki_env else SHARED_DIR / 'knowledge_index_v2.3.json'

# Excel DB: 환경변수 EXCEL_PATH 우선 (GitHub Actions에서 주입)
_excel_env = _os.environ.get('EXCEL_PATH', '')
if _excel_env:
    DB_PATH = BASE_DIR / _excel_env
else:
    # fallback: 여러 경로 순서대로 탐색
    for _p in [
        DATA_DIR / 'database' / 'Vietnam_Infra_News_Database_Final.xlsx',
        DATA_DIR / 'news_database.xlsx',
        BASE_DIR / 'news_database.xlsx',
    ]:
        if _p.exists():
            DB_PATH = _p
            break
    else:
        DB_PATH = DATA_DIR / 'news_database.xlsx'  # 기본값

REPORT_PATH = DATA_DIR / 'context_quality_report.json'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
# 1. knowledge_index 로드
# ════════════════════════════════════════════════════════════
def load_knowledge_index(path: Path) -> dict:
    """knowledge_index.json 로드 — policy_sentinel 포함"""
    if not path.exists():
        # fallback: 동일 디렉토리에서 탐색
        for p in [BASE_DIR / 'data' / 'shared' / 'knowledge_index_v2.3.json',
                  DATA_DIR / 'knowledge_index.json']:
            if p.exists():
                path = p
                break
        else:
            log.warning("knowledge_index.json 없음 — 기본 설정 사용")
            return {}

    with open(path, 'r', encoding='utf-8') as f:
        ki = json.load(f)
    log.info(f"knowledge_index v{ki.get('version','?')} 로드: "
             f"{ki.get('total_masterplans','?')}개 플랜")
    return ki


# ════════════════════════════════════════════════════════════
# 2. SA-7 스코어링 엔진 (기존)
# ════════════════════════════════════════════════════════════
# 플랜별 섹터 허용 목록
PLAN_SECTOR_OK = {
    "VN-WW-2030":            ["Waste Water","Water Supply","Water Supply/Drain","Water Supply/Drainage"],
    "VN-SWM-NATIONAL-2030":  ["Solid Waste"],
    "VN-ENV-IND-1894":       ["Solid Waste","Waste Water","Water Supply","Industrial Parks"],
    "VN-WAT-RESOURCES":      ["Water Supply","Water Supply/Drain","Water Supply/Drainage"],
    "VN-WAT-URBAN":          ["Water Supply","Water Supply/Drain","Water Supply/Drainage"],
    "VN-WAT-RURAL":          ["Water Supply","Water Supply/Drain","Water Supply/Drainage"],
    "VN-PWR-PDP8":           ["Power"],
    "VN-PWR-PDP8-RENEWABLE": ["Power"],
    "VN-PWR-PDP8-LNG":       ["Power","Oil & Gas"],
    "VN-PWR-PDP8-NUCLEAR":   ["Power"],
    "VN-PWR-PDP8-COAL":      ["Power"],
    "VN-PWR-PDP8-GRID":      ["Power"],
    "VN-PWR-PDP8-HYDROGEN":  ["Power"],
    "VN-OG-2030":            ["Oil & Gas"],
    "VN-TRAN-2055":          ["Transport","Smart City"],
    "VN-URB-METRO-2030":     ["Transport","Smart City"],
    "VN-SC-2030":            ["Smart City","Transport","Industrial Parks"],
    "VN-IP-NORTH-2030":      ["Industrial Parks","Smart City"],
    "VN-MEKONG-DELTA-2030":  ["Transport","Water Supply","Solid Waste","Power"],
    "VN-RED-RIVER-2030":     ["Industrial Parks","Smart City","Transport","Water Supply"],
    "HN-URBAN-INFRA":        ["Transport","Smart City"],
    "HN-URBAN-NORTH":        ["Smart City","Industrial Parks","Transport"],
    "HN-URBAN-WEST":         ["Smart City","Industrial Parks"],
    "HN-URBAN-SOUTH":        ["Transport","Industrial Parks"],
    "HN-URBAN-EAST":         ["Transport","Smart City","Industrial Parks"],
}

# 플랜별 SA-7 판정 기준
SA7_RULES = {
    "VN-WW-2030": {
        "must_any": ["wastewater","wwtp","sewage","thoát nước","nước thải","폐수","하수",
                     "treatment plant","yen xa","to lich","lu river","nhat tan wwtp"],
        "boost":    ["270,000","jica","oda","jfe","tekken","hanoi wastewater",
                     "ho chi minh wwtp","thu duc wwtp"],
        "occ_hard": ["drinking water","tap water","water supply network","reservoir",
                     "irrigation","dam","flood","drought"],
        "threshold": 36,
    },
    "VN-SWM-NATIONAL-2030": {
        "must_any": ["solid waste","waste-to-energy","wte","incineration","landfill",
                     "rác thải","고형폐기물","쓰레기","소각","매립",
                     "soc son","nam son","can tho wte"],
        "boost":    ["4000 ton","5000 ton","90mw","75mw","epr","extended producer"],
        "occ_hard": ["wastewater","sewage","water pollution","effluent"],
        "threshold": 36,
    },
    "VN-ENV-IND-1894": {
        "must_any": ["environmental industry","công nghiệp môi trường","1894",
                     "environmental technology","pollution control equipment",
                     "environmental equipment"],
        "boost":    ["decision 1894","1894/qd-ttg","환경산업"],
        "occ_hard": [],
        "threshold": 36,
    },
    "VN-WAT-RESOURCES": {
        "must_any": ["water resource","river basin","saltwater intrusion","drought",
                     "수자원","tài nguyên nước","mekong water","red river water"],
        "boost":    ["mekong","red river","climate","flood control","reservoir"],
        "occ_hard": ["water supply plant","tap water","wwtp","wastewater"],
        "threshold": 36,
    },
    "VN-WAT-URBAN": {
        "must_any": ["water supply plant","water treatment plant","cấp nước",
                     "상수도","정수장","water tariff","water service"],
        "boost":    ["adb water","ndf water","tu liem water","binh duong water"],
        "occ_hard": ["wastewater","sewage","irrigation","dam"],
        "threshold": 36,
    },
    "VN-PWR-PDP8": {
        "must_any": ["pdp8","power development plan","quy hoạch điện",
                     "전력개발계획","electricity law","evn capacity"],
        "boost":    ["decision 768","decision 500","180gw","236gw"],
        "occ_hard": [],
        "threshold": 30,
    },
    "VN-PWR-PDP8-RENEWABLE": {
        "must_any": ["offshore wind","solar farm","solar capacity","wind farm",
                     "renewable energy","재생에너지","태양광","풍력",
                     "điện gió","điện mặt trời","floating solar","dppa"],
        "boost":    ["decree 58","decree 57","gw offshore","rooftop solar"],
        "occ_hard": ["coal","lng","nuclear","oil","gas field"],
        "threshold": 36,
    },
    "VN-PWR-PDP8-LNG": {
        "must_any": ["lng","nhon trach","quang trach lng","hai phong lng",
                     "thai binh lng","lng power plant","lng terminal",
                     "imported lng","lng regasification"],
        "boost":    ["decree 100","decree 56","65% offtake","pv gas"],
        "occ_hard": ["offshore wind","solar","renewable"],
        "threshold": 36,
    },
    "VN-PWR-PDP8-NUCLEAR": {
        "must_any": ["nuclear","원자력","hạt nhân","ninh thuan",
                     "resolution 70","smr","atomic energy"],
        "boost":    ["rosatom","edf nuclear","2035 nuclear"],
        "occ_hard": [],
        "threshold": 36,
    },
    "VN-PWR-PDP8-COAL": {
        "must_any": ["coal phase","coal retirement","coal decommission",
                     "jetp","탈석탄","phaseout coal","coal-to-gas"],
        "boost":    ["just energy transition","2030 coal"],
        "occ_hard": [],
        "threshold": 36,
    },
    "VN-PWR-PDP8-GRID": {
        "must_any": ["500kv","transmission line","smart grid","substation",
                     "송전망","변전소","lưới điện","grid expansion",
                     "bess","battery storage","grid storage"],
        "boost":    ["18 billion grid","evn transmission"],
        "occ_hard": [],
        "threshold": 36,
    },
    "VN-PWR-PDP8-HYDROGEN": {
        "must_any": ["hydrogen","ammonia fuel","green hydrogen","blue hydrogen",
                     "수소","hydro energy export"],
        "boost":    [],
        "occ_hard": [],
        "threshold": 36,
    },
    "VN-OG-2030": {
        "must_any": ["crude oil","oil field","petrovietnam","pvn","pvgas",
                     "정유","원유","dầu thô","oil refinery","lng supply chain"],
        "boost":    ["bach ho","dung quat","nghi son"],
        "occ_hard": ["renewable","offshore wind","solar"],
        "threshold": 36,
    },
    "VN-TRAN-2055": {
        "must_any": ["expressway","highway","airport terminal","seaport berth",
                     "고속도로","공항","항만","교량","ring road","bridge construction",
                     "long thanh","cat linh","lach huyen","north south railway"],
        "boost":    ["ring road 4","long thanh airport","lach huyen phase"],
        "occ_hard": ["metro line","urban rail","urban railway"],
        "threshold": 36,
    },
    "VN-URB-METRO-2030": {
        "must_any": ["metro line","urban rail","urban railway","subway",
                     "메트로","도시철도","đường sắt đô thị","ben thanh"],
        "boost":    ["metro line 1","metro line 2","metro line 3"],
        "occ_hard": ["expressway","highway","seaport"],
        "threshold": 36,
    },
    "VN-SC-2030": {
        "must_any": ["smart city","digital city","e-government","iot infrastructure",
                     "스마트시티","thành phố thông minh","urban digital",
                     "brg smart city","da nang smart","binh duong smart"],
        "boost":    ["5g network","ai traffic","digital twin"],
        "occ_hard": [],
        "threshold": 36,
    },
    "VN-IP-NORTH-2030": {
        "must_any": ["industrial park","vsip","khu công nghiệp","산업단지",
                     "industrial zone fdi","deep c","thang long ip"],
        "boost":    ["vsip thai binh","vsip binh duong","deep c hai phong"],
        "occ_hard": ["smart city","metro","expressway"],
        "threshold": 36,
    },
    "VN-MEKONG-DELTA-2030": {
        "must_any": ["mekong delta","đồng bằng sông cửu long","메콩델타",
                     "can tho","an giang","dong thap","ca mau"],
        "boost":    ["saltwater intrusion","mekong flood","mekong transport"],
        "occ_hard": [],
        "threshold": 36,
    },
    "VN-RED-RIVER-2030": {
        "must_any": ["red river delta","đồng bằng sông hồng","홍강델타",
                     "hai phong port","quang ninh","ha long bay development"],
        "boost":    ["red river bridge","halong bay","lach huyen"],
        "occ_hard": [],
        "threshold": 36,
    },
    "HN-URBAN-INFRA": {
        "must_any": ["hanoi ring road","hanoi metro","to lich river",
                     "red river hanoi","하노이 링로드","하노이 메트로",
                     "ring road 4 hanoi","ring road 3.5","hanoi bridge"],
        "boost":    ["decision 1668","hanoi 2045","hanoi master plan"],
        "occ_hard": [],
        "threshold": 30,
    },
    "HN-URBAN-NORTH": {
        "must_any": ["dong anh","me linh","soc son","brg smart city",
                     "co loa","noi bai expansion","north hanoi"],
        "boost":    ["4.2 billion","sumitomo","nhat tan","north hanoi smart city"],
        "occ_hard": [],
        "threshold": 30,
    },
    "HN-URBAN-WEST": {
        "must_any": ["hoa lac","xuan mai","son tay hanoi","ba vi development",
                     "tien xuan","hoa lac hi-tech","west hanoi"],
        "boost":    ["460ha","silicon valley","hoa lac expansion","van cao hoa lac"],
        "occ_hard": [],
        "threshold": 30,
    },
    "HN-URBAN-SOUTH": {
        "must_any": ["gia binh airport","phu xuyen","southern hanoi",
                     "hanoi second airport","south hanoi logistics"],
        "boost":    ["gia binh","phu xuyen urban","nam son logistics"],
        "occ_hard": [],
        "threshold": 30,
    },
    "HN-URBAN-EAST": {
        "must_any": ["gia lam","long bien","eastern hanoi","red river new city",
                     "hong river hanoi","vinh tuy bridge","east hanoi"],
        "boost":    ["long bien urban","gia lam district","east hanoi bridge"],
        "occ_hard": [],
        "threshold": 30,
    },
}

# 부모-자식 플랜 계층 (자식 매칭 시 부모도 자동 포함)
PLAN_HIERARCHY = {
    "HN-URBAN-NORTH":        "HN-URBAN-INFRA",
    "HN-URBAN-WEST":         "HN-URBAN-INFRA",
    "HN-URBAN-SOUTH":        "HN-URBAN-INFRA",
    "HN-URBAN-EAST":         "HN-URBAN-INFRA",
    "VN-PWR-PDP8-RENEWABLE": "VN-PWR-PDP8",
    "VN-PWR-PDP8-LNG":       "VN-PWR-PDP8",
    "VN-PWR-PDP8-NUCLEAR":   "VN-PWR-PDP8",
    "VN-PWR-PDP8-COAL":      "VN-PWR-PDP8",
    "VN-PWR-PDP8-GRID":      "VN-PWR-PDP8",
    "VN-PWR-PDP8-HYDROGEN":  "VN-PWR-PDP8",
}


def score_sa7(text: str, sector: str, plan_id: str) -> tuple[int, list, list]:
    """
    SA-7 점수 계산
    Returns: (score, must_hits, boost_hits)
    """
    rules = SA7_RULES.get(plan_id)
    if not rules:
        return 0, [], []

    if sector not in PLAN_SECTOR_OK.get(plan_id, []):
        return -1, [], []  # 섹터 불일치

    t = text.lower()

    # occ_hard 제외어 → 즉시 탈락
    if any(e in t for e in rules.get('occ_hard', [])):
        return 0, [], []

    must_hits = [m for m in rules['must_any'] if m.lower() in t]
    boost_hits = [b for b in rules.get('boost', []) if b.lower() in t]

    if not must_hits:
        return 0, [], []

    score = len(must_hits) * 18 + len(boost_hits) * 8
    return score, must_hits, boost_hits


# ════════════════════════════════════════════════════════════
# 3. Policy Sentinel 엔진 (신규)
# ════════════════════════════════════════════════════════════
def build_policy_sentinel(ki: dict) -> dict:
    """knowledge_index에서 policy_sentinel 규칙 로드"""
    ps = ki.get('policy_sentinel', {})
    return {
        'signals': ps.get('_common_policy_signals', []),
        'plans':   ps.get('plans', {}),
    }


def score_policy(text: str, sector: str, plan_id: str,
                 sentinel: dict) -> tuple[int, list, list]:
    """
    Policy Sentinel 점수 계산
    Returns: (score, signal_hits, anchor_hits)
    Score 체계:
      0점:  탈락
      20점: 신호어만 (섹터 일치)
      40점: 신호어 + 앵커어 1개
      60점: 신호어 + 앵커어 2개 이상
    """
    if sector not in PLAN_SECTOR_OK.get(plan_id, []):
        return 0, [], []

    t = text.lower()
    signals = sentinel.get('signals', [])
    plan_rules = sentinel.get('plans', {}).get(plan_id, {})

    # Gate P1: 공통 신호어
    sig_hits = [s for s in signals if s.lower() in t]
    if not sig_hits:
        return 0, [], []

    # Gate P2: 플랜 앵커어
    anchors = plan_rules.get('plan_anchor', [])
    anchor_hits = [a for a in anchors if a.lower() in t]
    if not anchor_hits:
        return 0, [], []  # 앵커 없으면 탈락 (광범위 방지 핵심)

    # 제외어 확인
    excl = plan_rules.get('policy_excl', [])
    if any(e.lower() in t for e in excl):
        return 0, [], []

    score = 40 + min(len(anchor_hits) - 1, 1) * 20  # 40 or 60
    return score, sig_hits[:3], anchor_hits[:3]


# ════════════════════════════════════════════════════════════
# 4. 통합 분류기
# ════════════════════════════════════════════════════════════
def classify_article(title: str, summary: str, sector: str,
                     sentinel: dict) -> dict:
    """
    기사를 SA-7 + Policy Sentinel 두 경로로 동시 평가
    Returns classification dict
    """
    text = (str(title) + ' ' + str(summary)).lower()

    sa7_matches = {}
    policy_matches = {}

    for plan_id in SA7_RULES:
        # SA-7 경로
        score, must_h, boost_h = score_sa7(text, sector, plan_id)
        threshold = SA7_RULES[plan_id].get('threshold', 36)
        if score >= threshold:
            sa7_matches[plan_id] = {
                'score': score, 'must': must_h, 'boost': boost_h,
                'grade': 'HIGH' if score >= 65 else 'MEDIUM'
            }

    for plan_id in sentinel.get('plans', {}):
        # Policy Sentinel 경로
        p_score, sig_h, anc_h = score_policy(text, sector, plan_id, sentinel)
        if p_score >= 40:
            policy_matches[plan_id] = {
                'score': p_score, 'signals': sig_h, 'anchors': anc_h,
                'grade': 'HIGH' if p_score >= 60 else 'MEDIUM'
            }

    # 부모 플랜 자동 포함
    for child, parent in PLAN_HIERARCHY.items():
        if child in sa7_matches and parent not in sa7_matches:
            sa7_matches[parent] = {'score': 28, 'must': ['(child)'], 'boost': [],
                                    'grade': 'MEDIUM', 'auto_parent': True}
        if child in policy_matches and parent not in policy_matches:
            policy_matches[parent] = {'score': 20, 'signals': ['(child)'], 'anchors': [],
                                       'grade': 'MEDIUM', 'auto_parent': True}

    # 태그 결정
    has_sa7    = bool(sa7_matches)
    has_policy = bool(policy_matches)

    if has_sa7 and has_policy:
        tag = 'SA7+POLICY'
    elif has_sa7:
        tag = 'SA7_MATCH'
    elif has_policy:
        tag = 'POLICY_MATCH'
    else:
        tag = 'NONE'

    best_sa7_score = max((v['score'] for v in sa7_matches.values()), default=0)
    best_pol_score = max((v['score'] for v in policy_matches.values()), default=0)

    return {
        'tag':             tag,
        'sa7_plans':       list(sa7_matches.keys()),
        'sa7_best_score':  best_sa7_score,
        'sa7_details':     sa7_matches,
        'policy_plans':    list(policy_matches.keys()),
        'policy_best_score': best_pol_score,
        'policy_details':  policy_matches,
        'is_context':      tag != 'NONE',
    }


# ════════════════════════════════════════════════════════════
# 5. 메인 실행 함수
# ════════════════════════════════════════════════════════════
def run_quality_context_agent(mode: str = 'all', dry_run: bool = False):
    """Daily 파이프라인 실행 진입점"""
    log.info(f"quality_context_agent v2.0 시작 | mode={mode} | dry_run={dry_run}")

    # knowledge_index 로드
    ki = load_knowledge_index(KI_PATH)
    sentinel = build_policy_sentinel(ki)
    log.info(f"Policy Sentinel 로드: {len(sentinel['signals'])}개 신호어, "
             f"{len(sentinel['plans'])}개 플랜")

    # Excel DB 로드
    if not DB_PATH.exists():
        log.error(f"DB 없음: {DB_PATH}")
        sys.exit(1)

    import openpyxl
    wb = openpyxl.load_workbook(DB_PATH)
    ws = wb['News Database']

    headers = [cell.value for cell in ws[1]]
    title_col   = headers.index('News Title') + 1 if 'News Title' in headers else 4
    summary_col = headers.index('summary_en') + 1 if 'summary_en' in headers else None
    sector_col  = headers.index('Business Sector') + 1 if 'Business Sector' in headers else 2
    # QC 컬럼 위치 (없으면 생성)
    if 'QC' not in headers:
        ws.cell(1, len(headers)+1, 'QC')
        qc_col = len(headers) + 1
    else:
        qc_col = headers.index('QC') + 1

    stats = Counter()
    plan_policy_cnt = Counter()
    plan_sa7_cnt    = Counter()

    for row in ws.iter_rows(min_row=2):
        title   = str(row[title_col - 1].value or '')
        summary = str(row[summary_col - 1].value or '') if summary_col else ''
        sector  = str(row[sector_col - 1].value or '')

        result = classify_article(title, summary, sector, sentinel)

        # 통계 집계
        stats[result['tag']] += 1
        for p in result['sa7_plans']:
            plan_sa7_cnt[p] += 1
        for p in result['policy_plans']:
            plan_policy_cnt[p] += 1

        # QC 컬럼 업데이트 (dry_run이 아닐 때)
        if not dry_run and result['is_context']:
            tag_str = result['tag']
            if result['sa7_plans']:
                tag_str += f" | SA7:{','.join(result['sa7_plans'][:2])}"
            if result['policy_plans']:
                tag_str += f" | POL:{','.join(result['policy_plans'][:2])}"
            row[qc_col - 1].value = tag_str

    # 보고서 저장
    report = {
        'run_at': datetime.now().isoformat(),
        'mode': mode,
        'dry_run': dry_run,
        'stats': dict(stats),
        'plan_sa7_count': dict(plan_sa7_cnt.most_common(30)),
        'plan_policy_count': dict(plan_policy_cnt.most_common(30)),
    }
    if not dry_run:
        wb.save(DB_PATH)
        with open(REPORT_PATH, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    # 결과 출력
    total = sum(stats.values())
    log.info(f"분류 완료: {total}건")
    log.info(f"  SA7_MATCH:    {stats.get('SA7_MATCH', 0)}건")
    log.info(f"  POLICY_MATCH: {stats.get('POLICY_MATCH', 0)}건")
    log.info(f"  SA7+POLICY:   {stats.get('SA7+POLICY', 0)}건")
    log.info(f"  NONE:         {stats.get('NONE', 0)}건")

    if plan_policy_cnt:
        log.info("Policy 매칭 상위 플랜:")
        for pid, cnt in plan_policy_cnt.most_common(5):
            log.info(f"    {pid}: {cnt}건")

    return report


# ════════════════════════════════════════════════════════════
# 6. CLI 진입점
# ════════════════════════════════════════════════════════════
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='SA-7 + Policy Sentinel 분류 에이전트')
    parser.add_argument('--mode', choices=['all','sa7','policy'], default='all')
    parser.add_argument('--dry-run', action='store_true', help='DB 쓰기 없이 테스트')
    args = parser.parse_args()
    run_quality_context_agent(mode=args.mode, dry_run=args.dry_run)
