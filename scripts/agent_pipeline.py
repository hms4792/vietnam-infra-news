"""
Agent Pipeline - Vietnam Infrastructure News
Agent 1: News Collection  — gsk search (35개 쿼리)
Agent 2: Smart Classification — 키워드 + gsk summarize 기반
Agent 3: KB Matching (12 master plans) — 키워드 스코어링
Agent 4: Multilingual Summary — gsk summarize (KR/EN/VN)
Agent 5: Quality Control — 14개 항목

※ Anthropic API 불필요 — gsk CLI만 사용
"""

import os
import sys
from urllib.parse import urlparse
import json
import time
import hashlib
import subprocess
import re
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'), override=True)

# ──────────────────────────────────────────────────────────────
# gsk 래퍼
# ──────────────────────────────────────────────────────────────

_GSK_COUNTER = 0  # 호출 인덱스 (임시 파일명 고유화)

def _gsk(args: list, timeout: int = 35) -> dict:
    """gsk CLI 호출 → JSON 파싱 결과 반환. 실패/타임아웃 시 {}
    tmux 세션을 통해 TTY 환경에서 실행 → gsk stdout flush 문제 해결.
    """
    global _GSK_COUNTER
    import shlex
    _GSK_COUNTER += 1
    out_file = f"/tmp/_gsk_out_{_GSK_COUNTER}.json"
    done_file = f"/tmp/_gsk_done_{_GSK_COUNTER}.txt"

    # 임시 파일 초기화
    for f in [out_file, done_file]:
        try: os.unlink(f)
        except: pass

    inner = "gsk " + " ".join(shlex.quote(a) for a in args)
    cmd = f"{inner} > {shlex.quote(out_file)} 2>/dev/null; echo done > {shlex.quote(done_file)}"

    # tmux 세션에 명령 전송
    sess = "gsk_agent_pipeline"
    subprocess.run(f"tmux new-session -d -s {sess} 2>/dev/null || true", shell=True)
    subprocess.run(f"tmux send-keys -t {sess} {shlex.quote(cmd)} Enter", shell=True)

    # done_file 생성될 때까지 대기
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(done_file):
            break
        time.sleep(0.5)
    else:
        return {}  # timeout

    try:
        raw = open(out_file, encoding="utf-8", errors="ignore").read().strip()
        # ANSI escape 제거
        raw = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', raw)
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception:
        pass
    finally:
        for f in [out_file, done_file]:
            try: os.unlink(f)
            except: pass
    return {}


def gsk_search(query: str) -> list:
    """gsk search → organic_results 리스트 반환"""
    data = _gsk(["search", query]) or {}
    return (data.get("data") or {}).get("organic_results", [])


def gsk_crawl(url: str) -> str:
    """gsk crawl → 기사 본문 텍스트 반환"""
    data = _gsk(["crawl", url], timeout=30) or {}
    return (data.get("data") or {}).get("result", "")


def gsk_summarize(url_or_text: str, question: str) -> str:
    """
    gsk summarize로 질문에 대한 답 생성.
    url이면 URL로, 아니면 임시 파일 경로로 전달.
    """
    import tempfile
    if url_or_text.startswith("http"):
        data = _gsk(["summarize", url_or_text, "--question", question], timeout=60)
    else:
        # 텍스트를 임시 파일로 저장 후 전달
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt',
                                         delete=False, encoding='utf-8') as f:
            f.write(url_or_text)
            tmp_path = f.name
        data = _gsk(["summarize", tmp_path, "--question", question], timeout=60)
        try:
            os.unlink(tmp_path)
        except:
            pass
    return data.get("data", {}).get("result", "")


# ──────────────────────────────────────────────────────────────
# 공통 설정
# ──────────────────────────────────────────────────────────────

