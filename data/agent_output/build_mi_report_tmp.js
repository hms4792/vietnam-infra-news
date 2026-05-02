/**
 * SA-8 generate_mi_report.py 대응 — 주간 MI 리포트 자동 생성 스크립트
 * 
 * 기능:
 *   - knowledge_index.json에서 플랜별 KPI 기준값 읽기
 *   - Excel DB에서 최신 1주 기사 추출
 *   - KPI 변동사항 노란색 하이라이트 표시
 *   - 플랜별 섹션 자동 구성
 *
 * 출력: VN_Infra_MI_Weekly_Report_YYYYMMDD.docx
 *
 * 참고: 이 파일은 SA-8 Python 스크립트가 node.js로 호출하는 방식으로 통합됨
 */

const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  HeadingLevel, AlignmentType, BorderStyle, WidthType, ShadingType,
  LevelFormat, PageNumber, PageBreak
} = require('docx');
const fs = require('fs');

// ── 색상 팔레트 (모든 색상은 6자리 hex) ──────────────────────────────────
const C = {
  teal:     '0d9488', tealL:    'E1F5EE', tealD:    '085041',
  blue:     '185FA5', blueL:    'E6F1FB',
  amber:    '854F0B', amberL:   'FAEEDA',
  coral:    '993C1D', coralL:   'FAECE7',
  green:    '3B6D11', greenL:   'EAF3DE',
  gray:     '5F5E5A', grayL:    'F7F5F0',
  white:    'FFFFFF', black:    '1A1A1A',
  navy:     '0C2340',
  // ★ KPI 변동 강조 — 노란색 하이라이트
  yellow:   'FFFF00', yellowL:  'FFFDE7', yellowM:  'FFF176',
  // ★ v3.2: 새 AI 논평 강조 — 청록색 하이라이트
  newAI:    'E1F5EE', newAIB:   '0D9488', newAIT:   '085041',
};

// ── 테이블 보더 헬퍼 ──────────────────────────────────────────────────────
const bd  = (color = 'CCCCCC') => ({ style: BorderStyle.SINGLE, size: 1, color });
const bds = (color = 'CCCCCC') => ({
  top: bd(color), bottom: bd(color), left: bd(color), right: bd(color)
});
const noBorder = { top: bd('FFFFFF'), bottom: bd('FFFFFF'), left: bd('FFFFFF'), right: bd('FFFFFF') };
const cm = { top: 100, bottom: 100, left: 140, right: 140 };

// ── 기본 단락 생성 헬퍼 ──────────────────────────────────────────────────
function P(text, opts = {}) {
  return new Paragraph({
    spacing: { after: 80 },
    children: [new TextRun({ text, font: 'Arial', size: 20, color: C.black, ...opts })]
  });
}

function SP(n = 1) {
  return new Paragraph({ spacing: { after: 80 * n }, children: [new TextRun('')] });
}

// ── 헤딩 ──────────────────────────────────────────────────────────────────
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
    spacing: { before: 180, after: 80 },
    children: [new TextRun({ text, font: 'Arial', size: 22, bold: true, color })]
  });
}

// ── 구분선 ────────────────────────────────────────────────────────────────
function DIV(color = C.teal) {
  return new Paragraph({
    spacing: { before: 140, after: 140 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 4, color, space: 1 } },
    children: []
  });
}

// ── 강조 박스 (노란색 하이라이트 포함) ──────────────────────────────────
/**
 * KPI 변동 알림용 노란색 하이라이트 단락
 * @param {string} label  - "▲ 변동" 등 라벨
 * @param {string} text   - 상세 내용
 * @param {boolean} isNew - true = 신규 변동 (노란색), false = 기준값 (회색)
 */
function KPI_ROW(label, text, isNew = false) {
  const fillColor = isNew ? C.yellowM : C.grayL;
  const textColor = isNew ? C.amber   : C.gray;
  return new Paragraph({
    spacing: { before: 40, after: 40 },
    indent: { left: 200 },
    shading: { fill: fillColor, type: ShadingType.CLEAR },
    children: [
      new TextRun({ text: label + ' ', font: 'Arial', size: 19, bold: true, color: textColor }),
      new TextRun({ text,             font: 'Arial', size: 19,              color: C.black  }),
    ]
  });
}

// ── 테이블 헬퍼 ───────────────────────────────────────────────────────────
/**
 * KPI 테이블 생성
 * @param {string[]} headers  - 헤더 컬럼명 배열
 * @param {Array[]}  rows     - 행 데이터 배열, 각 행은 [셀값, 셀값, ...] 또는
 *                              [{text, changed}, ...] 형태
 *                              changed=true면 해당 셀 노란색 하이라이트
 * @param {number[]} widths   - 각 컬럼 너비 (DXA, 합계 = 9360)
 */
