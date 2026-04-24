/**
 * build_mi_report_sa8.js  ── SA-8 docx 빌더 v2.0
 * ===================================================
 * generate_mi_report.py가 호출하는 Node.js docx 생성기.
 *
 * 환경변수:
 *   SA8_DATA_FILE   — JSON 페이로드 경로 (generate_mi_report.py가 설정)
 *   SA8_OUTPUT_PATH — 출력 docx 경로
 *
 * Layer 1 (고정 데이터, 초록색 배경):
 *   사업 개요, KPI 목표값 테이블, 주요 프로젝트 목록
 *   → knowledge_index.json에서 로드, 매주 동일하게 유지
 *
 * Layer 2 (AI 동적 데이터, 파란색/노란색):
 *   최신 기사 카드, Haiku 분석문, Expert Insight
 *   → Claude Haiku가 생성, 매주 새로 작성
 *   → KPI 변동 항목은 노란색(#FFF176) 하이라이트
 */

'use strict';

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, BorderStyle, WidthType, ShadingType,
  LevelFormat, PageBreak
} = require('docx');
const fs = require('fs');
const path = require('path');

// ── 페이로드 로드 ─────────────────────────────────────────────────────────
const DATA_FILE   = process.env.SA8_DATA_FILE;
const OUTPUT_PATH = process.env.SA8_OUTPUT_PATH;

if (!DATA_FILE || !OUTPUT_PATH) {
  console.error('오류: SA8_DATA_FILE / SA8_OUTPUT_PATH 환경변수 필요');
  process.exit(1);
}

const payload = JSON.parse(fs.readFileSync(DATA_FILE, 'utf-8'));

// ── 색상 팔레트 ───────────────────────────────────────────────────────────
const C = {
  // 브랜드
  navy:    '0C2340',
  teal:    '0d9488', tealL:  'E1F5EE',
  blue:    '185FA5', blueL:  'E6F1FB',
  // Layer 1 — 사업 개요 (고정, 녹색 계열)
  l1Bg:    'EAF3DE', l1Bd:   '3B6D11', l1Tx:  '2D5A0E',
  // Layer 2 — AI 분석 (동적, 파란색 계열)
  l2Bg:    'E6F1FB', l2Bd:   '185FA5', l2Tx:  '0C3D6E',
  // KPI 변동 — 노란색 하이라이트
  yellow:  'FFF176', yellowL: 'FFFDE7', amber:  '854F0B',
  // 기사 등급
  high:    'FFF176', highTx: '854F0B',
  medium:  'F7F5F0',
  // 공통
  gray:    '5F5E5A', grayL:  'F7F5F0',
  white:   'FFFFFF', black:  '1A1A1A',
  // KPI 테이블
  kpiHdr:  '185FA5',
};

// ── 공통 헬퍼 ────────────────────────────────────────────────────────────
const bd  = (color = 'CCCCCC') => ({ style: BorderStyle.SINGLE, size: 1, color });
const bds = (color = 'CCCCCC') => ({
  top: bd(color), bottom: bd(color), left: bd(color), right: bd(color)
});
const cm  = { top: 90, bottom: 90, left: 130, right: 130 };
const SP  = (n = 1) => new Paragraph({ spacing: { after: 80 * n }, children: [new TextRun('')] });

function P(text, opts = {}) {
  return new Paragraph({
    spacing: { after: 80 },
    children: [new TextRun({ text, font: 'Arial', size: 20, color: C.black, ...opts })]
  });
}

function DIV(color = C.teal) {
  return new Paragraph({
    spacing: { before: 120, after: 120 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color, space: 1 } },
    children: []
  });
}

// ── 섹션 헤딩 ─────────────────────────────────────────────────────────────
function H1(text, color = C.navy) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 320, after: 160 },
    children: [new TextRun({ text, font: 'Arial', size: 32, bold: true, color })]
  });
}

function H2(text, color = C.blue) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 240, after: 120 },
    children: [new TextRun({ text, font: 'Arial', size: 26, bold: true, color })]
  });
}

function H3(text, color = C.teal) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 160, after: 80 },
    children: [new TextRun({ text, font: 'Arial', size: 22, bold: true, color })]
  });
}

// ── 레이어 라벨 배지 ──────────────────────────────────────────────────────
/**
 * @param {'L1'|'L2'|'AI'} type
 */
