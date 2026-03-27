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
MIN_CLASSIFY_THRESHOLD = 2  # 베트남어 기사 포용 (제목 secondary 키워드 2점으로 분류)

# Google News API (Nikkei/Reuters 보완용)
GNEWS_API_KEY    = os.environ.get('GNEWS_API_KEY', '')
ENABLE_GNEWS     = os.environ.get('ENABLE_GNEWS', 'false').lower() == 'true'
GNEWS_QUERY      = 'Vietnam infrastructure OR "Vietnam energy" OR "Vietnam transport"'
GNEWS_ENV_QUERY  = 'Vietnam environment OR "Vietnam wastewater" OR "Vietnam solid waste" OR "Vietnam water supply"'


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
            "chống ngập",             # VN: flood prevention
            "hồ chứa nước",            # VN: reservoir
            "nhà máy nước",            # VN: water plant
            "nước sinh hoạt",          # VN: household water
            "lũ lụt",                  # VN: flood
            "hạn hán",                 # VN: drought
            "nước mưa",                # VN: rainwater
            "ngập úng",                # VN: waterlogging
            "biến đổi khí hậu",        # VN: climate change
            "khí hậu",                 # VN: climate
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
            "thủy điện",            # VN: hydropower
            "nhiệt điện",           # VN: thermal power
            "lưới điện",            # VN: power grid
            "truyền tải điện",      # VN: power transmission
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
            "chất thải rắn",  # VN: solid waste
            "nhà máy xử lý rác",  # VN: waste treatment plant
            "thu gom rác",              # VN: waste collection
            "đốt rác phát điện",        # VN: waste-to-energy
            "ô nhiễm môi trường",       # VN: env pollution
            "ô nhiễm",                  # VN: pollution
            "phân loại rác",            # VN: waste sorting
            "không khí",                # VN: air quality
            "phát thải",                # VN: emissions
            "môi trường",               # VN: environment (critical)
            "tài nguyên môi trường",    # VN: natural resources & env
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
    # ── 환경/에너지 전문 소스 (신규 추가) ─────────────────────────
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
    # 영문 표기
    "vietnam", "vietnamese", "viet nam",
    "hanoi", "ho chi minh", "hcmc", "saigon",
    "da nang", "hai phong", "can tho",
    "binh duong", "dong nai", "quang ninh",
    "mekong", "evn", "petrovietnam", "pvn",
    # 베트남어 발음부호 형태 (베트남어 기사 감지용)
    "việt nam", "hà nội", "tp.hcm", "tp hcm",
    "đà nẵng", "hải phòng", "cần thơ",
    "bình dương", "đồng nai", "quảng ninh",
    "hà long", "bắc ninh", "long an",
    "quảng ngãi", "bình định", "khánh hòa",
    "lâm đồng", "đắk lắk", "gia lai",
    "tiền giang", "bến tre", "an giang",
    "kiên giang", "cà mau", "sóc trăng",
    "thanh hoá", "nghệ an", "hà tĩnh",
    "quảng bình", "quảng trị", "thừa thiên",
    "thái nguyên", "bắc giang", "hưng yên",
    "vĩnh phúc", "phú thọ", "hòa bình",
    # 공기업/기관 베트남어
    "tập đoàn điện lực", "tập đoàn dầu khí",
    # 추가: 환경부처 + 메콩 델타 + 기후 관련
    "bộ tài nguyên",          # Ministry of Natural Resources
    "tài nguyên và môi trường",  # Natural resources & environment
    "sông cửu long",          # Mekong River (Cuu Long)
    "đồng bằng sông",         # River delta
    "cửu long",               # Mekong (Cuu Long)
    "miền trung",             # Central Vietnam
    "miền nam",               # Southern Vietnam
    "miền bắc",               # Northern Vietnam
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
    "Tuoi Tre News":                   "https://tuoitre.vn/rss/tin-moi-nhat.rss",
    "SGGP News English":               "https://en.sggp.org.vn/rss/home.rss",
    "Nhan Dan English":                "https://en.nhandan.vn/rss/home.rss",
    # ── 영문 전문 소스 ─────────────────────────────────────────
    "PV-Tech":                         "https://www.pv-tech.org/feed/",
    # ── 베트남어 일반 ──────────────────────────────────────────
    "VnExpress - Kinh doanh":         "https://vnexpress.net/rss/kinh-doanh.rss",
    "VnExpress - Thời sự":            "https://vnexpress.net/rss/thoi-su.rss",
    "Tuoi Tre - Kinh doanh":          "https://tuoitre.vn/rss/kinh-doanh.rss",
    "Thanh Nien - Kinh te":           "https://thanhnien.vn/rss/kinh-te.rss",
    "VietnamNet - Kinh doanh":        "https://vietnamnet.vn/rss/kinh-doanh.rss",
    "Dan Tri - Kinh doanh":           "https://dantri.com.vn/rss/kinh-doanh.rss",
    "CafeBiz":                        "https://cafebiz.vn/rss/home.rss",
    # ── 베트남어 전문 소스 ─────────────────────────────────────
    "Bao Xay Dung":                   "https://baoxaydung.com.vn/rss/home.rss",       # [검증보고서] 우선추가
    # ── 북부 지역 ─────────────────────────────────────────────
    # ── 중부 지역 ─────────────────────────────────────────────
    "Bao Ha Tinh":                    "https://baohatinh.vn/rss/home.rss",
    "Bao Binh Dinh":                  "https://baobinhdinh.vn/rss/home.rss",
    # ── 남부 지역 ─────────────────────────────────────────────
    "SGGP":                           "https://www.sggp.org.vn/rss/home.rss",
    # ── 메콩 델타 ─────────────────────────────────────────────
    # ── 환경/에너지 전문 소스 ──────────────────────────────────
    "VietnamPlus - Moi truong":      "https://www.vietnamplus.vn/rss/moitruong.rss",
    "Nhandan - Moi truong":          "https://nhandan.vn/rss/moi-truong.rss",
    "Bao Dau Tu - Energy":           "https://baodautu.vn/rss/nang-luong.rss",
    "Vietnam Energy alt":            "https://vietnamenergy.vn/rss/tin-tuc.rss",
    "Tap chi Xay dung":              "https://tapchixaydung.vn/rss/home.rss",
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
    NewsData.io API — 상업용 무료 (200크레딧/일), 베트남어 지원, 89개 언어.
    GNEWS_API_KEY 환경변수에 NewsData.io 키를 설정하면 작동.
    gnews.io 키도 지원 (자동 감지).
    """
    if not GNEWS_API_KEY:
        return []

    articles = []
    try:
        # NewsData.io API (pub_로 시작하면 NewsData, 아니면 gnews.io)
        is_newsdata = GNEWS_API_KEY.startswith('pub_')

        if is_newsdata:
            url = (
                f"https://newsdata.io/api/1/news"
                f"?apikey={GNEWS_API_KEY}"
                f"&q={quote(query)}"
                f"&country=vn"
                f"&language=en,vi"
                f"&category=business,politics,technology"
                f"&size={min(max_articles, 10)}"
            )
            resp = requests.get(url, timeout=15)
            data = resp.json()
            for item in data.get('results', []):
                title = item.get('title', '') or ''
                if not title or len(title.strip()) < 15:
                    continue
                articles.append({
                    'title':          title,
                    'url':            item.get('link', ''),
                    'published_date': (item.get('pubDate', '') or '')[:10],
                    'source_name':    item.get('source_id', 'NewsData'),
                    'raw_summary':    item.get('description', '') or '',
                })
            log(f"NewsData.io: {len(articles)} articles for query '{query[:50]}'")
        else:
            # gnews.io fallback
            from_dt = (datetime.utcnow() - timedelta(hours=min(hours_back,720))).strftime('%Y-%m-%dT%H:%M:%SZ')
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
            log(f"GNews: {len(articles)} articles for query '{query[:50]}'")

    except Exception as e:
        log(f"News API error: {e}")
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
        log("GNews: fetching supplemental articles (infra + environment)...")
        gnews_raw = fetch_gnews(GNEWS_QUERY, hours_back)
        gnews_raw += fetch_gnews(GNEWS_ENV_QUERY, hours_back, max_articles=15)
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

def update_excel_database(articles, collection_stats=None, excel_path=None):
    """
    Excel DB 완전 업데이트:
    - 신규기사 노란색(#FFF9C4) 하이라이트
    - 전체 날짜순 정렬 (최신→오래된)
    - Area별 색상 구분 (환경=녹, 에너지=황, 도시=보라)
    - Collection_Log 시트 업데이트
    - RSS_Sources 시트 업데이트
    - Summary 시트 업데이트
    """
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from collections import Counter
        import shutil
    except ImportError:
        log("openpyxl not installed")
        return False

    # excel_path 파라미터 > EXCEL_PATH 환경변수 > 기본값 순서로 우선 적용
    _ep_str = excel_path or os.environ.get('EXCEL_PATH', EXCEL_PATH)
    ep = Path(_ep_str)
    if not ep.exists():
        log(f"Excel not found: {ep}")
        return False

    # 안전 확인
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

    try:
        shutil.copy2(ep, ep.with_suffix('.xlsx.backup'))
    except Exception:
        pass

    try:
        wb  = openpyxl.load_workbook(ep)
        ws  = wb.active
        last_row = ws.max_row

        # URL 컬럼 찾기
        url_col = 7
        for c in range(1, ws.max_column + 1):
            h = ws.cell(row=1, column=c).value
            if h and "link" in str(h).lower():
                url_col = c
                break

        # 기존 URL 수집
        existing_urls = set()
        for row in range(2, last_row + 1):
            v = ws.cell(row=row, column=url_col).value
            if v:
                existing_urls.add(v)

        # ── 스타일 ───────────────────────────────────────────
        NEW_FILL    = PatternFill(start_color="FFF9C4", end_color="FFF9C4", fill_type="solid")
        NEW_FONT    = Font(bold=True, color="1A1A1A", size=10)
        ENV_FILL    = PatternFill(start_color="F0FDF4", end_color="F0FDF4", fill_type="solid")
        ENERGY_FILL = PatternFill(start_color="FFFBEB", end_color="FFFBEB", fill_type="solid")
        URBAN_FILL  = PatternFill(start_color="F5F3FF", end_color="F5F3FF", fill_type="solid")
        PLAIN_FONT  = Font(color="1A1A1A", size=10)
        HDR_FILL    = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid")
        HDR_FONT    = Font(bold=True, color="FFFFFF", size=10)
        thin_side   = Side(style='thin', color='E2E8F0')
        thin_border = Border(bottom=thin_side)

        col_map = {'area':1,'sector':2,'province':3,'title':4,'date':5,'source':6,'url':7,'summary':8}

        def area_fill(area):
            a = str(area).lower()
            if 'environment' in a: return ENV_FILL
            if 'energy' in a:      return ENERGY_FILL
            return URBAN_FILL

        # ── 신규기사 추가 ────────────────────────────────────
        added    = 0
        new_urls = set()
        for art in articles:
            if art.get('url') in existing_urls:
                continue
            nr = last_row + 1 + added
            ws.cell(row=nr, column=col_map['area'],     value=art.get('area', ''))
            ws.cell(row=nr, column=col_map['sector'],   value=art.get('sector', ''))
            ws.cell(row=nr, column=col_map['province'], value=art.get('province', 'Vietnam'))
            ws.cell(row=nr, column=col_map['title'],    value=art.get('title', ''))
            ws.cell(row=nr, column=col_map['date'],     value=(art.get('published_date','') or '')[:10])
            ws.cell(row=nr, column=col_map['source'],   value=art.get('source', ''))
            ws.cell(row=nr, column=col_map['url'],      value=art.get('url', ''))
            ws.cell(row=nr, column=col_map['summary'],  value=art.get('summary', '')[:500])
            for c in range(1, 9):
                ws.cell(row=nr, column=c).fill   = NEW_FILL
                ws.cell(row=nr, column=c).font   = NEW_FONT
                ws.cell(row=nr, column=c).border = thin_border
            added    += 1
            new_urls.add(art.get('url'))
            existing_urls.add(art.get('url'))

        log(f"  +{added} new articles added (yellow highlight)")

        # ── 날짜순 정렬 + 색상 재적용 ───────────────────────
        max_row = ws.max_row
        if added > 0 and max_row > 2:
            max_col_dyn = max(8, ws.max_column)  # 사용자 컬럼 보존
            rows_data = []
            for r in range(2, max_row + 1):
                row_vals = [ws.cell(row=r, column=c).value for c in range(1, max_col_dyn + 1)]
                date_key = str(row_vals[col_map['date']-1] or '0000-00-00')[:10]
                url_key  = str(row_vals[col_map['url']-1]  or '')
                rows_data.append({'vals': row_vals, 'date': date_key, 'is_new': url_key in new_urls})

            rows_data.sort(key=lambda x: x['date'], reverse=True)

            for i, rd in enumerate(rows_data, 2):
                fill = NEW_FILL if rd['is_new'] else area_fill(rd['vals'][0])
                font = NEW_FONT if rd['is_new'] else PLAIN_FONT
                for c in range(1, max_col + 1):
                    cell = ws.cell(row=i, column=c)
                    cell.value  = rd['vals'][c-1] if c-1 < len(rd['vals']) else None
                    if c <= 8:  # 핵심 컬럼만 서식, 나머지는 값만
                        cell.fill   = fill
                        cell.font   = font
                    cell.border = thin_border

            log(f"  Sorted {max_row-1} rows newest-first | new=yellow env=green energy=yellow urban=purple")

        # 컬럼 너비
        for col, w in zip('ABCDEFGH', [18,22,20,60,12,22,50,60]):
            ws.column_dimensions[col].width = w
        ws.freeze_panes = 'A2'

        # ── RSS_Sources 시트 ──────────────────────────────────
        if collection_stats:
            for sn in ["RSS_Sources"]:
                if sn in wb.sheetnames:
                    wb.remove(wb[sn])
            ws_rss = wb.create_sheet("RSS_Sources")
            for ci, h in enumerate(["Source","URL","Status","Last Check",
                                     "Entries","Collected","Error"], 1):
                c = ws_rss.cell(row=1, column=ci, value=h)
                c.fill = HDR_FILL; c.font = HDR_FONT
                c.alignment = Alignment(horizontal='center')

            for ri, (src, st) in enumerate(collection_stats.items(), 2):
                ws_rss.cell(row=ri,column=1,value=src)
                ws_rss.cell(row=ri,column=2,value=st.get('url',''))
                ws_rss.cell(row=ri,column=3,value=st.get('status',''))
                ws_rss.cell(row=ri,column=4,value=st.get('last_check',''))
                ws_rss.cell(row=ri,column=5,value=st.get('entries_found',0))
                ws_rss.cell(row=ri,column=6,value=st.get('collected',0))
                ws_rss.cell(row=ri,column=7,value=st.get('error',''))
                sfill = ("D1FAE5" if st.get('status')=='Success' else
                         "FEE2E2" if st.get('status')=='Failed' else "F9FAFB")
                ws_rss.cell(row=ri,column=3).fill = PatternFill(
                    start_color=sfill,end_color=sfill,fill_type="solid")

            for col,w in zip('ABCDEFG',[28,50,12,20,10,12,45]):
                ws_rss.column_dimensions[col].width = w

        
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Source 시트 업데이트 (RSS + GNews API 수집 기록 통합)
        # 컬럼: Domain | URL | Type | Status | Last Checked |
        #        Check Result | Articles Found | Note
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        _src_sn = "Source"
        if _src_sn not in wb.sheetnames:
            ws_src = wb.create_sheet(_src_sn)
            for _ci, _h in enumerate(["Domain","URL","Type","Status",
                                       "Last Checked","Check Result","Articles Found","Note"], 1):
                _c = ws_src.cell(row=1, column=_ci, value=_h)
                _c.fill = HDR_FILL; _c.font = HDR_FONT
                _c.alignment = Alignment(horizontal='center')
        else:
            ws_src = wb[_src_sn]

        # 기존 도메인·URL → 행번호 인덱스 구축
        _domain_idx = {}
        _url_idx    = {}
        for _r in range(2, ws_src.max_row + 1):
            _d = ws_src.cell(row=_r, column=1).value
            _u = ws_src.cell(row=_r, column=2).value
            if _d:
                _domain_idx[str(_d).lower().replace('www.','')] = _r
            if _u:
                _url_idx[str(_u).rstrip('/')] = _r

        def _ext_domain(_url):
            try:
                from urllib.parse import urlparse
                return urlparse(_url).netloc.lower().replace('www.','')
            except Exception:
                return _url

        now = datetime.now()  # Source 시트용 타임스탬프
        _run_date = now.strftime("%Y-%m-%d %H:%M")

        # ── RSS 소스별 결과 기록 ──────────────────────────────────
        if collection_stats:
            for _sname, _st in collection_stats.items():
                _feed_url  = _st.get('url', '')
                if not _feed_url:
                    continue
                _domain    = _ext_domain(_feed_url)
                _status    = _st.get('status', 'Unknown')
                _collected = _st.get('collected', 0)
                _entries   = _st.get('entries_found', 0)
                _err       = _st.get('error', '') or ''

                if _status == 'Success' and _collected > 0:
                    _result = f"OK — {_entries} entries scanned, {_collected} collected"
                elif _status == 'Success':
                    _result = f"OK — {_entries} entries, 0 collected (no matching infra news)"
                else:
                    _result = f"FAILED: {_err[:70]}"

                _tr = _url_idx.get(_feed_url.rstrip('/')) or _domain_idx.get(_domain)

                if _tr:
                    ws_src.cell(row=_tr, column=4, value="Accessible" if _status=='Success' else "Inaccessible")
                    ws_src.cell(row=_tr, column=5, value=_run_date)
                    ws_src.cell(row=_tr, column=6, value=_result)
                    ws_src.cell(row=_tr, column=7, value=_collected)
                    if _err and _status == 'Failed':
                        ws_src.cell(row=_tr, column=8, value=_err[:120])
                else:
                    _tr = ws_src.max_row + 1
                    ws_src.cell(row=_tr, column=1, value=_domain)
                    ws_src.cell(row=_tr, column=2, value=_feed_url)
                    ws_src.cell(row=_tr, column=3, value="RSS Feed")
                    ws_src.cell(row=_tr, column=4, value="Accessible" if _status=='Success' else "Inaccessible")
                    ws_src.cell(row=_tr, column=5, value=_run_date)
                    ws_src.cell(row=_tr, column=6, value=_result)
                    ws_src.cell(row=_tr, column=7, value=_collected)
                    if _err:
                        ws_src.cell(row=_tr, column=8, value=_err[:120])
                    _url_idx[_feed_url.rstrip('/')] = _tr
                    _domain_idx[_domain] = _tr

                _sf = "D1FAE5" if _status == 'Success' else "FEE2E2"
                ws_src.cell(row=_tr, column=4).fill = PatternFill(
                    start_color=_sf, end_color=_sf, fill_type="solid")

        # ── GNews API 수집 기사의 원본 소스 기록 ─────────────────
        _gnews_by_pub = {}
        _gnews_total  = 0
        for _art in articles:
            _asrc = _art.get('source', '') or ''
            _aurl = _art.get('url', '') or ''
            _is_gn = ('GNews' in _asrc or 'NewsData' in _asrc or
                      'gnews' in _aurl.lower() or 'newsdata' in _aurl.lower())
            if _is_gn:
                _gnews_total += 1
                _pub = (_asrc if _asrc not in ('GNews','NewsData')
                        else _ext_domain(_aurl))
                _gnews_by_pub[_pub] = _gnews_by_pub.get(_pub, 0) + 1

        _gn_key = "gnews.io (Google News API)"
        _gn_row = None
        for _r in range(2, ws_src.max_row + 1):
            if str(ws_src.cell(row=_r, column=1).value or '').startswith('gnews.io'):
                _gn_row = _r
                break
        if not _gn_row:
            _gn_row = ws_src.max_row + 1

        ws_src.cell(row=_gn_row, column=1, value=_gn_key)
        ws_src.cell(row=_gn_row, column=2, value="https://gnews.io/api/v4/search")
        ws_src.cell(row=_gn_row, column=3, value="News API")
        ws_src.cell(row=_gn_row, column=4, value="Accessible" if _gnews_total > 0 else "Checked")
        ws_src.cell(row=_gn_row, column=5, value=_run_date)
        _pub_list = ', '.join(f"{k}({v})" for k, v in
                              sorted(_gnews_by_pub.items(), key=lambda x: -x[1])[:10])
        ws_src.cell(row=_gn_row, column=6,
                    value=(f"OK — {_gnews_total} articles | {_pub_list}"
                           if _gnews_total > 0 else f"Queried — 0 new articles")[:200])
        ws_src.cell(row=_gn_row, column=7, value=_gnews_total)
        ws_src.cell(row=_gn_row, column=8,
                    value=f"Queries: Vietnam infra + Vietnam environment | {_run_date}")
        ws_src.cell(row=_gn_row, column=4).fill = PatternFill(
            start_color="DBEAFE", end_color="DBEAFE", fill_type="solid")

        # GNews로 수집된 개별 출판사도 Source 시트에 추가/업데이트
        for _pub, _cnt in _gnews_by_pub.items():
            if not _pub:
                continue
            _ptr = _domain_idx.get(_pub.lower().replace('www.',''))
            if not _ptr:
                _ptr = ws_src.max_row + 1
                ws_src.cell(row=_ptr, column=1, value=_pub)
                ws_src.cell(row=_ptr, column=2, value=f"(via GNews API: {_pub})")
                ws_src.cell(row=_ptr, column=3, value="Media/News (via API)")
                ws_src.cell(row=_ptr, column=4, value="Accessible")
                _domain_idx[_pub.lower()] = _ptr
            ws_src.cell(row=_ptr, column=5, value=_run_date)
            ws_src.cell(row=_ptr, column=6, value=f"Collected via GNews API: {_cnt} articles")
            ws_src.cell(row=_ptr, column=7, value=_cnt)
            ws_src.cell(row=_ptr, column=8, value="Accessed via Google News API aggregation")

        # Source 시트 컬럼 너비 & 헤더 정비
        for _col, _w in zip('ABCDEFGH', [30, 52, 18, 14, 20, 60, 16, 55]):
            ws_src.column_dimensions[_col].width = _w
        ws_src.freeze_panes = 'A2'
        if ws_src.cell(row=1, column=1).value != 'Domain':
            for _ci, _h in enumerate(["Domain","URL","Type","Status",
                                       "Last Checked","Check Result","Articles Found","Note"], 1):
                _c = ws_src.cell(row=1, column=_ci, value=_h)
                _c.fill = HDR_FILL; _c.font = HDR_FONT
                _c.alignment = Alignment(horizontal='center')

        _rss_ok = sum(1 for _s in (collection_stats or {}).values() if _s.get('status')=='Success')
        _rss_tot = len(collection_stats) if collection_stats else 0
        log(f"✓ Source sheet updated | RSS {_rss_ok}/{_rss_tot} OK | GNews {_gnews_total} articles from {len(_gnews_by_pub)} publishers")


        # ── Collection_Log 시트 ───────────────────────────────
        if "Collection_Log" not in wb.sheetnames:
            ws_log = wb.create_sheet("Collection_Log")
            for ci,h in enumerate(["Date","Time","Hours Back","Sources Checked",
                                    "Success","Failed","New Articles","Total DB"],1):
                c = ws_log.cell(row=1,column=ci,value=h)
                c.fill=HDR_FILL; c.font=HDR_FONT
        else:
            ws_log = wb["Collection_Log"]

        now      = datetime.now()
        tot_src  = len(collection_stats) if collection_stats else 0
        ok_src   = sum(1 for s in (collection_stats or {}).values() if s.get('status')=='Success')
        log_row  = ws_log.max_row + 1
        cur_total = sum(1 for r in ws.iter_rows(min_row=2,values_only=True) if any(r))

        ws_log.cell(row=log_row,column=1,value=now.strftime("%Y-%m-%d"))
        ws_log.cell(row=log_row,column=2,value=now.strftime("%H:%M:%S"))
        ws_log.cell(row=log_row,column=3,value=HOURS_BACK)
        ws_log.cell(row=log_row,column=4,value=tot_src)
        ws_log.cell(row=log_row,column=5,value=ok_src)
        ws_log.cell(row=log_row,column=6,value=tot_src - ok_src)
        ws_log.cell(row=log_row,column=7,value=added)
        ws_log.cell(row=log_row,column=8,value=cur_total)
        today_hl = PatternFill(start_color="DBEAFE",end_color="DBEAFE",fill_type="solid")
        for c in range(1,9):
            ws_log.cell(row=log_row,column=c).fill = today_hl

        # ── Summary 시트 ─────────────────────────────────────
        for sn in ["Summary"]:
            if sn in wb.sheetnames:
                wb.remove(wb[sn])
        ws_sum = wb.create_sheet("Summary")

        # 전체 집계
        sectors_all  = [str(ws.cell(row=r,column=2).value or '') for r in range(2,ws.max_row+1) if any(ws.cell(row=r,column=c).value for c in range(1,9))]
        areas_all    = [str(ws.cell(row=r,column=1).value or '') for r in range(2,ws.max_row+1) if any(ws.cell(row=r,column=c).value for c in range(1,9))]
        prov_all     = [str(ws.cell(row=r,column=3).value or '') for r in range(2,ws.max_row+1) if any(ws.cell(row=r,column=c).value for c in range(1,9))]
        total_arts   = len(sectors_all)

        ws_sum.merge_cells('A1:D1')
        tc = ws_sum.cell(row=1,column=1,value="🇻🇳 Vietnam Infrastructure News — Summary")
        tc.font=Font(bold=True,size=14,color="0F766E"); tc.alignment=Alignment(horizontal='center')
        ws_sum.cell(row=2,column=1,value=f"Updated: {now.strftime('%Y-%m-%d %H:%M')}  |  Total: {total_arts:,} articles")
        ws_sum.cell(row=2,column=1).font=Font(size=10,color="475569")

        r = 4
        ws_sum.cell(row=r,column=1,value="Business Sector").font=Font(bold=True,size=11)
        ws_sum.cell(row=r,column=2,value="Articles").font=Font(bold=True,size=11)
        ws_sum.cell(row=r,column=3,value="Share").font=Font(bold=True,size=11)
        r += 1
        for sect,cnt in Counter(sectors_all).most_common():
            ws_sum.cell(row=r,column=1,value=sect)
            ws_sum.cell(row=r,column=2,value=cnt)
            ws_sum.cell(row=r,column=3,value=f"{cnt/total_arts*100:.1f}%" if total_arts else "0%")
            r += 1

        r += 1
        ws_sum.cell(row=r,column=1,value="Area").font=Font(bold=True,size=11)
        r += 1
        for area,cnt in Counter(areas_all).most_common():
            ws_sum.cell(row=r,column=1,value=area); ws_sum.cell(row=r,column=2,value=cnt); r+=1

        r += 1
        ws_sum.cell(row=r,column=1,value="Top 15 Provinces").font=Font(bold=True,size=11)
        r += 1
        for prov,cnt in Counter(prov_all).most_common(15):
            ws_sum.cell(row=r,column=1,value=prov); ws_sum.cell(row=r,column=2,value=cnt); r+=1

        for col,w in zip('ABCD',[30,12,10,10]):
            ws_sum.column_dimensions[col].width = w

        wb.save(ep)
        wb.close()
        log(f"✓ Excel saved | +{added} new(yellow) | total {cur_total} | sorted ↓date | Log+RSS+Summary updated")
        return True

    except Exception as e:
        log(f"Excel update error: {e}")
        import traceback; traceback.print_exc()
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
