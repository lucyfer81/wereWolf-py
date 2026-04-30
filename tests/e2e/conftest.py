from __future__ import annotations

import os
import subprocess
import sys
import time

import pytest
import requests

# Save proxy vars before clearing them for Playwright/Chromium
_PROXY_VARS = ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY")
_saved_proxy = {k: os.environ[k] for k in _PROXY_VARS if k in os.environ}
for _var in _PROXY_VARS:
    os.environ.pop(_var, None)


def _wait_for_server(url: str, timeout: int = 30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = requests.get(url, timeout=2, proxies={"http": None, "https": None})
            if resp.status_code == 200:
                return True
        except requests.ConnectionError:
            pass
        time.sleep(0.5)
    raise RuntimeError(f"Server at {url} did not start within {timeout}s")


@pytest.fixture(scope="session")
def server_url():
    port = 5174
    url = f"http://127.0.0.1:{port}"
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    # Restore proxy for server subprocess so it can reach external LLM APIs
    server_env = {
        **os.environ,
        **_saved_proxy,
        "PYTHONPATH": project_root,
        "NO_PROXY": "127.0.0.1,localhost",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=project_root,
        env=server_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        _wait_for_server(f"{url}/api/health")
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
