/**
 * build_mi_report_sa8.js  ── SA-8 docx 빌더 v2.0
 * ===================================================
 * generate_mi_report.py가 호출하는 Node.js docx 생성기.
 *
 * 구조 원칙:
 *   Layer 1 (정책 맥락):  knowledge_index.json 에서 로드
 *                         사업개요(description_ko) + KPI 목표(kpi_targets)
 *                         + 주요 계획 프로젝트(key_projects) → 절대 삭제 금지
 *   Layer 2 (뉴스 분석):  generate_mi_report.py 가 전달하는 articles 배열
 *                         Haiku AI 분석(analysis_ko) + 기사 목록
 *
 * v2.0 추가 기능 (Layer1 로직 완전 보존 후 추가):
 *   - 품질평가 섹션 (Quality Assessment): 수집품질 점수 시각화
 *   - 신규/기존 기사 구분 (isNew 플래그 기반 배지)
 *   - Executive Summary → 품질 개요 통합 표시
 *
 * 호출 방법:
 *   node build_mi_report_sa8.js <payload_json_path> <output_docx_path>
 *
 * payload JSON 구조:
 * {
 *   "report_date": "2026-05-10",
 *   "report_period": "2026-04-27 ~ 2026-05-10",
 *   "executive_summary_ko": "...",
 *   "total_articles": 42,
 *   "new_articles_count": 18,    // ★ v2.0 신규
 *   "quality_score": 82,          // ★ v2.0 신규 (0~100)
 *   "quality_details": {          // ★ v2.0 신규
 *     "specialist_ratio": 35,
 *     "province_coverage": 68,
 *     "translation_rate": 91,
 *     "matched_plan_ratio": 74
 *   },
 *   "plans": {
 *     "VN-ENV-NWSP": {
 *       "plan_name_ko": "국가 상하수도 기본계획",
 *       "sector": "Water Supply/Drainage",
 *       "description_ko": "...",        // ★ Layer1 필수
 *       "kpi_targets": [...],           // ★ Layer1 필수
 *       "key_projects": [...],          // ★ Layer1 필수
 *       "analysis_ko": "...",           // Layer2 AI 분석
 *       "kpi_changes": [...],
 *       "articles": [
 *         {
 *           "title_ko": "...",
 *           "summary_ko": "...",
 *           "source": "...",
 *           "date": "2026-05-08",
 *           "url": "...",
 *           "isNew": true               // ★ v2.0 신규/기존 구분
 *         }
 *       ]
 *     }
 *   }
 * }
 */

'use strict';

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, BorderStyle, WidthType, ShadingType,
  LevelFormat, PageBreak, VerticalAlign
} = require('docx');
const fs = require('fs');
const path = require('path');

// ── 색상 팔레트 (v2.0 동일 유지) ────────────────────────────────────────
const C = {
  teal:   '0d9488', tealL:  'E1F5EE', tealD:  '085041',
  blue:   '185FA5', blueL:  'E6F1FB', blueD:  '0D3A6A',
  amber:  '854F0B', amberL: 'FAEEDA',
  coral:  '993C1D', coralL: 'FAECE7',
  purple: '3C3489', purpleL:'EEEDFE',
  green:  '3B6D11', greenL: 'EAF3DE',
  gray:   '5F5E5A', grayL:  'F1EFE8', grayLL: 'FAFAF8',
  white:  'FFFFFF', black:  '1A1A1A',
  navy:   '0C2340',
  yellow: 'FFF9C4', yellowD:'856404',
  // ★ v2.0 추가 색상
  newBadge: 'E8F5E9', newBadgeText: '2E7D32',  // 신규기사 배지
  oldBadge: 'F5F5F5', oldBadgeText: '757575',  // 기존기사 배지
  scoreHigh:   'C8E6C9', scoreMid: 'FFF9C4', scoreLow: 'FFCDD2',
};

// ── 테두리 헬퍼 ─────────────────────────────────────────────────────────
const bd  = (color = 'CCCCCC') => ({ style: BorderStyle.SINGLE, size: 1, color });
const bds = (color = 'CCCCCC') => ({ top: bd(color), bottom: bd(color), left: bd(color), right: bd(color) });
const noBorder = { top: bd('FFFFFF'), bottom: bd('FFFFFF'), left: bd('FFFFFF'), right: bd('FFFFFF') };
const cm  = { top: 100, bottom: 100, left: 150, right: 150 };

// ── 기본 단락 헬퍼 ──────────────────────────────────────────────────────
function H1(text, color = C.teal) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 160 },
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

