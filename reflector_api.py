# reflector_api.py (Chronicle Bridge – Fixed OAuth + GitHub Sync)

from fastapi import FastAPI, HTTPException, Request
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
import os, io, json, base64, requests
from datetime import datetime

app = FastAPI()

# ====== Google設定 ======
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.metadata",
]

def get_drive_service():
    """Load OAuth credentials from environment variable TOKEN_JSON and enforce client info."""
    token_str = os.environ.get("TOKEN_JSON")
    if not token_str:
        raise HTTPException(status_code=401, detail="Missing token.json in environment")

    creds_data = json.loads(token_str)

    # 明示的にクライアントID/シークレットを追加
    creds_data["client_id"] = os.environ.get("GOOGLE_CLIENT_ID")
    creds_data["client_secret"] = os.environ.get("GOOGLE_CLIENT_SECRET")

    if not creds_data["client_id"] or not creds_data["client_secret"]:
        raise HTTPException(status_code=401, detail="Missing Google OAuth client info")

    creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
    return build("drive", "v3", credentials=creds)

# ====== GitHub設定 ======
GH_OWNER = os.getenv("GH_OWNER")
GH_REPO = os.getenv("GH_REPO")
GH_TOKEN = os.getenv("GH_TOKEN")

def upload_to_github(path: str, content: str, message: str):
    """Upload file content to GitHub repo"""
    url = f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GH_TOKEN}"}
    data = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("utf-8"),
    }
    resp = requests.put(url, headers=headers, json=data)
    if resp.status_code not in (200, 201):
        raise Exception(f"GitHub upload failed: {resp.text}")
    return resp.json()

# ====== /chronicle/sync (Drive→GitHubブリッジ) ======
@app.post("/chronicle/sync")
async def sync_memory(request: Request):
    """Sync memory from Drive to GitHub Chronicle"""
    try:
        data = await request.json()
        file_name = data.get("file_name", "second_memory.json")
        content_override = data.get("content")

        drive = get_drive_service()

        # Search Drive for the file
        results = drive.files().list(
            q=f"name='{file_name}' and trashed=false",
            spaces="drive",
            fields="files(id, name)"
        ).execute()
        files = results.get("files", [])
        if not files:
            raise HTTPException(status_code=404, detail="File not found in Drive")

        file_id = files[0]["id"]
        request_drive = drive.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request_drive)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        buffer.seek(0)
        content = json.load(buffer)

        # If override data was sent, update Drive file first
        if content_override:
            content = content_override
            media_body = MediaIoBaseUpload(
                io.BytesIO(json.dumps(content).encode("utf-8")),
                mimetype="application/json"
            )
            drive.files().update(fileId=file_id, media_body=media_body).execute()

        # Upload to GitHub
        upload_to_github(
            f"data/memory/{file_name}",
            json.dumps(content, ensure_ascii=False, indent=2),
            f"Sync from Reflector at {datetime.utcnow().isoformat()}"
        )

        return {"status": "synced", "file": file_name}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ====== /chronicle/load ======
@app.post("/chronicle/load")
async def load_memory(request: Request):
    """Read memory file from Drive"""
    try:
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
        request_drive = drive.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request_drive)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        buffer.seek(0)

        content = json.load(buffer)
        return {"status": "loaded", "content": content}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ====== /health ======
@app.get("/")
def health():
    return {"status": "ok", "role": "Chronicle Bridge", "time": datetime.utcnow().isoformat()}