// =============================================================
// 🔄 /chronicle/sync - Reflector Proxy Bridge (Full Payload Forwarding)
// =============================================================
app.post("/chronicle/sync", async (req, res) => {
  try {
    console.log("Incoming Reflector Sync:", req.body);

    const payload = req.body || {};

    // Reflector API endpoint (FastAPI側)
    const apiUrl =
      process.env.API_URL ||
      "https://reflector-api.onrender.com/chronicle/sync";
    const apiKey = process.env.REFLECTOR_API_KEY;

    let apiResponse;

    try {
      const { default: fetch } = await import("node-fetch");

      // ✅ payload 全体をそのまま Reflector API に送信
      const response = await fetch(apiUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Api-Key": apiKey || "",
        },
        body: JSON.stringify(payload),
      });

      const text = await response.text();
      try {
        apiResponse = JSON.parse(text);
      } catch {
        apiResponse = { raw: text };
      }
    } catch (err) {
      console.error("Upstream Reflector API Error:", err.message);
      apiResponse = { error: err.message };
    }

    // Proxy側レスポンス
    res.json({
      ok: true,
      message: "Data relayed successfully via Reflector Proxy (full payload)",
      from: "proxy",
      target: apiUrl,
      received_keys: Object.keys(payload),
      response: apiResponse,
    });
  } catch (err) {
    console.error("Error in /chronicle/sync:", err);
    res.status(500).json({
      ok: false,
      message: "Internal Server Error",
      error: err.message,
    });
  }
});