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
spec = importlib.util.spec_from_file_location("mapsuke_endpoint_test", root / "__init__.py",
                                              submodule_search_locations=[str(root)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
from mapsuke_endpoint_test.core.agent import AgentProcess

app = QCoreApplication([])
with tempfile.TemporaryDirectory() as directory:
    path = Path(directory)
    cli = path / "fake-cli"
    cli.write_text("#!/usr/bin/env python3\n" + r"""
import json, os, sys
sys.stdin.read()
with open(os.environ['MAPSUKE_ENDPOINT_TEST_LOG'], 'w') as log:
    json.dump({'args': sys.argv[1:], 'env': {key: os.environ.get(key) for key in (
        'ANTHROPIC_BASE_URL', 'ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN',
        'CLAUDE_CODE_USE_BEDROCK', 'CODEX_API_KEY', 'OPENAI_API_KEY',
        'AWS_REGION', 'AWS_PROFILE', 'AWS_BEARER_TOKEN_BEDROCK')}}, log)
sys.exit(1)
""")
    cli.chmod(0o755)
    os.environ["MAPSUKE_ENDPOINT_TEST_LOG"] = str(path / "call.json")
    os.environ["ANTHROPIC_AUTH_TOKEN"] = "must-not-leak"
    os.environ["ANTHROPIC_BASE_URL"] = "https://must-not-leak.example.test"
    os.environ["OPENAI_API_KEY"] = "must-not-leak"
    os.environ["AWS_REGION"] = "us-east-1"
    os.environ["AWS_PROFILE"] = "example"
    os.environ["AWS_BEARER_TOKEN_BEDROCK"] = "bedrock-key"
    agent = AgentProcess(app, path)

    def run(provider, endpoint, api_key="", web_search=False, resume=False):
        log = path / "call.json"
        log.unlink(missing_ok=True)
        agent.request(str(cli), "hello", provider=provider, endpoint=endpoint,
                      api_key=api_key, web_search=web_search,
                      resume=resume, session_id="test-session" if resume else None)
        deadline = time.monotonic() + 5
        while agent.process is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)
        assert agent.process is None and log.exists()
        return json.loads(log.read_text())

    for resume in (False, True):
        for enabled in (False, True):
            call = run("codex", "default", web_search=enabled, resume=resume)
            args = call['args']
            assert ('resume' in args) == resume
            expected = 'web_search="live"' if enabled else 'web_search="disabled"'
            assert expected in args
            assert '--allowedTools' not in args and '--disallowedTools' not in args

    claude = run("claude", "default", api_key="direct-key")
    assert claude["env"]["ANTHROPIC_BASE_URL"] is None
    assert claude["env"]["ANTHROPIC_API_KEY"] == "direct-key"
    assert claude["env"]["ANTHROPIC_AUTH_TOKEN"] is None
    assert claude["env"]["OPENAI_API_KEY"] is None
    assert claude["env"]["AWS_BEARER_TOKEN_BEDROCK"] is None

    claude_aws = run("claude", "bedrock")
    assert claude_aws["env"]["CLAUDE_CODE_USE_BEDROCK"] == "1"
    assert claude_aws["env"]["ANTHROPIC_API_KEY"] is None
    assert claude_aws["env"]["AWS_REGION"] == "us-east-1"
    assert claude_aws["env"]["AWS_BEARER_TOKEN_BEDROCK"] == "bedrock-key"

    codex = run("codex", "default", api_key="direct-key")
    assert 'forced_login_method="api"' in codex["args"]
    assert codex["env"]["CODEX_API_KEY"] == "direct-key"
    assert codex["env"]["OPENAI_API_KEY"] is None
    assert codex["env"]["AWS_BEARER_TOKEN_BEDROCK"] is None

    codex_aws = run("codex", "amazon-bedrock-runtime")
    assert 'model_provider="amazon-bedrock-runtime"' in codex_aws["args"]
    assert codex_aws["env"]["AWS_PROFILE"] == "example"
    assert codex_aws["env"]["AWS_BEARER_TOKEN_BEDROCK"] == "bedrock-key"
    assert codex_aws["env"]["CODEX_API_KEY"] is None
    assert not any(arg.startswith("forced_login_method=") for arg in codex_aws["args"])

    agent.close()
print("PASS: endpoint routing and credential isolation")
