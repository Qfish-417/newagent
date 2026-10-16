import asyncio
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.tools import Tools

def test_workspace_escape(tmp_path):
    tools = Tools(tmp_path / "workspace")
    with pytest.raises(ValueError):
        tools.path("../secret")
    with pytest.raises(ValueError):
        asyncio.run(tools.execute("bash", {"command": "python -c print(1)"}))
    asyncio.run(tools.execute("write_file", {"path": "note.txt", "content": "AI news"}))
    assert asyncio.run(tools.execute("search_content", {"keyword": "AI", "dir": "."})) == ["note.txt"]

def test_api_and_missing_key_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "openai_api_key", "")
    with TestClient(app) as client:
        assert client.post("/api/runs").status_code == 400
        assert client.put("/api/subscription", json={"nickname":"test","topics":"Agent"}).status_code == 200
        run = client.post("/api/runs").json()
        detail = client.get("/api/runs/" + run["id"]).json()
        assert detail["status"] == "failed"
        assert "OPENAI_API_KEY" in detail["error"]
        assert client.get("/").status_code == 200
        assert client.get("/api/runs/missing").status_code == 404


def test_model_drives_tool_order_and_stops(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import app.agent as agent
    from app.db import initialize, connect
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "openai_api_key", "test-only")
    initialize()
    with connect() as conn:
        conn.execute("INSERT INTO runs(id,status,created_at) VALUES('demo','queued','now')")
    seen = []
    class Message:
        def __init__(self, name=None):
            self.content = None if name else "测试简报 https://example.com/news"
            self.tool_calls = [SimpleNamespace(id=name, function=SimpleNamespace(name=name, arguments='{"query":"AI"}' if name == "search_news" else '{"path":"."}'))] if name else None
        def model_dump(self, **kwargs):
            return {"role": "assistant", "content": self.content}
    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=self)
            self.responses = iter([Message("search_news"), Message("list_dir"), Message()])
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def create(self, **kwargs):
            seen.append(list(kwargs["messages"]))
            return SimpleNamespace(choices=[SimpleNamespace(message=next(self.responses))])
    original = Tools.execute
    async def execute(self, name, args):
        if name == "search_news": return [{"url":"https://example.com/news", "title":"AI"}]
        return await original(self, name, args)
    monkeypatch.setattr(agent, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(Tools, "execute", execute)
    asyncio.run(agent.run_agent("demo", {"topics":"AI"}))
    with connect() as conn:
        assert conn.execute("SELECT status FROM runs WHERE id='demo'").fetchone()[0] == "succeeded"
        assert [r[0] for r in conn.execute("SELECT name FROM tool_calls ORDER BY id")] == ["search_news", "list_dir"]
    assert len(seen) == 3
    assert seen[1][-1]["role"] == "tool"


def test_deepseek_environment_config(monkeypatch):
    from app.config import Settings
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-deepseek-key")
    monkeypatch.setenv("OPENAI_API_KEY", "fake-other-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    config = Settings(_env_file=None)
    assert config.openai_api_key == "fake-deepseek-key"
    assert config.model == "deepseek-chat"
    assert config.openai_base_url == "https://api.deepseek.com"
