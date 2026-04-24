'use strict';
const pptxgen = require('pptxgenjs');
const fs = require('fs');

// ── 색상 시스템 ──────────────────────────────────────────────────────────
const C = {
  navy:   '0C2340', navyL:  '1A3A6B',
  teal:   '0D9488', tealL:  'E1F5EE', tealM:  '14B8A6',
  blue:   '185FA5', blueL:  'E6F1FB',
  amber:  '854F0B', amberL: 'FFF176', amberM: 'EF9F27',
  green:  '3B6D11', greenL: 'EAF3DE',
  coral:  '993C1D', coralL: 'FAECE7',
  gray:   '64748B', grayL:  'F8FAFC', grayM:  'E2E8F0',
  white:  'FFFFFF', black:  '1A1A1A',
  // 섹터별 컬러
  env:    '0D9488',  // 환경 — teal
  energy: 'F59E0B',  // 에너지 — amber
  urban:  '3B82F6',  // 도시교통 — blue
  hdr:    '0C2340',  // 헤더 배경
};

// 섹터 → 색상 매핑
const SECTOR_COLOR = {
  'Waste Water':            C.teal,
  'Water Supply/Drainage':  '0891B2',
  'Solid Waste':            '059669',
  'Power':                  'F59E0B',
  'Oil & Gas':              '78350F',
  'Transport':              '3B82F6',
  'Smart City':             '7C3AED',
  'Industrial Parks':       'DC2626',
};

const AREA_COLOR = {
  'Environment':    C.teal,
  'Energy Develop.': 'F59E0B',
  'Urban Develop.': '3B82F6',
};

const mkShadow = () => ({ type: 'outer', blur: 8, offset: 3, angle: 135, color: '000000', opacity: 0.10 });

// ── 데이터 로드 ──────────────────────────────────────────────────────────
const LAYER1 = JSON.parse(fs.readFileSync('/home/claude/data/shared/layer1_data.json', 'utf-8'));
const AREA_ORDER = { 'Environment': 0, 'Energy Develop.': 1, 'Urban Develop.': 2 };
const plans = Object.values(LAYER1).filter(p => p && p.plan_id).sort((a, b) =>
  (AREA_ORDER[a.area] ?? 9) - (AREA_ORDER[b.area] ?? 9) ||
  (a.plan_id || '').localeCompare(b.plan_id || '')
);

// ── 유틸 ─────────────────────────────────────────────────────────────────
function truncate(str, n) {
  if (!str) return '';
  return str.length > n ? str.slice(0, n - 1) + '…' : str;
}

// ══════════════════════════════════════════════════════════════════════════
//  슬라이드 빌더
// ══════════════════════════════════════════════════════════════════════════

// ── 슬라이드 1: 커버 ─────────────────────────────────────────────────────
function addCoverSlide(pres) {
  const slide = pres.addSlide();
  slide.background = { color: C.navy };

  // 좌측 강조 사각형
  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.35, h: 5.625, fill: { color: C.teal } });

  // 우측 하단 장식
  slide.addShape(pres.shapes.RECTANGLE, { x: 7.5, y: 4.0, w: 2.5, h: 1.625, fill: { color: C.navyL } });
  slide.addShape(pres.shapes.RECTANGLE, { x: 8.5, y: 3.2, w: 1.5, h: 0.8, fill: { color: C.teal, transparency: 60 } });

  // 메인 타이틀
  slide.addText('VIETNAM INFRASTRUCTURE', {
    x: 0.6, y: 0.7, w: 8.8, h: 0.7,
    fontSize: 32, bold: true, color: C.white, fontFace: 'Arial Black',
    charSpacing: 4,
  });
  slide.addText('MARKET INTELLIGENCE REPORT', {
    x: 0.6, y: 1.42, w: 8.8, h: 0.55,
    fontSize: 22, bold: true, color: C.tealM, fontFace: 'Arial',
    charSpacing: 2,
  });

  // 구분선
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 2.05, w: 8.0, h: 0.04, fill: { color: C.tealM } });

  slide.addText('베트남 인프라 시장 동향 주간 보고서', {
    x: 0.6, y: 2.2, w: 8.8, h: 0.45,
    fontSize: 16, color: 'A5B4C8', fontFace: 'Arial', italic: true,
  });

  // 발행 정보 카드
  const infoCards = [
    { label: '발행일',    value: '2026년 4월 24일' },
    { label: '분석 기준', value: 'knowledge_index v2.3' },
    { label: '마스터플랜', value: `${plans.length}개 플랜` },
    { label: 'AI 분석',  value: 'Claude Haiku' },
  ];
  infoCards.forEach((card, i) => {
    const x = 0.6 + i * 2.35;
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y: 2.85, w: 2.2, h: 1.0,
      fill: { color: C.navyL }, shadow: mkShadow(),
    });
    slide.addText(card.label, { x, y: 2.88, w: 2.2, h: 0.28, fontSize: 9, color: C.tealM, align: 'center', fontFace: 'Arial' });
    slide.addText(card.value, { x, y: 3.16, w: 2.2, h: 0.5, fontSize: 13, bold: true, color: C.white, align: 'center', fontFace: 'Arial' });
  });

  // 커버 하단 — 영역별 기사 수 표시
  slide.addText('Coverage by Area', {
    x: 0.6, y: 4.1, w: 8.8, h: 0.32, fontSize: 11, color: '8899AA', fontFace: 'Arial',
  });
  const areas = [
    { label: '환경 인프라',    count: '4 Plans', color: C.teal },
    { label: '에너지·전력',    count: '4 Plans', color: 'F59E0B' },
    { label: '도시·교통·산업', count: '4 Plans', color: '3B82F6' },
  ];
  areas.forEach((a, i) => {
    const x = 0.6 + i * 3.1;
    slide.addShape(pres.shapes.RECTANGLE, { x, y: 4.5, w: 2.9, h: 0.72, fill: { color: a.color, transparency: 20 } });
    slide.addText(a.label, { x, y: 4.52, w: 2.9, h: 0.32, fontSize: 11, bold: true, color: C.white, align: 'center', fontFace: 'Arial' });
    slide.addText(a.count,  { x, y: 4.84, w: 2.9, h: 0.32, fontSize: 12, color: C.white, align: 'center', fontFace: 'Arial' });
  });

  slide.addText('hms4792.github.io/vietnam-infra-news', {
    x: 0.6, y: 5.32, w: 8.8, h: 0.22, fontSize: 8, color: '445566', fontFace: 'Arial',
  });
}

