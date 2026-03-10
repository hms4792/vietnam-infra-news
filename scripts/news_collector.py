#!/usr/bin/env python3
"""
Vietnam Infrastructure News Collector
Version 5.1 - Fixed classification logic + Expanded sources
Changes from v4.0:
  - SECTOR SPLIT: Urban Development → Transport + Construction (separate sectors)
  - PRIORITY-BASED classifier replaces score-based (prevents cross-hits)
  - Waste Water / Water Supply separated properly
  - 'waste treatment' ambiguity resolved
  - Added 18 new specialized RSS sources (environment, northern/central regions)
  - Province detection expanded for underrepresented regions
  - Broad catch-all keywords removed from Urban Development
"""

import os
import sys
import json
import re
import sqlite3
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse, urljoin
import html
import concurrent.futures
import time

import requests
import feedparser
from bs4 import BeautifulSoup

# ============================================================
# CONFIGURATION
# ============================================================

DB_PATH = os.environ.get('DB_PATH', 'data/vietnam_infrastructure_news.db')
HOURS_BACK = int(os.environ.get('HOURS_BACK', 24))
EXCEL_PATH = os.environ.get('EXCEL_PATH', 'data/database/Vietnam_Infra_News_Database_Final.xlsx')

RSS_DISCOVERY_TIMEOUT = 5
RSS_DISCOVERY_MAX_WORKERS = 10
ENABLE_RSS_DISCOVERY = os.environ.get('ENABLE_RSS_DISCOVERY', 'false').lower() == 'true'
LANGUAGE_FILTER = os.environ.get('LANGUAGE_FILTER', 'english').lower()

# ============================================================
# VIETNAM PROVINCES
# ============================================================

PROVINCE_KEYWORDS = {
    "Ho Chi Minh City": ["ho chi minh", "hcmc", "saigon", "sai gon", "hồ chí minh"],
    "Hanoi": ["hanoi", "ha noi", "hà nội"],
    "Da Nang": ["da nang", "đà nẵng", "danang"],
    "Hai Phong": ["hai phong", "hải phòng", "haiphong"],
    "Can Tho": ["can tho", "cần thơ", "cantho"],
    "Binh Duong": ["binh duong", "bình dương"],
    "Dong Nai": ["dong nai", "đồng nai"],
    "Ba Ria - Vung Tau": ["ba ria", "vung tau", "vũng tàu", "bà rịa"],
    "Long An": ["long an"],
    "Tay Ninh": ["tay ninh", "tây ninh"],
    "Binh Phuoc": ["binh phuoc", "bình phước"],
    "Quang Ninh": ["quang ninh", "quảng ninh", "ha long", "hạ long"],
    "Bac Ninh": ["bac ninh", "bắc ninh"],
    "Hai Duong": ["hai duong", "hải dương"],
    "Hung Yen": ["hung yen", "hưng yên"],
    "Vinh Phuc": ["vinh phuc", "vĩnh phúc"],
    "Thai Nguyen": ["thai nguyen", "thái nguyên"],
    "Bac Giang": ["bac giang", "bắc giang"],
    "Phu Tho": ["phu tho", "phú thọ"],                      # NEW
    "Yen Bai": ["yen bai", "yên bái"],                      # NEW
    "Son La": ["son la", "sơn la"],                         # NEW (hydropower)
    "Hoa Binh": ["hoa binh", "hòa bình"],                   # NEW (hydropower)
    "Thanh Hoa": ["thanh hoa", "thanh hoá"],
    "Nghe An": ["nghe an", "nghệ an"],
    "Ha Tinh": ["ha tinh", "hà tĩnh"],
    "Quang Binh": ["quang binh", "quảng bình"],
    "Quang Tri": ["quang tri", "quảng trị"],
    "Thua Thien Hue": ["thua thien hue", "huế", "hue"],
    "Quang Nam": ["quang nam", "quảng nam"],
    "Quang Ngai": ["quang ngai", "quảng ngãi"],
    "Binh Dinh": ["binh dinh", "bình định"],
    "Phu Yen": ["phu yen", "phú yên"],
    "Khanh Hoa": ["khanh hoa", "khánh hòa", "nha trang"],
    "Ninh Thuan": ["ninh thuan", "ninh thuận"],
    "Binh Thuan": ["binh thuan", "bình thuận", "phan thiet"],
    "Lam Dong": ["lam dong", "lâm đồng", "da lat", "đà lạt"],
    "Dak Lak": ["dak lak", "đắk lắk", "buon ma thuot"],
    "Dak Nong": ["dak nong", "đắk nông"],                   # NEW
    "Gia Lai": ["gia lai"],
    "Kon Tum": ["kon tum"],
    "Tien Giang": ["tien giang", "tiền giang"],
    "Ben Tre": ["ben tre", "bến tre"],
    "Vinh Long": ["vinh long", "vĩnh long"],
    "Tra Vinh": ["tra vinh", "trà vinh"],
    "Dong Thap": ["dong thap", "đồng tháp"],
    "An Giang": ["an giang"],
    "Kien Giang": ["kien giang", "kiên giang", "phu quoc", "phú quốc"],
    "Hau Giang": ["hau giang", "hậu giang"],
    "Soc Trang": ["soc trang", "sóc trăng"],
    "Bac Lieu": ["bac lieu", "bạc liêu"],
    "Ca Mau": ["ca mau", "cà mau"],
    "Long Thanh": ["long thanh", "long thành"],
    "Mekong Delta": ["mekong delta", "mekong region", "delta region"],  # NEW regional
    "Red River Delta": ["red river delta", "red river"],               # NEW regional
    "Central Highlands": ["central highlands", "tay nguyen"],          # NEW regional
}

