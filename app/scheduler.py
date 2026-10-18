import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from .db import connect
from .agent import run_agent

UTC = timezone.utc

def next_occurrence(clock, zone, now=None):
    now = now or datetime.now(UTC)
    local = now.astimezone(ZoneInfo(zone))
    hour, minute = map(int, clock.split(":"))
    # Round-trip handles nonexistent spring-forward wall times; first fold only.
    for offset in range(3):
        day = local.date() + timedelta(days=offset)
        candidate = datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZoneInfo(zone), fold=0).astimezone(UTC)
        if candidate > now:
            return candidate.isoformat()
    raise ValueError("Cannot calculate next occurrence")

async def generate_and_notify(run_id, preference):
    await run_agent(run_id, preference)
    with connect() as conn:
        conn.execute("UPDATE run_owners SET unread=1 WHERE run_id=? AND EXISTS(SELECT 1 FROM runs WHERE id=? AND brief IS NOT NULL AND status IN ('succeeded','partial'))", (run_id,run_id))


def claim_due(now=None):
    now = now or datetime.now(UTC)
    claimed = []
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute("SELECT * FROM user_subscriptions WHERE enabled=1 AND next_run_at<=?", (now.isoformat(),)).fetchall()
        for row in rows:
            run_id = uuid.uuid4().hex
            existing = conn.execute("SELECT 1 FROM run_owners WHERE user_id=? AND scheduled_for=?", (row['user_id'],row['next_run_at'])).fetchone()
            if not existing:
                conn.execute("INSERT INTO runs(id,status,created_at) VALUES(?, 'queued', ?)", (run_id,now.isoformat()))
                conn.execute("INSERT INTO run_owners(run_id,user_id,scheduled_for) VALUES(?,?,?)", (run_id,row['user_id'],row['next_run_at']))
                claimed.append((run_id,{k:v for k,v in dict(row).items() if k != "user_id"}))
            conn.execute("UPDATE user_subscriptions SET next_run_at=? WHERE user_id=?", (next_occurrence(row['scheduled_time'],row['timezone'],now),row['user_id']))
    return claimed

class Scheduler:
    def __init__(self):
        self.wake = asyncio.Event()
        self.jobs = set()

    async def serve(self):
        while True:
            for run_id, preference in claim_due():
                task = asyncio.create_task(generate_and_notify(run_id,preference))
                self.jobs.add(task)
                task.add_done_callback(self.jobs.discard)
            with connect() as conn:
                row = conn.execute("SELECT MIN(next_run_at) FROM user_subscriptions WHERE enabled=1").fetchone()
            delay = min(30, max(0.1,(datetime.fromisoformat(row[0])-datetime.now(UTC)).total_seconds())) if row[0] else 30
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=delay)
            except asyncio.TimeoutError:
                pass
            self.wake.clear()

    async def close(self):
        for job in list(self.jobs):
            job.cancel()
        await asyncio.gather(*self.jobs, return_exceptions=True)
