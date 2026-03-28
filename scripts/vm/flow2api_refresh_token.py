import json
import sys
import urllib.request


BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:38000"
USERNAME = sys.argv[2] if len(sys.argv) > 2 else "admin"
PASSWORD = sys.argv[3] if len(sys.argv) > 3 else "admin"
TARGET_EMAIL = sys.argv[4] if len(sys.argv) > 4 else ""


def request_json(method: str, path: str, data=None, token: str | None = None):
    url = BASE_URL.rstrip("/") + path
    body = None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


if not TARGET_EMAIL:
    raise SystemExit(json.dumps({"error": "target email required"}, ensure_ascii=False))

login_res = request_json(
    "POST",
    "/api/admin/login",
    {"username": USERNAME, "password": PASSWORD},
)
admin_token = login_res["token"]
tokens = request_json("GET", "/api/tokens", token=admin_token)

target = None
for item in (tokens if isinstance(tokens, list) else []):
    if (item.get("email") or "").strip().lower() == TARGET_EMAIL.strip().lower():
        target = item
        break

if not target:
    raise SystemExit(json.dumps({"error": f"target email not found: {TARGET_EMAIL}"}, ensure_ascii=False))

payload = {
    "st": target.get("st"),
    "project_id": target.get("current_project_id"),
    "project_name": target.get("current_project_name"),
    "remark": target.get("remark"),
    "captcha_proxy_url": target.get("captcha_proxy_url"),
    "image_enabled": bool(target.get("image_enabled", True)),
    "video_enabled": bool(target.get("video_enabled", True)),
    "image_concurrency": target.get("image_concurrency", -1),
    "video_concurrency": target.get("video_concurrency", -1),
}

update_res = request_json("PUT", f"/api/tokens/{target['id']}", data=payload, token=admin_token)
enable_res = None
if not target.get("is_active"):
    enable_res = request_json("POST", f"/api/tokens/{target['id']}/enable", token=admin_token)

tokens_after = request_json("GET", "/api/tokens", token=admin_token)

print(
    json.dumps(
        {
            "target_email": TARGET_EMAIL,
            "target_id": target.get("id"),
            "update": update_res,
            "enable": enable_res,
            "tokens_after": tokens_after,
        },
        ensure_ascii=False,
    )
)
