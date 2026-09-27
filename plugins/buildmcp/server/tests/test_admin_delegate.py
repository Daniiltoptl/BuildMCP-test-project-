"""Delegation: a fake Gemini CLI (headless JSON, read-only and edit modes), a mocked Mistral API, the
refusal of building tasks, edit rights only in devplugin projects, and the usage log."""

import json
import os
import sys
import textwrap

import httpx
import pytest

from buildmcp.admin import delegate, devplugin, net

FAKE_GEMINI = textwrap.dedent('''
    import json, os, sys, pathlib
    args = sys.argv[1:]
    if args == ["--version"]:
        print("0.61.0"); sys.exit(0)
    stdin = sys.stdin.read()
    pathlib.Path(os.environ["FAKE_GEMINI_LOG"]).write_text(json.dumps({"args": args, "stdin": stdin, "cwd": os.getcwd()}))
    if "FAIL PLEASE" in stdin:
        print(json.dumps({"error": {"type": "ApiError", "message": "quota exceeded", "code": 429}})); sys.exit(1)
    if "--approval-mode" in args and args[args.index("--approval-mode") + 1] == "auto_edit":
        p = pathlib.Path("src/main/resources/config.yml")
        p.write_text(p.read_text() + "  bye: 'Bye'\\n")
    print("Loaded cached credentials.")
    print(json.dumps({"session_id": "s1", "response": "messages:\\n  hello: 'Привет'",
                      "stats": {"models": {"gemini-2.5-flash": {"tokens": {"total": 321}}}}}))
''')


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("BUILDMCP_DATA", str(tmp_path / "data"))
    script = tmp_path / "fake_gemini.py"
    script.write_text(FAKE_GEMINI, "utf-8")
    if os.name == "nt":
        exe = tmp_path / "gemini.cmd"
        exe.write_text(f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n')
    else:
        exe = tmp_path / "gemini"
        exe.write_text(f"#!{sys.executable}\n" + FAKE_GEMINI, "utf-8")
        exe.chmod(0o755)
    monkeypatch.setenv("BUILDMCP_GEMINI_CLI", str(exe))
    monkeypatch.setenv("FAKE_GEMINI_LOG", str(tmp_path / "gemini-call.json"))
    for var in ("BUILDMCP_MISTRAL_API_KEY", "MISTRAL_API_KEY", "BUILDMCP_GEMINI_MODEL", "BUILDMCP_MISTRAL_MODEL"):
        monkeypatch.delenv(var, raising=False)
    yield tmp_path
    net.set_transport(None)


def _call(tmp):
    return json.loads((tmp / "gemini-call.json").read_text())


def test_gemini_answers_read_only_with_the_task_on_stdin(env):
    cfg = env / "messages.yml"
    cfg.write_text("messages:\n  hello: 'Hello'\n")
    secret = env / "config.yml"
    secret.write_text("storage:\n  password: hunter2\n  api-key: sk-123\n")
    st = delegate.status()
    assert st["gemini"]["version"] == "0.61.0" and st["mistral"]["key"] is False
    out = delegate.run("Translate the messages to Russian, keep the keys.", files=[str(cfg), str(secret)])
    assert out["to"] == "gemini" and out["answer"].endswith("'Привет'") and out["tokens"] == 321
    assert out["model"] == "gemini-2.5-flash"
    call = _call(env)
    a = call["args"]
    assert a[a.index("--approval-mode") + 1] == "plan" and a[a.index("-o") + 1] == "json" and "--skip-trust" in a
    assert call["stdin"].startswith(delegate.SYSTEM) and "Translate the messages" in call["stdin"]
    assert "--- FILE messages.yml ---\nmessages:\n  hello: 'Hello'" in call["stdin"]
    assert "hunter2" not in call["stdin"] and "sk-123" not in call["stdin"] and "password: '***'" in call["stdin"]
    with pytest.raises(delegate.DelegateError, match="quota exceeded"):
        delegate.run("FAIL PLEASE")
    u = delegate.usage()
    assert u["by"]["gemini"]["calls"] == 2 and u["by"]["gemini"]["failed"] == 1 and u["by"]["gemini"]["tokens"] == 321


def test_gemini_edits_only_inside_a_devplugin_project(env):
    with pytest.raises(delegate.DelegateError, match="devplugin project"):
        delegate.run("tidy up", edit=True, workdir=str(env))
    proj = devplugin.create("Greeter", "paper", commands=["hello"])["project"]
    out = delegate.run("add a bye message to config.yml", edit=True, workdir=proj)
    assert out["changed_files"] == ["src/main/resources/config.yml"]
    assert "+  bye: 'Bye'" in out["diff"]
    assert os.path.samefile(_call(env)["cwd"], proj)
    with pytest.raises(delegate.DelegateError, match="Gemini only"):
        delegate.run("x", to="mistral", edit=True, workdir=proj)


def test_building_is_never_delegated(env):
    for task in ("Build me a spawn for the anarchy server", "постройте спавн в античном стиле",
                 "write a run_script step with scene.fill"):
        with pytest.raises(delegate.DelegateError, match="building stays with Claude"):
            delegate.run(task)
    assert not (env / "gemini-call.json").exists()


def test_mistral_models_key_and_errors(env, monkeypatch):
    seen = []

    def handler(req: httpx.Request):
        body = json.loads(req.content)
        seen.append((req.headers["authorization"], body["model"], body["messages"][0]["role"]))
        if req.headers["authorization"] == "Bearer bad":
            return httpx.Response(401, json={"message": "Unauthorized"})
        return httpx.Response(200, json={"model": body["model"], "usage": {"total_tokens": 42},
                                         "choices": [{"message": {"role": "assistant", "content": "done"}}]})

    net.set_transport(httpx.MockTransport(handler))
    with pytest.raises(delegate.DelegateError, match="no Mistral API key"):
        delegate.run("reword this MOTD", to="mistral")
    monkeypatch.setenv("BUILDMCP_MISTRAL_API_KEY", "k1")
    assert delegate.run("reword this MOTD", to="mistral")["answer"] == "done"
    assert delegate.run("write a Java method", to="mistral", kind="code")["model"] == "codestral-latest"
    monkeypatch.setenv("BUILDMCP_MISTRAL_MODEL", "mistral-medium-latest")
    assert delegate.run("reword", to="mistral")["model"] == "mistral-medium-latest"
    assert seen[0] == ("Bearer k1", "mistral-small-latest", "system")
    monkeypatch.setenv("BUILDMCP_MISTRAL_API_KEY", "bad")
    with pytest.raises(delegate.DelegateError, match="401"):
        delegate.run("x", to="mistral")
    # auto: Gemini when it is installed, else Mistral
    monkeypatch.setenv("BUILDMCP_MISTRAL_API_KEY", "k1")
    assert delegate.run("x")["to"] == "gemini"
    monkeypatch.setenv("BUILDMCP_GEMINI_CLI", str(env / "no-such-gemini"))
    assert delegate.run("x")["to"] == "mistral"


def test_the_tool(env):
    from buildmcp import admin_tools

    out = json.loads(admin_tools.delegate(action="status"))
    assert out["rule"].startswith("building")
    assert admin_tools.delegate(task="Build a castle hub").startswith("Error: building stays with Claude")
    assert json.loads(admin_tools.delegate(task="summarize", files=[]))["to"] == "gemini"
