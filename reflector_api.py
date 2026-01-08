def get_drive_service():
    """Load OAuth credentials safely, with debug logs"""
    print("========== GOOGLE DRIVE SERVICE DEBUG ==========")
    print("🧩 ENVIRONMENT DUMP (trimmed for safety) ==========")
    for key in ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "TOKEN_JSON"]:
        val = os.environ.get(key)
        print(f"{key} =>", "SET" if val else "None")
    print("================================================")

    token_str = os.environ.get("TOKEN_JSON")
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")

    print("DEBUG_CLIENT_ID:", client_id)
    print("DEBUG_CLIENT_SECRET_EXISTS:", bool(client_secret))
    print("DEBUG_TOKEN_EXISTS:", bool(token_str))