# 12 마스터플랜 정의
MASTERPLANS = [
    # ── 0. PDP8 상위 플랜 (Claude knowledge_index 통합 ID) ──────────────
    # Decision 768/QD-TTg (Apr 15, 2025) — Revised PDP8 ($136.3B 2026-2030)
    {
        "id": "VN-PWR-PDP8",
        "parent": None,  # 최상위 플랜
        "name_ko": "베트남 국가전력개발계획 8차 (PDP8)",
        "keywords": ["pdp8", "pdp 8", "pdp-8", "pdp viii", "pdp-viii",
                     "power development plan", "quy hoạch điện",
                     "electricity plan", "national power plan",
                     "decision 500", "decision 768", "qd-ttg",
                     "전력개발계획", "이니치계획"],
        "threshold": 2,
    },
    # ── 1. PDP8 재생에너지 (태양광·풍력·수력) ──────────────────────────
    {
        "id": "VN-PWR-PDP8-RENEWABLE",
        "parent": "VN-PWR-PDP8",  # 상위 플랜
        "name_ko": "PDP8 재생에너지 (태양광·풍력·수력)",
        "keywords": ["offshore wind", "onshore wind", "solar power", "solar capacity",
                     "wind capacity", "solar farm", "floating solar", "rooftop solar",
                     "wind power", "wind turbine", "hydropower", "pumped storage",
                     "battery storage", "re capacity", "renewable energy",
                     "nhà máy điện", "năng lượng tái tạo",
                     "phong điện", "điện mặt trời", "nàng lượng tái tạo",
                     "발전소 건설", "재생에너지", "태양광", "풍력", "수력"],
        "exclude_if": ["electric vehicle", "vinfast", "ev charger", "wastewater treatment",
                       "highway construction", "metro line", "lng terminal",
                       "nuclear power plant", "coal phase"],
        "threshold": 2,
    },
    # ── 2. 환경산업 발전 프로그램 (Decision 1894) ──────────────────────
    {
        "id": "VN-ENV-IND-1894",
        "name_ko": "베트남 환경산업 발전 프로그램 (Decision 1894)",
        "keywords": ["decision 1894", "environmental industry", "waste-to-energy", "wte",
                     "industrial waste", "solid waste management", "pollution control",
                     "air quality monitoring", "waste management", "epr",
                     "circular economy vietnam", "environmental monitoring",
                     "환경산업", "폐기물 에너지화", "산업폐기물"],
        "exclude_if": ["wastewater treatment plant", "water supply plant", "electric vehicle"],
        "threshold": 2,
    },
    # ── 3. 교통인프라 마스터플랜 2055 ─────────────────────────────────
    {
        "id": "VN-TRAN-2055",
        "name_ko": "베트남 교통인프라 마스터플랜 2055",
        "keywords": ["expressway", "highway", "high-speed rail", "railway project",
                     "port expansion", "airport terminal", "bridge construction", "ring road",
                     "north-south expressway", "long thanh", "lach huyen",
                     "transport infrastructure", "road construction", "km of road",
                     "đường cao tốc", "cầu", "sân bay", "cảng",
                     "고속도로", "교통 인프라", "교량 건설", "항만"],
        "exclude_if": ["electric vehicle", "metro line", "subway", "power plant gw",
                       "wastewater plant", "smart grid"],
        "threshold": 2,
    },
    # ── 4. 도시철도·메트로 2030 ────────────────────────────────────────
    {
        "id": "VN-URB-METRO-2030",
        "name_ko": "베트남 도시철도·메트로 개발계획 2030",
        "keywords": ["metro line", "urban rail", "subway construction", "mrt system",
                     "light rail transit", "hanoi metro", "hcmc metro", "tàu điện ngầm",
                     "đường sắt đô thị", "cat linh", "nhon ga",
                     "지하철 노선", "도시철도", "메트로 건설"],
        "exclude_if": ["highway", "airport", "seaport", "electric vehicle", "power plant"],
        "threshold": 2,
    },
    # ── 5. PDP8 LNG 발전 & 인프라 ────────────────────────────────────
    {
        "id": "VN-PWR-PDP8-LNG",
        "parent": "VN-PWR-PDP8",
        "name_ko": "PDP8 LNG 가스발전",
        "keywords": ["lng", "gas power", "lng terminal", "gas-fired power",
                     "combined cycle", "khi hoi long",
                     "nha may dien khi", "LNG설비", "가스발전소", "LNGE이설비",
                     "가스", "lng", "천연가스"],
        "exclude_if": ["electric vehicle", "ev charger", "solar farm gw",
                       "wind turbine mw", "highway construction",
                       "metro line", "wastewater treatment plant"],
        "threshold": 2,
    },
    # ── 6. 수자원 개발 마스터플랜 2050 ────────────────────────────────
    {
        # ── 6a. 수자원 마스터플랜 (Decision 1622) — 유역 관리·수안보
        "id": "VN-WAT-RESOURCES",
        "name_ko": "국가 수자원 마스터플랜 2021-2030/2050 (Decision 1622)",
        "keywords": [
            "water resources master plan", "river basin management", "water security",
            "flood control", "drought relief", "saltwater intrusion", "dam reservoir",
            "irrigation infrastructure", "groundwater", "water resource distribution",
            "mekong water resources", "red river water resources", "water basin",
            "decision 1622 water", "tài nguyên nước", "quy hoạch tài nguyên nước",
            "lưu vực sông", "an ninh nguồn nước", "hạn hán", "xâm nhập mặn",
            "lũ lụt", "đập thủy lợi", "hồ chứa", "nước ngầm",
            "수자원", "하천유역", "수안보", "염수침입", "가뭄", "홍수 방지"],
        "exclude_if": ["wastewater treatment plant", "water supply plant construction",
                       "electric vehicle", "power plant mw", "lng"],
        "threshold": 2,
    },
    # ── 6b. 도시 상수도 인프라 (MOC) ────────────────────────────────────
    {
        "id": "VN-WAT-URBAN",
        "name_ko": "도시 상수도 인프라 개발 계획 2025/2035 (MOC)",
        "keywords": [
            "water supply plant", "water treatment plant", "clean water supply",
            "water pipeline", "drinking water", "water network", "water loss reduction",
            "safe water program", "urban water supply", "water coverage",
            "water meter", "smart water", "water tariff", "centralized water supply",
            "nhà máy nước", "cấp nước đô thị", "mạng lưới cấp nước",
            "thất thoát nước", "nước sạch đô thị", "cấp nước an toàn",
            "đường ống cấp nước", "nước máy",
            "상수도", "정수장", "수도관", "청정수 공급", "누수 감소"],
        "exclude_if": ["wastewater", "sewage", "irrigation dam", "electric vehicle",
                       "power plant", "water resources basin management"],
        "threshold": 2,
    },
    # ── 6c. 농촌 상수도·위생 국가전략 (Decision 1978) ─────────────────
    {
        "id": "VN-WAT-RURAL",
        "name_ko": "농촌 상수도·위생 국가전략 2030/2045 (Decision 1978)",
        "keywords": [
            "rural water supply", "rural sanitation", "rural clean water",
            "commune water supply", "ethnic minority water", "highland water",
            "village water system", "rural waterworks", "rural wash",
            "decision 1978 rural water", "mard water",
            "cấp nước nông thôn", "vệ sinh nông thôn", "nước sạch nông thôn",
            "cấp nước vùng cao", "nước sinh hoạt nông thôn",
            "농촌 상수도", "농촌 위생", "오지 급수", "소수민족 급수"],
        "exclude_if": ["urban water supply plant", "wastewater treatment", "electric vehicle",
                       "power plant"],
        "threshold": 2,
    },
    # ── 7. PDP8 원자력·수소 ────────────────────────────────────────────
    {
        "id": "VN-PWR-PDP8-NUCLEAR",
        "parent": "VN-PWR-PDP8",
        "name_ko": "PDP8 원자력·수소 에너지",
        "keywords": ["nuclear power", "npp", "hydrogen",
                     "green hydrogen", "nha may dien hat nhan",
                     "hạt nhân", "điện hạt nhân", "ninh thuận hạt nhân",
                     "resolution 174", "resolution 189 nuclear",
                     "원자력 발전소", "닌투안 원전", "소형모듈원전", "그린수소"],
        "exclude_if": ["solar farm", "wind farm", "coal plant", "lng import",
                       "electric vehicle", "highway", "wastewater"],
        "threshold": 2,
    },
    # ── 8. PDP8 석탄 단계적 폐지 ────────────────────────────────────
    {
        "id": "VN-PWR-PDP8-COAL",
        "parent": "VN-PWR-PDP8",
        "name_ko": "PDP8 석탄전환 단계적 폐지",
        "keywords": ["coal phase-out", "coal retirement", "jetp",
                     "just energy transition", "coal-fired",
                     "nhiệt điện than đóng cửa", "chuyển đổi năng lượng",
                     "탈석탄", "석탄발전 폐지", "공정에너지전환"],
        "exclude_if": ["electric vehicle", "lng terminal", "solar capacity",
                       "wastewater", "highway"],
        "threshold": 2,
    },
    # ── 9. PDP8 송전망·스마트그리드 ───────────────────────────────────
    {
        "id": "VN-PWR-PDP8-GRID",
        "parent": "VN-PWR-PDP8",
        "name_ko": "PDP8 송전망·스마트그리드",
        "keywords": ["transmission line", "500kv", "power grid", "smart grid",
                     "substation", "duong day 500kv", "luoi dien", "송전선", "변전소",
                     "lưới điện thông minh", "đường dây 500kv", "trạm biến áp",
                     "스마트그리드", "500kv 송전", "변전소 건설", "송전망 확충"],
        "exclude_if": ["electric vehicle", "ev charging", "wastewater",
                       "highway", "nuclear power plant"],
        "threshold": 2,
    },
    # ── 9b. (VN-PDP8-HYDROGEN → VN-PWR-PDP8-NUCLEAR에 통합)
    # 수소·그린에너지는 원자력·수소 통합 트랙으로 이관됨
    # ── 10. 전기차·친환경 모빌리티 2030 ──────────────────────────────
    # MUST: EV·VinFast·충전 인프라 직접 언급 필수
    {
        "id": "VN-EV-2030",
        "name_ko": "베트남 전기차·친환경 모빌리티 2030",
        "keywords": ["electric vehicle", "vinfast", "ev charging", "ev sales",
                     "electric motorcycle", "electric bus fleet", "ev subsidy",
                     "charging infrastructure", "battery swap", "e-mobility",
                     "xe điện", "vinfast ev", "trạm sạc", "xe buýt điện",
                     "전기차", "vinfast", "ev 충전소", "전기버스", "친환경차"],
        "exclude_if": ["power development plan", "pdp8", "power plant capacity",
                       "solar farm mw", "wind farm gw", "lng terminal",
                       "wastewater plant", "highway km", "nuclear power",
                       "oil field", "coal plant"],
        "threshold": 2,
    },
    # ── 11. 탄소중립 2050 ─────────────────────────────────────────────
    {
        "id": "VN-CARBON-2050",
        "name_ko": "베트남 탄소중립 2050 로드맵",
        "keywords": ["carbon neutral vietnam", "net zero 2050", "carbon credit trading",
                     "ndc target", "greenhouse gas reduction plan", "carbon market",
                     "climate finance vietnam", "paris agreement vietnam",
                     "trung hòa carbon", "tín chỉ carbon", "phát thải ròng bằng 0",
                     "탄소중립", "탄소크레딧", "넷제로 2050", "온실가스 감축"],
        "exclude_if": ["electric vehicle model", "lng import deal",
                       "wastewater plant", "highway project km"],
        "threshold": 2,
    },
    # ── 12. 국가 수처리 마스터플랜 2021-2030 ──────────────────────────
    {
        "id": "VN-WW-2030",
        "name_ko": "베트남 국가 수처리 마스터플랜 2021-2030",
        "keywords": ["wastewater treatment plant", "wwtp", "sewage treatment",
                     "sewage plant construction", "sewer network", "sludge treatment",
                     "yen xa wwtp", "binh tan wwtp", "an don wwtp",
                     "xử lý nước thải", "nhà máy xử lý nước thải", "hệ thống thoát nước",
                     "하수처리장", "폐수처리장", "하수관로", "슬러지 처리"],
        "exclude_if": ["water supply", "dam", "irrigation", "electric vehicle",
                       "power plant", "highway", "industrial waste only"],
        "threshold": 2,
    },
    # ── 14. [VN-WS-NORTH-2030 → VN-WAT-URBAN으로 통합됨, 항목 삭제됨] ─────
    # ── 15. 메콩델타 지역개발 마스터플랜 2021-2030 ──────────────────────
    # Decision 287/QD-TTg (Feb 28, 2022) — 종합 지역개발 계획
    # 2026년 Decision 616/QD-TTg (Apr 4, 2026)으로 조정됨
    # 범위: Can Tho + 12개 성 (Long An, Tien Giang, Ben Tre, Dong Thap, Vinh Long,
    #        Tra Vinh, Hau Giang, An Giang, Soc Trang, Kien Giang, Bac Lieu, Ca Mau)
    # 핵심: 농업경제, 기후변화 적응, 교통인프라, 수자원, 해양경제, 도시개발
    {
        "id": "VN-MEKONG-DELTA-2030",
        "name_ko": "메콩델타 지역개발 마스터플랜 2021-2030",
        "keywords": [
            "mekong delta development", "mekong delta planning", "mekong delta master plan",
            "can tho development", "dong thap development", "an giang development",
            "kien giang development", "ca mau development", "soc trang development",
            "mekong delta agriculture", "mekong delta infrastructure", "mekong delta climate",
            "mekong delta transport", "mekong delta water", "delta economic corridor",
            "mekong delta urban", "mekong delta flood", "mekong delta saltwater intrusion",
            "mekong delta expressway", "can tho port", "mekong delta logistics",
            "decision 287", "decision 616 mekong",
            "quy hoạch vùng đồng bằng sông cửu long", "đồng bằng sông cửu long",
            "vùng đbscl", "kinh tế nông nghiệp đbscl",
            "메콩델타 개발", "메콩델타 마스터플랜", "껀터 개발", "메콩강 삼각주"],
        "exclude_if": ["wastewater treatment plant contract", "solid waste collection bid",
                       "mekong river dam china", "upper mekong"],
        "threshold": 2,
    },
    # ── 19 (NEW). 전국 고형폐기물 통합관리 국가전략 2025/2050 ──────────
    # Decision 491/QD-TTg (May 7, 2018) — 고형폐기물 통합관리 국가전략 (2025년 목표, 2050년 비전)
    # 원래 Decision 2149/QD-TTg (2009)를 대체
    # 주관: MONRE (환경부) + MOC (건설부)
    # 핵심: 도시/농촌/산업/의료폐기물 처리, WtE, 매립지 폐쇄, 재활용
    # 2030년 연계: Decision 450/QD-TTg (2022) 국가환경보호전략
    {
        "id": "VN-SWM-NATIONAL-2030",
        "name_ko": "전국 고형폐기물 통합관리 국가전략 2025/2050",
        "keywords": [
            "solid waste management vietnam", "solid waste treatment", "municipal solid waste",
            "waste-to-energy vietnam", "wte plant vietnam", "incineration plant vietnam",
            "landfill vietnam", "landfill closure", "composting vietnam",
            "urban solid waste collection", "rural solid waste", "hazardous waste vietnam",
            "industrial solid waste", "medical waste vietnam", "construction waste vietnam",
            "recycling vietnam", "plastic waste vietnam", "waste sorting vietnam",
            "solid waste collection rate", "waste burial rate", "garbage treatment",
            "epr extended producer responsibility", "waste management master plan",
            "decision 491 solid waste", "national strategy solid waste",
            "chất thải rắn", "rác thải", "xử lý rác", "đốt rác phát điện",
            "bãi chôn lấp", "tái chế rác", "thu gom rác thải",
            "고형폐기물", "쓰레기 처리", "폐기물 처리", "WtE 발전소",
            "매립지", "소각로", "재활용", "폐기물 분리수거"],
        "exclude_if": ["wastewater treatment plant", "sewage treatment",
                       "water supply pipeline", "power plant mw coal",
                       "environmental industry technology"],
        "threshold": 2,
    },
    # ── 16. 스마트시티 국가전략 2030 ──────────────────────────────────
    {
        # ── 16a. 스마트시티 국가전략 (기술·플랫폼 레이어) ──────────────────
        "id": "VN-SC-2030",
        "name_ko": "스마트시티 국가전략 2030 (기술·플랫폼)",
        "keywords": ["smart city technology", "smart city platform", "digital city",
                     "smart urban platform", "iot city infrastructure", "e-government",
                     "smart traffic system", "digital twin city",
                     "urban digital transformation", "thu duc smart",
                     "thành phố thông minh", "đô thị thông minh", "chuyển đổi số đô thị",
                     "스마트시티 플랫폼", "디지털 도시 기술"],
        "exclude_if": ["electric vehicle sales", "power plant mw",
                       "lng terminal", "wastewater treatment plant", "highway km"],
        "threshold": 2,
    },
    # ── 16b. 하노이 도시개발 마스터플랜 — 북부 신도시 (동아인·BRG·노이바이) ──
    # Decision 1668/QD-TTg (Dec 27, 2024)
    {
        "id": "HN-URBAN-NORTH",
        "name_ko": "하노이 북부 신도시 개발 (동아인·BRG스마트시티·노이바이)",
        "keywords": ["dong anh", "me linh", "soc son", "noi bai airport expansion",
                     "brg smart city", "brg sumitomo", "north hanoi smart city",
                     "co loa urban", "nhat tan noi bai", "northern city hanoi",
                     "đông anh", "mê linh", "sóc sơn", "thành phố thông minh đông anh",
                     "đô thị phía bắc hà nội", "smart city đông anh",
                     "동아인", "하노이 북부 신도시", "brg 스마트시티"],
        "exclude_if": ["mekong delta", "ho chi minh", "da nang", "wastewater"],
        "threshold": 2,
    },
    # ── 16c. 하노이 서부 과학기술도시 (호아락·하이테크파크·선따이) ──────
    {
        "id": "HN-URBAN-WEST",
        "name_ko": "하노이 서부 과학기술도시 (호아락 하이테크파크·선따이)",
        "keywords": ["hoa lac", "hoa lac hi-tech", "hoa lac high tech",
                     "western hanoi", "xuan mai", "son tay", "thach that",
                     "tien xuan smart urban", "lang hoa lac", "hanoi western city",
                     "hòa lạc", "khu công nghệ cao hòa lạc", "xuân mai", "sơn tây",
                     "호아락", "하노이 서부", "하이테크 파크"],
        "exclude_if": ["mekong delta", "ho chi minh", "da nang", "wastewater"],
        "threshold": 2,
    },
    # ── 16d. 하노이 도시 인프라 공통 (메트로·링로드·홍강·도심재개발) ─────
    {
        "id": "HN-URBAN-INFRA",
        "name_ko": "하노이 도시 인프라 (메트로·링로드·홍강·도심재개발)",
        "keywords": ["hanoi metro", "hanoi urban rail", "hanoi ring road",
                     "red river corridor hanoi", "hanoi master plan", "hanoi bridge",
                     "to lich river", "hanoi flooding solution", "hanoi urban development",
                     "hanoi decision 1668", "ring road 4 hanoi", "ring road 3.5 hanoi",
                     "metro hà nội", "đường sắt đô thị hà nội", "vành đai 4 hà nội",
                     "sông hồng hà nội", "quy hoạch hà nội", "sông tô lịch",
                     "하노이 메트로", "하노이 링로드", "홍강 개발", "하노이 마스터플랜"],
        "exclude_if": ["ho chi minh metro", "da nang", "wastewater treatment plant mw",
                       "power plant", "lng terminal"],
        "threshold": 2,
    },
    # ── 17. 북부 산업단지 개발 2030 ───────────────────────────────────
    {
        "id": "VN-IP-NORTH-2030",
        "name_ko": "북부 산업단지 개발 계획 2030",
        "keywords": ["industrial park vietnam", "vsip", "industrial zone development",
                     "economic zone fdi", "manufacturing hub vietnam",
                     "north vietnam industrial", "hai phong industrial park",
                     "quang ninh industrial", "khu công nghiệp", "khu kinh tế",
                     "산업단지 개발", "vsip", "경제특구", "북부 제조단지"],
        "exclude_if": ["wastewater", "power plant", "electric vehicle",
                       "smart city digital", "highway km"],
        "threshold": 2,
    },
    # ── 18. 석유가스 개발 계획 2030 ───────────────────────────────────
    {
        "id": "VN-OG-2030",
        "name_ko": "베트남 석유가스 개발 계획 2030",
        "keywords": ["oil field vietnam", "crude oil production", "petroleum exploration",
                     "offshore oil block", "oil refinery", "petrovietnam",
                     "dung quat refinery", "nghi son refinery", "dầu khí",
                     "khai thác dầu", "lọc dầu",
                     "유전 개발", "원유 생산", "정유 시설", "페트로베트남"],
        "exclude_if": ["electric vehicle", "lng terminal", "wastewater",
                       "solar farm", "wind farm", "highway"],
        "threshold": 2,
    },
    # ── 19. 홍강 델타 지역개발 마스터플랜 2030 ────────────────────────
    # Decision 368/QD-TTg (2022) — 홍강 델타 6개 성시 (Hanoi, Hai Phong, Quang Ninh, Hung Yen, Bac Ninh, Ninh Binh)
    # Decision 612/QD-TTg (Apr 4, 2026) — 조정판 (Hanoi + Hai Phong + Ninh Binh + Hung Yen + Bac Ninh + Quang Ninh)
    {
        "id": "VN-RED-RIVER-2030",
        "name_ko": "홍강 델타 지역개발 마스터플랜 2030",
        "keywords": ["red river delta", "hong ha delta", "red river region",
                     "hanoi development", "hung yen development", "bac ninh development",
                     "hai phong development", "quang ninh development",
                     "dong anh smart city", "brg smart city", "lh corporation vietnam",
                     "red river delta planning", "decision 612 red river",
                     "đồng bằng sông hồng", "vùng đồng bằng sông hồng",
                     "quy hoạch vùng đồng bằng sông hồng", "phát triển vùng đbsh",
                     "홍강 델타", "홍강 삼각주", "하노이 개발", "흥옌 개발",
                     "박닌 개발", "한국 lh공사 베트남"],
        "exclude_if": ["mekong delta", "wastewater treatment plant only",
                       "electric vehicle", "lng terminal"],
        "threshold": 2,
    },
]

