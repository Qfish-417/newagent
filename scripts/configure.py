"""Interactive local .env configuration. Never prints or transmits keys."""
import getpass
import os
from pathlib import Path
from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parent.parent


def ask(label, default):
    result = input(f"{label} [{default}]: ").strip()
    return result or default


def main():
    path = ROOT / ".env"
    current = dotenv_values(path) if path.exists() else {}
    print("\nnewagent configuration wizard")
    print("Only DEEPSEEK_API_KEY is required. All other settings are optional; press Enter to keep defaults.")
    print("Secrets are hidden while typing. Configuration stays in local .env (ignored by Git).")
    print("System environment variables take priority over .env. This wizard does not change system settings.")
    existing = bool(os.getenv("DEEPSEEK_API_KEY") or current.get("DEEPSEEK_API_KEY"))
    key = getpass.getpass("DeepSeek API key (hidden; Enter keeps existing key): ").strip()
    if not key and not existing:
        raise SystemExit("DEEPSEEK_API_KEY is required. Run the wizard again or set the environment variable.")
    values = {}
    if key:
        values["DEEPSEEK_API_KEY"] = key
        if os.getenv("DEEPSEEK_API_KEY"):
            print("An existing system DeepSeek key is active. The entered key is saved locally; system key still takes priority.")
    advanced = input("Configure optional model/search/data settings? [y/N]: ").strip().lower() == "y"
    if advanced:
        for name, default in [("DEEPSEEK_MODEL","deepseek-chat"),("DEEPSEEK_BASE_URL","https://api.deepseek.com"),("DATA_DIR","data"),("MAX_ROUNDS","12")]:
            values[name] = ask(name, os.getenv(name) or current.get(name) or default)
        if not values["MAX_ROUNDS"].isdigit() or not 1 <= int(values["MAX_ROUNDS"]) <= 100:
            raise SystemExit("MAX_ROUNDS must be between 1 and 100. No changes saved.")
        if not values["DEEPSEEK_BASE_URL"].startswith(("http://","https://")):
            raise SystemExit("DEEPSEEK_BASE_URL must start with http:// or https://. No changes saved.")
        optional_key = getpass.getpass("Optional Tavily SEARCH_API_KEY (hidden; Enter keeps existing / not configured): ").strip()
        if optional_key:
            values["SEARCH_API_KEY"] = optional_key
    if any("\n" in v or "\r" in v for v in values.values()):
        raise SystemExit("Multiline configuration is not supported. No changes saved.")
    for name, value in values.items():
        set_key(str(path), name, value, quote_mode="always", encoding="utf-8")
    print("Configuration saved locally. No API keys are displayed. Starting checks next.\n")

if __name__ == "__main__":
    main()
