from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import os
import sys
import types
import uuid

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
BRIDGE_DIR = ROOT / "tools" / "remote_browser_bridge"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if str(BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(BRIDGE_DIR))


@pytest.fixture
def bridge_app_module(monkeypatch, tmp_path):
    monkeypatch.setenv("REMOTE_BROWSER_API_KEY", "test-api-key")
    monkeypatch.chdir(BRIDGE_DIR)

    for module_name in ("bridge_config", "bridge_manager", "bridge_models", "bridge_runner"):
        sys.modules.pop(module_name, None)

    fake_bridge_runner = types.ModuleType("bridge_runner")

    class FakeRemoteBrowserRunner:
        def __init__(self, session_manager):
            self.session_manager = session_manager

        def describe_runtime(self):
            return {
                "backend": "stub",
                "attach_mode": "launch",
            }

        async def open_login_window(self):
            return {"success": True, "message": "stubbed"}

        async def solve(self, project_id, action):
            return {
                "success": True,
                "project_id": project_id,
                "action": action,
            }

        async def custom_score(self, **kwargs):
            return {
                "success": True,
                **kwargs,
            }

    fake_bridge_runner.RemoteBrowserRunner = FakeRemoteBrowserRunner
    monkeypatch.setitem(sys.modules, "bridge_runner", fake_bridge_runner)

    module_name = f"bridge_app_test_{uuid.uuid4().hex}"
    spec = spec_from_file_location(module_name, BRIDGE_DIR / "app.py")
    module = module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)

    module.session_manager._cache_file = tmp_path / "token_cache.json"
    yield module

    sys.modules.pop(module_name, None)


@pytest.fixture
def bridge_client(bridge_app_module):
    with TestClient(bridge_app_module.app) as test_client:
        yield test_client


@pytest.fixture
def bridge_auth_headers():
    return {"Authorization": "Bearer test-api-key"}
