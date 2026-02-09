import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

PARIS = ZoneInfo("Europe/Paris")
UTC = ZoneInfo("UTC")

OUT = Path("matches.json")

COMPETITIONS = [
    {"level": "N2", "competition": "National 2 - Poule B", "calendar_url": "https://epreuves.fff.fr/competition/engagement/439451-n2/phase/1/2/resultats-et-calendrier"},
    {"level": "N3", "competition": "National 3 - Poule E", "calendar_url": "https://epreuves.fff.fr/competition/engagement/439452-n3/phase/1/5/resultats-et-calendrier"},
    {"level": "R1", "competition": "R1 - Poule A", "calendar_url": "https://epreuves.fff.fr/competition/engagement/439189-seniors-regional-1/phase/1/1"},
    {"level": "R1", "competition": "R1 - Poule B", "calendar_url": "https://epreuves.fff.fr/competition/engagement/439189-seniors-regional-1/phase/1/2"},
    {"level": "R2", "competition": "R2 - Poule A", "calendar_url": "https://epreuves.fff.fr/competition/engagement/439190-seniors-regional-2/phase/1/1"},
    {"level": "R2", "competition": "R2 - Poule B", "calendar_url": "https://epreuves.fff.fr/competition/engagement/439190-seniors-regional-2/phase/1/2"},
    {"level": "R2", "competition": "R2 - Poule C", "calendar_url": "https://epreuves.fff.fr/competition/engagement/439190-seniors-regional-2/phase/1/3"},
    {"level": "R2", "competition": "R2 - Poule D", "calendar_url": "https://epreuves.fff.fr/competition/engagement/439190-seniors-regional-2/phase/1/4"},
    {"level": "R3", "competition": "R3 - Poule A", "calendar_url": "https://epreuves.fff.fr/competition/engagement/439191-seniors-regional-3/phase/1/1"},
    {"level": "R3", "competition": "R3 - Poule B", "competition": "R3 - Poule B", "calendar_url": "https://epreuves.fff.fr/competition/engagement/439191-seniors-regional-3/phase/1/2"},
    {"level": "R3", "competition": "R3 - Poule C", "calendar_url": "https://epreuves.fff.fr/competition/engagement/439191-seniors-regional-3/phase/1/3"},
    {"level": "R3", "competition": "R3 - Poule D", "calendar_url": "https://epreuves.fff.fr/competition/engagement/439191-seniors-regional-3/phase/1/4"},
    {"level": "R3", "competition": "R3 - Poule E", "calendar_url": "https://epreuves.fff.fr/competition/engagement/439191-seniors-regional-3/phase/1/5"},
    {"level": "R3", "competition": "R3 - Poule F", "calendar_url": "https://epreuves.fff.fr/competition/engagement/439191-seniors-regional-3/phase/1/6"},
    {"level": "R3", "competition": "R3 - Poule G", "calendar_url": "https://epreuves.fff.fr/competition/engagement/439191-seniors-regional-3/phase/1/7"},
    {"level": "R3", "competition": "R3 - Poule H", "calendar_url": "https://epreuves.fff.fr/competition/engagement/439191-seniors-regional-3/phase/1/8"},
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "match-radar-hdf (github actions)"
})

MONTHS = {
    "janv": 1, "févr": 2, "fevr": 2, "mars": 3, "avr": 4, "mai": 5, "juin": 6,
    "juil": 7, "aoû": 8, "aou": 8, "sept": 9, "oct": 10, "nov": 11, "déc": 12, "dec": 12
}

DATE_RE = re.compile(
    r"^(lun|mar|mer|jeu|ven|sam|dim)\s+(\d{1,2})\s+([a-zéûôîàç\.]+)\s+(\d{4})\s+-\s+(\d{1,2})h(\d{2})$",
    re.IGNORECASE
)

# 👉 On récupère les équipes via les liens "equipe"
TEAM_ANCHOR_RE = re.compile(
    r'href="[^"]*/competition/equipe/[^"]*"[^>]*>\s*([^<]{2,80}?)\s*</a>',
    re.IGNORECASE
)

