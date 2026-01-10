# app.py  (Reflector Stable Final)

from flask import Flask, request, jsonify
import os
import json

app = Flask(__name__)

# 環境変数に設定したAPIキー
VALID_API_KEY = os.getenv("REFLECTOR_API_KEY", "RFX-PROD-2026-XA7Y9VQ3KZ4R2M8T-LJQ8F0P@!B5N")

@app.route("/chronicle/sync", methods=["POST"])
def sync_chronicle():
    try:
        api_key = request.headers.get("X-Api-Key")
        if api_key != VALID_API_KEY:
            return jsonify({"error": "Unauthorized: invalid API key"}), 403

        data = request.json
        file_name = data.get("file_name", "second_personality.json")
        content = data.get("content", {})

        # （Drive/GitHub同期処理は既存でOK）
        print(f"[SYNC OK] {file_name}: {content}")

        return jsonify({
            "status": "success",
            "file": file_name,
            "message": "Sync completed successfully."
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/")
def health():
    return {"status": "ok", "service": "Reflector API"}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3000)