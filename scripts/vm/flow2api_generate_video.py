import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:38000"
USERNAME = sys.argv[2] if len(sys.argv) > 2 else "admin"
PASSWORD = sys.argv[3] if len(sys.argv) > 3 else "admin"
PROMPT = sys.argv[4] if len(sys.argv) > 4 else "一只猫遇到外星人，电影感，真实摄影风格。"
MODEL = sys.argv[5] if len(sys.argv) > 5 else "veo_3_1_t2v_fast_landscape"
OUTPUT_DIR = Path(sys.argv[6]) if len(sys.argv) > 6 else Path("output") / "flow2api"


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


def download_file(url: str, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=1800) as resp:
        out_path.write_bytes(resp.read())


def main():
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
    api_key = cfg_res.get("api_key")
    if cfg_status >= 400 or not api_key:
        raise SystemExit(json.dumps({"step": "get_api_key", "status": cfg_status, "response": cfg_res}, ensure_ascii=False))

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        "stream": False,
    }

    status, res = request_json(
        "POST",
        "/v1/chat/completions",
        data=payload,
        token=api_key,
        timeout=1800,
    )

    summary = {
        "prompt": PROMPT,
        "model": MODEL,
        "status": status,
        "response": res,
    }

    if status >= 400:
        print(json.dumps(summary, ensure_ascii=False))
        return

    content = ((((res.get("choices") or [{}])[0]).get("message") or {}).get("content") or "")
    match = re.search(r"<video[^>]+src='([^']+)'", content)
    if not match:
        summary["download"] = {"ok": False, "reason": "No video URL found"}
        print(json.dumps(summary, ensure_ascii=False))
        return

    video_url = match.group(1)
    out_path = OUTPUT_DIR / "cat-alien.mp4"
    download_file(video_url, out_path)
    summary["download"] = {
        "ok": True,
        "video_url": video_url,
        "output_path": str(out_path.resolve()),
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
