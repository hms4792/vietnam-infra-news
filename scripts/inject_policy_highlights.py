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
    policy_highlight 필드 추가.

    JSON 추출: regex 대신 문자열 인덱싱 방식으로 대용량·특수문자 안정 처리
    """
    MARKER = "/*__BACKEND_DATA__*/"
    marker_idx = html_content.find(MARKER)
    if marker_idx < 0:
        print("  [SKIP] BACKEND_DATA 플레이스홀더 없음")
        return html_content, 0

    # 마커 직후 '[' 위치에서 JSON 배열 끝 ']' 까지 직접 슬라이싱
    json_start = html_content.find("[", marker_idx)
    if json_start < 0:
        print("  [SKIP] BACKEND_DATA 배열 시작 없음")
        return html_content, 0

    # 중첩 배열/객체를 고려한 괄호 카운팅으로 안전하게 끝 위치 탐색
    depth = 0
    json_end = -1
    in_str = False
    escape = False
    for i, ch in enumerate(html_content[json_start:], json_start):
        if escape:
            escape = False
            continue
        if ch == '\\':
            escape = True
            continue
        if ch == '"' and not escape:
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == '[' or ch == '{':
            depth += 1
        elif ch == ']' or ch == '}':
            depth -= 1
            if depth == 0:
                json_end = i + 1
                break

    if json_end < 0:
        print("  [WARN] BACKEND_DATA JSON 끝 위치 탐색 실패 → fallback")
        articles = None
    else:
        json_str = html_content[json_start:json_end]
        try:
            articles = json.loads(json_str)
            print(f"  [OK] BACKEND_DATA {len(articles)}건 파싱 성공")
        except json.JSONDecodeError as e:
            print(f"  [WARN] BACKEND_DATA JSON 파싱 실패: {e}")
            print(f"  [INFO] URL 기반 fallback으로 전환")
            articles = None  # fallback 모드

    # Fallback: articles 파싱 실패 시 JS 주입 방식으로 대체
    if articles is None:
        # policy_map의 URL 목록을 JS 배열로 대시보드에 주입
        policy_urls = list(policy_map.keys())
        js_injection = f"""
<script>
// Policy highlight injection (URL-based fallback)
(function() {{
  var policyUrls = {json.dumps(policy_urls)};
  document.addEventListener('DOMContentLoaded', function() {{
    document.querySelectorAll('a[href]').forEach(function(a) {{
      if (policyUrls.includes(a.href)) {{
        var card = a.closest('.article-card, tr, li, div[data-url]');
        if (card) card.style.backgroundColor = '#FFF9C4';
      }}
    }});
  }});
}})();
</script>"""
        if '</body>' in html_content:
            html_content = html_content.replace('</body>', js_injection + '</body>')
            print(f"  [OK] URL 기반 정책 배지 JS 주입 ({len(policy_urls)}건)")
        return html_content, len(policy_urls)

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
/* Vietnam Infra News — 정책연계 기사 노란색 하이라이트 v2.0 */
(function() {
  /* BACKEND_DATA에서 policy_highlight=true 기사 URL 세트 구성 */
  function getPolicyUrls() {
    if (typeof BACKEND_DATA === 'undefined' || !Array.isArray(BACKEND_DATA)) return new Set();
    return new Set(
      BACKEND_DATA
        .filter(function(a) { return a.policy_highlight === true; })
        .map(function(a) { return a.url || ''; })
        .filter(Boolean)
    );
  }

  /* 기사 카드/행에 노란색 하이라이트 + 배지 적용 */
  function applyHighlight(el, art) {
    el.style.background = '#FFFDE7';
    el.style.borderLeft = '3px solid #F9A825';
    if (!el.querySelector('.policy-badge')) {
      var badge = document.createElement('span');
      badge.className = 'policy-badge';
      badge.textContent = art.policy_doc_id || 'Policy';
      badge.title = art.policy_plan_name || '';
      badge.style.cssText = 'background:#F9A825;color:#5D4037;padding:1px 6px;'
        + 'border-radius:3px;font-size:10px;font-weight:500;margin-left:6px;'
        + 'vertical-align:middle;display:inline-block;';
      var titleEl = el.querySelector('h3,h4,.article-title,.title,td:first-child');
      if (titleEl) titleEl.appendChild(badge);
    }
  }

  /* DOM에서 링크 href 또는 data-url로 기사 매핑 후 하이라이트 */
  function runHighlight() {
    if (typeof BACKEND_DATA === 'undefined') return;
    var policyMap = {};
    BACKEND_DATA.forEach(function(a) {
      if (a.policy_highlight && a.url) policyMap[a.url] = a;
    });

    /* a[href] 기반 */
    document.querySelectorAll('a[href]').forEach(function(a) {
      var art = policyMap[a.href];
      if (!art) return;
      var card = a.closest('tr,li,.card,.article-card,.article-item,div[class*="article"]');
      if (card) applyHighlight(card, art);
    });

    /* data-url 기반 (있는 경우) */
    document.querySelectorAll('[data-url]').forEach(function(el) {
      var art = policyMap[el.getAttribute('data-url')];
      if (art) applyHighlight(el, art);
    });
  }

  /* 초기 실행 + 동적 렌더링 대응 (MutationObserver) */
  function init() {
    runHighlight();
    var observer = new MutationObserver(function(mutations) {
      var relevant = mutations.some(function(m) { return m.addedNodes.length > 0; });
      if (relevant) runHighlight();
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
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