function LAYER_BADGE(type) {
  const cfg = {
    L1: { text: '📋 Layer 1 — 사업 개요 (knowledge_index 고정 데이터)', bg: C.l1Bg, tx: C.l1Tx },
    L2: { text: '🤖 Layer 2 — AI 분석 (Claude Haiku 동적 생성)',         bg: C.l2Bg, tx: C.l2Tx },
    AI: { text: '🤖 AI 논평 — Claude Haiku 생성',                        bg: C.l2Bg, tx: C.l2Tx },
  };
  const c = cfg[type] || cfg.L1;
  return new Paragraph({
    spacing: { before: 80, after: 60 },
    shading: { fill: c.bg, type: ShadingType.CLEAR },
    indent:  { left: 100 },
    children: [new TextRun({ text: c.text, font: 'Arial', size: 17, bold: true, color: c.tx })]
  });
}

// ── KPI 변동 배너 ─────────────────────────────────────────────────────────
function CHANGE_BANNER(changes) {
  const items = Array.isArray(changes) ? changes : [changes];
  return items.map(text => new Paragraph({
    spacing: { before: 60, after: 60 },
    shading: { fill: C.yellowL, type: ShadingType.CLEAR },
    border:  {
      left:   { style: BorderStyle.SINGLE, size: 8, color: C.amber, space: 2 },
      top:    { style: BorderStyle.SINGLE, size: 2, color: C.amber, space: 1 },
      bottom: { style: BorderStyle.SINGLE, size: 2, color: C.amber, space: 1 },
      right:  { style: BorderStyle.SINGLE, size: 2, color: C.amber, space: 1 },
    },
    indent: { left: 220 },
    children: [
      new TextRun({ text: '▲ KPI 변동 ', font: 'Arial', size: 19, bold: true, color: C.amber }),
      new TextRun({ text,                font: 'Arial', size: 19,              color: C.black }),
    ]
  }));
}

// ── [Layer 1] 사업 개요 박스 (고정 데이터) ────────────────────────────────
/**
 * 사업 개요 텍스트 렌더링 — 매주 동일하게 유지
 */
function L1_DESCRIPTION(text) {
  if (!text) return [];
  return [
    LAYER_BADGE('L1'),
    new Paragraph({
      spacing: { before: 40, after: 80 },
      indent:  { left: 160 },
      shading: { fill: C.l1Bg, type: ShadingType.CLEAR },
      border:  { left: { style: BorderStyle.SINGLE, size: 6, color: C.l1Bd, space: 2 } },
      children: [new TextRun({ text, font: 'Arial', size: 20, color: C.black })]
    }),
  ];
}

// ── [Layer 1] KPI 테이블 (고정, 매주 동일) ────────────────────────────────
/**
 * @param {Array} kpiTargets — [{indicator, target_2030, current, changed?}]
 * @param {boolean} hasChange — 이번 주 KPI 변동 여부
 */
function L1_KPI_TABLE(kpiTargets, hasChange = false) {
  if (!kpiTargets || kpiTargets.length === 0) return [];

  const hdrRow = new TableRow({
    tableHeader: true,
    children: ['지표', '목표(2030)', '현황(2024~2026)'].map((h, i) =>
      new TableCell({
        borders: bds(C.kpiHdr),
        width:   { size: [2800, 3200, 3360][i], type: WidthType.DXA },
        shading: { fill: C.kpiHdr, type: ShadingType.CLEAR },
        margins: cm,
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children:  [new TextRun({ text: h, font: 'Arial', size: 19, bold: true, color: C.white })]
        })]
      })
    )
  });

  const dataRows = kpiTargets.map((kpi, ri) => {
    const isChanged = kpi.changed === true;
    const rowBg     = isChanged ? C.yellow : (ri % 2 === 0 ? C.white : C.grayL);
    const cells     = [
      kpi.indicator   || '',
      kpi.target_2030 || '',
      kpi.current     || '',
    ];
    return new TableRow({
      children: cells.map((val, ci) =>
        new TableCell({
          borders: bds('BBBBBB'),
          width:   { size: [2800, 3200, 3360][ci], type: WidthType.DXA },
          shading: { fill: rowBg, type: ShadingType.CLEAR },
          margins: cm,
          children: [new Paragraph({
            alignment: ci === 0 ? AlignmentType.LEFT : AlignmentType.CENTER,
            children:  [new TextRun({
              text:  isChanged && ci > 0 ? '★ ' + val : val,
              font:  'Arial', size: 19,
              bold:  isChanged,
              color: isChanged ? C.amber : C.black
            })]
          })]
        })
      )
    });
  });

  return [new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [2800, 3200, 3360],
    rows: [hdrRow, ...dataRows]
  })];
}

