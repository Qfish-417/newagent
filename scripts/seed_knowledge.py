"""Run from repository root: python -m scripts.seed_knowledge"""
import json
from pathlib import Path
from app.db import initialize, connect
from app.knowledge import add_document


def main():
    initialize()
    items = json.loads((Path(__file__).resolve().parent.parent / "examples/knowledge_seed.json").read_text(encoding="utf-8"))
    added = 0
    for item in items:
        with connect() as conn:
            exists = conn.execute("SELECT id FROM knowledge_documents WHERE source=? AND title=?", (item["source"], item["title"])).fetchone()
        if exists:
            continue
        add_document(**item)
        added += 1
    print(f"Imported {added}; already present {len(items)-added}")

if __name__ == "__main__":
    main()
