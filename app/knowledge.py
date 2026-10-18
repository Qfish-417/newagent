"""Local lexical RAG: paragraph chunks, Chinese bigrams and term ranking."""
import math
import re
from collections import Counter
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
        rows = conn.execute("SELECT c.id,c.position,c.content,d.title,d.source,d.published_at,d.imported_at FROM knowledge_chunks c JOIN knowledge_documents d ON d.id=c.document_id").fetchall()
    corpus = [tokens(row["title"] + " " + row["content"]) for row in rows]
    counts = Counter(term for terms in corpus for term in terms)
    ranked = []
    for row, terms in zip(rows, corpus):
        overlap = set(query_terms) & set(terms)
        if not overlap:
            continue
        score = sum((1 + math.log(terms[t])) * math.log(1 + len(rows)/(1 + counts[t])) for t in overlap) / math.sqrt(max(1, sum(terms.values())))
        ranked.append({**dict(row), "citation": f"KB-{row['id']}", "score": round(score, 5), "kind": "background_knowledge"})
    return sorted(ranked, key=lambda r: (-r["score"], r["id"]))[:limit]
