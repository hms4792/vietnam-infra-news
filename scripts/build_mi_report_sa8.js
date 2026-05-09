/**
 * build_mi_report_sa8.js  ── SA-8 docx 빌더 v5.0
 * =====================================================
 * 경영진 보고용 전문 MI 보고서 생성기
 *
 * v5.0 핵심 변경 (2026-05-09):
 *   - is_new=true  기사: 노란색 배경 + "★ 신규" 배지
 *   - is_new=false 기사: 회색 배경 (기존 누적 기사 유지)
 *   - 신규 기사 없어도 기존 기사 전체 출력
 *   - 커버: 신규/전체 기사 수 요약
 *   - 영역별(환경/에너지/도시) 컬러 구분
 *   - 헤더/푸터 + 페이지 번호
 *
 * 환경변수:
 *   SA8_DATA_FILE   : Python이 생성한 JSON 페이로드 경로
 *   SA8_OUTPUT_PATH : 출력 docx 경로
 */

'use strict';

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, BorderStyle, WidthType, ShadingType,
  LevelFormat, PageBreak, Header, Footer, PageNumber, VerticalAlign,
  TableLayoutType,
} = require('docx');
const fs   = require('fs');
const path = require('path');

// ── Python이 동적으로 교체하는 플래그 ──────────────────────────────────
const EXEC_SUMMARY_IS_NEW = false;  // Python이 동적으로 교체

// ══════════════════════════════════════════════════════════════════════════
//  컬러 팔레트
// ══════════════════════════════════════════════════════════════════════════
const C = {
  navy:    '0C2340',
  teal:    '0D6E6E',
  blue:    '1B4F8A',
  purple:  '4A3B8C',
  orange:  'C75B00',
  green:   '2D6A4F',
  amber:   '854F0B',
  navyL:   'E8EEF4',
  tealL:   'E0F0EF',
  blueL:   'E3EDF8',
  purpleL: 'EDE9F8',
  greenL:  'E8F5E9',
  grayL:   'F5F5F5',
  amberL:  'FFF3E0',
  newBg:   'FFF9C4',
  newBd:   'F9A825',
  newTxt:  '6D4C00',
  oldBg:   'F5F5F5',
  oldBd:   'BDBDBD',
  oldTxt:  '757575',
  black:   '1A1A1A',
  grayD:   '3D3D3D',
  gray:    '5F5E5A',
  silver:  'AAAAAA',
  white:   'FFFFFF',
};

const AREA_COLORS = {
  'Environment':    { header: '0D6E6E', bg: 'E0F0EF', text: '0D6E6E', bdColor: '0D6E6E' },
  'Energy Develop.':{ header: '1B4F8A', bg: 'E3EDF8', text: '1B4F8A', bdColor: '1B4F8A' },
  'Urban Develop.': { header: '4A3B8C', bg: 'EDE9F8', text: '4A3B8C', bdColor: '4A3B8C' },
  'default':        { header: '0C2340', bg: 'E8EEF4', text: '0C2340', bdColor: '0C2340' },
};

const STAGE_DISPLAY = {
  'PLANNING':     { ko: '계획·승인',  icon: 'P', color: '1B4F8A' },
  'BIDDING':      { ko: '입찰·계약',  icon: 'B', color: '4A3B8C' },
  'CONSTRUCTION': { ko: '건설·시공',  icon: 'C', color: 'C75B00' },
  'COMPLETION':   { ko: '준공·개통',  icon: 'D', color: '2D6A4F' },
  'OPERATION':    { ko: '운영·확장',  icon: 'O', color: '0D6E6E' },
  'UNKNOWN':      { ko: '미확정',     icon: '?', color: '5F5E5A' },
};

// ══════════════════════════════════════════════════════════════════════════
//  유틸리티
// ══════════════════════════════════════════════════════════════════════════
const safe = (v, fb) => {
  if (v === null || v === undefined) return fb !== undefined ? fb : '';
  if (typeof v === 'number') return String(v);
  if (typeof v === 'string' && v.trim()) return v.trim();
  return fb !== undefined ? fb : '';
};