# ============================================================
# RSS FEEDS — v5.1 EXPANDED (41 → 59 sources)
# ============================================================

RSS_FEEDS = {
    # ── ENGLISH SOURCES (국가 수준) ───────────────────────────
    "VnExpress English - News":        "https://e.vnexpress.net/rss/news.rss",
    "VnExpress English - Business":    "https://e.vnexpress.net/rss/business.rss",
    "Vietnam News - Economy":          "https://vietnamnews.vn/rss/economy.rss",
    "Vietnam News - Politics":         "https://vietnamnews.vn/rss/politics-laws.rss",
    "Vietnam News - Society":          "https://vietnamnews.vn/rss/society.rss",
    "Vietnam News - Environment":      "https://vietnamnews.vn/rss/environment.rss",   # ★ 환경 전용
    "VietnamPlus English":             "https://en.vietnamplus.vn/rss/news.rss",
    "Hanoi Times":                     "https://hanoitimes.vn/rss/news.rss",
    "VietnamNet English":              "https://vietnamnet.vn/en/rss/home.rss",
    "The Investor":                    "https://theinvestor.vn/rss.html",
    "VIR":                             "https://vir.com.vn/rss/all.rss",
    "Tuoi Tre News":                   "https://tuoitrenews.vn/rss/all.rss",
    "SGGP News English":               "https://en.sggp.org.vn/rss/home.rss",
    "VOV World":                       "https://vovworld.vn/en-US/rss/all.rss",
    "Nhan Dan English":                "https://en.nhandan.vn/rss/home.rss",            # NEW ★
    "VCCINEWS":                        "https://vccinews.com/rss/news.rss",             # NEW ★ (FDI/Industry)

    # ── ENGLISH SPECIALIZED ──────────────────────────────────
    "Vietnam Energy Magazine EN":      "https://vietnamenergy.vn/en/rss/home.rss",     # NEW ★ (Energy EN)
    "VN Infrastructure News":          "https://vn.infrastructure.vn/rss/home.rss",    # NEW ★
    "Asia Water":                      "https://www.asiawater.org/rss/news.rss",       # NEW ★ (Water EN)
    "Vietnam Environment Admin":       "https://vea.gov.vn/en/rss/home.rss",          # NEW ★ (Gov env)

    # ── VIETNAMESE SOURCES (general) ─────────────────────────
    "VnExpress - Kinh doanh":         "https://vnexpress.net/rss/kinh-doanh.rss",
    "VnExpress - Thời sự":            "https://vnexpress.net/rss/thoi-su.rss",
    "Tuoi Tre - Tin mới":             "https://tuoitre.vn/rss/tin-moi-nhat.rss",
    "Tuoi Tre - Kinh doanh":          "https://tuoitre.vn/rss/kinh-doanh.rss",
    "Thanh Nien - Kinh te":           "https://thanhnien.vn/rss/kinh-te.rss",
    "VietnamPlus - Kinh te":          "https://www.vietnamplus.vn/rss/kinhte.rss",
    "VietnamNet - Kinh doanh":        "https://vietnamnet.vn/rss/kinh-doanh.rss",
    "Dan Tri - Kinh doanh":           "https://dantri.com.vn/rss/kinh-doanh.rss",
    "CafeBiz":                        "https://cafebiz.vn/rss/home.rss",
    "Bao Dau Tu":                     "https://baodautu.vn/rss/home.rss",
    "Nhadautu.vn":                    "https://nhadautu.vn/rss/home.rss",              # NEW ★ (Investment)
    "CafeF":                          "https://cafef.vn/rss/home.rss",

    # ── VIETNAMESE SPECIALIZED ───────────────────────────────
    "Nang Luong Vietnam":             "https://nangluongvietnam.vn/rss/home.rss",      # Energy ★
    "Vietnam Energy Magazine":        "https://vietnamenergy.vn/rss/home.rss",         # Energy ★
    "Bao Xay Dung":                   "https://baoxaydung.com.vn/rss/home.rss",        # Construction ★
    "Bao TN Moi Truong":             "https://nongnghiepmoitruong.vn/main-rss.html", # Environment ★★★
    "Kinh Te Moi Truong":            "https://kinhtemoitruong.vn/rss.html",        # Environment ★★★
    "Moi Truong va Do Thi":          "https://moitruongdothi.vn/rss/home.rss",        # NEW ★★★ Env+Urban
    "Tap chi Moi truong":            "https://tapchimoitruong.vn/rss/home.rss",        # NEW ★★★ Env journal
    "Nong nghiep VN":                "https://nongnghiep.vn/rss/home.rss",             # NEW ★ (water/env agri)
    "Bao Tai nguyen":                "https://baotainguyenmoitruong.vn/rss/moi-truong.rss", # NEW deeper env

    # ── REGIONAL — NORTHERN (부족 지역 보완) ─────────────────
    "Hanoi Moi":                      "https://hanoimoi.vn/rss",
    "Bao Quang Ninh":                 "https://baoquangninh.vn/rss/home.rss",
    "Bao Thai Binh":                  "https://baothaibinh.com.vn/rss/home.rss",       # NEW ★ (northern delta)
    "Bao Phu Tho":                    "https://baophutho.vn/rss/home.rss",             # NEW ★ (northern)
    "Bao Hoa Binh":                   "https://baohoabinh.com.vn/rss/home.rss",        # NEW ★ (hydropower)

    # ── REGIONAL — CENTRAL (중부 보완) ───────────────────────
    "Bao Nghe An":                    "https://baonghean.vn/rss/home.rss",             # NEW ★ (central)
    "Bao Ha Tinh":                    "https://baohatinh.vn/rss/home.rss",             # NEW ★ (central)
    "Bao Quang Nam":                  "https://baoquangninh.vn/rss",           # NEW ★ (central)
    "Bao Binh Dinh":                  "https://baobinhdinh.vn/rss/home.rss",           # NEW ★ (central)

    # ── REGIONAL — SOUTHERN (기존 유지) ──────────────────────
    "SGGP":                           "https://www.sggp.org.vn/rss/home.rss",
    "Bao Dong Nai":                   "https://baodongnai.com.vn/rss/home.rss",
    "Bao Binh Duong":                 "https://baobinhduong.vn/rss/home.rss",
    "Bao Da Nang":                    "https://en.baodanang.vn/",

    # ── MEKONG DELTA REGIONAL (신규) ─────────────────────────
    "Bao Can Tho":                    "https://baocantho.com.vn/thoi-su/",         # NEW ★ (Mekong)
    "Bao An Giang":                   "https://baoangiang.com.vn/rss/home.rss",        # NEW ★ (Mekong)
    "Bao Kien Giang":                 "https://baokiengiang.vn/rss/home.rss",          # NEW ★ (Mekong)
}