function H3(text, color = C.gray) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 180, after: 80 },
    children: [new TextRun({ text, font: 'Arial', size: 22, bold: true, color })]
  });
}

function P(text, opts = {}) {
  return new Paragraph({
    spacing: { after: 100 },
    children: [new TextRun({ text, font: 'Arial', size: 20, color: C.black, ...opts })]
  });
}

function PB(prefix, text, bulletRef = 'bullets') {
  return new Paragraph({
    spacing: { after: 80 },
    numbering: { reference: bulletRef, level: 0 },
    children: [
      new TextRun({ text: prefix, font: 'Arial', size: 20, bold: true, color: C.black }),
      new TextRun({ text, font: 'Arial', size: 20, color: C.black })
    ]
  });
}

function DIV(color = C.teal) {
  return new Paragraph({
    spacing: { before: 160, after: 160 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color, space: 1 } },
    children: []
  });
}

function SP(n = 1) {
  return new Paragraph({ spacing: { after: 80 * n }, children: [new TextRun('')] });
}

function ALERT(text, fill = C.amberL, textColor = C.amber, prefix = '') {
  return new Paragraph({
    spacing: { before: 80, after: 80 },
    indent: { left: 240 },
    shading: { fill, type: ShadingType.CLEAR },
    children: [new TextRun({ text: prefix + text, font: 'Arial', size: 19, color: textColor, bold: !!prefix })]
  });
}

// ── 표지 (Cover Page) ───────────────────────────────────────────────────
function buildCoverPage(payload) {
  const { report_date, report_period, total_articles, new_articles_count = 0, quality_score = null } = payload;
  const rows = [];

  // 메인 타이틀 배너 (2열 표)
  rows.push(new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [9360],
    rows: [
      new TableRow({
        children: [new TableCell({
          borders: noBorder,
          shading: { fill: C.navy, type: ShadingType.CLEAR },
          margins: { top: 400, bottom: 400, left: 600, right: 600 },
          children: [
            new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [new TextRun({ text: '베트남 인프라 MI 주간 보고서', font: 'Arial', size: 44, bold: true, color: C.white })]
            }),
            new Paragraph({
              alignment: AlignmentType.CENTER,
              spacing: { before: 120 },
              children: [new TextRun({ text: 'Vietnam Infrastructure Market Intelligence Report', font: 'Arial', size: 24, color: 'AADDFF' })]
            })
          ]
        })]
      })
    ]
  }));

  rows.push(SP(2));

  // 보고서 메타정보 표
  rows.push(new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [2400, 6960],
    rows: [
      makeMetaRow('보고서 기준일', report_date || ''),
      makeMetaRow('수집 기간', report_period || ''),
      makeMetaRow('전체 수집 기사', `${total_articles || 0}건 (신규 ${new_articles_count}건 포함)`),
      ...(quality_score !== null ? [makeMetaRow('수집 품질 점수', `${quality_score}점 / 100점`)] : []),
      makeMetaRow('작성 시스템', 'Claude SA-8 자동 생성 (Anthropic Claude Haiku)'),
    ]
  }));

  rows.push(SP(2));
  rows.push(DIV(C.teal));

  return rows;
}

function makeMetaRow(label, value) {
  return new TableRow({
    children: [
      new TableCell({
        borders: bds('DDDDDD'),
        shading: { fill: C.grayL, type: ShadingType.CLEAR },
        margins: cm,
        width: { size: 2400, type: WidthType.DXA },
        children: [new Paragraph({ children: [new TextRun({ text: label, font: 'Arial', size: 19, bold: true, color: C.navy })] })]
      }),
      new TableCell({
        borders: bds('DDDDDD'),
        margins: cm,
        width: { size: 6960, type: WidthType.DXA },
        children: [new Paragraph({ children: [new TextRun({ text: value, font: 'Arial', size: 19, color: C.black })] })]
      })
    ]
  });
}

