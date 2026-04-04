import asyncio
import subprocess
from typing import Optional
import traceback

from fastapi import FastAPI, Header, HTTPException

from bridge_config import API_KEY, FLOW2API_ROOT, POWERSHELL_EXECUTABLE, REMOTE_BROWSER_SCRIPTS_ROOT
from bridge_manager import RemoteBrowserSessionManager
from bridge_models import (
    CustomScoreRequest,
    LocalBootRequest,
    LocalFlowRequest,
    SessionEventRequest,
    SolveRequest,
    TokenPushRequest,
)
from bridge_runner import RemoteBrowserRunner


app = FastAPI(title="Flow2API Remote Browser Bridge", version="0.1.0")
session_manager = RemoteBrowserSessionManager()
runner = RemoteBrowserRunner(session_manager)
RUN_REQUEST_SCRIPT = REMOTE_BROWSER_SCRIPTS_ROOT / "run_request.ps1"


def require_auth(authorization: Optional[str]):
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing authorization")
    token = authorization[7:] if authorization.startswith("Bearer ") else authorization
    if token != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


async def run_remote_browser_script(action: str, payload: dict, timeout_seconds: int):
    if not POWERSHELL_EXECUTABLE.exists():
        raise HTTPException(status_code=500, detail=f"PowerShell not found: {POWERSHELL_EXECUTABLE}")
    if not RUN_REQUEST_SCRIPT.exists():
        raise HTTPException(status_code=500, detail=f"Remote browser script not found: {RUN_REQUEST_SCRIPT}")

    command = [
        str(POWERSHELL_EXECUTABLE),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(RUN_REQUEST_SCRIPT),
        "-Action",
        action,
        "-TargetEmail",
        payload["target_email"],
        "-ProjectId",
        payload["project_id"],
        "-DisableOtherTokens:$" + ("true" if payload.get("disable_other_tokens", True) else "false"),
    ]
    if action in {"Request", "Full"}:
        command.extend(["-Mode", payload.get("mode", "image")])

    def _run():
        return subprocess.run(
            command,
            cwd=str(FLOW2API_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )

    try:
        completed = await asyncio.to_thread(_run)
    except subprocess.TimeoutExpired as exc:
        session_manager.record_event("local_api_timeout", action=action, timeout_seconds=timeout_seconds)
        raise HTTPException(status_code=504, detail=f"Local {action.lower()} timed out after {timeout_seconds}s") from exc

    session_manager.record_event(
        "local_api_completed",
        action=action,
        exit_code=completed.returncode,
        target_email=payload["target_email"],
        project_id=payload["project_id"],
        mode=payload.get("mode"),
    )
    return {
        "success": completed.returncode == 0,
        "action": action,
        "command": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


@app.get("/health")
async def health():
    return {
        "ok": True,
        "flow2api_root": str(FLOW2API_ROOT),
        "session_count": session_manager.count(),
        "pending_request_count": len(session_manager.get_pending_requests()),
    }


@app.get("/api/v1/config")
async def config_info(authorization: Optional[str] = Header(None)):
    require_auth(authorization)
    return {"api_key_preview": API_KEY[:8] + "...", "flow2api_root": str(FLOW2API_ROOT)}


@app.get("/api/v1/debug/profile")
async def debug_profile(authorization: Optional[str] = Header(None)):
    require_auth(authorization)
    runtime = runner.describe_runtime()
    runtime["token_cache_file"] = str(session_manager._cache_file)
    runtime["pending_requests"] = session_manager.get_pending_requests()
    runtime["pending_plugin_sync"] = session_manager.get_pending_plugin_sync()
    runtime["recent_events"] = session_manager.get_events()
    for action_name, label in (("IMAGE_GENERATION", "image"), ("VIDEO_GENERATION", "video")):
        cached = session_manager.get_cached_token(action_name, 3600)
        runtime[f"cached_{label}_token"] = bool(cached)
        runtime[f"cached_{label}_token_meta"] = {
            "project_id": cached.get("project_id") if cached else None,
            "source": cached.get("source") if cached else None,
            "verify_mode": cached.get("verify_mode") if cached else None,
            "verify_http_status": cached.get("verify_http_status") if cached else None,
            "token_elapsed_ms": cached.get("token_elapsed_ms") if cached else None,
            "created_at": cached.get("created_at") if cached else None,
            "fingerprint": cached.get("fingerprint") if cached else None,
    }
    return runtime


@app.get("/api/v1/local/status")
async def local_status(authorization: Optional[str] = Header(None)):
    require_auth(authorization)
    runtime = runner.describe_runtime()
    runtime["flow2api_root"] = str(FLOW2API_ROOT)
    runtime["scripts_root"] = str(REMOTE_BROWSER_SCRIPTS_ROOT)
    runtime["run_request_script"] = str(RUN_REQUEST_SCRIPT)
    runtime["powershell_executable"] = str(POWERSHELL_EXECUTABLE)
    runtime["bridge_api_ready"] = True
    runtime["pending_requests"] = session_manager.get_pending_requests()
    runtime["pending_plugin_sync"] = session_manager.get_pending_plugin_sync()
    runtime["recent_events"] = session_manager.get_events()
    return runtime


@app.post("/api/v1/local/boot")
async def local_boot(request: LocalBootRequest, authorization: Optional[str] = Header(None)):
    require_auth(authorization)
    session_manager.record_event("local_api_boot_called", target_email=request.target_email, project_id=request.project_id)
    return await run_remote_browser_script(
        "Boot",
        {
            "target_email": request.target_email,
            "project_id": request.project_id,
            "disable_other_tokens": request.disable_other_tokens,
            "force_bridge_restart": request.force_bridge_restart,
            "skip_plugin_sync": request.skip_plugin_sync,
            "skip_project_context_page": request.skip_project_context_page,
            "skip_target_token": request.skip_target_token,
            "skip_remote_browser_mode": request.skip_remote_browser_mode,
        },
        request.timeout_seconds,
    )


@app.post("/api/v1/local/request")
async def local_request(request: LocalFlowRequest, authorization: Optional[str] = Header(None)):
    require_auth(authorization)
    mode = (request.mode or "image").strip().lower()
    if mode not in {"image", "video"}:
        raise HTTPException(status_code=400, detail="mode must be image or video")
    session_manager.record_event(
        "local_api_request_called",
        target_email=request.target_email,
        project_id=request.project_id,
        mode=mode,
    )
    return await run_remote_browser_script(
        "Request",
        {
            "mode": mode,
            "target_email": request.target_email,
            "project_id": request.project_id,
            "disable_other_tokens": request.disable_other_tokens,
        },
        request.timeout_seconds,
    )


@app.get("/api/v1/token-request")
async def get_token_request(authorization: Optional[str] = Header(None)):
    require_auth(authorization)
    session_manager.record_event("token_request_polled")
    pending = session_manager.get_pending_requests()
    pending_plugin_sync = session_manager.get_pending_plugin_sync()
    return {
        "success": True,
        "pending_actions": list(pending.keys()),
        "pending_requests": pending,
        "pending_plugin_sync": pending_plugin_sync,
    }


@app.post("/api/v1/plugin-sync-request")
async def request_plugin_sync(authorization: Optional[str] = Header(None)):
    require_auth(authorization)
    payload = session_manager.request_plugin_sync(source="flow2api_preflight", request_timeout_seconds=45)
    return {"success": True, "pending_plugin_sync": payload}


@app.post("/api/v1/plugin-sync-finish")
async def finish_plugin_sync(authorization: Optional[str] = Header(None)):
    require_auth(authorization)
    session_manager.record_event("plugin_sync_finished")
    session_manager.clear_pending_plugin_sync()
    return {"success": True}


@app.post("/api/v1/open-login")
async def open_login(authorization: Optional[str] = Header(None)):
    require_auth(authorization)
    try:
        return await runner.open_login_window()
    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/v1/solve")
async def solve(request: SolveRequest, authorization: Optional[str] = Header(None)):
    require_auth(authorization)
    session_manager.record_event("solve_called", project_id=request.project_id, action=request.action)
    try:
        return await runner.solve(request.project_id, request.action)
    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/v1/custom-score")
async def custom_score(request: CustomScoreRequest, authorization: Optional[str] = Header(None)):
    require_auth(authorization)
    session_manager.record_event("custom_score_called", action=request.action, website_url=request.website_url)
    try:
        return await runner.custom_score(
            website_url=request.website_url,
            website_key=request.website_key,
            verify_url=request.verify_url,
            action=request.action,
            enterprise=request.enterprise,
        )
    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/v1/token-cache")
async def push_token_cache(request: TokenPushRequest, authorization: Optional[str] = Header(None)):
    require_auth(authorization)
    session_manager.record_event("token_cache_push_called", action=request.action, source=request.source)
    cached = session_manager.cache_token(
        source=request.source,
        request_id=request.request_id,
        project_id=request.project_id,
        action=request.action,
        token=request.token,
        fingerprint=request.fingerprint,
        verify_result=request.verify_result,
        verify_http_status=request.verify_http_status,
        verify_mode=request.verify_mode,
        token_elapsed_ms=request.token_elapsed_ms,
    )
    return {
        "success": True,
        "request_id": request.request_id,
        "project_id": request.project_id,
        "action": request.action,
        "token_length": len(request.token or ""),
        "source": request.source,
        "created_at": cached.get("created_at"),
    }


@app.post("/api/v1/sessions/{session_id}/error")
async def mark_error(session_id: str, request: SessionEventRequest, authorization: Optional[str] = Header(None)):
    require_auth(authorization)
    session_manager.mark_error(session_id, request.error_reason or "")
    return {"success": True}


@app.post("/api/v1/sessions/{session_id}/finish")
async def finish(session_id: str, request: SessionEventRequest, authorization: Optional[str] = Header(None)):
    require_auth(authorization)
    session_manager.finish(session_id, request.status or "success")
    return {"success": True}
