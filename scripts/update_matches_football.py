import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

PARIS = ZoneInfo("Europe/Paris")
UTC = ZoneInfo("UTC")

OUT = Path("matches.json")

# IMPORTANT :
# - cp_no = l'identifiant numérique dans l'URL "competition/engagement/<ID>-..."
# - phase = souvent 1
COMPETITIONS = [
    {"level": "N2", "competition": "National 2 - Poule B", "cp_no": 439451, "phase": 1},
    {"level": "N3", "competition": "National 3 - Poule E", "cp_no": 439452, "phase": 1},

    {"level": "R1", "competition": "R1 - Poule A", "cp_no": 439189, "phase": 1},
    {"level": "R1", "competition": "R1 - Poule B", "cp_no": 439189, "phase": 1},

    {"level": "R2", "competition": "R2 - Poule A", "cp_no": 439190, "phase": 1},
    {"level": "R2", "competition": "R2 - Poule B", "cp_no": 439190, "phase": 1},
    {"level": "R2", "competition": "R2 - Poule C", "cp_no": 439190, "phase": 1},
    {"level": "R2", "competition": "R2 - Poule D", "cp_no": 439190, "phase": 1},

    {"level": "R3", "competition": "R3 - Poule A", "cp_no": 439191, "phase": 1},
    {"level": "R3", "competition": "R3 - Poule B", "cp_no": 439191, "phase": 1},
    {"level": "R3", "competition": "R3 - Poule C", "cp_no": 439191, "phase": 1},
    {"level": "R3", "competition": "R3 - Poule D", "cp_no": 439191, "phase": 1},
    {"level": "R3", "competition": "R3 - Poule E", "cp_no": 439191, "phase": 1},
    {"level": "R3", "competition": "R3 - Poule F", "cp_no": 439191, "phase": 1},
    {"level": "R3", "competition": "R3 - Poule G", "cp_no": 439191, "phase": 1},
    {"level": "R3", "competition": "R3 - Poule H", "cp_no": 439191, "phase": 1},
]

# L'API a déjà changé de domaine par le passé : on tente plusieurs bases.
BASE_URLS = [
    "https://api-dofa.prd-aws.fff.fr",
    "https://api-dofa.fff.fr",
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "match-radar-hdf (github actions) - contact: example@example.com",
    "Accept": "application/json,text/plain,*/*",
})

def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def iso_to_dt(s: str) -> datetime | None:
    # Supporte "2026-02-14T18:00:00+01:00" etc.
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=PARIS)
        return dt.astimezone(PARIS)
    except Exception:
        return None

def http_get_json(url: str):
    r = SESSION.get(url, timeout=30)
    r.raise_for_status()
    return r.json()

def first_working_base() -> str:
    # Ping léger : on tente un endpoint simple (clubs page 1) avec filter vide
    for base in BASE_URLS:
        try:
            _ = http_get_json(f"{base}/api/clubs.json?page=1&filter=")
            return base
        except Exception:
            continue
    raise RuntimeError("Impossible d'atteindre l'API DOFA (aucune base ne répond).")

def as_list(payload):
    # Certains endpoints renvoient une liste directe,
    # d'autres renvoient du JSON-LD/Hydra avec 'hydra:member'
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if "hydra:member" in payload and isinstance(payload["hydra:member"], list):
            return payload["hydra:member"]
        if "member" in payload and isinstance(payload["member"], list):
            return payload["member"]
        # fallback : parfois c'est un dict de dicts
        for k in ("items", "data", "results"):
            if k in payload and isinstance(payload[k], list):
                return payload[k]
    return []

def get_poules(base: str, cp_no: int, phase: int) -> list[dict]:
    # Souvent requis : .json?filter=
    url = f"{base}/api/compets/{cp_no}/phases/{phase}/poules.json?filter="
    payload = http_get_json(url)
    return as_list(payload)

def get_match_entities_for_poule(base: str, po_no: int, max_pages: int = 6) -> list[dict]:
    """
    On pagine pour éviter les runs à 24 minutes.
    max_pages=6 -> assez pour récupérer la fenêtre proche si le tri est standard.
    """
    all_items = []
    for page in range(1, max_pages + 1):
        tried = []

        # Plusieurs variantes existent selon les périodes :
        candidates = [
            f"{base}/api/poules/{po_no}/match_entities.json?page={page}&filter=",
            f"{base}/api/poules/{po_no}/match_entities.json?filter=&page={page}",
            f"{base}/api/poules/{po_no}/match_entities?page={page}&filter=",
        ]

        payload = None
        for u in candidates:
            tried.append(u)
            try:
                payload = http_get_json(u)
                break
            except Exception:
                payload = None

        if payload is None:
            # Rien sur cette poule (ou endpoint non dispo)
            return all_items

        items = as_list(payload)
        if not items:
            break

        all_items.extend(items)

        # petit frein pour être gentil avec l'API
        time.sleep(0.05)

    return all_items

