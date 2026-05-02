"""
export_masterplan_rules.py — GitHub 공유 파일 생성 + 업로드
============================================================
Claude SA (GitHub 파이프라인)가 참조하는 공유 파일 생성:
  data/shared/MASTER_RULES.json  — 기존 유지 (섹터→플랜 매핑 추가)
  data/shared/MASTERPLAN_IDS.json — 24개 플랜 ID + 키워드 전체 목록 (NEW)
  data/shared/RELEVANCE_RULES.json — 관련성 필터 규칙 전체 (NEW)

Claw 파이프라인 실행 시마다 자동 호출됨
"""
import os, json, sys, base64, re
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

BASE_DIR = Path("/home/work/claw")

def load_env():
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.strip() and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ.setdefault(k.strip(), v.strip())

def build_masterplan_ids():
    """24개 플랜 ID + 키워드 공유 파일"""
    from agent_pipeline import MASTERPLANS
    from relevance_filter import PLAN_RULES

    plans = []
    for p in MASTERPLANS:
        pid = p['id']
        rule = PLAN_RULES.get(pid, {})
        plans.append({
            "id":          pid,
            "name_ko":     p.get("name_ko", pid),
            "keywords":    p.get("keywords", [])[:15],   # 상위 15개만
            "must_any":    rule.get("must_any", []),
            "boost":       rule.get("boost", []),
            "conflict":    rule.get("conflict", []),
            "exclude_if":  p.get("exclude_if", []),
            "min_score":   rule.get("min_score", p.get("threshold", 1)),
            "sector_tags": rule.get("sector_tags", []),
        })

    return {
        "schema_version":  "2.0",
        "last_updated":    datetime.now().strftime("%Y-%m-%d"),
        "generated_by":    "claw_pipeline/export_masterplan_rules.py",
        "description":     "24개 베트남 인프라 마스터플랜 ID + 키워드 + 필터 규칙",
        "total_plans":     len(plans),
        "plans":           plans,
    }

def build_relevance_rules():
    """관련성 필터 전체 규칙"""
    from relevance_filter import PLAN_RULES
    from agent_pipeline import MASTERPLANS

    pipeline_ids = {p['id'] for p in MASTERPLANS}
    rules_out = {}
    for pid in pipeline_ids:
        rule = PLAN_RULES.get(pid, {})
        rules_out[pid] = {
            "must_any":    rule.get("must_any", []),
            "boost":       rule.get("boost", []),
            "conflict":    rule.get("conflict", []),
            "min_score":   rule.get("min_score", 1),
            "sector_tags": rule.get("sector_tags", []),
            "hard_exclude": rule.get("hard_exclude", []),
        }

    return {
        "schema_version": "2.0",
        "last_updated":   datetime.now().strftime("%Y-%m-%d"),
        "generated_by":   "claw_pipeline/export_masterplan_rules.py",
        "description":    "기사-마스터플랜 관련성 필터 규칙 (Claw 파이프라인 기준)",
        "rules":          rules_out,
    }

def build_sector_to_plan_mapping():
    """Claude SA 섹터 → Claw 플랜ID 매핑 테이블"""
    return {
        "schema_version": "2.0",
        "last_updated":   datetime.now().strftime("%Y-%m-%d"),
        "description":    "Claude SA 7개 섹터 ↔ Claw 24개 플랜ID 매핑",
        "mapping": {
            "Waste Water":       ["VN-WW-2030"],
            "Water Supply/Drainage": ["VN-WAT-RESOURCES","VN-WAT-URBAN","VN-WAT-RURAL"],
            "Solid Waste":       ["VN-SWM-NATIONAL-2030","VN-ENV-IND-1894"],
            "Power":             ["VN-PDP8-RENEWABLE","VN-PDP8-LNG","VN-PDP8-NUCLEAR",
                                  "VN-PDP8-COAL","VN-PDP8-GRID","VN-PDP8-HYDROGEN",
                                  "VN-CARBON-2050"],
            "Oil & Gas":         ["VN-OG-2030"],
            "Industrial Parks":  ["VN-IP-NORTH-2030","VN-RED-RIVER-2030","VN-MEKONG-DELTA-2030"],
            "Smart City":        ["VN-SC-2030","VN-URB-METRO-2030","HN-URBAN-NORTH",
                                  "HN-URBAN-WEST","HN-URBAN-INFRA"],
            "Transport":         ["VN-TRAN-2055","VN-URB-METRO-2030"],
            "EV/Mobility":       ["VN-EV-2030"],
            "Environment/Tech":  ["VN-ENV-IND-1894","VN-CARBON-2050"],
            "Hanoi":             ["HN-URBAN-NORTH","HN-URBAN-WEST","HN-URBAN-INFRA"],
        },
        "note": "Claude SA의 sector 필드 → Claw plan_id 매핑. "
                "genspark_output.json의 sector 값 기준으로 matched_plans 추론 가능."
    }

