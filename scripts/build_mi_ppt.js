/**
 * build_mi_ppt.js  ── SA-8 PPT 빌더 v3.0
 * =========================================================
 * 경영진 보고용 전문 MI 발표 자료 (PptxGenJS 기반)
 *
 * v3.0 (2026-05-09) 핵심:
 *   - 21개 플랜 전체 포함 (기사 없는 플랜도 현황 슬라이드 생성)
 *   - 신규 기사 노란 배지, 기존 기사 구분 표시
 *   - 슬라이드 구조:
 *       1. 표지 (타이틀 + 핵심 통계)
 *       2. 목차 (영역별)
 *       3. Executive Summary
 *       4. KPI 대시보드 (영역별 집계)
 *       5~N. 플랜별 슬라이드 (각 1장, 기사 많으면 2장)
 *       N+1. 클로징
 *
 * 데이터 소스: SA8_DATA_FILE 환경변수 (generate_mi_report.py 페이로드)
 *
 * 실행: node scripts/build_mi_ppt.js
 * 출력: docs/VN_Infra_MI_Weekly_Report_YYYYMMDD.pptx
 */

'use strict';

const pptxgen = require('pptxgenjs');
const fs      = require('fs');
const path    = require('path');

// ══════════════════════════════════════════════════════════════════════════
//  데이터 로드
// ══════════════════════════════════════════════════════════════════════════
const BASE_DIR  = path.resolve(__dirname, '..');
const DATA_FILE = process.env.SA8_DATA_FILE
  || path.join(BASE_DIR, 'data', 'agent_output', 'sa8_report_payload.json');
const OUT_DIR   = path.join(BASE_DIR, 'docs');

if (!fs.existsSync(DATA_FILE)) {
  console.error('[PPT] 데이터 파일 없음:', DATA_FILE);
  process.exit(1);
}
const payload = JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));

const today     = payload.report_date || new Date().toISOString().slice(0, 10);
const week      = payload.report_week || '';
const totalArts = payload.total_articles || 0;
const newCount  = payload.new_articles_count || 0;
const planSecs  = payload.plan_sections || [];
const execSumm  = payload.executive_summary || '';

const dateTag   = today.replace(/-/g, '');
const outPath   = process.env.SA8_OUTPUT_PATH
  || path.join(OUT_DIR, `VN_Infra_MI_Weekly_Report_${dateTag}.pptx`);

if (!fs.existsSync(path.dirname(outPath))) {
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
}

console.log(`[build_mi_ppt.js v3.0] 데이터 로드`);
console.log(`  BASE_DIR: ${BASE_DIR}`);
console.log(`  [OK] 로드: ${path.basename(DATA_FILE)}`);
console.log(`  플랜 ${planSecs.length}개 로드 완료`);

// ══════════════════════════════════════════════════════════════════════════
//  디자인 시스템
// ══════════════════════════════════════════════════════════════════════════

// 색상 (hex, # 없이)
const C = {
  navy:    '0C2340',
  navyMid: '1B3A5C',
  teal:    '0D6E6E',
  tealL:   'E0F0EF',
  blue:    '1B4F8A',
  blueL:   'E3EDF8',
  purple:  '4A3B8C',
  purpleL: 'EDE9F8',
  orange:  'D4820A',
  green:   '2D6A4F',
  greenL:  'E8F5E9',
  amber:   '92400E',
  amberL:  'FEF3C7',
  newYellow:'F59E0B',
  newYellowL:'FFF9C4',
  grayDark:'374151',
  grayMid: '6B7280',
  grayLight:'F3F4F6',
  white:   'FFFFFF',
  black:   '111827',
  silver:  '9CA3AF',
};

// 영역별 테마
const AREA_THEME = {
  'Environment':    { color: C.teal,   light: C.tealL,   icon: 'ENV' },
  'Energy Develop.':{ color: C.blue,   light: C.blueL,   icon: 'PWR' },
  'Urban Develop.': { color: C.purple, light: C.purpleL, icon: 'URB' },
  'default':        { color: C.navy,   light: 'E8EEF4',  icon: '---' },
};

// 진행단계
const STAGE = {
  PLANNING:     { ko: '계획·승인', bar: C.blue,   pct: 0.15 },
  BIDDING:      { ko: '입찰·계약', bar: C.purple, pct: 0.35 },
  CONSTRUCTION: { ko: '건설·시공', bar: C.orange, pct: 0.60 },
  COMPLETION:   { ko: '준공·완료', bar: C.green,  pct: 0.90 },
  OPERATION:    { ko: '운영·확장', bar: C.teal,   pct: 1.00 },
  UNKNOWN:      { ko: '미확정',   bar: C.grayMid,pct: 0.00 },
};

// 슬라이드 규격 (LAYOUT_16x9 = 10" × 5.625")
const W = 10, H = 5.625;
const MARGIN = 0.35;

// 그림자 (공통)
const mkShadow = () => ({ type: 'outer', color: '000000', opacity: 0.13, blur: 6, offset: 2, angle: 135 });

// 안전 문자열
const s = (v, fb) => {
  if (!v && v !== 0) return fb !== undefined ? fb : '';
  return String(v).trim() || (fb !== undefined ? fb : '');
};

// 줄임
const ellipsis = (str, max) => {
  const t = s(str, '');
  return t.length > max ? t.slice(0, max - 1) + '…' : t;
};

// ══════════════════════════════════════════════════════════════════════════
//  슬라이드 공통 헬퍼
// ══════════════════════════════════════════════════════════════════════════

