"""
update_knowledge_index_layer1.py — v1.0 (2026-05-24)
=====================================================
용도: knowledge_index.json의 21개 플랜에
      description_ko / kpi_targets / key_projects 필드를
      일괄 추가(upsert)하는 1회성 스크립트

실행 방법 (로컬 또는 GitHub Actions):
  python3 scripts/update_knowledge_index_layer1.py

처리 흐름:
  1. docs/shared/knowledge_index.json 읽기
  2. 각 플랜에 Layer1 3개 필드 추가/덮어쓰기
  3. 덮어쓰기 완료 후 저장
  4. 변경 요약 출력

주의:
  - 기존 keywords_en/vi, sectors 등 다른 필드는 절대 건드리지 않음
  - description_ko가 이미 있으면 덮어씀 (최신 데이터 우선)
"""

import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('update_layer1')

BASE_DIR = Path(__file__).parent.parent
KI_PATH  = BASE_DIR / 'docs' / 'shared' / 'knowledge_index.json'

# ── Layer1 데이터 (21개 플랜 전체) ────────────────────────────────────────
LAYER1_DATA = {
    "VN-PWR-PDP8": {
        "description_ko": "베트남 제8차 전력개발계획(PDP8)은 2023년 Decision 500/QĐ-TTg로 승인된 국가 에너지 마스터플랜입니다. 2024년 Decision 768로 개정되어 2030년까지 재생에너지 비율 47%, 총 발전설비 150GW 달성을 목표로 합니다. 해상풍력 6GW→17GW 상향, LNG 발전 24GW, 원자력 재도입(4,000MW) 등이 핵심 내용이며, 총 투자규모는 약 $1,350억(USD)입니다.",
        "kpi_targets": [
            {"indicator": "재생에너지 비율", "target": "47%", "current": "~26% (2023)", "baseline": "26%"},
            {"indicator": "총 발전설비 용량", "target": "150GW", "current": "~78GW", "baseline": "78GW"},
            {"indicator": "해상풍력 설비", "target": "17GW", "current": "0.1GW", "baseline": "0.1GW"},
        ],
        "key_projects": [
            {"name": "북부 광역 해상풍력 1단계", "location": "하이퐁·광닌", "capacity": "2,500MW", "note": "입찰 준비 중"},
            {"name": "중부 태양광 발전단지", "location": "닌투언·빈투언", "capacity": "1,500MW", "note": "공사 중"},
        ],
    },
    "VN-PWR-PDP8-RENEWABLE": {
        "description_ko": "PDP8의 재생에너지 세부 이행계획으로 2030년까지 태양광 12GW·풍력 18GW 구축이 목표입니다. BESS 의무화, RE100 DPPA 제도 도입, 수상태양광 확대가 핵심입니다. EVN과 외국인 50:50 합작 구조가 표준 투자 모델입니다.",
        "kpi_targets": [
            {"indicator": "태양광 설비", "target": "12GW", "current": "~7GW", "baseline": "7GW"},
            {"indicator": "풍력 설비(육상+해상)", "target": "18GW", "current": "~4.5GW", "baseline": "4.5GW"},
        ],
        "key_projects": [
            {"name": "손라 800MW 수상태양광", "location": "손라성", "capacity": "800MW", "note": "착공 2026"},
            {"name": "람동 수상태양광", "location": "람동성", "capacity": "270MW", "note": "투자 제안"},
        ],
    },
    "VN-PWR-PDP8-LNG": {
        "description_ko": "2030년까지 LNG 복합화력발전 24GW 구축 계획입니다. 인수보장(Take-or-Pay) 계약 의무화, LNG 수입터미널 3기 동시 추진이 핵심입니다. 한국 기업의 EPC 및 운영 참여 기회가 높은 분야입니다.",
        "kpi_targets": [
            {"indicator": "LNG 발전설비", "target": "24GW", "current": "0GW", "baseline": "0GW"},
            {"indicator": "LNG 수입 용량", "target": "6 MTPA", "current": "0", "baseline": "0"},
        ],
        "key_projects": [
            {"name": "Thi Vai LNG 터미널 2단계", "location": "바리아붕따우", "capacity": "$15억", "note": "EPC 계약 임박"},
            {"name": "Son My LNG 수입터미널", "location": "빈투언", "capacity": "$18억", "note": "입찰 진행"},
        ],
    },
    "VN-PWR-PDP8-GRID": {
        "description_ko": "PDP8 이행을 위한 송배전망 확충계획으로 총 투자규모 약 $200억입니다. 500kV DC 해저케이블, 765kV 신규 송전선, 스마트그리드 전환이 3대 과제입니다.",
        "kpi_targets": [
            {"indicator": "신규 송전선 구축", "target": "22,000km", "current": "진행 중", "baseline": ""},
            {"indicator": "765kV 신규 노선", "target": "3개", "current": "1개", "baseline": "1개"},
        ],
        "key_projects": [
            {"name": "하노이-하이퐁 765kV 송전선", "location": "하노이~하이퐁", "capacity": "$9억", "note": "계획 수립"},
            {"name": "라이차우 송전 인프라 확충", "location": "라이차우성", "capacity": "미정", "note": "계획 단계"},
        ],
    },
    "VN-PWR-PDP8-NUCLEAR": {
        "description_ko": "2025년 국회 결의로 원자력 발전 재개가 확정됐습니다. 2035년까지 4,000MW(2기) 구축 목표로, 닌투언성 2개 부지가 후보지입니다. 한국(APR-1400), 러시아(VVER), 프랑스(EPR)와 기술협력 논의가 진행 중이며 한-베 원전 협력협정이 2026년 체결됐습니다.",
        "kpi_targets": [
            {"indicator": "원전 설비 용량", "target": "4,000MW (2기)", "current": "0MW", "baseline": ""},
            {"indicator": "1기 COD 목표", "target": "2035년", "current": "타당성조사 중", "baseline": ""},
        ],
        "key_projects": [
            {"name": "닌투언 1 원전", "location": "닌투언성", "capacity": "2,000MW", "note": "부지 확보 완료"},
            {"name": "닌투언 2 원전", "location": "닌투언성", "capacity": "2,000MW", "note": "부지 선정"},
        ],
    },
    "VN-PWR-PDP8-HYDROGEN": {
        "description_ko": "2030년 그린수소 파일럿, 2050년 수소 수출국을 목표로 하는 국가 수소에너지 전략입니다. 재생에너지 잉여전력을 활용한 전해조 설치가 1단계 핵심이며 실질 투자는 2027년 이후 예상됩니다.",
        "kpi_targets": [
            {"indicator": "그린수소 생산 용량", "target": "100,000톤/년 (2030)", "current": "0", "baseline": ""},
        ],
        "key_projects": [
            {"name": "닌투언 그린수소 파일럿", "location": "닌투언성", "capacity": "소규모 실증", "note": "2027년 예정"},
        ],
    },
    "VN-OG-2030": {
        "description_ko": "베트남 석유가스산업 중장기 개발계획으로 2030년까지 원유·가스 생산 유지 및 LNG 인프라 확충이 목표입니다. PVN(페트로베트남) 주관으로 Nghi Son·Binh Son 정유단지 고도화, Ca Mau LNG 터미널 신설이 핵심입니다.",
        "kpi_targets": [
            {"indicator": "원유 생산량", "target": "8.0 MT/년", "current": "9.5 MT/년", "baseline": "9.5 MT/yr"},
            {"indicator": "LNG 도입량", "target": "6 MTPA", "current": "0", "baseline": ""},
        ],
        "key_projects": [
            {"name": "Nghi Son 정유단지 2단계", "location": "탄화성", "capacity": "$32억", "note": "진행 중"},
            {"name": "PVN-Vitol Asia 에너지 MoU", "location": "전국", "capacity": "협력", "note": "2026 체결"},
        ],
    },
    "VN-WW-2030": {
        "description_ko": "2030년까지 도시 폐수처리율 70% 달성을 목표로 하는 국가 폐수처리 마스터플랜입니다. 총 필요 투자액 약 $48억, BOT·PPP 방식 민간투자가 핵심 재원입니다. JICA($690M), ADB, WB 등 ODA가 주요 재원이며 한국 기업의 WWTP EPC 참여 기회가 높습니다.",
        "kpi_targets": [
            {"indicator": "도시 폐수처리율", "target": "70% (2030)", "current": "~18%", "baseline": "18%"},
            {"indicator": "신규 WWTP 용량", "target": "5,500,000 m³/일", "current": "~1,200,000 m³/일", "baseline": ""},
        ],
        "key_projects": [
            {"name": "하노이 옌짜(Yen Xa) WWTP", "location": "하노이", "capacity": "270,000 m³/일", "note": "2025.8 준공"},
            {"name": "호치민 빈흥화 WWTP 확장", "location": "호치민", "capacity": "1,100,000 m³/일", "note": "공사 중"},
        ],
    },
    "VN-WAT-RESOURCES": {
        "description_ko": "홍강·메콩강 등 주요 유역의 수자원 통합관리 국가계획입니다. 기후변화 대응 가뭄·홍수·염수침투 차단, 농업·도시 용수 공급 안정화가 3대 과제입니다. 다낭 염수차단댐 지연이 2026년 현안입니다.",
        "kpi_targets": [
            {"indicator": "도시 안정 급수율", "target": "98%", "current": "~89%", "baseline": "89%"},
            {"indicator": "농촌 안전 음용수", "target": "95%", "current": "~72%", "baseline": "72%"},
        ],
        "key_projects": [
            {"name": "다낭 염수차단댐", "location": "다낭", "capacity": "미정", "note": "지연 중 (2026 현안)"},
            {"name": "홍강 분홍수로 체계 개편", "location": "북부 전역", "capacity": "치수", "note": "2026 전환"},
        ],
    },
    "VN-WAT-URBAN": {
        "description_ko": "2030년까지 도시 상수도 보급률 95%, 하수처리율 70% 달성을 목표로 하는 국가 상하수도 기본계획입니다. 총 투자규모 약 $58억, PPP·BOT 방식 민간투자 유치가 핵심입니다. 스마트 수도계량·NRW 감축이 기술 과제입니다.",
        "kpi_targets": [
            {"indicator": "도시 상수도 보급률", "target": "95%", "current": "~89%", "baseline": "89%"},
            {"indicator": "하수처리율 (도시)", "target": "70%", "current": "~15%", "baseline": "15%"},
        ],
        "key_projects": [
            {"name": "하노이 북부 상수도 확장 2단계", "location": "하노이", "capacity": "$3.2억", "note": "입찰 진행"},
            {"name": "호치민 빈동 광역상수도", "location": "빈동성", "capacity": "$1.8억", "note": "공사 중"},
        ],
    },
    "VN-SWM-NATIONAL-2030": {
        "description_ko": "2030년까지 고형폐기물 재활용률 85%, 매립 비율 30% 이하 달성을 목표로 하는 국가계획입니다. WtE(폐기물에너지화) 30개 도시 확산, 하노이 Nam Son·호치민 Da Phuoc 전환이 최우선 과제입니다.",
        "kpi_targets": [
            {"indicator": "고형폐기물 재활용률", "target": "85%", "current": "~52%", "baseline": "52%"},
            {"indicator": "매립 비율", "target": "30% 이하", "current": "~70%", "baseline": "70%"},
        ],
        "key_projects": [
            {"name": "하이퐁 폐기물처리 현대화", "location": "하이퐁", "capacity": "도시 전체", "note": "2026 가속"},
            {"name": "하노이 Nam Son → WtE 전환", "location": "하노이", "capacity": "$1.8억", "note": "계획 수립"},
        ],
    },
    "VN-ENV-IND-1894": {
        "description_ko": "2030년까지 환경기술·서비스 산업을 GDP의 3% 규모로 육성하는 국가 프로그램입니다. 환경설비 국산화, 환경기술 수출, 그린산업단지 조성이 3대 목표입니다. 폐수 불법방류 단속 강화가 2026년 주요 이슈입니다.",
        "kpi_targets": [
            {"indicator": "환경산업 GDP 비중", "target": "3%", "current": "~1.2%", "baseline": "1.2%"},
            {"indicator": "인증 환경기업 수", "target": "5,000개", "current": "~800개", "baseline": "800개"},
        ],
        "key_projects": [
            {"name": "산업폐수 무단방류 단속 강화", "location": "전국", "capacity": "규제", "note": "2026 강화"},
        ],
    },
    "VN-IP-NORTH-2030": {
        "description_ko": "박닌·흥옌·하이퐁·광닌 중심 북부 첨단산업단지 개발계획입니다. 반도체·전자·자동차 부품 고부가가치 산업 유치가 핵심이며 Eco-IP(친환경 산업단지) 조성이 방향입니다. 인텔·삼성·폭스콘 추가투자와 함께 VKBIA(베트남-한국 비즈니스투자협회) 활동이 활발합니다.",
        "kpi_targets": [
            {"indicator": "FDI 유치 목표", "target": "$50억/년", "current": "~$28억/년", "baseline": "$28억/yr"},
            {"indicator": "산업단지 입주율", "target": "80%", "current": "~65%", "baseline": "65%"},
        ],
        "key_projects": [
            {"name": "KNIC 나트랑 산업단지 인프라", "location": "나트랑", "capacity": "KN Holdings", "note": "착공 2026.5"},
            {"name": "Lotte 동나이 콜드체인센터", "location": "동나이", "capacity": "물류", "note": "개장 2026.5"},
            {"name": "600억 전자부품 공장 착공", "location": "미정", "capacity": "$6억", "note": "착공 2026.5"},
        ],
    },
    "VN-TRAN-2055": {
        "description_ko": "2030년까지 고속도로 5,000km, 롱탄공항 개항, 메트로 확장을 포함한 국가 교통 종합계획입니다. 남북 고속철도($678억)가 장기 핵심 과제이며 TOD 역세권 개발 PPP 참여가 외국기업 기회입니다.",
        "kpi_targets": [
            {"indicator": "고속도로 총 연장", "target": "5,000km", "current": "~2,100km", "baseline": "2,100km"},
            {"indicator": "롱탄 공항 1단계", "target": "2026년 개항", "current": "공사 진행", "baseline": ""},
            {"indicator": "하노이 메트로 연장", "target": "1,153km (2050)", "current": "~35km", "baseline": "35km"},
        ],
        "key_projects": [
            {"name": "롱탄 국제공항 ($12.8B)", "location": "동나이성", "capacity": "1억명/년(궁극)", "note": "2026 개항 예정"},
            {"name": "하노이 링로드 6.30 개통", "location": "하노이", "capacity": "도로", "note": "철거 가속"},
            {"name": "라오스 연결 고속도로 착공", "location": "중서부", "capacity": "$9.1억", "note": "2026 착공"},
            {"name": "하노이 AI·TOD 메트로 미래도시", "location": "하노이", "capacity": "장기계획", "note": "마스터플랜"},
        ],
    },
    "VN-MEKONG-DELTA-2030": {
        "description_ko": "기후변화 대응 메콩델타 지속가능 발전계획입니다. 도로·수로 인프라 확충, 홍수·염수 대응이 핵심이며 2026년 깐터 폐수 이슈와 농업환경부 환경 선제대응 지시가 주요 현안입니다.",
        "kpi_targets": [
            {"indicator": "고속도로 연장", "target": "760km (2026)", "current": "~180km", "baseline": "180km"},
            {"indicator": "도시 폐수처리율", "target": "60%", "current": "~10%", "baseline": "10%"},
        ],
        "key_projects": [
            {"name": "메콩델타 상수도 공급 확대", "location": "안장·동탑", "capacity": "미정", "note": "계획"},
        ],
    },
    "VN-URB-METRO-2030": {
        "description_ko": "하노이·호치민 도시철도 대규모 확장계획입니다. Resolution 188/2025 TOD 특별 메커니즘 도입으로 민간투자 활성화가 기대되며 한국·일본 기업의 차량·설비 공급 협력이 핵심 기회입니다.",
        "kpi_targets": [
            {"indicator": "하노이 메트로 운영 노선", "target": "15개 노선 (2035)", "current": "2개 노선", "baseline": "2개"},
            {"indicator": "호치민 메트로", "target": "8개 노선 (2035)", "current": "1개 노선", "baseline": "1개"},
        ],
        "key_projects": [
            {"name": "하노이 메트로 AI·TOD 미래도시", "location": "하노이", "capacity": "1,153km(장기)", "note": "마스터플랜"},
            {"name": "HCM 핵심 연결 교통 장애 해소", "location": "호치민", "capacity": "광역 교통", "note": "2026.5 추진"},
        ],
    },
    "VN-SC-2030": {
        "description_ko": "2030년까지 스마트시티 서비스 보급률 80% 목표의 국가 스마트시티 계획입니다. 2026.5 디지털기술 청사진 승인으로 5개 인큐베이터 확정됐습니다.",
        "kpi_targets": [
            {"indicator": "스마트 서비스 보급률", "target": "80%", "current": "~12%", "baseline": "12%"},
            {"indicator": "ICT 인프라 투자", "target": "$21억", "current": "~$3억", "baseline": "$3억"},
        ],
        "key_projects": [
            {"name": "베트남 2030 디지털기술 청사진", "location": "전국", "capacity": "국가계획", "note": "2026.5 승인"},
            {"name": "교육부 5개 디지털기술 인큐베이터", "location": "전국", "capacity": "5개", "note": "확정"},
        ],
    },
    "VN-EV-2030": {
        "description_ko": "2030년까지 신규 판매차량 100%를 친환경차로 전환하는 국가 목표입니다. VinFast 기업구조 개편, Honda Vietnam EV 투자 인센티브 요청, 바이오연료(E10) 전국 출시가 2026년 현안입니다.",
        "kpi_targets": [
            {"indicator": "EV 신규 판매 비율", "target": "100% (2030)", "current": "~10%", "baseline": "10%"},
            {"indicator": "충전 인프라", "target": "25만 충전소", "current": "~5,000개소", "baseline": ""},
        ],
        "key_projects": [
            {"name": "VinFast 기업구조 개편", "location": "전국", "capacity": "EV 생산", "note": "2026 진행"},
            {"name": "바이오연료 E10 전국 출시", "location": "전국", "capacity": "정책 시행", "note": "준비 완료"},
        ],
    },
    "HN-URBAN-INFRA": {
        "description_ko": "하노이 100년 마스터플랜으로 인구 상한 2,000만명, AI·TOD 1,153km 메트로, 2035년 시내 개인차량 제한이 핵심입니다. 외국인에게는 TOD 역세권 개발 PPP 참여가 핵심 기회입니다.",
        "kpi_targets": [
            {"indicator": "인구 상한", "target": "2,000만명 (2045)", "current": "~1,050만명", "baseline": "1,050만명"},
            {"indicator": "개인차량 제한 시행", "target": "2035년", "current": "계획", "baseline": ""},
        ],
        "key_projects": [
            {"name": "하노이 링로드 6.30 개통", "location": "하노이", "capacity": "도로", "note": "철거 가속"},
            {"name": "하노이 2공항 계획", "location": "하노이 인근", "capacity": "5,000만명/년", "note": "장기 계획"},
        ],
    },
    "HN-URBAN-WEST": {
        "description_ko": "하노이 서부 호아락 첨단기술단지·하동 신도시 등을 포함한 서부 성장축 개발계획입니다. 하동 메트로 연장, TOD 역세권 주거·상업 복합개발이 핵심입니다.",
        "kpi_targets": [
            {"indicator": "호아락 첨단단지 입주율", "target": "80%", "current": "~45%", "baseline": "45%"},
        ],
        "key_projects": [
            {"name": "Vingroup 역대 최대 도시개발", "location": "하노이 서부", "capacity": "미정", "note": "2026 발표"},
        ],
    },
    "HN-URBAN-NORTH": {
        "description_ko": "하노이 북부 동아잉·솟선 일대 신도시·산업 개발계획입니다. 노이바이 공항 2단계 확장, 동아잉 도시발전 특별지구 지정이 핵심입니다.",
        "kpi_targets": [
            {"indicator": "노이바이 공항 용량", "target": "1억명/년 (2단계)", "current": "~4,500만명", "baseline": "4,500만명"},
        ],
        "key_projects": [
            {"name": "노이바이 공항 2단계 확장", "location": "하노이 북부", "capacity": "1억명/년", "note": "장기 계획"},
            {"name": "하노이 북부 상수도 확장 2단계", "location": "하노이 북부", "capacity": "$3.2억", "note": "입찰 진행"},
        ],
    },
}