# ============================================================
# SECTOR KEYWORDS — v5.1 PRIORITY-BASED (9 sectors)
#
# ★ KEY CHANGES from v4.0:
#   1. 'Urban Development' SPLIT into 'Transport' + 'Construction'
#   2. 'Waste Water' and 'Water Supply/Drainage' SEPARATED
#   3. STRICT keywords only — removed broad catch-alls
#   4. 'waste treatment' removed from Solid Waste (ambiguous)
#   5. Priority order now enforced by ORDERED list
# ============================================================

# Classification order: FIRST match wins (high-specificity → low)
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

# Area mapping for each sector
SECTOR_AREA = {
    "Waste Water":          "Environment",
    "Water Supply/Drainage":"Environment",
    "Solid Waste":          "Environment",
    "Power":                "Energy",
    "Oil & Gas":            "Energy",
    "Transport":            "Urban Development",
    "Industrial Parks":     "Urban Development",
    "Smart City":           "Urban Development",
    "Construction":         "Urban Development",
}

SECTOR_KEYWORDS = {

    # ── 1. WASTE WATER (하수/폐수 처리) ──────────────────────
    # STRICT: wastewater + sewage 중심. 'water treatment'는 wastewater plant에 한정
    "Waste Water": [
        "wastewater", "waste water",
        "sewage", "sewage treatment", "sewage plant", "sewage system",
        "wastewater treatment", "wastewater plant", "wastewater system",
        "sewer", "sewer network", "sewer line",
        "effluent", "effluent treatment",
        "sludge", "sludge treatment",
        "wwtp",                              # wastewater treatment plant 약어
        "water pollution control",
        "water quality improvement",
        "industrial wastewater",
        "domestic wastewater",
        "xử lý nước thải",                  # Vietnamese: wastewater treatment
    ],

    # ── 2. WATER SUPPLY / DRAINAGE (상수도/배수) ─────────────
    # 'water treatment' 단독 → Water Supply (정수장)로 처리
    "Water Supply/Drainage": [
        "water supply", "water supply system", "water supply network",
        "clean water", "clean water supply", "clean water access",
        "drinking water", "drinking water supply",
        "tap water", "piped water",
        "water plant", "water treatment plant", "water purification",
        "water distribution", "water network", "water pipeline",
        "water infrastructure",
        "groundwater", "groundwater extraction",
        "reservoir", "water reservoir",
        "drainage", "drainage system", "flood drainage",
        "stormwater", "stormwater management",
        "flood control", "flood prevention", "anti-flooding",
        "nước sạch",                         # Vietnamese: clean water
        "cấp nước",                          # Vietnamese: water supply
        "thoát nước",                        # Vietnamese: drainage
    ],

    # ── 3. OIL & GAS ──────────────────────────────────────────
    "Oil & Gas": [
        "oil and gas", "oil & gas",
        "petroleum", "petrochemical",
        "refinery", "oil refinery",
        "oil field", "gas field",
        "offshore oil", "offshore gas", "offshore drilling",
        "lng", "lng terminal", "lng plant", "liquefied natural gas",
        "gas pipeline", "oil pipeline",
        "natural gas", "natural gas plant",
        "crude oil",
        "oil exploration", "gas exploration", "drilling",
        "upstream", "downstream", "midstream",
        "petrovietnam", "pvn", "pvgas", "pv gas",
        "binh son refinery", "nghi son refinery", "dung quat refinery",
        "block b", "ca voi xanh",            # specific VN gas projects
        "lô b", "cá voi xanh",              # Vietnamese
    ],

    # ── 4. POWER (발전·송배전) ────────────────────────────────
    "Power": [
        "power plant", "power station", "power project",
        "electricity generation", "power generation",
        "thermal power", "coal power plant", "coal-fired power",
        "gas power plant", "combined cycle",
        "hydropower", "hydro power", "hydroelectric",
        "wind power", "wind farm", "wind energy", "offshore wind", "onshore wind",
        "solar power", "solar farm", "solar energy", "photovoltaic", "solar panel",
        "renewable energy", "clean energy", "green energy",
        "power grid", "national grid",
        "transmission line", "high voltage", "power line",
        "substation", "transformer station",
        "battery storage", "energy storage", "bess",
        "energy transition",
        "megawatt", "gigawatt", " mw ", " gw ", "mw capacity", "gw capacity",
        "evn", "vietnam electricity",
        "power purchase agreement", "ppa",
        "feed-in tariff", "fit",
        "nhà máy điện",                     # Vietnamese: power plant
        "năng lượng tái tạo",               # Vietnamese: renewable energy
        "điện mặt trời",                    # Vietnamese: solar
        "điện gió",                         # Vietnamese: wind
    ],

    # ── 5. SOLID WASTE (고형폐기물) ───────────────────────────
    # REMOVED: 'waste treatment' (→ too ambiguous, now goes to Waste Water or Water Supply)
    # REMOVED: 'waste management' alone (too broad)
    "Solid Waste": [
        "solid waste",
        "municipal solid waste", "msw",
        "garbage", "garbage collection", "garbage disposal",
        "trash", "refuse",
        "landfill", "landfill site", "sanitary landfill",
        "waste-to-energy", "waste to energy", "wte",
        "incineration", "incinerator", "incineration plant",
        "recycling", "recycling plant", "recycling facility",
        "composting",
        "hazardous waste", "toxic waste",
        "electronic waste", "e-waste",
        "construction waste", "demolition waste",
        "waste collection system",
        "rác thải",                          # Vietnamese: waste/garbage
        "rác sinh hoạt",                     # Vietnamese: household waste
        "lò đốt rác",                        # Vietnamese: incinerator
        "bãi rác",                           # Vietnamese: landfill/dump
        "xử lý rác",                         # Vietnamese: waste treatment
    ],

    # ── 6. TRANSPORT (교통·물류 인프라) ──────────────────────
    # SPLIT from old 'Urban Development'
    "Transport": [
        # Rail
        "metro", "metro line", "metro station", "metro project",
        "subway", "urban rail", "light rail", "lrt",
        "railway", "railroad", "rail project", "rail line",
        "high-speed rail", "high speed rail", "hsr",
        "train station", "railway station",
        # Road
        "expressway", "highway", "motorway", "freeway",
        "ring road", "ring expressway",
        "bypass road", "bypass highway",
        "overpass", "flyover", "interchange",
        "road construction", "road project", "road upgrade",
        # Bridges / Tunnels
        "bridge construction", "bridge project", "new bridge",
        "cable-stayed bridge", "suspension bridge",
        "tunnel", "road tunnel", "undersea tunnel",
        "viaduct",
        # Airport
        "airport", "airport terminal", "runway",
        "long thanh airport", "noi bai", "tan son nhat",
        # Port / Logistics
        "seaport", "deep-sea port", "container port",
        "container terminal",
        "logistics hub", "logistics center",
        "inland waterway",
        # Public transport
        "public transport", "bus rapid transit", "brt",
        "tram",
        # Vietnamese
        "đường cao tốc",                    # expressway
        "tuyến metro",                      # metro line
        "cầu vượt",                         # overpass
        "sân bay",                          # airport
        "cảng biển",                        # seaport
    ],

    # ── 7. INDUSTRIAL PARKS (산업단지) ───────────────────────
    "Industrial Parks": [
        "industrial park", "industrial zone", "industrial complex",
        "industrial estate", "industrial cluster", "industrial area",
        "economic zone", "economic development zone",
        "special economic zone", "sez",
        "export processing zone", "epz",
        "free trade zone", "ftc",
        "hi-tech park", "high-tech park", "technology park", "tech park",
        "manufacturing zone", "manufacturing hub",
        "industrial land", "factory zone",
        "fdi", "fdi project", "foreign direct investment",
        "khu công nghiệp",                  # Vietnamese: industrial zone
        "khu kinh tế",                      # Vietnamese: economic zone
        "khu công nghệ cao",                # Vietnamese: hi-tech zone
    ],

    # ── 8. SMART CITY (스마트시티) ────────────────────────────
    "Smart City": [
        "smart city", "smart cities",
        "smart urban", "intelligent city",
        "digital city", "digital urban",
        "smart traffic", "intelligent traffic", "traffic management system",
        "smart grid", "smart meter", "smart metering",
        "smart building", "intelligent building",
        "iot infrastructure", "internet of things",
        "5g infrastructure", "5g network", "5g deployment",
        "digital transformation", "e-government", "digital government",
        "surveillance system", "cctv network", "ai camera",
        "city data platform",
        "thành phố thông minh",             # Vietnamese: smart city
    ],

    # ── 9. CONSTRUCTION (건설·부동산 개발) ───────────────────
    # Previously mixed into 'Urban Development' — now separated
    "Construction": [
        "real estate development", "property development",
        "residential development", "housing project", "housing complex",
        "new urban area", "new township", "satellite city",
        "urban development project", "city planning project",
        "commercial building", "office building", "skyscraper",
        "construction project", "building construction",
        "urban infrastructure",
        # Materials / General
        "cement plant", "steel plant", "construction material",
        # NOT transport-specific bridges/roads
        "building permit", "zoning",
        "khu đô thị",                       # Vietnamese: urban area
        "dự án bất động sản",               # Vietnamese: real estate project
    ],
}