/** 헤더 바 (슬라이드 상단 네이비 바 + 제목) */
function addHeader(slide, title, subtitle, accentColor) {
  const ac = accentColor || C.navy;
  // 상단 좁은 네이비 스트라이프
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: W, h: 0.06,
    fill: { color: ac }, line: { color: ac }
  });
  // 제목 영역
  slide.addText(s(title, ''), {
    x: MARGIN, y: 0.12, w: W - MARGIN * 2 - 1.5, h: 0.46,
    fontSize: 18, bold: true, fontFace: 'Calibri',
    color: C.navy, valign: 'middle', margin: 0,
  });
  if (subtitle) {
    slide.addText(s(subtitle, ''), {
      x: MARGIN, y: 0.58, w: W - MARGIN * 2, h: 0.22,
      fontSize: 9, color: C.grayMid, fontFace: 'Calibri', margin: 0,
    });
  }
  // 날짜 우상단
  slide.addText(today, {
    x: W - 1.8, y: 0.12, w: 1.45, h: 0.28,
    fontSize: 8, color: C.silver, fontFace: 'Calibri',
    align: 'right', margin: 0,
  });
}

/** 하단 푸터 */
function addFooter(slide, pageNote) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: H - 0.22, w: W, h: 0.22,
    fill: { color: C.navy }, line: { color: C.navy }
  });
  slide.addText('Vietnam Infrastructure MI Report  |  CONFIDENTIAL', {
    x: MARGIN, y: H - 0.20, w: 5, h: 0.18,
    fontSize: 7, color: 'AABBCC', fontFace: 'Calibri', margin: 0,
  });
  if (pageNote) {
    slide.addText(s(pageNote, ''), {
      x: W - 2.5, y: H - 0.20, w: 2.15, h: 0.18,
      fontSize: 7, color: 'AABBCC', align: 'right', fontFace: 'Calibri', margin: 0,
    });
  }
}

/** 컬러 카드 박스 */
function addCard(slide, x, y, w, h, bgColor, opts) {
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h,
    fill: { color: bgColor || C.grayLight },
    line: { color: opts && opts.border ? opts.border : bgColor || C.grayLight, pt: 0.5 },
    shadow: opts && opts.shadow ? mkShadow() : undefined,
  });
}

/** 진행단계 프로그레스 바 */
function addProgressBar(slide, x, y, w, stage) {
  const info = STAGE[stage] || STAGE.UNKNOWN;
  const trackH = 0.09;
  // 트랙
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h: trackH,
    fill: { color: 'E5E7EB' }, line: { color: 'D1D5DB', pt: 0.3 }
  });
  // 채움
  const fillW = Math.max(w * info.pct, info.pct > 0 ? 0.05 : 0);
  if (fillW > 0) {
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y, w: fillW, h: trackH,
      fill: { color: info.bar }, line: { color: info.bar, pt: 0 }
    });
  }
  // 레이블
  slide.addText(info.ko, {
    x: x + w + 0.05, y: y - 0.01, w: 1.0, h: trackH + 0.02,
    fontSize: 7.5, color: info.bar, bold: true, fontFace: 'Calibri',
    valign: 'middle', margin: 0,
  });
}

/** KPI 행 (지표명 + 현황 + 목표) */
function addKpiRow(slide, x, y, w, kpi, isEven) {
  const rowH = 0.235;
  const c1 = w * 0.44, c2 = w * 0.28, c3 = w * 0.28;
  // 배경
  if (isEven) {
    slide.addShape(pres.shapes.RECTANGLE, {
      x, y, w, h: rowH,
      fill: { color: 'F9FAFB' }, line: { color: 'E5E7EB', pt: 0.3 }
    });
  }
  slide.addText(ellipsis(kpi.indicator, 28), {
    x: x + 0.04, y, w: c1 - 0.04, h: rowH,
    fontSize: 8, color: C.grayDark, fontFace: 'Calibri', valign: 'middle', margin: 0,
  });
  slide.addText(ellipsis(kpi.current || '수집 중', 22), {
    x: x + c1, y, w: c2, h: rowH,
    fontSize: 8, color: C.grayMid, fontFace: 'Calibri', valign: 'middle', align: 'center', margin: 0,
  });
  slide.addText(ellipsis(kpi.target_2030 || kpi.target || '-', 22), {
    x: x + c1 + c2, y, w: c3, h: rowH,
    fontSize: 8.5, bold: true, color: C.teal, fontFace: 'Calibri', valign: 'middle', align: 'center', margin: 0,
  });
}

