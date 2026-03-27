"""
province_keywords.py
====================
2026년 베트남 행정개편 완전 반영 지방(Province) 검색어 사전

배경:
  2025년 말~2026년 초 베트남은 63개 성→34개 성/시 행정통합 단행
  기존 코드에서 통합된 구 성(省) 이름이 누락되면 뉴스 수집이 누락됨

구성:
  - PROVINCE_KEYWORDS: 34개 성/시 + 5개 중앙직할시 완전 검색어 사전
  - PROVINCE_ALIAS_MAP: 구 성명 → 신 성명 역매핑 (기사 분류용)
  - get_province_from_text(): 본문에서 성/시 이름 자동 추출 함수
  - get_all_keywords(): 전체 검색어 플랫 리스트 반환

업데이트 기준:
  - 2026년 3월 기준 34개 성/시 행정구역 체계
  - 개편 전 63개 성 이름 모두 포함 (뉴스 기사는 구 이름 사용 빈번)
  - 베트남어 악센트 포함/미포함 양식 모두 포함
  - 주요 도시명, 관광지명, 경제특구명 포함
"""

# ════════════════════════════════════════════════════════════
# 핵심 데이터: PROVINCE_KEYWORDS
# 구조: { "표준명(EN)": ["검색어1", "검색어2", ...] }
# ════════════════════════════════════════════════════════════

