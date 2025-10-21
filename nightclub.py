#!/usr/bin/env python3
import os, sys, argparse, requests, csv, re
from datetime import datetime, timedelta

CLUB_HINTS = [
    r"\bclub\b", r"\bnightclub\b", r"\bdiscotheque\b",
    r"\bwarehouse\b", r"\blounge\b", r"\broom\b", r"\bbar\b",
    r"\bside room\b", r"\bterrace\b", r"\bbasement\b"
]
CLUB_REGEX = re.compile("|".join(CLUB_HINTS), re.IGNORECASE)

def looks_like_club(venue_name: str) -> bool:
    return bool(CLUB_REGEX.search(venue_name or ""))

def bandsintown_events(artist: str, app_id: str, start_date=None, end_date=None):
    # Docs: https://help.artists.bandsintown.com/en/articles/9186477-api-documentation
    url = f"https://rest.bandsintown.com/artists/{requests.utils.quote(artist)}/events"
    params = {"app_id": app_id}
    if start_date and end_date:
        params["date"] = f"{start_date},{end_date}"
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json() if r.text.strip().startswith("[") else []
    for ev in data:
        yield {
            "source": "Bandsintown",
            "artist": artist,
            "date": ev.get("datetime"),
            "venue": (ev.get("venue") or {}).get("name"),
            "city": f"{(ev.get('venue') or {}).get('city', '')}, {(ev.get('venue') or {}).get('country', '')}".strip(", "),
            "lineup": ", ".join(ev.get("lineup") or []),
            "url": ev.get("url"),
        }

def ticketmaster_events(query: str, apikey: str, country_code=None, start_date=None, end_date=None):
    # Docs: https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/
    url = "https://app.ticketmaster.com/discovery/v2/events.json"
    params = {
        "apikey": apikey,
        "keyword": query,
        "classificationName": "Electronic",
        "size": 100
    }
    if country_code:
        params["countryCode"] = country_code
    if start_date:
        params["startDateTime"] = start_date + "T00:00:00Z"
    if end_date:
        params["endDateTime"] = end_date + "T23:59:59Z"
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()
    for ev in (data.get("_embedded", {}).get("events", []) or []):
        venue = ""
        if ev.get("_embedded", {}).get("venues"):
            v = ev["_embedded"]["venues"][0]
            venue = v.get("name")
            city = f"{(v.get('city') or {}).get('name','')}, {(v.get('country') or {}).get('countryCode','')}".strip(", ")
        else:
            city = ""
        lineup = ", ".join([a.get("name","") for a in ev.get("_embedded", {}).get("attractions", []) or []])
        yield {
            "source": "Ticketmaster",
            "artist": query,
            "date": ev.get("dates", {}).get("start", {}).get("dateTime"),
            "venue": venue,
            "city": city,
            "lineup": lineup,
            "url": ev.get("url"),
        }

def main():
    p = argparse.ArgumentParser(description="Find nightclub shows for specified DJs.")
    p.add_argument("--artists", nargs="+", required=True, help="Artist names (e.g., Bontan 'Eats Everything' 'Joshua Butler')")
    p.add_argument("--from", dest="date_from", default=None, help="Start date YYYY-MM-DD (default: today)")
    p.add_argument("--to", dest="date_to", default=None, help="End date YYYY-MM-DD (default: +90 days)")
    p.add_argument("--country", default=None, help="Optional ISO country code for Ticketmaster (e.g., US, GB)")
    p.add_argument("--csv", default="club_nights.csv", help="Output CSV filename")
    p.add_argument("--include-ticketmaster", action="store_true", help="Also query Ticketmaster Discovery API")
    args = p.parse_args()

    # Dates
    today = datetime.utcnow().date()
    date_from = args.date_from or today.isoformat()
    date_to = args.date_to or (today + timedelta(days=90)).isoformat()

    app_id = os.environ.get("BANDSINTOWN_APP_ID")
    if not app_id:
        print("ERROR: set BANDSINTOWN_APP_ID in your environment.", file=sys.stderr)
        sys.exit(1)

    tm_key = os.environ.get("TICKETMASTER_API_KEY")

    rows = []
    # Bandsintown for exact artist matches
    for artist in args.artists:
        try:
            for ev in bandsintown_events(artist, app_id, start_date=date_from, end_date=date_to):
                if looks_like_club(ev["venue"] or ""):
                    rows.append(ev)
        except Exception as e:
            print(f"[Bandsintown] {artist}: {e}", file=sys.stderr)

    # Optional: Ticketmaster for extra coverage
    if args.include_ticketmaster:
        if not tm_key:
            print("WARN: --include-ticketmaster used but TICKETMASTER_API_KEY not set; skipping TM.", file=sys.stderr)
        else:
            for artist in args.artists:
                try:
                    for ev in ticketmaster_events(artist, tm_key, country_code=args.country, start_date=date_from, end_date=date_to):
                        if looks_like_club(ev["venue"] or ""):
                            rows.append(ev)
                except Exception as e:
                    print(f"[Ticketmaster] {artist}: {e}", file=sys.stderr)

    # Sort by date
    def norm_dt(x):
        try:
            return datetime.fromisoformat((x.get("date") or "").replace("Z",""))
        except Exception:
            return datetime.max
    rows.sort(key=norm_dt)

    # Write CSV
    with open(args.csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date","artist","venue","city","lineup","url","source"])
        w.writeheader()
        for r in rows:
            w.writerow(r)

    print(f"Wrote {len(rows)} events to {args.csv}")
    # Pretty print to stdout too
    for r in rows:
        print(f"{r['date'] or 'TBA'} | {r['artist']} @ {r['venue']} — {r['city']} | {r['url']}")

if __name__ == "__main__":
    main()
