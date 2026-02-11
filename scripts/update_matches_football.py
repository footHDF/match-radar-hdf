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

# Anti “runs interminables”
MAX_PAGES_PER_POULE = 3
MAX_POULES_PER_COMP = 1
SLEEP = 0.06

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

BASE_URLS = [
    "https://api-dofa.prd-aws.fff.fr",
    "https://api-dofa.fff.fr",
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "match-radar-hdf (github actions)",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "fr-FR,fr;q=0.9",
})

def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def fetch_text(url: str) -> str:
    r = SESSION.get(url, timeout=25)
    r.raise_for_status()
    return r.text

def http_get_json(url: str):
    r = SESSION.get(url, timeout=25)
    r.raise_for_status()
    return r.json()

def as_list(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        if "hydra:member" in payload and isinstance(payload["hydra:member"], list):
            return payload["hydra:member"]
        if "member" in payload and isinstance(payload["member"], list):
            return payload["member"]
        for k in ("items", "data", "results"):
            if k in payload and isinstance(payload[k], list):
                return payload[k]
    return []

def extract_token_from_epreuves() -> str | None:
    """
    On tente de récupérer un JWT dans le HTML de epreuves.fff.fr.
    Plusieurs patterns possibles.
    """
    html = fetch_text("https://epreuves.fff.fr/")
    # Pattern JWT typique : xxx.yyy.zzz (base64url)
    jwt_candidates = re.findall(r"([A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,})", html)
    if jwt_candidates:
        # on prend le plus long, souvent le vrai
        jwt_candidates.sort(key=len, reverse=True)
        return jwt_candidates[0]

    # Pattern "token":"...."
    m = re.search(r'"token"\s*:\s*"([^"]{20,})"', html)
    if m:
        return m.group(1)

    # Pattern "accessToken":"...."
    m = re.search(r'"accessToken"\s*:\s*"([^"]{20,})"', html)
    if m:
        return m.group(1)

    return None

def choose_base() -> str:
    # endpoint test
    for base in BASE_URLS:
        try:
            _ = http_get_json(f"{base}/api/clubs.json?page=1&filter=")
            return base
        except Exception:
            continue
    raise RuntimeError("API DOFA inaccessible (test /api/clubs.json KO).")

def iso_to_dt(s: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(PARIS)
    except Exception:
        return None

def extract_start_dt(me: dict) -> datetime | None:
    for k in ("starts_at", "date", "datetime", "match_date", "begin_at"):
        v = me.get(k)
        if isinstance(v, str):
            dt = iso_to_dt(v)
            if dt:
                return dt
    return None

def extract_teams(me: dict) -> tuple[str, str]:
    def name_of(x):
        if isinstance(x, str):
            return x
        if isinstance(x, dict):
            for k in ("name", "short_name", "label"):
                if k in x and isinstance(x[k], str):
                    return x[k]
        return ""
    home, away = "", ""
    for hk, ak in [("home_team","away_team"), ("team_home","team_away"), ("home","away"), ("club_home","club_away")]:
        if hk in me or ak in me:
            home = name_of(me.get(hk, ""))
            away = name_of(me.get(ak, ""))
            if home or away:
                break
    return home.strip() or "Domicile", away.strip() or "Extérieur"

def extract_venue(me: dict) -> tuple[str, str]:
    venue_name, city = "", ""
    for k in ("stadium", "venue", "lieu", "place", "terrain"):
        v = me.get(k)
        if isinstance(v, dict):
            venue_name = v.get("name") or v.get("label") or venue_name
            city = v.get("city") or v.get("town") or city
    venue_name = me.get("stadium_name") or me.get("venue_name") or venue_name
    city = me.get("city") or me.get("town") or city
    return (venue_name or "Stade (à compléter)"), (city or "")

def get_poules(base: str, cp_no: int, phase: int) -> list[dict]:
    url = f"{base}/api/compets/{cp_no}/phases/{phase}/poules.json?filter="
    return as_list(http_get_json(url))

def get_match_entities_for_poule(base: str, po_no: int, max_pages: int) -> list[dict]:
    all_items = []
    for page in range(1, max_pages + 1):
        url = f"{base}/api/poules/{po_no}/match_entities.json?page={page}&filter="
        payload = http_get_json(url)
        items = as_list(payload)
        if not items:
            break
        all_items.extend(items)
        time.sleep(SLEEP)
    return all_items

def main():
    now = datetime.now(PARIS)
    window_start = now
    window_end = now + timedelta(days=WINDOW_DAYS)
    print(f"[INFO] Fenêtre: {window_start.isoformat()} -> {window_end.isoformat()}")

    # 1) token depuis epreuves.fff.fr
    token = extract_token_from_epreuves()
    if token:
        SESSION.headers["Authorization"] = f"Bearer {token}"
        print("[INFO] Token trouvé sur epreuves.fff.fr")
    else:
        print("[WARN] Aucun token trouvé sur epreuves.fff.fr (on tente sans token)")

    # 2) base API
    base = choose_base()
    print(f"[INFO] API base: {base}")

    items = []
    poules_total = 0
    mes_total = 0

    for comp in COMPETITIONS:
        try:
            poules = get_poules(base, comp["cp_no"], comp["phase"])
        except Exception as e:
            print(f"[WARN] Poules KO {comp['level']} {comp['competition']} ({e})")
            continue

        poules = poules[:MAX_POULES_PER_COMP]
        poules_total += len(poules)
        print(f"[INFO] {comp['level']} {comp['competition']} | poules={len(poules)}")

        for p in poules:
            po_no = p.get("po_no") or p.get("id") or p.get("number")
            if not po_no:
                continue

            try:
                mes = get_match_entities_for_poule(base, int(po_no), MAX_PAGES_PER_POULE)
            except Exception:
                continue

            mes_total += len(mes)
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
                    "venue": {"name": venue_name, "city": city, "lat": 49.8489, "lon": 3.2876},
                    "source_url": "https://epreuves.fff.fr/"
                })

    uniq = {}
    for it in items:
        uniq[(it["starts_at"], it["home_team"], it["away_team"], it["level"])] = it
    items = sorted(uniq.values(), key=lambda x: x["starts_at"])

    out = {"updated_at": datetime.now(UTC).isoformat(), "items": items}
    save_json(OUT, out)

    print(f"[INFO] poules_total={poules_total} match_entities_lus={mes_total}")
    print(f"[OK] items={len(items)}")
    print("[OK] matches.json écrit")

if __name__ == "__main__":
    main()


