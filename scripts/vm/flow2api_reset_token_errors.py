import json
import sqlite3
import sys
import urllib.request


BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:38000"
USERNAME = sys.argv[2] if len(sys.argv) > 2 else "admin"
PASSWORD = sys.argv[3] if len(sys.argv) > 3 else "admin"
DB_PATH = sys.argv[4] if len(sys.argv) > 4 else "/opt/flow2api/data/flow.db"
TARGET_EMAIL = sys.argv[5] if len(sys.argv) > 5 else ""


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

target_ids: list[int] = []
for token in tokens if isinstance(tokens, list) else []:
    if TARGET_EMAIL and token.get("email") != TARGET_EMAIL:
        continue
    token_id = token.get("id")
    if isinstance(token_id, int):
        target_ids.append(token_id)

if not target_ids:
    raise SystemExit(json.dumps({"error": "TARGET_TOKEN_NOT_FOUND", "target_email": TARGET_EMAIL}, ensure_ascii=False))

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
for token_id in target_ids:
    cur.execute(
        """
        UPDATE token_stats
        SET consecutive_error_count = 0,
            error_count = 0
        WHERE token_id = ?
        """,
        (token_id,),
    )
    cur.execute(
        """
        UPDATE tokens
        SET is_active = 1,
            ban_reason = NULL,
            banned_at = NULL
        WHERE id = ?
        """,
        (token_id,),
    )
conn.commit()

summary = {"target_email": TARGET_EMAIL, "token_ids": target_ids, "tokens_after": []}
cur.execute(
    """
    SELECT t.id, t.email, t.is_active, ts.error_count, ts.today_error_count, ts.consecutive_error_count
    FROM tokens t
    LEFT JOIN token_stats ts ON ts.token_id = t.id
    WHERE t.id IN ({})
    ORDER BY t.id
    """.format(",".join("?" for _ in target_ids)),
    target_ids,
)
for row in cur.fetchall():
    summary["tokens_after"].append(
        {
            "id": row[0],
            "email": row[1],
            "is_active": bool(row[2]),
            "error_count": row[3],
            "today_error_count": row[4],
            "consecutive_error_count": row[5],
        }
    )
conn.close()

print(json.dumps(summary, ensure_ascii=False))
