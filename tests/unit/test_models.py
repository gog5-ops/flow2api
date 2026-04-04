import pytest
from pydantic import ValidationError

from bridge_models import (
    CustomScoreRequest,
    LocalBootRequest,
    LocalFlowRequest,
    SessionEventRequest,
    SolveRequest,
    TokenPushRequest,
)


def test_solve_request_requires_project_id():
    with pytest.raises(ValidationError) as exc_info:
        SolveRequest()

    assert "project_id" in str(exc_info.value)


def test_solve_request_uses_default_action():
    request = SolveRequest(project_id="project-123")

    assert request.project_id == "project-123"
    assert request.action == "IMAGE_GENERATION"
    assert request.token_id is None


def test_custom_score_request_rejects_missing_required_fields():
    with pytest.raises(ValidationError) as exc_info:
        CustomScoreRequest(website_url="https://example.com")

    assert "website_key" in str(exc_info.value)
    assert "verify_url" in str(exc_info.value)


def test_token_push_request_accepts_valid_payload_and_defaults():
    request = TokenPushRequest(
        token="token-value",
        request_id="req-1",
        project_id="project-123",
        fingerprint={"browser": "chrome"},
        verify_result={"ok": True},
        verify_http_status=200,
        verify_mode="image",
        token_elapsed_ms=321,
    )

    assert request.source == "extension_debugger"
    assert request.action == "IMAGE_GENERATION"
    assert request.token == "token-value"
    assert request.fingerprint == {"browser": "chrome"}
    assert request.verify_result == {"ok": True}
    assert request.verify_http_status == 200
    assert request.verify_mode == "image"
    assert request.token_elapsed_ms == 321


@pytest.mark.parametrize(
    ("payload", "field_name"),
    [
        ({"token": ["bad"]}, "token"),
        ({"token": "ok", "fingerprint": "bad"}, "fingerprint"),
        ({"token": "ok", "verify_result": "bad"}, "verify_result"),
        ({"token": "ok", "verify_http_status": "bad"}, "verify_http_status"),
        ({"token": "ok", "token_elapsed_ms": "bad"}, "token_elapsed_ms"),
    ],
)
def test_token_push_request_rejects_invalid_field_types(payload, field_name):
    with pytest.raises(ValidationError) as exc_info:
        TokenPushRequest(**payload)

    assert field_name in str(exc_info.value)


def test_local_boot_request_exposes_expected_defaults():
    request = LocalBootRequest()

    assert request.target_email == "kpveoiref@libertystreeteriepa.asia"
    assert request.project_id == "c6d7cff5-2977-4825-acbe-e978e4addc65"
    assert request.disable_other_tokens is True
    assert request.force_bridge_restart is False
    assert request.skip_plugin_sync is False
    assert request.skip_project_context_page is False
    assert request.skip_target_token is False
    assert request.skip_remote_browser_mode is False
    assert request.timeout_seconds == 300


def test_local_boot_request_rejects_invalid_timeout():
    with pytest.raises(ValidationError) as exc_info:
        LocalBootRequest(timeout_seconds="slow")

    assert "timeout_seconds" in str(exc_info.value)


def test_local_flow_request_defaults_to_image_mode():
    request = LocalFlowRequest()

    assert request.mode == "image"
    assert request.disable_other_tokens is True
    assert request.timeout_seconds == 600


def test_session_event_request_accepts_optional_fields():
    request = SessionEventRequest(error_reason="captcha failed", status="failed")

    assert request.error_reason == "captcha failed"
    assert request.status == "failed"