// ── 슬라이드 2: 전체 KPI 현황 대시보드 ───────────────────────────────────
function addKpiDashboardSlide(pres) {
  const slide = pres.addSlide();
  slide.background = { color: C.grayL };

  // 헤더 바
  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.72, fill: { color: C.navy } });
  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0.72, w: 10, h: 0.05, fill: { color: C.teal } });
  slide.addText('전체 마스터플랜 KPI 목표 현황', {
    x: 0.4, y: 0.12, w: 9.2, h: 0.5, fontSize: 22, bold: true, color: C.white, fontFace: 'Arial', margin: 0,
  });
  slide.addText('12개 마스터플랜 · KPI 47개 · 2030 목표 기준', {
    x: 6.5, y: 0.18, w: 3.2, h: 0.38, fontSize: 10, color: C.tealM, align: 'right', fontFace: 'Arial', margin: 0,
  });

  // 섹터별 KPI 카드 (3열 4행)
  const kpiHighlights = [
    { plan: 'VN-WW-2030',           label: '도시 폐수처리율',     target: '85%',          current: '~29%→50%', color: C.teal,  icon: '💧' },
    { plan: 'VN-SWM-NATIONAL-2030', label: 'WtE 소각 비율',      target: '50%',          current: '30% 달성중', color: '059669',icon: '♻️' },
    { plan: 'VN-WAT-RESOURCES',     label: '지하수 관리 대수층',  target: '27개 완전관리', current: '12개 관리', color: '0891B2',icon: '🌊' },
    { plan: 'VN-WAT-URBAN',         label: '도시 상수 보급률',    target: '100%',         current: '95% 수준', color: '0891B2',icon: '🚰' },
    { plan: 'VN-PWR-PDP8-RENEWABLE',label: '해상풍력(2030)',      target: '17,032 MW',    current: '★개정 3배↑', color: 'F59E0B',icon: '⚡' },
    { plan: 'VN-PWR-PDP8-LNG',      label: 'LNG 발전 용량',      target: '23,900 MW',    current: '3,000 MW', color: 'D97706',icon: '🔥' },
    { plan: 'VN-PWR-PDP8-NUCLEAR',  label: '원자력(2035 목표)',   target: '4,000 MW',     current: '★신규추가', color: '7C3AED',icon: '⚛️' },
    { plan: 'VN-OG-2030',           label: '원유 생산량',         target: '8~10백만톤/년', current: '유지 목표', color: '78350F',icon: '🛢️' },
    { plan: 'VN-TRAN-2055',         label: '고속도로 총연장',     target: '5,000 km',     current: '1,892 km', color: '3B82F6',icon: '🛣️' },
    { plan: 'VN-URB-METRO-2030',    label: '하노이 메트로',       target: '15개 노선',    current: '2개 운영중', color: '8B5CF6',icon: '🚇' },
    { plan: 'VN-IP-NORTH-2030',     label: 'FDI 유입 목표',       target: '연 $20B+',     current: '2025: $18B', color: 'DC2626',icon: '🏭' },
    { plan: 'VN-HAN-URBAN-2045',    label: '하노이 총투자',       target: '$2.5T (2045)', current: 'D1668 확정', color: '1D4ED8',icon: '🏙️' },
  ];

  kpiHighlights.forEach((item, i) => {
    const col = i % 3;
    const row = Math.floor(i / 3);
    const x = 0.2 + col * 3.27;
    const y = 0.95 + row * 1.18;

    // 카드 배경
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 3.1, h: 1.08,
      fill: { color: C.white }, shadow: mkShadow(),
    });
    // 좌측 색상 바
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 0.06, h: 1.08, fill: { color: item.color },
    });

    // 아이콘 + 라벨
    slide.addText(item.label, {
      x: x + 0.12, y: y + 0.06, w: 2.6, h: 0.28,
      fontSize: 10, bold: true, color: C.black, fontFace: 'Arial', margin: 0,
    });

    // 목표값 (크게)
    slide.addText(truncate(item.target, 18), {
      x: x + 0.12, y: y + 0.34, w: 1.5, h: 0.36,
      fontSize: 16, bold: true, color: item.color, fontFace: 'Arial', margin: 0,
    });
    slide.addText('목표', {
      x: x + 0.12, y: y + 0.70, w: 0.6, h: 0.22,
      fontSize: 8, color: C.gray, fontFace: 'Arial', margin: 0,
    });

    // 현황값
    const isChanged = item.current.startsWith('★');
    slide.addShape(pres.shapes.RECTANGLE, {
      x: x + 1.72, y: y + 0.30, w: 1.25, h: 0.42,
      fill: { color: isChanged ? C.amberL : C.grayM },
    });
    slide.addText(truncate(item.current.replace('★',''), 16), {
      x: x + 1.72, y: y + 0.30, w: 1.25, h: 0.42,
      fontSize: isChanged ? 9 : 10, bold: isChanged, color: isChanged ? C.amber : C.black,
      align: 'center', valign: 'middle', fontFace: 'Arial', margin: 0,
    });
    slide.addText('현황', {
      x: x + 1.72, y: y + 0.72, w: 1.25, h: 0.2,
      fontSize: 8, color: C.gray, align: 'center', fontFace: 'Arial', margin: 0,
    });
  });

  // 하단 변동 안내
  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 5.32, w: 10, h: 0.3, fill: { color: 'FFFDE7' } });
  slide.addText('★ 노란색 = 직전 주 대비 KPI 변동사항 (PDP8 해상풍력 3배↑ · 원자력 신규추가 · 롱탄공항 개항 일정 변경)',
    { x: 0.3, y: 5.33, w: 9.4, h: 0.26, fontSize: 9, color: C.amber, bold: true, fontFace: 'Arial', margin: 0 });
}