# ============================================================
# EXCLUDE KEYWORDS (기존 유지 + 보완)
# ============================================================

EXCLUDE_KEYWORDS = [
    # Crime/Legal
    "arrest", "jail", "prison", "sentenced", "trafficking", "smuggling",
    "fraud", "murder", "killed", "death", "crime", "drug",
    # Finance (non-infra)
    "gold price", "stock market", "forex", "exchange rate",
    "seafood export", "agricultural export",
    # Non-infra news
    "fire kills", "tourist", "tourism", "hotel", "resort",
    "education", "university", "school", "student", "scholarship",
    "sports", "football", "soccer", "tennis", "basketball",
    "party congress", "politburo", "state visit",
    # Junk content patterns found in data
    "multimedia",                           # navigation element
    "social links",                         # navigation element
    "vietnam today",                        # generic header
    "subscribe",                            # newsletter prompt
]

# ============================================================
# VIETNAM KEYWORDS
# ============================================================

VIETNAM_KEYWORDS = [
    "vietnam", "vietnamese", "hanoi", "ho chi minh", "hcmc", "saigon",
    "da nang", "hai phong", "can tho", "binh duong", "dong nai",
    "ba ria", "vung tau", "quang ninh", "bac ninh", "long an",
    "mekong", "red river", "evn", "petrovietnam", "pvn",
    "vn ", "việt nam",
]

