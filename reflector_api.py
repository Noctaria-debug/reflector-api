from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/")
def health_check():
    return jsonify({"status": "ok", "message": "Reflector API running"})

@app.route("/chronicle/sync", methods=["POST"])
def chronicle_sync():
    try:
        data = request.get_json(silent=True) or {}
        print("📥 Received data:", data)

        # シンプルな確認用レスポンス
        return jsonify({
            "status": "success",
            "message": "Data received successfully",
            "data_received": data
        }), 200
    except Exception as e:
        print("❌ Error in /chronicle/sync:", e)
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)