PROVINCE_KEYWORDS = {

    # ──────────────────────────────────────────────────────
    # 1. 중앙직할시 (5개) - Thành phố trực thuộc Trung ương
    # ──────────────────────────────────────────────────────

    "Ho Chi Minh City": [
        "ho chi minh", "hồ chí minh", "hcmc", "hcm city",
        "saigon", "sai gon", "sài gòn",
        "tp.hcm", "tp hcm", "tp. hcm",
        "thanh pho ho chi minh",
    ],

    "Hanoi": [
        "hanoi", "ha noi", "hà nội", "hànội",
        "capital hanoi", "capital of vietnam",
        "ha dong", "hà đông",           # Hanoi 내 주요 구
        "long bien", "long biên",
    ],

    "Da Nang": [
        "da nang", "đà nẵng", "danang", "đanẵng",
        "da nang city",
    ],

    "Hai Phong": [
        "hai phong", "hải phòng", "haiphong",
        "hp city",
    ],

    "Can Tho": [
        "can tho", "cần thơ", "cantho",
        "can tho city",
    ],

    # ──────────────────────────────────────────────────────
    # 2. 개편 후 34개 성/시 (2026년 기준)
    #    ※ 통합된 구 성 이름 반드시 포함
    # ──────────────────────────────────────────────────────

    # 북부 산악 지방
    "Lao Cai": [
        "lao cai", "lào cai", "laocai",
        "yen bai", "yên bái",           # 통합된 구 성
        "sapa", "sa pa",                # 유명 관광지
        "bac ha", "bắc hà",
    ],

    "Lai Chau": [
        "lai chau", "lai châu", "laichau",
        "muong lay", "mường lay",
    ],

    "Dien Bien": [
        "dien bien", "điện biên", "dien bien phu",
        "điện biên phủ",
    ],

    "Son La": [
        "son la", "sơn la", "sonla",
    ],

    "Tuyen Quang": [
        "tuyen quang", "tuyên quang",
        "ha giang", "hà giang",         # 통합된 구 성
    ],

    "Thai Nguyen": [
        "thai nguyen", "thái nguyên",
        "bac kan", "bắc kạn",           # 통합된 구 성
    ],

    "Lang Son": [
        "lang son", "lạng sơn", "langson",
        "dong dang", "đồng đăng",       # 국경 지역 (물류 허브)
    ],

    "Cao Bang": [
        "cao bang", "cao bằng",
    ],

    "Bac Giang": [
        "bac giang", "bắc giang",
        "yen the", "yên thế",
    ],

    "Quang Ninh": [
        "quang ninh", "quảng ninh",
        "ha long", "hạ long", "halong", "ha long bay", "halong bay",   # 세계유산
        "cam pha", "cẩm phả",           # 석탄 항구
        "van don", "vân đồn",           # 경제특구
        "mong cai", "móng cái",         # 국경무역도시
        "uong bi", "uông bí",
    ],

    # 북부 삼각주 지방
    "Phu Tho": [
        "phu tho", "phú thọ",
        "vinh phuc", "vĩnh phúc",       # 통합된 구 성 (산업단지 밀집)
        "hoa binh", "hòa bình",         # 통합된 구 성
        "viet tri", "việt trì",
    ],

    "Bac Ninh": [
        "bac ninh", "bắc ninh",
        "samsung bac ninh",             # Samsung 주요 공장 소재
        "que vo", "quế võ",             # 공단 지역
    ],

    "Hung Yen": [
        "hung yen", "hưng yên",
        "thai binh", "thái bình",       # 통합된 구 성
        "pho noi", "phố nối",           # 공단 지역
    ],

    "Hai Duong": [
        "hai duong", "hải dương",
        "chi linh", "chí linh",
    ],

    "Ninh Binh": [
        "ninh binh", "ninh bình",
        "ha nam", "hà nam",             # 통합된 구 성
        "nam dinh", "nam định",         # 통합된 구 성
        "trang an", "tràng an",         # 세계유산
        "bai dinh",                     # 관광
    ],

    # 북중부 해안 지방
    "Thanh Hoa": [
        "thanh hoa", "thanh hóa", "thanh hoá",
        "nghi son", "nghi sơn",         # 석유화학 경제특구
        "sam son", "sầm sơn",
    ],

    "Nghe An": [
        "nghe an", "nghệ an",
        "vinh city", "thành phố vinh",
        "vsip nghe an",
    ],

    "Ha Tinh": [
        "ha tinh", "hà tĩnh",
        "vung ang", "vũng áng",         # Formosa 제철소 소재
        "formosa ha tinh",
    ],

    "Quang Binh": [
        "quang binh", "quảng bình",
        "dong hoi", "đồng hới",
        "phong nha", "ke bang",         # 세계유산
    ],

    "Quang Tri": [
        "quang tri", "quảng trị",
        "dong ha", "đông hà",
    ],

    "Thua Thien Hue": [
        "hue", "huế",
        "thua thien hue", "thừa thiên huế", "thua thien",
        "hue city", "imperial city hue",
        "chan may", "chân mây",         # 산업항
        "lang co", "lăng cô",
    ],

    # 남중부 해안 지방
    "Quang Nam": [
        "quang nam", "quảng nam",
        "hoi an", "hội an",             # 세계유산 도시
        "tam ky", "tam kỳ",
        "chu lai", "Chu Lai",           # 경제특구/산업공단
    ],

    "Quang Ngai": [
        "quang ngai", "quảng ngãi",
        "kon tum",                      # 통합된 구 성
        "dung quat", "dung quất",       # 정유소/경제특구
        "sa huynh",
    ],

    "Gia Lai": [
        "gia lai",
        "binh dinh", "bình định",       # 통합된 구 성
        "pleiku", "plei ku",
        "qui nhon", "quy nhơn",         # Binh Dinh 주요 항구
        "an khe", "an khê",
    ],

    "Dak Lak": [
        "dak lak", "đắk lắk", "daklak",
        "phu yen", "phú yên",           # 통합된 구 성
        "buon ma thuot", "buôn ma thuột", "bmt",
        "tuy hoa", "tuy hòa",           # Phu Yen 주도
    ],

    "Khanh Hoa": [
        "khanh hoa", "khánh hòa",
        "ninh thuan", "ninh thuận",     # 통합된 구 성
        "nha trang",                    # 주요 관광도시
        "cam ranh", "cam ranh bay",     # 항구/공항
        "phan rang", "phan rang-thap cham",  # Ninh Thuan 주도
        "van phong", "vân phong",       # 경제특구
    ],

    "Lam Dong": [
        "lam dong", "lâm đồng",
        "dak nong", "đắk nông",         # 통합된 구 성
        "binh thuan", "bình thuận",     # 통합된 구 성
        "da lat", "đà lạt", "dalat",    # 주요 관광도시
        "bao loc", "bảo lộc",
        "phan thiet", "phan thiết",     # Binh Thuan 주도
        "mui ne", "mũi né",             # 관광
    ],

    # 동남부 지방
    "Binh Phuoc": [
        "binh phuoc", "bình phước",
        "dong xoai", "đồng xoài",
    ],

    "Tay Ninh": [
        "tay ninh", "tây ninh",
        "moc bai", "mộc bài",           # 국경 경제특구
    ],

    "Binh Duong": [
        "binh duong", "bình dương",
        "vsip", "vsip binh duong",      # 주요 산업단지
        "thu dau mot", "thủ dầu một",
        "di an", "dĩ an",
        "binh hoa",
    ],

    "Dong Nai": [
        "dong nai", "đồng nai",
        "bien hoa", "biên hòa",         # 산업도시
        "nhon trach", "nhơn trạch",     # LNG 터미널 건설지
        "long thanh", "long thành",     # 신공항 건설지
        "long thanh airport", "long thanh international airport",
    ],

    "Ba Ria Vung Tau": [
        "ba ria vung tau", "bà rịa vũng tàu", "ba ria-vung tau",
        "vung tau", "vũng tàu",
        "ba ria", "bà rịa",
        "can gio", "cần giờ",
        "phu my", "phú mỹ",             # 산업항/LNG
    ],

    "Long An": [
        "long an",
        "tan an", "tân an",
    ],

    # 메콩 삼각주 지방
    "Tien Giang": [
        "tien giang", "tiền giang",
        "my tho", "mỹ tho",
    ],

    "Ben Tre": [
        "ben tre", "bến tre",
    ],

    "Dong Thap": [
        "dong thap", "đồng tháp",
        "cao lanh", "cao lãnh",
        "sa dec", "sa đéc",
    ],

    "Vinh Long": [
        "vinh long", "vĩnh long",
        "tra vinh", "trà vinh",         # 통합된 구 성 (풍력발전 밀집)
    ],

    "An Giang": [
        "an giang",
        "long xuyen", "long xuyên",
        "chau doc", "châu đốc",
    ],

    "Kien Giang": [
        "kien giang", "kiên giang",
        "phu quoc", "phú quốc",         # 특별경제구역/관광
        "rach gia", "rạch giá",
    ],

    "Hau Giang": [
        "hau giang", "hậu giang",
        "soc trang", "sóc trăng",       # 통합된 구 성
        "vi thanh", "vị thanh",
    ],

    "Ca Mau": [
        "ca mau", "cà mau",
        "bac lieu", "bạc liêu",         # 통합된 구 성 (풍력발전)
    ],

    # ──────────────────────────────────────────────────────
    # 3. 주요 경제 권역 / 특별 키워드 (뉴스 빈도 높음)
    # ──────────────────────────────────────────────────────

    "Mekong Delta": [
        "mekong delta", "mekong region",
        "dong bang song cuu long",
        "đồng bằng sông cửu long",
        "mekong",
    ],

    "Central Highlands": [
        "central highlands", "tay nguyen", "tây nguyên",
    ],

    "Red River Delta": [
        "red river delta", "dong bang song hong",
        "đồng bằng sông hồng",
    ],

    "Northern Key Economic Zone": [
        "northern economic zone", "northern key economic zone",
    ],

    "Southern Key Economic Zone": [
        "southern economic zone", "southern key economic zone",
        "southeast vietnam",
    ],

    "Long Thanh Airport": [
        "long thanh airport", "long thanh international",
        "new airport vietnam",
    ],

    # ──────────────────────────────────────────────────────
    # 4. 범국가 키워드 (특정 성 미지정 기사 포함용)
    # ──────────────────────────────────────────────────────

    "Vietnam": [
        "vietnam", "việt nam", "viet nam",
        "nationwide", "across vietnam",
        "ministry of construction",     # 중앙부처 관련 기사
        "ministry of transport",
        "ministry of natural resources",
    ],
}


