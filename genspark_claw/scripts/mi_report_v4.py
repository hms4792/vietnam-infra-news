"""
mi_report_v4.py — MI 보고서 통합 오케스트레이터 v4.0
=====================================================
15개 보고서 일괄 생성:
  1  PDP8 통합      (에너지 6 sub-track → KPI형)
  2  Water 통합     (수자원 3 sub-track → KPI형)
  3  Hanoi 통합     (도시개발 3 sub-track → 지역성)
  4  VN-TRAN-2055  지역성
  5  VN-URB-METRO  지역성
  6  VN-MEKONG     지역성
  7  VN-RED-RIVER  지역성
  8  VN-IP-NORTH   지역성
  9  VN-WW-2030    지역성
  10 VN-SWM        지역성(혼합)
  11 VN-ENV-IND    KPI
  12 VN-SC-2030    KPI
  13 VN-OG-2030    KPI
  14 VN-EV-2030    KPI
  15 VN-CARBON     KPI
"""
import os, sys, time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/home/work/claw/scripts")

BASE_DIR  = Path("/home/work/claw")
OUTPUT_DIR = BASE_DIR / "outputs/reports/MI_Reports_v4"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def run_all(output_dir=str(OUTPUT_DIR)):
    results = []
    now = datetime.now()
    week = now.isocalendar()[1]
    print(f"\n{'='*60}")
    print(f"MI 보고서 v4.0 일괄 생성  —  W{week:02d}/{now.year}")
    print(f"출력: {output_dir}")
    print(f"{'='*60}\n")

    # ── 1. PDP8 통합 보고서 (에너지) ──────────────────────
    print("🔋 [1/15] PDP8 에너지 통합 보고서 (KPI형)")
    try:
        from mi_pdp8_report_v4 import generate_pdp8_report
        fpath = generate_pdp8_report(output_dir)
        _ok(results, "PDP8-INTEGRATED", fpath)
    except Exception as e:
        _fail(results, "PDP8-INTEGRATED", e)
        # 폴백: 구버전
        try:
            from mi_pdp8_report import generate_pdp8_report as gen_old
            fpath = gen_old(output_dir)
            _ok(results, "PDP8-INTEGRATED(fallback)", fpath)
        except Exception as e2:
            _fail(results, "PDP8-INTEGRATED(fallback)", e2)

    # ── 2. Water 통합 보고서 ──────────────────────────────
    print("💧 [2/15] Water 수자원 통합 보고서 (KPI형)")
    try:
        from mi_water_report_v4 import generate_water_report
        fpath = generate_water_report(output_dir)
        _ok(results, "WATER-INTEGRATED", fpath)
    except Exception as e:
        _fail(results, "WATER-INTEGRATED", e)
        try:
            from mi_water_report import generate_water_report as gen_old
            fpath = gen_old(output_dir)
            _ok(results, "WATER-INTEGRATED(fallback)", fpath)
        except Exception as e2:
            _fail(results, "WATER-INTEGRATED(fallback)", e2)

    # ── 3. Hanoi 통합 보고서 ─────────────────────────────
    print("🏙️  [3/15] Hanoi 도시개발 통합 보고서 (지역성)")
    try:
        from mi_hanoi_report_v4 import generate_hanoi_report
        fpath = generate_hanoi_report(output_dir)
        _ok(results, "HANOI-INTEGRATED", fpath)
    except Exception as e:
        _fail(results, "HANOI-INTEGRATED", e)
        try:
            from mi_hanoi_report import generate_hanoi_report as gen_old
            fpath = gen_old(output_dir)
            _ok(results, "HANOI-INTEGRATED(fallback)", fpath)
        except Exception as e2:
            _fail(results, "HANOI-INTEGRATED(fallback)", e2)

    # ── 4-10. 지역성 보고서 ──────────────────────────────
    from report_regional import generate_regional_report, PLAN_CONFIG
    regional_plans = [
        ("VN-TRAN-2055",         "[4/15]",  "🛣️"),
        ("VN-URB-METRO-2030",    "[5/15]",  "🚇"),
        ("VN-MEKONG-DELTA-2030", "[6/15]",  "🌊"),
        ("VN-RED-RIVER-2030",    "[7/15]",  "🏔️"),
        ("VN-IP-NORTH-2030",     "[8/15]",  "🏭"),
        ("VN-WW-2030",           "[9/15]",  "💧"),
        ("VN-SWM-NATIONAL-2030", "[10/15]", "♻️"),
    ]
    for plan_id, idx, icon in regional_plans:
        name = PLAN_CONFIG.get(plan_id, {}).get("name_ko", plan_id)
        print(f"{icon}  {idx} {plan_id} — {name[:30]} (지역성)")
        try:
            fpath = generate_regional_report(plan_id, output_dir)
            _ok(results, plan_id, fpath)
        except Exception as e:
            _fail(results, plan_id, e)

    # ── 11-15. KPI 보고서 ─────────────────────────────────
    from report_kpi import generate_kpi_report, KPI_CONFIG
    kpi_plans = [
        ("VN-ENV-IND-1894", "[11/15]", "🌿"),
        ("VN-SC-2030",      "[12/15]", "🏙️"),
        ("VN-OG-2030",      "[13/15]", "⛽"),
        ("VN-EV-2030",      "[14/15]", "🚗"),
        ("VN-CARBON-2050",  "[15/15]", "🌍"),
    ]
    for plan_id, idx, icon in kpi_plans:
        name = KPI_CONFIG.get(plan_id, {}).get("name_ko", plan_id)
        print(f"{icon}  {idx} {plan_id} — {name[:30]} (KPI형)")
        try:
            fpath = generate_kpi_report(plan_id, output_dir)
            _ok(results, plan_id, fpath)
        except Exception as e:
            _fail(results, plan_id, e)

    # ── 요약 ─────────────────────────────────────────────
    print(f"\n{'='*60}")
    ok  = [r for r in results if r[2]]
    fail= [r for r in results if not r[2]]
    total_kb = sum(r[3] for r in results if r[3])
    print(f"✅ 성공: {len(ok)}개  |  ❌ 실패: {len(fail)}개  |  총 용량: {total_kb}KB")
    if fail:
        print("실패 목록:")
        for plan_id, _, __, ___, err in fail:
            print(f"  ❌ {plan_id}: {err}")
    print(f"{'='*60}\n")
    return results

def _ok(results, plan_id, fpath):
    sz = os.path.getsize(fpath)//1024 if fpath and os.path.exists(fpath) else 0
    print(f"     → ✅ {sz}KB  [{Path(fpath).name if fpath else '?'}]")
    results.append((plan_id, True, fpath, sz, None))

def _fail(results, plan_id, err):
    print(f"     → ❌ {err}")
    results.append((plan_id, False, None, 0, str(err)))


if __name__ == "__main__":
    plan_arg = sys.argv[1] if len(sys.argv) > 1 else None
    if plan_arg:
        # 단일 보고서
        sys.path.insert(0, str(BASE_DIR/"scripts"))
        out = str(OUTPUT_DIR)
        if plan_arg.startswith("VN-") or plan_arg.startswith("HN-"):
            # regional or kpi
            try:
                from report_regional import generate_regional_report
                fpath = generate_regional_report(plan_arg, out)
                print(f"✅ {fpath}  ({os.path.getsize(fpath)//1024}KB)")
            except (ValueError, KeyError):
                from report_kpi import generate_kpi_report
                fpath = generate_kpi_report(plan_arg, out)
                print(f"✅ {fpath}  ({os.path.getsize(fpath)//1024}KB)")
    else:
        run_all()
