"""Local operator commands. Never exposed as HTTP routes."""
import argparse
import json
from datetime import date
from pathlib import Path
from app.db import initialize, connect
from app.knowledge import add_document, retrieve


def show_document(document_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM knowledge_documents WHERE id=?", (document_id,)).fetchone()
        if not row:
            raise ValueError("Document not found")
        chunks = conn.execute("SELECT content FROM knowledge_chunks WHERE document_id=? ORDER BY position", (document_id,)).fetchall()
    content = "" if not chunks else chunks[0][0] + "".join(c[0][150:] for c in chunks[1:])
    return {**dict(row), "content": content}


def import_file(path):
    items = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise ValueError("Expected JSON array")
    # Validate the entire input before inserting documents.
    for item in items:
        for key, limit in [("title",200), ("source",500), ("content",50000)]:
            value = item.get(key)
            if not isinstance(value,str) or not value.strip() or len(value)>limit:
                raise ValueError("Invalid field: " + key)
        if item.get("published_at"):
            date.fromisoformat(item["published_at"])
    added = 0
    for item in items:
        with connect() as conn:
            exists = conn.execute("SELECT id FROM knowledge_documents WHERE title=? AND source=?", (item["title"],item["source"])).fetchone()
        if not exists:
            add_document(item["title"],item["content"],item["source"],item.get("published_at"))
            added += 1
    return {"added": added, "skipped": len(items)-added}


def main():
    parser = argparse.ArgumentParser(description="Local knowledge administration")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    commands.add_parser("import").add_argument("path")
    commands.add_parser("show").add_argument("id", type=int)
    commands.add_parser("search").add_argument("query")
    args = parser.parse_args()
    initialize()
    if args.command == "import":
        result = import_file(args.path)
    elif args.command == "show":
        result = show_document(args.id)
    elif args.command == "search":
        result = retrieve(args.query)
    else:
        with connect() as conn:
            result = [dict(r) for r in conn.execute("SELECT * FROM knowledge_documents ORDER BY id DESC")]
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
