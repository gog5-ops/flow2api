import json
import sys
import urllib.error
import urllib.request


BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:38000"
USERNAME = sys.argv[2] if len(sys.argv) > 2 else "admin"
PASSWORD = sys.argv[3] if len(sys.argv) > 3 else "admin"


def request_json(method: str, path: str, data=None, token: str | None = None, timeout: int = 1800):
    url = BASE_URL.rstrip("/") + path
    body = None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
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
    timeout=30,
)
if login_status >= 400:
    raise SystemExit(json.dumps({"step": "admin_login", "status": login_status, "response": login_res}, ensure_ascii=False))

admin_token = login_res["token"]
cfg_status, cfg_res = request_json("GET", "/api/admin/config", token=admin_token, timeout=30)
tokens_status, tokens_res = request_json("GET", "/api/tokens", token=admin_token, timeout=30)

api_key = cfg_res.get("api_key")
if not api_key:
    raise SystemExit(json.dumps({"step": "get_api_key", "status": cfg_status, "response": cfg_res}, ensure_ascii=False))

payload = {
    "model": "veo_3_1_t2v_fast_landscape",
    "messages": [
        {
            "role": "user",
            "content": "一棵巨大的大树在风中轻轻摇曳，电影感镜头，日光穿过树叶，真实摄影风格。"
        }
    ],
    "stream": False,
}

generate_status, generate_res = request_json(
    "POST",
    "/v1/chat/completions",
    data=payload,
    token=api_key,
    timeout=1800,
)

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
    "generate_status": generate_status,
    "generate_response": generate_res,
}

print(json.dumps(summary, ensure_ascii=False))
