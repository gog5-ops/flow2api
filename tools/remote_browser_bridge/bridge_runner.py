import asyncio
import json
import os
import secrets
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import HTTPException
import websockets

from bridge_config import (
    AUTOMATION_PROFILE_DIR,
    BACKEND,
    CHROME_ATTACH_MODE,
    CHROME_DEBUG_PORT,
    CHROME_EXECUTABLE,
    DIRECT_CHROME_PROFILE_NAME,
    DIRECT_CHROME_USER_DATA_DIR,
    FLOW_WEBSITE_KEY,
    FLOW2API_ROOT,
    TOKEN_CACHE_TTL_SECONDS,
)  # noqa: F401
from bridge_manager import RemoteBrowserSessionManager

# Reuse flow2api's existing browser-captcha implementation locally for the nodriver path.
from src.services.browser_captcha_personal import BrowserCaptchaService  # type: ignore  # noqa: E402


class CdpPageSession:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.ws = None
        self._message_id = 0

    async def __aenter__(self):
        self.ws = await websockets.connect(self.ws_url, max_size=8 * 1024 * 1024)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self.ws is not None:
            await self.ws.close()

    async def send(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self.ws is None:
            raise RuntimeError("CDP websocket is not connected")

        self._message_id += 1
        message_id = self._message_id
        await self.ws.send(
            json.dumps(
                {
                    "id": message_id,
                    "method": method,
                    "params": params or {},
                }
            )
        )

        while True:
            raw = await self.ws.recv()
            payload = json.loads(raw)
            if payload.get("id") != message_id:
                continue
            if "error" in payload:
                raise HTTPException(status_code=500, detail=f"CDP {method} failed: {payload['error']}")
            return payload.get("result", {})

    async def evaluate(self, expression: str) -> Any:
        result = await self.send(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True,
            },
        )
        return ((result.get("result") or {}).get("value"))


