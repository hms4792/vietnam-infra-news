'use strict';
/**
 * build_mi_ppt.js — SA-8 PPT 보고서 생성기 v1.1
 * ================================================================
 * v1.1 수정사항 (2026-04-26):
 *   - 하드코딩 경로 /home/claude 제거 → 동적 BASE_DIR 계산
 *   - knowledge_index.json 우선 탐색 (docs/shared → data/shared)
 *   - 파일 없을 경우 graceful degradation (빈 슬라이드 생성)
 *   - sa8_report_payload.json AI 분석 결과 슬라이드 연동
 */
const pptxgen = require('pptxgenjs');
const fs      = require('fs');
const path    = require('path');

// ★ v1.1 핵심: 동적 경로 (하드코딩 /home/claude 제거)
const BASE_DIR   = path.resolve(__dirname, '..');
const SHARED_DIR = path.join(BASE_DIR, 'docs', 'shared');
const DATA_DIR   = path.join(BASE_DIR, 'data');
const AGENT_DIR  = path.join(DATA_DIR, 'agent_output');

// knowledge_index 탐색 경로 (우선순위 순)
const KI_SEARCH = [
    path.join(SHARED_DIR, 'knowledge_index.json'),
    path.join(DATA_DIR, 'shared', 'knowledge_index.json'),
    path.join(DATA_DIR, 'shared', 'layer1_data.json'),
    path.join(AGENT_DIR, 'knowledge_index.json'),
];

const SA8_PAYLOAD_PATH = path.join(AGENT_DIR, 'sa8_report_payload.json');
const TODAY_STR = new Date().toISOString().slice(0,10).replace(/-/g,'');
const OUT_PATH  = path.join(BASE_DIR, 'docs', `VN_Infra_MI_Weekly_Report_${TODAY_STR}.pptx`);

// ── 안전한 JSON 로드 ─────────────────────────────────────────────────────
function loadJSON(paths, fallback) {
    for (const p of paths) {
        if (fs.existsSync(p)) {
            try {
                const d = JSON.parse(fs.readFileSync(p, 'utf-8'));
                console.log(`  [OK] 로드: ${path.basename(p)}`);
                return d;
            } catch(e) { console.warn(`  [WARN] 파싱실패: ${p}`); }
        }
    }
    console.warn('  [WARN] 파일 없음 → fallback 사용');
    return fallback;
}

console.log('\n[build_mi_ppt.js v1.1] 데이터 로드');
console.log('  BASE_DIR:', BASE_DIR);

const ki_raw = loadJSON(KI_SEARCH, {});
let LAYER1 = {};
if (ki_raw.masterplans) {
    LAYER1 = ki_raw.masterplans;
    Object.entries(LAYER1).forEach(([id,p]) => { p.plan_id = id; });
} else {
    LAYER1 = ki_raw;
    Object.entries(LAYER1).forEach(([id,p]) => { if(p && typeof p==='object') p.plan_id = id; });
}
const SA8 = loadJSON([SA8_PAYLOAD_PATH], { plan_analyses: {} });

const AREA_ORDER = { 'Environment':0, 'Energy Develop.':1, 'Urban Develop.':2 };
const plans = Object.values(LAYER1)
    .filter(p => p && p.plan_id)
    .sort((a,b) => (AREA_ORDER[a.area]??9)-(AREA_ORDER[b.area]??9) || (a.plan_id||'').localeCompare(b.plan_id||''));

console.log(`  플랜 ${plans.length}개 로드 완료`);

