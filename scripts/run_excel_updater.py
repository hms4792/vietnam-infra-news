"""
파이프라인용 ExcelUpdater 실행 스크립트
collector_output.json 을 읽어 ExcelUpdater.update_all() 호출
"""
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLLECTOR_JSON = os.path.join(BASE_DIR, "data", "agent_output", "collector_output.json")

sys.path.insert(0, BASE_DIR)

if not os.path.exists(COLLECTOR_JSON):
    print("[SKIP] collector_output.json 없음")
    sys.exit(0)

with open(COLLECTOR_JSON, "r", encoding="utf-8") as f:
    data = json.load(f)

articles = data.get("articles", [])
stats    = data.get("stats", {})
if not articles:
    print("[SKIP] 수집 기사 없음")
    sys.exit(0)

from scripts.excel_updater import ExcelUpdater

updater = ExcelUpdater()
updater.update_all(articles, run_stats=stats)
print(f"[OK] ExcelUpdater 완료: {len(articles)}건")
