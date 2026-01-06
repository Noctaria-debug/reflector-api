# reflector_api.py (Chronicle Bridge Final)

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
    """Load OAuth credentials from environment variable TOKEN_JSON."""
    token_str = os.environ.get("TOKEN_JSON")
    if not token_str:
        raise HTTPException(status_code=401, detail="Missing token.json in environment")
    creds_data = json.loads(token_str)
    creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
    return build("drive", "v3", credentials=creds)

# ====== /chronicle/sync ======
@app.post("/chronicle/sync")
async def sync_memory(request: Request):
    """Upload or update memory file to Google Drive"""
    try:
        data = await request.json()
        file_name = data.get("file_name", "second_memory.json")
        content = data.get("content", {})

        drive = get_drive_service()

        # Search if file exists
        results = drive.files().list(
            q=f"name='{file_name}' and trashed=false",
            spaces="drive",
            fields="files(id, name)"
        ).execute()
        files = results.get("files", [])

        media_body = MediaIoBaseUpload(
            io.BytesIO(json.dumps(content).encode("utf-8")),
            mimetype="application/json"
        )

        if files:
            file_id = files[0]["id"]
            drive.files().update(fileId=file_id, media_body=media_body).execute()
            return {"status": "updated", "file_id": file_id}
        else:
            file_metadata = {"name": file_name}
            file = drive.files().create(
                body=file_metadata, media_body=media_body, fields="id"
            ).execute()
            return {"status": "created", "file_id": file.get("id")}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ====== /chronicle/load ======
@app.post("/chronicle/load")
async def load_memory(request: Request):
    """Read memory file from Google Drive"""
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