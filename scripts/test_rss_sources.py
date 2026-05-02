#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_rss_sources.py
====================
새 RSS 소스 후보들을 GitHub Actions 환경에서 직접 테스트하는 스크립트.
실행 결과를 data/agent_output/rss_test_result.json으로 저장.

실행: python3 scripts/test_rss_sources.py
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path

import requests
import feedparser

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0',
    'Accept': 'application/rss+xml, application/xml, text/xml, */*',
}

# ── 테스트 후보 소스 ──────────────────────────────────────────
# 검색에서 실제 기사가 확인된 소스들의 RSS URL 후보
CANDIDATES = {
    # ── 전문 인프라 미디어 ──────────────────────────────────
    "The Investor (EN)":          "https://theinvestor.vn/rss/en.rss",
    "The Investor (All)":         "https://theinvestor.vn/rss/all.rss",
    "The Investor (Feed)":        "https://theinvestor.vn/feed.xml",
    "The Investor (Atom)":        "https://theinvestor.vn/atom.xml",
    "VIR (Home RSS)":             "https://vir.com.vn/rss/home.rss",
    "VIR (Atom)":                 "https://vir.com.vn/atom.xml",
    "VIR (Infrastructure)":       "https://vir.com.vn/rss/infrastructure.rss",
    "Hanoi Times (RSS)":          "https://hanoitimes.vn/rss.xml",
    "Hanoi Times (Feed)":         "https://hanoitimes.vn/feed",
    "Hanoi Times (Home)":         "https://hanoitimes.vn/rss/home.rss",

    # ── 정부 공식 소스 ────────────────────────────────────
    "Vietnam.vn (EN Feed)":       "https://www.vietnam.vn/en/feed",
    "Vietnam.vn (RSS)":           "https://www.vietnam.vn/rss",
    "MoIT (Energy EN)":           "https://moit.gov.vn/en/rss/energy.rss",
    "MoIT (News EN)":             "https://moit.gov.vn/en/rss.xml",
    "EVN (EN News)":              "https://en.evn.com.vn/rss/news.rss",
    "EVN (EN RSS)":               "https://en.evn.com.vn/rss.xml",
    "PVN (Petrovietnam EN)":      "https://www.pvn.vn/en/rss",
    "PVN (EN Feed)":              "https://www.pvn.vn/en/feed",

    # ── 에너지 국제 전문지 ────────────────────────────────
    "PV-Tech (Asia)":             "https://www.pv-tech.org/category/asia/feed/",
    "PV-Tech (All)":              "https://www.pv-tech.org/feed/",
    "Offshore Energy (Asia)":     "https://www.offshore-energy.biz/category/asia/feed/",
    "Recharge News":              "https://www.rechargenews.com/rss",
    "Energy Monitor":             "https://www.energymonitor.ai/rss",

    # ── 비즈니스/투자 전문 ───────────────────────────────
    "Vietnam Briefing":           "https://www.vietnam-briefing.com/news/feed",
    "Vietnam Briefing (RSS)":     "https://www.vietnam-briefing.com/rss",
    "Nikkei Asia":                "https://asia.nikkei.com/rss/feed/nar",
    "Oxford Business Group VN":   "https://oxfordbusinessgroup.com/rss/vietnam",
    "KPMG Vietnam":               "https://home.kpmg/vn/en/home/insights.rss",

    # ── 건설/환경 분야 섹터별 RSS ────────────────────────
    "Bao Xay Dung (Moi truong)":  "https://baoxaydung.com.vn/rss/moi-truong.rss",
    "Bao Xay Dung (Ha Tang)":     "https://baoxaydung.com.vn/rss/ha-tang.rss",
    "Bao Xay Dung (Cap Nuoc)":    "https://baoxaydung.com.vn/rss/cap-thoat-nuoc.rss",
    "Bao Xay Dung (KCN)":         "https://baoxaydung.com.vn/rss/khu-do-thi.rss",

    # ── 에너지/석유가스 베트남어 ────────────────────────
    "PetroTimes (Home)":          "https://petrotimes.vn/rss/home.rss",
    "PetroTimes (Dau Khi)":       "https://petrotimes.vn/rss/dau-khi.rss",
    "PetroTimes (Nang luong)":    "https://petrotimes.vn/rss/nang-luong.rss",
    "Vietnam Energy (Home)":      "https://vietnamenergy.vn/rss/home.rss",
    "Vietnam Energy (Tin Tuc)":   "https://vietnamenergy.vn/rss/tin-tuc.rss",
    "Tap chi Nang luong VN":      "https://nangluongvietnam.vn/rss/home.rss",
    "Nang luong VN (Feed)":       "https://nangluongvietnam.vn/feed",

    # ── 산업/투자 베트남어 ───────────────────────────────
    "Bao Dau Tu (Home)":          "https://baodautu.vn/rss/home.rss",
    "Bao Dau Tu (Dau Tu)":        "https://baodautu.vn/rss/dau-tu.rss",
    "Bao Dau Tu (Nang Luong)":    "https://baodautu.vn/rss/nang-luong.rss",
    "VietnamBiz (RSS)":           "https://vietnambiz.vn/rss.rss",
    "VietnamBiz (Feed)":          "https://vietnambiz.vn/feed",

    # ── 환경/수자원 전문 ────────────────────────────────
    "Tap chi Moi Truong":         "https://tapchimôitruong.vn/rss/home.rss",
    "Tap chi MT (Feed)":          "https://tapchimôitruong.vn/feed",
    "Bao TN&MT":                  "https://baotainguyenmoitruong.vn/rss/tin-tuc.rss",
    "Bao TN&MT (Home)":           "https://baotainguyenmoitruong.vn/rss/home.rss",
    "Moi truong & Cuoc song":     "https://moitruong.net.vn/rss/home.rss",

    # ── 스마트시티/ICT ───────────────────────────────────
    "ICT News VN":                "https://ictnews.vietnamnet.vn/rss/home.rss",
    "VietnamNet ICT":             "https://vietnamnet.vn/rss/cong-nghe.rss",
    "Zing News Cong nghe":        "https://zingnews.vn/cong-nghe.rss",
}


