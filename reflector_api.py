from flask import Flask, request, jsonify
import os
import json
import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2.credentials import Credentials

app = Flask(__name__)

@app.route("/")
def index():
    return jsonify({"status": "Reflector API active"})

@app.route("/drive/sync", methods=["POST"])
def sync_drive():
    try:
        data = request.get_json()
        file_name = data.get("file_name")
        content = data.get("content")

        if not file_name or not content:
            return jsonify({"error": "file_name and content required"}), 400

        # OAuthトークンをRenderの環境変数から読み込む
        token_json = os.environ.get("GOOGLE_TOKEN_JSON")
        creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")

        if not token_json or not creds_json:
            return jsonify({"error": "Missing OAuth credentials"}), 500

        token_data = json.loads(token_json)
        creds_data = json.loads(creds_json)

        creds = Credentials(
            token=token_data.get("token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=creds_data["installed"]["client_id"],
            client_secret=creds_data["installed"]["client_secret"],
            scopes=[
                "https://www.googleapis.com/auth/drive.file",
                "https://www.googleapis.com/auth/drive.metadata",
                "https://www.googleapis.com/auth/drive.appdata"
            ]
        )

        service = build("drive", "v3", credentials=creds)

        # Driveにアップロード
        file_metadata = {"name": file_name}
        media = MediaIoBaseUpload(
            io.BytesIO(json.dumps(content, ensure_ascii=False, indent=2).encode("utf-8")),
            mimetype="application/json"
        )
        uploaded_file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id"
        ).execute()

        return jsonify({"status": "uploaded", "file": file_name, "id": uploaded_file.get("id")})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