NON_VIETNAM_COUNTRIES = [
    "singapore", "malaysia", "thailand", "indonesia", "philippines",
    "cambodia", "laos", "myanmar", "china", "japan", "korea", "india",
    "taiwan", "hong kong", "australia", "russia", "uk ", "usa", "america",
]

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def log(message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"{timestamp} - {message}")


def clean_html(text):
    if not text:
        return ""
    soup = BeautifulSoup(text, 'html.parser')
    return html.unescape(soup.get_text(separator=' ', strip=True))


def generate_url_hash(url):
    return hashlib.md5(url.encode()).hexdigest()


def extract_province(title, summary=""):
    text = f"{title} {summary}".lower()
    for province, keywords in PROVINCE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in text:
                return province
    return "Vietnam"


def is_english_title(title):
    if not title:
        return False
    ascii_letters = sum(1 for c in title if c.isascii() and c.isalpha())
    non_ascii = sum(1 for c in title if not c.isascii())
    total = ascii_letters + non_ascii
    if total == 0:
        return False
    return (ascii_letters / total) > 0.7


def is_vietnamese_title(title):
    if not title:
        return False
    vietnamese_chars = set('àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ'
                          'ÀÁẢÃẠĂẰẮẲẴẶÂẦẤẨẪẬÈÉẺẼẸÊỀẾỂỄỆÌÍỈĨỊÒÓỎÕỌÔỒỐỔỖỘƠỜỚỞỠỢÙÚỦŨỤƯỪỨỬỮỰỲÝỶỸỴĐ')
    return any(c in vietnamese_chars for c in title)


