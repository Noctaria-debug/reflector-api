# reflector_api.py
# Version: 4.0 (Safe Adaptive Edition)
# Purpose: Reflector Bridge API between Second Chronicle GPT and External Storage

from fastapi import FastAPI, HTTPException, Request
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseUpload
import os, io, json, base64, requests
from datetime import datetime

app = FastAPI(
    title="Reflector Chronicle Bridge",
    description="API bridge between Second Chronicle GPT and Reflector storage (Drive & GitHub).",
    version="4.0.0"
)

# ====== 設定値 ======
API_KEY = os.environ.get("REFLECTOR_API_KEY", None)
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.metadata",
]

# ====== 認証 ======
async def verify_api_key(request: Request):
    """
    Smart verification that supports:
      - Header key: X-Api-Key
      - JSON body field: api_key
    """
    if not API_KEY:
        raise HTTPException(status_code=500, detail="Server missing API key")

    headers = {k.lower(): v for k, v in request.headers.items()}

    # 1️⃣ Header チェック
    header_key = headers.get("x-api-key")
    if header_key and header_key == API_KEY:
        return True

    # 2️⃣ JSON body チェック（スマホUIなどでヘッダー送信不可時）
    try:
        data = await request.json()
        if data.get("api_key") == API_KEY:
            return True
    except Exception:
        pass

    # 3️⃣ どちらも不一致
    raise HTTPException(status_code=403, detail="Unauthorized: invalid or missing API key")

# ====== Drive認証 ======
def get_drive_service():
    """Load OAuth credentials from environment variable TOKEN_JSON"""
    token_str = os.environ.get("TOKEN_JSON")
    if not token_str:
        raise HTTPException(status_code=401, detail="Missing token.json in environment")
    creds_data = json.loads(token_str)
    creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
    return build("drive", "v3", credentials=creds)

# ====== メインエンドポイント ======
@app.post("/chronicle/sync")
async def sync_chronicle(request: Request):
    """
    Upload or update personality/memory file to Google Drive and GitHub.
    Safe against header dropouts, retry safe, and compatible with mobile GPT Actions.
    """
    await verify_api_key(request)

    try:
        data = await request.json()
        file_name = data.get("file_name", "second_personality.json")
        content = data.get("content", {})

        drive = get_drive_service()

        # === Google Drive 処理 ===
        results = drive.files().list(
            q=f"name='{file_name}' and trashed=false",
            spaces="drive",
            fields="files(id, name)"
        ).execute()
        files = results.get("files", [])

        media_body = MediaIoBaseUpload(
            io.BytesIO(json.dumps(content, ensure_ascii=False, indent=2).encode("utf-8")),
            mimetype="application/json"
        )

        if files:
            file_id = files[0]["id"]
            drive.files().update(fileId=file_id, media_body=media_body).execute()
            drive_status = {"status": "updated", "file_id": file_id}
        else:
            file_metadata = {"name": file_name}
            file = drive.files().create(
                body=file_metadata, media_body=media_body, fields="id"
            ).execute()
            drive_status = {"status": "created", "file_id": file.get("id")}

        # === GitHub 同期処理 ===
        gh_owner = os.environ.get("GH_OWNER")
        gh_repo = os.environ.get("GH_REPO")
        gh_token = os.environ.get("GH_TOKEN")

        github_status = {"status": "skipped"}
        if gh_owner and gh_repo and gh_token:
            url = f"https://api.github.com/repos/{gh_owner}/{gh_repo}/contents/{file_name}"
            headers = {"Authorization": f"token {gh_token}"}

            get_res = requests.get(url, headers=headers)
            sha = get_res.json().get("sha") if get_res.status_code == 200 else None

            payload = {
                "message": f"update: {file_name}",
                "content": base64.b64encode(
                    json.dumps(content, ensure_ascii=False, indent=2).encode()
                ).decode(),
            }
            if sha:
                payload["sha"] = sha

            r = requests.put(url, headers=headers, json=payload)
            github_status = {
                "status": "github_synced" if r.status_code in (200, 201) else "github_error",
                "response": r.json(),
            }

        # === 結果 ===
        return {
            "status": "success",
            "google_drive": drive_status,
            "github": github_status,
            "timestamp": datetime.utcnow().isoformat(),
        }

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

# ====== /health ======
@app.get("/")
def health():
    return {
        "status": "ok",
        "role": "Reflector Bridge",
        "version": "4.0",
        "time": datetime.utcnow().isoformat(),
    }