# =============================================================
# Reflector API - Unified Emotion/Memory Sync Version (403-safe)
# for Second Chronicle GPT + Reflector Proxy
# =============================================================

from fastapi import FastAPI, HTTPException, Request, Header
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaIoBaseUpload
import os, io, json, base64, requests
from datetime import datetime

app = FastAPI()

# =============================================================
# 🔐 API Key 認証設定
# =============================================================
API_KEY = os.environ.get("REFLECTOR_API_KEY", None)

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
# 🔄 /chronicle/sync
# =============================================================
@app.post("/chronicle/sync")
async def sync_memory(request: Request, x_api_key: str = Header(None)):
    """Upload or update memory/reflection/emotion data to Google Drive + GitHub."""
    verify_api_key(x_api_key)

    try:
        data = await request.json()

        # ----- データ抽出 -----
        file_name = data.get("file_name", "second_memory.json")

        # ✅ 入力統合
        content = {
            "test": data.get("test"),
            "data": data.get("data"),
            "emotion": data.get("emotion"),
            "memory": data.get("memory"),
            "reflection": data.get("reflection"),
            "timestamp": datetime.utcnow().isoformat()
        }
        content = {k: v for k, v in content.items() if v is not None}

        # Drive クライアント初期化
        drive = get_drive_service()

        # =============================================================
        # 🔁 Drive ファイル検索
        # =============================================================
        results = drive.files().list(
            q=f"name='{file_name}' and trashed=false",
            spaces="drive",
            fields="files(id, name)"
        ).execute()
        files = results.get("files", [])

        # ✅ reset_drive_file / create_new 指定で強制的に新規作成
        if data.get("create_new") or data.get("reset_drive_file"):
            files = []

        # =============================================================
        # 📄 JSON → バイナリ変換
        # =============================================================
        media_body = MediaIoBaseUpload(
            io.BytesIO(json.dumps(content, ensure_ascii=False, indent=2).encode("utf-8")),
            mimetype="application/json"
        )

        # =============================================================
        # 📝 Drive ファイル書き込み
        # =============================================================
        try:
            if files:
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
        except Exception as e:
            # ファイルアクセス拒否（403）の場合は再作成を試みる
            if "appNotAuthorizedToFile" in str(e):
                file_metadata = {"name": f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{file_name}"}
                new_file = drive.files().create(
                    body=file_metadata, media_body=media_body, fields="id"
                ).execute()
                drive_status = {
                    "status": "recreated_due_to_permission_error",
                    "file_id": new_file.get("id"),
                    "link": f"https://drive.google.com/file/d/{new_file.get('id')}/view"
                }
            else:
                raise

        # =============================================================
        # 🐙 GitHub 同期（環境変数が存在する場合のみ）
        # =============================================================
        gh_owner = os.environ.get("GH_OWNER")
        gh_repo = os.environ.get("GH_REPO")
        gh_token = os.environ.get("GH_TOKEN")

        if gh_owner and gh_repo and gh_token:
            url = f"https://api.github.com/repos/{gh_owner}/{gh_repo}/contents/{file_name}"
            headers = {"Authorization": f"token {gh_token}"}
            r_get = requests.get(url, headers=headers)
            sha = r_get.json().get("sha") if r_get.status_code == 200 else None

            payload = {
                "message": f"update: {file_name}",
                "content": base64.b64encode(
                    json.dumps(content, ensure_ascii=False, indent=2).encode()
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

        # =============================================================
        # 🧠 最終レスポンス
        # =============================================================
        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "google_drive": drive_status,
            "github": github_status,
            "data_received": content
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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