function KPI_TABLE(headers, rows, widths) {
  const totalW = widths.reduce((a, b) => a + b, 0);
  const hdrBg  = C.navy;

  const hdrRow = new TableRow({
    tableHeader: true,
    children: headers.map((h, i) => new TableCell({
      borders: bds(C.navy),
      width:   { size: widths[i], type: WidthType.DXA },
      shading: { fill: hdrBg, type: ShadingType.CLEAR },
      margins: cm,
      children: [new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: h, font: 'Arial', size: 19, bold: true, color: C.white })]
      })]
    }))
  });

  const dataRows = rows.map((row, ri) => {
    const rowBg = ri % 2 === 0 ? C.white : C.grayL;
    return new TableRow({
      children: row.map((cell, ci) => {
        // cell이 객체이면 {text, changed} 구조 처리
        const cellText    = typeof cell === 'object' ? cell.text    : cell;
        const cellChanged = typeof cell === 'object' ? cell.changed : false;
        const cellBg      = cellChanged ? C.yellowL : rowBg;

        return new TableCell({
          borders: bds('CCCCCC'),
          width:   { size: widths[ci], type: WidthType.DXA },
          shading: { fill: cellBg, type: ShadingType.CLEAR },
          margins: cm,
          children: [new Paragraph({
            alignment: ci === 0 ? AlignmentType.LEFT : AlignmentType.CENTER,
            children: [new TextRun({
              text: cellChanged ? '★ ' + cellText : cellText,
              font: 'Arial',
              size: 19,
              bold: cellChanged,
              color: cellChanged ? C.amber : C.black
            })]
          })]
        });
      })
    });
  });

  return new Table({
    width:        { size: totalW, type: WidthType.DXA },
    columnWidths: widths,
    rows:         [hdrRow, ...dataRows]
  });
}

// ── 기사 카드 (플랜별 최신 기사) ─────────────────────────────────────────
/**
 * @param {object} article - { date, source, grade, title, summary }
 * @param {boolean} isHighlight - HIGH 등급 기사 여부 (노란색 배경)
 */
function ARTICLE_CARD(article, isHighlight = false) {
  const headerBg = isHighlight ? C.yellowM : C.blueL;
  const headerTx = isHighlight ? C.amber   : C.blue;

  return [
    new Table({
      width:        { size: 9360, type: WidthType.DXA },
      columnWidths: [1800, 1800, 1800, 3960],
      rows: [
        new TableRow({
          children: [
            // 날짜
            new TableCell({
              borders: bds('AAAAAA'),
              width:   { size: 1800, type: WidthType.DXA },
              shading: { fill: headerBg, type: ShadingType.CLEAR },
              margins: cm,
              children: [new Paragraph({
                children: [new TextRun({ text: article.date, font: 'Arial', size: 18, bold: true, color: headerTx })]
              })]
            }),
            // 출처
            new TableCell({
              borders: bds('AAAAAA'),
              width:   { size: 1800, type: WidthType.DXA },
              shading: { fill: headerBg, type: ShadingType.CLEAR },
              margins: cm,
              children: [new Paragraph({
                children: [new TextRun({ text: article.source, font: 'Arial', size: 18, color: headerTx })]
              })]
            }),
            // 등급
            new TableCell({
              borders: bds('AAAAAA'),
              width:   { size: 1800, type: WidthType.DXA },
              shading: { fill: isHighlight ? C.yellowL : C.grayL, type: ShadingType.CLEAR },
              margins: cm,
              children: [new Paragraph({
                alignment: AlignmentType.CENTER,
                children: [new TextRun({
                  text:  isHighlight ? '★ HIGH' : article.grade,
                  font:  'Arial', size: 18,
                  bold:  isHighlight,
                  color: isHighlight ? C.amber : C.gray
                })]
              })]
            }),
            // 제목
            new TableCell({
              borders: bds('AAAAAA'),
              width:   { size: 3960, type: WidthType.DXA },
              shading: { fill: headerBg, type: ShadingType.CLEAR },
              margins: cm,
              children: [new Paragraph({
                children: [new TextRun({ text: article.title, font: 'Arial', size: 18, bold: true, color: C.black })]
              })]
            }),
          ]
        }),
        // 요약행
        new TableRow({
          children: [
            new TableCell({
              columnSpan: 4,
              borders:    bds('CCCCCC'),
              width:      { size: 9360, type: WidthType.DXA },
              shading:    { fill: C.white, type: ShadingType.CLEAR },
              margins:    { top: 80, bottom: 80, left: 200, right: 140 },
              children: [new Paragraph({
                children: [new TextRun({ text: article.summary, font: 'Arial', size: 19, color: C.black })]
              })]
            })
          ]
        })
      ]
    }),
    SP(0.5)
  ];
}

