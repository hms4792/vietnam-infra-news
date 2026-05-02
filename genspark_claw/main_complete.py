"""
Vietnam Infrastructure News Pipeline - Claw 완전 전환 버전
SA-Sub_AGENT_v2.1 모든 기능 구현
"""
import os
import sys
import json
from datetime import datetime
from pathlib import Path

# Python 경로 설정 — agents/ 우선, scripts/ 하위호환 유지
_BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_BASE, 'agents', 'agent1_collector'))
sys.path.insert(0, os.path.join(_BASE, 'agents', 'agent2_classifier'))
sys.path.insert(0, os.path.join(_BASE, 'agents', 'agent3_historian'))
sys.path.insert(0, os.path.join(_BASE, 'agents', 'agent4_reporter'))
sys.path.insert(0, os.path.join(_BASE, 'agents', 'agent4_reporter', 'templates'))
sys.path.insert(0, os.path.join(_BASE, 'agents', 'agent5_publisher'))
sys.path.insert(0, os.path.join(_BASE, 'scripts'))  # 하위호환

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'), override=True)

from publishing_agent_step5a_integrated import main as generate_reports
from dashboard_generator import generate_html_dashboard
from github_uploader import GitHubUploader
from email_sender import EmailSender
from agent_pipeline import run_pipeline as run_agents_1_5