// ── Executive Summary ────────────────────────────────────────────────────
function buildExecutiveSummary(payload) {
  const elems = [];
  elems.push(H1('Executive Summary — 총괄 분석'));
  elems.push(DIV(C.teal));

  if (payload.executive_summary_ko) {
    const lines = payload.executive_summary_ko.split('\n').filter(Boolean);
    for (const line of lines) {
      if (line.startsWith('##') || line.startsWith('**')) {
        elems.push(H2(line.replace(/[#*]/g, '').trim(), C.blue));
      } else if (line.startsWith('-') || line.startsWith('•')) {
        elems.push(PB('', line.replace(/^[-•]\s*/, '')));
      } else {
        elems.push(P(line));
      }
    }
  } else {
    elems.push(ALERT('AI 분석 요약이 생성되지 않았습니다. (DRY-RUN 모드 또는 API 키 미설정)', C.amberL, C.amber, '⚠️ '));
  }

  elems.push(SP());
  return elems;
}

// ── ★ v2.0 신규: 품질평가 섹션 ─────────────────────────────────────────
/**
 * buildQualitySection()
 * 수집 품질 점수 및 세부 지표를 시각화하는 섹션.
 * Layer1 로직과 완전히 분리된 독립 함수.
 *
 * @param {object} payload - 전체 페이로드
 * @returns {Array} - Paragraph/Table 배열
 */
function buildQualitySection(payload) {
  const elems = [];
  const { quality_score, quality_details = {}, total_articles = 0, new_articles_count = 0 } = payload;

  // 품질 점수가 없으면 섹션 자체를 스킵 (하위 호환성)
  if (quality_score === undefined || quality_score === null) return elems;

  elems.push(H1('수집 품질 평가 (Collection Quality Assessment)'));
  elems.push(DIV(C.teal));

  // 종합 품질 점수 배너
  const scoreColor = quality_score >= 80 ? C.green : quality_score >= 60 ? C.amber : C.coral;
  const scoreFill  = quality_score >= 80 ? C.scoreHigh : quality_score >= 60 ? C.scoreMid : C.scoreLow;
  const scoreLabel = quality_score >= 80 ? '우수 (Good)' : quality_score >= 60 ? '보통 (Fair)' : '개선 필요 (Poor)';

  elems.push(new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [4680, 4680],
    rows: [
      new TableRow({
        children: [
          new TableCell({
            borders: bds(scoreColor),
            shading: { fill: scoreFill, type: ShadingType.CLEAR },
            margins: { top: 200, bottom: 200, left: 300, right: 300 },
            width: { size: 4680, type: WidthType.DXA },
            verticalAlign: VerticalAlign.CENTER,
            children: [
              new Paragraph({
                alignment: AlignmentType.CENTER,
                children: [new TextRun({ text: `${quality_score}점`, font: 'Arial', size: 56, bold: true, color: scoreColor })]
              }),
              new Paragraph({
                alignment: AlignmentType.CENTER,
                children: [new TextRun({ text: scoreLabel, font: 'Arial', size: 22, bold: true, color: scoreColor })]
              })
            ]
          }),
          new TableCell({
            borders: bds('DDDDDD'),
            margins: cm,
            width: { size: 4680, type: WidthType.DXA },
            children: [
              new Paragraph({ children: [new TextRun({ text: '수집 현황', font: 'Arial', size: 20, bold: true, color: C.navy })] }),
              SP(),
              ...buildQualityDetailRows(quality_details, total_articles, new_articles_count)
            ]
          })
        ]
      })
    ]
  }));

  elems.push(SP());

  // 세부 지표 테이블
  if (Object.keys(quality_details).length > 0) {
    elems.push(H3('세부 품질 지표', C.blue));
    elems.push(buildQualityDetailTable(quality_details));
  }

  elems.push(SP());
  elems.push(DIV(C.blue));
  return elems;
}

/**
 * buildQualityDetailRows() — 품질 현황 텍스트 행 생성
 */
function buildQualityDetailRows(details, total, newCount) {
  const items = [
    { label: '전체 수집', value: `${total}건` },
    { label: '신규 기사', value: `${newCount}건` },
    { label: '기존 기사', value: `${total - newCount}건` },
  ];
  return items.map(item =>
    new Paragraph({
      spacing: { after: 60 },
      children: [
        new TextRun({ text: `${item.label}: `, font: 'Arial', size: 19, bold: true, color: C.gray }),
        new TextRun({ text: item.value, font: 'Arial', size: 19, color: C.black })
      ]
    })
  );
}

/**
 * buildQualityDetailTable() — 4개 품질 지표 테이블
 */
function buildQualityDetailTable(details) {
  const metrics = [
    { key: 'specialist_ratio',    label: '전문미디어 비율', unit: '%', target: 30, desc: '목표: 30% 이상' },
    { key: 'province_coverage',   label: '성(Province) 커버율', unit: '%', target: 75, desc: '목표: 75% 이상' },
    { key: 'translation_rate',    label: '번역 완료율', unit: '%', target: 90, desc: '목표: 90% 이상' },
    { key: 'matched_plan_ratio',  label: '정책 매핑률', unit: '%', target: 60, desc: '목표: 60% 이상' },
  ];

  const rows = [
    // 헤더
    new TableRow({
      children: ['지표', '현재값', '목표', '평가'].map(h =>
        new TableCell({
          borders: bds(C.blue),
          shading: { fill: C.blueD, type: ShadingType.CLEAR },
          margins: cm,
          width: { size: [3000, 1800, 1800, 2760][['지표','현재값','목표','평가'].indexOf(h)], type: WidthType.DXA },
          children: [new Paragraph({ alignment: AlignmentType.CENTER,
            children: [new TextRun({ text: h, font: 'Arial', size: 19, bold: true, color: C.white })] })]
        })
      )
    }),
    ...metrics.map(m => {
      const val  = details[m.key] ?? null;
      const ok   = val !== null && val >= m.target;
      const fill = val === null ? C.grayL : ok ? C.greenL : C.coralL;
      const fgCol= val === null ? C.gray  : ok ? C.green   : C.coral;
      const mark = val === null ? '-'     : ok ? '✓ 달성'  : '✗ 미달';
      return new TableRow({
        children: [
          _qCell(m.label, 3000, C.grayLL, C.black),
          _qCell(val !== null ? `${val}${m.unit}` : 'N/A', 1800, fill, fgCol, true),
          _qCell(`${m.target}${m.unit}`, 1800, C.grayLL, C.gray),
          _qCell(mark, 2760, fill, fgCol, true),
        ]
      });
    })
  ];

  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [3000, 1800, 1800, 2760],
    rows
  });
}

