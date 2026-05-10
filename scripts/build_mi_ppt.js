/**
 * build_mi_ppt.js  ── SA-8 PPT 빌더 v4.0
 * =========================================================
 * 경영진 보고용 전문 MI 발표 자료 (PptxGenJS 기반)
 *
 * v4.0 (2026-05-10) 핵심 변경:
 *   - 첨부 PPT(VN_Infra_MI_Weekly_Report_20260424.pptx) 디자인 완전 재현
 *   - Layer1 데이터(사업개요, KPI, 주요프로젝트) 완전 적용 — 절대 삭제 금지
 *   - 슬라이드 구조 (첨부 PPT 기준):
 *       Slide 1  : 표지 (Navy + Teal, Coverage by Area)
 *       Slide 2  : 전체 KPI 대시보드 (3×4 그리드)
 *       Slide 3  : 이번 주 KPI 변동사항 (노란 하이라이트)
 *       Slide 4  : KPI 달성률 비교 (가로 프로그레스 바)
 *       Slide 5  : 영역 구분 슬라이드 (환경 인프라)
 *       Slide 6+ : 플랜별 상세 슬라이드 (사업개요+KPI+프로젝트)
 *       Slide N  : 영역 구분 (에너지, 도시)
 *       Slide N+ : 플랜별 상세 슬라이드
 *       Slide L  : 클로징
 *   - 각 플랜: 주요 프로젝트 8개 이하는 1장, 초과시 전체 목록 테이블 슬라이드 추가
 *
 * 데이터 소스: SA8_DATA_FILE 환경변수 (generate_mi_report.py 페이로드)
 * 실행: node scripts/build_mi_ppt.js
 * 출력: docs/VN_Infra_MI_Weekly_Report_YYYYMMDD.pptx
 *
 * payload JSON 구조:
 * {
 *   report_date, report_period, total_articles, new_articles_count,
 *   executive_summary_ko,
 *   kpi_dashboard: [{label, target, current, changed}],
 *   kpi_changes:   [{plan_id, plan_name, indicator, from, to, reason}],
 *   kpi_achievement: [{label, current_pct}],
 *   areas: [
 *     { name_ko, name_en, color, plan_ids: [...] }
 *   ],
 *   plans: {
 *     "VN-XXX": {
 *       plan_name_ko, sector, area, decision,
 *       description_ko,           // ★ Layer1 필수
 *       kpi_targets: [            // ★ Layer1 필수
 *         {label, target, current, changed}
 *       ],
 *       key_projects: [           // ★ Layer1 필수
 *         {name_ko, location, capacity, note, status}
 *       ],
 *       analysis_ko,              // Layer2 AI 분석
 *       articles: [{title_ko, source, date, isNew}]
 *     }
 *   }
 * }
 */

'use strict';

const pptxgen = require('pptxgenjs');
const fs      = require('fs');
const path    = require('path');

// ── 데이터 로드 ────────────────────────────────────────────────────────
const BASE_DIR  = path.resolve(__dirname, '..');
const DATA_FILE = process.env.SA8_DATA_FILE
               || path.join(BASE_DIR, 'data', 'agent_output', 'sa8_report_payload.json');
const OUT_DIR   = path.join(BASE_DIR, 'docs');

if (!fs.existsSync(DATA_FILE)) {
  console.error('[PPT] 데이터 파일 없음:', DATA_FILE);
  process.exit(1);
}

const payload      = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));
const today        = payload.report_date   || new Date().toISOString().slice(0, 10);
const period       = payload.report_period || '';
const totalArts    = payload.total_articles      || 0;
const newCount     = payload.new_articles_count  || 0;
const execSumm     = payload.executive_summary_ko || payload.executive_summary || '';
const kpiDash      = payload.kpi_dashboard   || [];
const kpiChanges   = payload.kpi_changes     || [];
const kpiAchieve   = payload.kpi_achievement || [];
const areas        = payload.areas           || [];
const plans        = payload.plans           || {};
const dateTag      = today.replace(/-/g, '');
const outPath      = process.env.SA8_OUTPUT_PATH
               || path.join(OUT_DIR, `VN_Infra_MI_Weekly_Report_${dateTag}.pptx`);

if (!fs.existsSync(path.dirname(outPath))) {
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
}

console.log(`[build_mi_ppt.js v4.0] 데이터 로드`);
console.log(`  계획 수: ${Object.keys(plans).length}개 | 기사: ${totalArts}건 | 신규: ${newCount}건`);