# 섹터 분류
SECTORS = {
    "Power & Energy": ["power", "energy", "electricity", "solar", "wind", "coal", "gas", "nuclear",
                       "renewable", "hydropower", "điện", "năng lượng", "전력", "에너지", "발전"],
    "Transport & Infrastructure": ["highway", "road", "bridge", "port", "airport", "railway",
                                   "expressway", "giao thông", "đường", "cầu", "cảng",
                                   "교통", "도로", "교량", "항만", "공항", "철도"],
    "Environment & Climate": ["environment", "climate", "pollution", "carbon", "emission",
                               "waste", "green", "môi trường", "khí hậu", "ô nhiễm",
                               "환경", "기후", "탄소", "오염", "폐기물"],
    "Urban Development": ["urban", "city", "metro", "smart city", "housing", "real estate",
                          "construction", "đô thị", "thành phố", "도시", "메트로", "건설"],
    "Water Resources": ["water", "irrigation", "dam", "flood", "drought", "reservoir",
                        "nước", "thủy lợi", "đập", "lũ", "수자원", "댐", "홍수"],
    "Industry & Manufacturing": ["industrial", "factory", "manufacturing", "steel", "cement",
                                 "công nghiệp", "nhà máy", "산업", "제조", "공장"],
    "Finance & Investment": ["investment", "FDI", "funding", "loan", "bond", "finance",
                             "đầu tư", "tài chính", "투자", "금융", "펀딩"],
}



