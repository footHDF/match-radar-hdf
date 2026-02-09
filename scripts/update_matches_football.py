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

# Fenêtre de recherche : maintenant -> +14 jours
WINDOW_DAYS = 14

# Limites pour ne pas exploser les requêtes
MAX_TEAM_PAGES_PER_COMP = 40
MAX_MATCH_LINKS_PER_TEAM = 30

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

# Ex: "sam 14 fév 2026 - 15h00" / parfois "sam. 14 fév 2026 - 15h"
DATE_RE = re.compile(
    r"\b(lun|mar|mer|jeu|ven|sam|dim)\.?\s+(\d{1,2})\s+([a-zéûôîàç\.]+)\s+(\d{4})\s+-\s+(\d{1,2})h(\d{2})?\b",
    re.IGNORECASE
)

MATCH_URL_RE = re.compile(r"(https://epreuves\.fff\.fr)?(/competition/match/\d+[^\"'\s<]+)", re.IGNORECASE)

# Pages équipe (club + equipe)
TEAM_URL_RE = re.compile(r"(https://epreuves\.fff\.fr)?(/competition/club/\d+[^\"'\s<]+/equipe/[^\"'\s<]+)", re.IGNORECASE)

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

def parse_fr_datetime_from_match_text(text: str) -> datetime | None:
    """
    Cherche une date FR dans un texte, renvoie datetime Europe/Paris.
    """
    text = re.sub(r"\s+", " ", text.strip().lower())
    text = text.replace("févr.", "févr").replace("janv.", "janv").replace("sept.", "sept").replace("déc.", "déc")
    text = text.replace("août", "aoû")

    m = DATE_RE.search(text)
    if not m:
        return None

    day = int(m.group(2))
    mon_txt = m.group(3).strip(".")
    year = int(m.group(4))
    hh = int(m.group(5))
    mm_txt = m.group(6)
    mm = int(mm_txt) if mm_txt else 0

    mon = MONTHS.get(mon_txt)
    if not mon:
        return None

    return datetime(year, mon, day, hh, mm, tzinfo=PARIS)

def extract_team_pages_from_comp(html: str) -> list[str]:
    """
    Sur la page compétition, on récupère les liens vers les pages équipe.
    """
    links = set()
    for m in TEAM_URL_RE.finditer(html):
        links.add("https://epreuves.fff.fr" + m.group(2))
    return sorted(links)

def extract_match_links(html: str) -> list[str]:
    """
    Dans une page (équipe / match / etc), on récupère les liens des pages match.
    """
    links = set()
    for m in MATCH_URL_RE.finditer(html):
        links.add("https://epreuves.fff.fr" + m.group(2))
    return sorted(links)

def strip_tags(html: str) -> str:
    # Suffisant pour notre parsing “texte”
    html = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style.*?>.*?</style>", " ", html)
    return re.sub(r"(?s)<[^>]+>", " ", html)

def parse_match_page(url: str) -> dict | None:
    """
    Ouvre une page match et extrait:
    - date/heure
    - équipes (depuis <title> "Le match | HOME - AWAY")
    - lieu (stade + adresse)
    """
    html = fetch(url)
    text = strip_tags(html)
    text = re.sub(r"\s+", " ", text).strip()

    # 1) Date/heure
    dt = parse_fr_datetime_from_match_text(text)
    if not dt:
        return None

    # 2) Équipes via <title>
    title = re.search(r"<title>\s*Le match\s*\|\s*([^<]+?)\s*</title>", html, re.IGNORECASE)
    if not title:
        return None
    t = title.group(1).strip()
    if " - " not in t:
        return None
    home, away = [x.strip() for x in t.split(" - ", 1)]

    # 3) Lieu : on repère "Lieu de la rencontre" puis on prend les 2 lignes suivantes “utiles”
    venue_name = "Stade (à compléter)"
    venue_city = ""
    venue_addr = ""

    idx = text.lower().find("lieu de la rencontre")
    if idx != -1:
        chunk = text[idx: idx + 400]  # petit bloc après le titre
        # On enlève le titre lui-même
        chunk = re.sub(r"(?i)lieu de la rencontre", "", chunk).strip()
        # On tente d'attraper "STADE XXX" puis "ADRESSE 12345 VILLE"
        # Exemple vu : "STADE ERBAJOLO PASTORECCIA ... 20600 BASTIA"
        m1 = re.search(r"\b(stade|complexe|terrain|parc)\b[^0-9]{3,80}", chunk, re.IGNORECASE)
        if m1:
            venue_name = m1.group(0).strip()

        m2 = re.search(r"\b\d{5}\s+([A-ZÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸ \-’']{2,40})\b", chunk)
        if m2:
            venue_city = m2.group(1).title()

        # Adresse brute (optionnel)
        maddr = re.search(r"([0-9].{0,120}\b\d{5}\s+[A-ZÀÂÄÇÉÈÊËÎÏÔÖÙÛÜŸ \-’']{2,40})", chunk)
        if maddr:
            venue_addr = maddr.group(1).strip()

    return {
        "starts_at": dt,
        "home_team": home,
        "away_team": away,
        "venue_name": venue_name,
        "venue_city": venue_city,
        "venue_addr": venue_addr,
        "source_url": url,
    }

def main():
    now = datetime.now(PARIS)
    window_start = now
    window_end = now + timedelta(days=WINDOW_DAYS)

    print(f"[INFO] Fenêtre: {window_start.isoformat()}  ->  {window_end.isoformat()}")

    items = []
    seen_match_urls = set()

    for comp in COMPETITIONS:
        print(f"[INFO] === {comp['level']} {comp['competition']} ===")
        try:
            comp_html = fetch(comp["calendar_url"])
        except Exception as e:
            print(f"[WARN] Impossible de fetch compétition: {comp['calendar_url']} ({e})")
            continue

        team_pages = extract_team_pages_from_comp(comp_html)
        print(f"[INFO] pages équipe trouvées: {len(team_pages)}")

        # On limite pour éviter trop de requêtes
        team_pages = team_pages[:MAX_TEAM_PAGES_PER_COMP]

        comp_added = 0
        team_checked = 0

        for tp in team_pages:
            team_checked += 1
            try:
                thtml = fetch(tp)
            except Exception:
                continue

            match_urls = extract_match_links(thtml)
            match_urls = match_urls[:MAX_MATCH_LINKS_PER_TEAM]

            for mu in match_urls:
                if mu in seen_match_urls:
                    continue
                seen_match_urls.add(mu)

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
                        "name": mp.get("venue_name") or "Stade (à compléter)",
                        "city": mp.get("venue_city") or "",
                        # Pour l’instant pas de géocodage → coordonnées provisoires
                        "lat": 49.8489,
                        "lon": 3.2876,
                        "address": mp.get("venue_addr") or ""
                    },
                    "source_url": mp["source_url"]
                })
                comp_added += 1

                time.sleep(0.12)

        print(f"[INFO] équipes scannées: {team_checked} | matchs ajoutés (dans fenêtre): {comp_added}")

    # Tri + dédup “logique” (même affiche, même horaire)
    def key(m):
        return (m["starts_at"], m["home_team"], m["away_team"])

    uniq = {}
    for it in items:
        uniq[key(it)] = it

    items = sorted(uniq.values(), key=lambda x: x["starts_at"])

    out = load_json(OUT, {"updated_at": None, "items": []})
    out["updated_at"] = datetime.now(UTC).isoformat()
    out["items"] = items
    save_json(OUT, out)

    print(f"[OK] items={len(items)} (dans la fenêtre)")

if __name__ == "__main__":
    main()