// ── 노란색 변동 배너 ──────────────────────────────────────────────────────
function CHANGE_BANNER(text) {
  return new Paragraph({
    spacing: { before: 80, after: 80 },
    shading: { fill: C.yellowL, type: ShadingType.CLEAR },
    border: {
      left:   { style: BorderStyle.SINGLE, size: 8, color: C.amber, space: 1 },
      bottom: { style: BorderStyle.SINGLE, size: 2, color: C.amber, space: 1 },
      top:    { style: BorderStyle.SINGLE, size: 2, color: C.amber, space: 1 },
      right:  { style: BorderStyle.SINGLE, size: 2, color: C.amber, space: 1 },
    },
    indent: { left: 240 },
    children: [
      new TextRun({ text: '▲ KPI 변동 ', font: 'Arial', size: 19, bold: true, color: C.amber }),
      new TextRun({ text,               font: 'Arial', size: 19,              color: C.black }),
    ]
  });
}

// ════════════════════════════════════════════════════════════════════════════
//  보고서 데이터 정의 (SA-8이 Excel/JSON에서 읽어오는 부분을 여기서 시뮬레이션)
//  실제 SA-8 Python 스크립트는 이 데이터를 동적으로 채운 후 이 JS를 호출함
// ════════════════════════════════════════════════════════════════════════════

const REPORT_DATE  = '2026년 4월 24일';
// ★ v3.2: true면 이번 주 새 AI 논평 생성됨 → 청록 하이라이트
const EXEC_SUMMARY_IS_NEW = true;  // Python 자동 설정
const REPORT_WEEK  = '2026-W17';
const TOTAL_ARTS   = 157;
const PLAN_COUNT   = 12;

/**
 * 플랜별 KPI 데이터
 * changed: true → 직전 주 대비 변동 있음 → 노란색 하이라이트 표시
 */
