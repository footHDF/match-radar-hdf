import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

PARIS = ZoneInfo("Europe/Paris")
UTC = ZoneInfo("UTC")

OUT = Path("matches.json")
WINDOW_DAYS = 14

# IMPORTANT : gp_no = le dernier nombre de ton URL "phase/1/<gp_no>"
# Exemple N2 : .../phase/1/2/... => gp_no = 2
COMPETITIONS = [
    {"level": "N2", "competition": "National 2 - Poule B", "cp_no": 439451, "ph_no": 1, "gp_no": 2},
    {"level": "N3", "competition": "National 3 - Poule E", "cp_no": 439452, "ph_no": 1, "gp_no": 5},

    {"level": "R1", "competition": "R1 - Poule A", "cp_no": 439189, "ph_no": 1, "gp_no": 1},
    {"level": "R1", "competition": "R1 - Poule B", "cp_no": 439189, "ph_no": 1, "gp_no": 2},

    {"level": "R2", "competition": "R2 - Poule A", "cp_no": 439190, "ph_no": 1, "gp_no": 1},
    {"level": "R2", "competition": "R2 - Poule B", "cp_no": 439190, "ph_no": 1, "gp_no": 2},
    {"level": "R2", "competition": "R2 - Poule C", "cp_no": 439190, "ph_no": 1, "gp_no": 3},
    {"level": "R2", "competition": "R2 - Poule D", "cp_no": 439190, "ph_no": 1, "gp_no": 4},

    {"level": "R3", "competition": "R3 - Poule A", "cp_no": 439191, "ph_no": 1, "gp_no": 1},
    {"level": "R3", "competition": "R3 - Poule B", "cp_no": 439191, "ph_no": 1, "gp_no": 2},
    {"level": "R3", "competition": "R3 - Poule C", "cp_no": 439191, "ph_no": 1, "gp_no": 3},
    {"level": "R3", "competition": "R3 - Poule D", "cp_no": 439191, "ph_no": 1, "gp_no": 4},
    {"level": "R3", "competition": "R3 - Poule E", "cp_no": 439191, "ph_no": 1, "gp_no": 5},
    {"level": "R3", "competition": "R3 - Poule F", "cp_no": 439191, "ph_no": 1, "gp_no": 6},
    {"level": "R3", "competition": "R3 - Poule G", "cp_no": 439191, "ph_no": 1, "gp_no": 7},
    {"level": "R3", "competition": "R3 - Poule H", "cp_no": 439191, "ph_no": 1, "gp_no": 8},
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

def http_get_json(url: str):
    r = SESSION.get(url, timeout=20)
    r.raise_for_status()
    return r.json()

def choose_base() -> str:
    # Test léger. (Sans .json : c’est souvent plus fiable)
    for base in BASE_URLS:
        try:
            _ = http_get_json(f"{base}/api/clubs?page=1&filter=")
            return base
        except Exception:
            pass
    raise RuntimeError("API DOFA inaccessible (aucun base URL ne répond).")

def as_list(payload):
    # Hydra JSON-LD ou liste directe
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

def parse_dt(me: dict) -> datetime | None:
    """
    L’API renvoie souvent :
    - "date": "2024-11-23T00:00:00+00:00"
    - "time": "14H30" (ou "14H")
    Ou parfois "starts_at".
    """
    # 1) starts_at direct
    s = me.get("starts_at") or me.get("datetime")
    if isinstance(s, str):
        try:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(PARIS)
        except Exception:
            pass

    # 2) date + time
    d = me.get("date")
    t = me.get("time")
    if isinstance(d, str):
        try:
            base_dt = datetime.fromisoformat(d)
            if base_dt.tzinfo is None:
                base_dt = base_dt.replace(tzinfo=UTC)
            base_dt = base_dt.astimezone(PARIS)
        except Exception:
            return None

        hh, mm = 0, 0
        if isinstance(t, str):
            tt = t.strip().upper().replace("H", ":")
            if ":" in tt:
                parts = tt.split(":")
                try:
                    hh = int(parts[0])
                    mm = int(parts[1]) if parts[1] else 0
                except Exception:
                    hh, mm = 0, 0
            else:
                try:
                    hh = int(tt)
                except Exception:
                    hh = 0

        return base_dt.replace(hour=hh, minute=mm, second=0, microsecond=0)

    return None

def parse_teams(me: dict) -> tuple[str, str]:
    home = ""
    away = ""

    h = me.get("home")
    a = me.get("away")

    # Dans l'exemple API : home/away contiennent "short_name"
    if isinstance(h, dict):
        home = h.get("short_name") or h.get("short_name_ligue") or h.get("short_name_federation") or ""
    if isinstance(a, dict):
        away = a.get("short_name") or a.get("short_name_ligue") or a.get("short_name_federation") or ""

    return home or "Domicile", away or "Extérieur"

def parse_terrain(me: dict) -> dict:
    t = me.get("terrain") if isinstance(me.get("terrain"), dict) else {}
    return {
        "name": t.get("name") or "Stade (à compléter)",
        "city": t.get("city") or "",
        "address": t.get("address") or "",
        "zip_code": t.get("zip_code") or ""
    }

def fetch_calendrier(base: str, cp_no: int, ph_no: int, gp_no: int):
    # Plusieurs variantes selon les versions
    candidates = [
        f"{base}/api/compets/{cp_no}/phases/{ph_no}/poules/{gp_no}/calendrier",
        f"{base}/api/compets/{cp_no}/phases/{ph_no}/poules/{gp_no}/matchs",
        f"{base}/api/compets/{cp_no}/phases/{ph_no}/poules/{gp_no}/calendrier.json?filter=",
        f"{base}/api/compets/{cp_no}/phases/{ph_no}/poules/{gp_no}/matchs.json?filter=",
    ]
    last_err = None
    for url in candidates:
        try:
            return as_list(http_get_json(url))
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"Calendrier introuvable cp={cp_no} ph={ph_no} gp={gp_no} ({last_err})")

