"""
GitHub Uploader - G-STEP 5-C 구현
"""
import os
import sys
from github import Github, GithubException
from datetime import datetime

class GitHubUploader:
    def __init__(self, token: str, repo_name: str):
        """
        GitHub 업로더 초기화
        
        Args:
            token: GitHub Personal Access Token
            repo_name: 'owner/repo' 형식
        """
        self.client = Github(token)
        self.repo = self.client.get_repo(repo_name)
        
    def upload_file(self, local_path: str, github_path: str, commit_message: str = None):
        """
        파일 업로드 (이미 존재하면 업데이트)
        
        Args:
            local_path: 로컬 파일 경로
            github_path: GitHub 저장소 내 경로
            commit_message: 커밋 메시지
        """
        if not os.path.exists(local_path):
            raise FileNotFoundError(f"Local file not found: {local_path}")
        
        with open(local_path, 'rb') as f:
            content = f.read()
        
        if commit_message is None:
            commit_message = f"Update {os.path.basename(github_path)} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        try:
            # 파일이 존재하는지 확인
            contents = self.repo.get_contents(github_path)
            # 존재하면 업데이트
            self.repo.update_file(
                path=github_path,
                message=commit_message,
                content=content,
                sha=contents.sha
            )
            print(f"✓ Updated: {github_path}")
        except GithubException as e:
            if e.status == 404:
                # 존재하지 않으면 새로 생성
                self.repo.create_file(
                    path=github_path,
                    message=commit_message,
                    content=content
                )
                print(f"✓ Created: {github_path}")
            else:
                raise
    
    def upload_dashboard(self, local_html: str):
        """
        Genspark 대시보드를 docs/genspark/index.html로 업로드
        ⚠ docs/index.html은 Claude 대시보드 전용 — 절대 덮어쓰지 않음
        """
        self.upload_file(
            local_path=local_html,
            github_path='docs/genspark/index.html',
            commit_message='Genspark dashboard update'
        )
        print(f"✓ Genspark Dashboard: https://{self.repo.owner.login}.github.io/{self.repo.name}/genspark/")
    
    def upload_reports(self, reports_dir: str, target_dir: str = 'reports'):
        """
        보고서 파일들을 일괄 업로드 (하위 디렉토리 포함, 재귀 탐색)
        
        Args:
            reports_dir: 로컬 보고서 디렉터리
            target_dir: GitHub 내 타겟 디렉터리
        """
        if not os.path.exists(reports_dir):
            raise FileNotFoundError(f"Reports directory not found: {reports_dir}")
        
        date_str = datetime.now().strftime('%Y-%m-%d')
        
        for root, dirs, files in os.walk(reports_dir):
          for filename in files:
            if filename.endswith(('.xlsx', '.docx', '.pptx', '.json', '.txt')):
                local_path = os.path.join(root, filename)
                # 하위 디렉토리 구조 유지 (MI_Reports/, MI_PPT/ 등)
                rel_path = os.path.relpath(local_path, reports_dir)
                github_path = f"{target_dir}/{date_str}/{rel_path}"
                
                self.upload_file(
                    local_path=local_path,
                    github_path=github_path,
                    commit_message=f"Upload {rel_path} - {date_str}"
                )
    
    def ensure_pages_enabled(self):
        """
        GitHub Pages가 docs/ 폴더 기준으로 활성화되어 있는지 확인하고,
        비활성 상태면 자동 활성화 시도.
        """
        try:
            # REST API 직접 호출 (PyGithub 버전 호환성)
            status, data = self.repo._requester.requestJsonAndCheck(
                "GET",
                f"{self.repo.url}/pages",
            )
            html_url = data.get("html_url", "unknown")
            print(f"  ✓ GitHub Pages already enabled: {html_url}")
        except GithubException as e:
            if e.status == 404:
                try:
                    self.repo._requester.requestJsonAndCheck(
                        "POST",
                        f"{self.repo.url}/pages",
                        input={"source": {"branch": "main", "path": "/docs"}},
                        headers={"Accept": "application/vnd.github.switcheroo-preview+json"},
                    )
                    print("  ✓ GitHub Pages activated (docs/ folder, main branch)")
                except Exception as ex:
                    print(f"  ⚠ GitHub Pages auto-activation failed: {ex}")
                    print("  → 수동 설정: GitHub repo → Settings → Pages → Source: main/docs")
            else:
                print(f"  ⚠ Pages check skipped: {e}")

    def get_file_url(self, github_path: str) -> str:
        """
        GitHub 파일의 공개 URL 반환
        
        Args:
            github_path: GitHub 저장소 내 경로
            
        Returns:
            파일의 공개 URL
        """
        return f"https://github.com/{self.repo.full_name}/blob/main/{github_path}"