// ── 색상 ─────────────────────────────────────────────────────────────────
const C = {
    navy:'0C2340', navyL:'1A3A6B',
    teal:'0D9488', tealM:'14B8A6', tealL:'E1F5EE',
    amber:'854F0B', amberM:'EF9F27', amberL:'FFF176',
    gray:'64748B', grayL:'F8FAFC', grayM:'E2E8F0',
    blue:'185FA5', white:'FFFFFF', black:'1A1A1A',
};
const SCOLOR = {
    'Waste Water':'0D9488','Water Supply/Drainage':'0891B2','Solid Waste':'059669',
    'Power':'F59E0B','Oil & Gas':'78350F','Transport':'3B82F6',
    'Smart City':'7C3AED','Industrial Parks':'DC2626',
};
const ACOLOR = { 'Environment':'0D9488','Energy Develop.':'F59E0B','Urban Develop.':'3B82F6' };
const shadow = () => ({ type:'outer',blur:8,offset:3,angle:135,color:'000000',opacity:0.10 });
const trunc  = (s,n) => { if(!s) return ''; const t=String(s); return t.length>n?t.slice(0,n-1)+'…':t; };
const arr    = v => Array.isArray(v) ? v : [];

// ── 커버 ─────────────────────────────────────────────────────────────────
function addCover(pres) {
    const sl = pres.addSlide();
    sl.background = { color: C.navy };
    sl.addShape(pres.shapes.RECTANGLE,{x:0,y:0,w:0.35,h:5.625,fill:{color:C.teal}});
    sl.addText('VIETNAM INFRASTRUCTURE',{x:0.6,y:0.7,w:8.8,h:0.7,fontSize:32,bold:true,color:C.white,fontFace:'Arial Black',charSpacing:4});
    sl.addText('MARKET INTELLIGENCE REPORT',{x:0.6,y:1.42,w:8.8,h:0.55,fontSize:22,bold:true,color:C.tealM,fontFace:'Arial',charSpacing:2});
    sl.addShape(pres.shapes.RECTANGLE,{x:0.6,y:2.05,w:8,h:0.04,fill:{color:C.tealM}});
    sl.addText('베트남 인프라 시장 동향 주간 보고서',{x:0.6,y:2.2,w:8.8,h:0.45,fontSize:16,color:'A5B4C8',fontFace:'Arial',italic:true});
    const todayLabel = new Date().toLocaleDateString('ko-KR',{year:'numeric',month:'long',day:'numeric'});
    [{label:'발행일',value:todayLabel},{label:'분석 기준',value:'knowledge_index v2.1'},
     {label:'마스터플랜',value:`${plans.length}개 플랜`},{label:'AI 분석',value:'Claude Haiku'}
    ].forEach((c,i) => {
        const x = 0.6+i*2.35;
        sl.addShape(pres.shapes.RECTANGLE,{x,y:2.85,w:2.2,h:1.0,fill:{color:C.navyL},shadow:shadow()});
        sl.addText(c.label,{x,y:2.88,w:2.2,h:0.28,fontSize:9,color:C.tealM,align:'center',fontFace:'Arial'});
        sl.addText(c.value,{x,y:3.16,w:2.2,h:0.5,fontSize:12,bold:true,color:C.white,align:'center',fontFace:'Arial'});
    });
    const byArea = {};
    plans.forEach(p => { (byArea[p.area]=byArea[p.area]||[]).push(p); });
    const areaLabel = {'Environment':'환경 인프라','Energy Develop.':'에너지·전력','Urban Develop.':'도시·교통·산업'};
    Object.entries(byArea).sort((a,b)=>(AREA_ORDER[a[0]]??9)-(AREA_ORDER[b[0]]??9)).forEach(([area,ap],i) => {
        const x=0.6+i*3.1, color=ACOLOR[area]||C.teal;
        sl.addShape(pres.shapes.RECTANGLE,{x,y:4.5,w:2.9,h:0.72,fill:{color,transparency:20}});
        sl.addText(areaLabel[area]||area,{x,y:4.52,w:2.9,h:0.32,fontSize:11,bold:true,color:C.white,align:'center',fontFace:'Arial'});
        sl.addText(`${ap.length}개 플랜`,{x,y:4.84,w:2.9,h:0.32,fontSize:12,color:C.white,align:'center',fontFace:'Arial'});
    });
    sl.addText('hms4792.github.io/vietnam-infra-news',{x:0.6,y:5.32,w:8.8,h:0.22,fontSize:8,color:'445566',fontFace:'Arial'});
}

