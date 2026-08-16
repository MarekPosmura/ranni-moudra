"""Ranní moudra — load the starter library into Supabase.

Reads supabase/seed_insights.json (books + hand-written, paraphrased insights)
and upserts it. Safe to re-run: duplicate books/themes are merged, not doubled.

    python scripts/seed.py
"""
from __future__ import annotations

import json
from pathlib import Path

from lib import db

SEED_FILE = Path(__file__).resolve().parents[1] / "supabase" / "seed_insights.json"


def main() -> None:
    data = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    total = 0
    for book in data["books"]:
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
