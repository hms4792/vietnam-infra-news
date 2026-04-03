"""
Lead Agent — SA-1~7 오케스트레이터
실행 순서: collect → knowledge → summarize → excel → dashboard → quality_context → export_shared
"""

import os
import sys
import json
import subprocess
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR    = os.path.join(BASE_DIR, "scripts")
AGENT_OUT_DIR  = os.path.join(BASE_DIR, "data", "agent_output")
COLLECTOR_JSON = os.path.join(AGENT_OUT_DIR, "collector_output.json")
KNOWLEDGE_JSON = os.path.join(AGENT_OUT_DIR, "knowledge_output.json")
WHO_I_AM_MD    = os.path.join(BASE_DIR, "00_Context", "WHO_I_AM.md")

# 실행 결과 기록
step_results = {}


# ── 유틸 ──────────────────────────────────────────────────────────────────────

def banner(msg):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print('='*60)


def run_script(script_name, extra_args=None):
    """scripts/ 하위 스크립트를 subprocess로 실행."""
    cmd = [sys.executable, os.path.join(SCRIPTS_DIR, script_name)]
    if extra_args:
        cmd += extra_args
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env, cwd=BASE_DIR)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    return result.returncode


def script_exists(script_name):
    return os.path.exists(os.path.join(SCRIPTS_DIR, script_name))


# ── 시작: WHO_I_AM.md 출력 ───────────────────────────────────────────────────

def print_context():
    try:
        with open(WHO_I_AM_MD, "r", encoding="utf-8") as f:
            print(f.read())
    except Exception:
        print("[INFO] 00_Context/WHO_I_AM.md 없음 — 건너뜀")


# ── Step 1: 뉴스 수집 ────────────────────────────────────────────────────────

def step1_collect(hours_back=24):
    banner("Step 1: 뉴스 수집 (news_collector.py)")
    os.makedirs(AGENT_OUT_DIR, exist_ok=True)

    try:
        # collect_news() 직접 import
        sys.path.insert(0, BASE_DIR)
        os.environ.setdefault("COLLECTOR_OUTPUT", COLLECTOR_JSON)

        from scripts.news_collector import collect_news, translate_articles

        cnt, arts, stats = collect_news(hours_back)

        if cnt > 0:
            arts = translate_articles(arts)

        # quality_flags 계산
        total = len(arts)
        vietnam_ratio = (
            sum(1 for a in arts if a.get("province", "") == "Vietnam") / total
            if total > 0 else 0.0
        )
        missing_provinces = (
            sum(1 for a in arts if not a.get("province")) / total
            if total > 0 else 0.0
        )

        output = {
            "run_timestamp": datetime.now(timezone.utc).isoformat(),
            "hours_back": hours_back,
            "total_collected": cnt,
            "articles": [{k: v for k, v in a.items() if k != "url_hash"} for a in arts],
            "quality_flags": {
                "vietnam_ratio": round(vietnam_ratio, 3),
                "missing_provinces": round(missing_provinces, 3),
            },
        }

        with open(COLLECTOR_JSON, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, default=str)

        print(f"[OK] collector_output.json 저장 완료 ({cnt}건)")
        step_results["step1"] = {"status": "ok", "collected": cnt}
        return arts

    except Exception as e:
        print(f"[ERROR] Step 1 실패: {e}")
        step_results["step1"] = {"status": "error", "msg": str(e)}
        return []


# ── Step 2: 지식베이스 매칭 ──────────────────────────────────────────────────