// ── KPI 대시보드 ─────────────────────────────────────────────────────────
function addKpiDash(pres) {
    const sl = pres.addSlide();
    sl.background = {color:C.grayL};
    sl.addShape(pres.shapes.RECTANGLE,{x:0,y:0,w:10,h:0.72,fill:{color:C.navy}});
    sl.addShape(pres.shapes.RECTANGLE,{x:0,y:0.72,w:10,h:0.05,fill:{color:C.teal}});
    sl.addText('전체 마스터플랜 KPI 목표 현황',{x:0.4,y:0.12,w:9.2,h:0.5,fontSize:22,bold:true,color:C.white,fontFace:'Arial'});
    sl.addText(`${plans.length}개 마스터플랜 · 2030 목표 기준`,{x:6.5,y:0.18,w:3.2,h:0.38,fontSize:10,color:C.tealM,align:'right',fontFace:'Arial'});
    const items = [];
    plans.slice(0,12).forEach(plan => {
        const kpis = arr(plan.kpi_targets);
        if(kpis.length>0) {
            const k = kpis[0];
            items.push({ label:trunc(k.indicator||plan.title_ko,20), target:trunc(k.target_2030||'-',16),
                         current:trunc(k.current||'-',20), color:SCOLOR[plan.sector]||C.teal, changed:k.changed===true });
        }
    });
    items.forEach((item,i) => {
        const col=i%3, row=Math.floor(i/3), x=0.2+col*3.27, y=0.95+row*1.18;
        sl.addShape(pres.shapes.RECTANGLE,{x,y,w:3.1,h:1.08,fill:{color:C.white},shadow:shadow()});
        sl.addShape(pres.shapes.RECTANGLE,{x,y,w:0.06,h:1.08,fill:{color:item.color}});
        sl.addText(item.label,{x:x+0.12,y:y+0.06,w:2.6,h:0.28,fontSize:10,bold:true,color:C.black,fontFace:'Arial'});
        sl.addText(item.target,{x:x+0.12,y:y+0.34,w:1.5,h:0.36,fontSize:15,bold:true,color:item.color,fontFace:'Arial'});
        sl.addText('목표',{x:x+0.12,y:y+0.70,w:0.6,h:0.22,fontSize:8,color:C.gray,fontFace:'Arial'});
        sl.addShape(pres.shapes.RECTANGLE,{x:x+1.72,y:y+0.30,w:1.25,h:0.42,fill:{color:item.changed?C.amberL:C.grayM}});
        sl.addText((item.changed?'★ ':'')+item.current,{x:x+1.72,y:y+0.30,w:1.25,h:0.42,fontSize:9,bold:item.changed,color:item.changed?C.amber:C.black,align:'center',valign:'middle',fontFace:'Arial'});
        sl.addText('현황',{x:x+1.72,y:y+0.72,w:1.25,h:0.2,fontSize:8,color:C.gray,align:'center',fontFace:'Arial'});
    });
    sl.addShape(pres.shapes.RECTANGLE,{x:0,y:5.32,w:10,h:0.3,fill:{color:'FFFDE7'}});
    sl.addText('★ 노란색 = 직전 주 대비 KPI 변동사항',{x:0.3,y:5.34,w:9.4,h:0.26,fontSize:9,color:C.amber,bold:true,fontFace:'Arial'});
}