function _qCell(text, w, fill, color, bold = false) {
  return new TableCell({
    borders: bds('DDDDDD'),
    shading: { fill, type: ShadingType.CLEAR },
    margins: cm,
    width: { size: w, type: WidthType.DXA },
    children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: String(text), font: 'Arial', size: 19, color, bold })]
    })]
  });
}

// ── Layer 1: 사업개요 + KPI + 주요프로젝트 ──────────────────────────────
/**
 * buildLayer1Section()
 * ★ 기존 Layer1 로직 완전 보존 — 절대 변경 금지
 *
 * knowledge_index.json에서 로드된 plan_data의 3가지 필드를 렌더링:
 *   - description_ko : 사업 개요
 *   - kpi_targets    : KPI 목표 배열 [{indicator, target, unit, baseline}]
 *   - key_projects   : 주요 프로젝트 배열 [{name_ko, budget_usd, status, province}]
 *
 * @param {object} planData - knowledge_index의 플랜 데이터
 * @returns {Array} - Paragraph/Table 배열
 */
function buildLayer1Section(planData) {
  const elems = [];

  // ── 1-1: 사업 개요 ──────────────────────────────────────────────────
  elems.push(H2('① 사업 개요 (Layer 1 — 정책 맥락)', C.teal));

  if (planData.description_ko) {
    const descLines = planData.description_ko.split('\n').filter(Boolean);
    for (const line of descLines) {
      elems.push(P(line));
    }
  } else {
    elems.push(ALERT('사업 개요(description_ko)가 knowledge_index.json에 등록되지 않았습니다.', C.amberL, C.amber, '⚠️ '));
  }

  elems.push(SP());

  // ── 1-2: KPI 목표 테이블 ────────────────────────────────────────────
  elems.push(H2('② KPI 목표 및 기준값', C.teal));

  const kpis = planData.kpi_targets || [];
  if (kpis.length === 0) {
    elems.push(ALERT('KPI 목표(kpi_targets)가 knowledge_index.json에 등록되지 않았습니다.', C.amberL, C.amber, '⚠️ '));
  } else {
    // KPI 테이블 헤더
    const kpiHeaderCols = ['지표 (Indicator)', '목표값 (Target)', '단위', '기준값 (Baseline)'];
    const kpiColWidths  = [3600, 2000, 1200, 2560];

    const kpiRows = [
      new TableRow({
        children: kpiHeaderCols.map((h, i) =>
          new TableCell({
            borders: bds(C.teal),
            shading: { fill: C.tealD, type: ShadingType.CLEAR },
            margins: cm,
            width: { size: kpiColWidths[i], type: WidthType.DXA },
            children: [new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [new TextRun({ text: h, font: 'Arial', size: 19, bold: true, color: C.white })]
            })]
          })
        )
      }),
      ...kpis.map((kpi, idx) =>
        new TableRow({
          children: [
            _kpiCell(kpi.label || kpi.indicator || kpi.indicator_ko || '', 3600, idx % 2 === 0 ? C.white : C.grayLL),
            _kpiCell(String(kpi.target || ''), 2000, idx % 2 === 0 ? C.tealL : C.tealL, C.tealD, true),
            _kpiCell(kpi.unit || '', 1200, idx % 2 === 0 ? C.white : C.grayLL),
            _kpiCell(String(kpi.current || kpi.baseline || kpi.current_value || '-'), 2560, idx % 2 === 0 ? C.white : C.grayLL),
          ]
        })
      )
    ];

    elems.push(new Table({
      width: { size: 9360, type: WidthType.DXA },
      columnWidths: kpiColWidths,
      rows: kpiRows
    }));
  }

  elems.push(SP());

  // ── 1-3: 주요 계획 프로젝트 ─────────────────────────────────────────
  elems.push(H2('③ 주요 계획 프로젝트 목록', C.teal));

  const projects = planData.key_projects || [];
  if (projects.length === 0) {
    elems.push(ALERT('주요 프로젝트(key_projects)가 knowledge_index.json에 등록되지 않았습니다.', C.amberL, C.amber, '⚠️ '));
  } else {
    const projHeaderCols = ['프로젝트명', '예산 (USD)', '추진 상태', '대상 지역'];
    const projColWidths  = [3400, 1800, 1800, 2360];

    const projRows = [
      new TableRow({
        children: projHeaderCols.map((h, i) =>
          new TableCell({
            borders: bds(C.teal),
            shading: { fill: C.teal, type: ShadingType.CLEAR },
            margins: cm,
            width: { size: projColWidths[i], type: WidthType.DXA },
            children: [new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [new TextRun({ text: h, font: 'Arial', size: 19, bold: true, color: C.white })]
            })]
          })
        )
      }),
      ...projects.map((proj, idx) => {
        const statusColor = getStatusColor(proj.status);
        return new TableRow({
          children: [
            _projCell(proj.name_ko || proj.name || '', 3400, idx % 2 === 0 ? C.white : C.grayLL),
            _projCell(formatBudget(proj.budget_usd), 1800, idx % 2 === 0 ? C.white : C.grayLL, C.blue, true),
            _projCell(proj.status || '', 1800, statusColor.fill, statusColor.text, true),
            _projCell(proj.province || proj.location || '', 2360, idx % 2 === 0 ? C.white : C.grayLL),
          ]
        });
      })
    ];

    elems.push(new Table({
      width: { size: 9360, type: WidthType.DXA },
      columnWidths: projColWidths,
      rows: projRows
    }));
  }

  elems.push(SP());
  return elems;
}