def step2_knowledge():
    banner("Step 2: 지식베이스 매칭 (knowledge_agent.py)")
    try:
        rc = run_script("knowledge_agent.py")

        matched = 0
        if os.path.exists(KNOWLEDGE_JSON):
            with open(KNOWLEDGE_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
            matched = data.get("matched_count", 0)

        if rc == 0:
            print(f"[OK] knowledge_output.json 생성 완료 (매칭 {matched}건)")
            step_results["step2"] = {"status": "ok", "matched": matched}
        else:
            print(f"[WARN] knowledge_agent.py 비정상 종료 (returncode={rc})")
            step_results["step2"] = {"status": "warn", "matched": matched}

    except Exception as e:
        print(f"[ERROR] Step 2 실패: {e}")
        step_results["step2"] = {"status": "error", "msg": str(e)}


# ── Step 3: AI 요약 ──────────────────────────────────────────────────────────

def step3_summarize():
    banner("Step 3: AI 요약 (ai_summarizer.py)")
    try:
        if not script_exists("ai_summarizer.py"):
            print("ai_summarizer.py 없음, 건너뜀")
            step_results["step3"] = {"status": "skipped"}
            return

        rc = run_script("ai_summarizer.py")
        if rc == 0:
            print("[OK] ai_summarizer.py 완료")
            step_results["step3"] = {"status": "ok"}
        else:
            print(f"[WARN] ai_summarizer.py 비정상 종료 (returncode={rc})")
            step_results["step3"] = {"status": "warn"}

    except Exception as e:
        print(f"[ERROR] Step 3 실패: {e}")
        step_results["step3"] = {"status": "error", "msg": str(e)}


# ── Step 4: Excel 업데이트 ───────────────────────────────────────────────────

def step4_excel(articles):
    banner("Step 4: Excel 업데이트 (ExcelUpdater)")
    try:
        if not script_exists("excel_updater.py"):
            print("excel_updater.py 없음, 건너뜀")
            step_results["step4"] = {"status": "skipped"}
            return

        if not articles:
            # collector_output.json에서 읽기 시도
            if os.path.exists(COLLECTOR_JSON):
                with open(COLLECTOR_JSON, "r", encoding="utf-8") as f:
                    articles = json.load(f).get("articles", [])

        if not articles:
            print("[INFO] 업데이트할 기사 없음, 건너뜀")
            step_results["step4"] = {"status": "skipped"}
            return

        sys.path.insert(0, BASE_DIR)
        from scripts.excel_updater import ExcelUpdater

        updater = ExcelUpdater()
        updater.update_all(articles)
        print(f"[OK] ExcelUpdater.update_all() 완료 ({len(articles)}건)")
        step_results["step4"] = {"status": "ok", "updated": len(articles)}

    except Exception as e:
        print(f"[ERROR] Step 4 실패: {e}")
        step_results["step4"] = {"status": "error", "msg": str(e)}


# ── Step 5: 대시보드 업데이트 ────────────────────────────────────────────────

def step5_dashboard():
    banner("Step 5: 대시보드 업데이트 (dashboard_updater.py / build_dashboard.py)")
    try:
        if script_exists("dashboard_updater.py"):
            target = "dashboard_updater.py"
        elif script_exists("build_dashboard.py"):
            target = "build_dashboard.py"
        else:
            print("dashboard_updater.py / build_dashboard.py 없음, 건너뜀")
            step_results["step5"] = {"status": "skipped"}
            return

        rc = run_script(target)
        if rc == 0:
            print(f"[OK] {target} 완료")
            step_results["step5"] = {"status": "ok"}
        else:
            print(f"[WARN] {target} 비정상 종료 (returncode={rc})")
            step_results["step5"] = {"status": "warn"}

    except Exception as e:
        print(f"[ERROR] Step 5 실패: {e}")
        step_results["step5"] = {"status": "error", "msg": str(e)}


# ── Step 6: 품질 분석 ────────────────────────────────────────────────────────

def step6_quality():
    banner("Step 6: 품질 분석 (quality_context_agent.py)")
    try:
        if not script_exists("quality_context_agent.py"):
            print("quality_context_agent.py 없음, 건너뜀")
            step_results["step6"] = {"status": "skipped"}
            return

        rc = run_script("quality_context_agent.py")

        grade = None
        quality_json = os.path.join(AGENT_OUT_DIR, "quality_report.json")
        if os.path.exists(quality_json):
            with open(quality_json, "r", encoding="utf-8") as f:
                q = json.load(f)
            grade = q.get("quality_grade")

        if rc == 0:
            print(f"[OK] quality_report.json 생성 완료 (등급: {grade})")
            step_results["step6"] = {"status": "ok", "grade": grade}
        else:
            print(f"[WARN] quality_context_agent.py 비정상 종료 (returncode={rc})")
            step_results["step6"] = {"status": "warn", "grade": grade}

    except Exception as e:
        print(f"[ERROR] Step 6 실패: {e}")
        step_results["step6"] = {"status": "error", "msg": str(e)}


# ── Step 7: 공유 레이어 Export ───────────────────────────────────────────────

def step7_export():
    banner("Step 7: 공유 레이어 Export (export_shared.py)")
    try:
        rc = run_script("export_shared.py")
        if rc == 0:
            print("[OK] export_shared.py 완료")
            step_results["step7"] = {"status": "ok"}
        else:
            print(f"[WARN] export_shared.py 비정상 종료 (returncode={rc})")
            step_results["step7"] = {"status": "warn"}

    except Exception as e:
        print(f"[ERROR] Step 7 실패: {e}")
        step_results["step7"] = {"status": "error", "msg": str(e)}


# ── 최종 리포트 ──────────────────────────────────────────────────────────────

def print_summary():
    banner("실행 요약 리포트")

    icons = {"ok": "✅", "warn": "⚠", "skipped": "⚠", "error": "❌"}
    labels = {
        "step1": "Step 1: 수집",
        "step2": "Step 2: 지식베이스 매칭",
        "step3": "Step 3: AI 요약",
        "step4": "Step 4: Excel 업데이트",
        "step5": "Step 5: 대시보드",
        "step6": "Step 6: 품질 분석",
        "step7": "Step 7: Export",
    }

    has_error = False
    has_warn  = False

    for key, label in labels.items():
        r = step_results.get(key, {"status": "skipped"})
        status = r["status"]
        icon   = icons.get(status, "⚠")

        detail = ""
        if status == "ok":
            if key == "step1":
                detail = f" {r.get('collected', 0)}건"
            elif key == "step2":
                detail = f" {r.get('matched', 0)}건"
            elif key == "step4":
                detail = f" {r.get('updated', 0)}건"
            elif key == "step6":
                detail = f" 등급:{r.get('grade', '?')}"
            elif key == "step7":
                detail = " 완료"
        elif status == "skipped":
            detail = " 건너뜀"
        elif status in ("error", "warn"):
            detail = f" {r.get('msg', '')}"

        print(f"  {icon} {label}{detail}")

        if status == "error":
            has_error = True
        elif status in ("warn", "skipped"):
            has_warn = True

    if has_error:
        overall = "FAILED" if all(
            step_results.get(k, {}).get("status") == "error"
            for k in ("step1", "step2", "step3", "step4", "step5", "step6", "step7")
        ) else "PARTIAL"
    elif has_warn:
        overall = "PARTIAL"
    else:
        overall = "SUCCESS"

    print(f"\n  전체 상태: {overall}")


# ── 진입점 ───────────────────────────────────────────────────────────────────

def main():
    print_context()
    banner(f"Lead Agent 시작 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    hours_back = int(os.environ.get("HOURS_BACK", 24))

    articles = step1_collect(hours_back)
    step2_knowledge()
    step3_summarize()
    step4_excel(articles)
    step5_dashboard()
    step6_quality()
    step7_export()
    print_summary()


if __name__ == "__main__":
    main()