// ── 색상 팔레트 (첨부 PPT 기준) ────────────────────────────────────────
const C = {
  navy:    '0C2340',  // 표지 배경
  teal:    '0d9488',  // 환경 포인트
  gold:    'D4A017',  // 에너지 포인트
  blue:    '2563EB',  // 도시·교통 포인트
  green:   '1A6B3C',  // 사업개요 섹션 헤더
  orange:  'D97706',  // KPI 섹션 헤더
  white:   'FFFFFF',
  offWhite:'F8F9FA',
  black:   '1A1A1A',
  gray:    '64748B',
  grayL:   'E2E8F0',
  yellow:  'FEF08A',  // KPI 변동 하이라이트
  yellowD: '854D0E',
  red:     'DC2626',
  // 섹터 색상
  env:     '059669',  // 환경 인프라
  energy:  'D97706',  // 에너지
  urban:   '2563EB',  // 도시·교통
};

// 영역별 색상
const AREA_COLORS = {
  '환경 인프라':  C.env,
  'Environment':  C.env,
  '에너지·전력':  C.energy,
  'Energy':       C.energy,
  '도시·교통·산업': C.urban,
  'Urban':        C.urban,
};

function getAreaColor(area) {
  for (const [k, v] of Object.entries(AREA_COLORS)) {
    if ((area || '').includes(k) || (area || '').includes(k.split('·')[0])) return v;
  }
  return C.teal;
}

function getSectorColor(sector) {
  const s = (sector || '').toLowerCase();
  if (s.includes('waste water') || s.includes('wastewater') || s.includes('water supply') || s.includes('solid waste'))
    return C.env;
  if (s.includes('power') || s.includes('oil') || s.includes('gas') || s.includes('energy'))
    return C.energy;
  return C.urban;
}

// ── 슬라이드 치수 (16:9) ───────────────────────────────────────────────
const W = 10, H = 5.625;

// ── PPT 인스턴스 생성 ──────────────────────────────────────────────────
const pres = new pptxgen();
pres.layout  = 'LAYOUT_16x9';
pres.author  = 'Claude SA-8 Auto-Report';
pres.title   = `Vietnam Infrastructure MI Weekly Report ${today}`;
pres.subject = 'Vietnam Infrastructure Market Intelligence';

// ══════════════════════════════════════════════════════════════════════════
// Slide 1: 표지
// ══════════════════════════════════════════════════════════════════════════
function addCoverSlide() {
  const sl = pres.addSlide();
  sl.background = { color: C.navy };

  // 좌측 teal 수직 바
  sl.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.18, h: H,
    fill: { color: C.teal }, line: { color: C.teal, width: 0 }
  });

  // 메인 타이틀
  sl.addText('VIETNAM INFRASTRUCTURE', {
    x: 0.35, y: 0.25, w: 9.3, h: 0.75,
    fontSize: 38, bold: true, fontFace: 'Arial Black',
    color: C.white, charSpacing: 2
  });
  sl.addText('MARKET INTELLIGENCE REPORT', {
    x: 0.35, y: 1.05, w: 9.3, h: 0.45,
    fontSize: 20, bold: true, fontFace: 'Arial',
    color: C.teal, charSpacing: 2
  });
  // 구분선 (teal 언더라인 — 직접 shape으로 구현)
  sl.addShape(pres.shapes.LINE, {
    x: 0.35, y: 1.78, w: 5.5, h: 0,
    line: { color: C.teal, width: 2.5 }
  });
  sl.addText('베트남 인프라 시장 동향 주간 보고서', {
    x: 0.35, y: 1.95, w: 9.3, h: 0.45,
    fontSize: 16, italic: true, fontFace: 'Arial',
    color: 'AADDFF'
  });

  // 메타 카드 4개
  const cards = [
    { label: '발행일',   val: `${today.replace(/-/g, '년 ').replace('-', '월 ')}일` },
    { label: '분석 기준', val: payload.knowledge_version || 'knowledge_index v2.3' },
    { label: '마스터플랜', val: `${Object.keys(plans).length}개 플랜` },
    { label: 'AI 분석',   val: 'Claude Haiku' },
  ];
  const cardW = 2.3, cardH = 0.72, cardY = 2.6, cardGap = 0.08;
  cards.forEach((c, i) => {
    const x = 0.35 + i * (cardW + cardGap);
    sl.addShape(pres.shapes.RECTANGLE, {
      x, y: cardY, w: cardW, h: cardH,
      fill: { color: '1A3A5C' }, line: { color: C.teal, width: 1 }
    });
    sl.addText(c.label, { x, y: cardY + 0.04, w: cardW, h: 0.22,
      fontSize: 9, color: C.teal, align: 'center', fontFace: 'Arial', bold: true });
    sl.addText(c.val,   { x, y: cardY + 0.28, w: cardW, h: 0.36,
      fontSize: 13, color: C.white, align: 'center', fontFace: 'Arial', bold: true });
  });

  // Coverage by Area
  sl.addText('Coverage by Area', {
    x: 0.35, y: 3.55, w: 3, h: 0.3,
    fontSize: 11, color: C.gray, fontFace: 'Arial'
  });

  const areaBands = [
    { label: '환경 인프라', sub: `${areas.find(a=>a.name_ko?.includes('환경'))?.plan_ids?.length||4} Plans`, color: C.env },
    { label: '에너지·전력', sub: `${areas.find(a=>a.name_ko?.includes('에너지'))?.plan_ids?.length||4} Plans`, color: C.energy },
    { label: '도시·교통·산업', sub: `${areas.find(a=>a.name_ko?.includes('도시'))?.plan_ids?.length||4} Plans`, color: C.blue },
  ];
  const bw = 2.95, by = 3.9, bh = 0.65;
  areaBands.forEach((b, i) => {
    const bx = 0.35 + i * (bw + 0.08);
    sl.addShape(pres.shapes.RECTANGLE, { x: bx, y: by, w: bw, h: bh,
      fill: { color: b.color }, line: { color: b.color, width: 0 } });
    sl.addText(b.label, { x: bx, y: by + 0.06, w: bw, h: 0.3,
      fontSize: 14, bold: true, color: C.white, align: 'center', fontFace: 'Arial' });
    sl.addText(b.sub,   { x: bx, y: by + 0.36, w: bw, h: 0.22,
      fontSize: 11, color: C.white, align: 'center', fontFace: 'Arial' });
  });

  // URL 푸터
  sl.addText('hms4792.github.io/vietnam-infra-news', {
    x: 0.35, y: 5.3, w: 9.3, h: 0.25,
    fontSize: 9, color: '4A7FA5', fontFace: 'Arial'
  });
}

