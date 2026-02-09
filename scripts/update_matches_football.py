import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

OUT = Path("matches.json")

COMPETITIONS = [
    {
        "level": "N2",
        "competition": "National 2 - Poule B",
        "url": "https://epreuves.fff.fr/competition/engagement/439451-n2/phase/1/2/resultats-et-calendrier"
    },
    {
        "level": "N3",
        "competition": "National 3 - Poule E",
        "url": "https://epreuves.fff.fr/competition/engagement/439452-n3/phase/1/5/resultats-et-calendrier"
    }
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