// ── 슬라이드 3: 영역 구분 슬라이드 ───────────────────────────────────────
function addAreaDividerSlide(pres, area, planList) {
  const slide = pres.addSlide();
  const areaColor = AREA_COLOR[area] || C.navy;
  slide.background = { color: areaColor };

  // 우측 반투명 패턴
  slide.addShape(pres.shapes.RECTANGLE, { x: 6.5, y: 0, w: 3.5, h: 5.625, fill: { color: C.white, transparency: 88 } });
  slide.addShape(pres.shapes.RECTANGLE, { x: 7.5, y: 0, w: 2.5, h: 5.625, fill: { color: C.white, transparency: 82 } });

  const areaLabel = { 'Environment': '환경 인프라', 'Energy Develop.': '에너지·전력', 'Urban Develop.': '도시·교통·산업' };
  const areaEn    = { 'Environment': 'Environment Infrastructure', 'Energy Develop.': 'Energy & Power', 'Urban Develop.': 'Urban & Transport' };

  slide.addText(areaLabel[area] || area, {
    x: 0.5, y: 0.9, w: 9, h: 1.0, fontSize: 44, bold: true, color: C.white,
    fontFace: 'Arial Black', margin: 0,
  });
  slide.addText(areaEn[area] || area, {
    x: 0.5, y: 1.95, w: 9, h: 0.5, fontSize: 18, color: 'D0E4F0', fontFace: 'Arial', italic: true, margin: 0,
  });

  slide.addShape(pres.shapes.RECTANGLE, { x: 0.5, y: 2.55, w: 6, h: 0.04, fill: { color: C.white, transparency: 40 } });

  // 플랜 목록
  slide.addText('포함 마스터플랜', {
    x: 0.5, y: 2.75, w: 8, h: 0.32, fontSize: 12, color: 'FFFFFF', fontFace: 'Arial', margin: 0,
  });
  planList.forEach((plan, i) => {
    const col = i % 2, row = Math.floor(i / 2);
    const x = 0.5 + col * 4.5;
    const y = 3.12 + row * 0.56;
    slide.addShape(pres.shapes.RECTANGLE, { x, y, w: 4.2, h: 0.44, fill: { color: C.white, transparency: 75 } });
    slide.addText(plan.plan_id, {
      x: x + 0.1, y: y + 0.01, w: 2.1, h: 0.22, fontSize: 9, bold: true, color: C.white, fontFace: 'Arial', margin: 0,
    });
    slide.addText(truncate(plan.title_ko, 28), {
      x: x + 0.1, y: y + 0.22, w: 4.0, h: 0.18, fontSize: 9, color: 'FFFFFF', fontFace: 'Arial', margin: 0,
    });
  });
}