const bd1  = (color, size) => ({ style: BorderStyle.SINGLE, size: size || 4, color: color || 'CCCCCC' });
const bds  = (color) => { const b = bd1(color); return { top: b, bottom: b, left: b, right: b }; };
const noBd = () => { const b = bd1(C.white, 1); return { top: b, bottom: b, left: b, right: b }; };
const bdsL = (lc, oc, ls) => ({
  top: bd1(oc || 'DDDDDD'), bottom: bd1(oc || 'DDDDDD'), right: bd1(oc || 'DDDDDD'),
  left: { style: BorderStyle.SINGLE, size: ls || 16, color: lc || C.navy },
});

const PAGE_MARGIN = { top: 1134, right: 1134, bottom: 1134, left: 1417 };
const CONTENT_W   = 9355;
const CELL_PAD    = { top: 80, bottom: 80, left: 140, right: 120 };

function TR(text, opts) {
  return new TextRun({
    text: safe(text, ' '),
    font: 'Arial',
    size: (opts && opts.size) ? opts.size : 20,
    bold: (opts && opts.bold) ? true : false,
    color: (opts && opts.color) ? opts.color : C.black,
    italics: (opts && opts.italics) ? true : false,
  });
}

function SP(n) {
  return new Paragraph({ spacing: { after: 80 * (n || 1) }, children: [TR('')] });
}

function HR(color, thick) {
  return new Paragraph({
    spacing: { before: 100, after: 100 },
    border: { bottom: { style: BorderStyle.SINGLE, size: thick || 6, color: color || C.navy, space: 1 } },
    children: [],
  });
}

function Para(text, opts) {
  return new Paragraph({
    alignment: (opts && opts.align) ? opts.align : AlignmentType.LEFT,
    spacing: { before: (opts && opts.before) ? opts.before : 0, after: (opts && opts.after) ? opts.after : 80 },
    children: [TR(text, opts)],
  });
}

function BoxPara(text, opts) {
  return new Paragraph({
    spacing: { before: (opts && opts.before) ? opts.before : 60, after: (opts && opts.after) ? opts.after : 60 },
    shading: { fill: (opts && opts.fill) ? opts.fill : C.navyL, type: ShadingType.CLEAR },
    indent: { left: (opts && opts.indent) ? opts.indent : 160, right: 120 },
    children: [TR(text, { size: (opts && opts.size) ? opts.size : 19, bold: (opts && opts.bold) ? true : false, color: (opts && opts.color) ? opts.color : C.black })],
  });
}

function BoxTable1(children, opts) {
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [CONTENT_W],
    layout: TableLayoutType.FIXED,
    rows: [new TableRow({ children: [new TableCell({
      width: { size: CONTENT_W, type: WidthType.DXA },
      borders: (opts && opts.borders) ? opts.borders : bds((opts && opts.bdColor) ? opts.bdColor : 'DDDDDD'),
      shading: { fill: (opts && opts.fill) ? opts.fill : C.white, type: ShadingType.CLEAR },
      margins: (opts && opts.margins) ? opts.margins : CELL_PAD,
      children: children,
    })] })],
  });
}

