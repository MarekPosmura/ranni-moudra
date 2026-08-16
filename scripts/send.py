"""Ranní moudra — send one insight as an ntfy push notification.

Flow:
  1. Work out whether *now* (Europe/Prague) falls in the morning or the
     afternoon slot. If not, exit quietly (GitHub cron runs in UTC and
     fires several times to cover DST — only the right one sends).
  2. Guard against double-sends within the same slot today.
  3. Pick a not-yet-sent insight, avoiding the book sent last time.
  4. Record it in `activity` and push it via ntfy (silent, low priority).

Run manually to test:  python scripts/send.py --force
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


def already_sent_in_slot(now: datetime, slot: str) -> bool:
    """True if a push already went out inside today's slot window.

    We filter the start in the query (single filter — safe to URL-encode)
    and check the window end in Python.
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


def last_sent_book_id() -> int | None:
    rows = db.select(
        "activity",
        {
            "select": "insight_id,insights(book_id)",
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


def pick_insight() -> dict | None:
    """Random unsent insight, avoiding the book we sent last time."""
    unsent = db.select("v_unsent_insights", {"select": "*"})
    if not unsent:
        return None

    last_book = last_sent_book_id()
    pool = [row for row in unsent if row["book_id"] != last_book]
    if not pool:  # only the last book has anything left — allow it
        pool = unsent
    return random.choice(pool)


def make_teaser(body: str) -> str:
    text = " ".join(body.split())  # collapse newlines/whitespace
    if len(text) <= TEASER_LEN:
        return text
    return text[:TEASER_LEN].rstrip() + "…"


def send_push(insight: dict) -> None:
    title = f"📖 {insight['book_title']} — {insight['theme']}"
    teaser = make_teaser(insight["body"])
    click_url = f"{config.SITE_BASE_URL.rstrip('/')}/?id={insight['insight_id']}"

    payload = {
        "topic": config.NTFY_TOPIC,
        "title": title,
        "message": teaser,
        "click": click_url,
        "priority": 2,          # low = shows silently, no sound/vibration
        "tags": ["book"],
    }
    resp = requests.post(config.NTFY_SERVER, json=payload, timeout=30)
    resp.raise_for_status()


def main() -> None:
    parser = argparse.ArgumentParser(description="Send one Ranní moudro push.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Ignore the time window and the same-slot guard (for manual testing).",
    )
    args = parser.parse_args()

    now = datetime.now(PRAGUE)
    print(f"[send] Prague time: {now.isoformat()}")

    slot = current_slot(now)
    if not args.force:
        if slot is None:
            print("[send] Mimo ranní/odpolední okno — nic neposílám.")
            return
        if already_sent_in_slot(now, slot):
            print(f"[send] Slot '{slot}' už dnes odešel — přeskakuji (DST/dvojitý cron).")
            return
    else:
        slot = slot or "manual"
        print("[send] --force: ignoruji časové okno i pojistku.")

    insight = pick_insight()
    if insight is None:
        print("[send] Žádné neposlané myšlenky nezbývají. Vygeneruj další (generate.py).")
        return

    channel = "manual" if args.force else "push"
    db.insert("activity", {"insight_id": insight["insight_id"], "channel": channel})
    print(
        f"[send] Vybráno: '{insight['book_title']} — {insight['theme']}' "
        f"(insight_id={insight['insight_id']}, slot={slot})"
    )

    send_push(insight)
    print("[send] Notifikace odeslána přes ntfy. ✅")


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as exc:
        print(f"[send] HTTP chyba: {exc}\n{getattr(exc.response, 'text', '')}", file=sys.stderr)
        sys.exit(1)