// ══════════════════════════════════════════════════════════════════════════
// Slide 2: 전체 KPI 대시보드 (3×4 그리드)
// ══════════════════════════════════════════════════════════════════════════
function addKpiDashSlide() {
  if (kpiDash.length === 0) return;
  const sl = pres.addSlide();
  sl.background = { color: C.white };

  // 헤더
  sl.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: W, h: 0.52,
    fill: { color: C.navy }, line: { color: C.navy, width: 0 } });
  sl.addText('전체 마스터플랜 KPI 목표 현황', {
    x: 0.3, y: 0.06, w: 7, h: 0.4,
    fontSize: 20, bold: true, color: C.white, fontFace: 'Arial'
  });
  sl.addText(`${Object.keys(plans).length}개 마스터플랜 · KPI ${kpiDash.length}개 · 2030 목표 기준`, {
    x: 7, y: 0.1, w: 2.8, h: 0.35,
    fontSize: 9, color: 'AADDFF', align: 'right', fontFace: 'Arial'
  });

  // KPI 카드 그리드 (3열)
  const cols = 3, cardW = 3.1, cardH = 0.9, gapX = 0.08, gapY = 0.08;
  const startX = 0.18, startY = 0.62;

  kpiDash.forEach((kpi, i) => {
    const col = i % cols, row = Math.floor(i / cols);
    const x = startX + col * (cardW + gapX);
    const y = startY + row * (cardH + gapY);
    const changed = kpi.changed;
    const borderColor = changed ? C.gold : C.grayL;

    sl.addShape(pres.shapes.RECTANGLE, { x, y, w: cardW, h: cardH,
      fill: { color: changed ? 'FFFDE7' : C.offWhite },
      line: { color: borderColor, width: changed ? 2 : 1 }
    });

    sl.addText(kpi.label, { x: x+0.08, y: y+0.05, w: cardW-0.16, h: 0.2,
      fontSize: 9, color: C.gray, fontFace: 'Arial' });

    // 목표값 (크게)
    const targetColor = changed ? C.gold : C.teal;
    sl.addText(String(kpi.target), { x: x+0.08, y: y+0.22, w: cardW*0.55, h: 0.36,
      fontSize: 18, bold: true, color: targetColor, fontFace: 'Arial' });
    sl.addText('목표', { x: x+0.08, y: y+0.58, w: cardW*0.5, h: 0.2,
      fontSize: 8, color: C.gray, fontFace: 'Arial' });

    // 현황값
    const currentFill = changed ? C.yellow : C.grayL;
    sl.addShape(pres.shapes.RECTANGLE, {
      x: x + cardW*0.58, y: y+0.22, w: cardW*0.38, h: 0.36,
      fill: { color: currentFill }, line: { color: currentFill, width: 0 }
    });
    sl.addText(String(kpi.current || '-'), {
      x: x + cardW*0.58, y: y+0.22, w: cardW*0.38, h: 0.36,
      fontSize: 11, bold: changed, color: changed ? C.yellowD : C.black,
      align: 'center', valign: 'middle', fontFace: 'Arial'
    });
    sl.addText('현황', { x: x + cardW*0.58, y: y+0.58, w: cardW*0.38, h: 0.2,
      fontSize: 8, color: C.gray, align: 'center', fontFace: 'Arial' });
  });

  // 하단 노트
  const noteY = startY + Math.ceil(kpiDash.length / cols) * (cardH + gapY) + 0.05;
  if (noteY < H - 0.15) {
    const hasChanges = kpiDash.filter(k => k.changed);
    if (hasChanges.length > 0) {
      const noteText = `★ 노란색 = 직전 주 대비 KPI 변동사항 (${hasChanges.map(k=>k.label).join(' · ')})`;
      sl.addText(noteText, { x: 0.18, y: noteY, w: W-0.36, h: 0.22,
        fontSize: 8.5, color: C.yellowD, fontFace: 'Arial', italic: true });
    }
  }
}