// ── 영역 구분 ─────────────────────────────────────────────────────────────
function addAreaDiv(pres, area, ap) {
    const sl = pres.addSlide();
    const ac = ACOLOR[area]||C.navy;
    sl.background = {color:ac};
    sl.addShape(pres.shapes.RECTANGLE,{x:6.5,y:0,w:3.5,h:5.625,fill:{color:C.white,transparency:88}});
    const lbl = {'Environment':'환경 인프라','Energy Develop.':'에너지·전력','Urban Develop.':'도시·교통·산업'};
    const en  = {'Environment':'Environment Infrastructure','Energy Develop.':'Energy & Power','Urban Develop.':'Urban & Transport'};
    sl.addText(lbl[area]||area,{x:0.5,y:0.9,w:9,h:1.0,fontSize:44,bold:true,color:C.white,fontFace:'Arial Black'});
    sl.addText(en[area]||area,{x:0.5,y:1.95,w:9,h:0.5,fontSize:18,color:'D0E4F0',fontFace:'Arial',italic:true});
    sl.addShape(pres.shapes.RECTANGLE,{x:0.5,y:2.55,w:6,h:0.04,fill:{color:C.white,transparency:40}});
    sl.addText('포함 마스터플랜',{x:0.5,y:2.75,w:8,h:0.32,fontSize:12,color:C.white,fontFace:'Arial'});
    ap.forEach((plan,i) => {
        const col=i%2, row=Math.floor(i/2), x=0.5+col*4.5, y=3.12+row*0.56;
        sl.addShape(pres.shapes.RECTANGLE,{x,y,w:4.2,h:0.44,fill:{color:C.white,transparency:75}});
        sl.addText(plan.plan_id,{x:x+0.1,y:y+0.01,w:2.1,h:0.22,fontSize:9,bold:true,color:C.white,fontFace:'Arial'});
        sl.addText(trunc(plan.title_ko||plan.plan_id,28),{x:x+0.1,y:y+0.22,w:4.0,h:0.18,fontSize:9,color:'FFFFFF',fontFace:'Arial'});
    });
}

