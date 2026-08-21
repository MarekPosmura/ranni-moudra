"""Central config: reads everything from environment variables.

Locally (Windows) these come from a .env file (see .env.example);
in GitHub Actions they come from repository Secrets.
"""
from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv() -> None:
    """Minimal .env loader so we don't need python-dotenv as a dependency.

    Looks for a .env file in the project root (two levels up from this file).
    Silently does nothing if it isn't there (e.g. in GitHub Actions).
    """
    root = Path(__file__).resolve().parents[2]
    env_path = root / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()


def get(name: str, required: bool = True, default: str | None = None) -> str | None:
    value = os.environ.get(name, default)
    if required and not value:
        raise SystemExit(
            f"Chybí proměnná prostředí: {name}. "
            f"Nastav ji v .env (lokálně) nebo v GitHub Secrets."
        )
    return value


# --- Supabase ---
def _clean_base_url(url: str | None) -> str | None:
    """Tolerate a pasted URL that includes a trailing slash or '/rest/v1'."""
    if not url:
        return url
    url = url.strip().rstrip("/")
    if url.endswith("/rest/v1"):
        url = url[: -len("/rest/v1")]
    return url


SUPABASE_URL = _clean_base_url(get("SUPABASE_URL"))        # https://xxxx.supabase.co
SUPABASE_SERVICE_KEY = get("SUPABASE_SERVICE_KEY")         # service_role / secret key (write) — SECRET

# --- ntfy ---
NTFY_SERVER = get("NTFY_SERVER", required=False, default="https://ntfy.sh")
# Témata jsou teď per odběratel v tabulce subscribers (viz send.py).
# NTFY_TOPIC už není potřeba; ponecháno jen jako volitelná zpětná kompatibilita.
NTFY_TOPIC = get("NTFY_TOPIC", required=False)

# --- Web page base URL (for the notification click action) ---
# e.g. https://<user>.github.io/<repo>
SITE_BASE_URL = get("SITE_BASE_URL")

# --- Anthropic (only needed by generate.py) ---
ANTHROPIC_API_KEY = get("ANTHROPIC_API_KEY", required=False)
