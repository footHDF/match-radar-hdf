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
    "User-Agent": "match-radar-hdf (github actions)",
    "Accept-Language": "fr-FR,fr;q=0.9",
})

MONTHS = {
    "jan": 1, "janv": 1,
    "fév": 2, "fev": 2, "févr": 2, "fevr": 2,
    "mar": 3, "mars": 3,
    "avr": 4,
    "mai": 5,
    "jun": 6, "juin": 6,
    "jui": 7, "juil": 7,
    "aoû": 8, "aou": 8, "août": 8,
    "sep": 9, "sept": 9,
    "oct": 10,
    "nov": 11,
    "déc": 12, "dec": 12,
}

DATE_RE = re.compile(
    r"^(lun|mar|mer|jeu|ven|sam|dim)\.?\s+(\d{1,2})\s+([a-zéûôîàç\.]+)\s+(\d{4})\s+-\s+(\d{1,2})h(\d{2})?$",
    re.IGNORECASE
)

# liens des matchs
MATCH_URL_RE = re.compile(
    r"(https://epreuves\.fff\.fr)?(/competition/match/\d+[^\"'\s<]+)",
    re.IGNORECASE
)

# lien "navigation suivante"
NEXT_RE = re.compile(r'href="([^"]+)"[^>]*>\s*navigation suivante', re.IGNORECASE)

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
    s = s.replace("févr.", "févr").replace("fév.", "fév").replace("janv.", "janv")
    s = s.replace("sept.", "sept").replace("déc.", "déc").replace("août", "aoû")

    m = DATE_RE.match(s)
    if not m:
        return None

    day = int(m.group(2))
    mon_txt = m.group(3).strip(".")
    year = int(m.group(4))
    hh = int(m.group(5))
    mm_txt = m.group(6)
    mm = int(mm_txt) if mm_txt is not None else 0

    mon = MONTHS.get(mon_txt)
    if not mon:
        return None

    return datetime(year, mon, day, hh, mm, tzinfo=PARIS)

def extract_match_links(html: str) -> list[str]:
    links = set()
    for m in MATCH_URL_RE.finditer(html):
        links.add("https://epreuves.fff.fr" + m.group(2))
    return sorted(links)

def find_next_page(html: str, current_url: str) -> str | None:
    m = NEXT_RE.search(html)
    if not m:
        return None
    return urljoin(current_url, m.group(1))

def parse_match_page(url: str) -> dict | None:
    html = fetch(url)

    # date/heure en clair sur la page
    dt = None
    for line in re.findall(
        r"\b(?:lun|mar|mer|jeu|ven|sam|dim)\.?\s+\d{1,2}\s+[a-zéûôîàç\.]+\s+\d{4}\s+-\s+\d{1,2}h(?:\d{2})?\b",
        html,
        flags=re.IGNORECASE
    ):
        dt = parse_fr_datetime(line)
        if dt:
            break
    if not dt:
        return None

    # équipes via title
    title = re.search(r"<title>\s*Le match\s*\|\s*([^<]+?)\s*</title>", html, re.IGNORECASE)
    if not title:
        return None
    t = title.group(1)
    if " - " not in t:
        return None
    home, away = [x.strip() for x in t.split(" - ", 1)]

    return {"starts_at": dt, "home_team": home, "away_team": away, "source_url": url}

def main():
    now = datetime.now(PARIS)
    window_start = now
    window_end = now + timedelta(days=14)
    print(f"[INFO] Fenêtre: {window_start.isoformat()} -> {window_end.isoformat()}")

    items = []
    seen_match_urls = set()

    parsed_ok = 0
    parsed_fail = 0
    kept_in_window = 0

    # Pour chaque compétition : on avance page par page jusqu'à dépasser J+14
    for comp in COMPETITIONS:
        page_url = comp["calendar_url"]
        max_pages = 8  # ~8 semaines, largement suffisant pour trouver J+14

        for page_i in range(max_pages):
            try:
                html = fetch(page_url)
            except Exception as e:
                print(f"[WARN] Fetch impossible: {page_url} ({e})")
                break

            match_urls = extract_match_links(html)
            print(f"[INFO] {comp['level']} {comp['competition']} | page {page_i+1}/{max_pages} | matchs trouvés: {len(match_urls)}")

            # on parse les matchs de la page
            max_per_page = 60
            latest_dt_on_page = None

            for mu in match_urls[:max_per_page]:
                if mu in seen_match_urls:
                    continue
                seen_match_urls.add(mu)

                try:
                    mp = parse_match_page(mu)
                except Exception as e:
                    parsed_fail += 1
                    continue

                if not mp:
                    parsed_fail += 1
                    continue

                parsed_ok += 1
                dt = mp["starts_at"]
                if latest_dt_on_page is None or dt > latest_dt_on_page:
                    latest_dt_on_page = dt

                if window_start <= dt <= window_end:
                    kept_in_window += 1
                    items.append({
                        "sport": "football",
                        "level": comp["level"],
                        "starts_at": dt.isoformat(),
                        "competition": comp["competition"],
                        "home_team": mp["home_team"],
                        "away_team": mp["away_team"],
                        "venue": {"name": "Stade (à géolocaliser)", "city": "", "lat": 49.8489, "lon": 3.2876},
                        "source_url": mp["source_url"]
                    })

                time.sleep(0.08)

            # Si on a déjà une date sur la page et qu'elle dépasse la fenêtre, inutile d'aller plus loin
            if latest_dt_on_page and latest_dt_on_page > window_end:
                break

            nxt = find_next_page(html, page_url)
            if not nxt or nxt == page_url:
                break
            page_url = nxt
            time.sleep(0.2)

    items.sort(key=lambda x: x["starts_at"])

    out = load_json(OUT, {"updated_at": None, "items": []})
    out["updated_at"] = datetime.now(UTC).isoformat()
    out["items"] = items
    save_json(OUT, out)

    print(f"[INFO] parse_match_page ok={parsed_ok} fail={parsed_fail}")
    print(f"[OK] items={len(items)} (dans la fenêtre)")

if __name__ == "__main__":
    main()
