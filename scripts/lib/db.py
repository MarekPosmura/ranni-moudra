"""Tiny Supabase (PostgREST) client built on `requests`.

We deliberately avoid the heavy supabase-py dependency: a handful of REST
calls with the service_role key is all v1 needs, and it keeps the
Windows / GitHub Actions setup trivial.
"""
from __future__ import annotations

from typing import Any

import requests

from . import config

_REST = f"{config.SUPABASE_URL}/rest/v1"
_HEADERS = {
    "apikey": config.SUPABASE_SERVICE_KEY,
    "Authorization": f"Bearer {config.SUPABASE_SERVICE_KEY}",
    "Content-Type": "application/json",
}
_TIMEOUT = 30


def select(table: str, params: dict[str, Any] | None = None) -> list[dict]:
    """GET rows from a table or view. `params` are PostgREST query params."""
    resp = requests.get(
        f"{_REST}/{table}", headers=_HEADERS, params=params or {}, timeout=_TIMEOUT
    )
    resp.raise_for_status()
    return resp.json()


def insert(table: str, row: dict[str, Any], return_row: bool = False) -> dict | None:
    """Insert a single row. Returns the inserted row if return_row=True."""
    headers = dict(_HEADERS)
    if return_row:
        headers["Prefer"] = "return=representation"
    resp = requests.post(
        f"{_REST}/{table}", headers=headers, json=row, timeout=_TIMEOUT
    )
    resp.raise_for_status()
    if return_row and resp.text:
        data = resp.json()
        return data[0] if data else None
    return None


def delete_all(table: str) -> None:
    """Delete every row in a table (id > 0 matches all). Cascades via FKs."""
    resp = requests.delete(
        f"{_REST}/{table}",
        headers=_HEADERS,
        params={"id": "gt.0"},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()


def upsert(table: str, rows: list[dict[str, Any]], on_conflict: str) -> list[dict]:
    """Upsert rows, ignoring duplicates on the given unique column(s)."""
    headers = dict(_HEADERS)
    headers["Prefer"] = "resolution=merge-duplicates,return=representation"
    resp = requests.post(
        f"{_REST}/{table}",
        headers=headers,
        params={"on_conflict": on_conflict},
        json=rows,
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json() if resp.text else []
