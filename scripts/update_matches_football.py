import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

OUT = Path("matches.json")

COMPETITIONS = [
    # N2 / N3 (tes liens)
    {
        "level": "N2",
        "competition": "National 2 - Poule B",
        "url": "https://epreuves.fff.fr/competition/engagement/439451-n2/phase/1/2/resultats-et-calendrier",
    },
    {
        "level": "N3",
        "competition": "National 3 - Poule E",
        "url": "https://epreuves.fff.fr/competition/engagement/439452-n3/phase/1/5/resultats-et-calendrier",
    },

    # R1 (2 poules)
    {
        "level": "R1",
        "competition": "Seniors Régional 1 - Poule A (HDF)",
        "url": "https://epreuves.fff.fr/competition/engagement/439189-seniors-regional-1/phase/1/1",
    },
    {
        "level": "R1",
        "competition": "Seniors Régional 1 - Poule B (HDF)",
        "url": "https://epreuves.fff.fr/competition/engagement/439189-seniors-regional-1/phase/1/2",
    },

    # R2 (4 poules)
    {
        "level": "R2",
        "competition": "Seniors Régional 2 - Poule A (HDF)",
        "url": "https://epreuves.fff.fr/competition/engagement/439190-seniors-regional-2/phase/1/1",
    },
    {
        "level": "R2",
        "competition": "Seniors Régional 2 - Poule B (HDF)",
        "url": "https://epreuves.fff.fr/competition/engagement/439190-seniors-regional-2/phase/1/2",
    },
    {
        "level": "R2",
        "competition": "Seniors Régional 2 - Poule C (HDF)",
        "url": "https://epreuves.fff.fr/competition/engagement/439190-seniors-regional-2/phase/1/3",
    },
    {
        "level": "R2",
        "competition": "Seniors Régional 2 - Poule D (HDF)",
        "url": "https://epreuves.fff.fr/competition/engagement/439190-seniors-regional-2/phase/1/4",
    },

    # R3 (8 poules)
    {
        "level": "R3",
        "competition": "Seniors Régional 3 - Poule A (HDF)",
        "url": "https://epreuves.fff.fr/competition/engagement/439191-seniors-regional-3/phase/1/1",
    },
    {
        "level": "R3",
        "competition": "Seniors Régional 3 - Poule B (HDF)",
        "url": "https://epreuves.fff.fr/competition/engagement/439191-seniors-regional-3/phase/1/2",
    },
    {
        "level": "R3",
        "competition": "Seniors Régional 3 - Poule C (HDF)",
        "url": "https://epreuves.fff.fr/competition/engagement/439191-seniors-regional-3/phase/1/3",
    },
    {
        "level": "R3",
        "competition": "Seniors Régional 3 - Poule D (HDF)",
        "url": "https://epreuves.fff.fr/competition/engagement/439191-seniors-regional-3/phase/1/4",
    },
    {
        "level": "R3",
        "competition": "Seniors Régional 3 - Poule E (HDF)",
        "url": "https://epreuves.fff.fr/competition/engagement/439191-seniors-regional-3/phase/1/5",
    },
    {
        "level": "R3",
        "competition": "Seniors Régional 3 - Poule F (HDF)",
        "url": "https://epreuves.fff.fr/competition/engagement/439191-seniors-regional-3/phase/1/6",
    },
    {
        "level": "R3",
        "competition": "Seniors Régional 3 - Poule G (HDF)",
        "url": "https://epreuves.fff.fr/competition/engagement/439191-seniors-regional-3/phase/1/7",
    },
    {
        "level": "R3",
        "competition": "Seniors Régional 3 - Poule H (HDF)",
        "url": "https://epreuves.fff.fr/competition/engagement/439191-seniors-regional-3/phase/1/8",
    },
]


LOOKAHEAD_DAYS = 30


def fetch(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.text


def extract_matches(html):
    # Extraction simple équipes/date (MVP)
    matches = []

    pattern = re.findall(r'>([A-Z0-9 \-\'\.]+)\s*-\s*([A-Z0-9 \-\'\.]+)<', html)

    now = datetime.now(timezone.utc)
    for home, away in pattern[:15]:
        matches.append({
            "sport": "football",
            "level": "",
            "starts_at": now.isoformat(),
            "competition": "",
            "home_team": home.title(),
            "away_team": away.title(),
            "venue": {
                "name": "Lieu non récupéré",
                "city": "",
                "lat": 49.8489,
                "lon": 3.2876
            },
            "source_url": ""
        })
    return matches


def main():
    items = []

    for comp in COMPETITIONS:
        html = fetch(comp["url"])
        extracted = extract_matches(html)

        for m in extracted:
            m["level"] = comp["level"]
            m["competition"] = comp["competition"]
            m["source_url"] = comp["url"]
            items.append(m)

    data = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "items": items
    }

    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()