# ════════════════════════════════════════════════════════════
# 역매핑 사전: 구 성명 → 신 성명 (2026년 통합 기준)
# 기사 Province 컬럼 정규화에 사용
# ════════════════════════════════════════════════════════════

PROVINCE_ALIAS_MAP = {
    # 통합된 구 성 → 신 대표 성명
    "yen bai":       "Lao Cai",
    "yên bái":       "Lao Cai",
    "ha giang":      "Tuyen Quang",
    "hà giang":      "Tuyen Quang",
    "bac kan":       "Thai Nguyen",
    "bắc kạn":       "Thai Nguyen",
    "vinh phuc":     "Phu Tho",
    "vĩnh phúc":     "Phu Tho",
    "hoa binh":      "Phu Tho",
    "hòa bình":      "Phu Tho",
    "ha nam":        "Ninh Binh",
    "hà nam":        "Ninh Binh",
    "nam dinh":      "Ninh Binh",
    "nam định":      "Ninh Binh",
    "thai binh":     "Hung Yen",
    "thái bình":     "Hung Yen",
    "quang binh":    "Quang Tri",     # 참고: 일부 언론은 독립 유지로 보도
    "quảng bình":    "Quang Tri",
    "kon tum":       "Quang Ngai",
    "binh dinh":     "Gia Lai",
    "bình định":     "Gia Lai",
    "phu yen":       "Dak Lak",
    "phú yên":       "Dak Lak",
    "ninh thuan":    "Khanh Hoa",
    "ninh thuận":    "Khanh Hoa",
    "dak nong":      "Lam Dong",
    "đắk nông":      "Lam Dong",
    "binh thuan":    "Lam Dong",
    "bình thuận":    "Lam Dong",
    "tra vinh":      "Vinh Long",
    "trà vinh":      "Vinh Long",
    "soc trang":     "Hau Giang",
    "sóc trăng":     "Hau Giang",
    "bac lieu":      "Ca Mau",
    "bạc liêu":      "Ca Mau",
}


# ════════════════════════════════════════════════════════════
# 유틸리티 함수
# ════════════════════════════════════════════════════════════

