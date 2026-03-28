import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


def request_json(method: str, url: str, data=None, token: str | None = None, timeout: int = 180):
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
    with urllib.request.urlopen(url, timeout=180) as resp:
        out_path.write_bytes(resp.read())


def main():
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:38000"
    username = sys.argv[2] if len(sys.argv) > 2 else "admin"
    password = sys.argv[3] if len(sys.argv) > 3 else "admin"
    count = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    prompt = sys.argv[5] if len(sys.argv) > 5 else "一棵巨大的大树，细节丰富，摄影感强，白天自然光。"
    model = sys.argv[6] if len(sys.argv) > 6 else "gemini-3.1-flash-image-square"
    output_dir = Path(sys.argv[7]) if len(sys.argv) > 7 else Path("output") / "flow2api"

    login_status, login_res = request_json(
        "POST",
        f"{base_url.rstrip('/')}/api/admin/login",
        {"username": username, "password": password},
        timeout=30,
    )
    if login_status >= 400:
        raise SystemExit(json.dumps({"step": "admin_login", "status": login_status, "response": login_res}, ensure_ascii=False))

    admin_token = login_res["token"]
    cfg_status, cfg_res = request_json("GET", f"{base_url.rstrip('/')}/api/admin/config", token=admin_token, timeout=30)
    if cfg_status >= 400 or not cfg_res.get("api_key"):
        raise SystemExit(json.dumps({"step": "get_api_key", "status": cfg_status, "response": cfg_res}, ensure_ascii=False))
    api_key = cfg_res["api_key"]

    image_re = re.compile(r"!\[.*?\]\((.*?)\)")
    results = []
    output_dir = Path(output_dir)

    for idx in range(1, count + 1):
        item_prompt = f"{prompt} 第{idx}张，构图和细节略有变化。"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": item_prompt}],
            "stream": False,
        }
        status, res = request_json(
            "POST",
            f"{base_url.rstrip('/')}/v1/chat/completions",
            payload,
            token=api_key,
            timeout=240,
        )
        if status >= 400:
            results.append({"index": idx, "status": status, "error": res})
            continue
        content = (
            (((res.get("choices") or [{}])[0]).get("message") or {}).get("content") or ""
        )
        match = image_re.search(content)
        image_url = match.group(1) if match else ""
        if not image_url:
            results.append({"index": idx, "status": status, "error": {"message": "No image URL found", "response": res}})
            continue
        filename = f"tree-{idx}.png"
        out_path = output_dir / filename
        download_file(image_url, out_path)
        results.append(
            {
                "index": idx,
                "status": status,
                "prompt": item_prompt,
                "image_url": image_url,
                "output_path": str(out_path.resolve()),
            }
        )

    print(json.dumps({"count": count, "results": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
