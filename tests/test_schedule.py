import asyncio
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from app.main import app
from app.config import settings
from app.db import connect, initialize
from app.scheduler import next_occurrence, claim_due, generate_and_notify


def test_next_occurrence_and_midnight():
    now = datetime(2026,10,18,0,0,tzinfo=timezone.utc)
    assert next_occurrence("09:00","Asia/Shanghai",now) == "2026-10-18T01:00:00+00:00"
    assert next_occurrence("08:00","Asia/Shanghai",now) == "2026-10-19T00:00:00+00:00"
    assert next_occurrence("00:05","Asia/Shanghai",now) == "2026-10-18T16:05:00+00:00"


def test_user_isolation_and_schedule_edit(tmp_path,monkeypatch):
    monkeypatch.setattr(settings,"data_dir",tmp_path)
    monkeypatch.setattr(settings,"openai_api_key","")
    with TestClient(app) as a:
        a.put("/api/subscription",json={"nickname":"A", "scheduled_time":"23:58", "enabled":True})
        original = a.get("/api/subscription").json()
        assert original["next_run_at"]
        run = a.post("/api/runs").json()["id"]
        a.cookies.clear()  # A separate browser identity gets different data.
        assert a.get("/api/subscription").json() is None
        assert a.get("/api/runs").json() == []
        assert a.get("/api/runs/"+run).status_code == 404
        assert a.post("/api/runs/"+run+"/read").status_code == 404
        assert a.put("/api/subscription",json={"nickname":"B","timezone":"No/SuchZone"}).status_code == 422
        assert a.put("/api/subscription",json={"nickname":"B","scheduled_time":"24:00"}).status_code == 422
        a.put("/api/subscription",json={"nickname":"B","scheduled_time":"00:01","enabled":True})
        before = a.get("/api/subscription").json()["next_run_at"]
        a.put("/api/subscription",json={"nickname":"B","scheduled_time":"00:02","enabled":True})
        assert a.get("/api/subscription").json()["next_run_at"] != before
        a.put("/api/subscription",json={"nickname":"B","enabled":False})
        assert a.get("/api/schedule").json()["next_run_at"] is None


def test_due_claim_is_unique_and_notification_persists(tmp_path,monkeypatch):
    import app.scheduler as scheduler
    monkeypatch.setattr(settings,"data_dir",tmp_path)
    initialize()
    with connect() as conn:
        conn.execute("INSERT INTO users VALUES('a','now')")
        conn.execute("INSERT INTO user_subscriptions VALUES('a','A','AI','','','09:00','Asia/Shanghai',1,'2026-10-17T01:00:00+00:00')")
    with connect() as conn:
        conn.execute("INSERT INTO user_prompts VALUES('a','重点分析开源Agent')")
    now = datetime(2026,10,18,2,tzinfo=timezone.utc)
    due = claim_due(now)
    assert len(due) == 1
    assert due[0][1]["custom_prompt"] == "重点分析开源Agent"
    assert "user_id" not in due[0][1]
    assert claim_due(now) == []
    initialize()
    assert claim_due(now) == []
    with connect() as conn:
        assert conn.execute("SELECT next_run_at FROM user_subscriptions").fetchone()[0] == "2026-10-19T01:00:00+00:00"
    async def fake_agent(run_id, preference):
        with connect() as conn:
            conn.execute("UPDATE runs SET status='succeeded',brief='brief' WHERE id=?",(run_id,))
    monkeypatch.setattr(scheduler,"run_agent",fake_agent)
    asyncio.run(generate_and_notify(*due[0]))
    with connect() as conn:
        assert conn.execute("SELECT unread FROM run_owners").fetchone()[0] == 1