// ── 슬라이드 4: 플랜 메인 슬라이드 ──────────────────────────────────────
function addPlanMainSlide(pres, plan) {
  const slide = pres.addSlide();
  slide.background = { color: C.grayL };

  const sColor = SECTOR_COLOR[plan.sector] || C.navy;

  // 헤더 바
  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.65, fill: { color: C.navy } });
  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0.65, w: 10, h: 0.045, fill: { color: sColor } });

  // 플랜 ID 배지
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.3, y: 0.08, w: 2.0, h: 0.34, fill: { color: sColor } });
  slide.addText(plan.plan_id, {
    x: 0.3, y: 0.08, w: 2.0, h: 0.34, fontSize: 8.5, bold: true, color: C.white,
    align: 'center', valign: 'middle', fontFace: 'Arial', margin: 0,
  });

  // 플랜 제목
  slide.addText(truncate(plan.title_ko, 60), {
    x: 2.45, y: 0.08, w: 7.2, h: 0.34, fontSize: 14, bold: true, color: C.white,
    fontFace: 'Arial', valign: 'middle', margin: 0,
  });
  slide.addText(plan.decision, {
    x: 2.45, y: 0.4, w: 7.2, h: 0.2, fontSize: 9, color: 'A0B4C8',
    fontFace: 'Arial', margin: 0,
  });

  // ── 좌측: 사업 개요 + KPI ────────────────────────────────────────────
  const desc = plan.description_ko || '';

  // 사업 개요 섹션 헤더
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.2, y: 0.82, w: 4.6, h: 0.3, fill: { color: sColor } });
  slide.addText('■ 사업 개요', {
    x: 0.2, y: 0.82, w: 4.6, h: 0.3, fontSize: 11, bold: true, color: C.white,
    fontFace: 'Arial', valign: 'middle', margin: 4,
  });

  // 사업 개요 텍스트 박스
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.2, y: 1.12, w: 4.6, h: 1.6, fill: { color: C.white }, shadow: mkShadow() });
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.2, y: 1.12, w: 0.06, h: 1.6, fill: { color: sColor } });
  slide.addText(truncate(desc, 300), {
    x: 0.32, y: 1.14, w: 4.44, h: 1.56,
    fontSize: 10.5, color: C.black, fontFace: 'Arial',
    valign: 'top', wrap: true, margin: 4,
  });

  // KPI 섹션 헤더
  slide.addShape(pres.shapes.RECTANGLE, { x: 0.2, y: 2.82, w: 4.6, h: 0.3, fill: { color: sColor } });
  slide.addText('■ KPI 목표 및 현황', {
    x: 0.2, y: 2.82, w: 4.6, h: 0.3, fontSize: 11, bold: true, color: C.white,
    fontFace: 'Arial', valign: 'middle', margin: 4,
  });

  // KPI 카드들
  const kpis = plan.kpi_targets.slice(0, 4);
  kpis.forEach((kpi, i) => {
    const row = Math.floor(i / 2), col = i % 2;
    const x = 0.2 + col * 2.35;
    const y = 3.18 + row * 1.18;
    const isChanged = kpi.changed === true;

    slide.addShape(pres.shapes.RECTANGLE, {
      x, y, w: 2.2, h: 1.08,
      fill: { color: isChanged ? 'FFFDE7' : C.white }, shadow: mkShadow(),
    });
    slide.addShape(pres.shapes.RECTANGLE, { x, y, w: 0.06, h: 1.08, fill: { color: isChanged ? C.amberM : sColor } });

    slide.addText(truncate(kpi.indicator, 24), {
      x: x + 0.1, y: y + 0.06, w: 2.05, h: 0.28,
      fontSize: 9, bold: true, color: C.black, fontFace: 'Arial', margin: 0,
    });
    slide.addText(truncate(kpi.target_2030, 18), {
      x: x + 0.1, y: y + 0.34, w: 2.05, h: 0.36,
      fontSize: 14, bold: true, color: isChanged ? C.amber : sColor, fontFace: 'Arial', margin: 0,
    });
    slide.addText((isChanged ? '★ ' : '') + truncate(kpi.current, 28), {
      x: x + 0.1, y: y + 0.70, w: 2.05, h: 0.28,
      fontSize: 8.5, color: isChanged ? C.amber : C.gray, fontFace: 'Arial', margin: 0,
    });
  });

  // ── 우측: 프로젝트 목록 ──────────────────────────────────────────────
  slide.addShape(pres.shapes.RECTANGLE, { x: 5.0, y: 0.82, w: 4.8, h: 0.3, fill: { color: C.navy } });
  slide.addText('■ 주요 프로젝트 목록', {
    x: 5.0, y: 0.82, w: 4.8, h: 0.3, fontSize: 11, bold: true, color: C.white,
    fontFace: 'Arial', valign: 'middle', margin: 4,
  });

  const projects = plan.key_projects.slice(0, 8);
  const hasMultiCol = projects.length > 4;
  const colW = hasMultiCol ? 2.3 : 4.65;

  projects.forEach((proj, i) => {
    const col = hasMultiCol ? Math.floor(i / Math.ceil(projects.length / 2)) : 0;
    const row = hasMultiCol ? i % Math.ceil(projects.length / 2) : i;
    const x = 5.0 + col * (colW + 0.1);
    const y = 1.22 + row * 0.54;
    const rowH = 0.5;

    slide.addShape(pres.shapes.RECTANGLE, { x, y, w: colW, h: rowH, fill: { color: C.white }, shadow: mkShadow() });
    slide.addShape(pres.shapes.RECTANGLE, { x, y, w: 0.06, h: rowH, fill: { color: sColor, transparency: 30 } });

    // 프로젝트명
    slide.addText(truncate(proj.name, 30), {
      x: x + 0.1, y: y + 0.03, w: colW - 0.15, h: 0.22,
      fontSize: 9.5, bold: true, color: C.black, fontFace: 'Arial', margin: 0,
    });
    // 위치 + 용량
    const detail = [proj.location, proj.capacity].filter(Boolean).join(' | ');
    slide.addText(truncate(detail, 38), {
      x: x + 0.1, y: y + 0.25, w: colW - 0.15, h: 0.16,
      fontSize: 8.5, color: C.gray, fontFace: 'Arial', margin: 0,
    });
    // 비고
    if (proj.note && !hasMultiCol) {
      slide.addText(truncate(proj.note, 50), {
        x: x + 0.1, y: y + 0.41, w: colW - 0.15, h: 0.14,
        fontSize: 7.5, color: sColor, fontFace: 'Arial', margin: 0,
      });
    }
  });

  if (plan.key_projects.length > 8) {
    slide.addText(`+ ${plan.key_projects.length - 8}개 추가 프로젝트 (상세 보고서 참조)`, {
      x: 5.0, y: 5.25, w: 4.8, h: 0.22,
      fontSize: 8.5, color: C.gray, fontFace: 'Arial', margin: 0,
    });
  }

  // 하단 섹터 태그
  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 5.42, w: 10, h: 0.205, fill: { color: C.navy } });
  slide.addText(`${plan.sector}  |  ${plan.area}  |  ${plan.decision}`, {
    x: 0.3, y: 5.43, w: 9.4, h: 0.18, fontSize: 8, color: '8899AA', fontFace: 'Arial', margin: 0,
  });
}