// ══════════════════════════════════════════════════════════════════════════
//  커버 페이지
// ══════════════════════════════════════════════════════════════════════════
function buildCover(payload) {
  const date      = safe(payload.report_date, new Date().toISOString().slice(0, 10));
  const week      = safe(payload.report_week, '');
  const total     = payload.total_articles || 0;
  const newCount  = payload.new_articles_count || 0;
  const oldCount  = total - newCount;
  const planCount = payload.plan_count || 0;
  const hw        = Math.floor(CONTENT_W / 2);
  const hw2       = CONTENT_W - hw;

  return [
    SP(2),
    new Table({
      width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: [CONTENT_W], layout: TableLayoutType.FIXED,
      rows: [new TableRow({ children: [new TableCell({
        width: { size: CONTENT_W, type: WidthType.DXA }, borders: noBd(),
        shading: { fill: C.navy, type: ShadingType.CLEAR },
        margins: { top: 500, bottom: 500, left: 480, right: 480 }, verticalAlign: VerticalAlign.CENTER,
        children: [
          new Paragraph({ alignment: AlignmentType.CENTER, children: [TR('VIETNAM INFRASTRUCTURE', { size: 38, bold: true, color: C.white })] }),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 80 }, children: [TR('MARKET INTELLIGENCE REPORT', { size: 28, color: 'B0C8E4' })] }),
          new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 200 }, children: [TR('베트남 인프라 시장 분석 주간 보고서', { size: 26, bold: true, color: 'E8F4FD' })] }),
        ],
      })] })]
    }),
    SP(0.5),
    new Table({
      width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: [hw, hw2], layout: TableLayoutType.FIXED,
      rows: [
        new TableRow({ children: [
          new TableCell({ width: { size: hw, type: WidthType.DXA }, borders: bds('D0D0D0'), shading: { fill: C.navyL, type: ShadingType.CLEAR }, margins: { top: 120, bottom: 120, left: 280, right: 120 }, children: [Para('발행일', { bold: true, color: C.navy, size: 17 }), Para(date, { bold: true, size: 22 })] }),
          new TableCell({ width: { size: hw2, type: WidthType.DXA }, borders: bds('D0D0D0'), shading: { fill: C.navyL, type: ShadingType.CLEAR }, margins: { top: 120, bottom: 120, left: 280, right: 120 }, children: [Para('보고 기간', { bold: true, color: C.navy, size: 17 }), Para(week, { bold: true, size: 22 })] }),
        ] }),
        new TableRow({ children: [
          new TableCell({ width: { size: hw, type: WidthType.DXA }, borders: bds('D0D0D0'), margins: { top: 120, bottom: 120, left: 280, right: 120 }, children: [Para('수집 기사', { bold: true, color: C.gray, size: 17 }), Para('전체 ' + total + '건  (신규 ' + newCount + '건 + 기존 ' + oldCount + '건)', { bold: true, size: 19 })] }),
          new TableCell({ width: { size: hw2, type: WidthType.DXA }, borders: bds('D0D0D0'), margins: { top: 120, bottom: 120, left: 280, right: 120 }, children: [Para('분석 마스터플랜', { bold: true, color: C.gray, size: 17 }), Para(String(planCount) + '개', { bold: true, size: 22 })] }),
        ] }),
      ],
    }),
    SP(0.5),
    (newCount > 0
      ? BoxPara('★ 이번 주 신규 기사 ' + newCount + '건 — 노란색 배경으로 표시 / 기존 기사는 회색 배경', { fill: C.newBg, color: C.newTxt, bold: true, size: 18 })
      : BoxPara('이번 주 신규 기사 없음 — 기존 기사 및 분석 내용 유지', { fill: C.oldBg, color: C.oldTxt, size: 17 })
    ),
    SP(0.5),
    Para('■ 분석 영역', { bold: true, color: C.navy, size: 17, before: 80, after: 40 }),
    new Table({
      width: { size: CONTENT_W, type: WidthType.DXA },
      columnWidths: [Math.floor(CONTENT_W/3), Math.floor(CONTENT_W/3), CONTENT_W - Math.floor(CONTENT_W/3)*2],
      layout: TableLayoutType.FIXED,
      rows: [new TableRow({ children: [
        new TableCell({ width: { size: Math.floor(CONTENT_W/3), type: WidthType.DXA }, borders: noBd(), shading: { fill: C.tealL, type: ShadingType.CLEAR }, margins: { top: 80, bottom: 80, left: 160, right: 80 }, children: [Para('  [환경]  폐수/폐기물/상수도', { bold: true, color: C.teal, size: 16 })] }),
        new TableCell({ width: { size: Math.floor(CONTENT_W/3), type: WidthType.DXA }, borders: noBd(), shading: { fill: C.blueL, type: ShadingType.CLEAR }, margins: { top: 80, bottom: 80, left: 160, right: 80 }, children: [Para('  [에너지]  전력/석유가스', { bold: true, color: C.blue, size: 16 })] }),
        new TableCell({ width: { size: CONTENT_W - Math.floor(CONTENT_W/3)*2, type: WidthType.DXA }, borders: noBd(), shading: { fill: C.purpleL, type: ShadingType.CLEAR }, margins: { top: 80, bottom: 80, left: 160, right: 80 }, children: [Para('  [도시]  산단/스마트시티/교통', { bold: true, color: C.purple, size: 16 })] }),
      ] })],
    }),
    SP(1),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120 }, children: [TR('본 보고서는 Claude AI (Haiku)가 자동 생성한 Market Intelligence 문서입니다.  |  내부용 CONFIDENTIAL', { size: 15, color: C.silver, italics: true })] }),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}

