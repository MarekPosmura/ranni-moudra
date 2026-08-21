"""Ranní moudra — send one insight per subscriber as an ntfy push.

Flow (pro KAŽDÉHO aktivního odběratele zvlášť):
  1. Work out whether *now* (Europe/Prague) falls in the morning or the
     afternoon slot. If not, exit quietly (GitHub cron runs in UTC and
     fires several times to cover DST — only the right one sends).
  2. Guard against double-sends within the same slot today (per odběratel).
  3. Pick a not-yet-sent insight from that person's book list, avoiding
     the book sent last time.
  4. Record it in `activity` (s subscriber_id) and push it via ntfy on
     that person's own topic (silent, low priority).

Každý odběratel má vlastní ntfy_topic a může mít vyloučené kategorie knih
(sloupec subscribers.excluded_categories) — to řeší pohled v_unsent_insights.

Run manually to test:
  python scripts/send.py --force              # pošle všem
  python scripts/send.py --force --user marek # jen jednomu (podle slug)
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from lib import config, db

PRAGUE = ZoneInfo("Europe/Prague")

# Target hour + tolerance window (Prague local, 24h). The window start must
# stay above the *earlier* Prague time of each DST cron pair so the wrong one
# is skipped; late cron delays are absorbed up to the window end, and the
# same-slot guard stops the paired cron from sending twice.
SLOTS = {
    "morning":   {"target": 6,  "window": (6, 10)},
    "afternoon": {"target": 16, "window": (16, 20)},
}

TEASER_LEN = 120


def current_slot(now: datetime) -> str | None:
    hour = now.hour
    for name, cfg in SLOTS.items():
        start, end = cfg["window"]
        if start <= hour < end:
            return name
    return None


def subscribers() -> list[dict]:
    """Aktivní odběratelé s jejich ntfy tématem."""
    return db.select(
        "subscribers",
        {"select": "id,slug,name,ntfy_topic", "active": "eq.true", "order": "id.asc"},
    )


def already_sent_in_slot(now: datetime, slot: str, subscriber_id: int) -> bool:
    """True if a push already went out inside today's slot window for this person.

    We filter the start + subscriber in the query and check the window end
    in Python.
    """
    start_h, end_h = SLOTS[slot]["window"]
    day = now.date()
    win_start = datetime(day.year, day.month, day.day, start_h, tzinfo=PRAGUE)
    win_end = datetime(day.year, day.month, day.day, end_h, tzinfo=PRAGUE)
    rows = db.select(
        "activity",
        {
            "select": "sent_at",
            "channel": "eq.push",
            "subscriber_id": f"eq.{subscriber_id}",
            "sent_at": f"gte.{win_start.isoformat()}",
            "order": "sent_at.desc",
            "limit": "20",
        },
    )
    for row in rows:
        sent_at = datetime.fromisoformat(row["sent_at"])
        if sent_at < win_end:
            return True
    return False


def last_sent_book_id(subscriber_id: int) -> int | None:
    rows = db.select(
        "activity",
        {
            "select": "insight_id,insights(book_id)",
            "subscriber_id": f"eq.{subscriber_id}",
            "order": "sent_at.desc",
            "limit": "1",
        },
    )
    if not rows:
        return None
    joined = rows[0].get("insights")
    if isinstance(joined, dict):
        return joined.get("book_id")
    return None


def pick_insight(subscriber_id: int) -> dict | None:
    """Random unsent insight for this person, avoiding the last book."""
    unsent = db.select(
        "v_unsent_insights",
        {"select": "*", "subscriber_id": f"eq.{subscriber_id}"},
    )
    if not unsent:
        return None

    last_book = last_sent_book_id(subscriber_id)
    pool = [row for row in unsent if row["book_id"] != last_book]
    if not pool:  # only the last book has anything left — allow it
        pool = unsent
    return random.choice(pool)


def make_teaser(body: str) -> str:
    text = " ".join(body.split())  # collapse newlines/whitespace
    if len(text) <= TEASER_LEN:
        return text
    return text[:TEASER_LEN].rstrip() + "…"


def send_push(insight: dict, topic: str) -> None:
    title = f"📖 {insight['book_title']} — {insight['theme']}"
    teaser = make_teaser(insight["body"])
    click_url = f"{config.SITE_BASE_URL.rstrip('/')}/?id={insight['insight_id']}"

    payload = {
        "topic": topic,
        "title": title,
        "message": teaser,
        "click": click_url,
        "priority": 2,          # low = shows silently, no sound/vibration
        "tags": ["book"],
    }
    resp = requests.post(config.NTFY_SERVER, json=payload, timeout=30)
    resp.raise_for_status()


def process_subscriber(sub: dict, now: datetime, slot: str | None, force: bool) -> None:
    label = f"{sub['name']} ({sub['slug']})"

    if not force and slot is not None and already_sent_in_slot(now, slot, sub["id"]):
        print(f"[send] {label}: slot '{slot}' už dnes odešel — přeskakuji.")
        return

    insight = pick_insight(sub["id"])
    if insight is None:
        print(f"[send] {label}: žádné neposlané myšlenky nezbývají. Vygeneruj další (generate.py).")
        return

    channel = "manual" if force else "push"
    db.insert(
        "activity",
        {"insight_id": insight["insight_id"], "subscriber_id": sub["id"], "channel": channel},
    )
    print(
        f"[send] {label}: vybráno '{insight['book_title']} — {insight['theme']}' "
        f"(insight_id={insight['insight_id']}, slot={slot or 'manual'})"
    )
    send_push(insight, sub["ntfy_topic"])
    print(f"[send] {label}: notifikace odeslána přes ntfy. ✅")


def main() -> None:
    parser = argparse.ArgumentParser(description="Send one Ranní moudro push per subscriber.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore the time window and the same-slot guard (for manual testing).",
    )
    parser.add_argument(
        "--user",
        metavar="SLUG",
        help="Pošli jen jednomu odběrateli podle slug (např. marek). Výchozí: všem.",
    )
    args = parser.parse_args()

    now = datetime.now(PRAGUE)
    print(f"[send] Prague time: {now.isoformat()}")

    slot = current_slot(now)
    if not args.force:
        if slot is None:
            print("[send] Mimo ranní/odpolední okno — nic neposílám.")
            return
    else:
        print("[send] --force: ignoruji časové okno i pojistku.")

    subs = subscribers()
    if args.user:
        subs = [s for s in subs if s["slug"] == args.user]
        if not subs:
            print(f"[send] Odběratel se slug '{args.user}' neexistuje (nebo je neaktivní).")
            return
    if not subs:
        print("[send] Žádní aktivní odběratelé. Přidej je do tabulky subscribers.")
        return

    for sub in subs:
        process_subscriber(sub, now, slot, args.force)


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as exc:
        print(f"[send] HTTP chyba: {exc}\n{getattr(exc.response, 'text', '')}", file=sys.stderr)
        sys.exit(1)
