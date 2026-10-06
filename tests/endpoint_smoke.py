"""Verify that each configured service reaches the CLI without leaking other credentials."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import time

from qgis.PyQt.QtCore import QCoreApplication

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("geotaro_endpoint_test", root / "__init__.py",
                                              submodule_search_locations=[str(root)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
from geotaro_endpoint_test.core.agent import AgentProcess, valid_endpoint

assert valid_endpoint("https://example.test/openai/v1")
assert not valid_endpoint("http://localhost:8080/v1")
assert valid_endpoint("http://127.0.0.1:8080/v1")
assert valid_endpoint("http://[::1]:8080/v1")
assert not valid_endpoint("http://example.test/openai/v1")
assert not valid_endpoint("http://localhost.example.test/v1")
assert not valid_endpoint("file:///tmp/token")
assert not valid_endpoint("https://user:password@example.test/v1")

app = QCoreApplication([])
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    cli = path / "fake-cli"
    cli.write_text("#!/usr/bin/env python3\n" + r"""
import json, os, sys
sys.stdin.read()
with open(os.environ['GEOTARO_ENDPOINT_TEST_LOG'], 'w') as log:
    json.dump({'args': sys.argv[1:], 'env': {key: os.environ.get(key) for key in (
        'ANTHROPIC_BASE_URL', 'ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN',
        'CLAUDE_CODE_USE_BEDROCK', 'CODEX_API_KEY', 'OPENAI_API_KEY',
        'AWS_REGION', 'AWS_PROFILE', 'AWS_BEARER_TOKEN_BEDROCK')}}, log)
sys.exit(1)
""")
    cli.chmod(0o755)
    os.environ["GEOTARO_ENDPOINT_TEST_LOG"] = str(path / "call.json")
    os.environ["ANTHROPIC_AUTH_TOKEN"] = "must-not-leak"
    os.environ["OPENAI_API_KEY"] = "must-not-leak"
    os.environ["AWS_REGION"] = "us-east-1"
    os.environ["AWS_PROFILE"] = "example"
    os.environ["AWS_BEARER_TOKEN_BEDROCK"] = "bedrock-key"
    agent = AgentProcess(app, path)

    def run(provider, endpoint, base_url="", api_key=""):
        log = path / "call.json"
        log.unlink(missing_ok=True)
        agent.request(str(cli), "hello", provider=provider, endpoint=endpoint,
                      base_url=base_url, api_key=api_key)
        deadline = time.monotonic() + 5
        while agent.process is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)
        assert agent.process is None and log.exists()
        return json.loads(log.read_text())

    claude = run("claude", "custom", "https://claude.example.test", "gateway-key")
    assert claude["env"]["ANTHROPIC_BASE_URL"] == "https://claude.example.test"
    assert claude["env"]["ANTHROPIC_API_KEY"] == "gateway-key"
    assert claude["env"]["ANTHROPIC_AUTH_TOKEN"] is None
    assert claude["env"]["OPENAI_API_KEY"] is None
    assert claude["env"]["AWS_BEARER_TOKEN_BEDROCK"] is None

    claude_aws = run("claude", "bedrock")
    assert claude_aws["env"]["CLAUDE_CODE_USE_BEDROCK"] == "1"
    assert claude_aws["env"]["ANTHROPIC_API_KEY"] is None
    assert claude_aws["env"]["AWS_REGION"] == "us-east-1"
    assert claude_aws["env"]["AWS_BEARER_TOKEN_BEDROCK"] == "bedrock-key"

    codex = run("codex", "custom", "https://codex.example.test/openai/v1", "gateway-key")
    assert 'model_provider="geotaro-endpoint"' in codex["args"]
    assert 'model_providers.geotaro-endpoint.base_url="https://codex.example.test/openai/v1"' in codex["args"]
    assert codex["env"]["CODEX_API_KEY"] == "gateway-key"
    assert codex["env"]["OPENAI_API_KEY"] is None
    assert codex["env"]["AWS_BEARER_TOKEN_BEDROCK"] is None
    assert not any(arg.startswith("forced_login_method=") for arg in codex["args"])

    codex_aws = run("codex", "amazon-bedrock-runtime")
    assert 'model_provider="amazon-bedrock-runtime"' in codex_aws["args"]
    assert codex_aws["env"]["AWS_PROFILE"] == "example"
    assert codex_aws["env"]["AWS_BEARER_TOKEN_BEDROCK"] == "bedrock-key"
    assert codex_aws["env"]["CODEX_API_KEY"] is None
    assert not any(arg.startswith("forced_login_method=") for arg in codex_aws["args"])

    agent.close()
print("PASS: endpoint routing and credential isolation")
