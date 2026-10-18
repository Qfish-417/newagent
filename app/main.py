import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from datetime import date
from .knowledge import add_document, retrieve
from .db import initialize, connect
from .agent import run_agent

@asynccontextmanager
async def lifespan(app):
    initialize()
    with connect() as conn:
        conn.execute("UPDATE runs SET status='failed', error='Service restarted during task' WHERE status IN ('queued','running')")
    yield

app = FastAPI(title="newagent", lifespan=lifespan)

class Subscription(BaseModel):
    nickname: str = Field(min_length=1, max_length=50)
    topics: str = Field(default="AI Agent, 大模型", max_length=1000)
    keywords: str = Field(default="", max_length=1000)
    exclusions: str = Field(default="", max_length=1000)

@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static/index.html")

@app.get("/api/subscription")
def get_subscription():
    with connect() as conn:
        row = conn.execute("SELECT * FROM subscriptions WHERE id=1").fetchone()
    return dict(row) if row else None

@app.put("/api/subscription")
def save_subscription(body: Subscription):
    with connect() as conn:
        conn.execute("INSERT OR REPLACE INTO subscriptions VALUES(1,?,?,?,?)", tuple(body.model_dump().values()))
    return {"ok": True}

@app.post("/api/runs", status_code=202)
def create_run(tasks: BackgroundTasks):
    preference = get_subscription()
    if not preference:
        raise HTTPException(400, "Save subscription first")
    run_id = uuid.uuid4().hex
    with connect() as conn:
        conn.execute("INSERT INTO runs(id,status,created_at) VALUES(?,?,?)", (run_id,"queued",datetime.now(timezone.utc).isoformat()))
    tasks.add_task(run_agent, run_id, preference)
    return {"id": run_id, "status": "queued"}

@app.get("/api/runs")
def list_runs():
    with connect() as conn:
        return [dict(row) for row in conn.execute("SELECT id,status,created_at,error FROM runs ORDER BY created_at DESC LIMIT 50")]

@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    with connect() as conn:
        row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Run not found")
        result = dict(row)
        result["notices"] = [r[0] for r in conn.execute("SELECT message FROM run_notices WHERE run_id=?", (run_id,))]
        result["tool_calls"] = [dict(item) for item in conn.execute("SELECT name,arguments,result FROM tool_calls WHERE run_id=? ORDER BY id", (run_id,))]
    return result


class KnowledgeDocument(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=50000)
    source: str = Field(min_length=1, max_length=500)
    published_at: date | None = None

@app.post("/api/knowledge", status_code=201)
def import_knowledge(body: KnowledgeDocument):
    if not body.content.strip() or not body.title.strip() or not body.source.strip():
        raise HTTPException(422, "Title, content and source cannot be blank")
    try:
        doc_id = add_document(body.title, body.content, body.source, body.published_at.isoformat() if body.published_at else None)
    except ValueError as error:
        raise HTTPException(409, str(error))
    return {"id": doc_id}

@app.get("/api/knowledge")
def list_knowledge():
    with connect() as conn:
        return [dict(row) for row in conn.execute("SELECT d.*, CASE WHEN a.document_id IS NULL THEN 'manual' ELSE 'archived_news' END AS kind, a.first_seen_at,a.last_seen_at FROM knowledge_documents d LEFT JOIN news_archive a ON a.document_id=d.id ORDER BY d.id DESC")]

@app.get("/api/knowledge/search")
def search_knowledge(q: str = ""):
    if len(q) > 500:
        raise HTTPException(422, "Query too long")
    return retrieve(q)


@app.get("/api/knowledge/{document_id}")
def get_knowledge(document_id: int):
    with connect() as conn:
        row = conn.execute("SELECT * FROM knowledge_documents WHERE id=?", (document_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Document not found")
        chunks = conn.execute("SELECT content FROM knowledge_chunks WHERE document_id=? ORDER BY position", (document_id,)).fetchall()
    # Chunks overlap by 150 characters: restore original content without repetition.
    content = "" if not chunks else chunks[0][0] + "".join(c[0][150:] for c in chunks[1:])
    return {**dict(row), "content": content}
