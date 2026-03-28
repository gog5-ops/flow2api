import json
import sqlite3
import sys
import urllib.request


BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:38000"
USERNAME = sys.argv[2] if len(sys.argv) > 2 else "admin"
PASSWORD = sys.argv[3] if len(sys.argv) > 3 else "admin"
DB_PATH = sys.argv[4] if len(sys.argv) > 4 else "/opt/flow2api/data/flow.db"


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

summary = {
    "db_path": DB_PATH,
    "tokens_api": tokens if isinstance(tokens, list) else [],
    "tokens_db": [],
    "admin_config": {},
    "recent_request_logs": [],
}

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute(
    """
    SELECT
        t.id,
        t.email,
        t.is_active,
        t.current_project_id,
        t.current_project_name,
        t.image_enabled,
        t.video_enabled,
        t.image_concurrency,
        t.video_concurrency,
        t.ban_reason,
        t.banned_at,
        ts.error_count,
        ts.today_error_count,
        ts.consecutive_error_count,
        ts.last_error_at,
        ts.last_success_at
    FROM tokens t
    LEFT JOIN token_stats ts ON ts.token_id = t.id
    ORDER BY t.id
    """
)
for row in cur.fetchall():
    summary["tokens_db"].append({k: row[k] for k in row.keys()})

cur.execute(
    """
    SELECT id, username, api_key, error_ban_threshold, updated_at
    FROM admin_config
    WHERE id = 1
    """
)
row = cur.fetchone()
if row:
    summary["admin_config"] = {k: row[k] for k in row.keys()}

cur.execute(
    """
    SELECT
        id,
        token_id,
        operation,
        status_code,
        status_text,
        progress,
        created_at,
        updated_at,
        substr(response_body, 1, 500) AS response_body_preview
    FROM request_logs
    ORDER BY id DESC
    LIMIT 10
    """
)
for row in cur.fetchall():
    summary["recent_request_logs"].append({k: row[k] for k in row.keys()})
conn.close()

print(json.dumps(summary, ensure_ascii=False))
