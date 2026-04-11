#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
apply_dashboard_policy_patch.py
dashboard_template.html에 정책 연계 기사 노란색 뱃지 표시 패치 적용
실행: python3 scripts/apply_dashboard_policy_patch.py
"""
import json
from pathlib import Path

BASE_DIR   = Path(__file__).parent.parent
TEMPLATE   = BASE_DIR / "templates" / "dashboard_template.html"
SHARED_DOCS = BASE_DIR / "docs" / "shared"
POLICY_FILE = SHARED_DOCS / "policy_highlighted_articles.json"

PATCH_MARKER = "/* POLICY_HIGHLIGHT_PATCH_v1 */"

JS_PATCH = """
/* POLICY_HIGHLIGHT_PATCH_v1 */
/* 정책 연계 기사 노란색 뱃지 + 행 하이라이트 */
function getPolicyBadge(article) {
    if (!article.policy_highlight) return '';
    var label = article.policy_doc_id || 'Policy';
    var relevance = article.policy_relevance || '';
    var color = relevance === 'high' ? '#F9A825' : '#FFD54F';
    var textColor = '#5D4037';
    return '<span style="background:' + color + ';color:' + textColor + ';' +
           'padding:1px 6px;border-radius:3px;font-size:10px;margin-left:4px;' +
           'font-weight:500;vertical-align:middle" title="' + (article.policy_plan_name || label) + '">' +
           label + '</span>';
}

function applyPolicyHighlights() {
    // policy_highlighted_articles.json에서 URL 목록 로드
    fetch('/shared/policy_highlighted_articles.json')
        .then(function(r) { return r.ok ? r.json() : null; })
        .then(function(data) {
            if (!data || !data.articles) return;
            var policyMap = {};
            data.articles.forEach(function(a) {
                if (a.policy_highlight && a.url) {
                    policyMap[a.url] = {
                        doc_id: a.policy_doc_id,
                        plan_name: a.policy_plan_name,
                        relevance: a.policy_relevance
                    };
                }
            });
            // 기사 카드에 뱃지 적용
            document.querySelectorAll('[data-url]').forEach(function(el) {
                var url = el.getAttribute('data-url');
                if (policyMap[url]) {
                    el.style.borderLeft = '3px solid #F9A825';
                    el.style.backgroundColor = '#FFFDE7';
                    var badge = document.createElement('span');
                    badge.className = 'policy-badge';
                    badge.textContent = policyMap[url].doc_id || 'Policy';
                    badge.title = policyMap[url].plan_name || '';
                    badge.style.cssText = 'background:#F9A825;color:#5D4037;padding:1px 6px;' +
                        'border-radius:3px;font-size:10px;margin-left:4px;font-weight:500';
                    var titleEl = el.querySelector('.article-title, h3, .title');
                    if (titleEl) titleEl.appendChild(badge);
                }
            });
        })
        .catch(function() {});
}

/* BACKEND_DATA에 policy_highlight 플래그 반영 */
function renderArticleCard(n) {
    var policyBadge = n.policy_highlight ?
        '<span style="background:#F9A825;color:#5D4037;padding:1px 5px;' +
        'border-radius:3px;font-size:10px;font-weight:500;margin-left:4px">' +
        (n.policy_doc_id || 'Policy') + '</span>' : '';
    var rowStyle = n.policy_highlight ?
        'style="background:#FFFDE7;border-left:3px solid #F9A825"' : '';
    return { policyBadge: policyBadge, rowStyle: rowStyle };
}
"""

def apply_patch():
    if not TEMPLATE.exists():
        print(f"[SKIP] 템플릿 없음: {TEMPLATE}")
        return False

    with open(TEMPLATE, "r", encoding="utf-8") as f:
        content = f.read()

    if PATCH_MARKER in content:
        print("[INFO] 이미 패치 적용됨")
        return True

    # </head> 바로 앞에 JS 삽입
    if "</head>" in content:
        content = content.replace(
            "</head>",
            f"<script>{JS_PATCH}</script>\n</head>"
        )
        # </body> 앞에 applyPolicyHighlights() 호출 추가
        content = content.replace(
            "</body>",
            "<script>document.addEventListener('DOMContentLoaded', applyPolicyHighlights);</script>\n</body>"
        )
        with open(TEMPLATE, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[OK] 대시보드 템플릿에 정책 하이라이트 패치 적용")
        return True

    print("[WARN] </head> 태그 없음 — 수동 적용 필요")
    return False


if __name__ == "__main__":
    apply_patch()
