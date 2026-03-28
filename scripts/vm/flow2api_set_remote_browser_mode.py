import json
import sys
import urllib.request


BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:38000"
USERNAME = sys.argv[2] if len(sys.argv) > 2 else "admin"
PASSWORD = sys.argv[3] if len(sys.argv) > 3 else "admin"
REMOTE_BASE_URL = sys.argv[4] if len(sys.argv) > 4 else "http://172.21.0.1:8318"
REMOTE_API_KEY = sys.argv[5] if len(sys.argv) > 5 else ""
REMOTE_TIMEOUT = int(sys.argv[6] if len(sys.argv) > 6 else "120")


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
token = login_res["token"]

captcha_cfg = request_json("GET", "/api/captcha/config", token=token)
before_cfg = dict(captcha_cfg)

captcha_cfg["captcha_method"] = "remote_browser"
captcha_cfg["remote_browser_base_url"] = REMOTE_BASE_URL
captcha_cfg["remote_browser_api_key"] = REMOTE_API_KEY
captcha_cfg["remote_browser_timeout"] = REMOTE_TIMEOUT

update_res = request_json("POST", "/api/captcha/config", captcha_cfg, token=token)
after_cfg = request_json("GET", "/api/captcha/config", token=token)

print(
    json.dumps(
        {
            "before": before_cfg,
            "update": update_res,
            "after": after_cfg,
        },
        ensure_ascii=False,
    )
)