const PLAN_DATA = [
  // ── 1. VN-WW-2030 폐수처리 ─────────────────────────────────────────────
  {
    id: 'VN-WW-2030', sector: 'Waste Water',
    title_ko: '폐수처리 인프라 국가 마스터플랜 2021~2030',
    decision: 'Decision 1354/QD-TTg',
    area: 'Environment',
    kpi: [
      ['도시 폐수처리율', { text: '~29% → 50% (하노이)', changed: false }, '85% (2030)'],
      ['신규 WWTP 용량', { text: '약 800,000 m³/일', changed: false }, '2,900,000 m³/일'],
      ['ODA 연계 투자', { text: '$690M (옌짜 준공 확정)', changed: false }, '$2.5B+'],
    ],
    kpi_changes: [], // 이번 주 변동 없음
    articles: [
      {
        date: '2026-03-17', source: 'VWSA', grade: 'MEDIUM',
        title: 'Wastewater Treatment Market Growth at Vietnam Water Week 2026',
        summary: '베트남 수도협회 주최 베트남 워터위크 2026 행사 안내. 2026년 9월 하노이 개최 예정. 도시화 가속으로 폐수처리 수요 급증, 국내외 기업 참가 예정.'
      },
      {
        date: '2025-08-20', source: 'VietnamPlus', grade: 'HIGH',
        title: 'Yen Xa WWTP 공식 준공 — 270,000m³/일 북부 최대 규모',
        summary: '하노이 옌짜 폐수처리장 공식 준공. JICA ODA $690M, 처리율 29%→50% 향상 예상.'
      },
    ]
  },

  // ── 2. VN-SWM-NATIONAL-2030 고형폐기물 ────────────────────────────────
  {
    id: 'VN-SWM-NATIONAL-2030', sector: 'Solid Waste',
    title_ko: '전국 고형폐기물 통합관리 국가전략 2025/2050',
    decision: 'Decision 491/QD-TTg',
    area: 'Environment',
    kpi: [
      ['도시 폐기물 수거율', { text: '95% (2025 목표)', changed: false }, '100% (2030)'],
      ['WtE 소각 비율',     { text: '30% (2025 목표)', changed: false }, '50% (2030)'],
      ['매립 의존율',       { text: '속선 WtE 가동으로 감소 중', changed: false }, '30% 이하'],
    ],
    kpi_changes: [],
    articles: [
      {
        date: '2026-01-02', source: 'VnExpress English', grade: 'MEDIUM',
        title: 'Ca Mau Province approves $70M waste-to-energy plant',
        summary: '까마우성, 600톤/일 처리 규모 $70M WtE 발전소 승인. 지방 매립 부담 감소 목적.'
      },
      {
        date: '2025-10-15', source: 'theinvestor.vn', grade: 'HIGH',
        title: 'Soc Son WtE Plant — Vietnam largest, world 2nd (90MW)',
        summary: '속선 WtE 발전소 정식 준공. 4,000~5,000톤/일, 90MW. 세계 2위 규모. 하노이 폐기물 70% 처리.'
      },
    ]
  },

  // ── 3. VN-PWR-PDP8 전력개발계획 ───────────────────────────────────────
  {
    id: 'VN-PWR-PDP8', sector: 'Power',
    title_ko: '제8차 국가전력개발계획 (PDP8)',
    decision: 'Decision 500/QD-TTg 2023 → Decision 768 개정 2025.04',
    area: 'Energy Develop.',
    kpi: [
      ['해상풍력 목표',  { text: '17,032 MW (Decision 768 개정)', changed: true }, '2030 달성 목표'],
      ['원자력 재개',    { text: '4,000 MW, 2035년 목표 확정',   changed: true }, '신규 추가'],
      ['총 투자 규모',   { text: '$134.7B (전체 PDP8 기간)',      changed: false }, '2030~2050'],
      ['LNG 인수보장',   { text: 'Decree 100 — 65% 법제화',      changed: false }, 'Bankability 확보'],
    ],
    kpi_changes: [
      '해상풍력 목표 6GW → 17,032MW로 3배 상향 (Decision 768, 2025.04.15)',
      '원자력 재개 — 4,000MW, 2035년 목표 신규 추가 (Decision 768)',
    ],
    articles: [
      {
        date: '2026-04-10', source: 'PV Tech', grade: 'HIGH',
        title: 'Vietnam accelerates offshore wind targets under PDP8 revision',
        summary: 'Decision 768 이후 해상풍력 개발 가속. Equinox, Orsted 등 글로벌 개발사 관심 증가.'
      },
      {
        date: '2026-03-20', source: 'Energy Monitor', grade: 'MEDIUM',
        title: 'DPPA direct power purchase opens Vietnam renewables market',
        summary: 'DPPA 직접구매 시장 개방으로 RE100 기업 진입 가능. 삼성·인텔 등 FDI 기업 직접계약 추진 중.'
      },
    ]
  },

  // ── 4. VN-TRAN-2055 국가교통마스터플랜 ───────────────────────────────
  {
    id: 'VN-TRAN-2055', sector: 'Transport',
    title_ko: '국가 교통 인프라 마스터플랜 2021~2030 비전 2050',
    decision: 'Decision 1454/QD-TTg',
    area: 'Urban Develop.',
    kpi: [
      ['고속도로 총연장', { text: '1,892 km (2025 실적)', changed: false }, '5,000 km (2030)'],
      ['롱탄공항 개항',   { text: '2026년 6월 상업운영 예정', changed: true }, '1단계 25M PAX/년'],
      ['링로드4 진행',    { text: '2026.6 병행도로 개통',    changed: false }, '전체 2027년 완공'],
    ],
    kpi_changes: [
      '롱탄공항 개항 — 당초 2025.12 → 2026.06으로 상업운항 개시 일정 변경',
    ],
    articles: [
      {
        date: '2026-04-15', source: 'Nikkei Asia', grade: 'HIGH',
        title: 'Long Thanh Airport commercial ops delayed to June 2026',
        summary: '롱탄공항 상업운항 2026년 6월로 확정. 노동력 부족(약 6,000명) 및 비용 상승이 주요 원인.'
      },
    ]
  },

  // ── 5. VN-WAT-URBAN 도시 상수도 ───────────────────────────────────────
  {
    id: 'VN-WAT-URBAN', sector: 'Water Supply/Drainage',
    title_ko: '도시 상수도 공급 인프라 개발계획',
    decision: 'Decision 2147/QD-TTg',
    area: 'Environment',
    kpi: [
      ['도시 안전 상수 보급률', { text: '95% (2025 실적)', changed: false }, '100% (2030)'],
      ['투자 필요액',           { text: '$10~20B (2033년까지)', changed: true }, '민간 PPP 유치 핵심'],
      ['하수처리율',            { text: '현재 18% → 2033년 70% 목표', changed: true }, '대규모 투자 필요'],
    ],
    kpi_changes: [
      '도시 하수처리율 목표 상향 — 2030년 70% → 2033년 70% (달성 기한 연장)',
      '민간투자 필요액 $10~20B 공식 발표 (2026년 Q1 정부 보고서)',
    ],
    articles: [
      {
        date: '2026-03-01', source: 'Water Tech Online', grade: 'MEDIUM',
        title: 'Vietnam water sector requires $10-20B private investment by 2033',
        summary: '베트남 상하수도 부문 2033년까지 $10~20B 민간 투자 필요. PPP 구조 개선 시급.'
      },
    ]
  },

  // ── 6. VN-ENV-IND-1894 환경산업개발 ───────────────────────────────────
  {
    id: 'VN-ENV-IND-1894', sector: 'Industrial Parks',
    title_ko: '환경산업 발전 프로그램 2025~2030',
    decision: 'Decision 1894/QD-TTg 2024',
    area: 'Environment',
    kpi: [
      ['환경기술 수출목표',   { text: '연 $500M (2030)', changed: false }, '장기 목표'],
      ['GVC 편입 기업 수',   { text: '현재 집계 중', changed: false }, '100개사 (2030)'],
      ['녹색산업단지 전환율', { text: '파일럿 단계', changed: false }, '50% (2030)'],
    ],
    kpi_changes: [],
    articles: [
      {
        date: '2026-02-10', source: 'Vietnam Briefing', grade: 'MEDIUM',
        title: 'Vietnam environmental industry policy push under Decision 1894',
        summary: 'Decision 1894 이행을 위한 세부 로드맵 발표. 고형폐기물·폐수·상하수도·산업단지 4개 부문 집중.'
      },
    ]
  },
];

