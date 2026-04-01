import os
import json
import shutil
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLLECTOR_OUTPUT = os.path.join(BASE_DIR, "data", "agent_output", "collector_output.json")
KNOWLEDGE_INDEX  = os.path.join(BASE_DIR, "data", "knowledge", "knowledge_index.json")
AGENT_OUTPUT_DIR = os.path.join(BASE_DIR, "data", "agent_output")
KNOWLEDGE_OUTPUT = os.path.join(AGENT_OUTPUT_DIR, "knowledge_output.json")
SHARED_DOCS_DIR  = os.path.join(BASE_DIR, "docs", "shared")
SHARED_KI_DST    = os.path.join(SHARED_DOCS_DIR, "knowledge_index.json")


def get_text(article):
    return (
        article.get("summary_en")
        or article.get("title_en")
        or article.get("title")
        or ""
    ).lower()


def keyword_score(text, keywords):
    if not keywords:
        return 0.0
    hits = sum(1 for kw in keywords if kw.lower() in text)
    return hits / len(keywords)


def find_policy_context(doc, province):
    for target in doc.get("key_targets", []):
        if target.get("province") == province or target.get("province") == "Vietnam":
            return target.get("target", "")
    return ""


def process_article(article, knowledge_index):
    sector   = article.get("sector", "")
    province = article.get("province", "")
    text     = get_text(article)

    best_score = 0.0
    best_doc   = None

    for doc in knowledge_index:
        doc_sectors   = doc.get("sectors", [])
        doc_provinces = doc.get("provinces", [])

        sector_match   = sector in doc_sectors
        province_match = province in doc_provinces or "Vietnam" in doc_provinces

        if not (sector_match and province_match):
            continue

        score = keyword_score(text, doc.get("keywords_en", []))
        if score > best_score:
            best_score = score
            best_doc   = doc

    if best_doc is None or best_score <= 0.15:
        return None

    enriched = dict(article)
    enriched["policy_context"]        = find_policy_context(best_doc, province)
    enriched["plan_alignment_score"]  = round(best_score, 2)
    enriched["related_doc_id"]        = best_doc["doc_id"]
    enriched["high_policy_relevance"] = best_score > 0.7
    return enriched


def main():
    # 1. collector_output.json 확인
    if not os.path.exists(COLLECTOR_OUTPUT):
        print("collector_output.json 없음. news_collector.py --agent-mode 먼저 실행하세요.")
        return

    try:
        with open(COLLECTOR_OUTPUT, "r", encoding="utf-8") as f:
            collector_data = json.load(f)
    except Exception as e:
        print(f"[ERROR] collector_output.json 읽기 실패: {e}")
        return

    articles = collector_data.get("articles", [])

    # 2. knowledge_index.json 읽기
    try:
        with open(KNOWLEDGE_INDEX, "r", encoding="utf-8") as f:
            knowledge_index = json.load(f)
    except Exception as e:
        print(f"[ERROR] knowledge_index.json 읽기 실패: {e}")
        return

    # 3. 매칭 로직
    matched        = []
    unmatched      = []
    high_relevance = 0

    for article in articles:
        try:
            result = process_article(article, knowledge_index)
            if result is not None:
                matched.append(result)
                if result["high_policy_relevance"]:
                    high_relevance += 1
            else:
                unmatched.append(article)
        except Exception as e:
            print(f"  [WARN] 기사 처리 오류 ({article.get('title', '?')}): {e}")
            unmatched.append(article)

    # 4. 결과 저장
    os.makedirs(AGENT_OUTPUT_DIR, exist_ok=True)

    output = {
        "processed_at":        datetime.now(timezone.utc).isoformat(),
        "total_articles":      len(articles),
        "matched_count":       len(matched),
        "unmatched_count":     len(unmatched),
        "high_relevance_count": high_relevance,
        "articles_with_context": matched,
    }

    try:
        with open(KNOWLEDGE_OUTPUT, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"  [OK] knowledge_output.json 저장 완료")
    except Exception as e:
        print(f"  [ERROR] knowledge_output.json 저장 실패: {e}")

    # 5. docs/shared/knowledge_index.json 동기화
    try:
        os.makedirs(SHARED_DOCS_DIR, exist_ok=True)
        shutil.copy2(KNOWLEDGE_INDEX, SHARED_KI_DST)
        print(f"  [OK] knowledge_index.json → docs/shared/ 동기화 완료")
    except Exception as e:
        print(f"  [ERROR] knowledge_index.json 동기화 실패: {e}")

    # 6. 통계 출력
    print(
        f"\n총 {len(articles)}건 처리 / "
        f"매칭 성공 {len(matched)}건 / "
        f"미매칭 {len(unmatched)}건 / "
        f"고관련성 {high_relevance}건"
    )


if __name__ == "__main__":
    main()