def main():
    """
    Genspark Claw 파이프라인 완료 후 자동 호출
    ─────────────────────────────────────────────
    경로 분리 원칙 (절대 준수):
      공유   : docs/shared/          ← Genspark↔Claude 연동 전용
      Genspark: docs/genspark/       ← Genspark 전용 (Claude 파일 접근 금지)
               data/genspark/        ← Genspark Excel (Claude DB와 분리)
               reports/genspark/     ← Genspark Word 보고서
      Claude  : docs/index.html      ← Claude 대시보드 (Genspark 덮어쓰기 금지!)
               data/news_database.xlsx ← Claude Excel DB (9시트, 누적)
    """
    github_token = os.getenv('GITHUB_PAT')
    repo_name    = os.getenv('GITHUB_REPO', 'hms4792/vietnam-infra-news')
    output_dir   = os.getenv('PIPELINE_OUTPUT_DIR', '.')

    if not github_token:
        print("❌ ERROR: GITHUB_PAT environment variable not set")
        sys.exit(1)

    json_file   = os.path.join(output_dir, "genspark_output.json")
    qc_file     = os.path.join(output_dir, "genspark_qc_report.json")
    html_file   = os.path.join(output_dir, "dashboard", "index.html")
    reports_dir = os.path.join(output_dir, "reports")
    run_date    = datetime.now().strftime("%Y-%m-%d")

    try:
        uploader = GitHubUploader(github_token, repo_name)
        uploader.ensure_pages_enabled()

        print(f"\n── Genspark Claw → GitHub 업로드 ({run_date}) ──")
        print("  경로 분리 원칙: Claude docs/index.html 및 Excel DB 보호")

        # ① 공유: Claude SA-6 연동용 기사 데이터
        if os.path.exists(json_file):
            uploader.upload_file(
                local_path=json_file,
                github_path="docs/shared/genspark_output.json",
                commit_message=f"Genspark Claw weekly output {run_date}"
            )
        else:
            print(f"  ⚠ genspark_output.json 없음: {json_file}")

        # ② 공유: QC 리포트
        if os.path.exists(qc_file):
            uploader.upload_file(
                local_path=qc_file,
                github_path="docs/shared/genspark_qc_report.json",
                commit_message=f"Genspark QC report {run_date}"
            )

        # ③ Genspark 전용 대시보드 → docs/genspark/index.html
        #    Claude 대시보드(docs/index.html)와 완전 분리
        if os.path.exists(html_file):
            uploader.upload_file(
                local_path=html_file,
                github_path="docs/genspark/index.html",
                commit_message=f"Genspark dashboard {run_date}"
            )
            print(f"  ✓ Genspark 대시보드 URL: /vietnam-infra-news/genspark/")
        
        # ④ Genspark 전용 Excel → data/genspark/ (Claude Excel DB와 완전 분리)
        if os.path.exists(reports_dir):
            for fn in os.listdir(reports_dir):
                lp = os.path.join(reports_dir, fn)
                if fn.endswith('.xlsx'):
                    uploader.upload_file(
                        local_path=lp,
                        github_path=f"data/genspark/{run_date}_{fn}",
                        commit_message=f"Genspark Excel {run_date}"
                    )
                elif fn.endswith('.docx'):
                    uploader.upload_file(
                        local_path=lp,
                        github_path=f"reports/genspark/{run_date}/{fn}",
                        commit_message=f"Genspark Word report {run_date}"
                    )

        print("\n✓ 업로드 완료")
        print(f"  [공유]    docs/shared/genspark_output.json → Claude SA-6 오늘 KST 20:00 반영")
        print(f"  [Genspark] docs/genspark/index.html")
        print(f"  Claude 대시보드: https://hms4792.github.io/vietnam-infra-news/")
        print(f"  Genspark 대시보드: https://hms4792.github.io/vietnam-infra-news/genspark/")

    except Exception as e:
        print(f"❌ Upload failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
