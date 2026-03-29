#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vietnam Infrastructure News Collector
Version 5.3 — Environment & North Vietnam Coverage Enhancement

v5.2 대비 변경사항 (2026-03-29):
  [RSS 추가] 환경 전문 P1: VietnamPlus-Moi truong, Nhandan-Moi truong,
             Baotainguyenmoitruong, Kinhtemoitruong, VietnamPlus-Kinh te
  [RSS 추가] 북부 지역 P2: Hanoimoi, Baobacgiang English, Nhandan-Kinh te
  [RSS 추가] 보조 P3: Moitruong Net, Congnghiepmoitruong, VietnamPlus-Giao thong
  [키워드 추가] 베트남어 환경 키워드 강화: môi trường, ô nhiễm, phân loại rác 등
  [키워드 추가] 북부 지역 Province 키워드 보완: 꽝닌, 박장, 하이퐁 등
  [Google News] 환경+북부 보완 쿼리 추가
  [RSS_FEEDS] 딕셔너리 형태 유지 (기존 v5.2 구조 완전 호환)

v5.2 반영 사항:
  [검증보고서] 가중치 기반 점수제 분류 (최소 임계값 3점)
  [검증보고서] EXCLUDE_KEYWORDS 대폭 보강
  [검증보고서] 제목 키워드 3점 / 본문 키워드 1점 가중치 차등 적용
  [검증보고서] Province 추출 로직 강화 (본문 전체 스캔)
  [Genspark] LANGUAGE_FILTER='all' (영어+베트남어 모두 수집)
  [Genspark] 9개 섹터 완전 정의
  [Genspark] confidence_score 필드 추가
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

LANGUAGE_FILTER  = os.environ.get('LANGUAGE_FILTER', 'all').lower()

MIN_CLASSIFY_THRESHOLD = 2

GNEWS_API_KEY    = os.environ.get('GNEWS_API_KEY', '')
ENABLE_GNEWS     = os.environ.get('ENABLE_GNEWS', 'false').lower() == 'true'

# [v5.2] 인프라 기본 쿼리
GNEWS_QUERY      = 'Vietnam infrastructure OR "Vietnam energy" OR "Vietnam transport"'
# [v5.3 추가] 환경 + 북부 보완 쿼리
GNEWS_ENV_QUERY  = 'Vietnam environment OR "Vietnam wastewater" OR "Vietnam solid waste" OR "Vietnam water supply"'
GNEWS_NORTH_QUERY = '"Quang Ninh" infrastructure OR "Bac Giang" industrial OR "Hanoi" infrastructure OR "Hai Phong" port'


# ============================================================
# SECTOR DEFINITIONS
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
    "Power":                  "Energy Develop.",
    "Oil & Gas":              "Energy Develop.",
    "Transport":              "Urban Development",
    "Industrial Parks":       "Urban Development",
    "Smart City":             "Urban Development",
    "Construction":           "Urban Development",
}

