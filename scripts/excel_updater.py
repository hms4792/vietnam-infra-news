"""
excel_updater.py — v7.1
클래스: ExcelUpdater  /  메서드: update_all(articles)
파일명: Vietnam_Infra_News_Database_Final.xlsx

News Database 열 순서 (v7, 변경 금지):
  A=No  B=Date  C=Title(En/Vi)  D=Tit_ko
  E=Source  F=Src_Type  G=Province  H=Plan_ID
  I=Grade  J=URL  K=sum_ko  L=sum_en  M=sum_vi

영구 제약:
  - 번역: Google Translate만 (Anthropic API 절대 금지)
  - date: article.get('date') or article.get('published_date')
  - 신규 삽입: insert_rows(2)
  - wrap_text=False, 글자색 항상 검정(000000)
"""

import os
import logging
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from functools import cmp_to_key

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

logger = logging.getLogger(__name__)

FN = '맑은 고딕'; FS = 11; BLACK = '000000'; WHITE = 'FFFFFF'
GRADE_BG = {'HIGH': 'FFF9C4', 'MEDIUM': 'E3F2FD', 'POLICY': 'E8F5E9', '': 'FFFFFF'}
SECTOR_ORDER = ['Waste Water','Water Supply/Drainage','Solid Waste','Power','Oil & Gas',
                'Industrial Parks','Smart City','Transport','Construction','Environment']

def _thin():
    s = Side(style='thin', color='CCCCCC')
    return Border(left=s, right=s, top=s, bottom=s)

def _dat(ws, r, c, v='', bold=False, bg='FFFFFF', align='left'):
    cell = ws.cell(r, c, v)
    cell.font      = Font(name=FN, size=FS, bold=bold, color=BLACK)
    cell.fill      = PatternFill('solid', fgColor=bg)
    cell.alignment = Alignment(horizontal=align, vertical='center', wrap_text=False)
    cell.border    = _thin()
    return cell