function _kpiCell(text, w, fill = C.white, color = C.black, bold = false) {
  return new TableCell({
    borders: bds('DDDDDD'),
    shading: { fill, type: ShadingType.CLEAR },
    margins: cm,
    width: { size: w, type: WidthType.DXA },
    children: [new Paragraph({ children: [new TextRun({ text: String(text), font: 'Arial', size: 19, color, bold })] })]
  });
}

function _projCell(text, w, fill = C.white, color = C.black, bold = false) {
  return new TableCell({
    borders: bds('DDDDDD'),
    shading: { fill, type: ShadingType.CLEAR },
    margins: cm,
    width: { size: w, type: WidthType.DXA },
    children: [new Paragraph({ children: [new TextRun({ text: String(text), font: 'Arial', size: 19, color, bold })] })]
  });
}

/** 프로젝트 추진상태에 따른 색상 반환 */
function getStatusColor(status = '') {
  const s = status.toLowerCase();
  if (s.includes('완료') || s.includes('운영') || s.includes('operational') || s.includes('completed'))
    return { fill: C.greenL, text: C.green };
  if (s.includes('공사') || s.includes('시공') || s.includes('construction') || s.includes('under'))
    return { fill: C.blueL, text: C.blue };
  if (s.includes('계획') || s.includes('검토') || s.includes('planning') || s.includes('feasibility'))
    return { fill: C.purpleL, text: C.purple };
  if (s.includes('입찰') || s.includes('발주') || s.includes('tender') || s.includes('procurement'))
    return { fill: C.amberL, text: C.amber };
  return { fill: C.grayL, text: C.gray };
}