// ══════════════════════════════════════════════════════════════════════════
//  Executive Summary
// ══════════════════════════════════════════════════════════════════════════
function buildExecSummary(payload) {
  const execText = safe(payload.executive_summary, '이번 주 베트남 인프라 시장 동향 분석.');
  const kpiCount = payload.kpi_changes_count || 0;
  const isNew    = EXEC_SUMMARY_IS_NEW;
  const newCount = payload.new_articles_count || 0;

  const elems = [];

  elems.push(BoxTable1(
    [new Paragraph({ children: [TR('EXECUTIVE SUMMARY', { size: 28, bold: true, color: C.white }), TR('  |  시장 동향 종합 분석', { size: 19, color: 'B0C4DE' })] })],
    { fill: C.navy, bdColor: C.navy, margins: { top: 200, bottom: 200, left: 360, right: 360 } }
  ));
  elems.push(SP(0.5));

  const badgeTxt = isNew
    ? ('★ 이번 주 AI 신규 분석  |  신규 기사 ' + newCount + '건 기반')
    : (newCount > 0 ? ('신규 기사 ' + newCount + '건 수집') : '이번 주 신규 기사 없음 — 기존 분석 내용 유지');
  const badgeFill  = (isNew || newCount > 0) ? C.newBg : C.oldBg;
  const badgeColor = (isNew || newCount > 0) ? C.newTxt : C.oldTxt;

  elems.push(BoxPara(badgeTxt, { fill: badgeFill, color: badgeColor, bold: true, size: 18 }));
  elems.push(SP(0.5));

  const paras = execText.split('\n').filter(function(p) { return p.trim(); });
  if (paras.length === 0) paras.push(execText);

  elems.push(BoxTable1(
    paras.map(function(p) { return new Paragraph({ spacing: { after: 100 }, children: [TR(p, { size: 21, color: C.grayD })] }); }),
    { borders: bdsL(C.teal, 'EEEEEE', 20), fill: C.white, margins: { top: 160, bottom: 160, left: 280, right: 280 } }
  ));
  elems.push(SP(0.5));

  if (kpiCount > 0) {
    elems.push(BoxPara('※ 이번 주 KPI 변동 감지: ' + kpiCount + '개 항목 → 각 플랜 섹션 참조', { fill: C.amberL, color: C.amber, bold: true, size: 18 }));
    elems.push(SP(0.5));
  }

  elems.push(HR(C.navy, 4));
  elems.push(new Paragraph({ children: [new PageBreak()] }));
  return elems;
}

// ══════════════════════════════════════════════════════════════════════════
//  기사 카드 (신규=노란색, 기존=회색)
// ══════════════════════════════════════════════════════════════════════════
function buildArticleCard(art) {
  var isNew   = art.is_new === true;
  var grade   = safe(art.ctx_grade, 'MEDIUM');
  var isHigh  = grade === 'HIGH';
  var metaBg  = isNew ? C.newBg : C.oldBg;
  var metaBd  = isNew ? C.newBd : C.oldBd;
  var metaTxt = isNew ? C.newTxt : C.oldTxt;
  var conBg   = isNew ? 'FFFEF5' : C.white;
  var gradeTxt = isNew ? (isHigh ? '[신규·HIGH]' : '[신규]') : (isHigh ? 'HIGH' : grade);
  var title   = safe(art.title_ko || art.title_en, '(제목 없음)');
  var summary = safe(art.summary_ko || art.summary_en, '');
  var metaW   = 1600;
  var contW   = CONTENT_W - metaW;

  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: [metaW, contW], layout: TableLayoutType.FIXED,
    rows: [new TableRow({ children: [
      new TableCell({
        width: { size: metaW, type: WidthType.DXA }, borders: bds(metaBd),
        shading: { fill: metaBg, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 120, right: 80 },
        children: [
          Para(gradeTxt, { bold: true, color: metaTxt, size: 17 }),
          Para(safe(art.date, ''), { size: 17, color: isNew ? C.grayD : C.gray }),
          Para(safe(art.source, ''), { size: 16, color: isNew ? C.grayD : C.silver }),
          ...(art.province ? [Para('[' + safe(art.province, '') + ']', { size: 15, color: C.teal })] : []),
        ],
      }),
      new TableCell({
        width: { size: contW, type: WidthType.DXA }, borders: bds(metaBd),
        shading: { fill: conBg, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 160, right: 120 },
        children: [
          new Paragraph({ children: [TR(title, { bold: true, size: isNew ? 20 : 18, color: isNew ? C.black : C.grayD })] }),
          ...(summary ? [new Paragraph({ spacing: { before: 50 }, children: [TR(summary.slice(0, 200), { size: 17, color: C.gray })] })] : []),
        ],
      }),
    ] })],
  });
}