// ══════════════════════════════════════════════════════════════════════════
// Slide 3: 이번 주 KPI 변동사항
// ══════════════════════════════════════════════════════════════════════════
function addKpiChangesSlide() {
  if (kpiChanges.length === 0) return;
  const sl = pres.addSlide();
  sl.background = { color: C.white };

  sl.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: W, h: 0.52,
    fill: { color: C.navy }, line: { color: C.navy, width: 0 } });
  sl.addText('이번 주 핵심 KPI 변동사항', {
    x: 0.3, y: 0.06, w: 7, h: 0.4,
    fontSize: 20, bold: true, color: C.white, fontFace: 'Arial'
  });
  sl.addText('★ 노란색 항목 = 직전 주 대비 변동 확인', {
    x: 7, y: 0.12, w: 2.7, h: 0.3,
    fontSize: 9, color: C.yellow, align: 'right', fontFace: 'Arial'
  });

  let y = 0.65;
  kpiChanges.forEach((ch, i) => {
    const rowH = 0.85;
    // 좌측 plan_id 배지
    sl.addShape(pres.shapes.RECTANGLE, { x: 0.2, y, w: 1.6, h: 0.32,
      fill: { color: C.gold }, line: { color: C.gold, width: 0 } });
    sl.addText(ch.plan_id || '', { x: 0.2, y, w: 1.6, h: 0.32,
      fontSize: 9, bold: true, color: C.white, align: 'center', valign: 'middle', fontFace: 'Arial' });

    // 제목
    sl.addText(`★ ${ch.indicator || ''}`, { x: 2.0, y, w: 7.7, h: 0.32,
      fontSize: 13, bold: true, color: C.navy, fontFace: 'Arial' });

    // 변동 화살표 행
    const arrowY = y + 0.35;
    sl.addText(String(ch.from || ''), { x: 0.2, y: arrowY, w: 2.5, h: 0.3,
      fontSize: 18, bold: true, color: C.gray, fontFace: 'Arial' });
    sl.addText('→', { x: 2.7, y: arrowY, w: 0.5, h: 0.3,
      fontSize: 18, color: C.navy, align: 'center', fontFace: 'Arial' });
    sl.addText(String(ch.to || ''), { x: 3.2, y: arrowY, w: 3, h: 0.3,
      fontSize: 18, bold: true, color: C.teal, fontFace: 'Arial' });

    // 근거
    if (ch.reason) {
      sl.addText(ch.reason, { x: 0.2, y: arrowY + 0.32, w: W - 0.4, h: 0.2,
        fontSize: 9, color: C.gray, fontFace: 'Arial', italic: true });
    }

    // 구분선
    if (i < kpiChanges.length - 1) {
      sl.addShape(pres.shapes.LINE, { x: 0.2, y: y + rowH, w: W - 0.4, h: 0,
        line: { color: C.grayL, width: 1 } });
    }
    y += rowH;
    if (y > H - 0.3) return; // 슬라이드 넘침 방지
  });
}

// ══════════════════════════════════════════════════════════════════════════
// Slide 4: KPI 달성률 비교
// ══════════════════════════════════════════════════════════════════════════
function addKpiAchieveSlide() {
  if (kpiAchieve.length === 0) return;
  const sl = pres.addSlide();
  sl.background = { color: C.white };

  sl.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: W, h: 0.52,
    fill: { color: C.navy }, line: { color: C.navy, width: 0 } });
  sl.addText('KPI 달성률 현황 비교 (2025년 기준)', {
    x: 0.3, y: 0.08, w: 9, h: 0.4,
    fontSize: 20, bold: true, color: C.white, fontFace: 'Arial'
  });

  const barH = 0.42, barGap = 0.1, startY = 0.65;
  const barMaxW = 7.2, labelW = 2.2;

  kpiAchieve.forEach((item, i) => {
    const y = startY + i * (barH + barGap);
    const pct = Math.min(Math.max(item.current_pct || 0, 0), 100);
    const barFillW = (pct / 100) * barMaxW;
    const barColor = pct >= 80 ? C.env : pct >= 50 ? C.teal : C.gold;

    // 라벨
    sl.addText(item.label, { x: 0.2, y, w: labelW, h: barH,
      fontSize: 11, color: C.black, valign: 'middle', fontFace: 'Arial' });

    // 배경 바
    sl.addShape(pres.shapes.RECTANGLE, { x: labelW + 0.2, y: y + 0.08, w: barMaxW, h: barH - 0.16,
      fill: { color: C.grayL }, line: { color: C.grayL, width: 0 } });

    // 채워진 바
    if (barFillW > 0) {
      sl.addShape(pres.shapes.RECTANGLE, { x: labelW + 0.2, y: y + 0.08, w: barFillW, h: barH - 0.16,
        fill: { color: barColor }, line: { color: barColor, width: 0 } });
    }

    // 퍼센트 텍스트
    sl.addText(`${pct}% / 100%`, { x: labelW + 0.2 + barMaxW + 0.1, y, w: 1.5, h: barH,
      fontSize: 10, color: C.gray, valign: 'middle', fontFace: 'Arial' });
  });
}