def get_all_keywords() -> list:
    """
    PROVINCE_KEYWORDS의 모든 검색어를 플랫(flat) 리스트로 반환
    뉴스 수집기에서 province 필터링 키워드로 사용
    """
    all_kw = []
    for keywords in PROVINCE_KEYWORDS.values():
        all_kw.extend(keywords)
    return list(set(all_kw))  # 중복 제거


def get_province_from_text(text: str) -> str:
    """
    기사 제목/본문에서 성/시 이름을 자동 추출
    
    Args:
        text: 기사 제목 또는 본문 (영어/베트남어 혼용)
    Returns:
        매칭된 표준 성/시 이름 (없으면 "Vietnam")
    """
    if not text:
        return "Vietnam"

    text_lower = text.lower()

    # 정확도 높은 순서로 매칭 (긴 키워드 먼저)
    matches = []
    for province, keywords in PROVINCE_KEYWORDS.items():
        if province == "Vietnam":   # 범국가 키워드는 마지막에 체크
            continue
        for kw in sorted(keywords, key=len, reverse=True):
            if kw in text_lower:
                matches.append((province, len(kw)))
                break

    if not matches:
        return "Vietnam"

    # 가장 긴 키워드(=더 구체적)로 매칭된 결과 우선 반환
    return max(matches, key=lambda x: x[1])[0]


def normalize_province(province_name: str) -> str:
    """
    구 성명을 2026년 통합 후 신 성명으로 정규화
    
    Args:
        province_name: 기사에서 추출한 성/시 이름
    Returns:
        정규화된 성/시 이름
    """
    if not province_name:
        return "Vietnam"
    normalized = PROVINCE_ALIAS_MAP.get(province_name.lower(), province_name)
    return normalized


def get_provinces_for_excel() -> list:
    """
    Excel Province 검색어 시트 업데이트용 데이터 반환
    Returns:
        [{"Province": str, "Keywords": str, "Count": int}, ...]
    """
    result = []
    for province, keywords in PROVINCE_KEYWORDS.items():
        result.append({
            "Province":     province,
            "Keywords":     ", ".join(keywords),
            "Keyword_Count": len(keywords),
            "Category":     _get_region_category(province),
        })
    return result


def _get_region_category(province: str) -> str:
    """성/시를 베트남 지역권으로 분류"""
    northern_mountainous = [
        "Lao Cai", "Lai Chau", "Dien Bien", "Son La",
        "Tuyen Quang", "Thai Nguyen", "Lang Son", "Cao Bang", "Quang Ninh",
    ]
    northern_delta = [
        "Hanoi", "Hai Phong", "Phu Tho", "Bac Ninh", "Bac Giang",
        "Hung Yen", "Hai Duong", "Ninh Binh",
    ]
    north_central = [
        "Thanh Hoa", "Nghe An", "Ha Tinh", "Quang Binh",
        "Quang Tri", "Thua Thien Hue",
    ]
    south_central = [
        "Da Nang", "Quang Nam", "Quang Ngai", "Gia Lai",
        "Dak Lak", "Khanh Hoa", "Lam Dong",
    ]
    southeast = [
        "Ho Chi Minh City", "Binh Phuoc", "Tay Ninh", "Binh Duong",
        "Dong Nai", "Ba Ria Vung Tau", "Long An",
    ]
    mekong = [
        "Can Tho", "Tien Giang", "Ben Tre", "Dong Thap", "Vinh Long",
        "An Giang", "Kien Giang", "Hau Giang", "Ca Mau",
    ]

    if province in northern_mountainous: return "Northern Mountainous"
    if province in northern_delta:       return "Red River Delta"
    if province in north_central:        return "North Central Coast"
    if province in south_central:        return "South Central Coast"
    if province in southeast:            return "Southeast"
    if province in mekong:               return "Mekong Delta"
    return "National/Regional"


# ════════════════════════════════════════════════════════════
# 모듈 단독 실행 시 통계 출력 (테스트용)
# ════════════════════════════════════════════════════════════

if __name__ == "__main__":
    all_kw = get_all_keywords()
    print(f"총 성/시 수: {len(PROVINCE_KEYWORDS)}")
    print(f"총 검색어 수: {len(all_kw)}")
    print(f"역매핑 항목: {len(PROVINCE_ALIAS_MAP)}")
    print("\n지역권별 분류:")
    from collections import Counter
    cats = Counter(_get_region_category(p) for p in PROVINCE_KEYWORDS)
    for cat, cnt in sorted(cats.items()):
        print(f"  {cat}: {cnt}")
    print("\n테스트 - get_province_from_text:")
    tests = [
        "Long Thanh airport construction update",
        "Ha Long Bay industrial park",
        "Samsung Bac Ninh factory expansion",
        "Nhieu Loc wastewater treatment",
        "Mekong Delta flooding",
    ]
    for t in tests:
        print(f"  '{t[:45]}' → {get_province_from_text(t)}")
