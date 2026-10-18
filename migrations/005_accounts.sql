CREATE TABLE IF NOT EXISTS accounts (
 user_id TEXT PRIMARY KEY REFERENCES users(id), username TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES accounts(user_id), expires_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_prompts (
 user_id TEXT PRIMARY KEY REFERENCES users(id), custom_prompt TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS auth_attempts (
 key TEXT PRIMARY KEY, failures INTEGER NOT NULL, window_start TEXT NOT NULL
);