// ══════════════════════════════════════════════════════════════════════════
// 영역 구분 슬라이드
// ══════════════════════════════════════════════════════════════════════════
function addAreaDividerSlide(area) {
  const sl = pres.addSlide();
  const areaColor = getAreaColor(area.name_ko || area.name_en || '');
  sl.background = { color: C.navy };

  // 좌측 컬러 바
  sl.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.25, h: H,
    fill: { color: areaColor }, line: { color: areaColor, width: 0 } });

  // 영역명
  sl.addText(area.name_ko || area.name_en || '', {
    x: 0.5, y: 0.8, w: 9, h: 1.1,
    fontSize: 48, bold: true, color: C.white, fontFace: 'Arial Black'
  });
  sl.addText(area.name_en || '', {
    x: 0.5, y: 1.9, w: 9, h: 0.5,
    fontSize: 22, color: areaColor, fontFace: 'Arial'
  });

  // 포함 플랜 목록
  sl.addText('포함 마스터플랜', { x: 0.5, y: 2.65, w: 3, h: 0.3,
    fontSize: 11, color: C.gray, fontFace: 'Arial' });

  const planIds = area.plan_ids || [];
  planIds.forEach((pid, i) => {
    const pdata = plans[pid];
    if (!pdata) return;
    const y = 3.0 + i * 0.52;
    sl.addShape(pres.shapes.RECTANGLE, { x: 0.5, y, w: 9, h: 0.42,
      fill: { color: '132038' }, line: { color: areaColor, width: 1 } });
    sl.addText(pid, { x: 0.6, y: y + 0.04, w: 1.8, h: 0.32,
      fontSize: 9, bold: true, color: areaColor, valign: 'middle', fontFace: 'Arial' });
    sl.addText(pdata.plan_name_ko || pid, { x: 2.5, y: y + 0.04, w: 6.9, h: 0.32,
      fontSize: 10, color: C.white, valign: 'middle', fontFace: 'Arial' });
  });
}

// ══════════════════════════════════════════════════════════════════════════
// 플랜 상세 슬라이드 (Layer1 완전 적용)
// ══════════════════════════════════════════════════════════════════════════
/**
 * addPlanSlide()
 * ★ Layer1 핵심 함수 — 절대 삭제/수정 금지
 *   - description_ko : 사업 개요 (좌측 패널)
 *   - kpi_targets    : KPI 목표 및 현황 (좌측 하단)
 *   - key_projects   : 주요 프로젝트 목록 (우측 패널, 최대 8개)
 */
