#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_excel_updater.py  v2.3
SA-4 진입점 — collector_output.json을 읽어 Excel DB 업데이트
policy_highlighted_articles.json 우선 사용 (노란색 표시 포함)
"""
import json
import os
import sys
from pathlib import Path

BASE_DIR  = Path(__file__).parent.parent
AGENT_OUT = BASE_DIR / "data" / "agent_output"

POLICY_HIGHLIGHTED = AGENT_OUT / "policy_highlighted_articles.json"
COLLECTOR_OUT      = AGENT_OUT / "collector_output.json"


def load_articles():
    if POLICY_HIGHLIGHTED.exists():
        try:
            with open(POLICY_HIGHLIGHTED, "r", encoding="utf-8") as f:
                data = json.load(f)
            articles = data.get("articles", [])
            highlight_count = data.get("highlight_count", 0)
            print(f"[policy_highlighted] {len(articles)}건 로드 ({highlight_count}건 노란색 표시)")
            return articles
        except Exception as e:
            print(f"[WARN] policy_highlighted 로드 실패: {e}")

    if COLLECTOR_OUT.exists():
        try:
            with open(COLLECTOR_OUT, "r", encoding="utf-8") as f:
                data = json.load(f)
            articles = data.get("articles", [])
            print(f"[collector_output] {len(articles)}건 로드 (policy_highlight 없음)")
            return articles
        except Exception as e:
            print(f"[WARN] collector_output 로드 실패: {e}")

    print("[SKIP] 수집 기사 없음")
    return []


def main():
    sys.path.insert(0, str(BASE_DIR / "scripts"))
    try:
        from excel_updater import ExcelUpdater
    except ImportError as e:
        print(f"[ERROR] ExcelUpdater 임포트 실패: {e}")
        sys.exit(1)

    articles = load_articles()
    if not articles:
        print("[SKIP] 수집 기사 없음")
        return

    excel_path = Path(os.environ.get(
        "EXCEL_PATH",
        str(BASE_DIR / "data" / "database" / "Vietnam_Infra_News_Database_Final.xlsx")
    ))

    updater = ExcelUpdater(excel_path=excel_path)
    updater.update_all(articles)
    print(f"[OK] ExcelUpdater 완료: {len(articles)}건 처리")


if __name__ == "__main__":
    main()