// ── 워크플로 현황 (작업 1용) ──────────────────────────────────────────────
const WORKFLOW_STATUS = {
  completed: [
    { id: 'SA-1', name: '뉴스 수집 에이전트', desc: 'RSS + NewsData.io + Jina.ai(specialist_crawler)', status: '완료' },
    { id: 'SA-2', name: '번역 에이전트', desc: 'Google Translate MyMemory API + deep-translator, 3개국어', status: '완료' },
    { id: 'SA-3', name: 'DB 업데이트 에이전트', desc: 'ExcelUpdater.update_all() — 9개 시트 갱신', status: '완료' },
    { id: 'SA-4', name: '대시보드 빌드 에이전트', desc: 'build_dashboard.py → docs/index.html', status: '완료' },
    { id: 'SA-5', name: '지식베이스 에이전트', desc: 'knowledge_index.json v2.1 — 27개 마스터플랜', status: '완료' },
    { id: 'SA-6', name: '품질검증 에이전트', desc: 'quality_context_agent.py — Province 분류·등급 산정', status: '완료' },
    { id: 'SA-9', name: 'Jina 크롤 에이전트 (설계)', desc: 'specialist_crawler.py v4.0 — Jina.ai Reader API', status: '완료' },
    { id: 'Dual', name: '이중 파이프라인 분리', desc: 'Claude(docs/,data/) / Genspark(docs/genspark/,data/genspark/) / docs/shared/', status: '완료' },
    { id: 'NEWSDATA', name: 'NewsData.io 통합', desc: '/api/1/latest — Province+섹터 교차쿼리, 200건/일', status: '완료' },
  ],
  pending: [
    { id: 'SA-7', name: '맥락분석 에이전트', desc: 'context_analyzer.py — 규칙→Claude-haiku 2단계 분석', priority: '높음', session: '세션3', cost: '$0.06/월' },
    { id: 'SA-8', name: 'MI 리포트 에이전트', desc: 'generate_mi_report.py — docx 자동생성 + 노란색 KPI 변동 표시', priority: '높음', session: '세션4', cost: '$0.08/월' },
    { id: 'SA-8-EMAIL', name: '이메일 첨부 발송', desc: 'MI 리포트 생성 후 자동 이메일 첨부 발송', priority: '보통', session: '세션4', cost: '$0' },
    { id: 'PDP8-ID', name: 'PDP8 계층형 ID 교체', desc: 'agent_pipeline.py — Genspark PDP8 Sub-plan ID → VN-PWR-PDP8-xxx', priority: '긴급', session: '즉시', cost: '$0' },
    { id: 'SOURCE-FLD', name: 'source 필드 fallback', desc: 'agent_pipeline.py — dict.get() → Python or 연산자로 교체', priority: '긴급', session: '즉시', cost: '$0' },
    { id: 'NEWSDATA-Q', name: 'NEWSDATA_QUERIES 5가지 방법 반영', desc: 'news_collector.py — Web_Tracking_Guide 기준 플랜별 쿼리 완전 업데이트', priority: '높음', session: '세션1', cost: '$0' },
    { id: 'KI-24', name: 'knowledge_index 24개 완성', desc: 'Genspark 마스터플랜 이식 — 현재 27개 초안 → 검증 완료', priority: '보통', session: '세션2', cost: '$0' },
    { id: 'GDRIVE', name: 'Google Drive MCP 연동', desc: 'SA-5 Google Drive 읽기 — Vietnam_Infra_Knowledge/ 공유폴더', priority: '보통', session: '세션3', cost: '$0' },
    { id: 'TIMELINE', name: 'Time History Line 구현', desc: 'Excel Timeline 시트 — 마스터플랜×날짜×단계 자동 기록', priority: '낮음', session: '세션5', cost: '$0' },
  ]
};

