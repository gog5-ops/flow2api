def test_bridge_health_endpoint_is_public(bridge_client):
    response = bridge_client.get("/health")

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_bridge_config_requires_authorization(bridge_client):
    response = bridge_client.get("/api/v1/config")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing authorization"


def test_bridge_config_accepts_valid_bearer_token(bridge_client, bridge_auth_headers):
    response = bridge_client.get("/api/v1/config", headers=bridge_auth_headers)

    assert response.status_code == 200
    assert response.json()["api_key_preview"] == "test-api..."


def test_local_request_rejects_invalid_mode(bridge_client, bridge_auth_headers):
    response = bridge_client.post(
        "/api/v1/local/request",
        headers=bridge_auth_headers,
        json={
            "mode": "audio",
            "target_email": "user@example.com",
            "project_id": "project-123",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "mode must be image or video"


def test_local_request_normalizes_mode_and_dispatches_runner(
    bridge_client,
    bridge_app_module,
    bridge_auth_headers,
    monkeypatch,
):
    calls = {}

    async def fake_run_remote_browser_script(action, payload, timeout_seconds):
        calls["action"] = action
        calls["payload"] = payload
        calls["timeout_seconds"] = timeout_seconds
        return {
            "success": True,
            "action": action,
            "mode": payload["mode"],
        }

    monkeypatch.setattr(
        bridge_app_module,
        "run_remote_browser_script",
        fake_run_remote_browser_script,
    )

    response = bridge_client.post(
        "/api/v1/local/request",
        headers=bridge_auth_headers,
        json={
            "mode": " VIDEO ",
            "target_email": "user@example.com",
            "project_id": "project-123",
            "disable_other_tokens": False,
            "timeout_seconds": 123,
        },
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert calls == {
        "action": "Request",
        "payload": {
            "mode": "video",
            "target_email": "user@example.com",
            "project_id": "project-123",
            "disable_other_tokens": False,
        },
        "timeout_seconds": 123,
    }


def test_token_cache_endpoint_accepts_valid_payload(
    bridge_client,
    bridge_app_module,
    bridge_auth_headers,
    monkeypatch,
):
    captured = {}

    def fake_cache_token(**kwargs):
        captured.update(kwargs)
        return {"created_at": 1712217600.0}

    monkeypatch.setattr(bridge_app_module.session_manager, "cache_token", fake_cache_token)

    response = bridge_client.post(
        "/api/v1/token-cache",
        headers=bridge_auth_headers,
        json={
            "request_id": "req-1",
            "project_id": "project-123",
            "token": "bridge-token",
            "verify_http_status": 200,
            "verify_mode": "image",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "request_id": "req-1",
        "project_id": "project-123",
        "action": "IMAGE_GENERATION",
        "token_length": 12,
        "source": "extension_debugger",
        "created_at": 1712217600.0,
    }
    assert captured["token"] == "bridge-token"
    assert captured["verify_http_status"] == 200
    assert captured["verify_mode"] == "image"


def test_token_cache_endpoint_rejects_missing_required_token(bridge_client, bridge_auth_headers):
    response = bridge_client.post(
        "/api/v1/token-cache",
        headers=bridge_auth_headers,
        json={"project_id": "project-123"},
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "token"
