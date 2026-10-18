CREATE TABLE IF NOT EXISTS knowledge_documents (
 id INTEGER PRIMARY KEY, title TEXT NOT NULL, source TEXT NOT NULL,
 published_at TEXT, imported_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS knowledge_chunks (
 id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES knowledge_documents(id),
 position INTEGER NOT NULL, content TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS run_notices (
 id INTEGER PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id),
 message TEXT NOT NULL
);
