from fastapi import FastAPI, HTTPException, Request, Header
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
import os, io, json, base64, requests
from datetime import datetime

app = FastAPI()

# API Key verification
API_KEY = os.environ.get("REFLECTOR_API_KEY")
def verify_api_key(request_key: str):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="Server missing API key")
    if request_key != API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized: invalid API key")

# Google Drive configuration
SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.metadata",
]
def get_drive_service():
    token_str = os.environ.get("TOKEN_JSON")
    if not token_str:
        raise HTTPException(status_code=401, detail="Missing token.json in environment")
    try:
        creds = Credentials.from_authorized_user_info(json.loads(token_str), SCOPES)
        return build("drive", "v3", credentials=creds)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Drive credential error: {str(e)}")

# Helper to download existing JSON
def load_existing_json(drive, file_id):
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

# Recursive merge
def merge_json(old, new):
    merged = old.copy()
    for k, v in new.items():
        if isinstance(v, dict) and k in merged and isinstance(merged[k], dict):
            merged[k] = merge_json(merged[k], v)
        else:
            merged[k] = v
    return merged

# Sync endpoint
@app.post("/chronicle/sync")
async def sync_memory(request: Request, x_api_key: str = Header(None)):
    verify_api_key(x_api_key)
    data = await request.json()
    file_name = data.get("file_name", "second_memory.json")
    drive = get_drive_service()

    # Build content
    new_content = {
        "test": data.get("test"),
        "data": data.get("data"),
        "emotion": data.get("emotion"),
        "memory": data.get("memory"),
        "reflection": data.get("reflection"),
        "timestamp": datetime.utcnow().isoformat()
    }
    new_content = {k: v for k, v in new_content.items() if v is not None}

    # Find existing file
    results = drive.files().list(
        q=f"name='{file_name}' and trashed=false",
        spaces="drive",
        fields="files(id, name)"
    ).execute()
    files = results.get("files", [])

    # Decide whether to merge or replace
    if files and not data.get("create_new") and not data.get("reset_drive_file"):
        file_id = files[0]["id"]
        existing_content = load_existing_json(drive, file_id)
        merged_content = merge_json(existing_content, new_content)
        target_content = merged_content
    else:
        target_content = new_content

    # Prepare upload body
    media_body = MediaIoBaseUpload(
        io.BytesIO(json.dumps(target_content, ensure_ascii=False, indent=2).encode("utf-8")),
        mimetype="application/json"
    )

    # Write to Drive
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

    # GitHub sync
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

# Load endpoint
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

# Health check
@app.get("/")
def health():
    return {
        "status": "ok",
        "role": "Reflector Bridge",
        "time": datetime.utcnow().isoformat(),
        "environment": "production"
    }