import os
import secrets
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FLOW2API_ROOT = Path(os.environ.get("FLOW2API_ROOT", ROOT.parent.parent)).resolve()
if str(FLOW2API_ROOT) not in sys.path:
    sys.path.insert(0, str(FLOW2API_ROOT))

REMOTE_BROWSER_SCRIPTS_ROOT = Path(
    os.environ.get("REMOTE_BROWSER_SCRIPTS_ROOT", FLOW2API_ROOT / "scripts" / "remote_browser")
).resolve()
POWERSHELL_EXECUTABLE = Path(
    os.environ.get(
        "REMOTE_BROWSER_POWERSHELL_EXE",
        r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
    )
).resolve()

API_KEY = os.environ.get("REMOTE_BROWSER_API_KEY", "").strip() or secrets.token_urlsafe(24)
AUTOMATION_PROFILE_DIR = Path(
    os.environ.get("REMOTE_BROWSER_PROFILE_DIR", ROOT / "browser_data" / "automation_profile")
).resolve()
DIRECT_CHROME_USER_DATA_DIR = Path(
    os.environ.get(
        "REMOTE_BROWSER_CHROME_USER_DATA_DIR",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data",
    )
).resolve()
DIRECT_CHROME_PROFILE_NAME = os.environ.get("REMOTE_BROWSER_CHROME_PROFILE_NAME", "Default").strip() or "Default"
CHROME_EXECUTABLE = Path(
    os.environ.get(
        "REMOTE_BROWSER_CHROME_EXE",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    )
).resolve()
CHROME_DEBUG_PORT = int(os.environ.get("REMOTE_BROWSER_CHROME_DEBUG_PORT", "9224"))
FLOW_WEBSITE_KEY = os.environ.get("REMOTE_BROWSER_FLOW_WEBSITE_KEY", "6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV").strip()
BACKEND = os.environ.get("REMOTE_BROWSER_BACKEND", "chrome_direct").strip().lower() or "chrome_direct"
CHROME_ATTACH_MODE = os.environ.get("REMOTE_BROWSER_CHROME_ATTACH_MODE", "launch").strip().lower() or "launch"
TOKEN_CACHE_TTL_SECONDS = int(os.environ.get("REMOTE_BROWSER_TOKEN_CACHE_TTL_SECONDS", "180"))