def extract_teams(me: dict) -> tuple[str, str]:
    """
    Selon les retours, ça peut être :
    - home_team / away_team
    - team_home / team_away
    - home / away avec 'name'
    """
    def name_of(x):
        if isinstance(x, str):
            return x
        if isinstance(x, dict):
            for k in ("name", "short_name", "label"):
                if k in x and isinstance(x[k], str):
                    return x[k]
        return ""

    home = ""
    away = ""
    for hk, ak in [
        ("home_team", "away_team"),
        ("team_home", "team_away"),
        ("home", "away"),
        ("club_home", "club_away"),
    ]:
        if hk in me or ak in me:
            home = name_of(me.get(hk, ""))
            away = name_of(me.get(ak, ""))
            if home or away:
                break

    return home.strip() or "Domicile", away.strip() or "Extérieur"

def extract_start_dt(me: dict) -> datetime | None:
    # Clés courantes possibles
    for k in ("starts_at", "date", "datetime", "match_date", "begin_at"):
        v = me.get(k)
        if isinstance(v, str):
            dt = iso_to_dt(v)
            if dt:
                return dt
    return None

def extract_venue(me: dict) -> tuple[str, str]:
    """
    On prend ce qu'on peut : parfois 'stadium', 'venue', 'lieu'
    """
    venue_name = ""
    city = ""

    for k in ("stadium", "venue", "lieu", "place"):
        v = me.get(k)
        if isinstance(v, dict):
            venue_name = v.get("name") or v.get("label") or venue_name
            city = v.get("city") or v.get("town") or city

    # parfois c’est directement dans des clés "stadium_name" etc.
    venue_name = me.get("stadium_name") or me.get("venue_name") or venue_name
    city = me.get("city") or me.get("town") or city

    return (venue_name or "Stade (à compléter)"), (city or "")

def main():
    now = datetime.now(PARIS)
    window_start = now
    window_end = now + timedelta(days=14)

    print(f"[INFO] Fenêtre: {window_start.isoformat()}  ->  {window_end.isoformat()}")

    base = first_working_base()
    print(f"[INFO] API base utilisée: {base}")

    items = []
    pages_opened = 0

    for comp in COMPETITIONS:
        cp_no = comp["cp_no"]
        phase = comp["phase"]

        # 1) récupérer les poules
        try:
            poules = get_poules(base, cp_no, phase)
        except Exception as e:
            print(f"[WARN] Poules KO cp_no={cp_no} ({e})")
            continue

        print(f"[INFO] {comp['level']} {comp['competition']} | poules trouvées: {len(poules)}")

        # 2) pour chaque poule, récupérer les match_entities (paginés)
        for p in poules:
            po_no = p.get("po_no") or p.get("id") or p.get("number")
            if not po_no:
                continue

            mes = get_match_entities_for_poule(base, int(po_no), max_pages=6)
            pages_opened += 1

            for me in mes:
                dt = extract_start_dt(me)
                if not dt:
                    continue
                if not (window_start <= dt <= window_end):
                    continue

                home, away = extract_teams(me)
                venue_name, city = extract_venue(me)

                items.append({
                    "sport": "football",
                    "level": comp["level"],
                    "starts_at": dt.isoformat(),
                    "competition": comp["competition"],
                    "home_team": home,
                    "away_team": away,
                    "venue": {
                        "name": venue_name,
                        "city": city,
                        # provisoire tant qu'on ne géocode pas encore
                        "lat": 49.8489,
                        "lon": 3.2876,
                    },
                    # on met un lien "source" générique si on n'a pas mieux
                    "source_url": f"https://epreuves.fff.fr/",
                })

    items.sort(key=lambda x: x["starts_at"])
    print(f"[INFO] pages match ouvertes={pages_opened}")
    print(f"[OK] items={len(items)} (dans la fenêtre)")

    out = {
        "updated_at": datetime.now(UTC).isoformat(),
        "items": items
    }
    save_json(OUT, out)
    print("[OK] matches.json écrit")

if __name__ == "__main__":
    main()
