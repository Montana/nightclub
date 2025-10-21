#!/usr/bin/env python3

import os
import sys
import argparse
import requests
import csv
import re
from datetime import datetime, timedelta

CLUB_HINTS = [
    r"\bclub\b", r"\bnightclub\b", r"\bdiscotheque\b",
    r"\bwarehouse\b", r"\blounge\b", r"\bbasement\b",
    r"\broom\b", r"\bterrace\b", r"\bbar\b"
]
CLUB_REGEX = re.compile("|".join(CLUB_HINTS), re.IGNORECASE)


def looks_like_club(venue_name: str) -> bool:
    return bool(CLUB_REGEX.search(venue_name or ""))


def tm_events_for_artist(
    artist: str,
    apikey: str,
    country: str | None = None,
    city: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    max_pages: int = 4,
    size: int = 100,
):
    """Generator yielding Ticketmaster events for a given artist."""
    base = "https://app.ticketmaster.com/discovery/v2/events.json"
    params = {
        "apikey": apikey,
        "keyword": artist,
        "classificationName": "Electronic",
        "size": size,
        "sort": "date,asc",
    }
    if country:
        params["countryCode"] = country
    if city:
        params["city"] = city
    if date_from:
        params["startDateTime"] = f"{date_from}T00:00:00Z"
    if date_to:
        params["endDateTime"] = f"{date_to}T23:59:59Z"

    page = 0
    while page < max_pages:
        params["page"] = page
        r = requests.get(base, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()

        events = (data.get("_embedded", {}) or {}).get("events", []) or []
        for ev in events:

            vname, city_str = "", ""
            venues = (ev.get("_embedded", {}) or {}).get("venues", []) or []
            if venues:
                v = venues[0]
                vname = v.get("name", "") or ""
                city_str = ", ".join(filter(None, [
                    (v.get("city") or {}).get("name", ""),
                    (v.get("country") or {}).get("countryCode", "")
                ]))

            lineup = ", ".join([
                a.get("name", "")
                for a in (ev.get("_embedded", {}) or {}).get("attractions", []) or []
            ])

            yield {
                "source": "Ticketmaster",
                "artist": artist,
                "date": (ev.get("dates", {}) or {}).get("start", {}).get("dateTime"),
                "venue": vname,
                "city": city_str,
                "lineup": lineup,
                "url": ev.get("url"),
            }

        pg = (data.get("page") or {})
        total_pages = pg.get("totalPages", 1)
        page += 1
        if page >= total_pages:
            break


def main():
    p = argparse.ArgumentParser(
        description="Ticketmaster-only finder for club nights featuring specific DJs."
    )
    p.add_argument(
        "--artists", nargs="+", required=True,
        help="Artist names (e.g., 'Bontan' 'Eats Everything' 'Joshua Butler')"
    )
    p.add_argument("--from", dest="date_from", default=None,
                   help="Start date YYYY-MM-DD (default: today)")
    p.add_argument("--to", dest="date_to", default=None,
                   help="End date YYYY-MM-DD (default: +90 days)")
    p.add_argument("--country", default=None,
                   help="Optional ISO country code (e.g., US, GB)")
    p.add_argument("--city", default=None,
                   help="Optional city name (e.g., 'Los Angeles')")
    p.add_argument("--csv", default="club_nights_tm.csv",
                   help="Output CSV filename")
    p.add_argument(
        "--no-club-filter", dest="no_club_filter", action="store_true",
        help="Disable nightclub heuristic filter (show all venues)"
    )
    p.add_argument("--max-pages", type=int, default=4,
                   help="Max Ticketmaster pages per artist (default 4)")
    args = p.parse_args()

    today = datetime.utcnow().date()
    date_from = args.date_from or today.isoformat()
    date_to = args.date_to or (today + timedelta(days=90)).isoformat()

    tm_key = os.environ.get("TICKETMASTER_API_KEY")
    if not tm_key:
        print("ERROR: set TICKETMASTER_API_KEY in your environment.", file=sys.stderr)
        sys.exit(1)

    rows = []
    for artist in args.artists:
        try:
            for ev in tm_events_for_artist(
                artist,
                tm_key,
                country=args.country,
                city=args.city,
                date_from=date_from,
                date_to=date_to,
                max_pages=args.max_pages,
            ):
                if args.no_club_filter or looks_like_club(ev["venue"] or ""):
                    rows.append(ev)
        except Exception as e:
            print(f"[Ticketmaster] {artist}: {e}", file=sys.stderr)

    # Sort by ISO dates
    def norm_dt(x):
        try:
            return datetime.fromisoformat((x.get("date") or "").replace("Z", ""))
        except Exception:
            return datetime.max

    rows.sort(key=norm_dt)

    with open(args.csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f, fieldnames=["date", "artist", "venue", "city", "lineup", "url", "source"]
        )
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"Wrote {len(rows)} events to {args.csv}")
    for r in rows:
        print(f"{r['date'] or 'TBA'} | {r['artist']} @ {r['venue']} — {r['city']} | {r['url']}")


if __name__ == "__main__":
    main()
