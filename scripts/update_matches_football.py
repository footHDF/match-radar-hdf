import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

PARIS = ZoneInfo("Europe/Paris")
UTC = ZoneInfo("UTC")

OUT = Path("matches.json")

WINDOW_DAYS = 14

COMPETITIONS = [
    {"level": "N2", "competition": "National 2 - Poule B", "url": "https://epreuves.fff.fr/competition/engagement/439451-n2/phase/1/2/resultats-et-calendrier"},
    {"level": "N3", "competition": "National 3 - Poule E", "url": "https://epreuves.fff.fr/competition/engagement/439452-n3/phase/1/5/resultats-et-calendrier"},

    {"level": "R1", "competition": "R1 - Poule A", "url": "https://epreuves.fff.fr/competition/engagement/439189-seniors-regional-1/phase/1/1"},
    {"level": "R1", "competition": "R1 - Poule B", "url": "https://epreuves.fff.fr/competition/engagement/439189-seniors-regional-1/phase/1/2"},

    {"level": "R2", "competition": "R2 - Poule A", "url": "https://epreuves.fff.fr/competition/engagement/439190-seniors-regional-2/phase/1/1"},
    {"level": "R2", "competition": "R2 - Poule B", "url": "https://epreuves.fff.fr/competition/engagement/439190-seniors-regional-2/phase/1/2"},
    {"level": "R2", "competition": "R2 - Poule C", "url": "https://epreuves.fff.fr/competition/engagement/439190-seniors-regional-2/phase/1/3"},
    {"level": "R2", "competition": "R2 - Poule D", "url": "https://epreuves.fff.fr/competition/engagement/439190-seniors-regional-2/phase/1/4"},

    {"level": "R3", "competition": "R3 - Poule A", "url": "https://epreuves.fff.fr/competition/engagement/439191-seniors-regional-3/phase/1/1"},
    {"level": "R3", "competition": "R3 - Poule B", "url": "https://epreuves.fff.fr/competition/engagement/439191-seniors-regional-3/phase/1/2"},
    {"level": "R3", "competition": "R3 - Poule C", "url": "https://epreuves.fff.fr/competition/engagement/439191-seniors-regional-3/phase/1/3"},
    {"level": "R3", "competition": "R3 - Poule D", "url": "https://epreuves.fff.fr/competition/engagement/439191-seniors-regional-3/phase/1/4"},
    {"level": "R3", "competition": "R3 - Poule E", "url": "https://epreuves.fff.fr/competition/engagement/439191-seniors-regional-3/phase/1/5"},
    {"level": "R3", "competition": "R3 - Poule F", "url": "https://epreuves.fff.fr/competition/engagement/439191-seniors-regional-3/phase/1/6"},
    {"level": "R3", "competition": "R3 - Poule G", "url": "https://epreuves.fff.fr/competition/engagement/439191-seniors-regional-3/phase/1/7"},
    {"level": "R3", "competition": "R3 - Poule H", "url": "https://epreuves.fff.fr/competition/engagement/439191-seniors-regional-3/phase/1/8"},
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "match-radar-hdf (github actions)",
    "Accept-Language": "fr-FR,fr;q=0.9",
})

MONTHS = {
    "janv": 1, "jan": 1,
    "févr": 2, "fév": 2, "fevr": 2, "fev": 2,
    "mars": 3, "mar": 3,
    "avr": 4,
    "mai": 5,
    "juin": 6, "jun": 6,
    "juil": 7, "jui": 7,
    "aoû": 8, "août": 8, "aou": 8,
    "sept": 9, "sep": 9,
    "oct": 10,
    "nov": 11,
    "déc": 12, "dec": 12,
}

# accepte "sam 07 fév 2026 - 18h00" et "sam. 07 fév 2026 - 18h"
DATE_RE = re.compile(
    r"\b(?:lun|mar|mer|jeu|ven|sam|dim)\.?\s+(\d{1,2})\s+([a-zéûôîàç\.]+)\s+(\d{4})\s+-\s+(\d{1,2})h(\d{2})?\b",
    re.IGNORECASE
)

def fetch(url: str) -> str:
    r = SESSION.get(url, timeout=35)
    r.raise_for_status()
    return r.text