/** 기사 행 (신규=노란 배지, 기존=회색) */
function addArticleRow(slide, x, y, w, art, rowH) {
  const isNew = art.is_new === true;
  const isHigh = (art.ctx_grade || '') === 'HIGH';
  const bgColor = isNew ? C.newYellowL : C.white;
  const badgeColor = isNew ? C.newYellow : (isHigh ? C.blue : C.silver);
  const badgeTxt = isNew ? (isHigh ? 'NEW·H' : 'NEW') : (isHigh ? 'HIGH' : 'MED');
  const titleColor = isNew ? C.black : C.grayDark;

  // 배경
  slide.addShape(pres.shapes.RECTANGLE, {
    x, y, w, h: rowH,
    fill: { color: bgColor },
    line: { color: isNew ? 'FCD34D' : 'E5E7EB', pt: 0.4 }
  });

  const badgeW = 0.42;
  const dateW  = 0.65;
  const srcW   = 0.85;
  const titleW = w - badgeW - dateW - srcW - 0.08;

  // 배지
  slide.addShape(pres.shapes.RECTANGLE, {
    x: x + 0.02, y: y + 0.035, w: badgeW - 0.04, h: rowH - 0.07,
    fill: { color: badgeColor }, line: { color: badgeColor, pt: 0 }
  });
  slide.addText(badgeTxt, {
    x: x + 0.02, y: y + 0.035, w: badgeW - 0.04, h: rowH - 0.07,
    fontSize: 6.5, bold: true, color: C.white, fontFace: 'Calibri',
    align: 'center', valign: 'middle', margin: 0,
  });

  // 날짜
  slide.addText(s(art.date || '', '').slice(5), {
    x: x + badgeW, y, w: dateW, h: rowH,
    fontSize: 7, color: C.grayMid, fontFace: 'Calibri',
    valign: 'middle', align: 'center', margin: 0,
  });

  // 출처
  slide.addText(ellipsis(art.source || '', 12), {
    x: x + badgeW + dateW, y, w: srcW, h: rowH,
    fontSize: 7, color: C.grayMid, fontFace: 'Calibri',
    valign: 'middle', margin: 0,
  });

  // 제목
  slide.addText(ellipsis(art.title_ko || art.title_en || '', 42), {
    x: x + badgeW + dateW + srcW, y, w: titleW, h: rowH,
    fontSize: 7.5, bold: isNew, color: titleColor, fontFace: 'Calibri',
    valign: 'middle', margin: 0,
  });
}

// ══════════════════════════════════════════════════════════════════════════
//  1. 표지 슬라이드
// ══════════════════════════════════════════════════════════════════════════
function buildCoverSlide() {
  const slide = pres.addSlide();
  slide.background = { color: C.navy };

  // 왼쪽 밝은 세로 라인
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.06, h: H,
    fill: { color: C.teal }, line: { color: C.teal }
  });

  // 메인 타이틀
  slide.addText('VIETNAM INFRASTRUCTURE', {
    x: 0.5, y: 1.05, w: 9, h: 0.75,
    fontSize: 38, bold: true, fontFace: 'Calibri', color: C.white,
    charSpacing: 3,
  });
  slide.addText('MARKET INTELLIGENCE REPORT', {
    x: 0.5, y: 1.78, w: 9, h: 0.45,
    fontSize: 22, bold: false, fontFace: 'Calibri', color: '7EB8D4',
    charSpacing: 5,
  });
  slide.addText('베트남 인프라 시장 분석 주간 보고서', {
    x: 0.5, y: 2.22, w: 9, h: 0.38,
    fontSize: 15, fontFace: 'Calibri', color: 'B0CFDF',
  });

  // 구분선
  slide.addShape(pres.shapes.LINE, {
    x: 0.5, y: 2.68, w: 9, h: 0,
    line: { color: '2E6A9A', width: 1.2, dashType: 'dash' }
  });

  // 메타 정보 카드 (3개)
  const cards = [
    { label: '발행일', value: today },
    { label: '보고 기간', value: week },
    { label: `수집 기사 (신규 ${newCount}건)`, value: `${totalArts}건` },
  ];
  const cw = 2.8, cy = 3.0, ch = 0.85, gap = 0.22;
  cards.forEach((c, i) => {
    const cx = 0.5 + i * (cw + gap);
    slide.addShape(pres.shapes.RECTANGLE, {
      x: cx, y: cy, w: cw, h: ch,
      fill: { color: C.navyMid }, line: { color: '2E6A9A', pt: 0.8 },
    });
    slide.addText(c.label, {
      x: cx + 0.12, y: cy + 0.06, w: cw - 0.24, h: 0.22,
      fontSize: 8, color: '7EB8D4', fontFace: 'Calibri', margin: 0,
    });
    slide.addText(c.value, {
      x: cx + 0.12, y: cy + 0.26, w: cw - 0.24, h: 0.48,
      fontSize: 18, bold: true, color: C.white, fontFace: 'Calibri',
      valign: 'middle', margin: 0,
    });
  });

  // 신규 기사 배너
  if (newCount > 0) {
    slide.addShape(pres.shapes.RECTANGLE, {
      x: 0.5, y: 4.05, w: 9, h: 0.30,
      fill: { color: 'FFF9C4' }, line: { color: 'FCD34D', pt: 0.8 }
    });
    slide.addText(`★ 이번 주 신규 기사 ${newCount}건 — 슬라이드 내 노란색 배지로 표시  /  기존 기사는 회색 배지`, {
      x: 0.5, y: 4.05, w: 9, h: 0.30,
      fontSize: 9, bold: true, color: C.amber, fontFace: 'Calibri',
      align: 'center', valign: 'middle', margin: 0,
    });
  }

  // 하단 기밀 표시
  slide.addText('CONFIDENTIAL  —  내부 참고용  —  SA-8 자동 생성 (Claude Haiku)', {
    x: 0, y: H - 0.28, w: W, h: 0.28,
    fontSize: 7.5, color: '4A7B9D', fontFace: 'Calibri',
    align: 'center', valign: 'middle', margin: 0,
  });

  console.log('  ✅ 표지');
}

