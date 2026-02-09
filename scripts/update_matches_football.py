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
SESSION.headers.update({"User-Agent": "match-radar-hdf (github actions)"})

MONTHS = {
    "janv": 1, "févr": 2, "fevr": 2, "mars": 3, "avr": 4, "mai": 5, "juin": 6,
    "juil": 7, "aoû": 8, "aou": 8, "sept": 9, "oct": 10, "nov": 11, "déc": 12, "dec": 12
}

DATE_RE = re.compile(
    r"^(lun|mar|mer|jeu|ven|sam|dim)\s+(\d{1,2})\s+([a-zéûôîàç\.]+)\s+(\d{4})\s*-\s*(\d{1,2})h(\d{2})$",
    re.IGNORECASE
)

def fetch(url: str) -> str:
    r = SESSION.get(url, timeout=30)
    r.raise_for_status()
    return r.text

def parse_fr_datetime(line: str) -> datetime | None:
    s = re.sub(r"\s+", " ", line.strip().lower())
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

def strip_to_lines(html: str) -> list[str]:
    # Remplace les balises par des retours ligne, puis nettoie
    text = re.sub(r"<script[\s\S]*?</script>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text)
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    return lines

def find_next_week_url(html: str, current_url: str) -> str | None:
    # Cherche un href proche de "navigation suivante"
    m = re.search(r'href="([^"]+)"[^>]*>\s*navigation suivante', html, flags=re.IGNORECASE)
    if m:
        return urljoin(current_url, m.group(1))
    # fallback : prendre le premier href qui contient "resultats-et-calendrier" après le texte
    idx = html.lower().find("navigation suivante")
    if idx != -1:
        snippet = html[idx: idx + 4000]
        m2 = re.search(r'href="([^"]*resultats-et-calendrier[^"]*)"', snippet, flags=re.IGNORECASE)
        if m2:
            return urljoin(current_url, m2.group(1))
    return None

def extract_matches_from_page(html: str) -> list[tuple[datetime, str, str]]:
    """
    On utilise la structure visible :
    date/heure
    équipe domicile
    score (ou tiret)
    équipe extérieur
    """
    lines = strip_to_lines(html)
    matches = []
    i = 0
    while i < len(lines):
        dt = parse_fr_datetime(lines[i])
        if not dt:
            i += 1
            continue

        # Cherche les 2 équipes dans les lignes suivantes (en sautant score/tirets)
        j = i + 1
        home = None
        away = None

        # home = prochaine ligne "texte" (souvent en majuscules)
        while j < len(lines) and home is None:
            if lines[j].lower().startswith("navigation"):
                j += 1
                continue
            # évite les lignes de score du type "2 0" ou "1 1"
            if re.fullmatch(r"\d+\s+\d+", lines[j]):
                j += 1
                continue
            home = lines[j]
            j += 1

        # saute éventuellement une ligne score
        while j < len(lines) and re.fullmatch(r"\d+\s+\d+", lines[j]):
            j += 1

        # away = prochaine ligne texte
        while j < len(lines) and away is None:
            if lines[j].lower().startswith("navigation"):
                j += 1
                continue
            if re.fullmatch(r"\d+\s+\d+", lines[j]):
                j += 1
                continue
            away = lines[j]
            j += 1

        if home and away:
            matches.append((dt, home, away))
            i = j
        else:
            i += 1

    return matches

def weekend_window_for(dt: datetime) -> tuple[datetime, datetime]:
    saturday = dt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=(dt.weekday() - 5) % 7)
    sunday_end = saturday + timedelta(days=1, hours=23, minutes=59, seconds=59)
    return saturday, sunday_end

def get_future_matches_for_comp(comp_url: str, now: datetime, max_weeks: int = 12):
    url = comp_url
    for _ in range(max_weeks):
        html = fetch(url)
        matches = extract_matches_from_page(html)
        future = [(dt, h, a, url) for (dt, h, a) in matches if dt >= now]
        if future:
            return future  # on s'arrête dès qu'on a une semaine future
        nxt = find_next_week_url(html, url)
        if not nxt or nxt == url:
            return []
        url = nxt
        time.sleep(0.2)
    return []

def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default

def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def main():
    now = datetime.now(PARIS)

    # 1) On récupère, pour chaque compétition, la première semaine qui contient des matchs futurs
    future_all = []  # (dt, comp, home, away, src)
    for comp in COMPETITIONS:
        fut = get_future_matches_for_comp(comp["calendar_url"], now, max_weeks=12)
        for dt, home, away, src in fut:
            future_all.append((dt, comp, home, away, src))

    future_all.sort(key=lambda x: x[0])

    # 2) On garde seulement le prochain week-end qui contient au moins un match
    items = []
    if future_all:
        first_dt = future_all[0][0]
        w_start, w_end = weekend_window_for(first_dt)
        for dt, comp, home, away, src in future_all:
            if w_start <= dt <= w_end:
                items.append({
                    "sport": "football",
                    "level": comp["level"],
                    "starts_at": dt.isoformat(),
                    "competition": comp["competition"],
                    "home_team": home,
                    "away_team": away,
                    # MVP coords (géolocalisation plus tard)
                    "venue": {"name": "Stade (à géolocaliser)", "city": "", "lat": 49.8489, "lon": 3.2876},
                    "source_url": src
                })

    out = load_json(OUT, {"updated_at": None, "items": []})
    out["updated_at"] = datetime.now(UTC).isoformat()
    out["items"] = sorted(items, key=lambda x: x["starts_at"])
    save_json(OUT, out)

    # Debug très utile dans les logs Actions
    print(f"[OK] items={len(out['items'])}")

if __name__ == "__main__":
    main()

