"""
Google Drive 업로드 유틸리티 (서비스 계정 방식)
docs/shared/ 의 모든 파일을 Google Drive 공유 폴더에 동기화한다.

인증 우선순위:
  1. 환경변수 GDRIVE_SERVICE_ACCOUNT_JSON (JSON 내용 전체 — GitHub Actions용)
  2. 로컬 파일 ~/.google/gdrive_service_account.json

필요 환경변수:
  GDRIVE_FOLDER_ID  — 업로드 대상 폴더 ID 또는 Drive URL

필요 패키지:
  pip install google-api-python-client google-auth
"""

import io
import json
import mimetypes
import os

BASE_DIR        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHARED_DOCS_DIR = os.path.join(BASE_DIR, "docs", "shared")

LOCAL_SA_PATH = os.path.expanduser("~/.google/gdrive_service_account.json")
SCOPES        = ["https://www.googleapis.com/auth/drive"]


def _parse_folder_id(raw):
    """URL 또는 순수 ID 모두 허용."""
    if not raw:
        return ""
    raw = raw.strip().rstrip("/")
    if "/folders/" in raw:
        return raw.split("/folders/")[-1].split("?")[0]
    return raw


FOLDER_ID = _parse_folder_id(os.environ.get("GDRIVE_FOLDER_ID", ""))


def get_drive_service():
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError:
        raise ImportError(
            "필요 패키지 미설치.\n"
            "pip install google-api-python-client google-auth"
        )

    sa_json_str = os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON", "")

    if sa_json_str:
        # GitHub Actions: 환경변수에서 JSON 직접 파싱
        sa_info = json.loads(sa_json_str)
        creds = service_account.Credentials.from_service_account_info(
            sa_info, scopes=SCOPES
        )
        print("[인증] 환경변수 GDRIVE_SERVICE_ACCOUNT_JSON 사용")
    else:
        # 로컬: 파일에서 읽기
        if not os.path.exists(LOCAL_SA_PATH):
            raise FileNotFoundError(
                f"서비스 계정 키 파일이 없습니다: {LOCAL_SA_PATH}\n"
                "GCP 콘솔 → IAM → 서비스 계정 → 키 만들기(JSON) 후 저장하세요."
            )
        creds = service_account.Credentials.from_service_account_file(
            LOCAL_SA_PATH, scopes=SCOPES
        )
        print(f"[인증] 로컬 파일 사용: {LOCAL_SA_PATH}")

    return build("drive", "v3", credentials=creds)


def find_existing_file(service, name, folder_id):
    """Drive 폴더에서 동일 이름 파일 ID를 찾는다 (공유 드라이브 포함)."""
    q = f"name='{name}' and '{folder_id}' in parents and trashed=false"
    results = service.files().list(
        q=q,
        fields="files(id, name)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
    ).execute()
    files = results.get("files", [])
    return files[0]["id"] if files else None


def upload_file(service, local_path, folder_id):
    from googleapiclient.http import MediaFileUpload

    name     = os.path.basename(local_path)
    mimetype = mimetypes.guess_type(local_path)[0] or "application/octet-stream"
    media    = MediaFileUpload(local_path, mimetype=mimetype, resumable=False)

    existing_id = find_existing_file(service, name, folder_id)
    if existing_id:
        service.files().update(
            fileId=existing_id,
            media_body=media,
            supportsAllDrives=True,
        ).execute()
        print(f"  [업데이트] {name}")
    else:
        service.files().create(
            body={"name": name, "parents": [folder_id]},
            media_body=media,
            fields="id",
            supportsAllDrives=True,
        ).execute()
        print(f"  [신규]     {name}")


def main():
    if not FOLDER_ID:
        print("[SKIP] GDRIVE_FOLDER_ID 환경변수가 설정되지 않았습니다.")
        return

    try:
        service = get_drive_service()
    except (ImportError, FileNotFoundError) as e:
        print(f"[ERROR] Drive 서비스 초기화 실패: {e}")
        return

    if not os.path.isdir(SHARED_DOCS_DIR):
        print(f"[ERROR] 공유 폴더 없음: {SHARED_DOCS_DIR}")
        return

    files = [f for f in os.listdir(SHARED_DOCS_DIR)
             if os.path.isfile(os.path.join(SHARED_DOCS_DIR, f))]

    if not files:
        print(f"[INFO] {SHARED_DOCS_DIR} 에 업로드할 파일이 없습니다.")
        return

    print(f"\n업로드 대상: {len(files)}개 파일 → 폴더 {FOLDER_ID}")
    uploaded, failed = 0, 0

    for filename in sorted(files):
        local_path = os.path.join(SHARED_DOCS_DIR, filename)
        try:
            upload_file(service, local_path, FOLDER_ID)
            uploaded += 1
        except Exception as e:
            print(f"  [ERROR]    {filename}: {e}")
            failed += 1

    print(f"\n완료: {uploaded}개 업로드 / {failed}개 실패")
    print(f"Drive 폴더: https://drive.google.com/drive/folders/{FOLDER_ID}")


if __name__ == "__main__":
    main()
