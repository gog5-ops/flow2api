import base64
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:38000"
USERNAME = sys.argv[2] if len(sys.argv) > 2 else "admin"
PASSWORD = sys.argv[3] if len(sys.argv) > 3 else "admin"
PROJECT_ID = sys.argv[4] if len(sys.argv) > 4 else ""
IMAGE_PATH = Path(sys.argv[5]) if len(sys.argv) > 5 else Path("/tmp/flow2api_img2img_ref.png")


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
        with urllib.request.urlopen(req, timeout=240) as resp:
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
cfg_status, cfg_res = request_json("GET", "/api/admin/config", token=admin_token)
if cfg_status >= 400 or not cfg_res.get("api_key"):
    raise SystemExit(json.dumps({"step": "get_api_key", "status": cfg_status, "response": cfg_res}, ensure_ascii=False))

api_key = cfg_res["api_key"]
image_b64 = base64.b64encode(IMAGE_PATH.read_bytes()).decode("ascii")
image_data_url = f"data:image/png;base64,{image_b64}"

payload = {
    "model": "gemini-3.1-flash-image-square",
    "project_id": PROJECT_ID or None,
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "基于这张参考图，保留大树主体和整体构图，加入一只自然融入画面的猫，整体更精致、光影更强、细节更丰富。"},
                {"type": "image_url", "image_url": {"url": image_data_url}},
            ],
        }
    ],
    "stream": False,
}

generate_status, generate_res = request_json("POST", "/v1/chat/completions", data=payload, token=api_key)
print(
    json.dumps(
        {
            "requested_project_id": PROJECT_ID or None,
            "image_path": str(IMAGE_PATH),
            "generate_status": generate_status,
            "generate_response": generate_res,
        },
        ensure_ascii=False,
    )
)
