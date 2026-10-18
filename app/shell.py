"""Real Bash execution with a small allowlist and task-directory boundary."""
import os
import shlex
import shutil
import subprocess
from pathlib import Path

ALLOWED = {"pwd", "ls", "cat", "wc"}


def bash_path():
    if os.name == "nt":
        # Do not select Windows' legacy WSL bash.exe shim.
        candidates = [Path(os.environ.get("ProgramFiles", "C:/Program Files"))/"Git/bin/bash.exe",
                      Path(os.environ.get("LOCALAPPDATA", ""))/"Programs/Git/bin/bash.exe"]
        git = shutil.which("git")
        if git:
            candidates.append(Path(git).resolve().parent.parent/"bin/bash.exe")
        for path in candidates:
            if path.is_file():
                return str(path)
        raise ValueError("Install Git for Windows with Bash to use bash(command)")
    result = shutil.which("bash")
    if not result:
        raise ValueError("Bash is required for bash(command)")
    return result


def execute_bash(root, command):
    if not isinstance(command, str) or len(command) > 2000:
        raise ValueError("Invalid shell command")
    parts = shlex.split(command)
    if not parts or parts[0] not in ALLOWED:
        raise ValueError("Allowed shell commands: pwd, ls [DIR], cat FILE, wc FILE")
    name = parts[0]
    if name == "pwd":
        if len(parts) != 1:
            raise ValueError("pwd takes no arguments")
        script = "pwd"
    else:
        if name == "ls" and len(parts) == 1:
            parts.append(".")
        if len(parts) != 2:
            raise ValueError("Exactly one file/directory argument is required; pipelines and chaining are not allowed")
        target = (root/parts[1]).resolve()
        if not target.is_relative_to(root):
            raise ValueError("Path outside task workspace")
        if not target.exists():
            raise ValueError("File/directory does not exist")
        if name == "ls" and not target.is_dir():
            raise ValueError("ls requires a directory")
        if name in {"cat", "wc"} and (not target.is_file() or target.stat().st_size > 100000):
            raise ValueError("Expected file of at most 100000 bytes")
        # Reconstruct a quoted command from validated tokens, never execute raw model text.
        relative = "./" + target.relative_to(root).as_posix()
        script = name + " -- " + shlex.quote(relative)
    executable = bash_path()
    utility_dir = str(Path(executable).parent.parent/"usr/bin") if os.name == "nt" else "/usr/bin:/bin"
    env = {"PATH": utility_dir, "HOME": str(root), "LANG": "C.UTF-8", "LC_ALL":"C.UTF-8"}
    for key in ("SYSTEMROOT", "WINDIR", "TEMP", "TMP"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    try:
        result = subprocess.run([executable,"--noprofile","--norc","-c",script], cwd=root,
            env=env, capture_output=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    except subprocess.TimeoutExpired:
        raise ValueError("Shell command timed out after 5 seconds") from None
    return {"exit_code":result.returncode,"stdout":result.stdout.decode("utf-8",errors="replace")[:20000],
            "stderr":result.stderr.decode("utf-8",errors="replace")[:2000],"shell":"bash"}