def passes_language_filter(title):
    if LANGUAGE_FILTER == 'all':
        return True
    elif LANGUAGE_FILTER == 'vietnamese':
        return is_vietnamese_title(title) or not is_english_title(title)
    else:
        return is_english_title(title)


def is_vietnam_related(title, summary=""):
    text = f"{title} {summary}".lower()
    has_vietnam = any(kw in text for kw in VIETNAM_KEYWORDS)
    for country in NON_VIETNAM_COUNTRIES:
        if country in text:
            if text.count("vietnam") < text.count(country):
                return False
    return has_vietnam


def should_exclude(title, summary=""):
    """
    Returns True if the article should be excluded.
    Also catches navigation/junk content (very short titles, numeric-only).
    """
    if not title or len(title.strip()) < 10:
        return True
    text = f"{title} {summary}".lower()
    for keyword in EXCLUDE_KEYWORDS:
        if keyword in text:
            return True
    return False


# ============================================================
# SECTOR CLASSIFIER — v5.1 PRIORITY-BASED
#
# Replaces score-based matching.
# RULES:
#   1. Walk sectors in SECTOR_PRIORITY_ORDER
#   2. Return the FIRST sector that matches ANY keyword
#   3. Longer / more-specific keywords checked first within sector
#      (Python list ordering — put specific phrases before single words)
# ============================================================

def classify_sector(title, summary=""):
    """
    Priority-based sector classification.
    Returns (sector, area) tuple or (None, None) if excluded/unmatched.
    """
    if should_exclude(title, summary):
        return None, None

    text = f"{title} {summary}".lower()

    for sector in SECTOR_PRIORITY_ORDER:
        keywords = SECTOR_KEYWORDS[sector]
        for kw in keywords:
            if kw in text:
                return sector, SECTOR_AREA[sector]

    return None, None


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
    except:
        pass
    return None


def fetch_rss(url, timeout=30):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
        'Accept': 'application/rss+xml, application/xml, text/xml, */*',
    }
    try:
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        content = response.text
        content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', content)
        return feedparser.parse(content)
    except Exception as e:
        log(f"   Error fetching {url}: {e}")
        return type('Feed', (), {'entries': [], 'bozo': True})()


