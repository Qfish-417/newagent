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


@pytest.mark.parametrize("mode", ["news", "rag", "empty"])
def test_model_drives_tool_order_and_stops(tmp_path, monkeypatch, mode):
    from types import SimpleNamespace
    import app.agent as agent
    from app.db import initialize, connect
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "openai_api_key", "test-only")
    initialize()
    with connect() as conn:
        conn.execute("INSERT INTO runs(id,status,created_at) VALUES('demo','queued','now')")
    if mode == "rag":
        from app.knowledge import add_document
        add_document("AI Agent", "AI agents use tools and retrieval.", "my-notes.md", "2026-01-01")
    seen = []
    class Message:
        def __init__(self, name=None):
            self.content = None if name else "测试简报 https://example.com/news"
            self.tool_calls = [SimpleNamespace(id=name, function=SimpleNamespace(name=name, arguments='{"query":"AI"}' if name in {"search_news", "search_knowledge"} else '{"path":"."}'))] if name else None
        def model_dump(self, **kwargs):
            return {"role": "assistant", "content": self.content}
    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = SimpleNamespace(completions=self)
            self.responses = iter([Message("search_news"), Message("list_dir" if mode == "news" else "search_knowledge"), Message()])
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def create(self, **kwargs):
            seen.append(list(kwargs["messages"]))
            return SimpleNamespace(choices=[SimpleNamespace(message=next(self.responses))])
    original = Tools.execute
    async def execute(self, name, args):
        if name == "search_news":
            if mode != "news": raise ValueError("Search unavailable")
            return [{"url":"https://example.com/news", "title":"AI", "content":"AI agents use retrieval.", "published_date":"2026-10-18"}]
        return await original(self, name, args)
    monkeypatch.setattr(agent, "AsyncOpenAI", FakeClient)
    monkeypatch.setattr(Tools, "execute", execute)
    asyncio.run(agent.run_agent("demo", {"topics":"AI"}))
    with connect() as conn:
        row = conn.execute("SELECT status,brief FROM runs WHERE id='demo'").fetchone()
        assert row[0] == {"news":"succeeded", "rag":"partial", "empty":"failed"}[mode]
        if mode == "rag":
            assert "KB-" in row[1] and "my-notes.md" in row[1] and "2026-01-01" in row[1]
            assert "非实时新闻" in row[1]
        assert [r[0] for r in conn.execute("SELECT name FROM tool_calls ORDER BY id")] == ["search_news", "list_dir" if mode == "news" else "search_knowledge"]
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


def test_knowledge_api_retrieval_and_migration(tmp_path, monkeypatch):
    from app.db import initialize
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    with TestClient(app) as client:
        initialize()  # Migrations are repeatable, existing data is preserved.
        response = client.post("/api/knowledge", json={"title":"检索增强生成", "source":"个人笔记.md", "content":"检索增强生成通过知识库为大模型提供背景资料。"})
        assert response.status_code == 201
        matches = client.get("/api/knowledge/search", params={"q":"知识库"}).json()
        assert matches and matches[0]["source"] == "个人笔记.md"
        assert matches[0]["published_at"] is None
        assert matches[0]["kind"] == "background_knowledge"
        assert client.get("/api/knowledge/search", params={"q":"unrelatedxyz"}).json() == []
        assert client.get("/api/knowledge/search", params={"q":""}).json() == []
        assert client.post("/api/knowledge", json={"title":"x", "source":"y", "content":" "}).status_code == 422
        assert len(client.get("/api/knowledge").json()) == 1


def test_search_archive_deduplicates_and_is_retrievable(tmp_path, monkeypatch):
    from app.db import initialize, connect
    from app.knowledge import archive_news, retrieve
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    initialize()
    with connect() as conn:
        conn.execute("INSERT INTO runs(id,status,created_at) VALUES('archive','running','now')")
    news = {"title":"Agent retrieval", "url":"https://example.com/news?utm_source=test#top", "content":"Agent retrieval tools background", "published_date":"2026-10-17"}
    assert archive_news([news], "archive")["saved"] == 1
    news["url"] = "https://example.com/news"
    assert archive_news([news], "archive")["existing"] == 1
    hit = retrieve("retrieval")[0]
    assert hit["kind"] == "archived_news"
    assert hit["published_at"] == "2026-10-17"
    assert hit["source"] == "https://example.com/news"
    assert hit["first_seen_at"] and hit["last_seen_at"]
    assert archive_news([{"url":"file:///secret"}, {"title":"x", "url":"https://example.com/empty"}], "archive")["skipped"] == 2
    initialize()
    with connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM knowledge_documents").fetchone()[0] == 1


def test_knowledge_detail_restores_overlapping_chunks(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    content = "知识库资料详情" * 300
    with TestClient(app) as client:
        result = client.post("/api/knowledge", json={"title":"长文", "source":"notes", "content":content})
        detail = client.get("/api/knowledge/" + str(result.json()["id"]))
        assert detail.status_code == 200
        assert detail.json()["content"] == content
        assert client.get("/api/knowledge/99999").status_code == 404