// ── [Layer 1] 주요 프로젝트 목록 (고정) ──────────────────────────────────
function L1_PROJECT_TABLE(projects) {
  if (!projects || projects.length === 0) return [];

  // 컬럼 구성 동적 감지
  const sample = projects[0] || {};
  const hasCap  = 'capacity' in sample;
  const hasLoc  = 'location' in sample;

  const headers = ['프로젝트명', hasLoc ? '위치' : null, hasCap ? '규모/용량' : null, '비고'].filter(Boolean);
  const widths  = headers.length === 4 ? [2200, 1800, 2000, 3360]
                : headers.length === 3 ? [2800, 2200, 4360]
                : [4000, 5360];
  const total   = widths.reduce((a, b) => a + b, 0);

  const hdrRow = new TableRow({
    tableHeader: true,
    children: headers.map((h, i) =>
      new TableCell({
        borders: bds(C.l1Bd),
        width:   { size: widths[i], type: WidthType.DXA },
        shading: { fill: C.l1Bd, type: ShadingType.CLEAR },
        margins: cm,
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children:  [new TextRun({ text: h, font: 'Arial', size: 18, bold: true, color: C.white })]
        })]
      })
    )
  });

  const dataRows = projects.map((proj, ri) => {
    const cells = [
      proj.name       || '',
      hasLoc  ? (proj.location  || '') : null,
      hasCap  ? (proj.capacity  || '') : null,
      proj.note       || proj.status || '',
    ].filter(c => c !== null);

    return new TableRow({
      children: cells.map((val, ci) =>
        new TableCell({
          borders: bds('AAAAAA'),
          width:   { size: widths[ci], type: WidthType.DXA },
          shading: { fill: ri % 2 === 0 ? C.white : C.l1Bg, type: ShadingType.CLEAR },
          margins: cm,
          children: [new Paragraph({
            children: [new TextRun({ text: val, font: 'Arial', size: 18, color: C.black })]
          })]
        })
      )
    });
  });

  return [new Table({
    width: { size: total, type: WidthType.DXA },
    columnWidths: widths,
    rows: [hdrRow, ...dataRows]
  })];
}

// ── [Layer 2] AI 분석문 박스 (동적) ──────────────────────────────────────
function L2_ANALYSIS_BOX(newsAnalysis, insight) {
  const elems = [LAYER_BADGE('L2')];

  if (newsAnalysis) {
    // 분석문에서 ★ 강조 처리
    const lines = newsAnalysis.split('\n').filter(l => l.trim());
    lines.forEach(line => {
      const isHighlight = line.includes('★');
      elems.push(new Paragraph({
        spacing:  { before: 40, after: 60 },
        indent:   { left: 160 },
        shading:  { fill: C.l2Bg, type: ShadingType.CLEAR },
        border:   { left: { style: BorderStyle.SINGLE, size: 6, color: C.l2Bd, space: 2 } },
        children: [new TextRun({
          text:  line,
          font:  'Arial', size: 20,
          bold:  isHighlight,
          color: isHighlight ? C.amber : C.black,
        })]
      }));
    });
  }

  if (insight) {
    elems.push(SP(0.5));
    elems.push(new Paragraph({
      spacing: { before: 40, after: 60 },
      indent:  { left: 160 },
      shading: { fill: C.l2Bg, type: ShadingType.CLEAR },
      border:  { left: { style: BorderStyle.SINGLE, size: 6, color: C.l2Bd, space: 2 } },
      children: [
        new TextRun({ text: '💡 Expert Insight: ', font: 'Arial', size: 19, bold: true, color: C.l2Tx }),
        new TextRun({ text: insight,               font: 'Arial', size: 19,              color: C.black }),
      ]
    }));
  }

  return elems;
}

