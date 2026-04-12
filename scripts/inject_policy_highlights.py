#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
inject_policy_highlights.py
============================
build_dashboard.py 실행 후 docs/index.html에
정책 연계 기사 하이라이트 데이터를 추가로 주입합니다.

[역할]
  BACKEND_DATA의 각 기사에 policy_highlight 플래그 추가
  → 대시보드 JS가 이 플래그로:
     1. 홈 탭 "오늘 수집" 화면: 정책 연계 기사만 표시 (노란색)
     2. Database 탭: 전체 기사 표시 (정책 연계 기사는 노란색 배지)

[실행]
  python3 scripts/inject_policy_highlights.py
  (build_dashboard.py 실행 후 호출)
"""

import json
import re
from pathlib import Path

BASE_DIR     = Path(__file__).parent.parent
DASHBOARD    = BASE_DIR / "docs" / "index.html"
POLICY_FILE  = BASE_DIR / "docs" / "shared" / "policy_highlighted_articles.json"
AGENT_OUT    = BASE_DIR / "data" / "agent_output"
POLICY_LOCAL = AGENT_OUT / "policy_highlighted_articles.json"


def load_policy_map():
    """URL → {policy_highlight, policy_doc_id, policy_plan_name} 매핑 로드"""
    path = POLICY_FILE if POLICY_FILE.exists() else POLICY_LOCAL
    if not path.exists():
        print("  [SKIP] policy_highlighted_articles.json 없음")
        return {}, 0

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    policy_map = {}
    count = 0
    for article in data.get("articles", []):
        url = article.get("url", "")
        if url and article.get("policy_highlight"):
            policy_map[url] = {
                "policy_highlight": True,
                "policy_doc_id":    article.get("policy_doc_id", ""),
                "policy_plan_name": article.get("policy_plan_name", ""),
                "policy_relevance": article.get("policy_relevance", ""),
            }
            count += 1
    print(f"  [policy_map] {count}건 로드 ({path.name})")
    return policy_map, count


def inject_policy_flags(html_content, policy_map):
    """
    BACKEND_DATA JSON 배열에서 각 기사의 url을 찾아
    policy_highlight 필드 추가
    """
    pattern = re.compile(r'/\*__BACKEND_DATA__\*/(\[.*?\])', re.DOTALL)
    match = pattern.search(html_content)
    if not match:
        print("  [SKIP] BACKEND_DATA 플레이스홀더 없음")
        return html_content, 0

    try:
        articles = json.loads(match.group(1))
    except json.JSONDecodeError as e:
        print(f"  [ERROR] BACKEND_DATA JSON 파싱 실패: {e}")
        return html_content, 0

    updated = 0
    for art in articles:
        url = art.get("url", "")
        if url in policy_map:
            art.update(policy_map[url])
            updated += 1
        else:
            art["policy_highlight"] = False

    new_json    = json.dumps(articles, ensure_ascii=False, separators=(",", ":"))
    new_content = html_content.replace(
        match.group(0),
        f"/*__BACKEND_DATA__*/{new_json}"
    )
    print(f"  [OK] {updated}건 policy_highlight 플래그 주입")
    return new_content, updated


DASHBOARD_JS_PATCH = """
<script>
/* policy_highlight 대시보드 로직 v1.0 */
(function() {
  var _origRender = window._renderArticles || null;

  function applyPolicyUI() {
    if (typeof BACKEND_DATA === 'undefined') return;

    /* 홈 탭 "오늘 수집" 섹션: 정책 연계 기사만 표시 */
    var todaySection = document.getElementById('today-articles');
    if (todaySection) {
      var cards = todaySection.querySelectorAll('[data-url]');
      cards.forEach(function(card) {
        var url = card.getAttribute('data-url');
        var art = BACKEND_DATA.find(function(a) { return a.url === url; });
        if (art && !art.policy_highlight) {
          card.style.display = 'none';
        } else if (art && art.policy_highlight) {
          card.style.background = '#FFFDE7';
          card.style.borderLeft = '3px solid #F9A825';
          var badge = document.createElement('span');
          badge.textContent = art.policy_doc_id || 'Policy';
          badge.title = art.policy_plan_name || '';
          badge.style.cssText = 'background:#F9A825;color:#5D4037;padding:1px 6px;'
            + 'border-radius:3px;font-size:10px;font-weight:500;margin-left:6px;'
            + 'vertical-align:middle';
          var titleEl = card.querySelector('.article-title, h3, .card-title, a');
          if (titleEl) titleEl.appendChild(badge);
        }
      });
    }

    /* Database 탭: 전체 표시 + 정책 연계 기사 노란색 배지 */
    var dbSection = document.getElementById('db-articles') || document.getElementById('all-articles');
    if (dbSection) {
      dbSection.querySelectorAll('[data-url]').forEach(function(card) {
        var url = card.getAttribute('data-url');
        var art = BACKEND_DATA.find(function(a) { return a.url === url; });
        if (art && art.policy_highlight && !card.querySelector('.policy-badge')) {
          card.style.borderLeft = '3px solid #F9A825';
          var badge = document.createElement('span');
          badge.className = 'policy-badge';
          badge.textContent = art.policy_doc_id || 'Policy';
          badge.style.cssText = 'background:#F9A825;color:#5D4037;padding:1px 6px;'
            + 'border-radius:3px;font-size:10px;font-weight:500;margin-left:6px';
          var titleEl = card.querySelector('.article-title, h3, .card-title, a');
          if (titleEl) titleEl.appendChild(badge);
        }
      });
    }
  }

  /* DOM 렌더링 완료 후 실행 */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function() {
      setTimeout(applyPolicyUI, 500);
    });
  } else {
    setTimeout(applyPolicyUI, 500);
  }

  /* MutationObserver로 동적 렌더링도 감지 */
  var observer = new MutationObserver(function() {
    applyPolicyUI();
  });
  document.addEventListener('DOMContentLoaded', function() {
    observer.observe(document.body, { childList: true, subtree: true });
  });
})();
</script>"""


def inject_js_patch(html_content):
    """</body> 바로 앞에 policy JS 패치 삽입"""
    if "policy_highlight 대시보드 로직" in html_content:
        print("  [INFO] JS 패치 이미 적용됨")
        return html_content
    if "</body>" in html_content:
        html_content = html_content.replace(
            "</body>",
            DASHBOARD_JS_PATCH + "\n</body>"
        )
        print("  [OK] 대시보드 policy JS 패치 삽입")
    else:
        print("  [WARN] </body> 없음 — JS 패치 삽입 실패")
    return html_content


def main():
    print("[inject_policy_highlights] 시작")

    if not DASHBOARD.exists():
        print(f"  [SKIP] docs/index.html 없음")
        return

    with open(DASHBOARD, "r", encoding="utf-8") as f:
        html = f.read()

    policy_map, policy_count = load_policy_map()
    if policy_count == 0:
        print("  [SKIP] 정책 연계 기사 없음")
        return

    html, updated = inject_policy_flags(html, policy_map)
    html          = inject_js_patch(html)

    with open(DASHBOARD, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  [OK] docs/index.html 업데이트 완료 ({updated}건 하이라이트)")


if __name__ == "__main__":
    main()