# ──────────────────────────────────────────────────────────────
# Claude 파이프라인 호환 — 섹터명 변환 테이블
# Genspark 7개 섹터 → Claude 7개 섹터 매핑
# ──────────────────────────────────────────────────────────────
SECTOR_TO_CLAUDE = {
    "Power & Energy":           "Power",
    "Transport & Infrastructure":"Smart City",    # Claude에 Transport 없음 → 가장 유사
    "Environment & Climate":    "Solid Waste",    # 주요 환경 섹터
    "Urban Development":        "Smart City",
    "Water Resources":          "Water Supply/Drainage",
    "Industry & Manufacturing": "Industrial Parks",
    "Finance & Investment":     "Industrial Parks",
    "Other":                    "Industrial Parks",
}

# 세부 키워드로 Claude 섹터 재분류 (정밀 매핑)
def _to_claude_sector(gs_sector: str, title: str, content: str) -> str:
    text = (title + " " + content).lower()
    # 정밀 매핑 우선
    if any(k in text for k in ["wastewater", "sewage", "wwtp", "nuoc thai"]):
        return "Waste Water"
    if any(k in text for k in ["water supply", "clean water", "tap water", "cap nuoc"]):
        return "Water Supply/Drainage"
    if any(k in text for k in ["solid waste", "landfill", "garbage", "recycling", "waste-to-energy", "rac thai"]):
        return "Solid Waste"
    if any(k in text for k in ["smart city", "digital", "iot", "5g", "e-government"]):
        return "Smart City"
    if any(k in text for k in ["industrial park", "economic zone", "fdi", "vsip", "khu cong nghiep"]):
        return "Industrial Parks"
    if any(k in text for k in ["oil", "gas", "lng", "petroleum", "dau khi"]):
        return "Oil & Gas"
    # 기본 매핑 적용
    return SECTOR_TO_CLAUDE.get(gs_sector, "Power")