// ── [Layer 2] 기사 카드 ────────────────────────────────────────────────
function L2_ARTICLE_CARD(article, idx) {
  const isHigh  = (article.ctx_grade || article.grade || '') === 'HIGH';
  const headerBg = isHigh ? C.high   : C.grayL;
  const headerTx = isHigh ? C.amber  : C.gray;
  const title    = article.title_ko || article.title_en || '';
  const summary  = article.summary_ko || article.summary_en || '';

  return [
    new Table({
      width: { size: 9360, type: WidthType.DXA },
      columnWidths: [1600, 2000, 1200, 4560],
      rows: [
        // 헤더 행 (날짜 | 출처 | 등급 | 제목)
        new TableRow({
          children: [
            new TableCell({
              borders: bds('999999'), width: { size: 1600, type: WidthType.DXA },
              shading: { fill: headerBg, type: ShadingType.CLEAR }, margins: cm,
              children: [new Paragraph({ children: [
                new TextRun({ text: `[${idx}] ${article.date || ''}`, font: 'Arial', size: 18, bold: true, color: headerTx })
              ]})]
            }),
            new TableCell({
              borders: bds('999999'), width: { size: 2000, type: WidthType.DXA },
              shading: { fill: headerBg, type: ShadingType.CLEAR }, margins: cm,
              children: [new Paragraph({ children: [
                new TextRun({ text: article.source || '', font: 'Arial', size: 17, color: headerTx })
              ]})]
            }),
            new TableCell({
              borders: bds('999999'), width: { size: 1200, type: WidthType.DXA },
              shading: { fill: isHigh ? C.yellow : C.grayL, type: ShadingType.CLEAR }, margins: cm,
              children: [new Paragraph({
                alignment: AlignmentType.CENTER,
                children: [new TextRun({
                  text: isHigh ? '★ HIGH' : 'MEDIUM',
                  font: 'Arial', size: 18, bold: isHigh, color: isHigh ? C.amber : C.gray
                })]
              })]
            }),
            new TableCell({
              borders: bds('999999'), width: { size: 4560, type: WidthType.DXA },
              shading: { fill: headerBg, type: ShadingType.CLEAR }, margins: cm,
              children: [new Paragraph({ children: [
                new TextRun({ text: title.substring(0, 90), font: 'Arial', size: 18, bold: true, color: C.black })
              ]})]
            }),
          ]
        }),
        // 요약 행
        new TableRow({
          children: [new TableCell({
            columnSpan: 4,
            borders:    bds('BBBBBB'),
            width:      { size: 9360, type: WidthType.DXA },
            shading:    { fill: C.white, type: ShadingType.CLEAR },
            margins:    { top: 80, bottom: 80, left: 180, right: 130 },
            children:   [new Paragraph({ children: [
              new TextRun({ text: summary.substring(0, 200), font: 'Arial', size: 19, color: C.black })
            ]})]
          })]
        })
      ]
    }),
    SP(0.4)
  ];
}

// ══════════════════════════════════════════════════════════════════════════
//  보고서 섹션 빌더
// ══════════════════════════════════════════════════════════════════════════

// ── 커버 페이지 ───────────────────────────────────────────────────────────
function buildCover(data) {
  return [
    SP(5),
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { after: 100 },
      children: [new TextRun({ text: 'VIETNAM INFRASTRUCTURE', font: 'Arial', size: 52, bold: true, color: C.navy })]
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { after: 80 },
      children: [new TextRun({ text: 'MARKET INTELLIGENCE REPORT', font: 'Arial', size: 36, bold: true, color: C.teal })]
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { after: 80 },
      children: [new TextRun({ text: '베트남 인프라 시장 동향 주간 보고서', font: 'Arial', size: 24, color: C.gray })]
    }),
    DIV(C.teal),
    SP(2),
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { after: 60 },
      children: [new TextRun({ text: data.report_date, font: 'Arial', size: 30, bold: true, color: C.navy })]
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { after: 60 },
      children: [new TextRun({
        text: `주간호 ${data.report_week}  │  SA-7 knowledge_index + Claude Haiku 연계 분석`,
        font: 'Arial', size: 20, color: C.gray
      })]
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { after: 60 },
      children: [new TextRun({
        text: `수록 기사: ${data.total_articles}건  │  마스터플랜: ${data.plan_count}개  │  AI 분석: Claude Haiku`,
        font: 'Arial', size: 20, color: C.gray
      })]
    }),
    SP(2),
    // 레이어 안내
    new Table({
      width: { size: 9360, type: WidthType.DXA },
      columnWidths: [4680, 4680],
      rows: [new TableRow({ children: [
        new TableCell({
          borders: bds(C.l1Bd), width: { size: 4680, type: WidthType.DXA },
          shading: { fill: C.l1Bg, type: ShadingType.CLEAR }, margins: cm,
          children: [
            new Paragraph({ children: [new TextRun({ text: '📋 Layer 1 — 고정 데이터', font: 'Arial', size: 19, bold: true, color: C.l1Tx })]}),
            new Paragraph({ children: [new TextRun({ text: '사업 개요 · KPI · 프로젝트 목록', font: 'Arial', size: 18, color: C.black })]}),
            new Paragraph({ children: [new TextRun({ text: 'knowledge_index.json 기반, 매주 동일 유지', font: 'Arial', size: 17, color: C.gray })]}),
          ]
        }),
        new TableCell({
          borders: bds(C.l2Bd), width: { size: 4680, type: WidthType.DXA },
          shading: { fill: C.l2Bg, type: ShadingType.CLEAR }, margins: cm,
          children: [
            new Paragraph({ children: [new TextRun({ text: '🤖 Layer 2 — AI 동적 분석', font: 'Arial', size: 19, bold: true, color: C.l2Tx })]}),
            new Paragraph({ children: [new TextRun({ text: '최신 기사 → Haiku 분석 → 인사이트', font: 'Arial', size: 18, color: C.black })]}),
            new Paragraph({ children: [new TextRun({ text: '★ 노란색 = KPI 변동 (직전 주 대비)', font: 'Arial', size: 17, bold: true, color: C.amber })]}),
          ]
        }),
      ]})]
    }),
    SP(2),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}