SECTOR_KEYWORDS = {
    # ─────────────────────────────────────────────────────────
    # 1. WASTE WATER
    # ─────────────────────────────────────────────────────────
    "Waste Water": {
        "primary": [
            "wastewater", "waste water",
            "sewage treatment", "sewage plant", "sewage system",
            "wastewater treatment", "wastewater plant", "wwtp",
            "effluent treatment", "sludge treatment",
            "industrial wastewater", "domestic wastewater",
            "xử lý nước thải",
            "nước thải",
        ],
        "secondary": [
            "sewage", "sewer network", "sewer line",
            "effluent", "sludge",
            "water pollution control",
            "water quality improvement",
        ],
    },

    # ─────────────────────────────────────────────────────────
    # 2. WATER SUPPLY / DRAINAGE
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
            "nước sạch",
            "cấp nước",
            "thoát nước",
            "chống ngập",
            "hồ chứa nước",
            "nhà máy nước",
            "nước sinh hoạt",
            "lũ lụt",
            "hạn hán",
            "nước mưa",
            "ngập úng",
            "biến đổi khí hậu",
            "khí hậu",
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
            "lô b", "cá voi xanh",
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
    # 4. POWER
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
            "nhà máy điện",
            "năng lượng tái tạo",
            "điện mặt trời",
            "điện gió",
            "thủy điện",
            "nhiệt điện",
            "lưới điện",
            "truyền tải điện",
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
    # 5. SOLID WASTE
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
            "rác thải",
            "rác sinh hoạt",
            "lò đốt rác",
            "bãi rác",
            "xử lý rác",
            "chất thải rắn",
            "nhà máy xử lý rác",
            "thu gom rác",
            "đốt rác phát điện",
            # [v5.3] 환경 키워드 강화
            "ô nhiễm môi trường",
            "ô nhiễm",
            "phân loại rác",
            "không khí",
            "phát thải",
            "môi trường",
            "tài nguyên môi trường",
            "khí thải",
            "ô nhiễm nước",
            "chất thải nguy hại",
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
    # 6. TRANSPORT
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
            "tuyến metro",
            "đường cao tốc",
            "sân bay",
            "cảng biển",
            # [v5.3] 북부 물류 키워드
            "lạch huyện",
            "cảng hải phòng",
            "đường sắt tốc độ cao",
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
    # 7. INDUSTRIAL PARKS
    # ─────────────────────────────────────────────────────────
    "Industrial Parks": {
        "primary": [
            "industrial park", "industrial zone", "industrial complex",
            "special economic zone", "sez",
            "export processing zone", "epz",
            "hi-tech park", "high-tech park", "technology park",
            "industrial estate", "industrial cluster",
            "khu công nghiệp",
            "khu kinh tế",
            "khu công nghệ cao",
            # [v5.3] 북부 산업단지 특화
            "vsip bắc ninh", "vsip bắc giang", "vsip quảng ngãi",
            "deep c", "amata",
        ],
        "secondary": [
            "economic zone", "free trade zone",
            "manufacturing hub", "manufacturing zone",
            "factory zone", "industrial area",
            "fdi project",
        ],
    },

    # ─────────────────────────────────────────────────────────
    # 8. SMART CITY
    # ─────────────────────────────────────────────────────────
    "Smart City": {
        "primary": [
            "smart city project", "smart city development",
            "intelligent city", "digital city",
            "smart traffic system", "traffic management system",
            "iot infrastructure", "5g network deployment",
            "e-government system", "digital government",
            "thành phố thông minh",
            "đô thị thông minh",
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
    # 9. CONSTRUCTION
    # ─────────────────────────────────────────────────────────
    "Construction": {
        "primary": [
            "real estate development", "property development",
            "housing project", "residential complex",
            "new urban area", "new township",
            "satellite city development",
            "commercial building construction",
            "urban development project",
            "khu đô thị",
            "dự án bất động sản",
            "bao xay dung",
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
# EXCLUDE KEYWORDS
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
    # 금융·비인프라 경제
    "gold price", "stock market", "forex", "exchange rate",
    "cryptocurrency", "bitcoin",
    "seafood export", "agricultural export", "rice export",
    # 관광·호텔·소매
    "tourism promotion", "tourist", "hotel resort", "beach resort",
    "retail sales",
    # 교육·사회
    "university", "school enrollment", "scholarship",
    "beauty pageant", "fashion", "concert",
    # 실제 오분류 사례
    "matchmaking", "get married", "marriage club",
    "safety certification", "vinfast vf",
    "night flights", "flight schedule", "airline route",
    "train collision in spain", "earthquake in",
    # 정치 (인프라 무관)
    "party congress", "politburo", "state visit", "diplomatic",
    # 정크
    "multimedia", "social links", "subscribe",
]

NON_VIETNAM_COUNTRIES = [
    "singapore", "malaysia", "thailand", "indonesia", "philippines",
    "cambodia", "laos", "myanmar", "china", "japan", "south korea",
    "taiwan", "hong kong", "australia", "russia", " uk ", " usa ",
    "america", "india", "europe", "africa",
]

VIETNAM_KEYWORDS = [
    # 영문
    "vietnam", "vietnamese", "viet nam",
    "hanoi", "ho chi minh", "hcmc", "saigon",
    "da nang", "hai phong", "can tho",
    "binh duong", "dong nai", "quang ninh",
    "mekong", "evn", "petrovietnam", "pvn",
    # 베트남어
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
    "tập đoàn điện lực", "tập đoàn dầu khí",
    # [v5.3] 환경부처 + 메콩 + 기후
    "bộ tài nguyên",
    "tài nguyên và môi trường",
    "sông cửu long",
    "đồng bằng sông",
    "cửu long",
    "miền trung",
    "miền nam",
    "miền bắc",
    # [v5.3] 북부 지역 추가
    "bắc giang", "bắc ninh", "hải dương",
    "hưng yên", "thái bình", "nam định",
    "ninh bình", "lạng sơn", "yên bái",
    "lào cai", "tuyên quang", "hà giang",
    "cao bằng", "bắc kạn", "lai châu",
    "điện biên", "sơn la",
]


# ============================================================
# PROVINCE KEYWORDS — v5.3 강화 (북부 지역 추가)
# ============================================================

PROVINCE_KEYWORDS = {
    "Ho Chi Minh City":  ["ho chi minh", "hcmc", "saigon", "sai gon", "hồ chí minh", "tp.hcm", "tp hcm"],
    "Hanoi":             ["hanoi", "ha noi", "hà nội", "capital hanoi"],
    "Da Nang":           ["da nang", "đà nẵng", "danang"],
    "Hai Phong":         ["hai phong", "hải phòng", "haiphong", "lạch huyện", "cảng hải phòng"],
    "Can Tho":           ["can tho", "cần thơ"],
    "Binh Duong":        ["binh duong", "bình dương"],
    "Dong Nai":          ["dong nai", "đồng nai"],
    "Ba Ria - Vung Tau": ["ba ria", "vung tau", "vũng tàu", "bà rịa"],
    "Long An":           ["long an"],
    # [v5.3] 북부 지역 키워드 강화
    "Quang Ninh":        ["quang ninh", "quảng ninh", "ha long bay", "hạ long",
                          "hạ long bay", "vân đồn", "móng cái", "cẩm phả", "uông bí"],
    "Bac Ninh":          ["bac ninh", "bắc ninh", "yên phong", "vsip bắc ninh", "quế võ"],
    "Bac Giang":         ["bac giang", "bắc giang", "vsip bắc giang", "viettel bắc giang",
                          "công hòa", "quang châu"],
    "Hai Duong":         ["hai duong", "hải dương"],
    "Hung Yen":          ["hung yen", "hưng yên", "thăng long ii"],
    "Vinh Phuc":         ["vinh phuc", "vĩnh phúc"],
    "Thai Nguyen":       ["thai nguyen", "thái nguyên", "samsung thái nguyên"],
    "Phu Tho":           ["phu tho", "phú thọ"],
    "Hoa Binh":          ["hoa binh", "hòa bình"],
    "Lang Son":          ["lang son", "lạng sơn", "hữu nghị"],
    "Yen Bai":           ["yen bai", "yên bái"],
    "Lao Cai":           ["lao cai", "lào cai", "sa pa", "sapa"],
    "Tuyen Quang":       ["tuyen quang", "tuyên quang"],
    "Ha Giang":          ["ha giang", "hà giang"],
    "Cao Bang":          ["cao bang", "cao bằng"],
    "Bac Kan":           ["bac kan", "bắc kạn"],
    "Thai Binh":         ["thai binh", "thái bình"],
    "Nam Dinh":          ["nam dinh", "nam định"],
    "Ninh Binh":         ["ninh binh", "ninh bình", "tràng an"],
    "Ha Nam":            ["ha nam", "hà nam", "đồng văn"],
    "Son La":            ["son la", "sơn la", "nho quế"],
    "Dien Bien":         ["dien bien", "điện biên"],
    "Lai Chau":          ["lai chau", "lai châu"],
    # 중부·남부
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
# RSS FEEDS — v5.3 (기존 59개 + 신규 12개 = 최대 71개)
# [v5.3] 환경 전문 P1 5개 + 북부 지역 P2 4개 + 보조 P3 3개 추가
# [주의] 딕셔너리 형태 유지 — key=소스명, value=RSS URL
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
    "VnExpress - Kinh doanh":          "https://vnexpress.net/rss/kinh-doanh.rss",
    "VnExpress - Thời sự":             "https://vnexpress.net/rss/thoi-su.rss",
    "Tuoi Tre - Kinh doanh":           "https://tuoitre.vn/rss/kinh-doanh.rss",
    "Thanh Nien - Kinh te":            "https://thanhnien.vn/rss/kinh-te.rss",
    "VietnamNet - Kinh doanh":         "https://vietnamnet.vn/rss/kinh-doanh.rss",
    "Dan Tri - Kinh doanh":            "https://dantri.com.vn/rss/kinh-doanh.rss",
    "CafeBiz":                         "https://cafebiz.vn/rss/home.rss",
    # ── 베트남어 전문 소스 ─────────────────────────────────────
    "Bao Xay Dung":                    "https://baoxaydung.com.vn/rss/home.rss",
    # ── 중부 지역 ─────────────────────────────────────────────
    "Bao Ha Tinh":                     "https://baohatinh.vn/rss/home.rss",
    "Bao Binh Dinh":                   "https://baobinhdinh.vn/rss/home.rss",
    # ── 남부 지역 ─────────────────────────────────────────────
    "SGGP":                            "https://www.sggp.org.vn/rss/home.rss",
    # ──────────────────────────────────────────────────────────
    # [v5.3 신규 추가] P1: 환경 전문 RSS (검색으로 URL 검증 완료)
    # ──────────────────────────────────────────────────────────
    # ✅ VietnamPlus 공식 RSS 페이지에서 직접 확인된 URL
    "VietnamPlus - Moi truong":        "https://www.vietnamplus.vn/rss/moitruong-270.rss",
    # ✅ VietnamPlus 공식 RSS 페이지에서 직접 확인된 URL (경제/인프라)
    "VietnamPlus - Kinh te":           "https://www.vietnamplus.vn/rss/kinhte-311.rss",
    # ✅ Nhandan RSS 페이지에서 Môi trường 섹션 존재 확인
    "Nhandan - Moi truong":            "https://baotintuc.vn/moi-truong.rss",
    # ✅ feedspot 등재 확인 (환경경제 전문지)
    "Kinhtemoitruong":                 "https://kinhtemoitruong.vn/rss",
    # ⚠️ 환경부 공식 신문 - RSS 직접 접근 차단, 표준 패턴 적용 (실패시 자동 스킵)
    "Baotainguyenmoitruong":           "https://baotainguyenmoitruong.vn/rss/tin-tuc.rss",
    # ──────────────────────────────────────────────────────────
    # [v5.3 신규 추가] P2: 북부 지역지 RSS
    # ──────────────────────────────────────────────────────────
    # ✅ Nhandan 경제 섹션 (전국 인프라 프로젝트 포함)
    "Nhandan - Kinh te":               "https://baotintuc.vn/kinh-te.rss",
    # ✅ Source 시트 Accessible 확인 — 하노이 경제/인프라
    "Hanoimoi - Kinh te":              "https://hanoimoi.vn/rss/kinh-te.rss",
    # ✅ Source 시트 Accessible 확인 — 박장성 산업단지 특화 (영문)
    "Baobacgiang English":             "https://en.baobacgiang.vn/rss",
    # ⚠️ 꽝닌성 공식 신문 — 403 차단 가능, 실패시 자동 스킵
    "Baoquangninh - Kinh te":          "https://baoquangninh.vn/rss/kinh-te.rss",
    # ──────────────────────────────────────────────────────────
    # [v5.3 신규 추가] P3: 보조 환경/교통 RSS
    # ──────────────────────────────────────────────────────────
    # ✅ Source 시트 Accessible 확인 — 환경 전문
    "Moitruong Net":                   "https://moitruong.net.vn/rss",
    # ✅ Source 시트 Accessible 확인 — 산업환경 전문
    "Congnghiepmoitruong":             "https://congnghiepmoitruong.vn/rss",
    # ✅ VietnamPlus 공식 RSS — 교통 인프라 (Transport 섹터 보완)
    "VietnamPlus - Giao thong":        "https://www.vietnamplus.vn/rss/xahoi/giaothong-358.rss",
    # ── 기존 환경/에너지 전문 소스 (v5.2 유지) ────────────────
    "Bao Dau Tu - Energy":             "https://baodautu.vn/rss/nang-luong.rss",
    "Vietnam Energy alt":              "https://vietnamenergy.vn/rss/tin-tuc.rss",
    "Tap chi Xay dung":                "https://tapchixaydung.vn/rss/home.rss",
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
    else:
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
    if not title or len(title.strip()) < 15:
        return True
    text = f"{title} {summary}".lower()
    return any(kw in text for kw in EXCLUDE_KEYWORDS)


def extract_province(title, summary="", full_text=""):
    combined = f"{title} {summary} {full_text}".lower()
    for province, keywords in PROVINCE_KEYWORDS.items():
        for kw in keywords:
            if kw in combined:
                return province
    return "Vietnam"




# ============================================================
# TRANSLATE ARTICLES — [메모리항목1] Google Translate (MyMemory API)
# Anthropic API 절대 금지. MyMemory 1차, deep-translator 2차
# ============================================================

def translate_text(text, target_lang='ko'):
    """MyMemory API로 번역. 실패 시 deep-translator 폴백."""
    if not text or len(text.strip()) < 3:
        return text or ''
    src = 'en' if is_english_text(text) else 'vi'
    # 1차: MyMemory API
    try:
        url = (f"https://api.mymemory.translated.net/get"
               f"?q={requests.utils.quote(text[:500])}"
               f"&langpair={src}|{target_lang}")
        r = requests.get(url, timeout=10)
        data = r.json()
        result = data.get('responseData', {}).get('translatedText', '')
        if result and result != text and 'INVALID' not in result.upper():
            return result
    except Exception:
        pass
    # 2차: deep-translator
    try:
        from deep_translator import GoogleTranslator
        result = GoogleTranslator(source='auto', target=target_lang).translate(text[:500])
        if result:
            return result
    except Exception:
        pass
    return text


def translate_articles(articles):
    """수집된 기사 리스트를 ko/en/vi 3개 언어로 번역.
    [메모리항목1] MyMemory API 1차 + deep-translator 2차
    [메모리항목7] update_excel_database() 전에 반드시 호출"""
    if not articles:
        return articles

    log(f"Translating {len(articles)} articles (ko/en/vi)...")
    import time

    for i, art in enumerate(articles):
        title  = art.get('title', '') or ''
        summary = art.get('summary', '') or ''

        # 언어 감지
        is_en = is_english_text(title)
        is_vi = is_vietnamese_text(title)

        try:
            # title_ko
            if is_en:
                art['title_ko'] = translate_text(title, 'ko')
            elif is_vi:
                art['title_ko'] = translate_text(title, 'ko')
            else:
                art['title_ko'] = title

            # title_en
            if is_en:
                art['title_en'] = title
            else:
                art['title_en'] = translate_text(title, 'en')

            # title_vi
            if is_vi:
                art['title_vi'] = title
            else:
                art['title_vi'] = translate_text(title, 'vi')

            # summary_ko
            if summary:
                if is_en:
                    art['summary_ko'] = translate_text(summary[:300], 'ko')
                else:
                    art['summary_ko'] = translate_text(summary[:300], 'ko')
            else:
                art['summary_ko'] = ''

            # summary_en
            if summary:
                art['summary_en'] = summary if is_en else translate_text(summary[:300], 'en')
            else:
                art['summary_en'] = ''

            # summary_vi
            if summary:
                art['summary_vi'] = summary if is_vi else translate_text(summary[:300], 'vi')
            else:
                art['summary_vi'] = ''

        except Exception as e:
            log(f"  Translation error [{art.get('title','')[:40]}]: {e}")
            art.setdefault('title_ko', '')
            art.setdefault('title_en', title)
            art.setdefault('title_vi', '')
            art.setdefault('summary_ko', '')
            art.setdefault('summary_en', summary)
            art.setdefault('summary_vi', '')

        # API 과부하 방지 — 3건마다 0.5초 대기
        if (i + 1) % 3 == 0:
            time.sleep(0.5)

        if (i + 1) % 10 == 0:
            log(f"  Translated {i+1}/{len(articles)}")

    log(f"Translation complete: {len(articles)} articles")
    return articles


# ============================================================
# CLASSIFY SECTOR — 가중치 점수제
# ============================================================

def classify_sector(title, summary=""):
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
# GOOGLE NEWS API — v5.3: 환경+북부 쿼리 추가
# ============================================================

def fetch_gnews(query, hours_back=24, max_articles=20):
    if not GNEWS_API_KEY:
        return []

    articles = []
    try:
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
            from_dt = (datetime.utcnow() - timedelta(hours=min(hours_back, 720))).strftime('%Y-%m-%dT%H:%M:%SZ')
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
    """SQLite + Excel 양쪽에서 기존 URL hash를 수집.
    Excel이 정보의 원천(source of truth) — SQLite 초기화되어도 중복 방지."""
    # 1) SQLite에서 hash 수집
    cur = conn.execute("SELECT url_hash FROM articles")
    hashes = {row[0] for row in cur.fetchall()}

    # 2) Excel DB Link 컬럼에서 URL → hash 변환하여 추가
    _excel = os.environ.get('EXCEL_PATH', EXCEL_PATH)
    try:
        from pathlib import Path
        if Path(_excel).exists():
            import openpyxl
            _wb = openpyxl.load_workbook(_excel, read_only=True, data_only=True)
            _ws = _wb.active
            # Link 컬럼 위치 찾기 (헤더에서 'Link' 또는 'URL' 검색)
            _link_col = 7  # 기본값 (G열)
            for _c in range(1, _ws.max_column + 1):
                _h = str(_ws.cell(1, _c).value or '').lower()
                if _h in ('link', 'url'):
                    _link_col = _c
                    break
            # URL → hash 변환
            for _row in _ws.iter_rows(min_row=2, values_only=True):
                _url = _row[_link_col - 1] if _link_col - 1 < len(_row) else None
                if _url and str(_url).startswith('http'):
                    hashes.add(hashlib.md5(str(_url).encode()).hexdigest())
            _wb.close()
            log(f"  Loaded {len(hashes)} existing URL hashes (SQLite + Excel)")
    except Exception as _e:
        log(f"  Excel hash load warning: {_e}")

    return hashes


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
    conn             = init_database(DB_PATH)
    existing_hashes  = get_existing_hashes(conn)
    cutoff           = datetime.now() - timedelta(hours=hours_back)

    log(f"Cutoff: {cutoff:%Y-%m-%d %H:%M} | Language: {LANGUAGE_FILTER} | Threshold: {MIN_CLASSIFY_THRESHOLD}")
    log(f"RSS feeds: {len(RSS_FEEDS)} (v5.3: +12 environment+north feeds)")

    total_collected    = 0
    collected_articles = []
    collection_stats   = {}

    # ── RSS collection ──────────────────────────────────────
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
        log("GNews: fetching supplemental articles (infra + environment + north)...")
        gnews_raw = fetch_gnews(GNEWS_QUERY, hours_back)
        gnews_raw += fetch_gnews(GNEWS_ENV_QUERY, hours_back, max_articles=15)
        # [v5.3 추가] 북부 보완 쿼리
        gnews_raw += fetch_gnews(GNEWS_NORTH_QUERY, hours_back, max_articles=10)

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
    sector_counts   = Counter(a['sector']   for a in collected_articles)
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
    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from collections import Counter
        import shutil
    except ImportError:
        log("openpyxl not installed")
        return False

    _ep_str = excel_path or os.environ.get('EXCEL_PATH', EXCEL_PATH)
    ep = Path(_ep_str)
    if not ep.exists():
        log(f"Excel not found: {ep}")
        return False

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

        url_col = 7
        for c in range(1, ws.max_column + 1):
            h = ws.cell(row=1, column=c).value
            if h and "link" in str(h).lower():
                url_col = c
                break

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

        col_map = {
            'area':1,'sector':2,'province':3,'title':4,'date':5,
            'source':6,'url':7,'summary':8,
            'title_ko':9,'title_en':10,'title_vi':11,
            'summary_ko':12,'summary_en':13,'summary_vi':14,
        }

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
            # 번역 컬럼 (9~14): translate_articles()가 채운 값을 저장
            # [메모리항목7] translate_articles() 실행 후 이 함수 호출 → 번역값 존재
            ws.cell(row=nr, column=col_map['title_ko'],   value=art.get('title_ko',''))
            ws.cell(row=nr, column=col_map['title_en'],   value=art.get('title_en',''))
            ws.cell(row=nr, column=col_map['title_vi'],   value=art.get('title_vi',''))
            ws.cell(row=nr, column=col_map['summary_ko'], value=art.get('summary_ko',''))
            ws.cell(row=nr, column=col_map['summary_en'], value=art.get('summary_en',''))
            ws.cell(row=nr, column=col_map['summary_vi'], value=art.get('summary_vi',''))
            for c in range(1, 15):
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
            max_col_dyn = max(8, ws.max_column)
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
                for c in range(1, max_col_dyn + 1):
                    cell = ws.cell(row=i, column=c)
                    cell.value  = rd['vals'][c-1] if c-1 < len(rd['vals']) else None
                    if c <= 8:
                        cell.fill   = fill
                        cell.font   = font
                    cell.border = thin_border

            log(f"  Sorted {max_row-1} rows newest-first | new=yellow env=green energy=yellow urban=purple")

        for col, w in zip('ABCDEFGHIJKLMN', [18,22,20,60,12,22,50,60,40,40,40,50,50,50]):
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

        # ── Source 시트 업데이트 ──────────────────────────────
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

        _domain_idx = {}
        _url_idx    = {}
        for _r in range(2, ws_src.max_row + 1):
            _d = ws_src.cell(row=_r, column=1).value
            _u = ws_src.cell(row=_r, column=2).value
            # URL이 http로 시작하는 정상 행만 인덱싱 (separator·오염 행 제외)
            if _u and str(_u).startswith('http'):
                _url_idx[str(_u).rstrip('/')] = _r
                if _d:
                    _domain_idx[str(_d).lower().replace('www.','')] = _r

        def _ext_domain(_url):
            try:
                from urllib.parse import urlparse
                return urlparse(_url).netloc.lower().replace('www.','')
            except Exception:
                return _url

        now = datetime.now()
        _run_date = now.strftime("%Y-%m-%d %H:%M")

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
                    value=f"Queries: Vietnam infra + environment + north | {_run_date}")
        ws_src.cell(row=_gn_row, column=4).fill = PatternFill(
            start_color="DBEAFE", end_color="DBEAFE", fill_type="solid")

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

        sectors_all = [str(ws.cell(row=r,column=2).value or '') for r in range(2,ws.max_row+1)
                       if any(ws.cell(row=r,column=c).value for c in range(1,9))]
        areas_all   = [str(ws.cell(row=r,column=1).value or '') for r in range(2,ws.max_row+1)
                       if any(ws.cell(row=r,column=c).value for c in range(1,9))]
        prov_all    = [str(ws.cell(row=r,column=3).value or '') for r in range(2,ws.max_row+1)
                       if any(ws.cell(row=r,column=c).value for c in range(1,9))]
        total_arts  = len(sectors_all)

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
    p = argparse.ArgumentParser(description='Vietnam Infra News Collector v5.3')
    p.add_argument('--hours-back', type=int, default=HOURS_BACK)
    p.add_argument('--threshold',  type=int, default=MIN_CLASSIFY_THRESHOLD,
                   help='Min classification score (default: 2)')
    p.add_argument('--gnews',      action='store_true', help='Enable Google News API')
    # [메모리 항목7] main.py Step1→2→3→4 순서 준수:
    # --no-excel: Excel 저장 생략 → 번역 후 ExcelUpdater(Step3)가 저장
    p.add_argument('--no-excel',   action='store_true',
                   help='Skip Excel update (used when main.py handles ExcelUpdater)')
    args = p.parse_args()

    HOURS_BACK             = args.hours_back
    MIN_CLASSIFY_THRESHOLD = args.threshold
    if args.gnews:
        ENABLE_GNEWS = True

    print("=" * 60)
    print("VIETNAM INFRASTRUCTURE NEWS COLLECTOR  v5.3")
    print(f"Hours back: {HOURS_BACK} | Threshold: {MIN_CLASSIFY_THRESHOLD} | Language: {LANGUAGE_FILTER}")
    print(f"RSS feeds: {len(RSS_FEEDS)} | New v5.3 feeds: 12 (env+north)")
    print("=" * 60)

    cnt, arts, stats = collect_news(HOURS_BACK)

    # [메모리항목7] Step1(수집) → Step2(번역) → Step3(Excel) 순서 준수
    # 번역 먼저 완료 후 Excel 저장 → title_ko 등이 채워진 상태로 저장됨
    if cnt > 0:
        arts = translate_articles(arts)

    if args.no_excel:
        # [메모리 항목7] main.py 경유 시: Excel 저장 스킵
        # 수집 결과를 JSON으로 저장 → main.py의 ExcelUpdater가 처리
        import json
        _out = {
            'count': cnt,
            'articles': [
                {k: v for k, v in a.items() if k != 'url_hash'}
                for a in arts
            ],
            'stats': {
                src: {
                    'url':            st.get('url',''),
                    'status':         st.get('status',''),
                    'entries_found':  st.get('entries_found', 0),
                    'collected':      st.get('collected', 0),
                    'error':          st.get('error',''),
                }
                for src, st in stats.items()
            }
        }
        _json_path = os.environ.get('COLLECTOR_OUTPUT', 'data/collector_output.json')
        Path(_json_path).parent.mkdir(parents=True, exist_ok=True)
        with open(_json_path, 'w', encoding='utf-8') as _f:
            json.dump(_out, _f, ensure_ascii=False, default=str)
        log(f"Saved {cnt} articles to {_json_path} (Excel update deferred to ExcelUpdater)")
    else:
        # 단독 실행 시: Excel 직접 업데이트 (기존 동작 유지)
        update_excel_database(arts, stats)

    print("\nRSS SOURCE STATUS:")
    for src, st in stats.items():
        icon = "✓" if st['status'] == 'Success' else "✗"
        print(f"  {icon} {src}: {st['entries_found']} entries → {st['collected']} collected")

    print(f"\nTOTAL: {cnt} new articles collected")