AREA_MAP = {
    "Environment": ["environment", "pollution", "climate", "carbon", "waste", "môi trường", "환경", "기후"],
    "Energy Develop.": ["power", "energy", "electricity", "gas", "solar", "wind", "coal", "nuclear",
                        "điện", "năng lượng", "에너지", "전력"],
    "Urban Develop.": ["urban", "city", "infrastructure", "transport", "road", "bridge", "metro",
                       "đô thị", "hạ tầng", "giao thông", "도시", "인프라", "교통"],
}

PROVINCES = [
    "Hanoi", "Ho Chi Minh City", "Da Nang", "Hai Phong", "Can Tho",
    "An Giang", "Ba Ria-Vung Tau", "Bac Giang", "Bac Kan", "Bac Lieu",
    "Bac Ninh", "Ben Tre", "Binh Dinh", "Binh Duong", "Binh Phuoc",
    "Binh Thuan", "Ca Mau", "Cao Bang", "Dak Lak", "Dak Nong",
    "Dien Bien", "Dong Nai", "Dong Thap", "Gia Lai", "Ha Giang",
    "Ha Nam", "Ha Tinh", "Hai Duong", "Hau Giang", "Hoa Binh",
    "Hung Yen", "Khanh Hoa", "Kien Giang", "Kon Tum", "Lai Chau",
    "Lam Dong", "Lang Son", "Lao Cai", "Long An", "Nam Dinh",
    "Nghe An", "Ninh Binh", "Ninh Thuan", "Phu Tho", "Phu Yen",
    "Quang Binh", "Quang Nam", "Quang Ngai", "Quang Ninh", "Quang Tri",
    "Soc Trang", "Son La", "Tay Ninh", "Thai Binh", "Thai Nguyen",
    "Thanh Hoa", "Thua Thien-Hue", "Tien Giang", "Tra Vinh", "Tuyen Quang",
    "Vinh Long", "Vinh Phuc", "Yen Bai",
]

# 15개 검색 쿼리
SEARCH_QUERIES = [
    "vietnam power development plan PDP8 2026",
    "vietnam renewable energy solar wind 2026",
    "vietnam electricity coal LNG gas 2026",
    "vietnam smart grid transmission nuclear hydrogen 2026",
    "vietnam highway expressway bridge construction 2026",
    "vietnam metro urban rail high speed railway 2026",
    "vietnam port airport infrastructure investment 2026",
    "vietnam carbon neutral net zero climate environment 2026",
    "vietnam water dam flood mekong irrigation 2026",
    "vietnam urban smart city real estate development 2026",
    "vietnam electric vehicle EV VinFast energy transition 2026",
    "vietnam industrial zone environment pollution waste 2026",
    "vietnam infrastructure investment news 2026",
    "vietnam energy news vir.com.vn 2026",
    # Claude 7개 섹터 커버리지 보완
    "vietnam wastewater treatment WWTP sewage 2026",
    "vietnam water supply clean water infrastructure 2026",
    "vietnam smart city digital transformation IoT 2026",
    # 전문미디어 강화
    "site:theinvestor.vn vietnam infrastructure 2026",
    "site:vietnamenergy.vn power energy 2026",
    "vietnam oil gas petroleum exploration 2026",
    "vietnam hanoi urban development construction 2026",
]


# ──────────────────────────────────────────────────────────────
# Agent 1: 뉴스 수집 (gsk search + crawl)
# ──────────────────────────────────────────────────────────────

def _is_relevant(title: str, snippet: str) -> bool:
    """베트남 인프라 관련 여부 필터"""
    infra_kws = [
        "vietnam", "viet nam", "việt nam", "hanoi", "ho chi minh",
        "energy", "power", "electricity", "solar", "wind", "coal", "gas", "LNG",
        "transport", "highway", "road", "bridge", "port", "metro", "railway",
        "infrastructure", "environment", "carbon", "climate", "renewable",
        "investment", "FDI", "urban", "construction", "water", "dam",
        "전력", "에너지", "교통", "인프라", "환경", "투자",
    ]
    text = (title + " " + snippet).lower()
    return any(kw.lower() in text for kw in infra_kws)


def _parse_article_date(date_str: str) -> datetime | None:
    """기사 날짜 문자열 → datetime 파싱 (다양한 형식 지원)"""
    if not date_str:
        return None
    from dateutil import parser as _dp
    try:
        return _dp.parse(date_str, fuzzy=True)
    except Exception:
        return None