// ══════════════════════════════════════════════════════════════════════════
//  2. 목차 슬라이드
// ══════════════════════════════════════════════════════════════════════════
function buildTocSlide() {
  const slide = pres.addSlide();
  slide.background = { color: C.white };
  addHeader(slide, '목  차', `분석 기간: ${week}  |  전체 ${planSecs.length}개 마스터플랜`, C.navy);
  addFooter(slide, 'Table of Contents');

  const areaGroups = {};
  planSecs.forEach(sec => {
    const a = s(sec.area, 'default');
    if (!areaGroups[a]) areaGroups[a] = [];
    areaGroups[a].push(sec);
  });

  const areas = ['Environment', 'Energy Develop.', 'Urban Develop.'];
  const colW = (W - MARGIN * 2 - 0.3) / 3;
  const startY = 0.90;

  areas.forEach((area, col) => {
    const theme = AREA_THEME[area] || AREA_THEME.default;
    const secs  = areaGroups[area] || [];
    const cx = MARGIN + col * (colW + 0.15);

    // 영역 헤더
    slide.addShape(pres.shapes.RECTANGLE, {
      x: cx, y: startY, w: colW, h: 0.34,
      fill: { color: theme.color }, line: { color: theme.color }
    });
    slide.addText(area, {
      x: cx, y: startY, w: colW, h: 0.34,
      fontSize: 10, bold: true, color: C.white, fontFace: 'Calibri',
      align: 'center', valign: 'middle', margin: 0,
    });

    // 플랜 목록
    secs.forEach((sec, i) => {
      const ry = startY + 0.34 + i * 0.32;
      const isNew = (sec.new_count || 0) > 0;
      // 배경
      slide.addShape(pres.shapes.RECTANGLE, {
        x: cx, y: ry, w: colW, h: 0.30,
        fill: { color: i % 2 === 0 ? theme.light : C.white },
        line: { color: 'E5E7EB', pt: 0.3 }
      });
      // 플랜 ID
      slide.addText(s(sec.plan_id, ''), {
        x: cx + 0.06, y: ry, w: 1.5, h: 0.30,
        fontSize: 6.5, bold: true, color: theme.color, fontFace: 'Calibri',
        valign: 'middle', margin: 0,
      });
      // 신규 배지
      if (isNew) {
        slide.addShape(pres.shapes.RECTANGLE, {
          x: cx + colW - 0.42, y: ry + 0.06, w: 0.35, h: 0.18,
          fill: { color: C.newYellow }, line: { color: C.newYellow, pt: 0 }
        });
        slide.addText('★NEW', {
          x: cx + colW - 0.42, y: ry + 0.06, w: 0.35, h: 0.18,
          fontSize: 5.5, bold: true, color: C.white, fontFace: 'Calibri',
          align: 'center', valign: 'middle', margin: 0,
        });
      }
      // 제목
      slide.addText(ellipsis(sec.title_ko || '', 22), {
        x: cx + 0.06, y: ry + 0.14, w: colW - 0.5, h: 0.14,
        fontSize: 6, color: C.grayDark, fontFace: 'Calibri',
        valign: 'top', margin: 0,
      });
    });
  });

  console.log('  ✅ 목차');
}

// ══════════════════════════════════════════════════════════════════════════
//  3. Executive Summary 슬라이드
// ══════════════════════════════════════════════════════════════════════════
function buildExecSummarySlide() {
  const slide = pres.addSlide();
  slide.background = { color: C.white };
  addHeader(slide, 'Executive Summary', '이번 주 시장 종합 분석', C.navy);
  addFooter(slide, 'Executive Summary');

  const isNew = payload.exec_summary_is_new || false;
  const badgeTxt = isNew ? `★ AI 신규 분석  |  신규 기사 ${newCount}건` : '기존 분석 유지';
  const badgeColor = isNew ? C.newYellow : C.grayMid;

  // 배지
  slide.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN, y: 0.82, w: 2.6, h: 0.22,
    fill: { color: isNew ? C.newYellowL : C.grayLight },
    line: { color: badgeColor, pt: 0.5 }
  });
  slide.addText(badgeTxt, {
    x: MARGIN, y: 0.82, w: 2.6, h: 0.22,
    fontSize: 7.5, bold: true, color: badgeColor, fontFace: 'Calibri',
    align: 'center', valign: 'middle', margin: 0,
  });

  // 좌측 강조선
  slide.addShape(pres.shapes.RECTANGLE, {
    x: MARGIN, y: 1.12, w: 0.05, h: 3.38,
    fill: { color: C.teal }, line: { color: C.teal }
  });

  // 본문
  const summaryText = s(execSumm, '이번 주 베트남 인프라 시장 동향 분석.');
  slide.addText(summaryText, {
    x: MARGIN + 0.12, y: 1.12, w: W - MARGIN * 2 - 0.12, h: 3.38,
    fontSize: 11.5, color: C.grayDark, fontFace: 'Calibri',
    valign: 'top', wrap: true, margin: [6, 8, 6, 8],
  });

  // 우측 통계 박스
  const stats = [
    { label: '전체 누적 기사', value: `${totalArts}건` },
    { label: '이번 주 신규',   value: `${newCount}건` },
    { label: '분석 플랜',      value: `${planSecs.length}개` },
    { label: 'KPI 변동',       value: `${payload.kpi_changes_count || 0}개` },
  ];
  const sbx = W - 2.1, sby = 1.12, sbw = 1.72, sbh = 0.72;
  stats.forEach((st, i) => {
    const sy = sby + i * (sbh + 0.06);
    slide.addShape(pres.shapes.RECTANGLE, {
      x: sbx, y: sy, w: sbw, h: sbh,
      fill: { color: i === 1 ? C.newYellowL : 'F0F4F8' },
      line: { color: i === 1 ? 'FCD34D' : 'D1D5DB', pt: 0.5 },
    });
    slide.addText(st.label, {
      x: sbx + 0.06, y: sy + 0.04, w: sbw - 0.12, h: 0.22,
      fontSize: 7, color: C.grayMid, fontFace: 'Calibri', margin: 0,
    });
    slide.addText(st.value, {
      x: sbx + 0.06, y: sy + 0.25, w: sbw - 0.12, h: 0.38,
      fontSize: 20, bold: true, color: i === 1 ? C.amber : C.navy,
      fontFace: 'Calibri', valign: 'middle', margin: 0,
    });
  });

  console.log('  ✅ Executive Summary');
}