// ── 플랜 메인 ─────────────────────────────────────────────────────────────
function addPlanSlide(pres, plan) {
    const sl = pres.addSlide();
    sl.background = {color:C.grayL};
    const sc = SCOLOR[plan.sector]||C.navy;
    sl.addShape(pres.shapes.RECTANGLE,{x:0,y:0,w:10,h:0.65,fill:{color:C.navy}});
    sl.addShape(pres.shapes.RECTANGLE,{x:0,y:0.65,w:10,h:0.045,fill:{color:sc}});
    sl.addShape(pres.shapes.RECTANGLE,{x:0.3,y:0.08,w:2.0,h:0.34,fill:{color:sc}});
    sl.addText(plan.plan_id,{x:0.3,y:0.08,w:2.0,h:0.34,fontSize:8.5,bold:true,color:C.white,align:'center',valign:'middle',fontFace:'Arial'});
    sl.addText(trunc(plan.title_ko||plan.plan_id,60),{x:2.45,y:0.08,w:7.2,h:0.34,fontSize:14,bold:true,color:C.white,fontFace:'Arial',valign:'middle'});
    sl.addText(trunc(plan.decision||'',60),{x:2.45,y:0.4,w:7.2,h:0.2,fontSize:9,color:'A0B4C8',fontFace:'Arial'});
    // 사업 개요
    sl.addShape(pres.shapes.RECTANGLE,{x:0.2,y:0.82,w:4.6,h:0.3,fill:{color:sc}});
    sl.addText('■ 사업 개요',{x:0.2,y:0.82,w:4.6,h:0.3,fontSize:11,bold:true,color:C.white,fontFace:'Arial',valign:'middle',margin:4});
    sl.addShape(pres.shapes.RECTANGLE,{x:0.2,y:1.12,w:4.6,h:1.6,fill:{color:C.white},shadow:shadow()});
    sl.addShape(pres.shapes.RECTANGLE,{x:0.2,y:1.12,w:0.06,h:1.6,fill:{color:sc}});
    sl.addText(trunc(plan.description_ko||'사업 개요 정보 없음',300),{x:0.32,y:1.14,w:4.44,h:1.56,fontSize:10.5,color:C.black,fontFace:'Arial',valign:'top',wrap:true,margin:4});
    // KPI
    sl.addShape(pres.shapes.RECTANGLE,{x:0.2,y:2.82,w:4.6,h:0.3,fill:{color:sc}});
    sl.addText('■ KPI 목표 및 현황',{x:0.2,y:2.82,w:4.6,h:0.3,fontSize:11,bold:true,color:C.white,fontFace:'Arial',valign:'middle',margin:4});
    const kpis = arr(plan.kpi_targets).slice(0,4);
    if(kpis.length===0) {
        sl.addText('KPI 정보 없음',{x:0.2,y:3.18,w:4.6,h:0.5,fontSize:11,color:C.gray,fontFace:'Arial'});
    } else {
        kpis.forEach((k,i) => {
            const col=i%2, row=Math.floor(i/2), x=0.2+col*2.35, y=3.18+row*1.18;
            const changed = k.changed===true;
            sl.addShape(pres.shapes.RECTANGLE,{x,y,w:2.2,h:1.08,fill:{color:changed?'FFFDE7':C.white},shadow:shadow()});
            sl.addShape(pres.shapes.RECTANGLE,{x,y,w:0.06,h:1.08,fill:{color:changed?C.amberM:sc}});
            sl.addText(trunc(k.indicator||'',24),{x:x+0.1,y:y+0.06,w:2.05,h:0.28,fontSize:9,bold:true,color:C.black,fontFace:'Arial'});
            sl.addText(trunc(k.target_2030||'-',18),{x:x+0.1,y:y+0.34,w:2.05,h:0.36,fontSize:14,bold:true,color:changed?C.amber:sc,fontFace:'Arial'});
            sl.addText((changed?'★ ':'')+trunc(k.current||'-',28),{x:x+0.1,y:y+0.70,w:2.05,h:0.28,fontSize:8.5,color:changed?C.amber:C.gray,fontFace:'Arial'});
        });
    }
    // 프로젝트
    sl.addShape(pres.shapes.RECTANGLE,{x:5.0,y:0.82,w:4.8,h:0.3,fill:{color:C.navy}});
    sl.addText('■ 주요 프로젝트',{x:5.0,y:0.82,w:4.8,h:0.3,fontSize:11,bold:true,color:C.white,fontFace:'Arial',valign:'middle',margin:4});
    const projs = arr(plan.key_projects).slice(0,8);
    if(projs.length===0) {
        sl.addText('프로젝트 정보 없음',{x:5.0,y:1.22,w:4.8,h:0.5,fontSize:11,color:C.gray,fontFace:'Arial'});
    } else {
        const mc = projs.length>4, colW = mc?2.3:4.65;
        projs.forEach((p,i) => {
            const col=mc?Math.floor(i/Math.ceil(projs.length/2)):0;
            const row=mc?i%Math.ceil(projs.length/2):i;
            const x=5.0+col*(colW+0.1), y=1.22+row*0.54;
            sl.addShape(pres.shapes.RECTANGLE,{x,y,w:colW,h:0.5,fill:{color:C.white},shadow:shadow()});
            sl.addShape(pres.shapes.RECTANGLE,{x,y,w:0.06,h:0.5,fill:{color:sc,transparency:30}});
            sl.addText(trunc(p.name||'',30),{x:x+0.1,y:y+0.03,w:colW-0.15,h:0.22,fontSize:9.5,bold:true,color:C.black,fontFace:'Arial'});
            sl.addText(trunc([p.location,p.capacity].filter(Boolean).join(' | '),38),{x:x+0.1,y:y+0.25,w:colW-0.15,h:0.16,fontSize:8.5,color:C.gray,fontFace:'Arial'});
        });
    }
    // SA-8 AI 분석 결과
    const ai = (SA8.plan_analyses||{})[plan.plan_id];
    if(ai && ai.summary) {
        sl.addShape(pres.shapes.RECTANGLE,{x:0,y:5.22,w:10,h:0.41,fill:{color:'EEF6FF'}});
        sl.addShape(pres.shapes.RECTANGLE,{x:0,y:5.22,w:0.04,h:0.41,fill:{color:C.blue}});
        sl.addText(`🤖 AI 분석: ${trunc(ai.summary,120)}`,{x:0.1,y:5.24,w:9.8,h:0.37,fontSize:8.5,color:C.blue,fontFace:'Arial',wrap:true});
    } else {
        sl.addShape(pres.shapes.RECTANGLE,{x:0,y:5.42,w:10,h:0.205,fill:{color:C.navy}});
        sl.addText(`${plan.sector||''}  |  ${plan.area||''}  |  ${plan.decision||''}`,{x:0.3,y:5.43,w:9.4,h:0.18,fontSize:8,color:'8899AA',fontFace:'Arial'});
    }
}

