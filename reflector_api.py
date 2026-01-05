# reflector_api.py  (Chronicle Bridge edition)

from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
import os, base64, json, requests, io
from datetime import datetime

app = Flask(__name__)

# ====== 認証設定 ======
SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive.metadata",
]

# GitHub設定（Render環境変数から読み込み）
GH_OWNER = os.getenv("GH_OWNER", "Noctaria-debug")
GH_REPO = os.getenv("GH_REPO", "Second_Chronicle")
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