// ══════════════════════════════════════════════════════════════════════════
//  KPI 테이블
// ══════════════════════════════════════════════════════════════════════════
function buildKpiTable(kpiTargets, ac) {
  if (!kpiTargets || kpiTargets.length === 0) return [];
  var colW = [3500, 2500, 3355];
  var headerRow = new TableRow({
    tableHeader: true,
    children: [
      ['KPI 지표', colW[0]], ['2030 목표', colW[1]], ['현황', colW[2]],
    ].map(function(pair) {
      return new TableCell({
        width: { size: pair[1], type: WidthType.DXA }, borders: bds(ac.header),
        shading: { fill: ac.header, type: ShadingType.CLEAR }, margins: CELL_PAD,
        children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [TR(pair[0], { bold: true, color: C.white, size: 18 })] })],
      });
    }),
  });
  var dataRows = kpiTargets.map(function(kpi, i) {
    var bg = i % 2 === 0 ? C.white : C.grayL;
    return new TableRow({ children: [
      new TableCell({ width: { size: colW[0], type: WidthType.DXA }, borders: bds('D0D0D0'), shading: { fill: bg, type: ShadingType.CLEAR }, margins: CELL_PAD, children: [Para(safe(kpi.indicator, '-'), { size: 18 })] }),
      new TableCell({ width: { size: colW[1], type: WidthType.DXA }, borders: bds('D0D0D0'), shading: { fill: bg, type: ShadingType.CLEAR }, margins: CELL_PAD, children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [TR(safe(kpi.target_2030, '-'), { bold: true, color: ac.text, size: 18 })] })] }),
      new TableCell({ width: { size: colW[2], type: WidthType.DXA }, borders: bds('D0D0D0'), shading: { fill: bg, type: ShadingType.CLEAR }, margins: CELL_PAD, children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [TR(safe(kpi.current, '수집 중'), { size: 18, color: C.gray })] })] }),
    ] });
  });
  return [
    Para('■ KPI 목표 현황', { bold: true, color: C.navy, size: 19, before: 120, after: 60 }),
    new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: colW, layout: TableLayoutType.FIXED, rows: [headerRow].concat(dataRows) }),
    SP(0.5),
  ];
}

// ══════════════════════════════════════════════════════════════════════════
//  진행단계 섹션
// ══════════════════════════════════════════════════════════════════════════
function buildStageSection(section) {
  var stage     = safe(section.current_stage, 'UNKNOWN');
  var stageInfo = STAGE_DISPLAY[stage] || STAGE_DISPLAY['UNKNOWN'];
  var nextWatch = safe(section.next_watch, '데이터 수집 중');
  var colW      = [2800, CONTENT_W - 2800];

  return [
    Para('■ 사업 진행단계 (SA-7 분석)', { bold: true, color: C.navy, size: 19, before: 120, after: 60 }),
    new Table({
      width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: colW, layout: TableLayoutType.FIXED,
      rows: [new TableRow({ children: [
        new TableCell({ width: { size: colW[0], type: WidthType.DXA }, borders: noBd(), shading: { fill: C.greenL, type: ShadingType.CLEAR }, margins: { top: 100, bottom: 100, left: 160, right: 120 },
          children: [Para('현재 단계', { bold: true, color: C.green, size: 17 }), Para('[' + stageInfo.icon + '] ' + stageInfo.ko, { bold: true, color: stageInfo.color, size: 22 })] }),
        new TableCell({ width: { size: colW[1], type: WidthType.DXA }, borders: noBd(), margins: { top: 100, bottom: 100, left: 160, right: 120 },
          children: [Para('다음 관찰 포인트', { bold: true, color: C.gray, size: 17 }), Para(nextWatch, { size: 18, color: C.grayD })] }),
      ] })],
    }),
    SP(0.5),
  ];
}