// ══════════════════════════════════════════════════════════════════════════
//  4. KPI 대시보드 슬라이드 (영역별 진행단계 집계)
// ══════════════════════════════════════════════════════════════════════════
function buildKpiDashboardSlide() {
  const slide = pres.addSlide();
  slide.background = { color: C.white };
  addHeader(slide, 'KPI 대시보드', '마스터플랜 진행단계 및 기사 수집 현황', C.navy);
  addFooter(slide, 'KPI Dashboard');

  // 영역별 집계
  const areas = ['Environment', 'Energy Develop.', 'Urban Develop.'];
  const areaData = {};
  areas.forEach(a => {
    const secs = planSecs.filter(s => s.area === a);
    const totalA = secs.reduce((acc, s) => acc + (s.new_count||0) + (s.old_count||0), 0);
    const newA   = secs.reduce((acc, s) => acc + (s.new_count||0), 0);
    areaData[a] = { secs, total: totalA, new: newA };
  });

  // 영역 요약 카드 (3개)
  const cw = (W - MARGIN * 2 - 0.3) / 3, cy = 0.85, ch = 1.05;
  areas.forEach((area, i) => {
    const theme = AREA_THEME[area] || AREA_THEME.default;
    const ad    = areaData[area];
    const cx    = MARGIN + i * (cw + 0.15);

    slide.addShape(pres.shapes.RECTANGLE, {
      x: cx, y: cy, w: cw, h: ch,
      fill: { color: theme.light }, line: { color: theme.color, pt: 1.2 },
      shadow: mkShadow(),
    });
    slide.addShape(pres.shapes.RECTANGLE, {
      x: cx, y: cy, w: cw, h: 0.28,
      fill: { color: theme.color }, line: { color: theme.color }
    });
    slide.addText(area, {
      x: cx, y: cy, w: cw, h: 0.28,
      fontSize: 9.5, bold: true, color: C.white, fontFace: 'Calibri',
      align: 'center', valign: 'middle', margin: 0,
    });
    slide.addText(`${ad.secs.length}개 플랜`, {
      x: cx + 0.08, y: cy + 0.32, w: cw - 0.16, h: 0.28,
      fontSize: 8, color: theme.color, fontFace: 'Calibri', margin: 0,
    });
    slide.addText(`기사 ${ad.total}건`, {
      x: cx + 0.08, y: cy + 0.56, w: cw - 0.16, h: 0.22,
      fontSize: 8, color: C.grayDark, fontFace: 'Calibri', margin: 0,
    });
    if (ad.new > 0) {
      slide.addText(`★ 신규 ${ad.new}건`, {
        x: cx + 0.08, y: cy + 0.76, w: cw - 0.16, h: 0.20,
        fontSize: 8, bold: true, color: C.amber, fontFace: 'Calibri', margin: 0,
      });
    }
  });

  // 플랜별 진행단계 테이블 헤더
  const tby = 2.02, tbx = MARGIN;
  const tbw  = W - MARGIN * 2;
  const colWidths = [2.0, 1.05, 1.25, 1.2, 1.05, tbw - 2.0 - 1.05 - 1.25 - 1.2 - 1.05];

  // 헤더 행
  slide.addShape(pres.shapes.RECTANGLE, {
    x: tbx, y: tby, w: tbw, h: 0.24,
    fill: { color: C.navy }, line: { color: C.navy }
  });
  const hdrs = ['마스터플랜 ID', '영역', '진행단계', '누적 기사', '신규 기사', '다음 관찰 포인트'];
  let hx = tbx;
  hdrs.forEach((h, i) => {
    slide.addText(h, {
      x: hx, y: tby, w: colWidths[i], h: 0.24,
      fontSize: 7.5, bold: true, color: C.white, fontFace: 'Calibri',
      align: 'center', valign: 'middle', margin: 0,
    });
    hx += colWidths[i];
  });

  // 데이터 행
  const maxRows = Math.floor((H - tby - 0.24 - 0.28) / 0.195);
  const visibleSecs = planSecs.slice(0, maxRows);

  visibleSecs.forEach((sec, ri) => {
    const ry = tby + 0.24 + ri * 0.195;
    const isNew = (sec.new_count || 0) > 0;
    const rowBg = isNew ? C.newYellowL : (ri % 2 === 0 ? C.white : 'F9FAFB');
    const stage  = STAGE[sec.current_stage || 'UNKNOWN'] || STAGE.UNKNOWN;
    const theme  = AREA_THEME[sec.area || ''] || AREA_THEME.default;

    slide.addShape(pres.shapes.RECTANGLE, {
      x: tbx, y: ry, w: tbw, h: 0.192,
      fill: { color: rowBg }, line: { color: 'E5E7EB', pt: 0.3 }
    });

    let rx = tbx;
    const cells = [
      { text: s(sec.plan_id, ''), color: theme.color, bold: true },
      { text: ellipsis(sec.area || '', 12), color: C.grayMid },
      { text: stage.ko, color: stage.bar, bold: true },
      { text: String((sec.new_count||0) + (sec.old_count||0)) + '건', color: C.grayDark },
      { text: (sec.new_count||0) > 0 ? `★ ${sec.new_count}건` : '-', color: (sec.new_count||0)>0 ? C.amber : C.silver, bold: (sec.new_count||0) > 0 },
      { text: ellipsis(sec.next_watch || '', 38), color: C.grayMid },
    ];

    cells.forEach((cell, ci) => {
      slide.addText(cell.text, {
        x: rx + 0.03, y: ry, w: colWidths[ci] - 0.06, h: 0.192,
        fontSize: 7, bold: cell.bold || false, color: cell.color,
        fontFace: 'Calibri', valign: 'middle', margin: 0,
      });
      rx += colWidths[ci];
    });
  });

  if (planSecs.length > maxRows) {
    slide.addText(`+ ${planSecs.length - maxRows}개 플랜 — 상세 슬라이드 참조`, {
      x: tbx, y: H - 0.45, w: tbw, h: 0.20,
      fontSize: 7.5, color: C.grayMid, fontFace: 'Calibri',
      align: 'center', margin: 0,
    });
  }

  console.log('  ✅ KPI 대시보드');
}

