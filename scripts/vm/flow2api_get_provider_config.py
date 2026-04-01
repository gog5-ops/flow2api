import json
import hashlib
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path.cwd()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:38000"
USERNAME = sys.argv[2] if len(sys.argv) > 2 else "admin"
PASSWORD = sys.argv[3] if len(sys.argv) > 3 else "admin"
PUBLIC_BASE_URL = sys.argv[4] if len(sys.argv) > 4 else BASE_URL


def get_provider_api_key_alias(api_key: str) -> str:
    normalized = (api_key or "").strip()
    if not normalized:
        return ""
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]
    return f"sk-flow2api-{digest}"


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
        with urllib.request.urlopen(req, timeout=60) as resp:
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
config_status, config_res = request_json("GET", "/api/admin/config", token=admin_token)
if config_status >= 400 or not config_res.get("api_key"):
    raise SystemExit(json.dumps({"step": "get_admin_config", "status": config_status, "response": config_res}, ensure_ascii=False))

api_key = config_res["api_key"]
provider_key = get_provider_api_key_alias(api_key)

summary = {
    "base_url": PUBLIC_BASE_URL.rstrip("/"),
    "api_key": api_key,
    "provider_api_key": provider_key,
    "models_url": PUBLIC_BASE_URL.rstrip("/") + "/v1/models",
    "credits_url": PUBLIC_BASE_URL.rstrip("/") + "/v1/credits",
    "user_info_url": PUBLIC_BASE_URL.rstrip("/") + "/v1/user/info",
}

print(json.dumps(summary, ensure_ascii=False))