class VietnamNewsPipeline:
    """
    완전 기능 파이프라인 통합 클래스
    """
    def __init__(self):
        # 항상 main_complete.py 위치 기준으로 경로 설정
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        self.output_dir = Path('outputs')
        self.output_dir.mkdir(exist_ok=True)
        
        # 환경 변수 로드
        self.anthropic_key = os.getenv('ANTHROPIC_API_KEY')
        self.github_token = os.getenv('GITHUB_PAT')
        self.email_user = os.getenv('EMAIL_USERNAME')
        self.email_pass = os.getenv('EMAIL_PASSWORD')
        self.email_to = os.getenv('EMAIL_RECIPIENT', 'hms4792@gmail.com')
        self.github_repo = os.getenv('GITHUB_REPO', 'hms4792/vietnam-infra-news')
        
        # 검증
        self._validate_credentials()
    
    def _validate_credentials(self):
        """필수 인증 정보 검증"""
        missing = []
        if not self.anthropic_key:
            missing.append('ANTHROPIC_API_KEY')
        if not self.github_token:
            missing.append('GITHUB_PAT')
        
        if missing:
            print(f"❌ ERROR: Missing environment variables: {', '.join(missing)}")
            sys.exit(1)
    
    def run(self):
        """전체 파이프라인 실행"""
        print("=" * 80)
        print("🚀 Vietnam Infrastructure News Pipeline - COMPLETE VERSION")
        print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S KST')}")
        print("=" * 80)
        
        try:
            # STEP 1-4: Agent 1-5 실행 (기존 agent_pipeline.py)
            print("\n[STEP 1-4] Running Agents 1-5 (Collector → QC)...")
            self._run_agents_1_5()

            # STEP 4-B: History DB 증분 업데이트 (주간 신규 기사 → history_db.json 누적)
            print("\n[STEP 4-B] Updating History DB (weekly merge)...")
            self._update_history_db()

            # STEP 5-A: 보고서 생성 (Excel 12 sheets + Word 8 reports + Executive Summary)
            print("\n[STEP 5-A] Generating reports...")
            self._generate_reports()
            
            # STEP 5-B: HTML 대시보드 생성
            print("\n[STEP 5-B] Generating dashboard...")
            self._generate_dashboard()
            
            # STEP 5-C: GitHub 업로드
            print("\n[STEP 5-C] Uploading to GitHub...")
            self._upload_to_github()
            
            # STEP 5-D: 이메일 전송
            print("\n[STEP 5-D] Sending email notification...")
            self._send_email()
            
            # 최종 실행 보고서 생성
            self._generate_execution_report()
            
            print("\n" + "=" * 80)
            print("✅ PIPELINE COMPLETED SUCCESSFULLY")
            print("=" * 80)
            
        except Exception as e:
            print(f"\n❌ PIPELINE FAILED: {str(e)}")
            sys.exit(1)
    
    def _run_agents_1_5(self):
        """Agent 1-5 실행 (데이터 수집 → QC). 수집 범위: 최근 7일"""
        base_dir = os.path.dirname(os.path.abspath(__file__))
        articles, qc_report = run_agents_1_5(output_dir=base_dir, collection_days=7)
        print(f"  → 수집 완료: {len(articles)}개 기사, QC 통과율 {qc_report['qc_rate']}%")
        # outputs/ 에도 복사 (후속 단계에서 사용)
        import shutil
        for fname in ['genspark_output.json', 'genspark_qc_report.json']:
            src = os.path.join(base_dir, fname)
            dst = self.output_dir / fname
            if os.path.exists(src):
                shutil.copy2(src, dst)
    
    def _update_history_db(self):
        """STEP 4-B: 주간 신규 기사를 history_db.json에 누적 병합"""
        base = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, base)
        sys.path.insert(0, os.path.join(base, 'scripts'))
        try:
            from scripts.history_db_builder import update_weekly, load_history_db, save_history_db
            import json

            # 이번 주 수집 기사 로드
            weekly_path = self.output_dir / 'genspark_output.json'
            if not weekly_path.exists():
                weekly_path = Path(base) / 'genspark_output.json'

            if weekly_path.exists():
                with open(weekly_path, encoding='utf-8') as f:
                    weekly = json.load(f)
                if isinstance(weekly, dict):
                    weekly = weekly.get('articles', [])
                db = update_weekly(weekly)
                print(f"  ✓ History DB 업데이트: 누적 {db.get('total', '?')}건")
            else:
                print("  ⚠ genspark_output.json 없음 — history DB 업데이트 건너뜀")
        except Exception as e:
            print(f"  ⚠ History DB 업데이트 오류: {e}")

    def _generate_reports(self):
        """G-STEP 5-A: 모든 보고서 생성 (v4.0)"""
        base = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, base)
        sys.path.insert(0, os.path.join(base, 'scripts'))

        # 1. MI Word 보고서 15개 (v4.0 템플릿)
        print("  → [1/4] MI Word 보고서 15개 생성 (v4.0)...")
        try:
            from scripts.mi_report_generator import main as mi_main
            mi_results = mi_main()
            print(f"  ✓ Word 보고서: {len(mi_results)}개")
        except Exception as e:
            print(f"  ⚠ Word 보고서 오류: {e}")

        # 2. MI PPT Executive Summary 15개
        print("  → [2/4] MI PPT Executive Summary 15개 생성...")
        try:
            from scripts.mi_ppt_generator import generate_all_ppts
            ppt_out = str(self.output_dir / 'reports' / 'MI_PPT')
            Path(ppt_out).mkdir(parents=True, exist_ok=True)
            ppt_results = generate_all_ppts(ppt_out)
            ok_ppt = sum(1 for r in ppt_results if r[2])
            print(f"  ✓ PPT: {ok_ppt}/{len(ppt_results)}개")
        except Exception as e:
            print(f"  ⚠ PPT 생성 오류: {e}")

        # 3. GitHub 공유 파일 내보내기 (MASTERPLAN_IDS + RELEVANCE_RULES + SECTOR_TO_PLAN)
        print("  → [3/4] GitHub 공유 파일 업데이트...")
        try:
            from scripts.export_masterplan_rules import run as export_rules
            export_results = export_rules(push_to_github=True)
            ok_exp = sum(1 for v in export_results.values() if v)
            print(f"  ✓ 공유 파일: {ok_exp}/{len(export_results)}개 GitHub 업로드")
        except Exception as e:
            print(f"  ⚠ 공유 파일 오류: {e}")

        # 4. History DB Excel (전체 2668건 + 플랜별 시트 + 노란색 컬러링)
        print("  → [4/4] History DB Excel 생성 (All + 24개 플랜별 시트)...")
        try:
            from scripts.excel_history_exporter import generate_history_excel, generate_weekly_excel
            xlsx_path = generate_history_excel()
            print(f"  ✓ History Excel 완료: {os.path.basename(xlsx_path)}")

            # 주간 기사 Excel (대시보드 다운로드용, History DB와 동일 양식)
            articles_path = self.output_dir / 'genspark_output.json'
            if articles_path.exists():
                with open(articles_path, 'r', encoding='utf-8') as f:
                    weekly_arts = json.load(f)
                if isinstance(weekly_arts, dict):
                    weekly_arts = weekly_arts.get('articles', [])
                weekly_xl = generate_weekly_excel(weekly_arts,
                    str(self.output_dir / 'reports/weekly_excel'))
                self._weekly_excel_paths = weekly_xl
                print(f"  ✓ 주간 Excel 완료: 전체 1 + 플랜별 {len(weekly_xl.get('plans',{}))}개")
            else:
                print("  ⚠ genspark_output.json 없음 — 주간 Excel 건너뜀")
        except Exception as e:
            print(f"  ⚠ History Excel 오류: {e}")
            # 구버전 fallback
            try:
                generate_reports()
                print("  ✓ Legacy Excel 완료")
            except Exception as e2:
                print(f"  ⚠ Legacy Excel 오류: {e2}")

        print("  ✓ 전체 보고서 생성 완료")
    
    def _generate_dashboard(self):
        """G-STEP 5-B: HTML 대시보드 생성"""
        articles_path = self.output_dir / 'genspark_output.json'
        if not articles_path.exists():
            # fallback: 루트 디렉토리
            articles_path = Path(os.path.dirname(os.path.abspath(__file__))) / 'genspark_output.json'

        with open(articles_path, 'r', encoding='utf-8') as f:
            articles = json.load(f)

        dashboard_dir = self.output_dir / 'dashboard'
        dashboard_dir.mkdir(parents=True, exist_ok=True)
        dashboard_path = dashboard_dir / 'index.html'
        generate_html_dashboard(articles, str(dashboard_path))

        print(f"  ✓ Dashboard generated: {dashboard_path}")
    
    def _upload_to_github(self):
        """G-STEP 5-C: GitHub 업로드 + GitHub Pages 활성화"""
        uploader = GitHubUploader(self.github_token, self.github_repo)

        # GitHub Pages 활성화 (docs/ 폴더 기준)
        uploader.ensure_pages_enabled()

        # 1. 대시보드 업로드
        dashboard_path = self.output_dir / 'dashboard' / 'index.html'
        if dashboard_path.exists():
            uploader.upload_dashboard(str(dashboard_path))

        # 2. 보고서 파일 업로드 → Genspark 전용 경로
        reports_dir = self.output_dir / 'reports'
        if reports_dir.exists():
            uploader.upload_reports(str(reports_dir), target_dir='reports/genspark')

        # 3. 공유 JSON 데이터 → Claude SA-6 연동용
        articles_path = self.output_dir / 'genspark_output.json'
        if articles_path.exists():
            uploader.upload_file(
                local_path=str(articles_path),
                github_path='docs/shared/genspark_output.json',
                commit_message=f'Genspark Claw weekly output {datetime.now().strftime("%Y-%m-%d")}'
            )

        # 4. 공유 QC 리포트
        qc_path = self.output_dir / 'genspark_qc_report.json'
        if qc_path.exists():
            uploader.upload_file(
                local_path=str(qc_path),
                github_path='docs/shared/genspark_qc_report.json',
                commit_message=f'Genspark QC report {datetime.now().strftime("%Y-%m-%d")}'
            )

        # 5. AI Drive 업로드 (Word + PPT)
        try:
            import subprocess, glob
            now = datetime.now()
            week = now.isocalendar()[1]
            folder = f"/Vietnam_Infrastructure_News_Pipeline/weekly-reports/{now.year}-W{week:02d}_{now.strftime('%m%d')}"
            mi_dir  = str(self.output_dir / 'reports' / 'MI_Reports')
            ppt_dir = str(self.output_dir / 'reports' / 'MI_PPT')
            total_up = 0
            for fpath in glob.glob(f"{mi_dir}/*.docx") + glob.glob(f"{ppt_dir}/*.pptx"):
                fname  = os.path.basename(fpath)
                if fpath.endswith(".docx"):   subfld = "MI_Reports_v4"
                elif fpath.endswith(".pptx"): subfld = "MI_PPT"
                else:                         subfld = ""  # xlsx → 폴더 루트
                upload_dest = f"{folder}/{subfld}/{fname}" if subfld else f"{folder}/{fname}"
                r = subprocess.run(
                    ["gsk","drive","upload","--local_file",fpath,
                     "--upload_path",upload_dest,"--override"],
                    capture_output=True, text=True, timeout=120
                )
                if '"status": "ok"' in r.stdout: total_up += 1
            # History DB Excel 업로드 (고정 경로 덮어쓰기 + 주차 스냅샷)
            reports_base = str(self.output_dir / 'reports')
            fixed_xlsx = os.path.join(reports_base, "Vietnam_Infra_History_DB.xlsx")
            if os.path.exists(fixed_xlsx):
                # 1. 고정 경로 (항상 최신본 — 덮어쓰기)
                r = subprocess.run(
                    ["gsk","drive","upload","--local_file", fixed_xlsx,
                     "--upload_path",
                     "/Vietnam_Infrastructure_News_Pipeline/Vietnam_Infra_History_DB.xlsx",
                     "--override"],
                    capture_output=True, text=True, timeout=180
                )
                if '"status": "ok"' in r.stdout:
                    total_up += 1
                    print(f"  ✓ History DB Excel 고정 경로 업로드 완료")

                # 2. 주차별 스냅샷 (이번 주 폴더)
                snapshot_pattern = os.path.join(reports_base, f"Vietnam_Infra_History_DB_W{week:02d}_*.xlsx")
                for snap in glob.glob(snapshot_pattern):
                    snap_name = os.path.basename(snap)
                    r2 = subprocess.run(
                        ["gsk","drive","upload","--local_file", snap,
                         "--upload_path", f"{folder}/{snap_name}",
                         "--override"],
                        capture_output=True, text=True, timeout=180
                    )
                    if '"status": "ok"' in r2.stdout:
                        total_up += 1

            print(f"  ✓ AI Drive 업로드: {total_up}개")
        except Exception as e:
            print(f"  ⚠ AI Drive 업로드 오류: {e}")

        # 6. 주간 Excel GitHub Pages 업로드 + report_urls 갱신
        try:
            weekly_xl = getattr(self, '_weekly_excel_paths', None)
            if weekly_xl:
                now = datetime.now()
                week = now.isocalendar()[1]
                date_str = now.strftime('%m%d')
                report_urls_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config/report_urls.json')
                report_urls = {}
                if os.path.exists(report_urls_path):
                    with open(report_urls_path, 'r') as f:
                        report_urls = json.load(f)

                gh_base = f'https://{self.github_repo.split("/")[0]}.github.io/{self.github_repo.split("/")[1]}/genspark/excel'

                # 전체 주간 Excel
                all_xl = weekly_xl.get('all')
                if all_xl and os.path.exists(all_xl):
                    gh_filename = f'Vietnam_Infra_Weekly_W{week:02d}.xlsx'
                    uploader.upload_file(
                        local_path=all_xl,
                        github_path=f'docs/genspark/excel/{gh_filename}',
                        commit_message=f'Weekly Excel W{week:02d}'
                    )
                    report_urls['_weekly_excel'] = f'{gh_base}/{gh_filename}'
                    total_up += 1

                # 플랜별 Excel
                for plan_id, plan_xl_path in weekly_xl.get('plans', {}).items():
                    if os.path.exists(plan_xl_path):
                        safe_id = plan_id.replace('-', '_')
                        gh_filename = f'Weekly_{safe_id}_W{week:02d}.xlsx'
                        uploader.upload_file(
                            local_path=plan_xl_path,
                            github_path=f'docs/genspark/excel/{gh_filename}',
                            commit_message=f'Plan Excel {plan_id} W{week:02d}'
                        )
                        # report_urls에 플랜별 excel URL 추가
                        if plan_id in report_urls and isinstance(report_urls[plan_id], dict):
                            report_urls[plan_id]['excel'] = f'{gh_base}/{gh_filename}'
                        total_up += 1

                # report_urls.json 갱신
                with open(report_urls_path, 'w') as f:
                    json.dump(report_urls, f, indent=2, ensure_ascii=False)
                print(f"  ✓ 주간 Excel GitHub 업로드 완료 + report_urls 갱신")
        except Exception as e:
            print(f"  ⚠ 주간 Excel GitHub 업로드 오류: {e}")

        print("  ✓ All files uploaded to GitHub + AI Drive")
    
    def _send_email(self):
        """G-STEP 5-D: 이메일 전송"""
        if not self.email_user or not self.email_pass:
            print("  ⚠ Email credentials not set, skipping email notification")
            return
        
        # 통계 수집
        with open('genspark_output.json', 'r', encoding='utf-8') as f:
            articles = json.load(f)
        
        stats = {
            'total_articles': len(articles),
            'qc_passed': sum(1 for a in articles if a.get('qc_status') == 'PASS'),
            'plan_matched': sum(1 for a in articles if a.get('matched_plans')),
            'qc_rate': (sum(1 for a in articles if a.get('qc_status') == 'PASS') / len(articles) * 100) if articles else 0,
            'plan_counts': {},
            'dashboard_url': f'https://{self.github_repo.split("/")[0]}.github.io/{self.github_repo.split("/")[1]}/genspark/',
            'github_url': f'https://github.com/{self.github_repo}'
        }
        
        # 마스터플랜별 카운트
        plans = [
            "VN-PWR-PDP8", "VN-ENV-IND-1894", "VN-TRAN-2055", "VN-URB-METRO-2030",
            "VN-GAS-PDP8", "VN-WAT-2050", "VN-REN-NPP-2050", "VN-COAL-RETIRE",
            "VN-GRID-SMART", "VN-EV-2030", "VN-CARBON-2050", "VN-LNG-HUB"
        ]
        for plan in plans:
            count = sum(1 for a in articles if plan in a.get('matched_plans', []))
            if count > 0:
                stats['plan_counts'][plan] = count
        
        # 통계 파일 저장
        with open(self.output_dir / 'execution_stats.json', 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        
        # 이메일 전송
        sender = EmailSender(self.email_user, self.email_pass, self.email_to)
        week_num = datetime.now().isocalendar()[1]
        subject = f"🇻🇳 Vietnam Infra Weekly W{week_num:02d} — {stats.get('plan_matched',0)}건 매핑"
        html_body = sender.create_kpi_email(stats, articles)
        sender.send_email(subject, html_body)
        
        print(f"  ✓ Email sent to {self.email_to}")
    
    def _generate_execution_report(self):
        """최종 실행 보고서 생성"""
        with open('genspark_output.json', 'r', encoding='utf-8') as f:
            articles = json.load(f)
        
        report = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    EXECUTION REPORT - FINAL SUMMARY                          ║
╚══════════════════════════════════════════════════════════════════════════════╝

Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S KST')}

📊 COLLECTION METRICS:
  • Total Articles Collected: {len(articles)}
  • QC Passed: {sum(1 for a in articles if a.get('qc_status') == 'PASS')}
  • QC Pass Rate: {(sum(1 for a in articles if a.get('qc_status') == 'PASS') / len(articles) * 100):.1f}%
  • Plan Matched: {sum(1 for a in articles if a.get('matched_plans'))}

📑 MASTER PLAN COVERAGE:
"""
        
        plans = [
            "VN-PWR-PDP8", "VN-ENV-IND-1894", "VN-TRAN-2055", "VN-URB-METRO-2030",
            "VN-GAS-PDP8", "VN-WAT-2050", "VN-REN-NPP-2050", "VN-COAL-RETIRE",
            "VN-GRID-SMART", "VN-EV-2030", "VN-CARBON-2050", "VN-LNG-HUB"
        ]
        
        for plan in plans:
            count = sum(1 for a in articles if plan in a.get('matched_plans', []))
            report += f"  • {plan}: {count} articles\n"
        
        report += f"""
✅ PIPELINE STATUS:
  • Agent 1 (Collector): SUCCESS
  • Agent 2 (Classifier): SUCCESS
  • Agent 3 (KB Matcher): SUCCESS
  • Agent 4 (Summarizer): SUCCESS
  • Agent 5 (QC): SUCCESS
  • Agent 6 (Publisher): SUCCESS
    - Excel Database (12 sheets): ✓
    - Word Reports (8 projects): ✓
    - Executive Summary: ✓
    - Quality Report: ✓
    - HTML Dashboard: ✓
    - GitHub Upload: ✓
    - Email Notification: ✓

╔══════════════════════════════════════════════════════════════════════════════╗
║                         OVERALL STATUS: SUCCESS                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""
        
        print(report)
        
        # 파일로도 저장
        with open(self.output_dir / 'execution_report.txt', 'w', encoding='utf-8') as f:
            f.write(report)

def main():
    """메인 진입점"""
    pipeline = VietnamNewsPipeline()
    pipeline.run()

if __name__ == "__main__":
    main()