function addPlanSlide(planId, pdata) {
  const sl = pres.addSlide();
  sl.background = { color: C.white };
  const sectorColor = getSectorColor(pdata.sector || '');

  // ── 상단 헤더 ────────────────────────────────────────────────────────
  // Plan ID 배지
  sl.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 1.9, h: 0.42,
    fill: { color: sectorColor }, line: { color: sectorColor, width: 0 } });
  sl.addText(planId, { x: 0, y: 0, w: 1.9, h: 0.42,
    fontSize: 10, bold: true, color: C.white, align: 'center', valign: 'middle', fontFace: 'Arial' });

  // 플랜명
  sl.addText(pdata.plan_name_ko || planId, {
    x: 2.0, y: 0.02, w: 7.8, h: 0.44,
    fontSize: 18, bold: true, color: C.navy, valign: 'middle', fontFace: 'Arial'
  });

  // Decision 서브타이틀
  sl.addText(pdata.decision || '', {
    x: 2.0, y: 0.44, w: 7.8, h: 0.22,
    fontSize: 9, color: C.gray, fontFace: 'Arial'
  });

  // 헤더 구분선
  sl.addShape(pres.shapes.LINE, { x: 0, y: 0.68, w: W, h: 0,
    line: { color: C.navy, width: 1.5 } });

  // ── 좌측 패널 (사업개요 + KPI) ────────────────────────────────────
  const LEFT_W = 5.7, RIGHT_X = 5.95, RIGHT_W = 3.9;
  const CONTENT_Y = 0.75;

  // ① 사업 개요 헤더 (Layer1 — 절대 유지)
  sl.addShape(pres.shapes.RECTANGLE, { x: 0, y: CONTENT_Y, w: LEFT_W, h: 0.28,
    fill: { color: C.green }, line: { color: C.green, width: 0 } });
  sl.addText('■ 사업 개요', { x: 0.08, y: CONTENT_Y, w: LEFT_W - 0.16, h: 0.28,
    fontSize: 11, bold: true, color: C.white, valign: 'middle', fontFace: 'Arial' });

  // ① 사업 개요 내용 (Layer1 — 절대 유지)
  const desc = pdata.description_ko || '(사업 개요 미등록 — knowledge_index.json 업데이트 필요)';
  const descLines = desc.split('\n').filter(Boolean).slice(0, 5).join(' ');
  const descTrimmed = descLines.length > 280 ? descLines.substring(0, 280) + '...' : descLines;
  sl.addShape(pres.shapes.RECTANGLE, { x: 0, y: CONTENT_Y + 0.28, w: LEFT_W, h: 1.55,
    fill: { color: C.offWhite }, line: { color: C.grayL, width: 1 } });
  sl.addText(descTrimmed, { x: 0.1, y: CONTENT_Y + 0.32, w: LEFT_W - 0.2, h: 1.48,
    fontSize: 10, color: C.black, fontFace: 'Arial', valign: 'top',
    align: 'justify', wrap: true
  });

  // ② KPI 목표 및 현황 헤더 (Layer1 — 절대 유지)
  const KPI_Y = CONTENT_Y + 1.85;
  sl.addShape(pres.shapes.RECTANGLE, { x: 0, y: KPI_Y, w: LEFT_W, h: 0.28,
    fill: { color: C.orange }, line: { color: C.orange, width: 0 } });
  sl.addText('■ KPI 목표 및 현황', { x: 0.08, y: KPI_Y, w: LEFT_W - 0.16, h: 0.28,
    fontSize: 11, bold: true, color: C.white, valign: 'middle', fontFace: 'Arial' });

  // ② KPI 카드들 (Layer1 — 절대 유지)
  const kpis = pdata.kpi_targets || [];
  const kpiCardW = (LEFT_W - 0.12) / 3, kpiCardH = 0.82;
  kpis.slice(0, 3).forEach((kpi, i) => {
    const kx = i * (kpiCardW + 0.06);
    const ky = KPI_Y + 0.3;
    const isChanged = kpi.changed;
    sl.addShape(pres.shapes.RECTANGLE, { x: kx, y: ky, w: kpiCardW, h: kpiCardH,
      fill: { color: isChanged ? 'FFFDE7' : C.white },
      line: { color: isChanged ? C.gold : C.grayL, width: isChanged ? 2 : 1 }
    });
    sl.addText(kpi.label || kpi.indicator || '', { x: kx + 0.06, y: ky + 0.04, w: kpiCardW - 0.12, h: 0.22,
      fontSize: 9, color: C.gray, fontFace: 'Arial', wrap: true });
    sl.addText(String(kpi.target || ''), { x: kx + 0.06, y: ky + 0.24, w: kpiCardW - 0.12, h: 0.28,
      fontSize: 16, bold: true, color: isChanged ? C.gold : sectorColor, fontFace: 'Arial' });
    const currentBg = isChanged ? C.yellow : C.grayL;
    sl.addShape(pres.shapes.RECTANGLE, { x: kx + 0.06, y: ky + 0.53, w: kpiCardW - 0.12, h: 0.22,
      fill: { color: currentBg }, line: { color: currentBg, width: 0 } });
    sl.addText(String(kpi.current || '-'), { x: kx + 0.06, y: ky + 0.53, w: kpiCardW - 0.12, h: 0.22,
      fontSize: 9, color: isChanged ? C.yellowD : C.black, align: 'center', valign: 'middle', fontFace: 'Arial' });
  });

  // KPI 별표 (변동 있을 때)
  if (kpis.some(k => k.changed)) {
    sl.addText('★ KPI 변동', { x: 0, y: KPI_Y + 0.3 + kpiCardH + 0.03, w: LEFT_W, h: 0.18,
      fontSize: 8, color: C.yellowD, italic: true, fontFace: 'Arial' });
  }

  // ── 우측 패널 (주요 프로젝트 목록) — Layer1 ────────────────────────
  // 우측 헤더
  sl.addShape(pres.shapes.RECTANGLE, { x: RIGHT_X, y: CONTENT_Y, w: RIGHT_W, h: 0.28,
    fill: { color: C.navy }, line: { color: C.navy, width: 0 } });
  sl.addText('■ 주요 프로젝트 목록', { x: RIGHT_X + 0.08, y: CONTENT_Y, w: RIGHT_W - 0.16, h: 0.28,
    fontSize: 11, bold: true, color: C.white, valign: 'middle', fontFace: 'Arial' });

  // 프로젝트 카드 (최대 8개, Layer1 — 절대 유지)
  const projects = pdata.key_projects || [];
  const displayProjs = projects.slice(0, 8);
  const projCardH = (H - CONTENT_Y - 0.28 - 0.32) / Math.max(displayProjs.length, 1);
  const maxProjH = 0.68, minProjH = 0.35;
  const actualProjH = Math.min(maxProjH, Math.max(minProjH, projCardH));

  displayProjs.forEach((proj, i) => {
    const py = CONTENT_Y + 0.28 + i * (actualProjH + 0.04);
    if (py + actualProjH > H - 0.25) return;

    sl.addShape(pres.shapes.RECTANGLE, { x: RIGHT_X, y: py, w: RIGHT_W, h: actualProjH,
      fill: { color: i % 2 === 0 ? C.offWhite : C.white },
      line: { color: C.grayL, width: 1 }
    });

    // 프로젝트명
    sl.addText(proj.name_ko || proj.name || '', {
      x: RIGHT_X + 0.08, y: py + 0.03, w: RIGHT_W - 0.16, h: 0.24,
      fontSize: 10, bold: true, color: C.navy, fontFace: 'Arial', wrap: true
    });

    // 위치 | 규모
    const locCap = [proj.location || proj.province || '', proj.capacity || proj.size || '']
      .filter(Boolean).join(' | ');
    sl.addText(locCap, {
      x: RIGHT_X + 0.08, y: py + 0.26, w: RIGHT_W - 0.16, h: 0.18,
      fontSize: 9, color: C.gray, fontFace: 'Arial'
    });

    // 비고 (있을 때, actualProjH 충분할 때만)
    if (proj.note && actualProjH >= 0.55) {
      const noteText = proj.note.length > 50 ? proj.note.substring(0, 50) + '…' : proj.note;
      sl.addText(noteText, {
        x: RIGHT_X + 0.08, y: py + 0.42, w: RIGHT_W - 0.16, h: 0.18,
        fontSize: 8, color: getSectorColor(pdata.sector || ''), italic: true, fontFace: 'Arial'
      });
    }
  });

  // 추가 프로젝트 수 표시
  const extra = projects.length - displayProjs.length;
  if (extra > 0) {
    sl.addText(`+ ${extra}개 추가 프로젝트 (상세 보고서 참조)`, {
      x: RIGHT_X, y: H - 0.28, w: RIGHT_W, h: 0.22,
      fontSize: 9, color: C.gray, italic: true, align: 'center', fontFace: 'Arial'
    });
  }

  // ── 푸터 ─────────────────────────────────────────────────────────────
  sl.addShape(pres.shapes.RECTANGLE, { x: 0, y: H - 0.25, w: W, h: 0.25,
    fill: { color: C.grayL }, line: { color: C.grayL, width: 0 } });
  const footerParts = [
    pdata.sector || '',
    pdata.area || '',
    pdata.decision || ''
  ].filter(Boolean).join('  |  ');
  sl.addText(footerParts, { x: 0.15, y: H - 0.24, w: W - 0.3, h: 0.22,
    fontSize: 8, color: C.gray, fontFace: 'Arial' });
}