def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def html_to_lines(html: str) -> list[str]:
    # enlève scripts/styles
    html = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style.*?>.*?</style>", " ", html)
    # tags -> retours lignes
    text = re.sub(r"(?s)<[^>]+>", "\n", html)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
    # nettoie
    lines = [re.sub(r"\s+", " ", x).strip() for x in text.splitlines()]
    return [x for x in lines if x]

def parse_dt_from_line(line: str) -> datetime | None:
    s = line.strip().lower()
    s = s.replace("févr.", "févr").replace("fév.", "fév").replace("janv.", "janv")
    s = s.replace("sept.", "sept").replace("déc.", "déc").replace("août", "aoû")
    m = DATE_RE.search(s)
    if not m:
        return None
    day = int(m.group(1))
    mon_txt = m.group(2).strip(".")
    year = int(m.group(3))
    hh = int(m.group(4))
    mm = int(m.group(5)) if m.group(5) else 0
    mon = MONTHS.get(mon_txt)
    if not mon:
        return None
    return datetime(year, mon, day, hh, mm, tzinfo=PARIS)

def is_noise(line: str) -> bool:
    low = line.lower()
    if low.startswith("semaine du "):
        return True
    if "navigation" in low:
        return True
    if low in ("classement", "saison", "les matchs", "sélectionnez la poule", "choisissez une poule"):
        return True
    # score "1 2"
    if re.fullmatch(r"\d{1,2}\s+\d{1,2}", line.strip()):
        return True
    return False

def looks_like_team(line: str) -> bool:
    if is_noise(line):
        return False
    # évite les lignes trop courtes
    if len(line.strip()) < 3:
        return False
    # évite les heures "18:00"
    if re.fullmatch(r"\d{1,2}:\d{2}", line.strip()):
        return False
    # une équipe contient des lettres
    return bool(re.search(r"[A-Za-zÀ-ÿ]", line))

def extract_matches_from_competition_page(html: str, window_start: datetime, window_end: datetime):
    lines = html_to_lines(html)

    matches = []
    i = 0
    while i < len(lines):
        dt = parse_dt_from_line(lines[i])
        if not dt:
            i += 1
            continue

        # on cherche les 2 équipes juste après
        teams = []
        for j in range(i + 1, min(i + 25, len(lines))):
            if looks_like_team(lines[j]):
                teams.append(lines[j])
            if len(teams) == 2:
                break

        if len(teams) == 2 and (window_start <= dt <= window_end):
            matches.append((dt, teams[0], teams[1]))

        i += 1

    return matches

def main():
    now = datetime.now(PARIS)
    window_start = now
    window_end = now + timedelta(days=WINDOW_DAYS)
    print(f"[INFO] Fenêtre: {window_start.isoformat()} -> {window_end.isoformat()}")

    items = []
    total_parsed = 0

    for comp in COMPETITIONS:
        try:
            html = fetch(comp["url"])
        except Exception as e:
            print(f"[WARN] fetch KO: {comp['url']} ({e})")
            continue

        found = extract_matches_from_competition_page(html, window_start, window_end)
        total_parsed += len(found)
        print(f"[INFO] {comp['level']} {comp['competition']} => trouvés (dans fenêtre): {len(found)}")

        for dt, home, away in found:
            items.append({
                "sport": "football",
                "level": comp["level"],
                "starts_at": dt.isoformat(),
                "competition": comp["competition"],
                "home_team": home,
                "away_team": away,
                "venue": {
                    "name": "Stade (à géocoder ensuite)",
                    "city": "",
                    "lat": 49.8489,  # provisoire
                    "lon": 3.2876
                },
                "source_url": comp["url"],
            })

    # dédup + tri
    uniq = {}
    for it in items:
        uniq[(it["starts_at"], it["home_team"], it["away_team"], it["level"])] = it
    items = sorted(uniq.values(), key=lambda x: x["starts_at"])

    out = {"updated_at": datetime.now(UTC).isoformat(), "items": items}
    save_json(OUT, out)

    print(f"[INFO] total_matches_in_window={len(items)} (dedup)")
    print("[OK] matches.json écrit")

if __name__ == "__main__":
    main()
