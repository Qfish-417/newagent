import asyncio
import secrets
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator
from .db import initialize, connect
from .scheduler import Scheduler, next_occurrence, generate_and_notify

@asynccontextmanager
async def lifespan(app):
    initialize()
    with connect() as conn:
        conn.execute("UPDATE runs SET status='failed', error='Service restarted during task' WHERE status IN ('queued','running')")
    app.state.scheduler = Scheduler()
    task = asyncio.create_task(app.state.scheduler.serve())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await app.state.scheduler.close()

app = FastAPI(title="newagent", lifespan=lifespan)

@app.middleware("http")
async def identity(request: Request, call_next):
    token = request.cookies.get("newagent_user", "")
    with connect() as conn:
        row = conn.execute("SELECT id FROM users WHERE id=?", (token,)).fetchone() if token else None
        fresh = not row
        if fresh:
            token = secrets.token_urlsafe(32)
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT INTO users VALUES(?,?)", (token,datetime.now(timezone.utc).isoformat()))
            # One-time migration: first local visitor inherits the existing single-user data.
            migrated = conn.execute("SELECT 1 FROM app_metadata WHERE key='legacy_owner'").fetchone()
            if not migrated:
                conn.execute("INSERT INTO app_metadata VALUES('legacy_owner',?)", (token,))
                old = conn.execute("SELECT * FROM subscriptions WHERE id=1").fetchone()
                if old:
                    conn.execute("INSERT INTO user_subscriptions(user_id,nickname,topics,keywords,exclusions) VALUES(?,?,?,?,?)", (token,old['nickname'],old['topics'],old['keywords'],old['exclusions']))
                conn.execute("INSERT OR IGNORE INTO run_owners(run_id,user_id) SELECT id,? FROM runs", (token,))
    request.state.user_id = token
    response = await call_next(request)
    if fresh:
        response.set_cookie("newagent_user",token,httponly=True,samesite="strict",max_age=31536000,secure=request.url.scheme=="https")
    return response

class Subscription(BaseModel):
    nickname: str = Field(min_length=1, max_length=50)
    topics: str = Field(default="AI Agent, 大模型", max_length=1000)
    keywords: str = Field(default="", max_length=1000)
    exclusions: str = Field(default="", max_length=1000)
    scheduled_time: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: str = "Asia/Shanghai"
    enabled: bool = False

    @field_validator("timezone")
    @classmethod
    def validate_zone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Invalid IANA timezone")
        return value

@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static/index.html")

@app.get("/api/subscription")
def get_subscription(request: Request):
    with connect() as conn:
        row = conn.execute("SELECT * FROM user_subscriptions WHERE user_id=?", (request.state.user_id,)).fetchone()
    if not row:
        return None
    return {k:v for k,v in dict(row).items() if k!='user_id'}

@app.put("/api/subscription")
async def save_subscription(body: Subscription, request: Request):
    due = next_occurrence(body.scheduled_time,body.timezone) if body.enabled else None
    with connect() as conn:
        conn.execute("INSERT INTO user_subscriptions VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET nickname=excluded.nickname,topics=excluded.topics,keywords=excluded.keywords,exclusions=excluded.exclusions,scheduled_time=excluded.scheduled_time,timezone=excluded.timezone,enabled=excluded.enabled,next_run_at=excluded.next_run_at",
            (request.state.user_id,body.nickname,body.topics,body.keywords,body.exclusions,body.scheduled_time,body.timezone,int(body.enabled),due))
    request.app.state.scheduler.wake.set()
    return {"ok":True,"next_run_at":due,"server_time":datetime.now(timezone.utc).isoformat()}

@app.post("/api/runs", status_code=202)
def create_run(tasks: BackgroundTasks, request: Request):
    preference = get_subscription(request)
    if not preference:
        raise HTTPException(400,"Save subscription first")
    run_id = uuid.uuid4().hex
    with connect() as conn:
        conn.execute("INSERT INTO runs(id,status,created_at) VALUES(?, 'queued', ?)", (run_id,datetime.now(timezone.utc).isoformat()))
        conn.execute("INSERT INTO run_owners(run_id,user_id) VALUES(?,?)", (run_id,request.state.user_id))
    tasks.add_task(generate_and_notify,run_id,preference)
    return {"id":run_id,"status":"queued"}

@app.get("/api/runs")
def list_runs(request: Request):
    with connect() as conn:
        return [dict(row) for row in conn.execute("SELECT r.id,r.status,r.created_at,r.error,o.unread,o.scheduled_for FROM runs r JOIN run_owners o ON r.id=o.run_id WHERE o.user_id=? ORDER BY r.created_at DESC LIMIT 50", (request.state.user_id,))]

@app.get("/api/runs/{run_id}")
def get_run(run_id: str, request: Request):
    with connect() as conn:
        row = conn.execute("SELECT r.*,o.unread,o.scheduled_for FROM runs r JOIN run_owners o ON r.id=o.run_id WHERE r.id=? AND o.user_id=?", (run_id,request.state.user_id)).fetchone()
        if not row:
            raise HTTPException(404,"Run not found")
        result = dict(row)
        result['notices'] = [r[0] for r in conn.execute("SELECT message FROM run_notices WHERE run_id=?", (run_id,))]
        result['tool_calls'] = [dict(item) for item in conn.execute("SELECT name FROM tool_calls WHERE run_id=? ORDER BY id", (run_id,))]
    return result

@app.post("/api/runs/{run_id}/read")
def mark_read(run_id: str, request: Request):
    with connect() as conn:
        cursor = conn.execute("UPDATE run_owners SET unread=0 WHERE run_id=? AND user_id=?", (run_id,request.state.user_id))
        if not cursor.rowcount:
            raise HTTPException(404,"Run not found")
    return {"ok":True}

@app.get("/api/schedule")
def schedule_status(request: Request):
    pref = get_subscription(request)
    now = datetime.now(timezone.utc)
    due = pref.get('next_run_at') if pref else None
    return {"server_time":now.isoformat(),"next_run_at":due,"seconds_remaining":max(0,(datetime.fromisoformat(due)-now).total_seconds()) if due else None}