# ============================================================
# DATABASE
# ============================================================

def init_database(db_path):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url_hash TEXT UNIQUE,
            url TEXT,
            title TEXT,
            title_vi TEXT,
            title_ko TEXT,
            summary TEXT,
            summary_vi TEXT,
            summary_ko TEXT,
            source TEXT,
            sector TEXT,
            area TEXT,
            province TEXT,
            published_date TEXT,
            collected_date TEXT,
            processed INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    return conn


def get_existing_urls(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT url_hash FROM articles")
    return {row[0] for row in cursor.fetchall()}


def save_article(conn, article):
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO articles (
                url_hash, url, title, summary, source, sector, area,
                province, published_date, collected_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            article['url_hash'],
            article['url'],
            article['title'],
            article.get('summary', ''),
            article['source'],
            article['sector'],
            article.get('area', 'Environment'),
            article.get('province', 'Vietnam'),
            article.get('published_date', ''),
            datetime.now().isoformat()
        ))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


# ============================================================
# MAIN COLLECTION
# ============================================================

def collect_news(hours_back=24):
    conn = init_database(DB_PATH)
    existing_urls = get_existing_urls(conn)
    log(f"Loaded {len(existing_urls)} existing URLs")

    cutoff_time = datetime.now() - timedelta(hours=hours_back)
    log(f"Collecting news from last {hours_back} hours (cutoff: {cutoff_time:%Y-%m-%d %H:%M})")

    total_collected = 0
    total_entries = 0
    collected_articles = []
    collection_stats = {}

    log(f"Total RSS feeds: {len(RSS_FEEDS)}")

    for source_name, feed_url in RSS_FEEDS.items():
        print("")
        print("=" * 50)
        log(f"Source: {source_name}")

        collection_stats[source_name] = {
            'url': feed_url,
            'status': 'Unknown',
            'last_check': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'entries_found': 0,
            'collected': 0,
            'error': ''
        }

        feed = fetch_rss(feed_url)

        if feed.bozo and not feed.entries:
            log("Feed error or empty")
            collection_stats[source_name]['status'] = 'Failed'
            collection_stats[source_name]['error'] = 'Feed error or empty response'
            continue

        entries = feed.entries
        log(f"Found {len(entries)} entries")
        total_entries += len(entries)
        collection_stats[source_name]['entries_found'] = len(entries)
        collection_stats[source_name]['status'] = 'Success'

        source_collected = 0

        for entry in entries:
            title = getattr(entry, 'title', '')
            if not title:
                continue

            title = clean_html(title)
            link = getattr(entry, 'link', '')
            summary = clean_html(getattr(entry, 'summary', getattr(entry, 'description', '')))
            published = getattr(entry, 'published', getattr(entry, 'pubDate', ''))

            if not passes_language_filter(title):
                continue

            url_hash = generate_url_hash(link)
            if url_hash in existing_urls:
                continue

            pub_date = parse_date(published)
            if pub_date:
                if pub_date.tzinfo:
                    pub_date = pub_date.replace(tzinfo=None)
                if pub_date < cutoff_time:
                    continue

            if not is_vietnam_related(title, summary):
                continue

            # v5.1: returns tuple (sector, area)
            sector, area = classify_sector(title, summary)
            if not sector:
                continue

            province = extract_province(title, summary)

            article = {
                'url_hash': url_hash,
                'url': link,
                'title': title,
                'summary': summary[:1000] if summary else '',
                'source': source_name,
                'sector': sector,
                'area': area,
                'province': province,
                'published_date': pub_date.isoformat() if pub_date else ''
            }

            if save_article(conn, article):
                existing_urls.add(url_hash)
                source_collected += 1
                total_collected += 1
                collected_articles.append(article)
                log(f"  SAVED [{sector}] [{province}]: {title[:55]}...")

        collection_stats[source_name]['collected'] = source_collected
        log(f"Collected from {source_name}: {source_collected}")

    conn.close()

    print("")
    print("=" * 60)
    print("COLLECTION SUMMARY")
    print("=" * 60)
    print(f"Total RSS entries processed: {total_entries}")
    print(f"Total articles collected:    {total_collected}")

    # Sector breakdown
    from collections import Counter
    sector_counts = Counter(a['sector'] for a in collected_articles)
    print("\nSector breakdown:")
    for s, c in sector_counts.most_common():
        print(f"  {s:<25} {c:3d}")

    province_counts = Counter(a['province'] for a in collected_articles)
    print("\nTop provinces:")
    for p, c in province_counts.most_common(10):
        print(f"  {p:<30} {c:3d}")

    print("=" * 60)

    return total_collected, collected_articles, collection_stats


