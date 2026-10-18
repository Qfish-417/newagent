"""Local lexical RAG: paragraph chunks, Chinese bigrams and term ranking."""
import math
import re
from collections import Counter
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from datetime import datetime, timezone
from .db import connect


def tokens(text):
    text = text.casefold()
    words = re.findall(r"[a-z0-9_]+", text)
    for span in re.findall(r"[\u4e00-\u9fff]+", text):
        words.extend(span[i:i+2] for i in range(max(1, len(span)-1)))
    return Counter(words)


def add_document(title, content, source, published_at):
    # Bounded overlap retains context across chunk boundaries.
    chunks = [content[i:i+1000] for i in range(0, len(content), 850)]
    with connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM knowledge_documents").fetchone()[0]
        if total >= 200:
            raise ValueError("Knowledge base limit: 200 documents")
        cursor = conn.execute("INSERT INTO knowledge_documents(title,source,published_at,imported_at) VALUES(?,?,?,?)",
            (title, source, published_at, datetime.now(timezone.utc).isoformat()))
        doc_id = cursor.lastrowid
        conn.executemany("INSERT INTO knowledge_chunks(document_id,position,content) VALUES(?,?,?)",
            [(doc_id, i, chunk) for i, chunk in enumerate(chunks)])
    return doc_id


def retrieve(query, limit=5):
    query_terms = tokens(query)
    if not query_terms:
        return []
    with connect() as conn:
        rows = conn.execute("SELECT c.id,c.position,c.content,d.title,d.source,d.published_at,d.imported_at,a.first_seen_at,a.last_seen_at FROM knowledge_chunks c JOIN knowledge_documents d ON d.id=c.document_id LEFT JOIN news_archive a ON a.document_id=d.id").fetchall()
    corpus = [tokens(row["title"] + " " + row["content"]) for row in rows]
    counts = Counter(term for terms in corpus for term in terms)
    ranked = []
    for row, terms in zip(rows, corpus):
        overlap = set(query_terms) & set(terms)
        if not overlap:
            continue
        score = sum((1 + math.log(terms[t])) * math.log(1 + len(rows)/(1 + counts[t])) for t in overlap) / math.sqrt(max(1, sum(terms.values())))
        ranked.append({**dict(row), "citation": f"KB-{row['id']}", "score": round(score, 5), "kind": "archived_news" if row["first_seen_at"] else "background_knowledge"})
    return sorted(ranked, key=lambda r: (-r["score"], r["id"]))[:limit]


def canonical_url(value):
    if not isinstance(value, str) or len(value) > 2000:
        return None
    try:
        parts = urlsplit(value)
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            return None
        query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                 if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}]
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", urlencode(sorted(query)), ""))
    except ValueError:
        return None


def archive_news(results, run_id):
    """Persist provider evidence, never model-generated summaries. Unique URL is transactional."""
    stats = {"saved": 0, "existing": 0, "skipped": 0}
    now = datetime.now(timezone.utc).isoformat()
    with connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        for item in results[:50]:
            if not isinstance(item, dict):
                stats["skipped"] += 1
                continue
            url = canonical_url(item.get("url"))
            title = item.get("title")
            content = item.get("content") or item.get("raw_content")
            if not url or not isinstance(title, str) or not title.strip() or not isinstance(content, str) or not content.strip():
                stats["skipped"] += 1
                continue
            existing = conn.execute("SELECT document_id FROM news_archive WHERE canonical_url=?", (url,)).fetchone()
            if existing:
                conn.execute("UPDATE news_archive SET last_seen_at=?,last_run_id=? WHERE canonical_url=?", (now, run_id, url))
                stats["existing"] += 1
                continue
            if conn.execute("SELECT COUNT(*) FROM knowledge_documents").fetchone()[0] >= 200:
                stats["skipped"] += 1
                continue
            published = item.get("published_date") or item.get("published_at")
            published = published[:100] if isinstance(published, str) else None
            doc_id = conn.execute("INSERT INTO knowledge_documents(title,source,published_at,imported_at) VALUES(?,?,?,?)",
                (title[:200], url, published, now)).lastrowid
            content = content[:50000]
            conn.executemany("INSERT INTO knowledge_chunks(document_id,position,content) VALUES(?,?,?)",
                [(doc_id, i//850, content[i:i+1000]) for i in range(0, len(content), 850)])
            conn.execute("INSERT INTO news_archive VALUES(?,?,?,?,?)", (url, doc_id, now, now, run_id))
            stats["saved"] += 1
    return stats
