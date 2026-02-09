import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin
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
    {"level": "R3", "competition": "R3 - Poule B", "calendar_url": "https://epreuves.fff.fr/competition/engagement/439191-seniors-regional-3/phase/1/2"},
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
    r"(lun|mar|mer|jeu|ven|sam|dim)\s+(\d{1,2})\s+([a-zéûôîàç\.]+)\s+(\d{4})\s*-\s*(\d{1,2})h(\d{2})",
    re.IGNORECASE
)

# ✅ Les équipes sont liées sous la forme /competition/club/.../equipe/...
TEAM_LINK_RE = re.compile(
    r'href="(/competition/club/[^"]+/equipe/[^"]+)"[^>]*>\s*([^<]{2,120}?)\s*</a>',
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

def parse_fr_datetime_from_match(m: re.Match) -> datetime | None:
    day = int(m.group(2))
    mon_txt = m.group(3).strip(".").lower()
    year = int(m.group(4))
    hh = int(m.group(5))
    mm = int(m.group(6))
    mon = MONTHS.get(mon_txt)
    if not mon:
        return None
    return datetime(year, mon, day, hh, mm, tzinfo=PARIS)

def weekend_window_for(dt: datetime) -> tuple[datetime, datetime]:
    # samedi 00:00 -> dimanche 23:59:59 (heure de Paris)
    saturday = dt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=(dt.weekday() - 5) % 7)
    sunday_end = saturday + timedelta(days=1, hours=23, minutes=59, seconds=59)
    return saturday, sunday_end

def find_next_week_url(html: str, base_url: str) -> str | None:
    """
    Cherche l'URL de la "navigation suivante" (semaine suivante).
    On prend un bout de HTML autour du texte et on récupère un href proche.
    """
    low = html.lower()
    idx = low.find("navigation suivante")
    if idx == -1:
        return None
    snippet = html[max(0, idx - 2000): idx + 2000]
    m = re.search(r'href="([^"]+)"[^>]*>\s*navigation suivante', snippet, re.IGNORECASE)
    if m:
        return urljoin(base_url, m.group(1))
    # fallback : premier href vers resultats-et-calendrier dans le snippet (différent de base)
    for mm in re.finditer(r'href="([^"]*resultats-et-calendrier[^"]*)"', snippet, re.IGNORECASE):
        cand = urljoin(base_url, mm.group(1))
        if cand != base_url:
            return cand
    return None

def extract_future_matches_from_calendar(url: str, now: datetime, max_weeks: int = 10):
    """
    Avance semaine par semaine tant qu'on ne trouve pas de matchs futurs.
    Retourne une liste (dt, home, away, source_url).
    """
    current_url = url
    all_future = []

    for _ in range(max_weeks):
        html = fetch(current_url)

        # équipes dans l'ordre d'apparition
        teams = [t[1].strip() for t in TEAM_LINK_RE.findall(html)]
        team_i = 0

        # dates dans l'ordre d'apparition
        for dm in DATE_RE.finditer(html):
            dt = parse_fr_datetime_from_match(dm)
            if not dt:
                continue

            # on associe les 2 prochaines équipes à cette date
            if team_i + 1 < len(teams):
                home = teams[team_i]
                away = teams[team_i + 1]
                team_i += 2

                if dt >= now:
                    all_future.append((dt, home, away, current_url))

        if all_future:
            break  # on a trouvé au moins un match futur, on s'arrête

        nxt = find_next_week_url(html, current_url)
        if not nxt or nxt == current_url:
            break
        current_url = nxt
        time.sleep(0.3)

    return all_future

def main():
    now = datetime.now(PARIS)
    future = []  # (dt, comp, home, away, src)

    for comp in COMPETITIONS:
        matches = extract_future_matches_from_calendar(comp["calendar_url"], now, max_weeks=10)
        for dt, home, away, src in matches:
            future.append((dt, comp, home, away, src))

    future.sort(key=lambda x: x[0])

    items = []
    if future:
        first_dt = future[0][0]
        window_start, window_end = weekend_window_for(first_dt)

        for dt, comp, home, away, src in future:
            if window_start <= dt <= window_end:
                items.append({
                    "sport": "football",
                    "level": comp["level"],
                    "starts_at": dt.isoformat(),
                    "competition": comp["competition"],
                    "home_team": home,
                    "away_team": away,
                    # MVP coords (on géolocalise après)
                    "venue": {"name": "Stade (à géolocaliser)", "city": "", "lat": 49.8489, "lon": 3.2876},
                    "source_url": src
                })

    out = load_json(OUT, {"updated_at": None, "items": []})
    out["updated_at"] = datetime.now(UTC).isoformat()
    out["items"] = items
    save_json(OUT, out)

if __name__ == "__main__":
    main()