def main():
    log.info("=" * 60)
    log.info("knowledge_index.json Layer1 업데이트 시작")
    log.info("=" * 60)

    if not KI_PATH.exists():
        log.error(f"파일 없음: {KI_PATH}")
        return

    with open(KI_PATH, encoding='utf-8') as f:
        ki = json.load(f)

    plans = ki.get('masterplans', {})
    updated = 0
    skipped = 0

    for plan_id, layer1 in LAYER1_DATA.items():
        if plan_id not in plans:
            log.warning(f"  플랜 없음 (건너뜀): {plan_id}")
            skipped += 1
            continue

        # 기존 필드 보존, Layer1 3개 필드만 추가/업데이트
        for field in ('description_ko', 'kpi_targets', 'key_projects'):
            plans[plan_id][field] = layer1[field]

        updated += 1
        log.info(f"  ✅ {plan_id}: description_ko({len(layer1['description_ko'])}자) "
                 f"KPI({len(layer1['kpi_targets'])}개) "
                 f"프로젝트({len(layer1['key_projects'])}개)")

    # 저장
    with open(KI_PATH, 'w', encoding='utf-8') as f:
        json.dump(ki, f, ensure_ascii=False, indent=2)

    log.info("=" * 60)
    log.info(f"완료: {updated}개 플랜 업데이트 / {skipped}개 건너뜀")
    log.info(f"저장: {KI_PATH}")
    log.info("=" * 60)


if __name__ == '__main__':
    main()