// ══════════════════════════════════════════════════════════════════════════
//  AI 분석 섹션
// ══════════════════════════════════════════════════════════════════════════
function buildAiAnalysis(section, ac) {
  var analysis = safe(section.news_analysis, '');
  var insight  = safe(section.insight, '');
  var isNew    = section.analysis_is_new || false;
  var newCount = section.new_count || 0;
  var artCount = section.articles_used || 0;

  var elems = [];
  elems.push(Para('■ AI 시장 분석 (Claude Haiku)', { bold: true, color: C.navy, size: 19, before: 120, after: 60 }));

  var badgeTxt  = isNew ? ('★ 이번 주 신규 분석  |  신규 기사 ' + artCount + '건 기반') :
                  (newCount > 0 ? '이전 분석 업데이트 (신규 ' + newCount + '건 추가)' : '이번 주 신규 기사 없음 — 이전 분석 유지');
  var badgeFill = isNew ? C.newBg : (newCount > 0 ? C.amberL : C.oldBg);
  var badgeClr  = isNew ? C.newTxt : (newCount > 0 ? C.amber : C.oldTxt);

  elems.push(BoxPara(badgeTxt, { fill: badgeFill, color: badgeClr, size: 17 }));
  elems.push(SP(0.3));

  if (analysis) {
    var paras = analysis.split('\n').filter(function(p) { return p.trim(); });
    if (paras.length === 0) paras = [analysis];
    elems.push(BoxTable1(
      paras.map(function(p) { return new Paragraph({ spacing: { after: 100 }, children: [TR(p, { size: 20, color: C.grayD })] }); }),
      { borders: bdsL(ac.bdColor, 'DDDDDD', 12), fill: C.white, margins: { top: 140, bottom: 140, left: 240, right: 240 } }
    ));
    elems.push(SP(0.5));
  } else {
    elems.push(BoxPara('관련 신규 기사가 없어 분석을 생략합니다.', { fill: C.oldBg, color: C.gray, size: 18 }));
    elems.push(SP(0.5));
  }

  if (insight) {
    elems.push(Para('▶ Expert Insight', { bold: true, color: ac.text, size: 18, after: 40 }));
    elems.push(BoxTable1(
      [new Paragraph({ children: [TR(insight, { size: 20, bold: true, color: ac.text })] })],
      { fill: ac.bg, bdColor: ac.header, margins: { top: 120, bottom: 120, left: 240, right: 240 } }
    ));
    elems.push(SP(0.5));
  }

  return elems;
}

// ══════════════════════════════════════════════════════════════════════════
//  기사 목록 (신규 먼저, 기존 뒤)
// ══════════════════════════════════════════════════════════════════════════
function buildArticleList(articles) {
  if (!articles || articles.length === 0) return [];

  var newArts = articles.filter(function(a) { return a.is_new === true; });
  var oldArts = articles.filter(function(a) { return a.is_new !== true; });
  var total   = articles.length;

  var elems = [];
  elems.push(Para('■ 수집 기사 현황 (총 ' + total + '건  |  ★신규 ' + newArts.length + '건  +  기존 ' + oldArts.length + '건)', { bold: true, color: C.navy, size: 19, before: 120, after: 60 }));

  if (newArts.length > 0) {
    elems.push(BoxPara('★ 신규 기사 — 이번 주 (' + newArts.length + '건)', { fill: C.newBg, color: C.newTxt, bold: true, size: 17 }));
    elems.push(SP(0.3));
    newArts.slice(0, 10).forEach(function(art) {
      elems.push(buildArticleCard(art));
      elems.push(SP(0.3));
    });
  }

  if (oldArts.length > 0) {
    elems.push(BoxPara('기존 누적 기사 (' + oldArts.length + '건)', { fill: C.oldBg, color: C.oldTxt, size: 17 }));
    elems.push(SP(0.3));
    oldArts.slice(0, 8).forEach(function(art) {
      elems.push(buildArticleCard(art));
      elems.push(SP(0.3));
    });
  }

  elems.push(SP(0.5));
  return elems;
}