def test_rss(name, url):
    """RSS URL 테스트 — feedparser로 실제 파싱까지 확인"""
    result = {
        "name":       name,
        "url":        url,
        "status":     "unknown",
        "http_code":  None,
        "entries":    0,
        "sample_title": "",
        "error":      "",
    }
    try:
        r = requests.get(url, timeout=10, headers=HEADERS, allow_redirects=True)
        result["http_code"] = r.status_code

        if r.status_code != 200:
            result["status"] = f"HTTP_{r.status_code}"
            return result

        # feedparser로 파싱
        feed = feedparser.parse(r.content)
        entries = len(feed.entries)
        result["entries"] = entries

        if entries > 0:
            result["status"]       = "OK"
            result["sample_title"] = (feed.entries[0].get("title", "")[:60])
        else:
            result["status"] = "NO_ENTRIES"

    except requests.Timeout:
        result["status"] = "TIMEOUT"
        result["error"]  = "Request timeout"
    except Exception as e:
        result["status"] = "ERROR"
        result["error"]  = str(e)[:80]

    return result


def main():
    print(f"RSS 소스 테스트 시작: {len(CANDIDATES)}개 후보")
    print("=" * 60)

    results = []
    ok_sources  = []
    fail_sources = []

    for name, url in CANDIDATES.items():
        r = test_rss(name, url)
        results.append(r)

        if r["status"] == "OK":
            ok_sources.append(r)
            print(f"  [OK ✅ {r['entries']}건] {name}")
            print(f"          → {r['sample_title']}")
        else:
            fail_sources.append(r)
            print(f"  [NG ❌ {r['status']}] {name}")

        time.sleep(0.5)

    # 결과 저장
    output = {
        "tested_at":    datetime.utcnow().isoformat() + "Z",
        "total":        len(CANDIDATES),
        "ok_count":     len(ok_sources),
        "fail_count":   len(fail_sources),
        "ok_sources":   ok_sources,
        "fail_sources": [{"name": r["name"], "url": r["url"],
                          "status": r["status"]} for r in fail_sources],
    }

    out_dir = Path("data/agent_output")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "rss_test_result.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 60)
    print(f"✅ 성공: {len(ok_sources)}개")
    for r in ok_sources:
        print(f"   {r['name']}: {r['entries']}건 | {r['url']}")
    print()
    print(f"❌ 실패: {len(fail_sources)}개")
    print()
    print(f"결과 저장: {out_path}")
    print("=" * 60)
    print()
    print("▶ 다음 단계:")
    print("  성공한 소스를 news_collector.py의 RSS_FEEDS에 추가하세요.")


if __name__ == "__main__":
    main()