// ── 슬라이드 5: 플랜 프로젝트 상세 (프로젝트 많은 플랜 전용) ─────────────
function addPlanProjectDetailSlide(pres, plan) {
  if (plan.key_projects.length <= 8) return;

  const slide = pres.addSlide();
  slide.background = { color: C.grayL };
  const sColor = SECTOR_COLOR[plan.sector] || C.navy;

  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.65, fill: { color: C.navy } });
  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0.65, w: 10, h: 0.045, fill: { color: sColor } });
  slide.addText(`${plan.plan_id} — 프로젝트 전체 목록 (${plan.key_projects.length}개)`, {
    x: 0.3, y: 0.1, w: 9.4, h: 0.46, fontSize: 16, bold: true, color: C.white, fontFace: 'Arial', margin: 0,
  });

  // 테이블 형태로 표시
  const tableData = [
    [
      { text: '프로젝트명', options: { bold: true, fill: { color: C.navy }, color: C.white, fontSize: 9 } },
      { text: '위치',       options: { bold: true, fill: { color: C.navy }, color: C.white, fontSize: 9 } },
      { text: '규모/용량',  options: { bold: true, fill: { color: C.navy }, color: C.white, fontSize: 9 } },
      { text: '비고',       options: { bold: true, fill: { color: C.navy }, color: C.white, fontSize: 9 } },
    ],
    ...plan.key_projects.slice(0, 16).map((proj, i) => [
      { text: truncate(proj.name, 26),     options: { fontSize: 8.5, fill: { color: i % 2 === 0 ? C.white : 'F0F4F8' } } },
      { text: truncate(proj.location || '', 14), options: { fontSize: 8.5, fill: { color: i % 2 === 0 ? C.white : 'F0F4F8' } } },
      { text: truncate(proj.capacity || '', 18), options: { fontSize: 8.5, fill: { color: i % 2 === 0 ? C.white : 'F0F4F8' }, bold: true, color: sColor } },
      { text: truncate(proj.note || '', 34),     options: { fontSize: 8.5, fill: { color: i % 2 === 0 ? C.white : 'F0F4F8' }, color: C.gray } },
    ])
  ];

  slide.addTable(tableData, {
    x: 0.25, y: 0.82, w: 9.5,
    colW: [2.8, 1.6, 2.2, 2.9],
    border: { pt: 0.5, color: C.grayM },
    rowH: 0.29,
  });
}

