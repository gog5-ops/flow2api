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
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


login_res = request_json(
    "POST",
    "/api/admin/login",
    {"username": USERNAME, "password": PASSWORD},
)
admin_token = login_res["token"]
tokens = request_json("GET", "/api/tokens", token=admin_token)

result = {"enabled_ids": [], "tokens_before": [], "tokens_after": []}

if isinstance(tokens, list):
    for item in tokens:
        result["tokens_before"].append(
            {"id": item.get("id"), "email": item.get("email"), "is_active": item.get("is_active")}
        )
        if item.get("id") and not item.get("is_active"):
            request_json("POST", f"/api/tokens/{item['id']}/enable", token=admin_token)
            result["enabled_ids"].append(item["id"])

tokens_after = request_json("GET", "/api/tokens", token=admin_token)
if isinstance(tokens_after, list):
    for item in tokens_after:
        result["tokens_after"].append(
            {"id": item.get("id"), "email": item.get("email"), "is_active": item.get("is_active")}
        )

print(json.dumps(result, ensure_ascii=False))