// ══════════════════════════════════════════════════════════════════════════
//  플랜별 섹션
// ══════════════════════════════════════════════════════════════════════════
function buildPlanSection(section) {
  var planId   = safe(section.plan_id, 'UNKNOWN');
  var titleKo  = safe(section.title_ko, planId);
  var decision = safe(section.decision, '');
  var descKo   = safe(section.description_ko, '');
  var area     = safe(section.area, '');
  var newCount = section.new_count || 0;
  var changes  = section.kpi_changes || [];
  var hasChg   = section.has_kpi_change || false;
  var ac       = AREA_COLORS[area] || AREA_COLORS['default'];

  var elems = [];

  // 플랜 헤더
  var headerChildren = [
    new Paragraph({ children: [TR(planId, { size: 17, color: 'B0D0FF' }), TR('  ' + area, { size: 15, color: 'A0C0E0' }), ...(newCount > 0 ? [TR('  ★ 신규 ' + newCount + '건', { size: 16, color: C.newBg, bold: true })] : [])] }),
    new Paragraph({ spacing: { before: 60 }, children: [TR(titleKo, { size: 24, bold: true, color: C.white })] }),
  ];
  if (decision) headerChildren.push(new Paragraph({ spacing: { before: 40 }, children: [TR('근거: ' + decision, { size: 16, color: 'C0D8F0' })] }));

  elems.push(BoxTable1(headerChildren, { fill: ac.header, bdColor: ac.header, margins: { top: 160, bottom: 160, left: 360, right: 240 } }));
  elems.push(SP(0.5));

  // KPI 변동 경고
  if (hasChg && changes.length > 0) {
    elems.push(BoxTable1(
      [Para('※ KPI 변동 감지', { bold: true, color: C.amber, size: 19 })].concat(changes.map(function(c) { return Para('  - ' + c, { size: 18, color: C.amber }); })),
      { borders: bdsL(C.amber, C.amber, 16), fill: C.amberL, margins: { top: 100, bottom: 100, left: 200, right: 200 } }
    ));
    elems.push(SP(0.5));
  }

  // 사업 개요
  if (descKo) {
    elems.push(Para('■ 사업 개요', { bold: true, color: C.navy, size: 19, before: 80, after: 60 }));
    elems.push(BoxPara(descKo, { fill: ac.bg, color: C.grayD, size: 19, indent: 200 }));
    elems.push(SP(0.5));
  }

  elems = elems.concat(buildKpiTable(section.kpi_targets || [], ac));
  elems = elems.concat(buildStageSection(section));
  elems = elems.concat(buildAiAnalysis(section, ac));
  elems = elems.concat(buildArticleList(section.articles || []));

  elems.push(HR(ac.header, 4));
  elems.push(SP(1));

  return elems;
}

// ══════════════════════════════════════════════════════════════════════════
//  헤더 / 푸터
// ══════════════════════════════════════════════════════════════════════════
function buildHeader(date) {
  return new Header({ children: [new Paragraph({
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: C.navy, space: 1 } },
    children: [TR('Vietnam Infrastructure MI Report  |  ', { bold: true, color: C.navy, size: 16 }), TR(date, { color: C.gray, size: 16 }), TR('                                              CONFIDENTIAL', { color: C.silver, size: 14 })],
  })] });
}

function buildFooter() {
  return new Footer({ children: [new Paragraph({
    alignment: AlignmentType.RIGHT,
    border: { top: { style: BorderStyle.SINGLE, size: 4, color: C.navy, space: 1 } },
    children: [TR('Page ', { size: 16, color: C.gray }), new TextRun({ children: [PageNumber.CURRENT], font: 'Arial', size: 16, color: C.gray }), TR('  |  SA-8 자동 생성  |  내부용 CONFIDENTIAL', { size: 14, color: C.silver })],
  })] });
}