// ── 슬라이드: 차트 슬라이드 (선택 플랜) ─────────────────────────────────
function addChartSlides(pres) {
  // KPI 진행률 바 차트
  const slide = pres.addSlide();
  slide.background = { color: C.grayL };

  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 10, h: 0.65, fill: { color: C.navy } });
  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0.65, w: 10, h: 0.045, fill: { color: C.teal } });
  slide.addText('KPI 달성률 현황 비교 (2025년 기준)', {
    x: 0.3, y: 0.1, w: 9, h: 0.46, fontSize: 18, bold: true, color: C.white, fontFace: 'Arial', margin: 0,
  });

  // 진행률 데이터 (보고서 기반)
  const kpiProgress = [
    { label: '도시 상수 보급률',    current: 95,  target: 100, color: '0891B2' },
    { label: '도시 폐기물 수거율',  current: 93,  target: 100, color: '059669' },
    { label: '고속도로(5,000km)',   current: 38,  target: 100, color: '3B82F6' },
    { label: 'WtE 소각 비율',       current: 25,  target: 50,  color: '10B981' },
    { label: '도시 폐수처리율(하노이)', current: 50, target: 85, color: C.teal  },
    { label: '해상풍력(17,032MW)',   current: 2,   target: 100, color: 'F59E0B' },
    { label: 'LNG 발전(23,900MW)',   current: 12,  target: 100, color: 'D97706' },
    { label: '도시철도(46개 노선)',  current: 11,  target: 100, color: '7C3AED' },
  ];

  // 왼쪽: 진행률 바
  kpiProgress.forEach((item, i) => {
    const y = 0.9 + i * 0.59;
    // 라벨
    slide.addText(item.label, {
      x: 0.2, y: y, w: 2.8, h: 0.28, fontSize: 10, color: C.black, fontFace: 'Arial',
      align: 'right', valign: 'middle', margin: 0,
    });
    // 배경 바
    slide.addShape(pres.shapes.RECTANGLE, { x: 3.1, y: y + 0.04, w: 4.5, h: 0.24, fill: { color: C.grayM } });
    // 진행 바
    const pct = Math.min(item.current, 100);
    if (pct > 0) {
      slide.addShape(pres.shapes.RECTANGLE, {
        x: 3.1, y: y + 0.04, w: 4.5 * pct / 100, h: 0.24,
        fill: { color: item.color },
      });
    }
    // 수치
    slide.addText(`${item.current}% / ${item.target}%`, {
      x: 7.7, y: y, w: 2.0, h: 0.28, fontSize: 10, bold: true, color: item.color, fontFace: 'Arial',
      valign: 'middle', margin: 0,
    });
  });

  // 우측: 원형 차트 (환경/에너지/도시 비중)
  slide.addChart(pres.charts.PIE, [{
    name: '플랜 비중', labels: ['환경 인프라', '에너지·전력', '도시·교통'], values: [33, 33, 34]
  }], {
    x: 7.6, y: 1.0, w: 2.2, h: 2.2,
    chartColors: [C.teal, 'F59E0B', '3B82F6'],
    showPercent: true,
    dataLabelColor: C.white, dataLabelFontSize: 10, dataLabelFontBold: true,
    showLegend: true, legendPos: 'b', legendFontSize: 8,
    chartArea: { fill: { color: C.grayL } },
  });

  // 투자 규모 막대
  const invData = [
    { name: '투자 규모 ($B)', labels: ['환경(폐수)', 'WtE', '상수도', '재생에너지', 'LNG', '원자력', '교통'], values: [2.5, 1.0, 2.0, 134.7, 10.0, 8.0, 60.0] }
  ];
  slide.addChart(pres.charts.BAR, invData, {
    x: 0.2, y: 3.9, w: 7.2, h: 1.5, barDir: 'bar',
    chartColors: [C.teal, '059669', '0891B2', 'F59E0B', 'D97706', '7C3AED', '3B82F6'],
    chartArea: { fill: { color: C.white }, roundedCorners: true },
    catAxisLabelColor: C.gray, catAxisLabelFontSize: 8,
    valAxisLabelColor: C.gray, valAxisLabelFontSize: 8,
    valGridLine: { color: C.grayM, size: 0.5 },
    catGridLine: { style: 'none' },
    showValue: true, dataLabelFontSize: 8, dataLabelColor: C.black,
    showLegend: false, showTitle: true, title: '주요 부문 투자 계획 ($B)',
    titleFontSize: 10, titleColor: C.navy,
  });
}

