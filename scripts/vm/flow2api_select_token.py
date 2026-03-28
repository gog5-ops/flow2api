import json
import sys
import urllib.request


BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:38000"
USERNAME = sys.argv[2] if len(sys.argv) > 2 else "admin"
PASSWORD = sys.argv[3] if len(sys.argv) > 3 else "admin"
TARGET_EMAIL = sys.argv[4] if len(sys.argv) > 4 else ""
DISABLE_OTHERS = (sys.argv[5] if len(sys.argv) > 5 else "true").lower() in {"1", "true", "yes", "y"}


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

result = {
    "target_email": TARGET_EMAIL,
    "target_id": None,
    "enabled_target": False,
    "disabled_ids": [],
    "tokens_before": [],
    "tokens_after": [],
}

target = None
for item in (tokens if isinstance(tokens, list) else []):
    result["tokens_before"].append(
        {
            "id": item.get("id"),
            "email": item.get("email"),
            "is_active": item.get("is_active"),
            "current_project_id": item.get("current_project_id"),
        }
    )
    if (item.get("email") or "").strip().lower() == TARGET_EMAIL.strip().lower():
        target = item

if not target:
    raise SystemExit(json.dumps(result | {"error": f"target email not found: {TARGET_EMAIL}"}, ensure_ascii=False))

result["target_id"] = target.get("id")

if target.get("id") and not target.get("is_active"):
    request_json("POST", f"/api/tokens/{target['id']}/enable", token=admin_token)
    result["enabled_target"] = True

if DISABLE_OTHERS:
    for item in (tokens if isinstance(tokens, list) else []):
        token_id = item.get("id")
        email = (item.get("email") or "").strip().lower()
        if token_id and email != TARGET_EMAIL.strip().lower() and item.get("is_active"):
            request_json("POST", f"/api/tokens/{token_id}/disable", token=admin_token)
            result["disabled_ids"].append(token_id)

tokens_after = request_json("GET", "/api/tokens", token=admin_token)
for item in (tokens_after if isinstance(tokens_after, list) else []):
    result["tokens_after"].append(
        {
            "id": item.get("id"),
            "email": item.get("email"),
            "is_active": item.get("is_active"),
            "current_project_id": item.get("current_project_id"),
        }
    )

print(json.dumps(result, ensure_ascii=False))
