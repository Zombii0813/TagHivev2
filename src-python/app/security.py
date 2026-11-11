"""本机实例凭据及可信来源策略。"""

import os
import secrets
from fastapi import Request
from starlette.responses import JSONResponse

SESSION_TOKEN = os.environ.get("TAGHIVE_SESSION_TOKEN") or secrets.token_urlsafe(32)
INSTANCE_ID = os.environ.get("TAGHIVE_INSTANCE_ID") or secrets.token_hex(16)
DEV_MODE = os.environ.get("TAGHIVE_DEBUG") == "1" or not os.environ.get("TAGHIVE_SESSION_TOKEN")
ALLOWED_ORIGINS = ["tauri://localhost", "http://tauri.localhost", "https://tauri.localhost"]
if DEV_MODE:
    ALLOWED_ORIGINS += ["http://localhost:5173", "http://127.0.0.1:5173"]
    port = int(os.environ.get("TAGHIVE_PORT", "8721"))
    ALLOWED_ORIGINS += [f"http://127.0.0.1:{port}", f"http://localhost:{port}"]


def valid_token(value: str | None) -> bool:
    """恒定时间比较会话凭据。"""
    return isinstance(value, str) and value.isascii() and bool(value) and secrets.compare_digest(value, SESSION_TOKEN)


async def authorize_request(request: Request, call_next):
    """校验来源与凭据；媒体 GET 可携带查询凭据以支持 img/video。"""
    origin = request.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        return JSONResponse({"detail": "Untrusted origin"}, status_code=403)
    if request.method == "OPTIONS":
        return await call_next(request)
    if request.url.path == "/api/session" and DEV_MODE and (origin is None or origin in ALLOWED_ORIGINS):
        return JSONResponse({"token": SESSION_TOKEN, "instance_id": INSTANCE_ID}, headers={"Cache-Control": "no-store"})
    if request.url.path == "/" or request.url.path.startswith("/assets/"):
        return await call_next(request)
    authorization = request.headers.get("authorization", "")
    token = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else None
    path = request.url.path
    media = path.startswith("/api/thumbnails/") or (path.startswith("/api/files/") and path.endswith(("/preview", "/transcode")))
    if request.method == "GET" and media:
        token = token or request.query_params.get("session")
    if not valid_token(token):
        return JSONResponse({"detail": "Instance session required"}, status_code=401)
    return await call_next(request)
