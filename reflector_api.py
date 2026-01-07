# reflector_api.py (Chronicle Bridge Final Render Edition)
# Fully integrated and Render-compatible Google Drive Sync API

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
    """Load OAuth credentials from environment variables (Render-compatible)."""
    try:
        # 1️⃣ Load TOKEN_JSON
        token_str = os.getenv("TOKEN_JSON")
        if not token_str:
            raise HTTPException(status_code=401, detail="Missing TOKEN_JSON in environment")

        creds_data = json.loads(token_str)

        # 2️⃣ Load Client ID / Secret explicitly
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        if not client_id or not client_secret:
            raise HTTPException(status_code=401, detail="Missing GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET")

        # 3️⃣ Build Credentials (explicit form avoids 'invalid_client')
        creds = Credentials(
            token=creds_data.get("access_token"),
            refresh_token=creds_data.get("refresh_token"),
            token_uri=creds_data.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=client_id,
            client_secret=client_secret,
            scopes=creds_data.get("scopes", SCOPES),
        )

        # 4️⃣ Build Google Drive service
        return build("drive", "v3", credentials=creds)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google auth failed: {e}")


# ====== /chronicle/sync ======
@app.post("/chronicle/sync")
async def sync_memory(request: Request):
    """Upload or update memory file to Google Drive"""
    try:
        data = await request.json()
        file_name = data.get("file_name", "second_memory.json")
        content = data.get("content", {})

        drive = get_drive_service()

        # Check if file already exists
        results = drive.files().list(
            q=f"name='{file_name}' and trashed=false",
            spaces="drive",
            fields="files(id, name)"
        ).execute()
        files = results.get("files", [])

        # Prepare JSON data for upload
        media_body = MediaIoBaseUpload(
            io.BytesIO(json.dumps(content, ensure_ascii=False, indent=2).encode("utf-8")),
            mimetype="application/json"
        )

        if files:
            # Update existing file
            file_id = files[0]["id"]
            drive.files().update(fileId=file_id, media_body=media_body).execute()
            return {"status": "updated", "file_id": file_id}
        else:
            # Create new file
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

        # Find the file
        results = drive.files().list(
            q=f"name='{file_name}' and trashed=false",
            spaces="drive",
            fields="files(id, name)"
        ).execute()
        files = results.get("files", [])
        if not files:
            raise HTTPException(status_code=404, detail="File not found")

        # Download file content
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
    """Health check endpoint"""
    return {"status": "ok", "role": "Chronicle Bridge", "time": datetime.utcnow().isoformat()}