// ══════════════════════════════════════════════════════════════════════════
//  5~N. 플랜별 슬라이드 (21개 모두)
// ══════════════════════════════════════════════════════════════════════════
function buildPlanSlide(sec, slideNum, totalSlides) {
  const slide = pres.addSlide();
  slide.background = { color: C.white };

  const theme   = AREA_THEME[s(sec.area, 'default')] || AREA_THEME.default;
  const stage   = STAGE[sec.current_stage || 'UNKNOWN'] || STAGE.UNKNOWN;
  const newCount2 = sec.new_count || 0;
  const oldCount2 = sec.old_count || 0;
  const kpis    = sec.kpi_targets || [];
  const arts    = sec.articles    || [];
  const newArts = arts.filter(a => a.is_new === true);
  const oldArts = arts.filter(a => a.is_new !== true);

  // ── 상단 헤더 ──────────────────────────────────────────────────
  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: W, h: 0.82,
    fill: { color: theme.color }, line: { color: theme.color }
  });

  // 영역 태그
  slide.addText(s(sec.area, ''), {
    x: MARGIN, y: 0.05, w: 2.5, h: 0.20,
    fontSize: 7.5, color: theme.light, fontFace: 'Calibri',
    bold: false, margin: 0,
  });

  // 플랜 ID
  slide.addText(s(sec.plan_id, ''), {
    x: MARGIN, y: 0.08, w: 3.5, h: 0.22,
    fontSize: 8, bold: true, color: 'CCDDF0', fontFace: 'Calibri', margin: 0,
  });

  // 플랜 타이틀
  slide.addText(ellipsis(sec.title_ko || '', 50), {
    x: MARGIN, y: 0.28, w: W - MARGIN * 2 - 1.2, h: 0.38,
    fontSize: 17, bold: true, color: C.white, fontFace: 'Calibri',
    valign: 'middle', margin: 0,
  });

  // 근거 법령
  slide.addText(ellipsis(sec.decision || '', 55), {
    x: MARGIN, y: 0.65, w: W - MARGIN * 2 - 2.5, h: 0.16,
    fontSize: 7.5, color: theme.light, fontFace: 'Calibri', margin: 0,
  });

  // 기사 수 배지 (우상단)
  const totalA = newCount2 + oldCount2;
  slide.addText(`기사 ${totalA}건  |  ★신규 ${newCount2}건`, {
    x: W - 2.1, y: 0.30, w: 1.75, h: 0.30,
    fontSize: 9, bold: true, color: newCount2 > 0 ? C.newYellowL : 'CCDDF0',
    fontFace: 'Calibri', align: 'right', valign: 'middle', margin: 0,
  });

  // ── 슬라이드 번호 ──────────────────────────────────────────────
  slide.addText(`${slideNum} / ${totalSlides}`, {
    x: W - 1.0, y: 0.05, w: 0.65, h: 0.18,
    fontSize: 7, color: 'AABBCC', fontFace: 'Calibri', align: 'right', margin: 0,
  });

  // ── 진행단계 바 ────────────────────────────────────────────────
  const pbY = 0.86;
  slide.addText('진행단계:', {
    x: MARGIN, y: pbY, w: 0.8, h: 0.16,
    fontSize: 7.5, color: C.grayMid, fontFace: 'Calibri', margin: 0,
  });
  addProgressBar(slide, MARGIN + 0.82, pbY + 0.03, 4.5, sec.current_stage || 'UNKNOWN');

  // ── 콘텐츠 영역 ────────────────────────────────────────────────
  const contentY = 1.08;
  const leftW    = 4.2;
  const rightX   = MARGIN + leftW + 0.18;
  const rightW   = W - rightX - MARGIN;

  // ── 좌측: KPI + 사업 개요 ──────────────────────────────────────

  // KPI 테이블
  if (kpis.length > 0) {
    slide.addText('KPI 목표 현황', {
      x: MARGIN, y: contentY, w: leftW, h: 0.22,
      fontSize: 8.5, bold: true, color: theme.color, fontFace: 'Calibri', margin: 0,
    });
    // KPI 헤더
    const khY = contentY + 0.22;
    slide.addShape(pres.shapes.RECTANGLE, {
      x: MARGIN, y: khY, w: leftW, h: 0.20,
      fill: { color: theme.color }, line: { color: theme.color }
    });
    ['KPI 지표', '현황', '2030 목표'].forEach((h, i) => {
      const ws = [leftW * 0.44, leftW * 0.28, leftW * 0.28];
      const xs = [MARGIN, MARGIN + ws[0], MARGIN + ws[0] + ws[1]];
      slide.addText(h, {
        x: xs[i], y: khY, w: ws[i], h: 0.20,
        fontSize: 7.5, bold: true, color: C.white, fontFace: 'Calibri',
        align: 'center', valign: 'middle', margin: 0,
      });
    });
    const maxKpi = Math.min(kpis.length, 5);
    for (let ki = 0; ki < maxKpi; ki++) {
      addKpiRow(slide, MARGIN, khY + 0.20 + ki * 0.235, leftW, kpis[ki], ki % 2 === 1);
    }
    const kpiEndY = khY + 0.20 + maxKpi * 0.235;

    // 사업 개요 (KPI 아래)
    const descY = kpiEndY + 0.10;
    const desc  = ellipsis(sec.description_ko || '', 120);
    if (desc && descY < contentY + 3.2) {
      slide.addShape(pres.shapes.RECTANGLE, {
        x: MARGIN, y: descY, w: leftW, h: 0.20,
        fill: { color: theme.light }, line: { color: theme.color, pt: 0.3 }
      });
      slide.addText('사업 개요', {
        x: MARGIN + 0.05, y: descY, w: leftW, h: 0.20,
        fontSize: 8, bold: true, color: theme.color, fontFace: 'Calibri', valign: 'middle', margin: 0,
      });
      slide.addText(desc, {
        x: MARGIN + 0.05, y: descY + 0.20, w: leftW - 0.1, h: 0.70,
        fontSize: 8, color: C.grayDark, fontFace: 'Calibri',
        valign: 'top', wrap: true, margin: [3, 4, 3, 4],
      });
    }
  }

  // ── 우측: AI 분석 + 기사 ───────────────────────────────────────

  // AI 분석
  const analysis = s(sec.news_analysis, '');
  const insight  = s(sec.insight, '');
  const isNewAnalysis = sec.analysis_is_new || false;

  slide.addText('AI 시장 분석 (Claude Haiku)', {
    x: rightX, y: contentY, w: rightW, h: 0.20,
    fontSize: 8.5, bold: true, color: theme.color, fontFace: 'Calibri', margin: 0,
  });

  // 분석 배지
  const abadge = isNewAnalysis ? '★ 이번 주 신규 분석' : '이전 분석 유지';
  const abadgeColor = isNewAnalysis ? C.newYellow : C.silver;
  slide.addShape(pres.shapes.RECTANGLE, {
    x: rightX, y: contentY + 0.21, w: rightW, h: 0.18,
    fill: { color: isNewAnalysis ? C.newYellowL : C.grayLight },
    line: { color: abadgeColor, pt: 0.5 }
  });
  slide.addText(abadge, {
    x: rightX, y: contentY + 0.21, w: rightW, h: 0.18,
    fontSize: 7, bold: true, color: abadgeColor, fontFace: 'Calibri',
    align: 'center', valign: 'middle', margin: 0,
  });

  // 분석 본문
  const analysisText = analysis || '이번 주 신규 기사가 없습니다. 기존 분석을 유지합니다.';
  slide.addShape(pres.shapes.RECTANGLE, {
    x: rightX, y: contentY + 0.40, w: rightW, h: 0.80,
    fill: { color: C.white },
    line: { color: theme.color, pt: 0.8 }
  });
  slide.addShape(pres.shapes.RECTANGLE, {
    x: rightX, y: contentY + 0.40, w: 0.04, h: 0.80,
    fill: { color: theme.color }, line: { color: theme.color, pt: 0 }
  });
  slide.addText(ellipsis(analysisText, 200), {
    x: rightX + 0.08, y: contentY + 0.40, w: rightW - 0.12, h: 0.80,
    fontSize: 8, color: C.grayDark, fontFace: 'Calibri',
    valign: 'top', wrap: true, margin: [4, 6, 4, 6],
  });

  // Expert Insight
  if (insight) {
    slide.addShape(pres.shapes.RECTANGLE, {
      x: rightX, y: contentY + 1.22, w: rightW, h: 0.46,
      fill: { color: theme.light }, line: { color: theme.color, pt: 0.8 }
    });
    slide.addText('💡 Insight', {
      x: rightX + 0.05, y: contentY + 1.22, w: 0.7, h: 0.18,
      fontSize: 7, bold: true, color: theme.color, fontFace: 'Calibri', margin: 0,
    });
    slide.addText(ellipsis(insight, 95), {
      x: rightX + 0.05, y: contentY + 1.40, w: rightW - 0.1, h: 0.26,
      fontSize: 7.5, bold: true, color: theme.color, fontFace: 'Calibri',
      valign: 'middle', wrap: true, margin: 0,
    });
  }

  // ── 기사 목록 ──────────────────────────────────────────────────
  const artStartY = contentY + (insight ? 1.72 : 1.70);
  const artH      = H - artStartY - 0.30;
  const artRowH   = 0.215;
  const maxRows   = Math.floor(artH / artRowH);

  // 기사 섹션 헤더
  if (arts.length > 0) {
    const artLabelY = artStartY - 0.20;
    slide.addText(`수집 기사  (★신규 ${newCount2}건  +  기존 ${oldCount2}건)`, {
      x: MARGIN, y: artLabelY, w: W - MARGIN * 2, h: 0.18,
      fontSize: 8, bold: true, color: C.navy, fontFace: 'Calibri', margin: 0,
    });

    // 기사 헤더 행
    slide.addShape(pres.shapes.RECTANGLE, {
      x: MARGIN, y: artStartY, w: W - MARGIN * 2, h: 0.20,
      fill: { color: C.grayDark }, line: { color: C.grayDark }
    });
    ['등급', '날짜', '출처', '제목 (한국어)'].forEach((h, i) => {
      const ws = [0.42, 0.65, 0.85, W - MARGIN * 2 - 0.42 - 0.65 - 0.85];
      const xs = [MARGIN, MARGIN + 0.42, MARGIN + 0.42 + 0.65, MARGIN + 0.42 + 0.65 + 0.85];
      slide.addText(h, {
        x: xs[i], y: artStartY, w: ws[i], h: 0.20,
        fontSize: 7, bold: true, color: C.white, fontFace: 'Calibri',
        align: 'center', valign: 'middle', margin: 0,
      });
    });

    // 신규 기사 우선 출력
    const displayArts = [...newArts, ...oldArts].slice(0, maxRows - 1);
    displayArts.forEach((art, ri) => {
      addArticleRow(slide, MARGIN, artStartY + 0.20 + ri * artRowH, W - MARGIN * 2, art, artRowH);
    });

    if (arts.length > displayArts.length) {
      slide.addText(`+ ${arts.length - displayArts.length}건 추가 기사 — Word 보고서 참조`, {
        x: MARGIN, y: H - 0.40, w: W - MARGIN * 2, h: 0.14,
        fontSize: 6.5, color: C.silver, fontFace: 'Calibri', align: 'right', margin: 0,
      });
    }
  } else {
    slide.addShape(pres.shapes.RECTANGLE, {
      x: MARGIN, y: artStartY, w: W - MARGIN * 2, h: 0.32,
      fill: { color: C.grayLight }, line: { color: 'D1D5DB', pt: 0.4 }
    });
    slide.addText('이번 주 수집된 기사 없음 — 기존 분석 및 KPI 현황 유지', {
      x: MARGIN, y: artStartY, w: W - MARGIN * 2, h: 0.32,
      fontSize: 8.5, color: C.silver, fontFace: 'Calibri',
      align: 'center', valign: 'middle', margin: 0,
    });
  }

  addFooter(slide, `${s(sec.plan_id, '')}  |  ${s(sec.area, '')}`);

  return slide;
}