def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default

def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def fetch(url: str) -> str:
    r = SESSION.get(url, timeout=30)
    r.raise_for_status()
    return r.text

def parse_fr_datetime(s: str) -> datetime | None:
    s = re.sub(r"\s+", " ", s.strip().lower())
    s = s.replace("févr.", "févr").replace("janv.", "janv").replace("sept.", "sept").replace("déc.", "déc")
    s = s.replace("août", "aoû")
    m = DATE_RE.match(s)
    if not m:
        return None
    day = int(m.group(2))
    mon_txt = m.group(3).strip(".")
    year = int(m.group(4))
    hh = int(m.group(5))
    mm = int(m.group(6))
    mon = MONTHS.get(mon_txt)
    if not mon:
        return None
    return datetime(year, mon, day, hh, mm, tzinfo=PARIS)

def weekend_window_for(dt: datetime) -> tuple[datetime, datetime]:
    # samedi 00:00 -> dimanche 23:59:59
    saturday = dt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=(dt.weekday() - 5) % 7)
    sunday_end = saturday + timedelta(days=1, hours=23, minutes=59, seconds=59)
    return saturday, sunday_end

def extract_matches_from_calendar(html: str) -> list[tuple[datetime, str, str]]:
    """
    On parse la page calendrier :
    - on récupère toutes les dates/heure "sam 07 fév 2026 - 18h00"
    - juste après, dans le flux HTML, on récupère les 2 prochains noms d'équipe (domicile/extérieur)
    """
    matches = []

    # 1) On transforme le HTML en une suite de "tokens" texte :
    #    On repère les dates avec un regex sur le texte brut,
    #    et on récupère les équipes avec un regex sur les <a .../equipe/...>Nom</a>
    #
    # Astuce simple : on remplace "<" par "\n<" pour casser les gros blocs
    html2 = html.replace("<", "\n<")

    # 2) Extraire toutes les occurrences de dates (dans le texte)
    # On récupère des lignes proches de ce que tu vois à l'écran
    text_lines = [re.sub(r"<[^>]+>", "", line).strip() for line in html2.splitlines()]
    text_lines = [x for x in text_lines if x]

    # 3) Extraire les équipes (dans l'ordre d'apparition dans le HTML)
    teams = TEAM_ANCHOR_RE.findall(html)
    team_idx = 0

    for line in text_lines:
        dt = parse_fr_datetime(line)
        if not dt:
            continue

        # On prend les deux prochains noms d'équipes trouvés dans le HTML
        if team_idx + 1 < len(teams):
            home = teams[team_idx].strip()
            away = teams[team_idx + 1].strip()
            team_idx += 2

            # évite quelques faux positifs
            if len(home) >= 2 and len(away) >= 2:
                matches.append((dt, home, away))

    return matches

def main():
    now = datetime.now(PARIS)

    future = []  # (dt, comp, home, away)

    for comp in COMPETITIONS:
        html = fetch(comp["calendar_url"])
        parsed = extract_matches_from_calendar(html)

        for dt, home, away in parsed:
            if dt >= now:
                future.append((dt, comp, home, away))

    future.sort(key=lambda x: x[0])

    items = []

    if future:
        first_dt = future[0][0]
        window_start, window_end = weekend_window_for(first_dt)

        for dt, comp, home, away in future:
            if window_start <= dt <= window_end:
                items.append({
                    "sport": "football",
                    "level": comp["level"],
                    "starts_at": dt.isoformat(),
                    "competition": comp["competition"],
                    "home_team": home,
                    "away_team": away,
                    "venue": {
                        "name": "Stade (à géolocaliser)",
                        "city": "",
                        "lat": 49.8489,
                        "lon": 3.2876
                    },
                    "source_url": comp["calendar_url"]
                })

    items.sort(key=lambda x: x["starts_at"])

    out = load_json(OUT, {"updated_at": None, "items": []})
    out["updated_at"] = datetime.now(UTC).isoformat()
    out["items"] = items
    save_json(OUT, out)

if __name__ == "__main__":
    main()