// ── Executive Summary ─────────────────────────────────────────────────────
function buildExecutiveSummary(data) {
  const elems = [
    H1('Executive Summary — 주요 동향 분석', C.navy),
    DIV(C.navy),
    SP(),
    LAYER_BADGE('AI'),
  ];

  // AI 논평 렌더링
  const lines = (data.executive_summary || '이번 주 분석 내용을 확인하세요.').split('\n').filter(l => l.trim());
  lines.forEach(line => {
    const isHighlight = line.includes('★');
    elems.push(new Paragraph({
      spacing: { before: 40, after: 60 },
      indent:  { left: 160 },
      shading: { fill: C.l2Bg, type: ShadingType.CLEAR },
      border:  { left: { style: BorderStyle.SINGLE, size: 6, color: C.l2Bd, space: 2 } },
      children: [new TextRun({
        text: line, font: 'Arial', size: 20,
        bold:  isHighlight,
        color: isHighlight ? C.amber : C.black,
      })]
    }));
  });

  // KPI 변동 요약
  if (data.kpi_changes_count > 0) {
    elems.push(SP(0.5));
    elems.push(new Paragraph({
      spacing: { before: 60, after: 60 },
      shading: { fill: C.yellowL, type: ShadingType.CLEAR },
      children: [
        new TextRun({ text: '★ 이번 주 KPI 변동 ', font: 'Arial', size: 19, bold: true, color: C.amber }),
        new TextRun({
          text: `${data.kpi_changes_count}건 감지 — 각 플랜 섹션의 노란색 항목 참조`,
          font: 'Arial', size: 19, color: C.black
        }),
      ]
    }));
  }

  elems.push(SP());
  elems.push(new Paragraph({ children: [new PageBreak()] }));
  return elems;
}

