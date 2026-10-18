CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_subscriptions (
 user_id TEXT PRIMARY KEY REFERENCES users(id), nickname TEXT NOT NULL,
 topics TEXT NOT NULL, keywords TEXT NOT NULL, exclusions TEXT NOT NULL,
 scheduled_time TEXT NOT NULL DEFAULT '09:00', timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
 enabled INTEGER NOT NULL DEFAULT 0, next_run_at TEXT
);
CREATE TABLE IF NOT EXISTS run_owners (
 run_id TEXT PRIMARY KEY REFERENCES runs(id), user_id TEXT NOT NULL REFERENCES users(id),
 scheduled_for TEXT, unread INTEGER NOT NULL DEFAULT 0,
 UNIQUE(user_id, scheduled_for)
);
CREATE INDEX IF NOT EXISTS run_owners_user ON run_owners(user_id);
CREATE TABLE IF NOT EXISTS app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