// ════════════════════════════════════════════════════════════════════════════
//  문서 조립
// ════════════════════════════════════════════════════════════════════════════

// ── 커버 페이지 요소 ──────────────────────────────────────────────────────
function buildCover() {
  return [
    SP(6),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 120 },
      children: [new TextRun({ text: 'VIETNAM INFRASTRUCTURE', font: 'Arial', size: 48, bold: true, color: C.navy })]
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 80 },
      children: [new TextRun({ text: 'MARKET INTELLIGENCE REPORT', font: 'Arial', size: 36, bold: true, color: C.teal })]
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 80 },
      children: [new TextRun({ text: '베트남 인프라 시장 동향 주간 보고서', font: 'Arial', size: 24, color: C.gray })]
    }),
    DIV(C.teal),
    SP(2),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 60 },
      children: [new TextRun({ text: REPORT_DATE, font: 'Arial', size: 28, bold: true, color: C.navy })]
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 60 },
      children: [new TextRun({ text: `주간호 ${REPORT_WEEK} │ SA-8 자동생성`, font: 'Arial', size: 20, color: C.gray })]
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { after: 60 },
      children: [new TextRun({ text: `수록 기사: ${TOTAL_ARTS}건 │ 마스터플랜: ${PLAN_COUNT}개`, font: 'Arial', size: 20, color: C.gray })]
    }),
    SP(2),
    // KPI 변동 안내 배너
    new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 120, after: 80 },
      shading: { fill: C.yellowL, type: ShadingType.CLEAR },
      children: [
        new TextRun({ text: '★ ', font: 'Arial', size: 22, bold: true, color: C.amber }),
        new TextRun({ text: '노란색 강조 = 직전 주 대비 KPI 변동사항', font: 'Arial', size: 22, bold: true, color: C.amber }),
        new TextRun({ text: ' ★', font: 'Arial', size: 22, bold: true, color: C.amber }),
      ]
    }),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}

// ── 섹션 1: 워크플로 현황표 ───────────────────────────────────────────────
function buildWorkflowStatus() {
  const elems = [
    H1('Section 1 — 파이프라인 구축 현황', C.navy),
    DIV(C.navy),
    SP(),

    H2('1.1 완료된 작업', C.green),
    SP(0.5),
    KPI_TABLE(
      ['SA ID', '에이전트명', '설명', '상태'],
      WORKFLOW_STATUS.completed.map(w => [w.id, w.name, w.desc, '✅ 완료']),
      [700, 1800, 5360, 1500]
    ),
    SP(),

    H2('1.2 추가 작업 목록 (우선순위순)', C.coral),
    SP(0.5),
    KPI_TABLE(
      ['SA ID', '에이전트명', '설명', '우선순위', '예상 세션', 'API 비용'],
      WORKFLOW_STATUS.pending.map(w => [
        w.id, w.name, w.desc,
        { text: w.priority, changed: w.priority === '긴급' },
        w.session, w.cost
      ]),
      [700, 1500, 3760, 900, 900, 800]
    ),
    SP(),
    new Paragraph({ children: [new PageBreak()] }),
  ];
  return elems;
}

