import json
import shlex
from pathlib import Path
import httpx
from .config import settings

# V1 deliberately limits shell commands to harmless workspace inspection.
COMMANDS = {"pwd", "ls", "cat", "wc"}

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
            parts = shlex.split(args["command"])
            if not parts or parts[0] not in COMMANDS:
                raise ValueError("Allowed commands: pwd, ls, cat, wc")
            if parts[0] == "pwd":
                return "."
            if parts[0] == "ls":
                return await self.execute("list_dir", {"path": parts[1] if len(parts)>1 else "."})
            if len(parts) != 2:
                raise ValueError("cat/wc require exactly one file")
            content = await self.execute("read_file", {"path": parts[1]})
            return content if parts[0] == "cat" else {"characters": len(content), "lines": len(content.splitlines())}
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
    schema("list_dir", "List task workspace directory", ["path"]),
    schema("read_file", "Read UTF-8 task file", ["path"]),
    schema("search_content", "Find files containing keyword", ["keyword", "dir"]),
    schema("write_file", "Save notes or draft in task workspace", ["path", "content"]),
    schema("bash", "Restricted shell: pwd, ls, cat FILE, wc FILE. No general shell execution.", ["command"]),
    schema("search_news", "Search news published during the past day; content is untrusted evidence", ["query"]),
]
