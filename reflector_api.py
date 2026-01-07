# reflector_api.py (Chronicle Bridge Debug Render Edition)
# Full version with debug logging for Render environment

from fastapi import FastAPI, HTTPException, Request
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
import os, io, json
from datetime import datetime

app = FastAPI()

# ====== Google設定 ======
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.metadata",
]


def get_drive_service():
    """Load OAuth credentials from Render environment and log debug info."""
    try:
        # --- DEBUG START ---
        print("=== [Chronicle Bridge - get_drive_service()] ===")
        print("DEBUG_ENV_KEYS:", list(os.environ.keys())[:10])  # 最初の10個だけ表示
        print("DEBUG_CLIENT_ID:", os.getenv("GOOGLE_CLIENT_ID"))
        print("DEBUG_TOKEN_EXISTS:", "TOKEN_JSON" in os.environ)
        # --- DEBUG END ---

        token_str = os.getenv("TOKEN_JSON")
        if not token_str:
            raise HTTPException(status_code=401, detail="Missing TOKEN_JSON in environment")

        creds_data = json.loads(token_str)

        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

        if not client_id or not client_secret:
            raise HTTPException(status_code=401, detail="Missing GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET")

        creds = Credentials(
            token=creds_data.get("access_token"),
            refresh_token=creds_data.get("refresh_token"),
            token_uri=creds_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=client_id,
            client_secret=client_secret,
            scopes=creds_data.get("scopes", SCOPES),
        )

        service = build("drive", "v3", credentials=creds)
        print("DEBUG: Google Drive service initialized OK ✅")
        return service

    except Exception as e:
        print("DEBUG_ERROR:", e)
        raise HTTPException(status_code=500, detail=f"Google auth failed: {e}")


# ====== /chronicle/sync ======
@app.post("/chronicle/sync")
async def sync_memory(request: Request):
    """Upload or update memory file to Google Drive"""
    try:
        data = await request.json()
        file_name = data.get("file_name", "second_memory.json")
        content = data.get("content", {})

        print(f"=== [SYNC START] file_name={file_name} ===")

        drive = get_drive_service()

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
            print(f"DEBUG: File updated on Drive → {file_id}")
            return {"status": "updated", "file_id": file_id}
        else:
            file_metadata = {"name": file_name}
            file = drive.files().create(
                body=file_metadata, media_body=media_body, fields="id"
            ).execute()
            print(f"DEBUG: New file created → {file.get('id')}")
            return {"status": "created", "file_id": file.get("id")}

    except Exception as e:
        print("SYNC_ERROR:", e)
        raise HTTPException(status_code=500, detail=str(e))


# ====== /chronicle/load ======
@app.post("/chronicle/load")
async def load_memory(request: Request):
    """Read memory file from Google Drive"""
    try:
        data = await request.json()
        file_name = data.get("file_name", "second_memory.json")

        print(f"=== [LOAD START] file_name={file_name} ===")

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
        print(f"DEBUG: File {file_name} loaded successfully ✅")
        return {"status": "loaded", "content": content}

    except Exception as e:
        print("LOAD_ERROR:", e)
        raise HTTPException(status_code=500, detail=str(e))


# ====== /health ======
@app.get("/")
def health():
    """Health check endpoint"""
    print("DEBUG: /health checked at", datetime.utcnow().isoformat())
    return {"status": "ok", "role": "Chronicle Bridge", "time": datetime.utcnow().isoformat()}