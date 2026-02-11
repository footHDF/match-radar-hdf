import json
from pathlib import Path
from datetime import datetime

RAW = Path("matches_raw.json")   # entrée
OUTDIR = Path("data")            # sortie

def main():
    if not RAW.exists():
        raise SystemExit("matches_raw.json introuvable à la racine")

    OUTDIR.mkdir(exist_ok=True)

    raw = json.loads(RAW.read_text(encoding="utf-8"))
    items = raw.get("items", [])

    buckets = {}  # "YYYY-MM" -> list
    for it in items:
        s = it.get("starts_at")
        if not s:
            continue
        dt = datetime.fromisoformat(s)
        key = f"{dt.year:04d}-{dt.month:02d}"
        buckets.setdefault(key, []).append(it)

    for key, arr in buckets.items():
        arr.sort(key=lambda x: x.get("starts_at", ""))
        out = {"updated_at": datetime.utcnow().isoformat() + "Z", "items": arr}
        (OUTDIR / f"{key}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"OK: {len(items)} matchs répartis sur {len(buckets)} mois.")

if __name__ == "__main__":
    main()
