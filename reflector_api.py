import os
import json
import base64
import io
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

app = FastAPI()

# ==========================
# モデル
# ==========================
class ChroniclePayload(BaseModel):
    file_name: str
    content: dict = None


# ==========================
# Google Drive 同期
# ==========================
def sync_to_google_drive(file_name, content):
    try:
        creds_data = json.loads(os.getenv("TOKEN_JSON"))
        creds = Credentials.from_authorized_user_info(creds_data)
        service = build("drive", "v3", credentials=creds)

        results = service.files().list(
            q=f"name='{file_name}' and trashed=false",
            spaces="drive",
            fields="files(id, name)"
        ).execute()

        files = results.get("files", [])
        content_str = json.dumps(content, ensure_ascii=False, indent=2)
        media_body = MediaIoBaseUpload(io.BytesIO(content_str.encode()), mimetype="application/json")

        if files:
            file_id = files[0]["id"]
            service.files().update(
                fileId=file_id,
                body={"name": file_name},
                media_body=media_body
            ).execute()
            return {"status": "updated", "file_id": file_id}
        else:
            file_metadata = {"name": file_name}
            file = service.files().create(
                body=file_metadata,
                media_body=media_body,
                fields="id"
            ).execute()
            return {"status": "created", "file_id": file.get("id")}
    except Exception as e:
        return {"error": str(e)}


# ==========================
# GitHub 同期
# ==========================
def sync_to_github(file_name, content):
    try:
        owner = os.getenv("GH_OWNER")
        repo = os.getenv("GH_REPO")
        token = os.getenv("GH_TOKEN")

        if not all([owner, repo, token]):
            raise HTTPException(status_code=400, detail="GitHub環境変数が不足しています")

        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_name}"
        headers = {"Authorization": f"token {token}"}

        # ファイルの存在確認（SHA取得）
        r = requests.get(url, headers=headers)
        sha = r.json().get("sha") if r.status_code == 200 else None

        encoded_content = base64.b64encode(
            json.dumps(content, ensure_ascii=False, indent=2).encode()
        ).decode()

        data = {"message": f"update: {file_name}", "content": encoded_content}
        if sha:
            data["sha"] = sha

        response = requests.put(url, headers=headers, json=data)
        if response.status_code not in [200, 201]:
            return {"error": f"GitHub sync failed: {response.text}"}

        return {"status": "github_synced", "response": response.json()}
    except Exception as e:
        return {"error": str(e)}


# ==========================
# /chronicle/sync
# ==========================
@app.post("/chronicle/sync")
async def chronicle_sync(payload: ChroniclePayload):
    file_name = payload.file_name
    content = payload.content or {}

    drive_result = sync_to_google_drive(file_name, content)
    github_result = sync_to_github(file_name, content)

    return {
        "google_drive": drive_result,
        "github": github_result
    }


# ==========================
# /chronicle/load
# ==========================
@app.post("/chronicle/load")
async def chronicle_load(payload: ChroniclePayload):
    creds_data = json.loads(os.getenv("TOKEN_JSON"))
    creds = Credentials.from_authorized_user_info(creds_data)
    service = build("drive", "v3", credentials=creds)

    results = service.files().list(
        q=f"name='{payload.file_name}' and trashed=false",
        spaces="drive",
        fields="files(id, name)"
    ).execute()

    files = results.get("files", [])
    if not files:
        raise HTTPException(status_code=404, detail="ファイルが見つかりません")

    file_id = files[0]["id"]
    request = service.files().get_media(fileId=file_id)
    content = request.execute()

    return {"status": "loaded", "content": json.loads(content)}