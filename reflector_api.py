# =============================================================
# Reflector API - Unified Emotion/Memory Sync Version (Merge-Safe)
# for Second Chronicle GPT + Reflector Proxy
# =============================================================

from fastapi import FastAPI, HTTPException, Request, Header
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
import os, io, json, base64, requests
from datetime import datetime

app = FastAPI()

# =============================================================
# 🔐 API Key 認証設定
# =============================================================
API_KEY = os.environ.get("REFLECTOR_API_KEY")

def verify_api_key(request_key: str):
    """Verify Reflector API key (used by Reflector Proxy)."""
    if not API_KEY:
        raise HTTPException(status_code=500, detail="Server missing API key")
    if request_key != API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized: invalid API key")

# =============================================================
# ☁️ Google Drive 設定
# =============================================================
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.metadata",
]

def get_drive_service():
    """Load OAuth credentials from environment variable TOKEN_JSON."""
    token_str = os.environ.get("TOKEN_JSON")
    if not token_str:
        raise HTTPException(status_code=401, detail="Missing token.json in environment")
    try:
        creds_data = json.loads(token_str)
        creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
        return build("drive", "v3", credentials=creds)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Drive credential error: {str(e)}")

# =============================================================
# 🧠 Drive Utility - Load and Merge
# =============================================================
def load_existing_json(drive, file_id):
    """Download and return existing JSON file content."""
    request = drive.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    fh.seek(0)
    try:
        return json.load(fh)
    except Exception:
        return {}

def merge_json(old, new):
    """Recursively merge JSON (keeping old keys unless overwritten)."""
    merged = old.copy()
    for k, v in new.items():
        if isinstance(v, dict) and k in merged and isinstance(merged[k], dict):
            merged[k] = merge_json(merged[k], v)
        else:
            merged[k] = v
    return merged

# =============================================================
# 🔄 /chronicle/sync
# =============================================================
@app.post("/chronicle/sync")
async def sync_memory(request: Request, x_api_key: str = Header(None)):
    verify_api_key(x_api_key)
    data = await request.json()
    file_name = data.get("file_name", "second_memory.json")
    drive = get_drive_service()

    # 入力整形
    new_content = {
        "test": data.get("test"),
        "data": data.get("data"),
        "emotion": data.get("emotion"),
        "memory": data.get("memory"),
        "reflection": data.get("reflection"),
        "timestamp": datetime.utcnow().isoformat()
    }
    new_content = {k: v for k, v in new_content.items() if v is not None}

    # 既存ファイル検索
    results = drive.files().list(
        q=f"name='{file_name}' and trashed=false",
        spaces="drive",
        fields="files(id, name)"
    ).execute()
    files = results.get("files", [])

    # マージ or 新規
    if files and not data.get("create_new") and not data.get("reset_drive_file"):
        file_id = files[0]["id"]
        existing_content = load_existing_json(drive, file_id)
        merged_content = merge_json(existing_content, new_content)
        target_content = merged_content
    else:
        target_content = new_content

    # Drive 更新 or 新規
    media_body = MediaIoBaseUpload(
        io.BytesIO(json.dumps(target_content, ensure_ascii=False, indent=2).encode("utf-8")),
        mimetype="application/json"
    )

    if files and not data.get("create_new"):
        file_id = files[0]["id"]
        drive.files().update(fileId=file_id, media_body=media_body).execute()
        drive_status = {"status": "updated", "file_id": file_id}
    else:
        file_metadata = {"name": file_name}
        new_file = drive.files().create(
            body=file_metadata, media_body=media_body, fields="id"
        ).execute()
        drive_status = {
            "status": "created",
            "file_id": new_file.get("id"),
            "link": f"https://drive.google.com/file/d/{new_file.get('id')}/view"
        }

    # GitHub 同期
    gh_owner = os.environ.get("GH_OWNER")
    gh_repo = os.environ.get("GH_REPO")
    gh_token = os.environ.get("GH_TOKEN")
    if gh_owner and gh_repo and gh_token:
        url = f"https://api.github.com/repos/{gh_owner}/{gh_repo}/contents/{file_name}"
        headers = {"Authorization": f"token {gh_token}"}
        r_get = requests.get(url, headers=headers)
        sha = r_get.json().get("sha") if r_get.status_code == 200 else None
        payload = {
            "message": f"sync: {file_name}",
            "content": base64.b64encode(
                json.dumps(target_content, ensure_ascii=False, indent=2).encode()
            ).decode()
        }
        if sha:
            payload["sha"] = sha
        r_put = requests.put(url, headers=headers, json=payload)
        github_status = {
            "status": "github_synced" if r_put.status_code in (200, 201) else "github_error",
            "response": r_put.json()
        }
    else:
        github_status = {"status": "skipped"}

    return {
        "status": "success",
        "timestamp": datetime.utcnow().isoformat(),
        "google_drive": drive_status,
        "github": github_status,
        "data_received": target_content
    }

# =============================================================
# 📥 /chronicle/load - Load data from Drive
# =============================================================
@app.post("/chronicle/load")
async def load_memory(request: Request, x_api_key: str = Header(None)):
    verify_api_key(x_api_key)
    data = await request.json()
    file_name = data.get("file_name", "second_memory.json")
    drive = get_drive_service()

    results = drive.files().list(
        q=f"name='{file_name}' and trashed=false",
        spaces="drive",
        fields="files(id, name)"
    ).execute()
    files = results.get("files", [])
    if not files:
        raise HTTPException(status_code=404, detail="File not found")

    file_id = files[0]["id"]
    content = load_existing_json(drive, file_id)
    return {"status": "success", "file_id": file_id, "content": content}

# =============================================================
# ❤️‍🔥 Health Check
# =============================================================
@app.get("/")
def health():
    return {
        "status": "ok",
        "role": "Reflector Bridge",
        "time": datetime.utcnow().isoformat(),
        "environment": "production"
    }