// ── 슬라이드: 롱탄 공항 / PDP8 변동 하이라이트 ──────────────────────────
function addHighlightSlide(pres) {
  const slide = pres.addSlide();
  slide.background = { color: C.navy };

  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.35, h: 5.625, fill: { color: C.amberM } });
  slide.addText('이번 주 핵심 KPI 변동사항', {
    x: 0.6, y: 0.25, w: 9, h: 0.55, fontSize: 24, bold: true, color: C.white, fontFace: 'Arial', margin: 0,
  });
  slide.addText('★ 노란색 항목 = 직전 주 대비 변동 확인', {
    x: 0.6, y: 0.82, w: 9, h: 0.32, fontSize: 12, color: C.amberM, fontFace: 'Arial', margin: 0,
  });

  const highlights = [
    {
      title: '★ PDP8 해상풍력 3배 상향',
      plan:  'VN-PWR-PDP8-RENEWABLE',
      prev:  '6,000 MW',
      curr:  '17,032 MW',
      note:  'Decision 768 (2025.04.15) — GDP 성장 7%→10% 목표 상향이 촉발',
      color: 'F59E0B',
    },
    {
      title: '★ 원자력 재개 — 신규 추가',
      plan:  'VN-PWR-PDP8-NUCLEAR',
      prev:  '미포함',
      curr:  '4,000 MW (2035)',
      note:  'Resolution 70-NQ/TW — 닌투언 1·2호기 개발 재개 공식화',
      color: '7C3AED',
    },
    {
      title: '★ 롱탄공항 개항 일정 변경',
      plan:  'VN-TRAN-2055',
      prev:  '2025년 12월',
      curr:  '2026년 6월',
      note:  '노동력 부족(~6,000명) + 건설비 상승(아스팔트 40~50%↑) 원인',
      color: '3B82F6',
    },
  ];

  highlights.forEach((h, i) => {
    const y = 1.3 + i * 1.38;
    slide.addShape(pres.shapes.RECTANGLE, { x: 0.5, y, w: 9, h: 1.22, fill: { color: C.navyL }, shadow: mkShadow() });
    slide.addShape(pres.shapes.RECTANGLE, { x: 0.5, y, w: 0.06, h: 1.22, fill: { color: h.color } });

    slide.addText(h.title, {
      x: 0.7, y: y + 0.08, w: 8.6, h: 0.3, fontSize: 14, bold: true, color: h.color, fontFace: 'Arial', margin: 0,
    });
    slide.addText(h.plan, {
      x: 0.7, y: y + 0.38, w: 2.5, h: 0.22, fontSize: 8.5, color: '8899BB', fontFace: 'Arial', margin: 0,
    });

    // 이전/이후 화살표
    slide.addShape(pres.shapes.RECTANGLE, { x: 3.3, y: y + 0.32, w: 1.6, h: 0.38, fill: { color: C.gray } });
    slide.addText(h.prev, { x: 3.3, y: y + 0.32, w: 1.6, h: 0.38, fontSize: 12, color: C.white, align: 'center', valign: 'middle', fontFace: 'Arial', margin: 0 });
    slide.addText('→', { x: 5.0, y: y + 0.3, w: 0.6, h: 0.42, fontSize: 20, color: h.color, align: 'center', margin: 0 });
    slide.addShape(pres.shapes.RECTANGLE, { x: 5.65, y: y + 0.32, w: 2.2, h: 0.38, fill: { color: h.color } });
    slide.addText(h.curr, { x: 5.65, y: y + 0.32, w: 2.2, h: 0.38, fontSize: 13, bold: true, color: C.white, align: 'center', valign: 'middle', fontFace: 'Arial', margin: 0 });

    slide.addText(h.note, {
      x: 0.7, y: y + 0.86, w: 8.6, h: 0.28, fontSize: 9, color: 'A0B4C8', fontFace: 'Arial', margin: 0,
    });
  });
}