// ══════════════════════════════════════════════════════════════════════════
// 프로젝트 전체 목록 슬라이드 (8개 초과 시)
// ══════════════════════════════════════════════════════════════════════════
function addProjectTableSlide(planId, pdata) {
  const projects = pdata.key_projects || [];
  if (projects.length <= 8) return;

  const sl = pres.addSlide();
  sl.background = { color: C.white };
  const sectorColor = getSectorColor(pdata.sector || '');

  // 헤더
  sl.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: W, h: 0.45,
    fill: { color: C.navy }, line: { color: C.navy, width: 0 } });
  sl.addText(`${planId} — 프로젝트 전체 목록 (${projects.length}개)`, {
    x: 0.2, y: 0.05, w: W - 0.4, h: 0.38,
    fontSize: 15, bold: true, color: C.white, fontFace: 'Arial'
  });

  // 테이블 헤더
  const cols = ['프로젝트명', '위치', '규모/용량', '비고'];
  const colW  = [3.5, 1.5, 2.0, 2.8];
  let tx = 0.1, ty = 0.5;
  cols.forEach((col, i) => {
    sl.addShape(pres.shapes.RECTANGLE, { x: tx, y: ty, w: colW[i], h: 0.3,
      fill: { color: sectorColor }, line: { color: sectorColor, width: 0 } });
    sl.addText(col, { x: tx + 0.05, y: ty, w: colW[i] - 0.1, h: 0.3,
      fontSize: 10, bold: true, color: C.white, valign: 'middle', fontFace: 'Arial' });
    tx += colW[i];
  });

  // 데이터 행
  projects.forEach((proj, i) => {
    const ry = ty + 0.3 + i * 0.38;
    if (ry + 0.38 > H - 0.2) return;
    tx = 0.1;
    const rowFill = i % 2 === 0 ? C.offWhite : C.white;
    const cells = [
      proj.name_ko || proj.name || '',
      proj.location || proj.province || '',
      proj.capacity || proj.size || '',
      proj.note || ''
    ];
    cells.forEach((cell, j) => {
      sl.addShape(pres.shapes.RECTANGLE, { x: tx, y: ry, w: colW[j], h: 0.36,
        fill: { color: rowFill }, line: { color: C.grayL, width: 1 } });
      sl.addText(cell.length > 50 ? cell.substring(0, 50) + '…' : cell, {
        x: tx + 0.05, y: ry, w: colW[j] - 0.1, h: 0.36,
        fontSize: 9, color: C.black, valign: 'middle', fontFace: 'Arial', wrap: true
      });
      tx += colW[j];
    });
  });
}

