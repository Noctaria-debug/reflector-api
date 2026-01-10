from flask import Flask, request, jsonify
import os
import json
import datetime

app = Flask(__name__)

# 環境変数からAPIキーを取得
API_KEY = os.getenv("REFLECTOR_API_KEY")

@app.route("/chronicle/sync", methods=["POST"])
def sync_chronicle():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Missing JSON body"}), 400

        # APIキーの検証
        key = data.get("api_key")
        if not key or key != API_KEY:
            return jsonify({"error": "Unauthorized: invalid API key"}), 403

        file_name = data.get("file_name", "default.json")
        content = data.get("content", {})

        # ローカルに一時保存（Renderでは一時ファイル扱い）
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        local_path = f"/tmp/{file_name}"
        with open(local_path, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)

        print(f"[SYNC] {file_name} saved locally at {timestamp}")

        return jsonify({
            "status": "success",
            "file_name": file_name,
            "timestamp": timestamp,
            "message": "File synced successfully"
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "online", "message": "Reflector API ready"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)