// ══════════════════════════════════════════════════════════════════════════
//  클로징 슬라이드
// ══════════════════════════════════════════════════════════════════════════
function buildClosingSlide() {
  const slide = pres.addSlide();
  slide.background = { color: C.navy };

  slide.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 0, w: 0.06, h: H,
    fill: { color: C.teal }, line: { color: C.teal }
  });

  slide.addText('THANK YOU', {
    x: 0.5, y: 1.5, w: 9, h: 0.8,
    fontSize: 48, bold: true, fontFace: 'Calibri', color: C.white, align: 'center',
    charSpacing: 8,
  });
  slide.addText(`Vietnam Infrastructure Market Intelligence  |  ${week}`, {
    x: 0.5, y: 2.42, w: 9, h: 0.35,
    fontSize: 13, color: '7EB8D4', fontFace: 'Calibri', align: 'center',
  });

  slide.addShape(pres.shapes.LINE, {
    x: 1.5, y: 2.90, w: 7, h: 0,
    line: { color: '2E6A9A', width: 1, dashType: 'dash' }
  });

  slide.addText([
    { text: `총 ${planSecs.length}개 마스터플랜  |  전체 ${totalArts}건 기사  |  신규 ${newCount}건`, options: { breakLine: true } },
    { text: 'SA-8 자동 생성 파이프라인 (Claude Haiku + Node.js)  |  CONFIDENTIAL' }
  ], {
    x: 0.5, y: 3.05, w: 9, h: 0.55,
    fontSize: 9.5, color: '7EB8D4', fontFace: 'Calibri', align: 'center',
  });

  console.log('  ✅ 클로징');
}

