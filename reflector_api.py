# reflector_api.py (Safe Debug + FastAPI app fix)

from fastapi import FastAPI, HTTPException, Request
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
import os, io, json
from datetime import datetime

# =============================
# FastAPI アプリ定義（必須）
# =============================
app = FastAPI()


# =============================
# Google Drive 設定
# =============================
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.metadata",
]


def get_drive_service():
    """Load OAuth credentials safely, with debug logs"""
    print("========== GOOGLE DRIVE SERVICE DEBUG ==========")
    print("🧩 ENVIRONMENT DUMP (trimmed for safety) ==========")
    for key in ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "TOKEN_JSON"]:
        val = os.environ.get(key)
        print(f"{key} =>", "SET" if val else "None")
    print("================================================")

    token_str = os.environ.get("TOKEN_JSON")
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")

    print("DEBUG_CLIENT_ID:", client_id)
    print("DEBUG_CLIENT_SECRET_EXISTS:", bool(client_secret))
    print("DEBUG_TOKEN_EXISTS:", bool(token_str))

    if not token_str:
        raise HTTPException(status_code=401, detail="Missing token.json in environment")

    try:
        creds_data = json.loads(token_str)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid TOKEN_JSON format")

    creds_data["client_id"] = client_id
    creds_data["client_secret"] = client_secret

    creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
    print("✅ GOOGLE DRIVE CREDENTIALS LOADED SUCCESSFULLY")

    return build("drive", "v3", credentials=creds)


# =============================
# /chronicle/sync
# =============================
@app.post("/chronicle/sync")
async def sync_memory(request: Request):
    """Upload or update memory file to Google Drive"""
    try:
        data = await request.json()
        file_name = data.get("file_name", "second_memory.json")
        content = data.get("content", {})

        print(f"SYNC_REQUEST → file_name={file_name}")

        drive = get_drive_service()

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
            print(f"🔁 Updating existing file: {file_id}")
            drive.files().update(fileId=file_id, media_body=media_body).execute()
            return {"status": "updated", "file_id": file_id}
        else:
            file_metadata = {"name": file_name}
            print(f"🆕 Creating new file: {file_name}")
            file = drive.files().create(
                body=file_metadata, media_body=media_body, fields="id"
            ).execute()
            return {"status": "created", "file_id": file.get("id")}

    except Exception as e:
        print("❌ ERROR in /chronicle/sync:", str(e))
        raise HTTPException(status_code=500, detail=str(e))


# =============================
# /chronicle/load
# =============================
@app.post("/chronicle/load")
async def load_memory(request: Request):
    """Read memory file from Google Drive"""
    try:
        data = await request.json()
        file_name = data.get("file_name", "second_memory.json")

        print(f"LOAD_REQUEST → file_name={file_name}")

        drive = get_drive_service()

        results = drive.files().list(
            q=f"name='{file_name}' and trashed=false",
            spaces="drive",
            fields="files(id, name)"
        ).execute()
        files = results.get("files", [])
        if not files:
            print("❌ File not found in Drive")
            raise HTTPException(status_code=404, detail="File not found")

        file_id = files[0]["id"]
        print(f"📥 Downloading file: {file_id}")

        request_drive = drive.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request_drive)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        buffer.seek(0)

        content = json.load(buffer)
        print("✅ File loaded successfully:", file_name)
        return {"status": "loaded", "content": content}

    except Exception as e:
        print("❌ ERROR in /chronicle/load:", str(e))
        raise HTTPException(status_code=500, detail=str(e))


# =============================
# /health
# =============================
@app.get("/")
def health():
    print("✅ Health check requested")
    return {
        "status": "ok",
        "role": "Chronicle Bridge",
        "time": datetime.utcnow().isoformat()
    }