def run_agent1_collection(collection_days: int = 7) -> list[dict]:
    """Agent 1: 뉴스 수집.
    collection_days: 수집 범위 (기본 7일 = 최근 1주일).
    수집 날짜가 범위 밖인 기사는 제외합니다.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=collection_days)
    cutoff_str = cutoff.strftime("%Y-%m-%d")
    print(f"  [Agent 1] gsk search 기반 뉴스 수집 ({len(SEARCH_QUERIES)}개 쿼리)")
    print(f"  [Agent 1] 수집 범위: {cutoff_str} ~ 오늘 ({collection_days}일)")
    all_articles = []
    seen_urls = set()
    skipped_old = 0
    exempt_kept = 0  # 정부·연구기관 면제로 포함된 건수

    for i, query in enumerate(SEARCH_QUERIES, 1):
        print(f"    [{i:02d}/{len(SEARCH_QUERIES)}] {query[:50]}...", end=" ", flush=True)
        results = gsk_search(query)
        new_count = 0
        if not results:
            print("+0 (skip)")
            time.sleep(1.0)
            continue

        for r in results:
            url = r.get("link", "")
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            raw_date = r.get("date", "")

            if not url or not title:
                continue

            # 날짜 필터링: 수집 범위 밖 기사 제외
            # 단, 정부기관/국제기구/연구기관 도메인은 면제 (보도자료·법령·보고서)
            EXEMPT_DOMAINS = {
                # 베트남 정부
                "chinhphu.vn", "moit.gov.vn", "mpi.gov.vn", "monre.gov.vn",
                "most.gov.vn", "mof.gov.vn", "mod.gov.vn", "mard.gov.vn",
                "molisa.gov.vn", "moet.gov.vn", "mic.gov.vn",
                "evn.com.vn", "erav.vn", "erea.gov.vn",
                "baochinhphu.vn", "dangcongsan.vn",
                "hanoi.gov.vn", "hochiminhcity.gov.vn",
                # 국제기구·연구기관
                "worldbank.org", "adb.org", "iea.org", "irena.org",
                "undp.org", "unido.org", "oecd.org", "imf.org",
                "sei.org", "wri.org", "iisd.org",
                # 전문 리서치
                "fitch", "moody", "sp global", "bloomberg",
            }
            url_lower = url.lower()
            is_exempt = any(d in url_lower for d in EXEMPT_DOMAINS)

            parsed = _parse_article_date(raw_date)
            if parsed:
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                if parsed < cutoff:
                    if is_exempt:
                        exempt_kept += 1  # 면제: 정부·연구기관 문서
                    else:
                        skipped_old += 1
                        continue
                date = parsed.strftime("%Y-%m-%d")
            else:
                # 날짜 파싱 실패 → 오늘 날짜 사용 (수집일 기준)
                date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            uid = hashlib.md5(url.encode()).hexdigest()
            if uid in seen_urls:
                continue
            if not _is_relevant(title, snippet):
                continue

            seen_urls.add(uid)
            all_articles.append({
                "id": uid,
                "title": title,
                "url": url,
                "published_date": date,
                "content": snippet,
                "source": r.get("source") or urlparse(url).netloc.replace("www.", ""),
                "lang": "en",
                "_is_new": True,  # 이번 주 신규 수집 마킹
            })
            new_count += 1

        print(f"+{new_count}")
        time.sleep(0.5)

    print(f"  [Agent 1] 완료: {len(all_articles)}개 수집, {skipped_old}개 날짜 외 제외, {exempt_kept}개 정부·연구기관 면제 포함")

    print(f"  [Agent 1] 완료: {len(all_articles)}개 기사 수집")
    return all_articles


# ──────────────────────────────────────────────────────────────
# Agent 2: 스마트 분류 (키워드 기반)
# ──────────────────────────────────────────────────────────────

def _classify_sector(text: str) -> tuple[str, float]:
    text_lower = text.lower()
    scores = {s: sum(1 for kw in kws if kw.lower() in text_lower)
              for s, kws in SECTORS.items()}
    best = max(scores, key=scores.get)
    total = sum(scores.values()) or 1
    confidence = round(scores[best] / total * 100, 1)
    return (best if scores[best] > 0 else "Other", confidence)


def _classify_area(text: str) -> str:
    text_lower = text.lower()
    scores = {area: sum(1 for kw in kws if kw.lower() in text_lower)
              for area, kws in AREA_MAP.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "Urban Develop."


def _classify_province(text: str) -> str:
    """63개 성·시 키워드 매칭 (2025 정부조직개편 반영)"""
    text_lower = text.lower()
    # config/province_keywords.json 로드 (캐시)
    if not hasattr(_classify_province, "_kw_cache"):
        import json as _json
        from pathlib import Path as _Path
        _kw_path = _Path(__file__).parent.parent / "config" / "province_keywords.json"
        try:
            _data = _json.loads(_kw_path.read_text(encoding="utf-8"))
            _classify_province._kw_cache = {k: v for k, v in _data.items() if not k.startswith("_")}
        except Exception:
            _classify_province._kw_cache = {}
    for province, variants in _classify_province._kw_cache.items():
        if any(v in text_lower for v in variants):
            return province
    # fallback: PROVINCES 리스트 단순 매칭
    for province in PROVINCES:
        if province.lower() in text_lower:
            return province
    return "Vietnam"


def run_agent2_classification(articles: list[dict]) -> list[dict]:
    """Agent 2: 키워드 기반 섹터/Area/Province 분류"""
    print(f"  [Agent 2] 분류 시작 ({len(articles)}개)...")
    for art in articles:
        text = art["title"] + " " + art.get("content", "")
        gs_sector, art["confidence"] = _classify_sector(text)
        art["sector_genspark"] = gs_sector   # Genspark 원본 섹터 보존
        art["sector"] = _to_claude_sector(gs_sector, art["title"], art.get("content",""))  # Claude 섹터
        art["area"] = _classify_area(text)
        art["province"] = _classify_province(text)
    print(f"  [Agent 2] 완료")
    return articles


# ──────────────────────────────────────────────────────────────
# Agent 3: Knowledge Base 매칭 (키워드 스코어링)
# ──────────────────────────────────────────────────────────────

def run_agent3_kb_matching(articles: list[dict]) -> list[dict]:
    """Agent 3: 마스터플랜 키워드 매칭 (v2.4 — 계층 구조 + parent 자동 포함)"""
    from scripts.relevance_filter import apply_collection_filter

    print(f"  [Agent 3] KB 매칭 시작 ({len(articles)}개)...")

    # 피드백 blocklist 기반 1차 필터 (수집 단계 오염 제거)
    articles = apply_collection_filter(articles)

    # parent 맵 구축 (하위→상위 자동 포함용)
    parent_map = {p["id"]: p.get("parent") for p in MASTERPLANS if p.get("parent")}

    for art in articles:
        text = (art["title"] + " " + art.get("content", "")[:800]).lower()
        matched = []
        best_score = 0
        policy_context = None

        for plan in MASTERPLANS:
            # exclude_if: 충돌 키워드 있으면 이 플랜 스킵
            excluded = any(ex.lower() in text for ex in plan.get("exclude_if", []))
            if excluded:
                continue

            score = sum(1 for kw in plan["keywords"] if kw.lower() in text)
            if score >= plan["threshold"]:
                matched.append(plan["id"])
                if score > best_score:
                    best_score = score
                    policy_context = {
                        "plan_id": plan["id"],
                        "plan_name": plan["name_ko"],
                        "score": score,
                    }

        # Sector → Plan fallback (키워드 매핑 0건이지만 sector가 분류된 경우)
        if not matched and art.get("sector"):
            sector_lower = art["sector"].lower()
            SECTOR_FALLBACK = {
                "power": "VN-PWR-PDP8",
                "renewable": "VN-PWR-PDP8-RENEWABLE",
                "solar": "VN-PWR-PDP8-RENEWABLE",
                "wind": "VN-PWR-PDP8-RENEWABLE",
                "lng": "VN-PWR-PDP8-LNG",
                "gas": "VN-PWR-PDP8-LNG",
                "nuclear": "VN-PWR-PDP8-NUCLEAR",
                "coal": "VN-PWR-PDP8-COAL",
                "grid": "VN-PWR-PDP8-GRID",
                "transport": "VN-TRAN-2055",
                "highway": "VN-TRAN-2055",
                "metro": "VN-URB-METRO-2030",
                "urban rail": "VN-URB-METRO-2030",
                "water": "VN-WAT-RESOURCES",
                "water supply": "VN-WAT-URBAN",
                "wastewater": "VN-WW-2030",
                "solid waste": "VN-SWM-NATIONAL-2030",
                "waste management": "VN-SWM-NATIONAL-2030",
                "environment": "VN-ENV-IND-1894",
                "carbon": "VN-CARBON-2050",
                "climate": "VN-CARBON-2050",
                "net zero": "VN-CARBON-2050",
                "ev": "VN-EV-2030",
                "electric vehicle": "VN-EV-2030",
                "smart city": "VN-SC-2030",
                "oil": "VN-OG-2030",
                "petroleum": "VN-OG-2030",
                "mekong": "VN-MEKONG-DELTA-2030",
                "industrial zone": "VN-IP-NORTH-2030",
                "industrial park": "VN-IP-NORTH-2030",
            }
            for keyword, fallback_plan in SECTOR_FALLBACK.items():
                if keyword in sector_lower:
                    matched.append(fallback_plan)
                    policy_context = {
                        "plan_id": fallback_plan,
                        "plan_name": f"[sector-fallback] {art['sector']}",
                        "score": 0,
                    }
                    break

        # 하위 플랜 매핑 시 상위(parent)도 자동 포함
        for pid in list(matched):
            parent = parent_map.get(pid)
            if parent and parent not in matched:
                matched.append(parent)

        art["matched_plans"] = matched
        art["policy_context"] = policy_context

    matched_count = sum(1 for a in articles if a["matched_plans"])
    print(f"  [Agent 3] 완료: {matched_count}/{len(articles)}개 매칭")
    return articles


# ──────────────────────────────────────────────────────────────
# Agent 4: 다국어 요약 (gsk summarize)
# ──────────────────────────────────────────────────────────────

def _parse_3lang(raw: str, title: str) -> tuple:
    """gsk summarize 응답에서 KO/EN/VI 추출"""
    import re as _re
    answer_m = _re.search(r'answer:\s*(.*?)(?:\n\nSource:|\Z)', raw, _re.DOTALL)
    text = answer_m.group(1).strip() if answer_m else raw
    ko_m = _re.search(r'KO:\s*(.+?)(?=\nEN:|\Z)', text, _re.DOTALL)
    en_m = _re.search(r'EN:\s*(.+?)(?=\nVI:|\Z)', text, _re.DOTALL)
    vi_m = _re.search(r'VI:\s*(.+?)(?:\n|\Z)', text, _re.DOTALL)
    ko = ko_m.group(1).strip() if ko_m else title
    en = en_m.group(1).strip() if en_m else title
    vi = vi_m.group(1).strip() if vi_m else title
    return ko, en, vi
def _summarize_3lang_gsk(article: dict) -> dict:
    """gsk summarize 1회 호출로 KO/EN/VI 3개국어 요약 동시 생성.
    기존 3회 → 1회로 줄여 품질 유지 + 호출 수 67% 감소.
    """
    import shlex as _shlex
    title   = article.get("title", "")
    url     = article.get("url", "")
    sector  = article.get("sector", "")
    plans   = ", ".join(article.get("matched_plans", [])) or "N/A"
    source  = url if url.startswith("http") else title

    question = (
        f"Summarize this Vietnam infrastructure news in THREE languages.\n"
        f"Sector: {sector}, Related plans: {plans}\n\n"
        f"Format EXACTLY as:\n"
        f"KO: [2-3 sentences in Korean]\n"
        f"EN: [2-3 sentences in English]\n"
        f"VI: [2-3 câu tiếng Việt]"
    )
    inner = f"gsk summarize {_shlex.quote(source)} --question {_shlex.quote(question)}"
    cmd   = f"script -q -c {_shlex.quote(inner)} /dev/null"

    try:
        r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=40)
        raw = r.stdout.decode("utf-8", errors="ignore")
        raw = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', raw)
        # JSON 안의 result 텍스트 추출
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        text = ""
        if m:
            d = json.loads(m.group())
            text = d.get("data", {}).get("result", "") or str(d.get("data", ""))
        ko, en, vi = _parse_3lang(text or raw, title)
    except Exception:
        ko = en = vi = title

    article["summary_ko"] = ko
    article["summary_en"] = en
    article["summary_vi"] = vi
    return article


def run_agent4_summarization(articles: list[dict]) -> list[dict]:
    """Agent 4: gsk summarize 1회/기사 → KO/EN/VI 동시 생성
    - 기존 3회 호출 대비 67% 감소, 품질 동일
    - tmux 기반 _gsk()와 동일한 TTY 환경 사용
    """
    print(f"  [Agent 4] 3개국어 요약 시작 ({len(articles)}개, gsk 1회/기사)...")
    for i, art in enumerate(articles, 1):
        if i % 10 == 0 or i == 1:
            print(f"    진행: {i}/{len(articles)}")
        articles[i - 1] = _summarize_3lang_gsk(art)
        time.sleep(1.5)   # gsk rate limit 방지
    print(f"  [Agent 4] 완료 (gsk 호출: {len(articles)}회)")
    return articles


# ──────────────────────────────────────────────────────────────
# Agent 5: QC (14개 항목)
# ──────────────────────────────────────────────────────────────

def run_agent5_qc(articles: list[dict]) -> tuple[list[dict], dict]:
    """Agent 5: 14개 항목 품질 검사"""
    print(f"  [Agent 5] QC 시작 ({len(articles)}개)...")
    from collections import Counter

    # Genspark 원본 섹터 + Claude 변환 섹터 모두 유효로 처리
    valid_sectors = set(SECTORS.keys()) | {"Other"} | set(SECTOR_TO_CLAUDE.values())
    valid_areas = {"Environment", "Energy Develop.", "Urban Develop."}
    seen_titles = {}
    issues_log = []

    for art in articles:
        issues = []

        if not art.get("title"):
            issues.append("QC01: Title missing")
        if not art.get("url", "").startswith("http"):
            issues.append("QC02: Invalid URL")
        # sector_genspark(원본) 또는 sector(Claude변환) 중 하나라도 유효하면 통과
        gs_sec = art.get("sector_genspark", art.get("sector",""))
        cl_sec = art.get("sector", "")
        if gs_sec not in valid_sectors and cl_sec not in valid_sectors:
            issues.append("QC03: Invalid sector")
        if art.get("area") not in valid_areas:
            issues.append("QC04: Invalid area")
        if not art.get("province"):
            issues.append("QC05: Province missing")
        if len(art.get("summary_ko", "")) < 20:
            issues.append("QC06: Summary too short")

        title_key = art.get("title", "").lower()[:50]
        if title_key in seen_titles:
            issues.append("QC11: Duplicate title")
        else:
            seen_titles[title_key] = True

        art["qc_issues"] = issues
        art["qc_status"] = "PASS" if not issues else "FAIL"
        if issues:
            issues_log.append({"title": art.get("title", "")[:50], "issues": issues})

    total = len(articles)
    passed = sum(1 for a in articles if a["qc_status"] == "PASS")
    qc_rate = passed / total * 100 if total else 0

    pro_sources_kws = ["vir.com.vn", "nikkei", "bloomberg", "reuters", "spglobal",
                       "woodmac", "adb.org", "worldbank", "freshfields"]
    pro_count = sum(1 for a in articles
                    if any(kw in a.get("url", "").lower() for kw in pro_sources_kws))
    pro_ratio = pro_count / total * 100 if total else 0

    sector_counts = Counter(a.get("sector") for a in articles)
    max_sector_ratio = max(sector_counts.values()) / total * 100 if total else 0

    pdp8_count = sum(1 for a in articles if "VN-PWR-PDP8" in a.get("matched_plans", []))
    d1894_count = sum(1 for a in articles if "VN-ENV-IND-1894" in a.get("matched_plans", []))
    unclassified = sum(1 for a in articles if a.get("province") in ["Vietnam", "National / Unspecified", ""])
    unclassified_ratio = unclassified / total * 100 if total else 0
    integrity_ok = all(a.get("id") and a.get("title") and a.get("url") for a in articles)

    qc_report = {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "qc_rate": round(qc_rate, 1),
        "qc07_pro_media_ratio": round(pro_ratio, 1),
        "qc07_pass": pro_ratio >= 30,
        "qc08_sector_balance": round(max_sector_ratio, 1),
        "qc08_pass": max_sector_ratio < 60,
        "qc09_pdp8_count": pdp8_count,
        "qc09_pass": pdp8_count >= 5,
        "qc10_d1894_count": d1894_count,
        "qc10_pass": d1894_count >= 3,
        "qc12_unclassified_province_ratio": round(unclassified_ratio, 1),
        "qc12_pass": unclassified_ratio <= 25,
        "qc13_pass_rate_ok": qc_rate >= 95,
        "qc14_integrity_ok": integrity_ok,
        "sector_distribution": dict(sector_counts),
        "issues_log": issues_log[:20],
        "recommendations": [],
    }

    if not qc_report["qc07_pass"]:
        qc_report["recommendations"].append(f"전문 미디어 소스 비율 증가 필요 (현재 {pro_ratio:.0f}%)")
    if not qc_report["qc08_pass"]:
        qc_report["recommendations"].append("섹터 다양성 확보 필요")
    if not qc_report["qc09_pass"]:
        qc_report["recommendations"].append(f"PDP8 관련 기사 추가 수집 필요 (현재 {pdp8_count}건)")
    if not qc_report["qc10_pass"]:
        qc_report["recommendations"].append(f"Decision 1894 관련 기사 추가 필요 (현재 {d1894_count}건)")
    if not qc_report["qc12_pass"]:
        qc_report["recommendations"].append(f"Province 미분류 비율 감소 필요 (현재 {unclassified_ratio:.0f}%)")

    print(f"  [Agent 5] QC 완료: 통과 {passed}/{total} ({qc_rate:.1f}%)")
    return articles, qc_report


# ──────────────────────────────────────────────────────────────
# 전체 파이프라인 실행
# ──────────────────────────────────────────────────────────────

def run_pipeline(output_dir: str = None, collection_days: int = 7) -> tuple[list[dict], dict]:
    """
    Agent 1~5 순서대로 실행.
    gsk CLI 기반 — Anthropic API 불필요.

    Args:
        output_dir: 출력 디렉토리
        collection_days: 뉴스 수집 범위 (기본 7일 = 최근 1주일)
    """
    if output_dir is None:
        output_dir = os.getenv("PIPELINE_OUTPUT_DIR", ".")
    os.makedirs(output_dir, exist_ok=True)

    start = datetime.now()
    print(f"\n{'='*60}")
    print(f"Agent Pipeline 시작 (gsk 기반): {start.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"수집 범위: 최근 {collection_days}일")
    print(f"{'='*60}")

    articles = run_agent1_collection(collection_days=collection_days)

    if not articles:
        print("  ⚠ 수집된 기사 없음 — 파이프라인 중단")
        return [], {}

    articles = run_agent2_classification(articles)
    articles = run_agent3_kb_matching(articles)
    articles = run_agent4_summarization(articles)
    articles, qc_report = run_agent5_qc(articles)

    # ── 저장 — Claude 파이프라인 호환 파일명 사용 ──
    output_path = os.path.join(output_dir, "genspark_output.json")  # Claude SA-6이 읽는 파일명
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    print(f"\n  ✓ genspark_output.json 저장 ({len(articles)}개)")

    qc_path = os.path.join(output_dir, "genspark_qc_report.json")
    with open(qc_path, "w", encoding="utf-8") as f:
        json.dump(qc_report, f, ensure_ascii=False, indent=2)
    print(f"  ✓ genspark_qc_report.json 저장")

    # ── History DB 증분 업데이트 ──────────────────────────────────
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from history_db_builder import update_weekly
        update_weekly(articles)
        print("  ✓ History DB 증분 업데이트 완료")
    except Exception as e:
        print(f"  ⚠ History DB 업데이트 실패: {e}")

    # ── MI 보고서 생성 (History 포함) ────────────────────────────
    try:
        from mi_report_generator import main as mi_main
        mi_main()
        print("  ✓ MI 보고서 생성 완료 (역사 포함)")
    except Exception as e:
        print(f"  ⚠ MI 보고서 생성 실패: {e}")

    # ── GitHub 업로드 — github_uploader.main()으로 일원화 ──────────
    # (docs/shared/genspark_output.json + docs/shared/genspark_qc_report.json)
    try:
        import github_uploader
        github_uploader.main()
        print(f"  ✓ GitHub 업로드 완료 (docs/shared/)")
    except Exception as e:
        print(f"  ⚠ github_uploader.main() 실패: {e}")

    elapsed = (datetime.now() - start).seconds
    print(f"  ⏱ 총 소요: {elapsed // 60}분 {elapsed % 60}초")
    return articles, qc_report


if __name__ == "__main__":
    articles, qc = run_pipeline()  # PIPELINE_OUTPUT_DIR 환경변수 사용
    print(f"\n결과: {len(articles)}개 기사, QC 통과율 {qc.get('qc_rate', 0)}%")
    print(f"PDP8 매칭: {qc.get('qc09_pdp8_count', 0)}건, D1894: {qc.get('qc10_d1894_count', 0)}건")
    print(f"섹터 분포: {qc.get('sector_distribution', {})}")
