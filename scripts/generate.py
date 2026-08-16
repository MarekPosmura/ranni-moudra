"""Ranní moudra — reusable insight generator.

Give it a book, it asks Claude for N distilled insights (Czech, paraphrased),
and upserts them into Supabase. Duplicate themes are ignored thanks to the
unique(book_id, theme) constraint, so it's safe to re-run.

Examples:
    python scripts/generate.py --book "Atomové návyky" --author "James Clear"
    python scripts/generate.py --book "Proč spíme" --author "Matthew Walker" --count 15 --verified
    python scripts/generate.py --book "..." --author "..." --dry-run   # just print, don't upload

For NEWER books, verify the core idea yourself first, then pass --verified.
This tool never stores verbatim text and is told not to invent page numbers.
"""
from __future__ import annotations

import argparse
import json
import sys

from lib import config, db

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = """\
Jsi editor, který z knih destiluje praktická ranní moudra pro osobní appku.
Piš česky. Dodržuj přísně tato pravidla:

- ŽÁDNÉ doslovné citace z knihy. Vždy parafráze vlastními slovy (kvůli autorským právům).
- Nevymýšlej čísla stránek, kapitol ani konkrétní statistiky, které si nejsi jistý.
  Když to nejde ověřit, neuváděj to.
- Drž se ověřeného jádra myšlenek autora. Nehalucinuj koncepty, které v knize nejsou.
- Tón: srozumitelný, praktický, česky, aplikovatelný v běžném dni. Ne akademicky, ne rozvláčně.
- Každý odstavec ať nese něco použitelného, ne omáčku.
- Každá myšlenka = krátký nadpis tématu (2–5 slov) + 2 až 3 odstavce.
- Témata i myšlenky ať se navzájem NEopakují.

Vrať POUZE validní JSON pole, nic víc, bez markdown bloků. Formát:
[
  {"theme": "Krátký nadpis", "body": "Odstavec 1.\\n\\nOdstavec 2.\\n\\nOdstavec 3."},
  ...
]
Odstavce odděluj dvojitým zalomením řádku (\\n\\n)."""


def build_user_prompt(book: str, author: str, count: int, hint: str | None) -> str:
    prompt = (
        f"Kniha: „{book}“ od {author}.\n"
        f"Vygeneruj {count} různých myšlenek podle pravidel výše."
    )
    if hint:
        prompt += f"\nZaměř se hlavně na tato témata / oblasti: {hint}."
    return prompt


def call_claude(book: str, author: str, count: int, hint: str | None) -> list[dict]:
    try:
        from anthropic import Anthropic
    except ImportError:
        raise SystemExit("Chybí balíček 'anthropic'. Spusť: pip install -r requirements.txt")

    if not config.ANTHROPIC_API_KEY:
        raise SystemExit("Chybí ANTHROPIC_API_KEY (nastav v .env).")

    client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model=MODEL,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_prompt(book, author, count, hint)}],
    )
    text = "".join(block.text for block in message.content if block.type == "text").strip()

    # Be forgiving if the model wraps the JSON in a code fence.
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        text = text.removeprefix("json").strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Model nevrátil validní JSON: {exc}\n---\n{text[:500]}")

    cleaned = []
    for item in data:
        theme = (item.get("theme") or "").strip()
        body = (item.get("body") or "").strip()
        if theme and body:
            cleaned.append({"theme": theme, "body": body})
    return cleaned


def ensure_book(title: str, author: str) -> int:
    rows = db.upsert(
        "books",
        [{"title": title, "author": author}],
        on_conflict="title,author",
    )
    if rows:
        return rows[0]["id"]
    # Already existed and upsert returned nothing — fetch it.
    existing = db.select(
        "books", {"select": "id", "title": f"eq.{title}", "author": f"eq.{author}"}
    )
    return existing[0]["id"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Vygeneruj myšlenky pro jednu knihu.")
    parser.add_argument("--book", required=True, help="Název knihy")
    parser.add_argument("--author", required=True, help="Autor")
    parser.add_argument("--count", type=int, default=12, help="Kolik myšlenek (výchozí 12)")
    parser.add_argument("--hint", default=None, help="Volitelné zaměření témat")
    parser.add_argument(
        "--verified",
        action="store_true",
        help="Označ myšlenky jako ověřené (u novějších knih, kde sis jádro ověřil).",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Jen vypiš, nenahrávej do Supabase."
    )
    args = parser.parse_args()

    print(f"[generate] Volám Claude ({MODEL}) pro „{args.book}“ …")
    insights = call_claude(args.book, args.author, args.count, args.hint)
    print(f"[generate] Vygenerováno {len(insights)} myšlenek.")

    if args.dry_run:
        for i, ins in enumerate(insights, 1):
            print(f"\n--- {i}. {ins['theme']} ---\n{ins['body']}")
        print("\n[generate] --dry-run: nic jsem nenahrál.")
        return

    book_id = ensure_book(args.book, args.author)
    rows = [
        {
            "book_id": book_id,
            "theme": ins["theme"],
            "body": ins["body"],
            "verified": args.verified,
        }
        for ins in insights
    ]
    saved = db.upsert("insights", rows, on_conflict="book_id,theme")
    print(f"[generate] Uloženo/aktualizováno {len(saved)} myšlenek do Supabase. ✅")


if __name__ == "__main__":
    main()