def github_upload(token, repo, path, content_str, message):
    """GitHub API로 파일 업로드/업데이트"""
    import urllib.request
    api_url = f"https://api.github.com/repos/{repo}/contents/{path}"
    # 현재 SHA 조회
    req = urllib.request.Request(api_url, headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "ClaWPipeline/2.0"
    })
    sha = None
    try:
        with urllib.request.urlopen(req) as r:
            sha = json.loads(r.read())["sha"]
    except: pass

    # 업로드
    payload = {
        "message": message,
        "content": base64.b64encode(content_str.encode()).decode(),
    }
    if sha: payload["sha"] = sha

    data = json.dumps(payload).encode()
    req2 = urllib.request.Request(api_url, data=data, headers={
        "Authorization": f"token {token}",
        "Content-Type":  "application/json",
        "Accept":        "application/vnd.github.v3+json",
        "User-Agent":    "ClaWPipeline/2.0"
    }, method="PUT")
    try:
        with urllib.request.urlopen(req2) as r:
            return r.status in (200, 201)
    except Exception as e:
        print(f"      GitHub 업로드 오류: {e}")
        return False

def run(push_to_github=True):
    load_env()
    token = os.getenv("GITHUB_PAT","")
    repo  = os.getenv("GITHUB_REPO","hms4792/vietnam-infra-news")

    now = datetime.now()
    results = {}

    # 1. MASTERPLAN_IDS.json
    print("  → MASTERPLAN_IDS.json 생성...", end=" ", flush=True)
    try:
        mp_ids = build_masterplan_ids()
        mp_str = json.dumps(mp_ids, ensure_ascii=False, indent=2)
        # 로컬 저장
        local = BASE_DIR / "config/masterplan_ids_export.json"
        local.write_text(mp_str, encoding='utf-8')
        if push_to_github and token:
            ok = github_upload(token, repo, "data/shared/MASTERPLAN_IDS.json", mp_str,
                               f"[Claw] Update MASTERPLAN_IDS — {mp_ids['total_plans']} plans ({now.strftime('%Y-%m-%d')})")
            print(f"{'✅ GitHub' if ok else '✅ 로컬만'}")
        else:
            print("✅ 로컬")
        results["MASTERPLAN_IDS"] = True
    except Exception as e:
        print(f"❌ {e}"); results["MASTERPLAN_IDS"] = False

    # 2. RELEVANCE_RULES.json
    print("  → RELEVANCE_RULES.json 생성...", end=" ", flush=True)
    try:
        rr = build_relevance_rules()
        rr_str = json.dumps(rr, ensure_ascii=False, indent=2)
        local2 = BASE_DIR / "config/relevance_rules_export.json"
        local2.write_text(rr_str, encoding='utf-8')
        if push_to_github and token:
            ok = github_upload(token, repo, "data/shared/RELEVANCE_RULES.json", rr_str,
                               f"[Claw] Update RELEVANCE_RULES ({now.strftime('%Y-%m-%d')})")
            print(f"{'✅ GitHub' if ok else '✅ 로컬만'}")
        else:
            print("✅ 로컬")
        results["RELEVANCE_RULES"] = True
    except Exception as e:
        print(f"❌ {e}"); results["RELEVANCE_RULES"] = False

    # 3. SECTOR_TO_PLAN.json
    print("  → SECTOR_TO_PLAN.json 생성...", end=" ", flush=True)
    try:
        s2p = build_sector_to_plan_mapping()
        s2p_str = json.dumps(s2p, ensure_ascii=False, indent=2)
        local3 = BASE_DIR / "config/sector_to_plan_export.json"
        local3.write_text(s2p_str, encoding='utf-8')
        if push_to_github and token:
            ok = github_upload(token, repo, "data/shared/SECTOR_TO_PLAN.json", s2p_str,
                               f"[Claw] Update SECTOR_TO_PLAN mapping ({now.strftime('%Y-%m-%d')})")
            print(f"{'✅ GitHub' if ok else '✅ 로컬만'}")
        else:
            print("✅ 로컬")
        results["SECTOR_TO_PLAN"] = True
    except Exception as e:
        print(f"❌ {e}"); results["SECTOR_TO_PLAN"] = False

    return results

if __name__ == "__main__":
    sys.path.insert(0, str(BASE_DIR/"scripts"))
    ok = run(push_to_github=True)
    print(f"\n결과: {ok}")
