import json
import sys
import urllib.request


BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:38000"
USERNAME = sys.argv[2] if len(sys.argv) > 2 else "admin"
PASSWORD = sys.argv[3] if len(sys.argv) > 3 else "admin"


def request_json(method: str, path: str, data=None, token: str | None = None):
    url = BASE_URL.rstrip("/") + path
    body = None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


login_res = request_json(
    "POST",
    "/api/admin/login",
    {"username": USERNAME, "password": PASSWORD},
)
token = login_res["token"]

tokens = request_json("GET", "/api/tokens", token=token)
plugin_cfg = request_json("GET", "/api/plugin/config", token=token).get("config", {})
health = request_json("GET", "/health")

summary = {
    "health": health,
    "plugin": {
        "connection_url": plugin_cfg.get("connection_url"),
        "auto_enable_on_update": plugin_cfg.get("auto_enable_on_update"),
        "connection_token_preview": (
            (plugin_cfg.get("connection_token") or "")[:8] + "..."
            if plugin_cfg.get("connection_token")
            else ""
        ),
    },
    "token_count": len(tokens) if isinstance(tokens, list) else None,
    "tokens": [],
}

if isinstance(tokens, list):
    for item in tokens[:10]:
        summary["tokens"].append(
            {
                "id": item.get("id"),
                "email": item.get("email"),
                "is_active": item.get("is_active"),
                "current_project_id": item.get("current_project_id"),
                "at_expires": item.get("at_expires"),
                "remark": item.get("remark"),
            }
        )

print(json.dumps(summary, ensure_ascii=False))