// ── 플랜별 섹션 ───────────────────────────────────────────────────────────
function buildPlanSection(section, sectionIdx) {
  const hasChange = section.has_kpi_change;
  const titleColor = hasChange ? C.amber : C.blue;

  const elems = [
    // 플랜 헤더
    H2(`${sectionIdx}. [${section.plan_id}] ${section.title_ko}`, titleColor),
    new Paragraph({
      spacing: { after: 60 },
      children: [
        new TextRun({ text: section.decision, font: 'Arial', size: 18, color: C.gray }),
        new TextRun({ text: '  │  ', font: 'Arial', size: 18, color: C.gray }),
        new TextRun({ text: section.sector,   font: 'Arial', size: 18, color: C.gray }),
        new TextRun({ text: '  │  ', font: 'Arial', size: 18, color: C.gray }),
        new TextRun({ text: section.area,     font: 'Arial', size: 18, color: C.gray }),
      ]
    }),
    SP(0.5),
  ];

  // KPI 변동 배너
  if (hasChange && section.kpi_changes.length > 0) {
    elems.push(...CHANGE_BANNER(section.kpi_changes));
    elems.push(SP(0.5));
  }

  // ── Layer 1: 사업 목표 및 KPI ─────────────────────────────────────────
  elems.push(H3('■ 사업 목표 및 진행현황 (KPI)'));

  // KPI 테이블: 변동 항목에 changed 플래그 추가
  const kpiWithFlags = (section.kpi_targets || []).map(kpi => ({
    ...kpi,
    changed: hasChange && section.kpi_changes.some(
      c => c.toLowerCase().includes((kpi.indicator || '').toLowerCase().slice(0, 5))
    ),
  }));
  elems.push(...L1_KPI_TABLE(kpiWithFlags, hasChange));
  elems.push(SP(0.5));

  // ── Layer 1: 사업 개요 ────────────────────────────────────────────────
  elems.push(H3('■ 사업 개요'));
  elems.push(...L1_DESCRIPTION(section.description_ko));
  elems.push(SP(0.5));

  // ── Layer 1: 주요 프로젝트 목록 ──────────────────────────────────────
  if (section.key_projects && section.key_projects.length > 0) {
    elems.push(H3('■ 주요 프로젝트 목록'));
    elems.push(LAYER_BADGE('L1'));
    elems.push(...L1_PROJECT_TABLE(section.key_projects));
    elems.push(SP(0.5));
  }

  // ── Layer 2: AI 분석문 ────────────────────────────────────────────────
  const articleCount = (section.articles || []).length;
  elems.push(H3(`■ 최신 뉴스 분석 (${articleCount}건) — Claude Haiku AI 연계 분석`));
  elems.push(...L2_ANALYSIS_BOX(section.news_analysis, section.insight));
  elems.push(SP(0.5));

  // ── Layer 2: 기사 카드 ────────────────────────────────────────────────
  if (articleCount > 0) {
    elems.push(H3('■ 수집 기사 목록 (최신순)'));
    (section.articles || []).forEach((art, i) => {
      elems.push(...L2_ARTICLE_CARD(art, i + 1));
    });
  }

  elems.push(DIV(C.grayL));
  elems.push(SP());
  return elems;
}

// ══════════════════════════════════════════════════════════════════════════
//  문서 생성 실행
// ══════════════════════════════════════════════════════════════════════════
async function build() {
  const sections = payload.plan_sections || [];

  // 영역별 정렬: Environment → Energy Develop. → Urban Develop.
  const AREA_ORDER = { 'Environment': 0, 'Energy Develop.': 1, 'Urban Develop.': 2 };
  sections.sort((a, b) =>
    (AREA_ORDER[a.area] ?? 9) - (AREA_ORDER[b.area] ?? 9)
  );

  const children = [
    ...buildCover(payload),
    ...buildExecutiveSummary(payload),
  ];

  let planIdx = 1;
  let lastArea = '';
  sections.forEach(section => {
    // 영역 구분 헤딩 삽입
    if (section.area && section.area !== lastArea) {
      const areaLabel = {
        'Environment':     '【 환경 인프라 (Environment) 】',
        'Energy Develop.': '【 에너지·전력 (Energy & Power) 】',
        'Urban Develop.':  '【 도시·교통 (Urban & Transport) 】',
      }[section.area] || `【 ${section.area} 】`;

      children.push(H1(areaLabel, C.navy));
      children.push(DIV(C.navy));
      children.push(SP());
      lastArea = section.area;
    }

    children.push(...buildPlanSection(section, planIdx++));
  });

  const doc = new Document({
    styles: {
      default: { document: { run: { font: 'Arial', size: 20 } } },
      paragraphStyles: [
        { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
          run: { size: 32, bold: true, font: 'Arial' },
          paragraph: { spacing: { before: 320, after: 160 }, outlineLevel: 0 } },
        { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
          run: { size: 26, bold: true, font: 'Arial' },
          paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 } },
        { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
          run: { size: 22, bold: true, font: 'Arial' },
          paragraph: { spacing: { before: 160, after: 80 }, outlineLevel: 2 } },
      ]
    },
    sections: [{
      properties: {
        page: {
          size:   { width: 11906, height: 16838 }, // A4
          margin: { top: 1440, right: 1260, bottom: 1440, left: 1260 }
        }
      },
      children
    }]
  });

  const buffer = await Packer.toBuffer(doc);
  fs.mkdirSync(path.dirname(OUTPUT_PATH), { recursive: true });
  fs.writeFileSync(OUTPUT_PATH, buffer);

  const kb = (buffer.length / 1024).toFixed(0);
  console.log(`✅ SA-8 docx 생성 완료: ${path.basename(OUTPUT_PATH)} (${kb} KB)`);
  console.log(`   플랜: ${sections.length}개 | Layer1 고정 + Layer2 Haiku AI 연계`);
}

build().catch(err => { console.error('빌더 오류:', err); process.exit(1); });