// ── 섹션 2: Executive Summary ─────────────────────────────────────────────
function buildExecutiveSummary() {
  // ★ v3.2: EXEC_SUMMARY_IS_NEW=true면 청록 박스로 Executive Summary 감쌈
  const execBg = (typeof EXEC_SUMMARY_IS_NEW !== 'undefined' && EXEC_SUMMARY_IS_NEW)
                 ? C.newAI : C.grayL;
  return [
    H1('Section 2 — Executive Summary', C.navy),
    DIV(C.navy),
    SP(),

    H2('2.1 핵심 동향 요약 (2026년 4월 기준)', C.blue),
    SP(0.5),

    KPI_TABLE(
      ['영역', '핵심 내용'],
      [
        ['환경 인프라',
         '하노이 옌짜 WWTP 준공(270,000m³/일, 2025.8) — 북부 최대. 속선 WtE(90MW) 가동. 도시 하수처리율 18%→70% 목표에 $10~20B 투자 필요.'],
        ['에너지 (★변동)',
         '★PDP8 개정(Decision 768) — 해상풍력 17,032MW(3배 상향), 원자력 4,000MW 재개. DPPA 시장 개방. LNG Decree 100 bankability 확보.'],
        ['교통 (★변동)',
         '★롱탄공항 상업운항 2026.06 확정(노동력 6,000명 부족). 링로드4 병행도로 2026.6 개통. 고속도로 1,892km→5,000km(2030) 목표.'],
        ['하노이 도시개발',
         'Decision 1668 마스터플랜 확정. BRG 동아인 스마트시티($4.2B) 착공. 호아락 하이테크 460ha 확장.'],
      ],
      [1800, 7560]
    ),
    SP(),

    CHANGE_BANNER('이번 주 KPI 변동 플랜: VN-PWR-PDP8 (해상풍력/원자력 상향) │ VN-TRAN-2055 (롱탄 개항 일정) │ VN-WAT-URBAN (투자필요액 발표)'),
    SP(),
    new Paragraph({ children: [new PageBreak()] }),
  ];
}


// ── v3.2: 새 AI 논평 표시 박스 (청록색 하이라이트) ─────────────────────────
function AI_INSIGHT_BOX(newsAnalysis, insight, isNew = false) {
  const bgColor  = isNew ? C.newAI  : C.grayL;   // 새 논평: 청록, 재사용: 회색
  const bdColor  = isNew ? C.newAIB : 'CCCCCC';   // 좌측 보더 색상
  const labelTxt = isNew ? '★ NEW  AI 분석 (이번 주 신규 생성)' : 'AI 분석 (이전 논평 유지)';
  const labelClr = isNew ? C.newAIT : C.gray;

  const elems = [];

  // 레이블 헤더
  elems.push(new Paragraph({
    spacing: { after: 60 },
    border: { left: { style: BorderStyle.SINGLE, size: 8, color: bdColor, space: 1 } },
    shading: { fill: bgColor, type: ShadingType.CLEAR },
    indent: { left: 120 },
    children: [
      new TextRun({
        text: labelTxt,
        font: 'Arial', size: 17, bold: true,
        color: labelClr,
      }),
    ],
  }));

  // 뉴스 분석 본문
  if (newsAnalysis) {
    elems.push(new Paragraph({
      spacing: { after: 80 },
      border: { left: { style: BorderStyle.SINGLE, size: 8, color: bdColor, space: 1 } },
      shading: { fill: bgColor, type: ShadingType.CLEAR },
      indent: { left: 120 },
      children: [
        new TextRun({
          text: newsAnalysis,
          font: 'Arial', size: 19,
          color: C.black,
        }),
      ],
    }));
  }

  // Expert Insight (있을 때만)
  if (insight) {
    elems.push(new Paragraph({
      spacing: { after: 60 },
      border: { left: { style: BorderStyle.SINGLE, size: 8, color: bdColor, space: 1 } },
      shading: { fill: bgColor, type: ShadingType.CLEAR },
      indent: { left: 120 },
      children: [
        new TextRun({ text: '💡 Expert Insight  ', font: 'Arial', size: 18, bold: true, color: isNew ? C.newAIT : C.gray }),
        new TextRun({ text: insight, font: 'Arial', size: 18, color: C.black }),
      ],
    }));
  }

  return elems;
}

// ── 섹션 3: 플랜별 상세 분석 ─────────────────────────────────────────────
function buildPlanSections() {
  const elems = [
    H1('Section 3 — 마스터플랜별 상세 분석', C.navy),
    DIV(C.navy),
    SP(),
  ];

  PLAN_DATA.forEach((plan, idx) => {
    const hasChanges = plan.kpi_changes.length > 0;

    // 플랜 헤더
    elems.push(H2(`${idx + 1}. [${plan.id}] ${plan.title_ko}`, hasChanges ? C.amber : C.blue));
    elems.push(P(`${plan.decision} │ 섹터: ${plan.sector} │ 영역: ${plan.area}`, { color: C.gray, size: 18 }));
    elems.push(SP(0.5));

    // KPI 변동 배너 (변동 있는 경우)
    if (hasChanges) {
      plan.kpi_changes.forEach(change => {
        elems.push(CHANGE_BANNER(change));
      });
      elems.push(SP(0.5));
    }

    // KPI 테이블
    elems.push(H3('■ KPI 현황', C.teal));
    elems.push(KPI_TABLE(
      ['지표', '현황 (2025~2026)', '목표'],
      plan.kpi,
      [2800, 3680, 2880]
    ));
    elems.push(SP(0.5));

    // 최신 기사
    elems.push(H3(`■ 최신 기사 동향 (${plan.articles.length}건)`, C.teal));
    plan.articles.forEach(art => {
      const isHigh = art.grade === 'HIGH';
      elems.push(...ARTICLE_CARD(art, isHigh));
    });
    elems.push(SP(0.5));

    // ★ v3.2: AI 논평 박스 (새 논평 = 청록 하이라이트, 이전 재사용 = 회색)
    const hasAI = plan.news_analysis || plan.insight;
    if (hasAI) {
      const isNewAI = plan.analysis_is_new === true;
      elems.push(H3('■ AI 분석 & Expert Insight', C.teal));
      elems.push(...AI_INSIGHT_BOX(plan.news_analysis || '', plan.insight || '', isNewAI));
    }

    elems.push(DIV(C.grayL));
    elems.push(SP());
  });

  return elems;
}