// ══════════════════════════════════════════════════════════════════════════
// Closing 슬라이드
// ══════════════════════════════════════════════════════════════════════════
function addClosingSlide() {
  const sl = pres.addSlide();
  sl.background = { color: C.navy };

  sl.addShape(pres.shapes.RECTANGLE, { x: 0, y: 0, w: 0.2, h: H,
    fill: { color: C.teal }, line: { color: C.teal, width: 0 } });

  sl.addText('Vietnam Infrastructure MI', {
    x: 0.4, y: 0.8, w: 9.4, h: 0.8,
    fontSize: 36, bold: true, color: C.white, fontFace: 'Arial Black'
  });
  sl.addText('Automated Report Pipeline · SA-8', {
    x: 0.4, y: 1.6, w: 9.4, h: 0.4,
    fontSize: 18, color: C.teal, fontFace: 'Arial'
  });

  const planCnt = Object.keys(plans).length;
  const kpiCnt  = Object.values(plans).reduce((acc, p) => acc + (p.kpi_targets||[]).length, 0);
  const projCnt = Object.values(plans).reduce((acc, p) => acc + (p.key_projects||[]).length, 0);

  sl.addText(`${planCnt}개 마스터플랜 · KPI ${kpiCnt}개 · 프로젝트 ${projCnt}개 — knowledge_index 기반`, {
    x: 0.4, y: 2.2, w: 9.4, h: 0.3,
    fontSize: 12, color: 'AADDFF', fontFace: 'Arial'
  });
  sl.addText('매주 토요일 KST 22:00 자동 생성 — Claude Haiku AI 기사 분석 연계', {
    x: 0.4, y: 2.55, w: 9.4, h: 0.3,
    fontSize: 12, color: 'AADDFF', fontFace: 'Arial'
  });
  sl.addText('Layer 1 (사업 개요 고정) + Layer 2 (AI 동적 분석) 이중 레이어 구조', {
    x: 0.4, y: 2.9, w: 9.4, h: 0.3,
    fontSize: 12, color: 'AADDFF', fontFace: 'Arial'
  });
  sl.addText('★ 노란색 하이라이트 = KPI 변동 자동 감지 · 이메일 자동 첨부 발송', {
    x: 0.4, y: 3.25, w: 9.4, h: 0.3,
    fontSize: 12, color: C.yellow, fontFace: 'Arial'
  });
  sl.addText(`대시보드: hms4792.github.io/vietnam-infra-news/`, {
    x: 0.4, y: 4.1, w: 9.4, h: 0.3,
    fontSize: 13, color: C.teal, fontFace: 'Arial'
  });
}

// ══════════════════════════════════════════════════════════════════════════
// 메인 빌드 실행
// ══════════════════════════════════════════════════════════════════════════
console.log('[build_mi_ppt.js v4.0] 슬라이드 생성 시작...');

addCoverSlide();
addKpiDashSlide();
addKpiChangesSlide();
addKpiAchieveSlide();

// 영역별 → 플랜별 순서로 생성
if (areas.length > 0) {
  // areas 배열이 있으면 영역 순서 따름
  areas.forEach(area => {
    addAreaDividerSlide(area);
    (area.plan_ids || []).forEach(pid => {
      const pdata = plans[pid];
      if (!pdata) return;
      addPlanSlide(pid, pdata);
      addProjectTableSlide(pid, pdata);
    });
  });
} else {
  // areas 배열 없으면 plans 순서 그대로
  Object.entries(plans).forEach(([pid, pdata]) => {
    addPlanSlide(pid, pdata);
    addProjectTableSlide(pid, pdata);
  });
}

addClosingSlide();

pres.writeFile({ fileName: outPath })
  .then(() => {
    const bytes = fs.statSync(outPath).size;
    console.log(`[build_mi_ppt.js v4.0] ✅ 완료`);
    console.log(`   출력: ${outPath}`);
    console.log(`   크기: ${(bytes/1024).toFixed(0)} KB`);
    console.log(`   슬라이드 수: 표지+KPI(${kpiDash.length>0?3:0})+영역(${areas.length})+플랜(${Object.keys(plans).length})+클로징`);
  })
  .catch(err => {
    console.error('[build_mi_ppt.js v4.0] 오류:', err.message);
    process.exit(1);
  });
