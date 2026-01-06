from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import json
import os
import io
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

app = FastAPI()

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

def get_drive_service():
    """Load OAuth credentials from environment variable TOKEN_JSON."""
    token_str = os.environ.get("TOKEN_JSON")
    if not token_str:
        raise HTTPException(status_code=401, detail="Missing token.json in environment")
    creds_data = json.loads(token_str)
    creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
    return build("drive", "v3", credentials=creds)

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
            q=f"name='{file_name}' and trashed=false", spaces="drive",
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

@app.post("/chronicle/load")
async def load_memory(request: Request):
    """Read memory file from Google Drive"""
    try:
        data = await request.json()
        file_name = data.get("file_name", "second_memory.json")

        drive = get_drive_service()

        results = drive.files().list(
            q=f"name='{file_name}' and trashed=false", spaces="drive",
            fields="files(id, name)"
        ).execute()
        files = results.get("files", [])
        if not files:
            raise HTTPException(status_code=404, detail="File not found")

        file_id = files[0]["id"]
        request = drive.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        buffer.seek(0)

        content = json.load(buffer)
        return {"status": "loaded", "content": content}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))", "Second_Chronicle")
GH_TOKEN = os.getenv("GH_TOKEN")

# Google OAuthトークンファイル
TOKEN_FILE = "token.json"

# ====== Google Drive操作 ======
def get_drive_service():
    if not os.path.exists(TOKEN_FILE):
        raise Exception("Missing token.json")
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    return build("drive", "v3", credentials=creds)

def download_from_drive(file_name: str):
    drive = get_drive_service()
    results = drive.files().list(q=f"name='{file_name}'", fields="files(id, name)").execute()
    files = results.get("files", [])
    if not files:
        return None
    file_id = files[0]["id"]
    content = drive.files().get_media(fileId=file_id).execute()
    return content.decode("utf-8") if isinstance(content, bytes) else content

# ====== GitHub操作 ======
def upload_to_github(path: str, content: str, message: str):
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

def fetch_from_github(path: str):
    url = f"https://api.github.com/repos/{GH_OWNER}/{GH_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GH_TOKEN}"}
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        return None
    data = resp.json()
    return base64.b64decode(data["content"]).decode("utf-8")

# ====== APIエンドポイント ======

@app.route("/")
def index():
    return jsonify({"status": "ok", "role": "Chronicle Bridge", "time": datetime.utcnow().isoformat()})

@app.post("/chronicle/sync")
def chronicle_sync():
    """Drive→GitHub同期"""
    try:
        payload = request.get_json()
        file_name = payload.get("file_name", "second_memory.json")

        # Driveから取得
        content = download_from_drive(file_name)
        if not content:
            return jsonify({"error": "Drive file not found"}), 404

        # GitHubへ保存
        upload_to_github(
            f"data/memory/{file_name}",
            content,
            f"Sync memory from Reflector at {datetime.utcnow().isoformat()}"
        )
        return jsonify({"ok": True, "synced": file_name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/chronicle/load")
def chronicle_load():
    """GitHub→返却（GPT用のロード）"""
    try:
        payload = request.get_json()
        file_name = payload.get("file_name", "second_memory.json")

        content = fetch_from_github(f"data/memory/{file_name}")
        if not content:
            return jsonify({"error": "Memory not found in repo"}), 404

        return jsonify({"ok": True, "file_name": file_name, "content": json.loads(content)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.post("/drive/upload")
def drive_upload():
    """Driveに直接アップロード"""
    try:
        payload = request.get_json()
        file_name = payload["file_name"]
        content = json.dumps(payload["content"], ensure_ascii=False)
        drive = get_drive_service()
        file_metadata = {"name": file_name}
        media = io.BytesIO(content.encode("utf-8"))
        drive.files().create(body=file_metadata, media_body=media, fields="id").execute()
        return jsonify({"ok": True, "file_name": file_name})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
