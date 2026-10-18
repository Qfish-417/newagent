CREATE TABLE IF NOT EXISTS news_archive (
 canonical_url TEXT PRIMARY KEY,
 document_id INTEGER NOT NULL UNIQUE REFERENCES knowledge_documents(id),
 first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
 last_run_id TEXT NOT NULL REFERENCES runs(id)
);
