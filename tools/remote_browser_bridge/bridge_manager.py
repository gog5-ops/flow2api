import json
import time
from pathlib import Path
from typing import Any, Dict


class RemoteBrowserSessionManager:
    """In-memory session lifecycle manager for remote browser solve requests."""

    def __init__(self) -> None:
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._token_cache: Dict[str, Dict[str, Any]] = {}
        self._pending_requests: Dict[str, Dict[str, Any]] = {}
        self._pending_plugin_sync: Dict[str, Any] | None = None
        self._events: list[Dict[str, Any]] = []
        self._cache_file = Path("token_cache.json")
        self._load_cache()

    def _token_key(self, action: str, project_id: str | None = None, request_id: str | None = None) -> str:
        normalized_request = (request_id or "").strip()
        if normalized_request:
            return f"request::{normalized_request}"
        normalized_action = (action or "").strip().upper()
        normalized_project = (project_id or "").strip()
        return f"{normalized_project}::{normalized_action}"

    def record_event(self, event: str, **data: Any) -> Dict[str, Any]:
        payload = {
            "ts": time.time(),
            "event": event,
            **data,
        }
        self._events.append(payload)
        if len(self._events) > 100:
            self._events = self._events[-100:]
        return payload

    def get_events(self, limit: int = 30) -> list[Dict[str, Any]]:
        if limit <= 0:
            return []
        return self._events[-limit:]

    def request_plugin_sync(self, *, source: str = "flow2api", request_timeout_seconds: int = 45) -> Dict[str, Any]:
        payload = {
            "source": source,
            "created_at": time.time(),
            "request_timeout_seconds": request_timeout_seconds,
        }
        self._pending_plugin_sync = payload
        self.record_event("plugin_sync_requested", source=source, request_timeout_seconds=request_timeout_seconds)
        return payload

    def get_pending_plugin_sync(self, max_age_seconds: int = 120) -> Dict[str, Any] | None:
        if not self._pending_plugin_sync:
            return None
        age = time.time() - float(self._pending_plugin_sync.get("created_at") or 0)
        if age > max_age_seconds:
            self.record_event("plugin_sync_request_expired", max_age_seconds=max_age_seconds)
            self._pending_plugin_sync = None
            return None
        return self._pending_plugin_sync

    def clear_pending_plugin_sync(self) -> None:
        if self._pending_plugin_sync is not None:
            self.record_event("plugin_sync_request_cleared")
        self._pending_plugin_sync = None

    def _load_cache(self) -> None:
        if not self._cache_file.exists():
            return
        try:
            self._token_cache = json.loads(self._cache_file.read_text(encoding="utf-8"))
            if not isinstance(self._token_cache, dict):
                self._token_cache = {}
        except Exception:
            self._token_cache = {}

    def _save_cache(self) -> None:
        try:
            self._cache_file.write_text(json.dumps(self._token_cache, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def create_session(self, session_id: str, *, project_id: str, action: str, fingerprint: Dict[str, Any] | None) -> Dict[str, Any]:
        payload = {
            "project_id": project_id,
            "action": action,
            "created_at": time.time(),
            "fingerprint": fingerprint,
        }
        self._sessions[session_id] = payload
        self.record_event("session_created", session_id=session_id, project_id=project_id, action=action)
        return payload

    def mark_error(self, session_id: str, error_reason: str) -> None:
        session = self._sessions.get(session_id)
        if not session:
            return
        session["last_error_reason"] = error_reason or ""
        session["last_error_at"] = time.time()
        self.record_event("session_error", session_id=session_id, error_reason=error_reason or "")

    def finish(self, session_id: str, status: str) -> None:
        session = self._sessions.get(session_id)
        if not session:
            return
        session["finished_at"] = time.time()
        session["status"] = status or "success"
        self.record_event("session_finished", session_id=session_id, status=status or "success")

    def count(self) -> int:
        return len(self._sessions)

    def request_token(
        self,
        action: str,
        *,
        request_id: str | None = None,
        project_id: str | None = None,
        source: str = "flow2api",
        request_timeout_seconds: int = 45
    ) -> Dict[str, Any]:
        key = self._token_key(action, project_id, request_id=request_id)
        payload = {
            "request_id": request_id,
            "key": key,
            "project_id": project_id,
            "action": action,
            "source": source,
            "created_at": time.time(),
            "request_timeout_seconds": request_timeout_seconds,
        }
        self._pending_requests[key] = payload
        self.record_event(
            "token_requested",
            key=key,
            request_id=request_id,
            project_id=project_id,
            action=action,
            source=source,
            request_timeout_seconds=request_timeout_seconds,
        )
        return payload

    def get_pending_requests(self, max_age_seconds: int = 60) -> Dict[str, Dict[str, Any]]:
        now = time.time()
        result: Dict[str, Dict[str, Any]] = {}
        expired: list[str] = []
        for key, payload in self._pending_requests.items():
            age = now - float(payload.get("created_at") or 0)
            if age > max_age_seconds:
                expired.append(key)
                continue
            result[key] = payload
        for key in expired:
            payload = self._pending_requests.pop(key, None) or {}
            self.record_event(
                "pending_request_expired",
                key=key,
                project_id=payload.get("project_id"),
                action=payload.get("action"),
                max_age_seconds=max_age_seconds
            )
        return result

    def clear_pending_request(self, action: str, project_id: str | None = None, request_id: str | None = None) -> None:
        key = self._token_key(action, project_id, request_id=request_id)
        self._pending_requests.pop(key, None)
        self.record_event("pending_request_cleared", key=key, request_id=request_id, project_id=project_id, action=action)

    def cache_token(
        self,
        *,
        source: str,
        request_id: str | None = None,
        project_id: str | None = None,
        action: str,
        token: str,
        fingerprint: Dict[str, Any] | None = None,
        verify_result: Dict[str, Any] | None = None,
        verify_http_status: int | None = None,
        verify_mode: str | None = None,
        token_elapsed_ms: int | None = None,
    ) -> Dict[str, Any]:
        key = self._token_key(action, project_id, request_id=request_id)
        payload = {
            "request_id": request_id,
            "key": key,
            "project_id": project_id,
            "source": source,
            "action": action,
            "token": token,
            "fingerprint": fingerprint or {},
            "verify_result": verify_result or {},
            "verify_http_status": verify_http_status,
            "verify_mode": verify_mode or "unknown",
            "token_elapsed_ms": token_elapsed_ms,
            "created_at": time.time(),
        }
        self._token_cache[key] = payload
        self.clear_pending_request(action, project_id=project_id, request_id=request_id)
        self._save_cache()
        self.record_event(
            "token_cached",
            key=key,
            request_id=request_id,
            project_id=project_id,
            action=action,
            source=source,
            verify_mode=payload["verify_mode"],
            verify_http_status=verify_http_status,
            token_elapsed_ms=token_elapsed_ms,
        )
        return payload

    def get_cached_token(
        self,
        action: str,
        max_age_seconds: int,
        project_id: str | None = None,
        request_id: str | None = None
    ) -> Dict[str, Any] | None:
        key = self._token_key(action, project_id, request_id=request_id)
        payload = self._token_cache.get(key)
        fallback_key = None
        if not payload and request_id:
            fallback_key = self._token_key(action, project_id, request_id=None)
            payload = self._token_cache.get(fallback_key)
            if payload:
                self.record_event(
                    "token_cache_request_id_fallback_hit",
                    key=key,
                    fallback_key=fallback_key,
                    request_id=request_id,
                    project_id=project_id,
                    action=action,
                )
        if not payload:
            self.record_event(
                "token_cache_miss",
                key=key,
                request_id=request_id,
                project_id=project_id,
                action=action,
                max_age_seconds=max_age_seconds,
            )
            return None
        age = time.time() - float(payload.get("created_at") or 0)
        if age > max_age_seconds:
            self.record_event(
                "token_cache_expired",
                key=fallback_key or key,
                request_id=request_id,
                project_id=project_id,
                action=action,
                age_seconds=age,
                max_age_seconds=max_age_seconds,
            )
            return None
        self.record_event(
            "token_cache_hit",
            key=fallback_key or key,
            request_id=request_id,
            project_id=project_id,
            action=action,
            age_seconds=age,
            max_age_seconds=max_age_seconds,
        )
        return payload

    def pop_cached_token(
        self,
        action: str,
        max_age_seconds: int,
        project_id: str | None = None,
        request_id: str | None = None
    ) -> Dict[str, Any] | None:
        key = self._token_key(action, project_id, request_id=request_id)
        payload = self.get_cached_token(action, max_age_seconds, project_id=project_id, request_id=request_id)
        if not payload:
            return None
        pop_key = key
        if request_id and key not in self._token_cache:
            fallback_key = self._token_key(action, project_id, request_id=None)
            if fallback_key in self._token_cache:
                pop_key = fallback_key
        self._token_cache.pop(pop_key, None)
        self._save_cache()
        self.record_event("token_cache_consumed", key=pop_key, request_id=request_id, project_id=project_id, action=action)
        return payload