def main():
    now = datetime.now(PARIS)
    window_start = now
    window_end = now + timedelta(days=WINDOW_DAYS)
    print(f"[INFO] Fenêtre: {window_start.isoformat()} -> {window_end.isoformat()}")

    base = choose_base()
    print(f"[INFO] API base: {base}")

    items = []

    for comp in COMPETITIONS:
        cp_no, ph_no, gp_no = comp["cp_no"], comp["ph_no"], comp["gp_no"]

        try:
            mes = fetch_calendrier(base, cp_no, ph_no, gp_no)
        except Exception as e:
            print(f"[WARN] KO {comp['level']} {comp['competition']} (cp={cp_no} gp={gp_no}) => {e}")
            continue

        kept = 0
        for me in mes:
            dt = parse_dt(me)
            if not dt:
                continue
            if not (window_start <= dt <= window_end):
                continue

            home, away = parse_teams(me)
            terrain = parse_terrain(me)

            items.append({
                "sport": "football",
                "level": comp["level"],
                "starts_at": dt.isoformat(),
                "competition": comp["competition"],
                "home_team": home,
                "away_team": away,
                "venue": {
                    "name": terrain["name"],
                    "city": terrain["city"],
                    "lat": 49.8489,  # provisoire (géocodage plus tard)
                    "lon": 3.2876,
                    "address": terrain["address"],
                    "zip_code": terrain["zip_code"],
                },
                "source_url": "https://epreuves.fff.fr/"
            })
            kept += 1

        print(f"[INFO] {comp['level']} {comp['competition']} => gardés dans fenêtre: {kept}")
        time.sleep(0.05)

    # dédup + tri
    uniq = {}
    for it in items:
        uniq[(it["starts_at"], it["home_team"], it["away_team"])] = it
    items = sorted(uniq.values(), key=lambda x: x["starts_at"])

    out = {"updated_at": datetime.now(UTC).isoformat(), "items": items}
    save_json(OUT, out)

    print(f"[OK] items={len(items)}")

if __name__ == "__main__":
    main()
