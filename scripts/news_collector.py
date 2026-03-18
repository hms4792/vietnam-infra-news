#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News Collector
Version 5.2 — Full Integration Update

반영된 개선사항:
  [검증보고서] 가중치 기반 점수제 분류 (최소 임계값 3점)
  [검증보고서] EXCLUDE_KEYWORDS 대폭 보강 (사고/스포츠/결혼/자동차 등)
  [검증보고서] 제목 키워드 3점 / 본문 키워드 1점 가중치 차등 적용
  [검증보고서] Province 추출 로직 강화 (본문 전체 스캔)
  [검증보고서] Google News API 채널 추가 (Nikkei, Reuters 보완)
  [Genspark] LANGUAGE_FILTER='all' (영어+베트남어 모두 수집)
  [Genspark] 9개 섹터 완전 정의 (Transport, Construction, Water Supply/Drainage 분리)
  [Genspark] confidence_score 필드 추가 (QC 에이전트 연계)
  [Genspark] 수집 후 JSON 출력 포맷 통일
  [v5.1]    우선순위 기반 분류 → 가중치 점수제로 통합 (보고서 권장방식)
"""

import os
import sys
import re
import sqlite3
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse, urljoin, quote
import html
import concurrent.futures
import time

import requests
import feedparser
from bs4 import BeautifulSoup

# ============================================================
# CONFIGURATION
# ============================================================

DB_PATH          = os.environ.get('DB_PATH',       'data/vietnam_infrastructure_news.db')
HOURS_BACK       = int(os.environ.get('HOURS_BACK', 24))
EXCEL_PATH       = os.environ.get('EXCEL_PATH',    'data/database/Vietnam_Infra_News_Database_Final.xlsx')

# [Genspark] 모든 언어 수집 (영어 + 베트남어)
LANGUAGE_FILTER  = os.environ.get('LANGUAGE_FILTER', 'all').lower()

# [검증보고서] 분류 최소 임계값: 3점 이상이어야 섹터 확정
MIN_CLASSIFY_THRESHOLD = 3

# Google News API (Nikkei/Reuters 보완용)
GNEWS_API_KEY    = os.environ.get('GNEWS_API_KEY', '')
ENABLE_GNEWS     = os.environ.get('ENABLE_GNEWS', 'false').lower() == 'true'
GNEWS_QUERY      = 'Vietnam infrastructure OR "Vietnam energy" OR "Vietnam transport"'


# ============================================================
# SECTOR DEFINITIONS  (9개 섹터, 가중치 키워드 사전)
# [검증보고서] primary 키워드: 제목 3점 / 본문 1점
# [검증보고서] secondary 키워드: 제목 2점 / 본문 0.5점 (정수 반올림)
# [Genspark]  Smart Classification Agent 프롬프트 키워드 통합
# ============================================================

SECTOR_PRIORITY_ORDER = [
    "Waste Water",
    "Water Supply/Drainage",
    "Oil & Gas",
    "Power",
    "Solid Waste",
    "Transport",
    "Industrial Parks",
    "Smart City",
    "Construction",
]

SECTOR_AREA = {
    "Waste Water":            "Environment",
    "Water Supply/Drainage":  "Environment",
    "Solid Waste":            "Environment",
    "Power":                  "Energy",
    "Oil & Gas":              "Energy",
    "Transport":              "Urban Development",
    "Industrial Parks":       "Urban Development",
    "Smart City":             "Urban Development",
    "Construction":           "Urban Development",
}

SECTOR_KEYWORDS = {
    # ─────────────────────────────────────────────────────────
    # 1. WASTE WATER  (하수·폐수 처리)
    # ─────────────────────────────────────────────────────────
    "Waste Water": {
        "primary": [
            "wastewater", "waste water",
            "sewage treatment", "sewage plant", "sewage system",
            "wastewater treatment", "wastewater plant", "wwtp",
            "effluent treatment", "sludge treatment",
            "industrial wastewater", "domestic wastewater",
            "xử lý nước thải",   # VN: wastewater treatment
            "nước thải",         # VN: wastewater
        ],
        "secondary": [
            "sewage", "sewer network", "sewer line",
            "effluent", "sludge",
            "water pollution control",
            "water quality improvement",
        ],
    },

    # ─────────────────────────────────────────────────────────
    # 2. WATER SUPPLY / DRAINAGE  (상수도·배수)
    # ─────────────────────────────────────────────────────────
    "Water Supply/Drainage": {
        "primary": [
            "water supply system", "water supply network",
            "clean water supply", "drinking water supply",
            "tap water", "piped water", "potable water",
            "water treatment plant", "water purification plant",
            "water infrastructure", "water distribution",
            "desalination plant",
            "drainage system", "stormwater management",
            "flood control project", "flood prevention",
            "nước sạch",     # VN: clean water
            "cấp nước",      # VN: water supply
            "thoát nước",    # VN: drainage
        ],
        "secondary": [
            "clean water", "drinking water",
            "water project", "water plant", "water reservoir",
            "groundwater management",
            "flood control", "anti-flooding",
            "water pipeline",
        ],
    },

    # ─────────────────────────────────────────────────────────
    # 3. OIL & GAS
    # ─────────────────────────────────────────────────────────
    "Oil & Gas": {
        "primary": [
            "oil and gas", "oil & gas",
            "petroleum refinery", "oil refinery",
            "offshore oil", "offshore gas", "offshore drilling",
            "lng terminal", "lng plant", "liquefied natural gas",
            "gas pipeline", "oil pipeline",
            "petrovietnam", "pvn", "pvgas", "pv gas",
            "binh son refinery", "nghi son refinery", "dung quat",
            "block b", "ca voi xanh",
            "lô b", "cá voi xanh",   # VN project names
        ],
        "secondary": [
            "petroleum", "petrochemical",
            "natural gas plant", "crude oil",
            "oil exploration", "gas exploration", "drilling",
            "upstream", "downstream", "midstream",
            "gas field", "oil field",
        ],
    },

    # ─────────────────────────────────────────────────────────
    # 4. POWER  (발전·송배전)
    # ─────────────────────────────────────────────────────────
    "Power": {
        "primary": [
            "power plant", "power station", "power project",
            "wind farm", "offshore wind farm", "solar farm",
            "hydroelectric plant", "hydropower plant",
            "transmission line", "high voltage line",
            "power purchase agreement", "ppa",
            "feed-in tariff",
            "battery storage system", "bess",
            "evn", "vietnam electricity",
            "nhà máy điện",         # VN: power plant
            "năng lượng tái tạo",   # VN: renewable energy
            "điện mặt trời",        # VN: solar power
            "điện gió",             # VN: wind power
        ],
        "secondary": [
            "wind power", "solar power", "solar energy", "photovoltaic",
            "renewable energy", "clean energy",
            "thermal power", "coal-fired power",
            "hydropower", "hydroelectric",
            "power generation", "power grid",
            "electricity generation",
            "substation", "transformer station",
            "megawatt", "gigawatt", " mw ", " gw ",
            "energy storage", "energy transition",
            "lng power",
        ],
    },

    # ─────────────────────────────────────────────────────────
    # 5. SOLID WASTE  (고형폐기물)
    # ─────────────────────────────────────────────────────────
    "Solid Waste": {
        "primary": [
            "solid waste management",
            "municipal solid waste", "msw",
            "landfill site", "sanitary landfill",
            "waste-to-energy plant", "wte plant", "wte facility",
            "incineration plant", "incinerator",
            "recycling plant", "recycling facility",
            "hazardous waste facility",
            "rác thải",       # VN: waste
            "rác sinh hoạt",  # VN: household waste
            "lò đốt rác",     # VN: incinerator
            "bãi rác",        # VN: landfill/dump
            "xử lý rác",      # VN: waste treatment
        ],
        "secondary": [
            "solid waste", "garbage collection", "garbage disposal",
            "trash collection",
            "landfill",
            "waste-to-energy", "wte",
            "incineration",
            "composting facility",
            "electronic waste", "e-waste",
            "construction waste disposal",
        ],
    },

    # ─────────────────────────────────────────────────────────
    # 6. TRANSPORT  (교통·물류 인프라)
    # ─────────────────────────────────────────────────────────
    "Transport": {
        "primary": [
            "metro line", "metro project", "metro station",
            "urban rail project", "light rail project",
            "high-speed rail", "high speed rail", "hsr project",
            "railway project", "railroad project",
            "expressway project", "highway project",
            "ring road project", "ring expressway",
            "bridge construction", "cable-stayed bridge",
            "long thanh airport",
            "deep-sea port", "container terminal",
            "tuyến metro",    # VN: metro line
            "đường cao tốc",  # VN: expressway
            "sân bay",        # VN: airport
            "cảng biển",      # VN: seaport
        ],
        "secondary": [
            "metro", "subway",
            "railway", "railroad",
            "expressway", "highway", "motorway",
            "bypass road", "overpass", "flyover", "interchange",
            "road construction", "road upgrade",
            "bridge", "tunnel", "viaduct",
            "airport", "airport terminal", "runway",
            "seaport", "logistics hub", "logistics center",
            "public transport", "bus rapid transit", "brt",
            "inland waterway",
        ],
    },

    # ─────────────────────────────────────────────────────────
    # 7. INDUSTRIAL PARKS  (산업단지)
    # ─────────────────────────────────────────────────────────
    "Industrial Parks": {
        "primary": [
            "industrial park", "industrial zone", "industrial complex",
            "special economic zone", "sez",
            "export processing zone", "epz",
            "hi-tech park", "high-tech park", "technology park",
            "industrial estate", "industrial cluster",
            "khu công nghiệp",    # VN: industrial zone
            "khu kinh tế",        # VN: economic zone
            "khu công nghệ cao",  # VN: hi-tech zone
        ],
        "secondary": [
            "economic zone", "free trade zone",
            "manufacturing hub", "manufacturing zone",
            "factory zone", "industrial area",
            "fdi project",
        ],
    },

    # ─────────────────────────────────────────────────────────
    # 8. SMART CITY  (스마트시티)
    # ─────────────────────────────────────────────────────────
    "Smart City": {
        "primary": [
            "smart city project", "smart city development",
            "intelligent city", "digital city",
            "smart traffic system", "traffic management system",
            "iot infrastructure", "5g network deployment",
            "e-government system", "digital government",
            "thành phố thông minh",  # VN: smart city
        ],
        "secondary": [
            "smart city",
            "smart urban",
            "smart grid", "smart meter",
            "smart building",
            "5g infrastructure",
            "digital transformation",
            "surveillance system", "cctv network", "ai camera",
        ],
    },

    # ─────────────────────────────────────────────────────────
    # 9. CONSTRUCTION  (건설·도시개발)
    # ─────────────────────────────────────────────────────────
    "Construction": {
        "primary": [
            "real estate development", "property development",
            "housing project", "residential complex",
            "new urban area", "new township",
            "satellite city development",
            "commercial building construction",
            "urban development project",
            "khu đô thị",              # VN: urban area
            "dự án bất động sản",      # VN: real estate project
            "bao xay dung",            # VN construction newspaper
        ],
        "secondary": [
            "urban development",
            "city planning", "urban planning",
            "construction project",
            "building construction",
            "urban infrastructure",
            "cement plant", "steel plant",
        ],
    },
}


# ============================================================
# EXCLUDE KEYWORDS — 대폭 보강
# [검증보고서] 실제 오분류 사례 기반: 결혼, 자동차, 항공노선, 해외사건 등 추가
# [Genspark]  Context Check: bridge tournament, party congress 등
# ============================================================

EXCLUDE_KEYWORDS = [
    # 범죄·사법
    "arrest", "jail", "prison", "sentenced", "trafficking", "smuggling",
    "fraud", "murder", "crime", "drug trafficking",
    # 사고·재해 (인명피해 중심)
    "killed", "death toll", "crash kills", "fire kills", "collision kills",
    "accident kills", "flood kills",
    # 스포츠·엔터테인먼트
    "football", "soccer", "tennis", "basketball", "volleyball", "badminton",
    "sports", "world cup", "olympics", "championship", "tournament",
    "golf tournament", "bridge tournament",
    # 금융·비(非)인프라 경제
    "gold price", "stock market", "forex", "exchange rate",
    "cryptocurrency", "bitcoin",
    "seafood export", "agricultural export", "rice export",
    # 관광·호텔·소매
    "tourism promotion", "tourist", "hotel resort", "beach resort",
    "retail sales",
    # 교육·사회
    "university", "school enrollment", "scholarship",
    "beauty pageant", "fashion", "concert",
    # [검증보고서] 실제 오분류 사례
    "matchmaking", "get married", "marriage club",        # 결혼 뉴스
    "safety certification", "vinfast vf",                 # 자동차 인증
    "night flights", "flight schedule", "airline route",  # 항공노선 (인프라 아님)
    "train collision in spain", "earthquake in",          # 명백한 해외 사건
    # 정치 (인프라 무관)
    "party congress", "politburo", "state visit", "diplomatic",
    # 내비게이션 요소 (정크)
    "multimedia", "social links", "subscribe",
]

# 비베트남 국가 필터
NON_VIETNAM_COUNTRIES = [
    "singapore", "malaysia", "thailand", "indonesia", "philippines",
    "cambodia", "laos", "myanmar", "china", "japan", "south korea",
    "taiwan", "hong kong", "australia", "russia", " uk ", " usa ",
    "america", "india", "europe", "africa",
]

VIETNAM_KEYWORDS = [
    "vietnam", "vietnamese", "viet nam",
    "hanoi", "ho chi minh", "hcmc", "saigon",
    "da nang", "hai phong", "can tho",
    "binh duong", "dong nai", "quang ninh",
    "mekong", "evn", "petrovietnam", "pvn",
    "việt nam",
]


# ============================================================
# PROVINCE KEYWORDS — 강화판
# [검증보고서] 'Vietnam' 통칭 1,024건 → 성별 추출 강화
# ============================================================

PROVINCE_KEYWORDS = {
    "Ho Chi Minh City":  ["ho chi minh", "hcmc", "saigon", "sai gon", "hồ chí minh", "tp.hcm", "tp hcm"],
    "Hanoi":             ["hanoi", "ha noi", "hà nội", "capital hanoi"],
    "Da Nang":           ["da nang", "đà nẵng", "danang"],
    "Hai Phong":         ["hai phong", "hải phòng", "haiphong"],
    "Can Tho":           ["can tho", "cần thơ"],
    "Binh Duong":        ["binh duong", "bình dương"],
    "Dong Nai":          ["dong nai", "đồng nai"],
    "Ba Ria - Vung Tau": ["ba ria", "vung tau", "vũng tàu", "bà rịa"],
    "Long An":           ["long an"],
    "Quang Ninh":        ["quang ninh", "quảng ninh", "ha long bay", "hạ long"],
    "Bac Ninh":          ["bac ninh", "bắc ninh"],
    "Hai Duong":         ["hai duong", "hải dương"],
    "Hung Yen":          ["hung yen", "hưng yên"],
    "Vinh Phuc":         ["vinh phuc", "vĩnh phúc"],
    "Thai Nguyen":       ["thai nguyen", "thái nguyên"],
    "Bac Giang":         ["bac giang", "bắc giang"],
    "Phu Tho":           ["phu tho", "phú thọ"],
    "Hoa Binh":          ["hoa binh", "hòa bình"],
    "Thanh Hoa":         ["thanh hoa", "thanh hoá", "thanh hóa"],
    "Nghe An":           ["nghe an", "nghệ an"],
    "Ha Tinh":           ["ha tinh", "hà tĩnh"],
    "Quang Binh":        ["quang binh", "quảng bình"],
    "Thua Thien Hue":    ["thua thien hue", "huế", " hue ", "thua thien"],
    "Quang Nam":         ["quang nam", "quảng nam"],
    "Quang Ngai":        ["quang ngai", "quảng ngãi"],
    "Binh Dinh":         ["binh dinh", "bình định"],
    "Khanh Hoa":         ["khanh hoa", "khánh hòa", "nha trang"],
    "Lam Dong":          ["lam dong", "lâm đồng", "da lat", "đà lạt", "dalat"],
    "Dak Lak":           ["dak lak", "đắk lắk", "buon ma thuot"],
    "Gia Lai":           ["gia lai"],
    "Kon Tum":           ["kon tum"],
    "Tien Giang":        ["tien giang", "tiền giang"],
    "Ben Tre":           ["ben tre", "bến tre"],
    "Vinh Long":         ["vinh long", "vĩnh long"],
    "Dong Thap":         ["dong thap", "đồng tháp"],
    "An Giang":          ["an giang"],
    "Kien Giang":        ["kien giang", "kiên giang", "phu quoc", "phú quốc"],
    "Ca Mau":            ["ca mau", "cà mau"],
    "Long Thanh":        ["long thanh airport", "long thành airport"],
    "Mekong Delta":      ["mekong delta", "mekong region"],
    "Central Highlands": ["central highlands", "tay nguyen"],
}


# ============================================================
# RSS FEEDS — 59개 소스 (v5.1 유지 + 검증보고서 권장 추가)
# ============================================================

RSS_FEEDS = {
    # ── 영문 주요 소스 ─────────────────────────────────────────
    "VnExpress English - News":        "https://e.vnexpress.net/rss/news.rss",
    "VnExpress English - Business":    "https://e.vnexpress.net/rss/business.rss",
    "Vietnam News - Economy":          "https://vietnamnews.vn/rss/economy.rss",
    "Vietnam News - Environment":      "https://vietnamnews.vn/rss/environment.rss",
    "Vietnam News - Society":          "https://vietnamnews.vn/rss/society.rss",
    "VietnamPlus English":             "https://en.vietnamplus.vn/rss/news.rss",
    "Hanoi Times":                     "https://hanoitimes.vn/rss/news.rss",
    "VietnamNet English":              "https://vietnamnet.vn/en/rss/home.rss",
    "The Investor":                    "https://theinvestor.vn/feed",
    "VIR":                             "https://vir.com.vn/rss/all.rss",
    "Tuoi Tre News":                   "https://tuoitrenews.vn/rss/all.rss",
    "SGGP News English":               "https://en.sggp.org.vn/rss/home.rss",
    "VOV World":                       "https://vovworld.vn/en-US/rss/all.rss",
    "Nhan Dan English":                "https://en.nhandan.vn/rss/home.rss",
    "VCCINEWS":                        "https://vccinews.com/rss/news.rss",
    # ── 영문 전문 소스 ─────────────────────────────────────────
    "Vietnam Energy Magazine EN":      "https://vietnamenergy.vn/en/rss/news.rss",
    "PV-Tech":                         "https://www.pv-tech.org/feed/",
    "Offshore Energy":                 "https://www.offshore-energy.biz/feed/",
    # ── 베트남어 일반 ──────────────────────────────────────────
    "VnExpress - Kinh doanh":         "https://vnexpress.net/rss/kinh-doanh.rss",
    "VnExpress - Thời sự":            "https://vnexpress.net/rss/thoi-su.rss",
    "Tuoi Tre - Kinh doanh":          "https://tuoitre.vn/rss/kinh-doanh.rss",
    "Thanh Nien - Kinh te":           "https://thanhnien.vn/rss/kinh-te.rss",
    "VietnamNet - Kinh doanh":        "https://vietnamnet.vn/rss/kinh-doanh.rss",
    "Dan Tri - Kinh doanh":           "https://dantri.com.vn/rss/kinh-doanh.rss",
    "CafeBiz":                        "https://cafebiz.vn/rss/home.rss",
    "Bao Dau Tu":                     "https://baodautu.vn/rss/home.rss",
    "Nhadautu.vn":                    "https://nhadautu.vn/rss/home.rss",
    "CafeF":                          "https://cafef.vn/rss/home.rss",
    # ── 베트남어 전문 소스 ─────────────────────────────────────
    "Nang Luong Vietnam":             "https://nangluongvietnam.vn/rss/home.rss",
    "Vietnam Energy Magazine":        "https://vietnamenergy.vn/rss/home.rss",
    "Bao Xay Dung":                   "https://baoxaydung.com.vn/rss/home.rss",       # [검증보고서] 우선추가
    "Bao TN Moi Truong":             "https://baotainguyenmoitruong.vn/rss/tin-tuc.rss",
    "Kinh Te Moi Truong":            "https://kinhtemoitruong.vn/rss/home.rss",
    "Moi Truong Va Do Thi":          "https://moitruongdothi.vn/rss/home.rss",
    "Tap Chi Moi Truong":            "https://tapchimoitruong.vn/rss/home.rss",
    "Nong Nghiep VN":                "https://nongnghiep.vn/rss/home.rss",
    # ── 북부 지역 ─────────────────────────────────────────────
    "Hanoi Moi":                      "https://hanoimoi.vn/rss/tin-tuc.rss",
    "Bao Quang Ninh EN":              "https://english.baoquangninh.vn/rss/news.rss",
    "Bao Bac Giang EN":               "https://en.baobacgiang.vn/rss/news.rss",
    "Bao Thai Binh":                  "https://baothaibinh.com.vn/rss/home.rss",
    "Bao Hoa Binh":                   "https://baohoabinh.com.vn/rss/home.rss",
    # ── 중부 지역 ─────────────────────────────────────────────
    "Bao Nghe An":                    "https://baonghean.vn/rss/home.rss",
    "Bao Ha Tinh":                    "https://baohatinh.vn/rss/home.rss",
    "Da Nang Today":                  "https://danangtoday.com.vn/rss/news.rss",
    "Bao Binh Dinh":                  "https://baobinhdinh.vn/rss/home.rss",
    # ── 남부 지역 ─────────────────────────────────────────────
    "SGGP":                           "https://www.sggp.org.vn/rss/home.rss",
    "Bao Dong Nai":                   "https://baodongnai.com.vn/rss/home.rss",
    "Bao Binh Duong":                 "https://baobinhduong.vn/rss/home.rss",
    "Bao Da Nang":                    "https://baodanang.vn/rss/home.rss",
    # ── 메콩 델타 ─────────────────────────────────────────────
    "Bao Can Tho":                    "https://baocantho.com.vn/rss/home.rss",
    "Bao An Giang":                   "https://baoangiang.com.vn/rss/home.rss",
    "Bao Kien Giang":                 "https://baokiengiang.vn/rss/home.rss",
}


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def log(msg):
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {msg}")


def clean_html(text):
    if not text:
        return ""
    soup = BeautifulSoup(text, 'html.parser')
    return html.unescape(soup.get_text(separator=' ', strip=True))


def generate_url_hash(url):
    return hashlib.md5(url.encode()).hexdigest()


def is_english_text(title):
    if not title:
        return False
    ascii_cnt = sum(1 for c in title if c.isascii() and c.isalpha())
    non_ascii  = sum(1 for c in title if not c.isascii())
    total = ascii_cnt + non_ascii
    return (ascii_cnt / total) > 0.7 if total else False


def is_vietnamese_text(title):
    if not title:
        return False
    vn_chars = set('àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ'
                   'ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ')
    return any(c in vn_chars for c in title)


def passes_language_filter(title, mode=None):
    m = mode or LANGUAGE_FILTER
    if m == 'all':
        return True
    elif m == 'vietnamese':
        return is_vietnamese_text(title) or not is_english_text(title)
    else:  # 'english'
        return is_english_text(title)


def is_vietnam_related(title, summary=""):
    text = f"{title} {summary}".lower()
    if not any(kw in text for kw in VIETNAM_KEYWORDS):
        return False
    for country in NON_VIETNAM_COUNTRIES:
        if country in text and text.count("vietnam") < text.count(country):
            return False
    return True


def should_exclude(title, summary=""):
    """
    [검증보고서] 강화된 제외 로직
    - 최소 길이 체크 (정크 제목 차단)
    - EXCLUDE_KEYWORDS 전체 스캔
    """
    if not title or len(title.strip()) < 15:
        return True
    text = f"{title} {summary}".lower()
    return any(kw in text for kw in EXCLUDE_KEYWORDS)


def extract_province(title, summary="", full_text=""):
    """
    [검증보고서] Province 추출 강화:
    - 제목 → 요약 → 본문 전체 순서로 스캔
    - 더 많은 별칭 커버
    """
    combined = f"{title} {summary} {full_text}".lower()
    for province, keywords in PROVINCE_KEYWORDS.items():
        for kw in keywords:
            if kw in combined:
                return province
    return "Vietnam"


# ============================================================
# CLASSIFY SECTOR — 가중치 점수제 (검증보고서 권장방식)
# [검증보고서] 제목 primary=3점, 본문 primary=1점
#              제목 secondary=2점, 본문 secondary=1점
#              최소 임계값 3점 미만 → None 반환
# [Genspark]  confidence_score 반환 (QC 에이전트 연계)
# ============================================================

def classify_sector(title, summary=""):
    """
    가중치 기반 섹터 분류.
    Returns: (sector, area, confidence_score) tuple
             None, None, 0 if excluded or below threshold
    """
    if should_exclude(title, summary):
        return None, None, 0

    text_title = title.lower()
    text_full  = f"{title} {summary}".lower()

    scores = {}
    for sector, kw_dict in SECTOR_KEYWORDS.items():
        score = 0
        for kw in kw_dict.get("primary", []):
            if kw in text_title:
                score += 3
            elif kw in text_full:
                score += 1
        for kw in kw_dict.get("secondary", []):
            if kw in text_title:
                score += 2
            elif kw in text_full:
                score += 1
        scores[sector] = score

    if not scores:
        return None, None, 0

    best_sector = max(scores, key=scores.get)
    best_score  = scores[best_sector]

    if best_score < MIN_CLASSIFY_THRESHOLD:
        return None, None, 0

    # confidence: 0~100 (최대 20점 기준 정규화)
    confidence = min(100, int(best_score / 20 * 100))

    return best_sector, SECTOR_AREA[best_sector], confidence


# ============================================================
# RSS FETCH
# ============================================================

def parse_date(date_str):
    if not date_str:
        return None
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str)
    except Exception:
        pass
    return None


def fetch_rss(url, timeout=30):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*',
    }
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', resp.text)
        return feedparser.parse(content)
    except Exception as e:
        log(f"  RSS error [{url}]: {e}")
        return type('Feed', (), {'entries': [], 'bozo': True})()


# ============================================================
# GOOGLE NEWS API — [검증보고서] Nikkei/Reuters 보완
# ============================================================

def fetch_gnews(query, hours_back=24, max_articles=20):
    """
    Google News API를 통해 Nikkei, Reuters 등 RSS 미지원 소스 보완.
    GNEWS_API_KEY 환경변수 필요. https://gnews.io 무료 플랜 사용 가능.
    """
    if not GNEWS_API_KEY:
        return []

    articles = []
    try:
        from_dt = (datetime.utcnow() - timedelta(hours=hours_back)).strftime('%Y-%m-%dT%H:%M:%SZ')
        url = (
            f"https://gnews.io/api/v4/search"
            f"?q={quote(query)}"
            f"&lang=en&country=vn"
            f"&from={from_dt}"
            f"&max={max_articles}"
            f"&apikey={GNEWS_API_KEY}"
        )
        resp = requests.get(url, timeout=15)
        data = resp.json()
        for item in data.get('articles', []):
            articles.append({
                'title':          item.get('title', ''),
                'url':            item.get('url', ''),
                'published_date': item.get('publishedAt', '')[:10],
                'source_name':    item.get('source', {}).get('name', 'GNews'),
                'raw_summary':    item.get('description', ''),
            })
        log(f"GNews: {len(articles)} articles for query '{query}'")
    except Exception as e:
        log(f"GNews error: {e}")
    return articles


# ============================================================
# DATABASE
# ============================================================

def init_database(db_path):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            url_hash       TEXT UNIQUE,
            url            TEXT,
            title          TEXT,
            title_vi       TEXT,
            title_ko       TEXT,
            summary        TEXT,
            summary_vi     TEXT,
            summary_ko     TEXT,
            source         TEXT,
            sector         TEXT,
            area           TEXT,
            province       TEXT,
            confidence     INTEGER DEFAULT 0,
            published_date TEXT,
            collected_date TEXT,
            processed      INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    return conn


def get_existing_hashes(conn):
    cur = conn.execute("SELECT url_hash FROM articles")
    return {row[0] for row in cur.fetchall()}


def save_article(conn, article):
    try:
        conn.execute('''
            INSERT INTO articles
              (url_hash, url, title, summary, source,
               sector, area, province, confidence,
               published_date, collected_date)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ''', (
            article['url_hash'], article['url'], article['title'],
            article.get('summary', ''), article['source'],
            article['sector'], article.get('area', ''),
            article.get('province', 'Vietnam'),
            article.get('confidence', 0),
            article.get('published_date', ''),
            datetime.now().isoformat(),
        ))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


# ============================================================
# MAIN COLLECTION
# ============================================================

def collect_news(hours_back=24):
    """
    Main entry point. Returns (count, articles_list, stats_dict).
    articles_list items follow Genspark JSON output format:
      { url, title, published_date, source_name, raw_summary,
        sector, area, province, confidence }
    """
    conn             = init_database(DB_PATH)
    existing_hashes  = get_existing_hashes(conn)
    cutoff           = datetime.now() - timedelta(hours=hours_back)

    log(f"Cutoff: {cutoff:%Y-%m-%d %H:%M} | Language: {LANGUAGE_FILTER} | Threshold: {MIN_CLASSIFY_THRESHOLD}")

    total_collected   = 0
    collected_articles = []
    collection_stats   = {}

    # ── RSS collection ──────────────────────────────────────
    log(f"RSS feeds: {len(RSS_FEEDS)}")
    for source_name, feed_url in RSS_FEEDS.items():
        stats = {
            'url': feed_url, 'status': 'Unknown',
            'last_check': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'entries_found': 0, 'collected': 0, 'error': '',
        }
        collection_stats[source_name] = stats

        feed = fetch_rss(feed_url)
        if feed.bozo and not feed.entries:
            stats['status'] = 'Failed'
            stats['error']  = 'Feed error or empty'
            continue

        stats['entries_found'] = len(feed.entries)
        stats['status']        = 'Success'
        source_cnt = 0

        for entry in feed.entries:
            title   = clean_html(getattr(entry, 'title', ''))
            link    = getattr(entry, 'link', '')
            summary = clean_html(getattr(entry, 'summary',
                                          getattr(entry, 'description', '')))
            pubdate = getattr(entry, 'published', getattr(entry, 'pubDate', ''))

            if not title or not passes_language_filter(title):
                continue

            url_hash = generate_url_hash(link)
            if url_hash in existing_hashes:
                continue

            pub_dt = parse_date(pubdate)
            if pub_dt:
                if pub_dt.tzinfo:
                    pub_dt = pub_dt.replace(tzinfo=None)
                if pub_dt < cutoff:
                    continue

            if not is_vietnam_related(title, summary):
                continue

            sector, area, confidence = classify_sector(title, summary)
            if not sector:
                continue

            province = extract_province(title, summary)

            article = {
                'url_hash':       url_hash,
                'url':            link,
                'title':          title,
                'summary':        summary[:1000] if summary else '',
                'source':         source_name,
                'source_name':    source_name,
                'sector':         sector,
                'area':           area,
                'province':       province,
                'confidence':     confidence,
                'published_date': pub_dt.isoformat() if pub_dt else '',
                'raw_summary':    summary[:500] if summary else '',
            }

            if save_article(conn, article):
                existing_hashes.add(url_hash)
                source_cnt    += 1
                total_collected += 1
                collected_articles.append(article)
                log(f"  SAVED [{sector}|{confidence}%] [{province}] {title[:55]}...")

        stats['collected'] = source_cnt

    # ── Google News (보완 채널) ─────────────────────────────
    if ENABLE_GNEWS:
        log("GNews: fetching supplemental articles...")
        gnews_raw = fetch_gnews(GNEWS_QUERY, hours_back)
        for item in gnews_raw:
            title   = item.get('title', '')
            link    = item.get('url', '')
            summary = item.get('raw_summary', '')

            if not title or not is_vietnam_related(title, summary):
                continue

            url_hash = generate_url_hash(link)
            if url_hash in existing_hashes:
                continue

            sector, area, confidence = classify_sector(title, summary)
            if not sector:
                continue

            province = extract_province(title, summary)
            article  = {
                'url_hash': url_hash, 'url': link,
                'title': title, 'summary': summary[:1000],
                'source': item.get('source_name', 'GNews'),
                'source_name': item.get('source_name', 'GNews'),
                'sector': sector, 'area': area,
                'province': province, 'confidence': confidence,
                'published_date': item.get('published_date', ''),
                'raw_summary': summary[:500],
            }
            if save_article(conn, article):
                existing_hashes.add(url_hash)
                total_collected += 1
                collected_articles.append(article)

    conn.close()

    # ── Summary ─────────────────────────────────────────────
    from collections import Counter
    sector_counts  = Counter(a['sector']   for a in collected_articles)
    province_counts = Counter(a['province'] for a in collected_articles)
    low_conf = sum(1 for a in collected_articles if a.get('confidence', 0) < 50)

    print("\n" + "=" * 60)
    print(f"COLLECTION COMPLETE  |  {total_collected} articles")
    print("-" * 60)
    print("Sector breakdown:")
    for s, c in sector_counts.most_common():
        print(f"  {s:<28} {c:3d}")
    print(f"\nLow-confidence articles (<50%): {low_conf}")
    print(f"Top province: {province_counts.most_common(1)}")
    print("=" * 60)

    return total_collected, collected_articles, collection_stats


# ============================================================
# EXCEL UPDATE
# ============================================================

def update_excel_database(articles, collection_stats=None):
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment
        import shutil
    except ImportError:
        log("openpyxl not installed — skipping Excel update")
        return False

    ep = Path(EXCEL_PATH)
    if not ep.exists():
        log(f"Excel not found: {ep}")
        return False

    # Safety check
    try:
        wb_c = openpyxl.load_workbook(ep, read_only=True)
        ws_c = wb_c.active
        existing_count = sum(1 for r in ws_c.iter_rows(min_row=2, values_only=True) if any(r))
        wb_c.close()
        if existing_count < 100:
            log(f"Safety check failed: only {existing_count} rows")
            return False
    except Exception as e:
        log(f"Safety check error: {e}")
        return False

    # Backup
    try:
        shutil.copy2(ep, ep.with_suffix('.xlsx.backup'))
    except Exception:
        pass

    try:
        wb = openpyxl.load_workbook(ep)
        ws = wb.active
        last_row = ws.max_row

        # Build existing URL set
        existing_urls = set()
        url_col = None
        for col in range(1, ws.max_column + 1):
            h = ws.cell(row=1, column=col).value
            if h and "link" in str(h).lower():
                url_col = col
                break
        if url_col:
            for row in range(2, last_row + 1):
                v = ws.cell(row=row, column=url_col).value
                if v:
                    existing_urls.add(v)

        col_map = {
            'area': 1, 'sector': 2, 'province': 3, 'title': 4,
            'date': 5, 'source': 6, 'url': 7, 'summary': 8,
        }

        added = 0
        for art in articles:
            if art.get('url') in existing_urls:
                continue
            nr = last_row + 1 + added
            ws.cell(row=nr, column=col_map['area'],    value=art.get('area', ''))
            ws.cell(row=nr, column=col_map['sector'],  value=art.get('sector', ''))
            ws.cell(row=nr, column=col_map['province'], value=art.get('province', 'Vietnam'))
            ws.cell(row=nr, column=col_map['title'],   value=art.get('title', ''))
            ws.cell(row=nr, column=col_map['date'],    value=(art.get('published_date', '') or '')[:10])
            ws.cell(row=nr, column=col_map['source'],  value=art.get('source', ''))
            ws.cell(row=nr, column=col_map['url'],     value=art.get('url', ''))
            ws.cell(row=nr, column=col_map['summary'], value=art.get('summary', '')[:500])
            added += 1
            existing_urls.add(art.get('url'))

        # Update RSS_Sources sheet
        if collection_stats:
            if "RSS_Sources" in wb.sheetnames:
                wb.remove(wb["RSS_Sources"])
            ws_rss = wb.create_sheet("RSS_Sources")
            hdr_fill = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid")
            for ci, h in enumerate(["Source", "URL", "Status", "Last Check",
                                    "Entries", "Collected", "Error"], 1):
                c = ws_rss.cell(row=1, column=ci, value=h)
                c.fill = hdr_fill
                c.font = Font(bold=True, color="FFFFFF")
            for ri, (src, st) in enumerate(collection_stats.items(), 2):
                ws_rss.cell(row=ri, column=1, value=src)
                ws_rss.cell(row=ri, column=2, value=st.get('url', ''))
                ws_rss.cell(row=ri, column=3, value=st.get('status', ''))
                ws_rss.cell(row=ri, column=4, value=st.get('last_check', ''))
                ws_rss.cell(row=ri, column=5, value=st.get('entries_found', 0))
                ws_rss.cell(row=ri, column=6, value=st.get('collected', 0))
                ws_rss.cell(row=ri, column=7, value=st.get('error', ''))
                if st.get('status') == 'Success':
                    ws_rss.cell(row=ri, column=3).fill = PatternFill(
                        start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")
                elif st.get('status') == 'Failed':
                    ws_rss.cell(row=ri, column=3).fill = PatternFill(
                        start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")

        wb.save(ep)
        wb.close()
        log(f"Excel updated: +{added} articles  |  total {last_row - 1 + added}")
        return True

    except Exception as e:
        log(f"Excel update error: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description='Vietnam Infra News Collector v5.2')
    p.add_argument('--hours-back', type=int, default=HOURS_BACK)
    p.add_argument('--threshold',  type=int, default=MIN_CLASSIFY_THRESHOLD,
                   help='Min classification score (default: 3)')
    p.add_argument('--gnews',      action='store_true', help='Enable Google News API')
    args = p.parse_args()

    HOURS_BACK              = args.hours_back
    MIN_CLASSIFY_THRESHOLD  = args.threshold
    if args.gnews:
        ENABLE_GNEWS = True

    print("=" * 60)
    print("VIETNAM INFRASTRUCTURE NEWS COLLECTOR  v5.2")
    print(f"Hours back: {HOURS_BACK} | Threshold: {MIN_CLASSIFY_THRESHOLD} | Language: {LANGUAGE_FILTER}")
    print("=" * 60)

    cnt, arts, stats = collect_news(HOURS_BACK)
    update_excel_database(arts, stats)

    print("\nRSS SOURCE STATUS:")
    for src, st in stats.items():
        icon = "✓" if st['status'] == 'Success' else "✗"
        print(f"  {icon} {src}: {st['entries_found']} entries → {st['collected']} collected")

    print(f"\nTOTAL: {cnt} new articles collected")
