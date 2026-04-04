from typing import Optional

from pydantic import BaseModel


class SolveRequest(BaseModel):
    project_id: str
    action: str = "IMAGE_GENERATION"
    token_id: Optional[int] = None


class CustomScoreRequest(BaseModel):
    website_url: str
    website_key: str
    verify_url: str
    action: str = "homepage"
    enterprise: bool = False


class SessionEventRequest(BaseModel):
    error_reason: Optional[str] = None
    status: Optional[str] = None


class TokenPushRequest(BaseModel):
    source: str = "extension_debugger"
    request_id: Optional[str] = None
    project_id: Optional[str] = None
    action: str = "IMAGE_GENERATION"
    token: str
    fingerprint: Optional[dict] = None
    verify_result: Optional[dict] = None
    verify_http_status: Optional[int] = None
    verify_mode: Optional[str] = None
    token_elapsed_ms: Optional[int] = None


class LocalBootRequest(BaseModel):
    target_email: str = "kpveoiref@libertystreeteriepa.asia"
    project_id: str = "c6d7cff5-2977-4825-acbe-e978e4addc65"
    disable_other_tokens: bool = True
    force_bridge_restart: bool = False
    skip_plugin_sync: bool = False
    skip_project_context_page: bool = False
    skip_target_token: bool = False
    skip_remote_browser_mode: bool = False
    timeout_seconds: int = 300


class LocalFlowRequest(BaseModel):
    mode: str = "image"
    target_email: str = "kpveoiref@libertystreeteriepa.asia"
    project_id: str = "c6d7cff5-2977-4825-acbe-e978e4addc65"
    disable_other_tokens: bool = True
    timeout_seconds: int = 600
