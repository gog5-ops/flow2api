import base64
import concurrent.futures
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path


BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:38000"
USERNAME = sys.argv[2] if len(sys.argv) > 2 else "admin"
PASSWORD = sys.argv[3] if len(sys.argv) > 3 else "admin"
PROJECT_ID = sys.argv[4] if len(sys.argv) > 4 else ""
REFERENCE_IMAGE_PATH = Path(sys.argv[5]) if len(sys.argv) > 5 else Path("/tmp/flow2api_matrix_ref.png")


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


def build_data_url(image_path: Path) -> str:
    image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")
    suffix = image_path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    return f"data:{mime};base64,{image_b64}"


def multimodal_content(text: str, image_urls: list[str]) -> list[dict]:
    content = [{"type": "text", "text": text}]
    for image_url in image_urls:
        content.append({"type": "image_url", "image_url": {"url": image_url}})
    return content


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

reference_data_url = build_data_url(REFERENCE_IMAGE_PATH)

cases = [
    {
        "name": "text_to_image",
        "payload": {
            "model": "gemini-3.1-flash-image-square",
            "project_id": PROJECT_ID or None,
            "messages": [{"role": "user", "content": "生成一张极简风格的蓝色圆形图标，白色背景。"}],
            "stream": False,
        },
        "timeout": 240,
    },
    {
        "name": "image_to_image",
        "payload": {
            "model": "gemini-3.1-flash-image-square",
            "project_id": PROJECT_ID or None,
            "messages": [
                {
                    "role": "user",
                    "content": multimodal_content(
                        "基于这张参考图，保留大树主体和整体构图，加入一只猫。",
                        [reference_data_url],
                    ),
                }
            ],
            "stream": False,
        },
        "timeout": 360,
    },
    {
        "name": "text_to_video",
        "payload": {
            "model": "veo_3_1_t2v_fast_landscape",
            "project_id": PROJECT_ID or None,
            "messages": [{"role": "user", "content": "一棵巨大的大树在风中轻轻摇曳，电影感镜头，日光穿过树叶，真实摄影风格。"}],
            "stream": False,
        },
        "timeout": 1800,
    },
    {
        "name": "image_to_video_single_frame",
        "payload": {
            "model": "veo_3_1_i2v_s_fast_fl",
            "project_id": PROJECT_ID or None,
            "messages": [
                {
                    "role": "user",
                    "content": multimodal_content(
                        "基于这张大树参考图生成一段短视频，镜头轻微推进，树叶和光影自然变化。",
                        [reference_data_url],
                    ),
                }
            ],
            "stream": False,
        },
        "timeout": 1800,
    },
    {
        "name": "image_to_video_start_end_frames",
        "payload": {
            "model": "veo_3_1_i2v_s_fast_fl",
            "project_id": PROJECT_ID or None,
            "messages": [
                {
                    "role": "user",
                    "content": multimodal_content(
                        "使用两张参考图作为首尾帧，生成一段树景过渡视频，运动自然平滑。",
                        [reference_data_url, reference_data_url],
                    ),
                }
            ],
            "stream": False,
        },
        "timeout": 1800,
    },
    {
        "name": "reference_to_video",
        "payload": {
            "model": "veo_3_1_r2v_fast",
            "project_id": PROJECT_ID or None,
            "messages": [
                {
                    "role": "user",
                    "content": multimodal_content(
                        "基于参考图生成一段电影感树景视频，镜头有轻微运动，氛围自然。",
                        [reference_data_url],
                    ),
                }
            ],
            "stream": False,
        },
        "timeout": 1800,
    },
]

def run_case(case: dict) -> dict:
    status, response = request_json(
        "POST",
        "/v1/chat/completions",
        data=case["payload"],
        token=api_key,
        timeout=case["timeout"],
    )
    return {
        "name": case["name"],
        "model": case["payload"]["model"],
        "status": status,
        "ok": status < 400,
        "response": response,
    }


results_by_name: dict[str, dict] = {}
with concurrent.futures.ThreadPoolExecutor(max_workers=len(cases)) as executor:
    future_map = {executor.submit(run_case, case): case["name"] for case in cases}
    for future in concurrent.futures.as_completed(future_map):
        name = future_map[future]
        try:
            results_by_name[name] = future.result()
        except Exception as exc:
            results_by_name[name] = {
                "name": name,
                "model": next((case["payload"]["model"] for case in cases if case["name"] == name), ""),
                "status": 500,
                "ok": False,
                "response": {"error": str(exc)},
            }

results = [results_by_name[case["name"]] for case in cases]

summary = {
    "project_id": PROJECT_ID or None,
    "reference_image_path": str(REFERENCE_IMAGE_PATH),
    "results": results,
}

print(json.dumps(summary, ensure_ascii=False))