// ── 클로징 ───────────────────────────────────────────────────────────────
function addClosing(pres) {
    const sl = pres.addSlide();
    sl.background = {color:C.navy};
    sl.addShape(pres.shapes.RECTANGLE,{x:0,y:0,w:0.35,h:5.625,fill:{color:C.teal}});
    sl.addText('Vietnam Infrastructure MI',{x:0.6,y:0.8,w:9,h:0.65,fontSize:30,bold:true,color:C.white,fontFace:'Arial Black'});
    sl.addText('Automated Report Pipeline · SA-8',{x:0.6,y:1.5,w:9,h:0.4,fontSize:16,color:C.tealM,fontFace:'Arial',italic:true});
    sl.addShape(pres.shapes.RECTANGLE,{x:0.6,y:2.05,w:8,h:0.04,fill:{color:C.tealM}});
    [`${plans.length}개 마스터플랜 · knowledge_index v2.1 기반`,
     '매주 토요일 KST 22:00 자동 생성 — Claude Haiku AI 기사 분석 연계',
     'Layer 1 (사업 개요 고정) + Layer 2 (AI 동적 분석) 이중 레이어 구조',
     '★ 노란색 하이라이트 = KPI 변동 자동 감지 · 이메일 자동 첨부 발송',
     '대시보드: hms4792.github.io/vietnam-infra-news/',
    ].forEach((b,i) => {
        sl.addText([{text:b,options:{bullet:true}}],{x:0.6,y:2.25+i*0.48,w:9,h:0.4,fontSize:12.5,color:'C0D0E0',fontFace:'Arial',margin:4});
    });
    const todayStr = new Date().toISOString().slice(0,10);
    sl.addShape(pres.shapes.RECTANGLE,{x:0,y:5.28,w:10,h:0.345,fill:{color:C.navyL}});
    sl.addText(`Vietnam Infrastructure MI Report — SA-8 Auto-Generated | ${todayStr}`,{x:0.3,y:5.3,w:9.4,h:0.3,fontSize:8.5,color:'667788',fontFace:'Arial'});
}

// ══════════════════════════════════════════════════════════════════════════
//  메인
// ══════════════════════════════════════════════════════════════════════════
async function buildPPT() {
    const pres = new pptxgen();
    pres.layout  = 'LAYOUT_16x9';
    pres.author  = 'SA-8 MI Report Pipeline';
    pres.title   = `Vietnam Infrastructure MI Report ${TODAY_STR}`;
    pres.subject = '베트남 인프라 시장 동향 주간 보고서';

    console.log('\n[슬라이드 생성]');
    addCover(pres);    console.log('  ✅ 커버');
    addKpiDash(pres);  console.log('  ✅ KPI 대시보드');

    const byArea = {};
    plans.forEach(p => { (byArea[p.area]=byArea[p.area]||[]).push(p); });
    const sorted = Object.entries(byArea).sort((a,b)=>(AREA_ORDER[a[0]]??9)-(AREA_ORDER[b[0]]??9));

    for(const [area, ap] of sorted) {
        addAreaDiv(pres, area, ap); console.log(`  ✅ 영역: ${area}`);
        for(const plan of ap) {
            addPlanSlide(pres, plan); console.log(`  ✅ ${plan.plan_id}`);
        }
    }
    addClosing(pres); console.log('  ✅ 클로징');

    const outDir = path.dirname(OUT_PATH);
    if(!fs.existsSync(outDir)) fs.mkdirSync(outDir, {recursive:true});

    await pres.writeFile({fileName: OUT_PATH});
    const size = (fs.statSync(OUT_PATH).size/1024).toFixed(0);
    console.log(`\n✅ 완료: ${OUT_PATH} (${size} KB) | 플랜 ${plans.length}개`);
}

buildPPT().catch(err => { console.error('[오류]', err); process.exit(1); });