class RemoteBrowserRunner:
    """Runner that adapts local browser capability to flow2api remote_browser protocol."""

    def __init__(self, session_manager: RemoteBrowserSessionManager) -> None:
        self.session_manager = session_manager

    def describe_runtime(self) -> Dict[str, Any]:
        direct_exists = DIRECT_CHROME_USER_DATA_DIR.exists()
        return {
            "backend": BACKEND,
            "attach_mode": CHROME_ATTACH_MODE,
            "chrome_executable": str(CHROME_EXECUTABLE),
            "mode": "system_default_profile" if direct_exists else "cloned_profile",
            "user_data_dir": str(DIRECT_CHROME_USER_DATA_DIR if direct_exists else AUTOMATION_PROFILE_DIR),
            "profile_directory": DIRECT_CHROME_PROFILE_NAME if direct_exists else "",
            "automation_profile_dir": str(AUTOMATION_PROFILE_DIR),
            "debug_port": CHROME_DEBUG_PORT,
            "cdp_http_url": f"http://127.0.0.1:{CHROME_DEBUG_PORT}",
            "cdp_url": f"http://127.0.0.1:{CHROME_DEBUG_PORT}",
        }

    async def _get_service(self) -> BrowserCaptchaService:
        service = await BrowserCaptchaService.get_instance(None)
        direct_dir = DIRECT_CHROME_USER_DATA_DIR
        if direct_dir.exists():
            service.user_data_dir = str(direct_dir)
            os.environ["BROWSER_PROFILE_DIRECTORY"] = DIRECT_CHROME_PROFILE_NAME
            return service

        if AUTOMATION_PROFILE_DIR.exists():
            target_dir = Path(service.user_data_dir)
            default_profile_dir = target_dir / "Default"
            target_dir.mkdir(parents=True, exist_ok=True)
            if default_profile_dir.exists():
                shutil.rmtree(default_profile_dir, ignore_errors=True)
            shutil.copytree(AUTOMATION_PROFILE_DIR, default_profile_dir)
        return service

    def _launch_system_chrome(self, runtime: Dict[str, Any]) -> Dict[str, Any]:
        if not CHROME_EXECUTABLE.exists():
            raise HTTPException(status_code=500, detail=f"Chrome executable not found: {CHROME_EXECUTABLE}")

        profile_name = str(runtime["profile_directory"])
        args = [str(CHROME_EXECUTABLE)]

        if runtime["mode"] == "system_default_profile":
            args.extend(
                [
                    f"--profile-directory={profile_name}",
                    f"--remote-debugging-port={CHROME_DEBUG_PORT}",
                    "--remote-allow-origins=*",
                    "--new-window",
                    "https://labs.google/fx/tools/flow",
                ]
            )
        else:
            user_data_dir = Path(runtime["user_data_dir"])
            args.extend(
                [
                    f"--user-data-dir={user_data_dir}",
                    f"--remote-debugging-port={CHROME_DEBUG_PORT}",
                    "--remote-allow-origins=*",
                    "--new-window",
                    "https://labs.google/fx/tools/flow",
                ]
            )

        try:
            subprocess.Popen(args)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to launch Chrome: {exc}") from exc

        return {
            "success": True,
            "message": "Login window opened",
            **runtime,
        }

    def _kill_all_chrome(self) -> None:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/IM", "chrome.exe", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:
                subprocess.run(
                    ["pkill", "-f", "chrome"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
        except Exception:
            pass

    def _fetch_json(self, url: str, *, timeout: int = 5) -> Dict[str, Any]:
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except urllib.error.URLError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to connect to Chrome CDP: {exc}") from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to query Chrome CDP: {exc}") from exc

    def _wait_for_cdp(self, *, timeout: float = 15.0) -> Dict[str, Any]:
        deadline = time.time() + timeout
        last_error: Optional[str] = None
        while time.time() < deadline:
            try:
                return self._fetch_json(f"http://127.0.0.1:{CHROME_DEBUG_PORT}/json/version", timeout=3)
            except HTTPException as exc:
                last_error = str(exc.detail)
                time.sleep(0.5)
        raise HTTPException(status_code=500, detail=last_error or "Chrome CDP did not become ready in time")

    def _ensure_debuggable_chrome(self, runtime: Dict[str, Any], *, target_url: str) -> Dict[str, Any]:
        if CHROME_ATTACH_MODE == "attach":
            version = self._wait_for_cdp(timeout=3.0)
            return {
                "success": True,
                "message": "Attach-mode Chrome detected",
                "cdp_ready": True,
                "cdp_version": version,
                **runtime,
            }

        # launch / ensure-debuggable: if CDP is already up, reuse it; otherwise restart Chrome cleanly.
        try:
            version = self._wait_for_cdp(timeout=3.0)
            return {
                "success": True,
                "message": "Debuggable Chrome already available",
                "cdp_ready": True,
                "cdp_version": version,
                **runtime,
            }
        except HTTPException:
            pass

        self._kill_all_chrome()
        time.sleep(2)
        launch_info = self._launch_system_chrome(runtime)
        version = self._wait_for_cdp(timeout=20.0)
        return {
            **launch_info,
            "cdp_ready": True,
            "cdp_version": version,
            "target_url": target_url,
        }

    def _list_targets(self) -> list[dict]:
        payload = self._fetch_json(f"http://127.0.0.1:{CHROME_DEBUG_PORT}/json/list", timeout=5)
        return payload if isinstance(payload, list) else []

    def _new_target(self, url: str) -> Dict[str, Any]:
        encoded = urllib.parse.quote(url, safe=":/?&=%")
        return self._fetch_json(f"http://127.0.0.1:{CHROME_DEBUG_PORT}/json/new?{encoded}", timeout=10)

    def _close_target(self, target_id: str) -> None:
        try:
            self._fetch_json(f"http://127.0.0.1:{CHROME_DEBUG_PORT}/json/close/{target_id}", timeout=5)
        except Exception:
            pass

    async def _open_target_session(self, target_url: str) -> tuple[CdpPageSession, str]:
        target = None
        for existing in self._list_targets():
            if isinstance(existing, dict) and existing.get("type") == "page" and str(existing.get("url", "")).startswith(target_url):
                target = existing
                break
        if target is None:
            target = self._new_target(target_url)

        ws_url = target.get("webSocketDebuggerUrl")
        target_id = target.get("id")
        if not ws_url or not target_id:
            raise HTTPException(status_code=500, detail=f"Failed to obtain page websocket for {target_url}")

        session = CdpPageSession(ws_url)
        await session.__aenter__()
        await session.send("Page.enable")
        await session.send("Runtime.enable")
        return session, str(target_id)

    async def _navigate_and_wait(self, session: CdpPageSession, url: str) -> None:
        await session.send("Page.navigate", {"url": url})
        for _ in range(60):
            await asyncio.sleep(0.5)
            ready_state = await session.evaluate("document.readyState")
            if ready_state == "complete":
                return
        raise HTTPException(status_code=500, detail=f"Page did not become ready: {url}")

    async def _wait_for_custom_recaptcha_on_page(self, session: CdpPageSession, website_key: str, enterprise: bool = False) -> bool:
        ready_check = (
            "typeof grecaptcha !== 'undefined' && typeof grecaptcha.enterprise !== 'undefined' && typeof grecaptcha.enterprise.execute === 'function'"
            if enterprise
            else "typeof grecaptcha !== 'undefined' && typeof grecaptcha.execute === 'function'"
        )
        script_path = "recaptcha/enterprise.js" if enterprise else "recaptcha/api.js"

        is_ready = await session.evaluate(ready_check)
        if is_ready:
            return True

        await session.evaluate(
            f"""
            (() => {{
                if (document.querySelector('script[src*="recaptcha"]')) return true;
                const script = document.createElement('script');
                script.src = 'https://www.google.com/{script_path}?render={website_key}';
                script.async = true;
                document.head.appendChild(script);
                return true;
            }})()
            """
        )

        for _ in range(40):
            await asyncio.sleep(0.5)
            is_ready = await session.evaluate(ready_check)
            if is_ready:
                return True
        return False

    async def _execute_custom_recaptcha_on_page(
        self,
        session: CdpPageSession,
        website_key: str,
        action: str = "homepage",
        enterprise: bool = False,
    ) -> Optional[str]:
        ts = int(time.time() * 1000)
        token_var = f"_custom_recaptcha_token_{ts}"
        error_var = f"_custom_recaptcha_error_{ts}"
        execute_target = "grecaptcha.enterprise.execute" if enterprise else "grecaptcha.execute"

        await session.evaluate(
            f"""
            (() => {{
                window.{token_var} = null;
                window.{error_var} = null;
                try {{
                    grecaptcha.ready(function() {{
                        {execute_target}('{website_key}', {{action: '{action}'}})
                            .then(function(token) {{ window.{token_var} = token; }})
                            .catch(function(err) {{ window.{error_var} = err.message || 'execute failed'; }});
                    }});
                }} catch (e) {{
                    window.{error_var} = e.message || 'exception';
                }}
                return true;
            }})()
            """
        )

        for _ in range(30):
            await asyncio.sleep(0.5)
            token = await session.evaluate(f"window.{token_var}")
            if token:
                return token
            error = await session.evaluate(f"window.{error_var}")
            if error:
                raise HTTPException(status_code=500, detail=f"reCAPTCHA execution failed: {error}")
        return None

    async def _extract_page_fingerprint(self, session: CdpPageSession) -> Optional[Dict[str, Any]]:
        fingerprint = await session.evaluate(
            """
            (() => {
                const ua = navigator.userAgent || "";
                const lang = navigator.language || "";
                const uaData = navigator.userAgentData || null;
                let secChUa = "";
                let secChUaMobile = "";
                let secChUaPlatform = "";

                if (uaData) {
                    if (Array.isArray(uaData.brands) && uaData.brands.length > 0) {
                        secChUa = uaData.brands.map((item) => `"${item.brand}";v="${item.version}"`).join(", ");
                    }
                    secChUaMobile = uaData.mobile ? "?1" : "?0";
                    if (uaData.platform) {
                        secChUaPlatform = `"${uaData.platform}"`;
                    }
                }

                return {
                    user_agent: ua,
                    accept_language: lang,
                    sec_ch_ua: secChUa,
                    sec_ch_ua_mobile: secChUaMobile,
                    sec_ch_ua_platform: secChUaPlatform,
                    proxy_url: null,
                };
            })()
            """
        )
        return fingerprint if isinstance(fingerprint, dict) else None

    def _verify_score(self, verify_url: str, token: str) -> Dict[str, Any]:
        data = json.dumps({"g-recaptcha-response": token}).encode("utf-8")
        req = urllib.request.Request(
            verify_url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Origin": "https://antcpt.com",
                "Referer": "https://antcpt.com/score_detector/",
                "X-Requested-With": "XMLHttpRequest",
            },
            method="POST",
        )
        started = time.time()
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                body = json.loads(raw) if raw else {}
                return {
                    "verify_mode": "server_post",
                    "verify_elapsed_ms": int((time.time() - started) * 1000),
                    "verify_http_status": resp.status,
                    "verify_result": body if isinstance(body, dict) else {"raw": raw},
                }
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                body = json.loads(raw) if raw else {}
            except Exception:
                body = {"raw": raw}
            return {
                "verify_mode": "server_post",
                "verify_elapsed_ms": int((time.time() - started) * 1000),
                "verify_http_status": exc.code,
                "verify_result": body,
            }

    async def _wait_for_cached_token(
        self,
        action: str,
        project_id: str,
        request_id: str | None = None,
        timeout_seconds: int = 120
    ) -> Dict[str, Any] | None:
        deadline = time.time() + timeout_seconds
        self.session_manager.record_event(
            "wait_for_cached_token_started",
            request_id=request_id,
            project_id=project_id,
            action=action,
            timeout_seconds=timeout_seconds,
        )
        while time.time() < deadline:
            cached = self.session_manager.get_cached_token(
                action,
                TOKEN_CACHE_TTL_SECONDS,
                project_id=project_id,
                request_id=request_id,
            )
            if cached:
                self.session_manager.record_event(
                    "wait_for_cached_token_satisfied",
                    request_id=request_id,
                    project_id=project_id,
                    action=action,
                )
                return cached
            await asyncio.sleep(0.5)
        self.session_manager.record_event(
            "wait_for_cached_token_timeout",
            request_id=request_id,
            project_id=project_id,
            action=action,
            timeout_seconds=timeout_seconds,
        )
        return None

    async def open_login_window(self) -> Dict[str, Any]:
        runtime = self.describe_runtime()
        if BACKEND == "chrome_direct":
            try:
                return self._ensure_debuggable_chrome(runtime, target_url="https://labs.google/fx/tools/flow")
            except HTTPException as exc:
                return {
                    "success": False,
                    "cdp_ready": False,
                    "cdp_error": str(exc.detail),
                    "message": "Chrome is not exposing a usable CDP endpoint.",
                    **runtime,
                }
        return self._launch_system_chrome(runtime)

    async def solve(self, project_id: str, action: str) -> Dict[str, Any]:
        self.session_manager.record_event("runner_solve_entered", project_id=project_id, action=action, backend=BACKEND)
        if BACKEND == "chrome_direct":
            request_id = secrets.token_urlsafe(12)
            cached = self.session_manager.pop_cached_token(
                action,
                TOKEN_CACHE_TTL_SECONDS,
                project_id=project_id,
                request_id=request_id,
            )
            if cached:
                session_id = secrets.token_urlsafe(16)
                self.session_manager.create_session(
                    session_id,
                    project_id=project_id,
                    action=action,
                    fingerprint=cached.get("fingerprint") if isinstance(cached.get("fingerprint"), dict) else None,
                )
                return {
                    "token": cached["token"],
                    "token_elapsed_ms": cached.get("token_elapsed_ms"),
                    "session_id": session_id,
                    "fingerprint": cached.get("fingerprint") or {},
                    "verify_mode": cached.get("verify_mode") or "extension_debugger_cache",
                    "verify_http_status": cached.get("verify_http_status"),
                    "verify_result": cached.get("verify_result") or {},
                    "source": cached.get("source") or "extension_debugger",
                    "request_id": request_id,
                }

            self.session_manager.request_token(
                action,
                request_id=request_id,
                project_id=project_id,
                source="flow2api_solve",
                request_timeout_seconds=120,
            )
            cached = await self._wait_for_cached_token(action, project_id=project_id, request_id=request_id, timeout_seconds=120)
            if cached:
                cached = self.session_manager.pop_cached_token(
                    action,
                    TOKEN_CACHE_TTL_SECONDS,
                    project_id=project_id,
                    request_id=request_id,
                ) or cached
                session_id = secrets.token_urlsafe(16)
                self.session_manager.create_session(
                    session_id,
                    project_id=project_id,
                    action=action,
                    fingerprint=cached.get("fingerprint") if isinstance(cached.get("fingerprint"), dict) else None,
                )
                return {
                    "token": cached["token"],
                    "token_elapsed_ms": cached.get("token_elapsed_ms"),
                    "session_id": session_id,
                    "fingerprint": cached.get("fingerprint") or {},
                    "verify_mode": cached.get("verify_mode") or "extension_debugger_cache",
                    "verify_http_status": cached.get("verify_http_status"),
                    "verify_result": cached.get("verify_result") or {},
                    "source": cached.get("source") or "extension_debugger",
                    "request_id": request_id,
                }

            runtime = self.describe_runtime()
            self.session_manager.record_event("runner_solve_fallback_direct", project_id=project_id, action=action)
            self._ensure_debuggable_chrome(runtime, target_url=f"https://labs.google/fx/tools/flow/project/{project_id}")
            target_url = f"https://labs.google/fx/tools/flow/project/{project_id}"
            session, target_id = await self._open_target_session(target_url)
            try:
                await self._navigate_and_wait(session, target_url)
                ready = await self._wait_for_custom_recaptcha_on_page(session, FLOW_WEBSITE_KEY, enterprise=True)
                if not ready:
                    raise HTTPException(status_code=500, detail="Flow reCAPTCHA did not become ready")
                token_started_at = time.time()
                token = await self._execute_custom_recaptcha_on_page(session, FLOW_WEBSITE_KEY, action=action, enterprise=True)
                token_elapsed_ms = int((time.time() - token_started_at) * 1000)
                if not token:
                    raise HTTPException(status_code=500, detail="Failed to obtain reCAPTCHA token")
                fingerprint = await self._extract_page_fingerprint(session)
                session_id = secrets.token_urlsafe(16)
                self.session_manager.create_session(
                    session_id,
                    project_id=project_id,
                    action=action,
                    fingerprint=fingerprint,
                )
                return {
                    "token": token,
                    "token_elapsed_ms": token_elapsed_ms,
                    "session_id": session_id,
                    "fingerprint": fingerprint,
                }
            finally:
                await session.__aexit__(None, None, None)
                self._close_target(target_id)

        service = await self._get_service()
        token = await service.get_token(project_id, action)
        fingerprint = service.get_last_fingerprint() if token else None
        if not token:
            raise HTTPException(status_code=500, detail="Failed to obtain reCAPTCHA token")

        session_id = secrets.token_urlsafe(16)
        self.session_manager.create_session(
            session_id,
            project_id=project_id,
            action=action,
            fingerprint=fingerprint,
        )
        return {
            "token": token,
            "session_id": session_id,
            "fingerprint": fingerprint,
        }

    async def custom_score(
        self,
        website_url: str,
        website_key: str,
        verify_url: str,
        action: str,
        enterprise: bool,
    ) -> Dict[str, Any]:
        if BACKEND == "chrome_direct":
            runtime = self.describe_runtime()
            self._ensure_debuggable_chrome(runtime, target_url=website_url)
            session, target_id = await self._open_target_session(website_url)
            try:
                await self._navigate_and_wait(session, website_url)
                ready = await self._wait_for_custom_recaptcha_on_page(session, website_key, enterprise=enterprise)
                if not ready:
                    raise HTTPException(status_code=500, detail="Custom reCAPTCHA did not become ready")
                token_started_at = time.time()
                token = await self._execute_custom_recaptcha_on_page(
                    session,
                    website_key=website_key,
                    action=action,
                    enterprise=enterprise,
                )
                token_elapsed_ms = int((time.time() - token_started_at) * 1000)
                fingerprint = await self._extract_page_fingerprint(session)
                if not token:
                    return {
                        "token": None,
                        "token_elapsed_ms": token_elapsed_ms,
                        "verify_mode": "browser_page",
                        "verify_elapsed_ms": 0,
                        "verify_http_status": None,
                        "verify_result": {},
                        "fingerprint": fingerprint,
                    }
                verify_payload = self._verify_score(verify_url, token)
                return {
                    "token": token,
                    "token_elapsed_ms": token_elapsed_ms,
                    "fingerprint": fingerprint,
                    **verify_payload,
                }
            finally:
                await session.__aexit__(None, None, None)
                self._close_target(target_id)

        service = await self._get_service()
        payload = await service.get_custom_score(
            website_url=website_url,
            website_key=website_key,
            verify_url=verify_url,
            action=action,
            enterprise=enterprise,
        )
        payload["fingerprint"] = service.get_last_fingerprint()
        return payload
