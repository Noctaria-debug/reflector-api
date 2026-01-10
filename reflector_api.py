# reflector_api.py (GPT Bridge Enabled)

from fastapi import FastAPI, HTTPException, Request, Header
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
import os, io, json, base64, requests
from datetime import datetime

app = FastAPI()

# ====== 認証設定 ======
API_KEY = os.environ.get("REFLECTOR_API_KEY", None)

def verify_api_key(request_key: str):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="Server missing API key")
    if request_key != API_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized: invalid API key")

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
async def sync_memory(request: Request, x_api_key: str = Header(None), authorization: str = Header(None)):
    """Upload or update memory file to Google Drive and GitHub"""
    # Accept both header formats: X-Api-Key and Authorization: Bearer
    request_key = None
    if x_api_key:
        request_key = x_api_key
    elif authorization and authorization.startswith("Bearer "):
        request_key = authorization.split(" ")[1]

    verify_api_key(request_key)
    try:
        data = await request.json()
        file_name = data.get("file_name", "second_memory.json")
        content = data.get("content", {})

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
            drive.files().update(fileId=file_id, media_body=media_body).execute()
            drive_status = {"status": "updated", "file_id": file_id}
        else:
            file_metadata = {"name": file_name}
            file = drive.files().create(
                body=file_metadata, media_body=media_body, fields="id"
            ).execute()
            drive_status = {"status": "created", "file_id": file.get("id")}

        # ===== GitHub同期 =====
        gh_owner = os.environ.get("GH_OWNER")
        gh_repo = os.environ.get("GH_REPO")
        gh_token = os.environ.get("GH_TOKEN")

        if gh_owner and gh_repo and gh_token:
            url = f"https://api.github.com/repos/{gh_owner}/{gh_repo}/contents/{file_name}"
            headers = {"Authorization": f"token {gh_token}"}
            data = {
                "message": f"update: {file_name}",
                "content": base64.b64encode(json.dumps(content).encode()).decode()
            }
            r = requests.put(url, headers=headers, json=data)
            github_status = {
                "status": "github_synced" if r.status_code in (200, 201) else "github_error",
                "response": r.json()
            }
        else:
            github_status = {"status": "skipped"}

        return {"google_drive": drive_status, "github": github_status}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ====== /health ======
@app.get("/")
def health():
    return {
        "status": "ok",
        "role": "Reflector Bridge",
        "time": datetime.utcnow().isoformat()
    }