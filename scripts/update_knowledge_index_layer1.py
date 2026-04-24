"""
update_knowledge_index_layer1.py  v2.0
========================================
업로드된 주간 보고서 워드파일에서 파싱한 전체 Layer 1 데이터를
knowledge_index.json v2.3에 업서트(upsert)합니다.

포함 데이터 (보고서 원문 기준):
  - 12개 마스터플랜 전체
  - 플랜별: 사업개요 / KPI 47개 / 프로젝트 73개
  - 기존 keywords_en / keywords_vi / match_threshold 유지 (덮어쓰지 않음)

사용법:
  python3 scripts/update_knowledge_index_layer1.py

입력:  docs/shared/knowledge_index.json
출력:  docs/shared/knowledge_index.json (업서트 후 저장)

버전: v2.0 (2026-04-24) — 보고서 원문 전체 반영
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
KI_PATHS = [
    BASE_DIR / 'docs'  / 'shared' / 'knowledge_index.json',
    BASE_DIR / 'data'  / 'shared' / 'knowledge_index.json',
]

# ══════════════════════════════════════════════════════════════════════════
#  Layer 1 전체 데이터 — 업로드된 보고서(20260421) 원문 기준
#  수정하지 마세요. 보고서 업데이트 시 이 딕셔너리만 갱신합니다.
# ══════════════════════════════════════════════════════════════════════════
LAYER1 = {

    # ── 1. 폐수처리 ────────────────────────────────────────────────────
    "VN-WW-2030": {
        "title_ko":  "폐수처리 인프라 국가 마스터플랜 2021~2030",
        "decision":  "Decision 1354/QD-TTg",
        "sector":    "Waste Water",
        "area":      "Environment",
        "description_ko": (
            "국가 폐수처리 마스터플랜(2021~2030)은 도시 폐수처리율을 2025년 50%, 2030년 85%로 "
            "끌어올리는 것을 목표로 한다. 하노이·호치민·다낭 등 주요 도시 권역별 WWTP 신규·확장이 "
            "핵심이다. JICA, ADB, KfW 등 다자금융기관 ODA가 투자의 80% 이상을 차지하며, "
            "민관협력(PPP) 확대가 정책 방향이다. 2024년 기준 하노이 폐수처리율은 약 29%로 "
            "목표(50%, 2025년)에 크게 못 미치나, 옌짜 WWTP 준공(2025.8)으로 처리 용량이 "
            "2배 이상 증가할 전망이다."
        ),
        "kpi_targets": [
            {"indicator": "도시 폐수처리율",   "target_2030": "85%",             "current": "~29% → 50% (하노이 옌짜 준공)"},
            {"indicator": "신규 WWTP 용량",    "target_2030": "2,900,000 m³/일", "current": "약 800,000 m³/일 운영"},
            {"indicator": "ODA 연계 투자",     "target_2030": "$2.5B+",          "current": "JICA $690M (옌짜 준공 확정)"},
        ],
        "key_projects": [
            {"name": "옌짜 (Yen Xa)",          "location": "하노이 (Thanh Tri)",  "capacity": "270,000 m³/일",        "note": "2025.8.19 준공, 북부 최대 시설"},
            {"name": "빈흥 (Binh Hung)",        "location": "호치민 (Binh Chanh)", "capacity": "141,000→512,000 m³/일","note": "2030년까지 단계적 확장"},
            {"name": "투득시 (Thu Duc)",        "location": "호치민 (Thu Duc)",    "capacity": "1,100,000 m³/일",      "note": "동남아 최대, MBBR 기술 적용"},
            {"name": "탐르엉 (Tham Luong)",    "location": "호치민 (Go Vap)",     "capacity": "131,000→310,000 m³/일","note": "2030년 최종 확장 목표"},
            {"name": "응우옌루 (Nhieu Loc)",    "location": "호치민",              "capacity": "480,000 m³/일",        "note": "2026년 완공 예정"},
            {"name": "박탕롱-반찌",            "location": "하노이",              "capacity": "42,000→116,000 m³/일", "note": "2030년까지 용량 증설"},
            {"name": "손짜 (Son Tra)",          "location": "다낭",                "capacity": "60,000 m³/일",         "note": "WB 지원, 2020년 이후 확장"},
            {"name": "화쑤언 (Hoa Xuan)",      "location": "다낭",                "capacity": "100,000 m³/일",        "note": "2030년 2단계 완공 목표"},
            {"name": "년짝 (Nhon Trach)",      "location": "동나이",              "capacity": "30,000 m³/일",         "note": "산업단지 연계 하수처리"},
            {"name": "푸록 (Phu Loc)",          "location": "다낭",                "capacity": "65,000 m³/일",         "note": "바이오필터(Biofilter) 공법"},
        ],
    },

    # ── 2. 고형폐기물 ──────────────────────────────────────────────────
    "VN-SWM-NATIONAL-2030": {
        "title_ko":  "전국 고형폐기물 통합관리 국가전략 2025/2050",
        "decision":  "Decision 491/QD-TTg",
        "sector":    "Solid Waste",
        "area":      "Environment",
        "description_ko": (
            "전국 고형폐기물 관리 전략은 2030년까지 WtE(폐기물 에너지화) 비율을 50%로 높이고 "
            "매립 의존도를 획기적으로 낮추는 것이 핵심이다. 하노이 속선(Soc Son) WtE 발전소 "
            "준공(2025.10, 90MW)이 베트남 WtE 전략의 이정표다. EPR(생산자책임재활용) 규정 시행, "
            "재활용 기반 강화가 중기 정책 방향이다."
        ),
        "kpi_targets": [
            {"indicator": "도시 폐기물 수거율", "target_2030": "100%",     "current": "95% (2025 목표 수준)"},
            {"indicator": "WtE 소각 비율",      "target_2030": "50%",      "current": "30% 목표 (2025), 속선 WtE 가동"},
            {"indicator": "매립 의존율",        "target_2030": "30% 이하", "current": "속선 WtE 가동으로 현저히 감소 중"},
        ],
        "key_projects": [
            {"name": "속선 (Soc Son) WtE",   "location": "하노이",      "capacity": "4,000~5,000 톤/일", "note": "WtE 90MW, 세계 2위 규모, 2025.10 준공"},
            {"name": "다프억 (Da Phuoc)",     "location": "호치민",      "capacity": "10,000 톤/일",      "note": "위생 매립 및 WtE 전환 중"},
            {"name": "남선 (Nam Son) WtE",    "location": "하노이",      "capacity": "4,000 톤/일",       "note": "2025년 완공, 대규모 소각"},
            {"name": "빈즈엉 처리장",          "location": "빈즈엉",      "capacity": "1,500 톤/일",       "note": "재활용 및 WtE 병행"},
            {"name": "푸손 (Phu Son)",        "location": "트어티엔후에", "capacity": "600 톤/일",         "note": "2025.11 가동, 도시폐기물 80% 처리"},
            {"name": "타일라이 (Thoi Lai)",   "location": "껀터",        "capacity": "400 톤/일",         "note": "2024년 준공, 메콩델타 핵심 WtE"},
            {"name": "박닌 WtE (VSIP)",       "location": "박닌",        "capacity": "1,000 톤/일",       "note": "2028년 에너지 회수 최적화 목표"},
            {"name": "쿠찌 (Cu Chi) WtE",     "location": "호치민",      "capacity": "2,000 톤/일",       "note": "WtE 및 퇴비화 복합 공정"},
            {"name": "푸꾸옥 (Phu Quoc)",     "location": "끼엔장",      "capacity": "500 톤/일",         "note": "도서 지역 특화 소각 및 재활용"},
            {"name": "탄호아-롱안",            "location": "롱안",        "capacity": "300→500 톤/일",     "note": "용량 확장 중"},
        ],
    },

    # ── 3. 수자원 관리 ────────────────────────────────────────────────
    "VN-WAT-RESOURCES": {
        "title_ko":  "수자원법 2023 + 국가 수자원 전략 2030",
        "decision":  "Law 28/2023/QH15",
        "sector":    "Water Supply/Drainage",
        "area":      "Environment",
        "description_ko": (
            "베트남은 기후변화로 메콩델타 해수 침투, 홍강 유역 가뭄·홍수 교차, 지하수 과잉 채굴 등 "
            "복합 수자원 위기에 직면해 있다. 2023년 수자원법 전면 개정으로 유역통합관리(IWRM), "
            "지하수 이용 허가제, 오염자부담 원칙이 강화됐다. ADB·세계은행 지원 하에 메콩델타 "
            "수자원 인프라 현대화가 가속 중이다."
        ),
        "kpi_targets": [
            {"indicator": "지하수 관리 대수층",    "target_2030": "전국 27개 완전 관리", "current": "12개 관리 중"},
            {"indicator": "중복 댐·저수지 안전진단","target_2030": "100% 완료",          "current": "65% 완료"},
            {"indicator": "홍수 피해 GDP 비중",    "target_2030": "0.5% 미만으로 감소", "current": "연평균 1.2%"},
        ],
        "key_projects": [
            {"name": "메콩델타 수자원 현대화",  "location": "메콩델타",  "capacity": "대규모 인프라", "note": "ADB·세계은행 지원"},
            {"name": "홍강 유역 홍수 관리",     "location": "홍강 유역", "capacity": "유역통합관리", "note": "환경부 주관, IWRM 적용"},
            {"name": "메콩강 MRC 모니터링",     "location": "메콩강",    "capacity": "예측 시스템",  "note": "홍수·가뭄 조기 경보 체계"},
        ],
    },

    # ── 4. 도시 상수도 ────────────────────────────────────────────────
    "VN-WAT-URBAN": {
        "title_ko":  "국가 상수도 개발전략 2030",
        "decision":  "Decision 1979/QD-TTg",
        "sector":    "Water Supply/Drainage",
        "area":      "Environment",
        "description_ko": (
            "국가 상수도 개발전략은 2030년 도시 지역 100% 안전 수돗물 보급을 목표로 한다. "
            "ADB가 빈증성 바우방(Bau Bang) 정수장 확장($200M+), KfW가 중부 지역 상수도 현대화를 "
            "지원 중이다. 민영화(PPP·BOT) 확대로 TDM 수자원(빈증), BWS(호치민) 등 민간 사업자의 "
            "역할이 증가하고 있다."
        ),
        "kpi_targets": [
            {"indicator": "도시 안전 상수 보급률", "target_2030": "100%",     "current": "95% 수준 (2025)"},
            {"indicator": "1인당 공급량",          "target_2030": "150 L/일", "current": "120 L/일 (2025 목표)"},
            {"indicator": "누수율",                "target_2030": "15% 이하", "current": "20% 이하 (2025 목표)"},
        ],
        "key_projects": [
            {"name": "송다 (Song Da)",             "location": "화빈",        "capacity": "600,000 m³/일",  "note": "하노이 및 인근 성"},
            {"name": "투득 (Thu Duc)",             "location": "호치민",      "capacity": "500,000 m³/일",  "note": "호치민 중심부"},
            {"name": "꺼우도 (Cau Do)",            "location": "다낭",        "capacity": "250,000 m³/일",  "note": "다낭시 전역"},
            {"name": "동아인 (Dong Anh)",          "location": "하노이",      "capacity": "150,000 m³/일",  "note": "하노이 북부 신도시"},
            {"name": "동나이 (Dong Nai)",          "location": "동나이",      "capacity": "200,000 m³/일",  "note": "비엔화 및 호치민"},
            {"name": "닌투언 (Ninh Thuan)",        "location": "닌투언",      "capacity": "80,000 m³/일",   "note": "판랑-탑짬"},
            {"name": "껀터 2 (Can Tho 2)",         "location": "껀터",        "capacity": "120,000 m³/일",  "note": "껀터시 중심권"},
            {"name": "타이닌 (Tay Ninh)",          "location": "타이닌",      "capacity": "90,000 m³/일",   "note": "타이닌성"},
            {"name": "붕따우 (Vung Tau)",          "location": "바리아붕따우", "capacity": "100,000 m³/일", "note": "붕따우시 전역"},
            {"name": "동탑 (Dong Thap)",           "location": "동탑",        "capacity": "70,000 m³/일",   "note": "까오라인"},
            {"name": "꽝찌 (Quang Tri)",           "location": "꽝찌",        "capacity": "75,000 m³/일",   "note": "동하"},
            {"name": "끼엔장 (Kien Giang)",        "location": "끼엔장",      "capacity": "85,000 m³/일",   "note": "락지아"},
            {"name": "라오카이 (Lao Cai)",         "location": "라오카이",    "capacity": "60,000 m³/일",   "note": "라오카이시"},
            {"name": "하남 (Ha Nam)",              "location": "하남",        "capacity": "100,000 m³/일",  "note": "풀리"},
            {"name": "꽝응아이 (Quang Ngai)",      "location": "꽝응아이",    "capacity": "80,000 m³/일",   "note": "꽝응아이시"},
            {"name": "박장 (Bac Giang)",           "location": "박장",        "capacity": "95,000 m³/일",   "note": "박장시"},
            {"name": "푸옌 (Phu Yen)",             "location": "푸옌",        "capacity": "70,000 m³/일",   "note": "뚜이호아"},
            {"name": "빈증 (Binh Duong)",          "location": "빈증",        "capacity": "120,000 m³/일",  "note": "투저우못 (확장)"},
            {"name": "응에안 (Nghe An)",           "location": "응에안",      "capacity": "85,000 m³/일",   "note": "빈(Vinh)"},
            {"name": "칸화 (Khanh Hoa)",           "location": "칸화",        "capacity": "110,000 m³/일",  "note": "냐짱"},
        ],
    },

    # ── 5. 재생에너지 ─────────────────────────────────────────────────
    "VN-PWR-PDP8-RENEWABLE": {
        "title_ko":  "전력개발계획 PDP8 개정 — 해상풍력·태양광·DPPA",
        "decision":  "Decision 768/QD-TTg (2025.4.15)",
        "sector":    "Power",
        "area":      "Energy Develop.",
        "description_ko": (
            "2025년 4월 Decision 768로 PDP8이 전면 개정됐다. GDP 성장률 목표 7%→10% 상향이 "
            "전력 수요 재계산을 촉발했으며, 해상풍력 목표가 3배 가까이 늘었다. "
            "Decree 57(DPPA·직접전력구매계약) 시행으로 RE100 기업의 재생에너지 직구매가 "
            "가능해졌다. 2030년까지 총 투자 $134.7B 규모다."
        ),
        "kpi_targets": [
            {"indicator": "해상풍력(2030)",        "target_2030": "17,032 MW",     "current": "6,000MW → 3배 상향 확정", "changed": True},
            {"indicator": "육상풍력(2030)",        "target_2030": "38,029 MW",     "current": "21,880MW (PDP8 원안) 대폭 상향"},
            {"indicator": "태양광(2030)",          "target_2030": "73 GW",         "current": "26,046MW → 대폭 상향"},
            {"indicator": "BESS 배터리(2030)",     "target_2030": "10,000 MW",     "current": "300MW → 33배 상향", "changed": True},
        ],
        "key_projects": [
            {"name": "해상풍력 Zone 1~6",          "location": "남중국해 연안",    "capacity": "17,032 MW (2030)",  "note": "Equinox/Orsted/Viet Dragon 입찰 준비"},
            {"name": "닌투언 태양광 단지",         "location": "닌투언성",         "capacity": "73 GW (2030 누적)", "note": "FiT→경쟁입찰 전환 추진"},
            {"name": "BESS 배터리 저장",           "location": "전국",             "capacity": "10,000 MW (2030)", "note": "Decision 768 신규 대폭 상향"},
            {"name": "DPPA 직접구매 시장",         "location": "전국",             "capacity": "시장 개방",         "note": "삼성·인텔 등 RE100 계약 추진"},
        ],
    },

    # ── 6. LNG 발전 ───────────────────────────────────────────────────
    "VN-PWR-PDP8-LNG": {
        "title_ko":  "LNG 발전 인수보장 + 닌투언 LNG 허브",
        "decision":  "Decree 100/2025/ND-CP",
        "sector":    "Power",
        "area":      "Energy Develop.",
        "description_ko": (
            "Decree 100(2025)은 LNG 발전사업의 최소 연간 발전량 65% 인수를 보장하는 "
            "정부 보증을 법제화해 외국인 투자자의 진입 장벽을 크게 낮췄다. "
            "닌투언LNG 복합터미널, 박류-탄호아 LNG 등 대형 프로젝트가 FID(최종투자결정) "
            "단계에 있다."
        ),
        "kpi_targets": [
            {"indicator": "LNG 수입 터미널",  "target_2030": "8개소",     "current": "2개소 운영 중"},
            {"indicator": "LNG 발전 용량",    "target_2030": "23,900 MW", "current": "약 3,000 MW"},
            {"indicator": "연간 LNG 수입량",  "target_2030": "14백만 톤", "current": "2백만 톤"},
        ],
        "key_projects": [
            {"name": "닌투언 LNG 복합터미널", "location": "닌투언성",     "capacity": "LNG 허브",     "note": "FID 단계 추진"},
            {"name": "박류-탄호아 LNG",       "location": "탄호아성",     "capacity": "대규모 LNG",   "note": "FID 단계"},
            {"name": "티바이 LNG",            "location": "바리아붕따우", "capacity": "LNG 터미널",   "note": "2023년 운영 개시"},
            {"name": "까마우 LNG",            "location": "까마우성",     "capacity": "LNG 발전",     "note": "가스전 연계"},
        ],
    },

    # ── 7. 원자력 ────────────────────────────────────────────────────
    "VN-PWR-PDP8-NUCLEAR": {
        "title_ko":  "원자력 재개 — Resolution 70-NQ/TW (2025) / 닌투언 1·2호기",
        "decision":  "Resolution 70-NQ/TW (2025)",
        "sector":    "Power",
        "area":      "Energy Develop.",
        "description_ko": (
            "2025년 정치국 결의(Resolution 70)로 2010년 중단된 원자력 재개 추진이 공식화됐다. "
            "닌투언 1호기(러시아 Rosatom, 2,000MW)와 2호기(일본 ADB 컨소시엄) 개발 재개가 "
            "확정됐으며, 소형모듈원전(SMR) 도입도 검토 중이다. "
            "에너지 안보·탄소중립 이중 과제 대응이 배경이다."
        ),
        "kpi_targets": [
            {"indicator": "원자력 발전 용량(2035)", "target_2030": "4,000 MW (2035 목표)", "current": "Decision 768 신규 추가", "changed": True},
            {"indicator": "닌투언 1호기",           "target_2030": "2,000 MW",             "current": "Rosatom, 재개 확정"},
            {"indicator": "닌투언 2호기",           "target_2030": "2,000 MW",             "current": "일본 컨소시엄, 협의 중"},
        ],
        "key_projects": [
            {"name": "닌투언 1호기 (Rosatom)",      "location": "닌투언성", "capacity": "2,000 MW", "note": "러시아 기술, 2025 재개 확정"},
            {"name": "닌투언 2호기 (Japan)",        "location": "닌투언성", "capacity": "2,000 MW", "note": "일본 ADB 컨소시엄, 협의 진행"},
            {"name": "SMR 소형모듈원전",            "location": "검토 중",  "capacity": "미정",      "note": "2040년대 도입 검토 중"},
        ],
    },

    # ── 8. 석유·가스 ─────────────────────────────────────────────────
    "VN-OG-2030": {
        "title_ko":  "석유가스 개발전략 2030 — PVN 국가 에너지 안보",
        "decision":  "PVN 국가 에너지 안보전략 2030",
        "sector":    "Oil & Gas",
        "area":      "Energy Develop.",
        "description_ko": (
            "베트남 석유가스공사(PVN)는 바흐호(Bach Ho)·람손(Rang Dong) 등 노후 유전 생산 감소에 "
            "대응해 심해 탐사(113·115·129 블록)와 LNG 공급망 구축을 병행 추진 중이다. "
            "국내 가스전(Ca Mau·Nam Con Son)을 LNG 발전소와 연계하는 통합 공급망이 핵심 전략이다."
        ),
        "kpi_targets": [
            {"indicator": "원유 생산량",        "target_2030": "8~10백만 톤/년",  "current": "11백만 톤/년 (유지 목표)"},
            {"indicator": "가스 생산량",        "target_2030": "13~15억 m³/년",   "current": "10억 m³/년"},
            {"indicator": "LNG 수입 의존도",    "target_2030": "국내 가스 우선 활용", "current": "2백만 톤/년 수입"},
        ],
        "key_projects": [
            {"name": "바흐호 유전 (Bach Ho)",   "location": "바리아붕따우 해상", "capacity": "원유 생산",   "note": "노후화 대응, 심해 탐사 병행"},
            {"name": "113·115·129 블록 탐사",  "location": "남중국해 심해",     "capacity": "탐사 단계",   "note": "PVN 주도, 국제 컨소시엄"},
            {"name": "까마우 가스전",           "location": "까마우성 해상",     "capacity": "국내 공급",   "note": "LNG 발전소 연계 통합 공급"},
            {"name": "남콘손 파이프라인",       "location": "남부 해상",         "capacity": "파이프라인",  "note": "가스 육상 이송 핵심 인프라"},
        ],
    },

    # ── 9. 교통인프라 ────────────────────────────────────────────────
    "VN-TRAN-2055": {
        "title_ko":  "국가 교통인프라 마스터플랜 2021~2030, Vision 2050",
        "decision":  "Decision 1454/QD-TTg",
        "sector":    "Transport",
        "area":      "Urban Develop.",
        "description_ko": (
            "교통인프라 마스터플랜은 2030년 고속도로 5,000km, 항구·공항 대규모 확충을 목표로 한다. "
            "롱탄 국제공항($18B, 4단계)은 핵심 메가프로젝트로 2026년 1단계 개항이 목전이다. "
            "하노이 링로드4, 호치민 링로드3·고가도로, 라크후옌 항구 확장이 병행 추진 중이다. "
            "PPP(BOT) 방식 확대로 민간 참여가 증가하고 있다."
        ),
        "kpi_targets": [
            {"indicator": "고속도로 총연장",       "target_2030": "5,000 km",          "current": "1,892 km (2025 실적)"},
            {"indicator": "롱탄공항 개항",         "target_2030": "25M PAX/년 (1단계)","current": "2026.06 상업운항 목표", "changed": True},
            {"indicator": "공항 네트워크",         "target_2030": "30개 공항",          "current": "22개 운영"},
            {"indicator": "항만 처리 용량",        "target_2030": "1,100M 톤/년",       "current": "600M 톤/년"},
        ],
        "key_projects": [
            {"name": "롱탄 국제공항",              "location": "동나이성",  "capacity": "25M PAX (1단계)",     "note": "2026.06 개항 목표, $18B (4단계)"},
            {"name": "링로드4 (호치민)",           "location": "호치민 광역","capacity": "200km, $5.4B",       "note": "병행도로 2026.6 개통"},
            {"name": "링로드4 (하노이)",           "location": "하노이",     "capacity": "113km, $3.6B",       "note": "착공 진행 중"},
            {"name": "라크후옌 항구 2단계",        "location": "하이퐁",     "capacity": "심해 컨테이너",       "note": "국제 화물 허브"},
            {"name": "호치민 메트로 1호선",        "location": "호치민",     "capacity": "19.7km, 14역",        "note": "2024.12 개통 완료"},
        ],
    },

    # ── 10. 도시철도 메트로 ─────────────────────────────────────────
    "VN-URB-METRO-2030": {
        "title_ko":  "도시철도 국가전략 2030 — 하노이·호치민 15개 노선 계획",
        "decision":  "도시철도 국가전략 2030",
        "sector":    "Smart City",
        "area":      "Urban Develop.",
        "description_ko": (
            "하노이와 호치민은 각각 2030년까지 메트로 15개·8개 노선 완성을 목표로 하지만 "
            "재원조달·용지보상·기술역량 부족으로 지연이 상시적이다. "
            "하노이 2A(껫린~하동)·3(못처~하노이역 부분) 운영 중이고, 1·2B·4호선이 건설 중이다. "
            "호치민 1호선(벤탄~수오이티엔)은 2024년 말 개통됐다."
        ),
        "kpi_targets": [
            {"indicator": "하노이 메트로 목표",   "target_2030": "15개 노선",    "current": "2A·3호선 운영, 1·2B 건설"},
            {"indicator": "호치민 메트로 목표",   "target_2030": "8개 노선",     "current": "1호선 2024.12 개통"},
            {"indicator": "전국 도시철도 목표",   "target_2030": "46개 노선 3,045km","current": "약 5개 노선 운영/건설"},
        ],
        "key_projects": [
            {"name": "하노이 2A (껫린~하동)",       "location": "하노이", "capacity": "13km",              "note": "운영 중 (2021)"},
            {"name": "하노이 3 (못처~하노이역)",    "location": "하노이", "capacity": "부분 운영",         "note": "운영 중"},
            {"name": "하노이 1호선",               "location": "하노이", "capacity": "38.7km",            "note": "건설 중, 2027 목표"},
            {"name": "하노이 2B·4호선",            "location": "하노이", "capacity": "계획 중",           "note": "2030 이후 단계별"},
            {"name": "호치민 1호선 (벤탄~수오이티엔)","location": "호치민","capacity": "19.7km, 14역",    "note": "2024.12 개통, 운영 중"},
            {"name": "호치민 2호선",               "location": "호치민", "capacity": "11.3km",            "note": "건설 중, ODA 확보"},
        ],
    },

    # ── 11. 북부 산업단지 ────────────────────────────────────────────
    "VN-IP-NORTH-2030": {
        "title_ko":  "북부 산업단지 개발계획 2030 — FDI 유입 핵심 거점",
        "decision":  "북부 산업단지 개발계획 2030",
        "sector":    "Industrial Parks",
        "area":      "Urban Develop.",
        "description_ko": (
            "북부 산업단지 클러스터(하이퐁·박닌·타이응우옌·박장·흥옌)는 삼성·LG·인텔·폭스콘 등 "
            "글로벌 전자·반도체 공급망의 핵심 기지다. VSIP(베트남-싱가포르 산업단지)는 19개 단지를 "
            "운영 중이며, 타이빈성 신규 착공으로 확장 중이다. "
            "2025~2030년 반도체·배터리·첨단제조 클러스터 집중 육성이 정책 방향이다."
        ),
        "kpi_targets": [
            {"indicator": "VSIP 단지 수",        "target_2030": "25개 이상",       "current": "19개 운영 (타이빈 신규 착공)"},
            {"indicator": "첨단산업 비중",        "target_2030": "40% 이상",        "current": "전자·반도체 집중 육성"},
            {"indicator": "FDI 유입",             "target_2030": "연 $20B 이상",    "current": "2025년 $18B 수준"},
            {"indicator": "배터리·반도체 거점",  "target_2030": "특화 클러스터 3개","current": "박닌·하이퐁 중심"},
            {"indicator": "일자리 창출",         "target_2030": "400만 명",        "current": "250만 명 (2024)"},
            {"indicator": "하이퐁 신규 단지",    "target_2030": "15개 단지",       "current": "DEEP C 등 10개 운영"},
            {"indicator": "타이응우옌 확장",     "target_2030": "삼성 EV 전환",    "current": "삼성 SDI 배터리 투자"},
            {"indicator": "박장 클러스터",       "target_2030": "반도체 특화",     "current": "Foxconn 확장"},
            {"indicator": "흥옌 신도시",         "location": "하노이 인근",        "note": "첨단제조 복합단지"},
            {"indicator": "환경 기준 강화",      "target_2030": "ISO 14001 의무화","current": "2025년 시범 도입"},
            {"indicator": "신재생에너지 공급",   "target_2030": "30% RE 달성",     "current": "DPPA 활용 추진"},
            {"indicator": "스마트 물류 허브",    "target_2030": "5개 허브 구축",   "current": "라크후옌 항구 연계"},
        ],
        "key_projects": [
            {"name": "VSIP 타이빈 (신규)",       "location": "타이빈성",   "capacity": "신규 착공",    "note": "19번째 VSIP 단지"},
            {"name": "DEEP C 하이퐁",            "location": "하이퐁",     "capacity": "1,300 ha",     "note": "외국인 투자 선호 1순위"},
            {"name": "삼성 SDI 배터리",          "location": "타이응우옌", "capacity": "EV 배터리",    "note": "스마트폰→EV 공급망 전환"},
            {"name": "폭스콘 박장 확장",         "location": "박장성",     "capacity": "반도체 부품",  "note": "애플 공급망 핵심 거점"},
            {"name": "인텔 하이퐁",              "location": "하이퐁",     "capacity": "반도체 패키징","note": "최대 외투 반도체 시설"},
        ],
    },

    # ── 12. 하노이 도시개발 ──────────────────────────────────────────
    "VN-HAN-URBAN-2045": {
        "title_ko":  "하노이 도시개발 마스터플랜 2045/2065",
        "decision":  "Decision 1668/QD-TTg (2024.12)",
        "sector":    "Smart City",
        "area":      "Urban Develop.",
        "description_ko": (
            "2024년 12월 Decision 1668로 확정된 하노이 도시개발 마스터플랜 2045/2065는 "
            "9×9×9 다핵다중심 클러스터 모델을 적용해 5대 도시권·7개 위성도시를 체계화한다. "
            "총 투자 $2.5T(2026~2045), 인구 2045년 최대 16M 수용이 목표다. "
            "링로드4(113km, $3.6B) 착공이 서막이며, 홍강 양안 신도시, 또리히강 정화, "
            "15개 메트로 노선이 핵심이다."
        ),
        "kpi_targets": [
            {"indicator": "도시개발 총투자",   "target_2030": "$2.5T (2026~2045)", "current": "Decision 1668 확정"},
            {"indicator": "인구 수용 목표",    "target_2030": "16M명 (2045)",      "current": "현재 8.5M명"},
            {"indicator": "링로드4 완공",      "target_2030": "2027년 전체 완공",  "current": "착공 진행"},
        ],
        "key_projects": [
            {"name": "동아인 (BRG 스마트시티)", "location": "하노이 동아인구",   "note": "1단계 착공. 639m(108층) 금융타워 포함"},
            {"name": "호아락 (Hoa Lac) 하이테크","location": "하노이 서부",       "note": "460ha 확장. AI/반도체 '베트남 실리콘밸리'"},
            {"name": "링로드4 (113km)",          "location": "하노이 광역",       "note": "$3.6B, 착공 진행 중, 2027 완공 목표"},
            {"name": "홍강 양안 신도시",         "location": "하노이 홍강변",     "note": "5대 도시권 중 핵심 개발 지구"},
            {"name": "또리히강 정화 프로젝트",  "location": "하노이 도심",       "note": "옌짜 WWTP 연계, 도심 수질 개선"},
        ],
    },
}


# ══════════════════════════════════════════════════════════════════════════
#  실행
# ══════════════════════════════════════════════════════════════════════════
def main():
    ki_path = None
    for p in KI_PATHS:
        if p.exists():
            ki_path = p
            break

    if not ki_path:
        print("⚠  knowledge_index.json 없음 — Layer1만 standalone 저장")
        # standalone 모드: data/shared/ 폴더에 layer1_data.json 저장
        out_path = BASE_DIR / 'data' / 'shared' / 'layer1_data.json'
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(LAYER1, f, ensure_ascii=False, indent=2)
        print(f"✅ Layer1 standalone 저장: {out_path}")
        print(f"   generate_mi_report.py가 이 파일을 자동으로 읽습니다.")
        return

    print(f"📂 대상 파일: {ki_path}")
    bak = ki_path.with_suffix(f'.bak_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
    shutil.copy2(ki_path, bak)
    print(f"💾 백업: {bak.name}")

    with open(ki_path, 'r', encoding='utf-8') as f:
        ki = json.load(f)

    plans = ki.get('masterplans', {})
    if not isinstance(plans, dict):
        print("❌ masterplans가 dict 구조가 아닙니다.")
        return

    print(f"\n📋 knowledge_index: {len(plans)}개 플랜")
    print(f"   Layer1 데이터:    {len(LAYER1)}개 플랜\n")

    updated = []
    added_new = []

    for plan_id, layer1 in LAYER1.items():
        if plan_id not in plans:
            # 플랜 자체가 없으면 기본 구조로 신규 추가
            plans[plan_id] = {
                'sectors': [layer1['sector']],
                'area': layer1['area'],
                'keywords_en': [],
                'keywords_vi': [],
                'match_threshold': 50,
            }
            added_new.append(plan_id)
            print(f"  ➕ {plan_id} — 신규 플랜 추가")

        plan = plans[plan_id]
        changed_fields = []

        # Layer1 필드 업서트 (기존 keywords_en 등 유지하면서 Layer1 필드만 덮어씀)
        for field, value in layer1.items():
            if field in ('sector', 'area'):
                continue  # sectors 배열 우선 유지
            plan[field] = value
            changed_fields.append(field)

        updated.append(plan_id)
        print(f"  ✅ {plan_id} — {', '.join(changed_fields[:3])}{'...' if len(changed_fields)>3 else ''} 업서트")

    ki['updated_at'] = datetime.now().strftime('%Y-%m-%d')
    ki.setdefault('changelog', {})['layer1_v2'] = f"Full Layer1 upsert ({datetime.now().strftime('%Y-%m-%d')}) — {len(LAYER1)} plans"

    with open(ki_path, 'w', encoding='utf-8') as f:
        json.dump(ki, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*55}")
    print(f"✅ 저장 완료: {ki_path}")
    print(f"   업서트: {len(updated)}개 플랜")
    print(f"   신규 추가: {len(added_new)}개 플랜")
    total_kpi  = sum(len(v['kpi_targets'])  for v in LAYER1.values())
    total_proj = sum(len(v['key_projects']) for v in LAYER1.values())
    print(f"   KPI:  {total_kpi}개 / 프로젝트: {total_proj}개")


if __name__ == '__main__':
    main()
