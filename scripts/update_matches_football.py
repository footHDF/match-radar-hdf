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
    "User-Agent": "match-radar-hdf (github actions) - contact: example@example.com",
    "Accept-Language": "fr-FR,fr;q=0.9",
})

MONTHS = {
    "janv": 1, "févr": 2, "fevr": 2, "mars": 3, "avr": 4, "mai": 5, "juin": 6,
    "juil": 7, "aoû": 8, "aou": 8, "sept": 9, "oct": 10, "nov": 11, "déc": 12, "dec": 12
}

DATE_RE = re.compile(
    r"^(lun|mar|mer|jeu|ven|sam|dim)\.?\s+(\d{1,2})\s+([a-zéûôîàç\.]+)\s+(\d{4})\s+-\s+(\d{1,2})h(\d{2})?$",
    re.IGNORECASE
)

# On attrape les URLs de match même si ce n’est pas un href classique
MATCH_URL_RE = re.compile(r"(https://epreuves\.fff\.fr)?(/competition/match/\d+[^\"'\s<]+)", re.IGNORECASE)

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
    mm_txt = m.group(6)
    mm = int(mm_txt) if mm_txt is not None else 0
    mon = MONTHS.get(mon_txt)
    if not mon:
        return None
    return datetime(year, mon, day, hh, mm, tzinfo=PARIS)

def extract_match_links(html: str) -> list[str]:
    links = set()
    for m in MATCH_URL_RE.finditer(html):
        path = m.group(2)
        links.add("https://epreuves.fff.fr" + path)
    return sorted(links)

def parse_match_page(url: str) -> dict | None:
    html = fetch(url)

    # 1) Date/heure : souvent en haut de page en clair (ex: "sam 07 fév 2026 - 14h00")
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


    # 2) Équipes depuis le <title> : "Le match | HOME - AWAY"
    title = re.search(r"<title>\s*Le match\s*\|\s*([^<]+?)\s*</title>", html, re.IGNORECASE)
    if not title:
        return None
    t = title.group(1)
    if " - " not in t:
        return None
    home, away = [x.strip() for x in t.split(" - ", 1)]

    # 3) Stade + adresse (optionnel)
    venue_name = ""
    venue_city = ""
    m_venue = re.search(r"##\s*Lieu de la rencontre\s*(?:\s|.){0,200}?\s*([A-Z0-9 \-’'ÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸ]+)\s*(?:\s|.){0,200}?\s*(\d{1,4}\s+[^<\n]+?\s+\d{5}\s+([A-ZÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸ \-’']+))", html, re.IGNORECASE)
    if m_venue:
        venue_name = m_venue.group(1).strip()
        # ville = 3e groupe (souvent tout en majuscules)
        venue_city = m_venue.group(3).strip().title()

    return {
        "starts_at": dt,
        "home_team": home,
        "away_team": away,
        "venue_name": venue_name,
        "venue_city": venue_city,
        "source_url": url,
    }

def extra_pages(calendar_url: str) -> list[str]:
    """
    On essaye plusieurs pages :
    - l’URL donnée
    - si elle finit par /resultats-et-calendrier => on ajoute la version sans ce suffixe
    - si elle ne finit pas par /resultats-et-calendrier => on ajoute la version avec
    """
    urls = [calendar_url]
    if calendar_url.endswith("/resultats-et-calendrier"):
        urls.append(calendar_url.replace("/resultats-et-calendrier", ""))
    else:
        urls.append(calendar_url.rstrip("/") + "/resultats-et-calendrier")
    # dédup
    out = []
    for u in urls:
        if u not in out:
            out.append(u)
    return out

def main():
    now = datetime.now(PARIS)
    window_start = now
    window_end = now + timedelta(days=14)

    print(f"[INFO] Fenêtre: {window_start.isoformat()}  ->  {window_end.isoformat()}")

    items = []
    seen_match_urls = set()
    parsed_ok = 0
    parsed_fail = 0

    for comp in COMPETITIONS:
        urls_to_try = extra_pages(comp["calendar_url"])
        comp_match_urls = set()

        for page_url in urls_to_try:
            try:
                html = fetch(page_url)
            except Exception as e:
                print(f"[WARN] Fetch impossible: {page_url} ({e})")
                continue

            found = extract_match_links(html)
            print(f"[INFO] {comp['level']} {comp['competition']} | {page_url} | liens match trouvés: {len(found)}")
            for u in found:
                comp_match_urls.add(u)

        comp_match_urls = sorted(comp_match_urls)
        if not comp_match_urls:
            continue

        # On limite pour éviter trop de requêtes
        for mu in comp_match_urls[:180]:
            if mu in seen_match_urls:
                continue
            seen_match_urls.add(mu)

           mp = None
try:
    mp = parse_match_page(mu)
except Exception as e:
    print(f"[WARN] parse match KO: {mu} ({e})")
    parsed_fail += 1
    continue

if not mp:
    parsed_fail += 1
    continue

parsed_ok += 1

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
                    "name": mp.get("venue_name") or "Stade (à compléter)",
                    "city": mp.get("venue_city") or "",
                    "lat": 49.8489,   # provisoire (Saint-Quentin)
                    "lon": 3.2876
                },
                "source_url": mp["source_url"]
            })

            time.sleep(0.15)

    items.sort(key=lambda x: x["starts_at"])

    out = load_json(OUT, {"updated_at": None, "items": []})
    out["updated_at"] = datetime.now(UTC).isoformat()
    out["items"] = items
    save_json(OUT, out)

    print(f"[INFO] parse_match_page ok={parsed_ok} fail={parsed_fail}")
    print(f"[OK] items={len(items)}")

if __name__ == "__main__":
    main()

