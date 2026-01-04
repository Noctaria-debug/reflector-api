from flask import Flask, request, jsonify
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2 import service_account
import os
import io
import json

app = Flask(__name__)

# ============================================================
# Google Drive 認証設定
# ============================================================

def get_drive_service():
    """
    Google Drive API の認証情報を取得
    Render環境変数 GOOGLE_CREDENTIALS_JSON から読み込む
    """
    try:
        if "GOOGLE_CREDENTIALS_JSON" in os.environ:
            creds_json = os.environ["GOOGLE_CREDENTIALS_JSON"]
            creds_dict = json.loads(creds_json)
            creds = service_account.Credentials.from_service_account_info(
                creds_dict, scopes=["https://www.googleapis.com/auth/drive.file"]
            )
        else:
            raise RuntimeError("環境変数 GOOGLE_CREDENTIALS_JSON が設定されていません。")
        service = build("drive", "v3", credentials=creds)
        return service
    except Exception as e:
        print(f"[ERROR] 認証に失敗しました: {e}")
        return None


# ============================================================
# API エンドポイント
# ============================================================

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "Reflector API active"}), 200


@app.route("/drive/sync", methods=["POST"])
def drive_sync():
    """
    Second の YAMLやJSONデータをGoogle Driveにアップロードする。
    ファイルが存在すれば更新、存在しなければ新規作成。
    """
    try:
        data = request.get_json()
        file_name = data.get("file_name")
        content = data.get("content")

        if not file_name or not content:
            return jsonify({"error": "file_name と content は必須です"}), 400

        service = get_drive_service()
        if not service:
            return jsonify({"error": "Google Drive 認証に失敗しました"}), 500

        # ファイルをJSONとしてバイナリ化
        file_bytes = io.BytesIO(json.dumps(content, ensure_ascii=False, indent=2).encode("utf-8"))

        # 既存ファイルを検索
        results = service.files().list(
            q=f"name='{file_name}' and trashed=false",
            spaces="drive",
            fields="files(id, name)"
        ).execute()

        if results.get("files"):
            file_id = results["files"][0]["id"]
            service.files().update(
                fileId=file_id,
                media_body=MediaIoBaseUpload(file_bytes, mimetype="application/json", resumable=True)
            ).execute()
            return jsonify({"status": "updated", "file_id": file_id}), 200
        else:
            file_metadata = {"name": file_name}
            service.files().create(
                body=file_metadata,
                media_body=MediaIoBaseUpload(file_bytes, mimetype="application/json", resumable=True),
                fields="id"
            ).execute()
            return jsonify({"status": "created", "file_name": file_name}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# メイン起動
# ============================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