// ══════════════════════════════════════════════════════════════════════════
//  메인 빌더
// ══════════════════════════════════════════════════════════════════════════
async function buildReport(payload, outputPath) {
  var reportDate  = safe(payload.report_date, new Date().toISOString().slice(0, 10));
  var allSections = payload.plan_sections || [];
  var newCount    = payload.new_articles_count || 0;

  console.log('[SA-8 docx v5.0] 보고서 생성 시작');
  console.log('  플랜: ' + allSections.length + '개 | 전체기사: ' + (payload.total_articles || 0) + '건 | 신규: ' + newCount + '건');

  var bodyChildren = buildCover(payload).concat(buildExecSummary(payload));

  var areaOrder = ['Environment', 'Energy Develop.', 'Urban Develop.'];
  var grouped   = {};
  var noArea    = [];

  allSections.forEach(function(sec) {
    var a = safe(sec.area, '');
    if (areaOrder.indexOf(a) >= 0) {
      if (!grouped[a]) grouped[a] = [];
      grouped[a].push(sec);
    } else {
      noArea.push(sec);
    }
  });

  areaOrder.forEach(function(area) {
    var secs = grouped[area] || [];
    if (secs.length === 0) return;
    var ac = AREA_COLORS[area] || AREA_COLORS['default'];
    bodyChildren.push(Para('◆ ' + area, { bold: true, color: ac.text, size: 26, before: 160, after: 80 }));
    bodyChildren.push(HR(ac.header, 8));
    bodyChildren.push(SP(0.5));
    secs.forEach(function(sec) {
      bodyChildren = bodyChildren.concat(buildPlanSection(sec));
    });
  });

  noArea.forEach(function(sec) {
    bodyChildren = bodyChildren.concat(buildPlanSection(sec));
  });

  var doc = new Document({
    numbering: { config: [{ reference: 'bullets', levels: [{ level: 0, format: LevelFormat.BULLET, text: '-', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] }] },
    styles: {
      default: { document: { run: { font: 'Arial', size: 20, color: C.black } } },
      paragraphStyles: [
        { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', run: { size: 32, bold: true, font: 'Arial', color: C.navy }, paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 0 } },
        { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', run: { size: 26, bold: true, font: 'Arial', color: C.blue }, paragraph: { spacing: { before: 180, after: 80 }, outlineLevel: 1 } },
      ],
    },
    sections: [{ properties: { page: { size: { width: 11906, height: 16838 }, margin: PAGE_MARGIN } }, headers: { default: buildHeader(reportDate) }, footers: { default: buildFooter() }, children: bodyChildren }],
  });

  var buffer = await Packer.toBuffer(doc);
  fs.writeFileSync(outputPath, buffer);
  console.log('docx 생성 완료: ' + outputPath + ' (' + (buffer.length / 1024).toFixed(1) + ' KB)');
  return true;
}

// ══════════════════════════════════════════════════════════════════════════
//  엔트리포인트
// ══════════════════════════════════════════════════════════════════════════
(async function() {
  var dataFile   = process.env.SA8_DATA_FILE;
  var outputPath = process.env.SA8_OUTPUT_PATH;

  if (!dataFile || !outputPath) {
    console.error('[SA-8] SA8_DATA_FILE / SA8_OUTPUT_PATH 환경변수 필요');
    process.exit(1);
  }
  if (!fs.existsSync(dataFile)) {
    console.error('[SA-8] 데이터 파일 없음: ' + dataFile);
    process.exit(1);
  }

  var payload;
  try {
    payload = JSON.parse(fs.readFileSync(dataFile, 'utf8'));
  } catch(e) {
    console.error('[SA-8] JSON 파싱 오류: ' + e.message);
    process.exit(1);
  }

  var outDir = path.dirname(outputPath);
  if (!fs.existsSync(outDir)) fs.mkdirSync(outDir, { recursive: true });

  await buildReport(payload, outputPath);
})();