/** 예산 숫자 포맷 (단위: USD) */
function formatBudget(val) {
  if (!val && val !== 0) return 'N/A';
  const n = Number(val);
  if (isNaN(n)) return String(val);
  if (n >= 1e9)  return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6)  return `$${(n / 1e6).toFixed(0)}M`;
  if (n >= 1e3)  return `$${(n / 1e3).toFixed(0)}K`;
  return `$${n}`;
}

// ── Layer 2: AI 분석 + 기사 목록 ────────────────────────────────────────
/**
 * buildLayer2Section()
 * ★ Layer2 뉴스 분석 — v2.0에서 신규/기존 기사 구분 배지 추가
 *   기존 분석 텍스트 렌더링 로직 완전 보존
 *
 * @param {object} planData - 플랜 데이터 (analysis_ko, kpi_changes, articles)
 * @returns {Array}
 */
function buildLayer2Section(planData) {
  const elems = [];

  elems.push(H2('④ AI 분석 요약 (Layer 2 — 뉴스 인사이트)', C.blue));

  // KPI 변동 알림
  const kpiChanges = planData.kpi_changes || [];
  if (kpiChanges.length > 0) {
    for (const kc of kpiChanges) {
      elems.push(ALERT(
        `${kc.indicator}: ${kc.previous} → ${kc.current} (${kc.change_pct >= 0 ? '+' : ''}${kc.change_pct}%)`,
        C.yellow, C.yellowD, '📊 KPI 변동 — '
      ));
    }
    elems.push(SP());
  }

  // AI 분석 텍스트
  if (planData.analysis_ko) {
    const lines = planData.analysis_ko.split('\n').filter(Boolean);
    for (const line of lines) {
      if (line.startsWith('##') || line.startsWith('**')) {
        elems.push(H3(line.replace(/[#*]/g, '').trim(), C.blueD));
      } else if (line.startsWith('-') || line.startsWith('•')) {
        elems.push(PB('', line.replace(/^[-•]\s*/, '')));
      } else {
        elems.push(P(line));
      }
    }
  } else {
    elems.push(ALERT('AI 분석이 생성되지 않았습니다. (DRY-RUN 또는 해당 기간 기사 없음)', C.grayL, C.gray, 'ℹ️ '));
  }

  elems.push(SP());

  // 기사 목록 (신규/기존 구분 배지 ★ v2.0 추가)
  const articles = planData.articles || [];
  if (articles.length > 0) {
    elems.push(H2('⑤ 수집 기사 목록 (Matched Articles)', C.blue));

    const newCount = articles.filter(a => a.isNew).length;
    const oldCount = articles.length - newCount;

    // 기사 수 요약 배지
    elems.push(new Table({
      width: { size: 9360, type: WidthType.DXA },
      columnWidths: [4680, 4680],
      rows: [
        new TableRow({
          children: [
            new TableCell({
              borders: bds(C.newBadgeText),
              shading: { fill: C.newBadge, type: ShadingType.CLEAR },
              margins: cm,
              width: { size: 4680, type: WidthType.DXA },
              children: [new Paragraph({
                alignment: AlignmentType.CENTER,
                children: [new TextRun({ text: `🆕 신규 기사: ${newCount}건`, font: 'Arial', size: 20, bold: true, color: C.newBadgeText })]
              })]
            }),
            new TableCell({
              borders: bds('BBBBBB'),
              shading: { fill: C.oldBadge, type: ShadingType.CLEAR },
              margins: cm,
              width: { size: 4680, type: WidthType.DXA },
              children: [new Paragraph({
                alignment: AlignmentType.CENTER,
                children: [new TextRun({ text: `📋 기존 기사: ${oldCount}건`, font: 'Arial', size: 20, bold: true, color: C.oldBadgeText })]
              })]
            })
          ]
        })
      ]
    }));

    elems.push(SP());

    // 기사 개별 행 (신규 = 초록 배경, 기존 = 흰색)
    const artHeaderCols = ['구분', '제목 (한국어)', '출처', '날짜'];
    const artColWidths  = [700, 5560, 1800, 1300];

    const artRows = [
      new TableRow({
        children: artHeaderCols.map((h, i) =>
          new TableCell({
            borders: bds(C.blue),
            shading: { fill: C.blue, type: ShadingType.CLEAR },
            margins: cm,
            width: { size: artColWidths[i], type: WidthType.DXA },
            children: [new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [new TextRun({ text: h, font: 'Arial', size: 18, bold: true, color: C.white })]
            })]
          })
        )
      }),
      ...articles.map(art => {
        const isNew = art.isNew === true;
        const rowFill = isNew ? C.newBadge : C.white;
        const badge   = isNew ? '🆕' : '·';
        const badgeColor = isNew ? C.newBadgeText : C.gray;
        return new TableRow({
          children: [
            new TableCell({
              borders: bds('DDDDDD'),
              shading: { fill: rowFill, type: ShadingType.CLEAR },
              margins: cm,
              width: { size: 700, type: WidthType.DXA },
              children: [new Paragraph({
                alignment: AlignmentType.CENTER,
                children: [new TextRun({ text: badge, font: 'Arial', size: 18, color: badgeColor })]
              })]
            }),
            new TableCell({
              borders: bds('DDDDDD'),
              shading: { fill: rowFill, type: ShadingType.CLEAR },
              margins: cm,
              width: { size: 5560, type: WidthType.DXA },
              children: [
                new Paragraph({ children: [new TextRun({ text: art.title_ko || art.title || '', font: 'Arial', size: 18, color: C.black, bold: isNew })] }),
                ...(art.summary_ko ? [new Paragraph({ spacing: { before: 40 }, children: [new TextRun({ text: art.summary_ko.substring(0, 120) + (art.summary_ko.length > 120 ? '...' : ''), font: 'Arial', size: 16, color: C.gray })] })] : [])
              ]
            }),
            new TableCell({
              borders: bds('DDDDDD'),
              shading: { fill: rowFill, type: ShadingType.CLEAR },
              margins: cm,
              width: { size: 1800, type: WidthType.DXA },
              children: [new Paragraph({ children: [new TextRun({ text: art.source || '', font: 'Arial', size: 17, color: C.blue })] })]
            }),
            new TableCell({
              borders: bds('DDDDDD'),
              shading: { fill: rowFill, type: ShadingType.CLEAR },
              margins: cm,
              width: { size: 1300, type: WidthType.DXA },
              children: [new Paragraph({
                alignment: AlignmentType.CENTER,
                children: [new TextRun({ text: art.date || '', font: 'Arial', size: 17, color: C.gray })]
              })]
            })
          ]
        });
      })
    ];

    elems.push(new Table({
      width: { size: 9360, type: WidthType.DXA },
      columnWidths: artColWidths,
      rows: artRows
    }));
  } else {
    elems.push(ALERT('해당 기간 수집 기사가 없습니다.', C.grayL, C.gray, 'ℹ️ '));
  }

  elems.push(SP(2));
  return elems;
}

// ── 플랜별 통합 섹션 (Layer1 + Layer2) ──────────────────────────────────
/**
 * buildPlanSection()
 * 각 마스터플랜에 대한 완전한 섹션 구성.
 * Layer1 → Layer2 순서 고정. 절대 순서 변경 금지.
 *
 * @param {string} planId
 * @param {object} planData
 * @param {number} idx - 플랜 인덱스
 * @returns {Array}
 */
function buildPlanSection(planId, planData, idx) {
  const elems = [];

  // 섹터 색상 매핑
  const sectorColor = getSectorColor(planData.sector || '');

  // 플랜 헤더 배너
  elems.push(new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [800, 8560],
    rows: [
      new TableRow({
        children: [
          new TableCell({
            borders: noBorder,
            shading: { fill: sectorColor, type: ShadingType.CLEAR },
            margins: { top: 120, bottom: 120, left: 160, right: 160 },
            width: { size: 800, type: WidthType.DXA },
            verticalAlign: VerticalAlign.CENTER,
            children: [new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [new TextRun({ text: `${idx + 1}`, font: 'Arial', size: 32, bold: true, color: C.white })]
            })]
          }),
          new TableCell({
            borders: noBorder,
            shading: { fill: C.grayL, type: ShadingType.CLEAR },
            margins: { top: 120, bottom: 120, left: 240, right: 160 },
            width: { size: 8560, type: WidthType.DXA },
            children: [
              new Paragraph({ children: [new TextRun({ text: planData.plan_name_ko || planId, font: 'Arial', size: 26, bold: true, color: C.navy })] }),
              new Paragraph({ children: [new TextRun({ text: `플랜 ID: ${planId}  |  섹터: ${planData.sector || 'N/A'}`, font: 'Arial', size: 18, color: C.gray })] })
            ]
          })
        ]
      })
    ]
  }));

  elems.push(SP());

  // ★ Layer 1 — 기존 로직 완전 보존
  elems.push(...buildLayer1Section(planData));

  // ★ Layer 2 — 뉴스 분석 (신규/기존 구분 v2.0 추가)
  elems.push(...buildLayer2Section(planData));

  // 섹션 구분선
  elems.push(DIV(sectorColor));
  elems.push(SP(2));

  return elems;
}