// ── 마지막 슬라이드: 요약 ────────────────────────────────────────────────
function addClosingSlide(pres) {
  const slide = pres.addSlide();
  slide.background = { color: C.navy };
  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.35, h: 5.625, fill: { color: C.teal } });

  slide.addText('Vietnam Infrastructure MI', {
    x: 0.6, y: 0.8, w: 9, h: 0.65, fontSize: 30, bold: true, color: C.white, fontFace: 'Arial Black', margin: 0,
  });
  slide.addText('Automated Report Pipeline · SA-8', {
    x: 0.6, y: 1.5, w: 9, h: 0.4, fontSize: 16, color: C.tealM, fontFace: 'Arial', italic: true, margin: 0,
  });

  slide.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 2.05, w: 8, h: 0.04, fill: { color: C.tealM } });

  const bullets = [
    '12개 마스터플랜 · KPI 47개 · 프로젝트 79개 — knowledge_index v2.3 기반',
    '매주 토요일 KST 22:00 자동 생성 — Claude Haiku AI 기사 분석 연계',
    'Layer 1 (사업 개요 고정) + Layer 2 (AI 동적 분석) 이중 레이어 구조',
    '★ 노란색 하이라이트 = KPI 변동 자동 감지 · 이메일 자동 첨부 발송',
    '대시보드: hms4792.github.io/vietnam-infra-news/',
  ];
  bullets.forEach((b, i) => {
    slide.addText([{ text: b, options: { bullet: true } }], {
      x: 0.6, y: 2.25 + i * 0.48, w: 9, h: 0.4,
      fontSize: 12.5, color: 'C0D0E0', fontFace: 'Arial', margin: 4,
    });
  });

  slide.addShape(pres.shapes.RECTANGLE, { x: 0, y: 5.28, w: 10, h: 0.345, fill: { color: C.navyL } });
  slide.addText('Vietnam Infrastructure Market Intelligence Report — SA-8 Auto-Generated | 2026-04-24', {
    x: 0.3, y: 5.3, w: 9.4, h: 0.3, fontSize: 8.5, color: '667788', fontFace: 'Arial', margin: 0,
  });
}

// ══════════════════════════════════════════════════════════════════════════
//  메인: 전체 PPT 조립
// ══════════════════════════════════════════════════════════════════════════
async function buildPPT() {
  const pres = new pptxgen();
  pres.layout  = 'LAYOUT_16x9';
  pres.author  = 'SA-8 MI Report Pipeline';
  pres.title   = 'Vietnam Infrastructure MI Report 2026-W17';
  pres.subject = '베트남 인프라 시장 동향 주간 보고서';

  console.log('슬라이드 생성 시작...');

  // 1. 커버
  addCoverSlide(pres);
  console.log('  ✅ 커버 슬라이드');

  // 2. 전체 KPI 대시보드
  addKpiDashboardSlide(pres);
  console.log('  ✅ KPI 대시보드');

  // 3. KPI 변동 하이라이트
  addHighlightSlide(pres);
  console.log('  ✅ KPI 변동 하이라이트');

  // 4. 차트 슬라이드
  addChartSlides(pres);
  console.log('  ✅ 차트 슬라이드');

  // 5. 플랜별 슬라이드 (영역 구분 + 각 플랜)
  const byArea = {};
  for (const plan of plans) {
    (byArea[plan.area] = byArea[plan.area] || []).push(plan);
  }

  for (const [area, areaPlans] of Object.entries(byArea).sort((a, b) =>
    (AREA_ORDER[a[0]] ?? 9) - (AREA_ORDER[b[0]] ?? 9)
  )) {
    addAreaDividerSlide(pres, area, areaPlans);
    console.log(`  ✅ 영역 구분: ${area}`);

    for (const plan of areaPlans) {
      addPlanMainSlide(pres, plan);
      // 프로젝트 상세 (20개 이상)
      addPlanProjectDetailSlide(pres, plan);
      console.log(`  ✅ 플랜: ${plan.plan_id}`);
    }
  }

  // 6. 마무리
  addClosingSlide(pres);
  console.log('  ✅ 클로징 슬라이드');

  const outPath = '/home/claude/VN_Infra_MI_Weekly_Report_20260424.pptx';
  await pres.writeFile({ fileName: outPath });
  const size = (require('fs').statSync(outPath).size / 1024).toFixed(0);
  console.log(`\n✅ PPT 생성 완료: ${outPath} (${size} KB)`);
  console.log(`   총 슬라이드: 커버+대시보드+차트+플랜12개+영역구분3개+클로징`);
}

buildPPT().catch(err => { console.error('오류:', err); process.exit(1); });