class ExcelUpdater:
    def __init__(self, excel_path: str):
        self.path = excel_path
        if not os.path.exists(excel_path):
            raise FileNotFoundError(f"Excel 없음: {excel_path}")

    def update_all(self, articles: list) -> dict:
        """Step3 호출 메서드 (이름 변경 금지)"""
        if not articles:
            logger.warning("신규 기사 없음")
            return {}
        # date fallback
        for a in articles:
            if not a.get('date'):
                a['date'] = a.get('published_date', '')
            tko = a.get('title_ko', '')
            if tko.startswith('[EN]') or tko.startswith('[KO]'):
                a['title_ko'] = ''

        wb = load_workbook(self.path)
        stats = {}
        try:
            stats['News Database']    = self._update_nd(wb, articles)
            stats['Matched_Plan']     = self._update_mp(wb, articles)
            stats['Keywords History'] = self._update_kwh(wb, articles)
            stats['Province_Keywords']= self._update_prov(wb)
            stats['Source']           = self._update_src(wb)
            stats['RSS_Sources']      = self._update_rss(wb)
            stats['Collection_Log']   = self._append_log(wb, stats)
            stats['Summary']          = self._update_summary(wb)
            wb.save(self.path)
            logger.info(f"저장 완료: {self.path}")
        except Exception as e:
            logger.error(f"업데이트 실패: {e}"); raise
        finally:
            wb.close()
        return stats

    def _update_nd(self, wb, articles):
        ws = wb['News Database']
        existing = set(str(r[9] or '') for r in ws.iter_rows(min_row=2, values_only=True) if r[9])
        inserted = 0
        for a in reversed(articles):
            url = a.get('url', '')
            if not url or url in existing: continue
            ws.insert_rows(2)
            existing.add(url)
            grade = a.get('grade', '')
            bg = GRADE_BG.get(grade, 'FFFFFF')
            vals = [1, a.get('date',''), a.get('title_en','') or a.get('title',''),
                    a.get('title_ko',''), a.get('source',''), a.get('src_type','NewsData.io'),
                    a.get('province',''), a.get('plan','') or a.get('plan_id',''),
                    grade, url, a.get('sum_ko',''), a.get('sum_en',''), a.get('sum_vi','')]
            for ci, val in enumerate(vals, 1):
                _dat(ws, 2, ci, val, bold=(ci in {3,4}), bg=bg,
                     align='center' if ci in {1,2,6,9} else 'left')
            ws.row_dimensions[2].height = 16
            inserted += 1
        self._renum(ws); self._sort_date(ws)
        logger.info(f"ND +{inserted}건")
        return inserted

    def _update_mp(self, wb, articles):
        ws = wb['Matched_Plan']
        existing = set()
        for row in ws.iter_rows(min_row=2, values_only=True):
            for v in row:
                if v and str(v).startswith('http'): existing.add(str(v)); break
        sa7 = [a for a in articles if a.get('grade','') in {'HIGH','MEDIUM','POLICY'}
               and a.get('url','') not in existing]
        inserted = 0
        for a in reversed(sa7):
            ws.insert_rows(2); existing.add(a['url'])
            grade = a.get('grade','MEDIUM')
            bg = GRADE_BG.get(grade, 'F8F9FA')
            vals = [1, a.get('date',''), a.get('title_en','') or a.get('title',''),
                    a.get('title_ko',''), a.get('source',''), a.get('src_type',''),
                    a.get('province',''), a.get('plan_id','') or a.get('plan',''),
                    grade, a.get('sector',''), a.get('title_vi',''),
                    a.get('sum_ko',''), a.get('sum_en',''), a.get('sum_vi',''), a.get('url','')]
            for ci, val in enumerate(vals, 1):
                _dat(ws, 2, ci, val, bold=(ci in {3,4,8}), bg=bg,
                     align='center' if ci in {1,2,9} else 'left')
            ws.row_dimensions[2].height = 16; inserted += 1
        self._renum(ws); self._sort_date(ws)
        return inserted

    def _update_kwh(self, wb, new_arts):
        ws = wb['Keywords History']
        cutoff = (datetime.now()-timedelta(days=30)).strftime('%Y-%m-%d')
        existing = set(str(r[3] or '') for r in ws.iter_rows(min_row=2, values_only=True) if r[3])
        to_add = [a for a in new_arts if (a.get('title_en','') or a.get('title','')) not in existing]
        if not to_add: return 0
        all_data = [list(r[:8]) for r in ws.iter_rows(min_row=2, values_only=True) if r[2]]
        for a in to_add:
            all_data.append([a.get('sector',''), a.get('province',''), a.get('date',''),
                              a.get('title_en','') or a.get('title',''), a.get('source',''),
                              a.get('src_type',''), a.get('plan','') or a.get('plan_id',''),
                              a.get('grade','')])
        def cmp(a, b):
            sa = SECTOR_ORDER.index(str(a[0])) if str(a[0]) in SECTOR_ORDER else 99
            sb = SECTOR_ORDER.index(str(b[0])) if str(b[0]) in SECTOR_ORDER else 99
            if sa != sb: return sa-sb
            if str(a[1] or '') != str(b[1] or ''): return -1 if str(a[1] or'')<str(b[1] or'') else 1
            return -1 if str(a[2] or'')>str(b[2] or'') else 1
        all_data.sort(key=cmp_to_key(cmp))
        ws.delete_rows(2, ws.max_row)
        for ri, row in enumerate(all_data, 2):
            is_new = str(row[2] or '') >= cutoff
            bg = 'FFF9C4' if is_new else 'FFFFFF'
            for ci, val in enumerate(row[:8], 1):
                c = ws.cell(ri, ci, val)
                c.font      = Font(name=FN, size=10, bold=(is_new and ci==3), color=BLACK)
                c.fill      = PatternFill('solid', fgColor=bg)
                c.alignment = Alignment(horizontal='left', vertical='center', wrap_text=False)
                c.border    = _thin()
            ws.row_dimensions[ri].height = 14
        return len(to_add)

    def _update_prov(self, wb):
        ws_db = wb['News Database']; ws = wb['Province_Keywords']
        prov = defaultdict(lambda: {'total':0,'sa7':0,'sources':Counter()})
        for row in ws_db.iter_rows(min_row=2, values_only=True):
            if not row[2]: continue
            p = str(row[6] or 'Unknown')  # G열: Province
            prov[p]['total'] += 1
            if str(row[8] or '') in {'HIGH','MEDIUM','POLICY'}: prov[p]['sa7'] += 1
            if row[4]: prov[p]['sources'][str(row[4])] += 1
        ws.delete_rows(2, ws.max_row)
        ri = 2
        for p in sorted(prov.keys()):
            ps = prov[p]; t=ps['total']; m=ps['sa7']
            unc = (t-m)/t*100 if t else 100
            top = ps['sources'].most_common(1)[0][0] if ps['sources'] else ''
            g = '🟢 양호' if unc<=25 else ('🟡 보통' if unc<=44 else '🔴 요개선')
            bg = 'F0FFF4' if unc<=25 else ('FFFDE7' if unc<=44 else 'FDEDEC')
            for ci, val in enumerate([p,t,m,'',top,f'{unc:.1f}%',g],1):
                _dat(ws, ri, ci, val, bold=(ci==1), bg=bg,
                     align='left' if ci in {1,4,5,7} else 'center')
            ws.row_dimensions[ri].height=16; ri+=1
        return 'updated'

    def _update_src(self, wb):
        ws_db=wb['News Database']; ws=wb['Source']
        src_s = defaultdict(lambda:{'cnt':0,'type':'','dates':[]})
        total=0
        for row in ws_db.iter_rows(min_row=2, values_only=True):
            if not row[2]: continue
            total+=1; s=str(row[4] or ''); t=str(row[5] or ''); d=str(row[1] or '')
            src_s[s]['cnt']+=1; src_s[s]['type']=t
            if d: src_s[s]['dates'].append(d)
        ws.delete_rows(2, ws.max_row)
        TYPE_BG={'NewsData.io':'EAF4FB','RSS':'F0FFF4','Government':'F5EEF8','Specialist':'FEF9E7'}
        ri=2
        for sn,sd in sorted(src_s.items(),key=lambda x:-x[1]['cnt']):
            cnt=sd['cnt']; pct=cnt/total*100 if total else 0
            latest=max(sd['dates']) if sd['dates'] else ''
            t=sd['type']; bg=TYPE_BG.get(t,'FFFFFF')
            for ci,val in enumerate([sn,t,cnt,f'{pct:.1f}%',latest,'✅ 활성',''],1):
                _dat(ws,ri,ci,val,bold=(ci==1),bg=bg,
                     align='left' if ci in{1,2,6,7} else 'center')
            ws.row_dimensions[ri].height=15; ri+=1
        return 'updated'

    def _update_rss(self, wb):
        ws_db=wb['News Database']; ws=wb['RSS_Sources']
        rss_cnt=defaultdict(int); rss_d=defaultdict(list)
        for row in ws_db.iter_rows(min_row=2,values_only=True):
            if str(row[5] or '')=='RSS' and row[4]:
                rss_cnt[str(row[4])]+=1
                if row[1]: rss_d[str(row[4])].append(str(row[1]))
        for ri in range(2, ws.max_row+1):
            sn=ws.cell(ri,1).value
            if sn and str(sn) in rss_cnt:
                _dat(ws,ri,4,rss_cnt[str(sn)],bg='F0FFF4',align='center')
                latest=max(rss_d.get(str(sn),['—'])) if rss_d.get(str(sn)) else '—'
                _dat(ws,ri,5,latest,bg='F0FFF4',align='center')
        return 'updated'

    def _append_log(self, wb, stats):
        ws=wb['Collection_Log']; ws.insert_rows(2)
        now=datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
        cnt=sum(v for v in stats.values() if isinstance(v,int))
        for ci,val in enumerate([now,cnt,'Daily Automated','✅','',''],1):
            _dat(ws,2,ci,val,align='center' if ci in{2,4} else 'left')
        ws.row_dimensions[2].height=16
        return 'appended'

    def _update_summary(self, wb):
        ws_db=wb['News Database']; ws=wb['Summary']
        total=matched=sko=0
        for row in ws_db.iter_rows(min_row=2,values_only=True):
            if not row[2]: continue
            total+=1
            if str(row[8] or '') in {'HIGH','MEDIUM','POLICY'}: matched+=1
            if row[10] and any('\uac00'<=c<='\ud7a3' for c in str(row[10])): sko+=1
        mp_cnt=sum(1 for r in wb['Matched_Plan'].iter_rows(min_row=2,values_only=True) if r[2])
        update_map={'News Database (관리 기준)':total,'SA-7 확정 (Matched_Plan)':mp_cnt,
                    'ND sum_ko 한글(전체)':sko}
        for row in ws.iter_rows(min_row=3,values_only=False):
            if len(row)>1 and str(row[1].value or '') in update_map:
                c=row[2]; c.value=update_map[str(row[1].value)]
                c.font=Font(name=FN,size=FS,color=BLACK)
        return 'rebuilt'

    def _renum(self, ws):
        no=1
        for ri in range(2,ws.max_row+1):
            if ws.cell(ri,3).value:
                c=ws.cell(ri,1,no)
                c.font=Font(name=FN,size=FS,color=BLACK)
                c.alignment=Alignment(horizontal='center',vertical='center',wrap_text=False)
                no+=1

    def _sort_date(self, ws, date_col=2):
        data=[]
        for ri in range(2,ws.max_row+1):
            row=[ws.cell(ri,ci).value for ci in range(1,ws.max_column+1)]
            if any(v for v in row if v): data.append(row)
        data.sort(key=lambda r:str(r[date_col-1] or ''),reverse=True)
        for ri,row in enumerate(data,2):
            for ci,val in enumerate(row,1): ws.cell(ri,ci).value=val