// ── 섹션 4: NEWSDATA_QUERIES 업데이트 안내 ───────────────────────────────
function buildNewsdataGuide() {
  return [
    new Paragraph({ children: [new PageBreak()] }),
    H1('Section 4 — NEWSDATA_QUERIES 5가지 수집 방법', C.navy),
    DIV(C.navy),
    SP(),
    P('Web_Tracking_Guide 기준으로 news_collector.py를 업데이트해야 하는 5가지 방법 요약입니다.', { bold: true }),
    SP(0.5),

    KPI_TABLE(
      ['방법', '도구/파일', '설명', '주기', '플랜 커버'],
      [
        ['방법1', 'news_collector.py\nNEWSDATA_QUERIES', 'NewsData.io /api/1/latest — 7개 섹터 × Province 교차쿼리 (마스터플랜 키워드 반영)', '매일', '전체 12개 플랜'],
        ['방법2', 'specialist_crawler.py\n(Jina.ai Reader API)', 'theinvestor.vn, VIR 등 전문미디어 직접 크롤 — 차단 우회', '주 1회 (토)', 'PDP8, TRAN, WW'],
        ['방법3', 'quality_context_agent.py\n(SA-6)', '기수집 기사 재분류 — Province unclassified 보정, 등급 재산정', '매일', '전체 플랜 (DB 보정)'],
        ['방법4', 'backfill_newsdata.py\n(supplement_newsdata.py)', '/api/1/latest로 최신 1주 보완 수집 — 과거 소급 X', '주 1회', '7개 섹터 전체'],
        ['방법5', '웹 검색 수동 점검\n(월 1회)', 'Decision/KPI 변동 수동 확인 — SA-8 보고서 KPI 변동 표시에 활용', '월 1회', 'PDP8, TRAN, WAT 등'],
      ],
      [700, 1800, 3460, 900, 2500]
    ),
    SP(),
  ];
}

// ════════════════════════════════════════════════════════════════════════════
//  문서 생성 실행
// ════════════════════════════════════════════════════════════════════════════
async function buildReport() {
  const allChildren = [
    ...buildCover(),
    ...buildWorkflowStatus(),
    ...buildExecutiveSummary(),
    ...buildPlanSections(),
    ...buildNewsdataGuide(),
  ];

  const doc = new Document({
    styles: {
      default: {
        document: { run: { font: 'Arial', size: 20 } }
      },
      paragraphStyles: [
        {
          id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
          run: { size: 32, bold: true, font: 'Arial' },
          paragraph: { spacing: { before: 320, after: 160 }, outlineLevel: 0 }
        },
        {
          id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
          run: { size: 26, bold: true, font: 'Arial' },
          paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 }
        },
        {
          id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
          run: { size: 22, bold: true, font: 'Arial' },
          paragraph: { spacing: { before: 180, after: 80 }, outlineLevel: 2 }
        },
      ]
    },
    numbering: {
      config: [
        {
          reference: 'bullets',
          levels: [{
            level: 0, format: LevelFormat.BULLET, text: '•',
            alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 360 } } }
          }]
        }
      ]
    },
    sections: [{
      properties: {
        page: {
          size: { width: 11906, height: 16838 }, // A4
          margin: { top: 1440, right: 1260, bottom: 1440, left: 1260 }
        }
      },
      children: allChildren
    }]
  });

  const buffer = await Packer.toBuffer(doc);
  const outPath = `/mnt/user-data/outputs/VN_Infra_MI_Weekly_Report_${REPORT_DATE.replace(/[년월일\s]/g, '').replace(/\s/g,'')}.docx`;
  fs.writeFileSync(outPath, buffer);
  console.log(`✅ 보고서 생성: ${outPath} (${(buffer.length/1024).toFixed(0)} KB)`);
}

buildReport().catch(console.error);
