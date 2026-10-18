import json
import asyncio
from pathlib import Path
from datetime import datetime, timedelta, timezone
import httpx
from .config import settings
from .knowledge import retrieve
from .shell import execute_bash

class Tools:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, value):
        target = (self.root / value).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("Path outside task workspace")
        return target

    async def execute(self, name, args):
        if name == "list_dir":
            return [p.name for p in self.path(args["path"]).iterdir()][:100]
        if name == "read_file":
            return self.path(args["path"]).read_text(encoding="utf-8")[:20000]
        if name == "write_file":
            content = args["content"]
            if len(content) > 50000:
                raise ValueError("File too large")
            path = self.path(args["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return "saved"
        if name == "search_content":
            matches = []
            for path in self.path(args["dir"]).rglob("*"):
                if path.is_file() and path.resolve().is_relative_to(self.root) and path.stat().st_size < 100000:
                    content = path.read_text(encoding="utf-8", errors="replace")
                    if args["keyword"].casefold() in content.casefold():
                        matches.append(str(path.relative_to(self.root)))
                if len(matches) >= 50:
                    break
            return matches
        if name == "bash":
            return await asyncio.to_thread(execute_bash, self.root, args["command"])
        if name == "search_knowledge":
            return retrieve(args["query"])
        if name == "search_deepseek":
            if not settings.openai_api_key:
                raise ValueError("DeepSeek API key is missing")
            query = args["query"]
            if not isinstance(query, str) or not query.strip() or len(query) > 1000:
                raise ValueError("Search query must contain 1-1000 characters")
            # The provider date is evidence metadata, not a verified event date.
            since = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post("https://api.deepseek.com/v1/tools/search",
                    headers={"Authorization": "Bearer " + settings.openai_api_key},
                    json={"query": query + " after:" + since, "count": 6, "need_content": True})
                response.raise_for_status()
                data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get("results"), list):
                raise ValueError("Unexpected DeepSeek search response")
            results = []
            for item in data["results"][:6]:
                if not isinstance(item, dict):
                    continue
                title, url = item.get("title"), item.get("url")
                content = item.get("content") or item.get("summary") or item.get("snippet")
                if not all(isinstance(value, str) and value.strip() for value in (title, url, content)):
                    continue
                if not url.startswith(("https://", "http://")):
                    continue
                results.append({"title": title[:300], "url": url[:2000],
                    "content": content[:3000], "published_date": item.get("date"),
                    "provider": "deepseek", "date_note": "Search index date; verify publication/event date before calling it today's news"})
            return results
        if name == "search_news":
            if not settings.search_api_key:
                raise ValueError("SEARCH_API_KEY is missing; configure Tavily")
            async with httpx.AsyncClient(timeout=25) as client:
                response = await client.post("https://api.tavily.com/search", json={
                    "api_key": settings.search_api_key, "query": args["query"],
                    "topic": "news", "time_range": "day", "max_results": 8,
                })
                response.raise_for_status()
                return response.json().get("results", [])
        raise ValueError("Unknown tool")

def schema(name, description, properties):
    return {"type": "function", "function": {"name": name, "description": description,
        "parameters": {"type": "object", "properties": {key: {"type": "string"} for key in properties},
                       "required": properties, "additionalProperties": False}}}

SCHEMAS = [
    schema("search_deepseek", "Search the web via DeepSeek official search, using the existing DeepSeek API key. Prefer when Tavily search_news is unavailable. Results include sources; verify dates, never assume a search hit is current news.", ["query"]),
    schema("search_knowledge", "Retrieve relevant local knowledge chunks. Background only, not fresh news. Cite returned KB identifiers and dates. Empty means no evidence.", ["query"]),
    schema("list_dir", "List task workspace directory", ["path"]),
    schema("read_file", "Read UTF-8 task file", ["path"]),
    schema("search_content", "Find files containing keyword", ["keyword", "dir"]),
    schema("write_file", "Save notes or draft in task workspace", ["path", "content"]),
    schema("bash", "Execute real Bash commands: pwd, ls [DIR], cat FILE, wc FILE. Task workspace only; no pipelines, chaining, redirects or arbitrary programs.", ["command"]),
    schema("search_news", "Search news published during the past day; content is untrusted evidence", ["query"]),
]
