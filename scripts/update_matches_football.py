import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, parse_qs, unquote_plus

import requests

PARIS = ZoneInfo("Europe/Paris")
UTC = ZoneInfo("UTC")

OUT = Path("matches.json")
GEOCACHE = Path("geocache.json")

WINDOW_DAYS = 14

# Anti “run infini”
MAX_TEAMS_PER_COMP = 40       # large, mais suffisant
MAX_MATCHES_PER_TEAM = 12     # on prend seulement les prochains matchs trouvés
SLEEP = 0.10

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
    r"^(?:lun|mar|mer|jeu|ven|sam|dim)\.?\s+(\d{1,2})\s+([a-zéûôîàç\.]+)\s+(\d{4})\s+-\s+(\d{1,2})h(\d{2})?$",
    re.IGNORECASE
)

TEAM_PAGE_RE = re.compile(
    r"(https://epreuves\.fff\.fr)?(/competition/club/\d+-[^\"'\s<]+/equipe/[^\"'\s<]+)",
    re.IGNORECASE
)

CLUB_ROOT_RE = re.compile(
    r"(https://epreuves\.fff\.fr)?(/competition/club/\d+-[^\"'\s<]+)",
    re.IGNORECASE
)

APPLE_MAPS_RE = re.compile(r'href="([^"]*maps\.apple\.com[^"]*)"', re.IGNORECASE)

def fetch(url: str) -> str:
    r = SESSION.get(url, timeout=30)
    r.raise_for_status()
    return r.text

def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default

def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()

def html_to_lines(html: str) -> list[str]:
    # enlève scripts/styles
    html = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style.*?>.*?</style>", " ", html)
    # remplace les tags par des retours ligne
    text = re.sub(r"(?s)<[^>]+>", "\n", html)
    # decode entités simples
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
    lines = [normalize_space(x) for x in text.splitlines()]
    return [x for x in lines if x]

def parse_fr_datetime(line: str) -> datetime | None:
    s = normalize_space(line.lower())
    s = s.replace("févr.", "févr").replace("fév.", "fév").replace("janv.", "janv")
    s = s.replace("sept.", "sept").replace("déc.", "déc").replace("août", "aoû")

    m = DATE_RE.match(s)
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

def is_time_token(s: str) -> bool:
    return bool(re.fullmatch(r"\d{1,2}:\d{2}", s))

def is_score_token(s: str) -> bool:
    # ex: "1 2" ou "0 0"
    return bool(re.fullmatch(r"\d{1,2}\s+\d{1,2}", s))

def extract_team_pages(comp_html: str) -> list[str]:
    links = set()
    for m in TEAM_PAGE_RE.finditer(comp_html):
        links.add("https://epreuves.fff.fr" + m.group(2))
    return sorted(links)

def club_root_from_team_page(team_url: str) -> str:
    m = re.search(r"(https://epreuves\.fff\.fr)?(/competition/club/\d+-[^/]+)", team_url, re.IGNORECASE)
    if not m:
        return ""
    return "https://epreuves.fff.fr" + m.group(2)

def try_coords_from_apple_maps(url: str) -> tuple[float, float] | None:
    try:
        u = urlparse(url)
        qs = parse_qs(u.query)
        # cas 1: ll=LAT,LON
        if "ll" in qs and qs["ll"]:
            ll = qs["ll"][0]
            if "," in ll:
                lat_s, lon_s = ll.split(",", 1)
                return float(lat_s), float(lon_s)
        # cas 2: query contient LAT,LON
        for key in ("q", "address"):
            if key in qs and qs[key]:
                val = unquote_plus(qs[key][0])
                m = re.search(r"(-?\d+(?:\.\d+)?),\s*(-?\d+(?:\.\d+)?)", val)
                if m:
                    return float(m.group(1)), float(m.group(2))
    except Exception:
        return None
    return None

def get_club_coords_and_city(club_url: str, geocache: dict) -> tuple[float, float, str]:
    """
    On essaie :
    - coordonnées depuis les liens Apple Maps "Voir sur la carte" (souvent avec ll=lat,lon)
    - sinon fallback: coord défaut Saint-Quentin
    """
    if club_url in geocache:
        g = geocache[club_url]
        return g["lat"], g["lon"], g.get("city", "")

    lat, lon, city = 49.8489, 3.2876, ""  # défaut

    try:
        html = fetch(club_url)
        # 1) Apple Maps
        for m in APPLE_MAPS_RE.finditer(html):
            amap = m.group(1)
            coords = try_coords_from_apple_maps(amap)
            if coords:
                lat, lon = coords
                break

        # 2) Ville via lignes texte (best effort: prendre le code postal + ville dans "Coordonnées")
        lines = html_to_lines(html)
        for i, line in enumerate(lines):
            if "Coordonnées" in line or "COORDONNEES" in line.upper():
                # chercher une ligne contenant "75000 PARIS"
                for j in range(i, min(i + 10, len(lines))):
                    m2 = re.search(r"\b\d{5}\s+([A-ZÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸ \-’']+)\b", lines[j])
                    if m2:
                        city = m2.group(1).title()
                        break
            if city:
                break

    except Exception:
        pass

    geocache[club_url] = {"lat": lat, "lon": lon, "city": city}
    return lat, lon, city

