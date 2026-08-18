"""Ranní moudra — load the starter library into Supabase.

Reads all book files from supabase/seed/*.json (each with the same shape:
{"books": [...]}) and upserts them. If that folder is missing/empty it falls
back to the single supabase/seed_insights.json. Safe to re-run: duplicate
books/themes are merged, not doubled.

    python scripts/seed.py            # upsert everything (keeps existing)
    python scripts/seed.py --fresh    # wipe books/insights/activity first, then load
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from lib import db

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "supabase" / "seed"
SEED_FILE = ROOT / "supabase" / "seed_insights.json"


def load_sources() -> list[dict]:
    """Return a list of {'books': [...]} dicts from the seed folder or file."""
    if SEED_DIR.is_dir():
        files = sorted(SEED_DIR.glob("*.json"))
        if files:
            return [json.loads(f.read_text(encoding="utf-8")) for f in files]
    return [json.loads(SEED_FILE.read_text(encoding="utf-8"))]


def main() -> None:
    parser = argparse.ArgumentParser(description="Nahraj knihovnu myšlenek do Supabase.")
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Napřed smaže všechny knihy/myšlenky/aktivitu, pak nahraje čistě znovu.",
    )
    args = parser.parse_args()

    if args.fresh:
        print("[seed] --fresh: mažu stávající knihy (kaskádově i myšlenky a aktivitu)…")
        db.delete_all("books")

    total = 0
    for source in load_sources():
        for book in source["books"]:
            book_rows = db.upsert(
                "books",
                [{"title": book["title"], "author": book["author"]}],
                on_conflict="title,author",
            )
            if book_rows:
                book_id = book_rows[0]["id"]
            else:
                existing = db.select(
                    "books",
                    {
                        "select": "id",
                        "title": f"eq.{book['title']}",
                        "author": f"eq.{book['author']}",
                    },
                )
                book_id = existing[0]["id"]

            insight_rows = [
                {
                    "book_id": book_id,
                    "theme": ins["theme"],
                    "body": ins["body"],
                    "verified": book.get("verified", False),
                }
                for ins in book["insights"]
            ]
            saved = db.upsert("insights", insight_rows, on_conflict="book_id,theme")
            total += len(saved)
            print(f"[seed] {book['title']}: {len(saved)} myšlenek")

    print(f"[seed] Hotovo. Celkem {total} myšlenek nahráno. ✅")


if __name__ == "__main__":
    main()
