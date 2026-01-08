def get_drive_service():
    """Load OAuth credentials safely, ensuring client info is injected."""
    token_str = os.environ.get("TOKEN_JSON")
    if not token_str:
        raise HTTPException(status_code=401, detail="Missing token.json in environment")

    creds_data = json.loads(token_str)

    # Google OAuth情報をRender環境変数から強制注入
    creds_data["client_id"] = os.environ.get("GOOGLE_CLIENT_ID")
    creds_data["client_secret"] = os.environ.get("GOOGLE_CLIENT_SECRET")

    # デバッグログ（Renderログで確認可）
    print("DEBUG_CLIENT_ID:", creds_data.get("client_id"))
    print("DEBUG_CLIENT_SECRET_EXISTS:", bool(creds_data.get("client_secret")))

    if not creds_data["client_id"] or not creds_data["client_secret"]:
        raise HTTPException(status_code=401, detail="Missing Google OAuth client info")

    creds = Credentials.from_authorized_user_info(creds_data, SCOPES)
    return build("drive", "v3", credentials=creds)