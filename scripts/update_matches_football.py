import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

PARIS = ZoneInfo("Europe/Paris")
UTC = ZoneInfo("UTC")

OUT = Path("matches.json")

WINDOW_DAYS = 14

# Garde-fous pour ne plus faire des runs interminables
MAX_TEAM_PAGES_PER_COMP = 20          # max pages équipe à visiter par compétition
MAX_CANDIDATES_PER_TEAM = 12          # max "match à venir" repérés par équipe
SLEEP = 0.08

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

# Mois rencontrés sur les pages epreuves
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

# Ex: "sam 14 fév 2026 - 18h00" / "sam. 14 fév 2026 - 18h"
DATE_RE = re.compile(
    r"\b(?:lun|mar|mer|jeu|ven|sam|dim)\.?\s+(\d{1,2})\s+([a-zéûôîàç\.]+)\s+(\d{4})\s+-\s+(\d{1,2})h(\d{2})?\b",
    re.IGNORECASE
)

# Pages équipe
TEAM_URL_RE = re.compile(
    r'(https://epreuves\.fff\.fr)?(/competition/club/\d+[^"\'\s<]+/equipe/[^"\'\s<]+)',
    re.IGNORECASE
)

# Pages match
MATCH_URL_RE = re.compile(
    r'(https://epreuves\.fff\.fr)?(/competition/match/\d+[^"\'\s<]+)',
    re.IGNORECASE
)

def fetch(url: str) -> str:
    r = SESSION.get(url, timeout=30)
    r.raise_for_status()
    return r.text

def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def parse_fr_dt_from_snippet(snippet: str) -> datetime | None:
    s = re.sub(r"\s+", " ", snippet.strip().lower())
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

def extract_team_pages(comp_html: str) -> list[str]:
    links = set()
    for m in TEAM_URL_RE.finditer(comp_html):
        links.add("https://epreuves.fff.fr" + m.group(2))
    return sorted(links)

def extract_future_match_candidates_from_team_page(team_html: str, window_start: datetime, window_end: datetime) -> list[tuple[str, datetime]]:
    """
    On cherche des occurrences où la DATE et un lien /competition/match/... sont proches.
    On ne va ouvrir la page match QUE si la date est dans la fenêtre.
    """
    candidates = []
    # On parcourt les liens match et on prend un “contexte” autour pour trouver la date
    for m in MATCH_URL_RE.finditer(team_html):
        url = "https://epreuves.fff.fr" + m.group(2)
        start = max(0, m.start() - 350)
        end = min(len(team_html), m.end() + 350)
        snippet = team_html[start:end]

        dt = parse_fr_dt_from_snippet(snippet)
        if not dt:
            continue
        if window_start <= dt <= window_end:
            candidates.append((url, dt))

    # dédup + tri
    uniq = {}
    for url, dt in candidates:
        uniq[url] = dt
    out = sorted([(u, d) for u, d in uniq.items()], key=lambda x: x[1])
    return out

def parse_match_page(url: str) -> dict | None:
    html = fetch(url)

    # Date/heure : on rescanne la page match (plus fiable)
    dt = parse_fr_dt_from_snippet(html)
    if not dt:
        return None

    # Équipes via <title> : "Le match | HOME - AWAY"
    title = re.search(r"<title>\s*Le match\s*\|\s*([^<]+?)\s*</title>", html, re.IGNORECASE)
    if not title:
        return None
    t = title.group(1).strip()
    if " - " not in t:
        return None
    home, away = [x.strip() for x in t.split(" - ", 1)]

    # Stade/ville (best effort — on fera mieux ensuite)
    venue_name = "Stade (à compléter)"
    venue_city = ""
    text = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    text = re.sub(r"(?is)<style.*?>.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    idx = text.lower().find("lieu de la rencontre")
    if idx != -1:
        chunk = text[idx: idx + 450]
        # petit heuristic : prendre ce qui ressemble à un nom de stade
        m_stade = re.search(r"(?i)\b(stade|terrain|complexe|parc)\b.{0,80}", chunk)
        if m_stade:
            venue_name = m_stade.group(0).strip()
        m_city = re.search(r"\b\d{5}\s+([A-ZÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸ \-’']{2,40})\b", chunk)
        if m_city:
            venue_city = m_city.group(1).title()

    return {
        "starts_at": dt,
        "home_team": home,
        "away_team": away,
        "venue_name": venue_name,
        "venue_city": venue_city,
        "source_url": url,
    }

def main():
    now = datetime.now(PARIS)
    window_start = now
    window_end = now + timedelta(days=WINDOW_DAYS)
    print(f"[INFO] Fenêtre: {window_start.isoformat()} -> {window_end.isoformat()}")

    items = []
    seen_match_urls = set()

    total_team_pages = 0
    total_candidates = 0
    opened_match_pages = 0

    for comp in COMPETITIONS:
        try:
            comp_html = fetch(comp["calendar_url"])
        except Exception as e:
            print(f"[WARN] fetch comp KO: {comp['calendar_url']} ({e})")
            continue

        team_pages = extract_team_pages(comp_html)[:MAX_TEAM_PAGES_PER_COMP]
        total_team_pages += len(team_pages)
        print(f"[INFO] {comp['level']} {comp['competition']} | team_pages={len(team_pages)}")

        for tp in team_pages:
            try:
                thtml = fetch(tp)
            except Exception:
                continue

            cand = extract_future_match_candidates_from_team_page(thtml, window_start, window_end)
            if not cand:
                continue

            total_candidates += len(cand)
            cand = cand[:MAX_CANDIDATES_PER_TEAM]

            for mu, dt_hint in cand:
                if mu in seen_match_urls:
                    continue
                seen_match_urls.add(mu)

                opened_match_pages += 1
                mp = None
                try:
                    mp = parse_match_page(mu)
                except Exception:
                    mp = None

                if not mp:
                    continue

                dt = mp["starts_at"]
                if not (window_start <= dt <= window_end):
                    continue

                items.append({
                    "sport": "football",
                    "level": comp["level"],
                    "starts_at": dt.isoformat(),
                    "competition": comp["competition"],
                    "home_team": mp["home_team"],
                    "away_team": mp["away_team"],
                    "venue": {
                        "name": mp["venue_name"],
                        "city": mp["venue_city"],
                        # provisoire tant qu'on ne géocode pas
                        "lat": 49.8489,
                        "lon": 3.2876
                    },
                    "source_url": mp["source_url"],
                })

                time.sleep(SLEEP)

    # dédup + tri
    uniq = {}
    for it in items:
        uniq[(it["starts_at"], it["home_team"], it["away_team"], it["level"])] = it
    items = sorted(uniq.values(), key=lambda x: x["starts_at"])

    out = {"updated_at": datetime.now(UTC).isoformat(), "items": items}
    save_json(OUT, out)

    print(f"[INFO] team_pages_total={total_team_pages} candidates_total={total_candidates} match_pages_opened={opened_match_pages}")
    print(f"[OK] items={len(items)} (dans la fenêtre)")
    print("[OK] matches.json écrit")

if __name__ == "__main__":
    main()