// ══════════════════════════════════════════════════════════════════════════
//  메인 실행
// ══════════════════════════════════════════════════════════════════════════
const pres = new pptxgen();
pres.layout  = 'LAYOUT_16x9';
pres.author  = 'SA-8 MI Pipeline';
pres.company = 'Vietnam Infra Intelligence';
pres.title   = `VN Infra MI Report ${today}`;

console.log('\n[슬라이드 생성]');

buildCoverSlide();
buildTocSlide();
buildExecSummarySlide();
buildKpiDashboardSlide();

// 플랜별 슬라이드 (21개 전체)
const FIXED_SLIDES = 4;  // 표지+목차+ExecSummary+KPI대시보드
const totalPlanSlides = planSecs.length;
const totalSlideCount = FIXED_SLIDES + totalPlanSlides + 1;  // +1 클로징

planSecs.forEach((sec, i) => {
  buildPlanSlide(sec, FIXED_SLIDES + i + 1, totalSlideCount);
  console.log(`  ✅ ${s(sec.plan_id, '???')} (${(sec.new_count||0)>0?'★신규':'기존'})`);
});

buildClosingSlide();

// 저장
pres.writeFile({ fileName: outPath }).then(() => {
  const stat = fs.statSync(outPath);
  console.log(`\n✅ 완료: ${outPath} (${(stat.size/1024).toFixed(0)} KB) | 플랜 ${planSecs.length}개`);
}).catch(err => {
  console.error('[PPT] 저장 오류:', err);
  process.exit(1);
});