/** 섹터별 색상 반환 */
function getSectorColor(sector) {
  const s = sector.toLowerCase();
  if (s.includes('waste water') || s.includes('wastewater'))       return '0d9488'; // teal
  if (s.includes('water supply') || s.includes('drainage'))         return '1565C0'; // blue
  if (s.includes('solid waste'))                                    return '2E7D32'; // green
  if (s.includes('power') || s.includes('energy'))                  return 'E65100'; // orange
  if (s.includes('oil') || s.includes('gas'))                       return '37474F'; // dark blue-gray
  if (s.includes('industrial') || s.includes('park'))               return '6A1B9A'; // purple
  if (s.includes('smart') || s.includes('city'))                    return '1976D2'; // medium blue
  if (s.includes('transport'))                                      return '795548'; // brown
  return '5F5E5A'; // default gray
}

// ── 메인 빌더 ────────────────────────────────────────────────────────────
async function buildReport(payloadPath, outputPath) {
  // 페이로드 로드
  let payload;
  try {
    const raw = fs.readFileSync(payloadPath, 'utf8');
    payload = JSON.parse(raw);
  } catch (err) {
    console.error(`[SA-8] 페이로드 읽기 실패: ${err.message}`);
    process.exit(1);
  }

  const plans = payload.plans || {};
  const planIds = Object.keys(plans);
  console.log(`[SA-8] 페이로드 로드 완료 — 플랜: ${planIds.length}개, 기사: ${payload.total_articles || 0}건`);

  // 문서 콘텐츠 조립
  const children = [];

  // 1. 표지
  children.push(...buildCoverPage(payload));

  // 2. Executive Summary
  children.push(new Paragraph({ children: [new PageBreak()] }));
  children.push(...buildExecutiveSummary(payload));

  // 3. ★ v2.0: 품질평가 섹션 (payload에 quality_score가 있을 때만)
  const qualityElems = buildQualitySection(payload);
  if (qualityElems.length > 0) {
    children.push(new Paragraph({ children: [new PageBreak()] }));
    children.push(...qualityElems);
  }

  // 4. 플랜별 섹션 (Layer1 + Layer2)
  for (let i = 0; i < planIds.length; i++) {
    const pid = planIds[i];
    children.push(new Paragraph({ children: [new PageBreak()] }));
    children.push(H1(`플랜 분석 [${i + 1}/${planIds.length}]: ${plans[pid].plan_name_ko || pid}`, C.navy));
    children.push(...buildPlanSection(pid, plans[pid], i));
  }

  // 5. 문서 생성
  const doc = new Document({
    styles: {
      default: { document: { run: { font: 'Arial', size: 20 } } },
      paragraphStyles: [
        { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
          run: { size: 32, bold: true, font: 'Arial' },
          paragraph: { spacing: { before: 360, after: 160 }, outlineLevel: 0 } },
        { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
          run: { size: 26, bold: true, font: 'Arial' },
          paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 } },
        { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
          run: { size: 22, bold: true, font: 'Arial' },
          paragraph: { spacing: { before: 180, after: 80 }, outlineLevel: 2 } },
      ]
    },
    numbering: {
      config: [
        { reference: 'bullets',
          levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
        { reference: 'numbers',
          levels: [{ level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      ]
    },
    sections: [{
      properties: {
        page: {
          size: { width: 11906, height: 16838 }, // A4
          margin: { top: 1080, right: 1080, bottom: 1080, left: 1080 }
        }
      },
      children
    }]
  });

  // 파일 저장
  const buffer = await Packer.toBuffer(doc);
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, buffer);
  console.log(`[SA-8] ✅ 보고서 생성 완료: ${outputPath} (${(buffer.length / 1024).toFixed(0)} KB)`);
}

// ── 진입점 ───────────────────────────────────────────────────────────────
const [,, payloadArg, outputArg] = process.argv;
if (!payloadArg || !outputArg) {
  console.error('Usage: node build_mi_report_sa8.js <payload.json> <output.docx>');
  process.exit(1);
}

buildReport(payloadArg, outputArg).catch(err => {
  console.error(`[SA-8] 치명적 오류: ${err.message}`);
  console.error(err.stack);
  process.exit(1);
});