def extract_matches_from_team_page(team_url: str, level: str, competition: str, window_start: datetime, window_end: datetime) -> list[dict]:
    """
    On lit les lignes du HTML (sans JS) et on repère les blocs :
      DATE
      compétition (ex: "N2 - Senior Journée 18")
      équipe A
      (heure éventuelle "18:00")
      équipe B
    """
    html = fetch(team_url)
    lines = html_to_lines(html)

    matches = []
    i = 0
    while i < len(lines):
        dt = parse_fr_datetime(lines[i])
        if not dt:
            i += 1
            continue

        # filtre fenêtre tout de suite
        if not (window_start <= dt <= window_end):
            i += 1
            continue

        # chercher les 2 équipes dans les prochaines lignes
        teams = []
        lookahead = lines[i+1:i+20]
        for tok in lookahead:
            if is_time_token(tok):
                continue
            if is_score_token(tok):
                continue
            low = tok.lower()
            if "journée" in low or "journee" in low or "classement" in low or "navigation" in low:
                continue
            if low in ("dernier match", "prochain match", "saison", "mois précédent", "mois suivant"):
                continue
            # on garde des tokens “équipes” (souvent en MAJ)
            if len(tok) >= 3 and re.search(r"[A-Za-zÀ-ÿ]", tok):
                teams.append(tok)
            if len(teams) >= 2:
                break

        if len(teams) >= 2:
            home_team = teams[0]
            away_team = teams[1]
            matches.append({
                "starts_at": dt,
                "home_team": home_team,
                "away_team": away_team,
                "level": level,
                "competition": competition,
                "team_page_url": team_url,
            })

        i += 1

        if len(matches) >= MAX_MATCHES_PER_TEAM:
            break

    return matches

def main():
    now = datetime.now(PARIS)
    window_start = now
    window_end = now + timedelta(days=WINDOW_DAYS)
    print(f"[INFO] Fenêtre: {window_start.isoformat()} -> {window_end.isoformat()}")

    geocache = load_json(GEOCACHE, {})

    # On collecte des team pages, puis on extrait les matchs des team pages
    all_items = []
    seen_keys = set()

    team_pages_total = 0
    team_pages_opened = 0

    for comp in COMPETITIONS:
        try:
            comp_html = fetch(comp["calendar_url"])
        except Exception as e:
            print(f"[WARN] fetch compétition KO: {comp['calendar_url']} ({e})")
            continue

        team_pages = extract_team_pages(comp_html)[:MAX_TEAMS_PER_COMP]
        print(f"[INFO] {comp['level']} {comp['competition']} | team_pages trouvées={len(team_pages)}")
        team_pages_total += len(team_pages)

        for tp in team_pages:
            team_pages_opened += 1
            try:
                found = extract_matches_from_team_page(
                    tp, comp["level"], comp["competition"], window_start, window_end
                )
            except Exception:
                continue

            for m in found:
                dt = m["starts_at"]

                key = (dt.isoformat(), m["home_team"], m["away_team"], m["level"])
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                # venue = club du domicile
                # on essaye de retrouver le club root depuis la team page (ça marche car URL contient /competition/club/ID-...)
                club_url = club_root_from_team_page(tp)
                lat, lon, city = get_club_coords_and_city(club_url, geocache) if club_url else (49.8489, 3.2876, "")

                all_items.append({
                    "sport": "football",
                    "level": m["level"],
                    "starts_at": dt.isoformat(),
                    "competition": m["competition"],
                    "home_team": m["home_team"],
                    "away_team": m["away_team"],
                    "venue": {
                        "name": "Stade (club domicile)",
                        "city": city,
                        "lat": lat,
                        "lon": lon,
                    },
                    "source_url": tp,  # source = page équipe (fiable sans token)
                })

            time.sleep(SLEEP)

    all_items.sort(key=lambda x: x["starts_at"])

    save_json(GEOCACHE, geocache)

    out = {
        "updated_at": datetime.now(UTC).isoformat(),
        "items": all_items,
    }
    save_json(OUT, out)

    print(f"[INFO] team_pages_total={team_pages_total} team_pages_opened={team_pages_opened}")
    print(f"[OK] items={len(all_items)} (dans la fenêtre)")
    print("[OK] matches.json écrit")

if __name__ == "__main__":
    main()

