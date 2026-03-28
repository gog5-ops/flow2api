import json
import sys
import urllib.request
import urllib.error


BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:38000"
USERNAME = sys.argv[2] if len(sys.argv) > 2 else "admin"
PASSWORD = sys.argv[3] if len(sys.argv) > 3 else "admin"
PROJECT_ID = sys.argv[4] if len(sys.argv) > 4 else ""


def request_json(method: str, path: str, data=None, token: str | None = None):
    url = BASE_URL.rstrip("/") + path
    body = None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {"raw": raw}
        return exc.code, payload


login_status, login_res = request_json(
    "POST",
    "/api/admin/login",
    {"username": USERNAME, "password": PASSWORD},
)
if login_status >= 400:
    raise SystemExit(json.dumps({"step": "admin_login", "status": login_status, "response": login_res}, ensure_ascii=False))

admin_token = login_res["token"]
admin_cfg_status, admin_cfg = request_json("GET", "/api/admin/config", token=admin_token)
tokens_status, tokens_res = request_json("GET", "/api/tokens", token=admin_token)

api_key = admin_cfg.get("api_key")
if not api_key:
    raise SystemExit(json.dumps({"step": "get_api_key", "status": admin_cfg_status, "response": admin_cfg}, ensure_ascii=False))

models_status, models_res = request_json("GET", "/v1/models", token=api_key)

test_payload = {
    "model": "gemini-3.1-flash-image-square",
    "project_id": PROJECT_ID or None,
    "messages": [
        {
            "role": "user",
            "content": "生成一张极简风格的蓝色圆形图标，白色背景。"
        }
    ],
    "stream": False
}
generate_status, generate_res = request_json("POST", "/v1/chat/completions", data=test_payload, token=api_key)
tokens_after_status, tokens_after_res = request_json("GET", "/api/tokens", token=admin_token)

summary = {
    "api_key_preview": api_key[:6] + "..." if api_key else "",
    "token_count": len(tokens_res) if isinstance(tokens_res, list) else None,
    "tokens": [
        {
            "id": item.get("id"),
            "email": item.get("email"),
            "is_active": item.get("is_active"),
            "current_project_id": item.get("current_project_id"),
        }
        for item in (tokens_res[:5] if isinstance(tokens_res, list) else [])
    ],
    "models_status": models_status,
    "models_count": len(models_res.get("data", [])) if isinstance(models_res, dict) else None,
    "generate_status": generate_status,
    "generate_response": generate_res,
    "requested_project_id": PROJECT_ID or None,
    "tokens_after_generate": [
        {
            "id": item.get("id"),
            "email": item.get("email"),
            "is_active": item.get("is_active"),
            "current_project_id": item.get("current_project_id"),
        }
        for item in (tokens_after_res[:5] if isinstance(tokens_after_res, list) else [])
    ],
}

print(json.dumps(summary, ensure_ascii=False))