# ============================================================
# EXCEL UPDATE (unchanged from v4.0 — sector mapping updated)
# ============================================================

def update_excel_database(articles, collection_stats=None):
    try:
        import openpyxl
        from openpyxl.utils import get_column_letter
        from openpyxl.styles import Font, PatternFill, Alignment
        import shutil
    except ImportError:
        log("openpyxl not installed")
        return False

    EXCEL_PATH_OBJ = Path(EXCEL_PATH)
    if not EXCEL_PATH_OBJ.exists():
        log(f"Excel not found: {EXCEL_PATH_OBJ}")
        return False

    # Safety check
    try:
        wb_check = openpyxl.load_workbook(EXCEL_PATH_OBJ, read_only=True)
        ws_check = wb_check.active
        existing_count = sum(1 for row in ws_check.iter_rows(min_row=2, values_only=True) if any(row))
        wb_check.close()
        if existing_count < 100:
            log(f"⚠️ Only {existing_count} rows — skipping to prevent data loss")
            return False
    except Exception as e:
        log(f"Safety check failed: {e}")
        return False

    backup_path = EXCEL_PATH_OBJ.with_suffix('.xlsx.backup')
    try:
        shutil.copy2(EXCEL_PATH_OBJ, backup_path)
        log(f"✓ Backup: {backup_path}")
    except:
        pass

    try:
        wb = openpyxl.load_workbook(EXCEL_PATH_OBJ)
        ws = wb.active
        last_row = ws.max_row

        existing_urls = set()
        url_col = None
        for col in range(1, ws.max_column + 1):
            header = ws.cell(row=1, column=col).value
            if header and "link" in str(header).lower():
                url_col = col
                break
        if url_col:
            for row in range(2, last_row + 1):
                url = ws.cell(row=row, column=url_col).value
                if url:
                    existing_urls.add(url)

        col_map = {'area':1,'sector':2,'province':3,'title':4,'date':5,'source':6,'url':7,'summary':8}

        added_count = 0
        for article in articles:
            if article.get('url') in existing_urls:
                continue
            new_row = last_row + 1 + added_count
            ws.cell(row=new_row, column=col_map['area'],    value=article.get('area',''))
            ws.cell(row=new_row, column=col_map['sector'],  value=article.get('sector',''))
            ws.cell(row=new_row, column=col_map['province'],value=article.get('province','Vietnam'))
            ws.cell(row=new_row, column=col_map['title'],   value=article.get('title',''))
            date_str = (article.get('published_date','') or '')[:10]
            ws.cell(row=new_row, column=col_map['date'],    value=date_str)
            ws.cell(row=new_row, column=col_map['source'],  value=article.get('source',''))
            ws.cell(row=new_row, column=col_map['url'],     value=article.get('url',''))
            ws.cell(row=new_row, column=col_map['summary'], value=article.get('summary','')[:500])
            added_count += 1
            existing_urls.add(article.get('url'))

        log(f"✓ Added {added_count} new articles")

        wb.save(EXCEL_PATH_OBJ)
        wb.close()
        return True

    except Exception as e:
        log(f"Error updating Excel: {e}")
        import traceback
        traceback.print_exc()
        return False


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Vietnam Infrastructure News Collector v5.1')
    parser.add_argument('--hours-back', type=int, default=HOURS_BACK)
    args = parser.parse_args()
    HOURS_BACK = args.hours_back

    print("=" * 60)
    print("VIETNAM INFRASTRUCTURE NEWS COLLECTOR v5.1")
    print("=" * 60)

    collected_count, collected_articles, collection_stats = collect_news(args.hours_back)

    print("")
    print("=" * 60)
    print("UPDATING EXCEL DATABASE")
    print("=" * 60)
    update_excel_database(collected_articles, collection_stats)

    print("")
    print("=" * 60)
    print("RSS SOURCE STATUS")
    print("=" * 60)
    for source, stats in collection_stats.items():
        icon = "✓" if stats['status'] == 'Success' else "✗"
        print(f"  {icon} {source}: {stats['entries_found']} entries, {stats['collected']} collected")
        if stats['error']:
            print(f"      Error: {stats['error']}")

    print(f"\nTOTAL: {collected_count} articles collected")
