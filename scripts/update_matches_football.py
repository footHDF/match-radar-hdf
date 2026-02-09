import json
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("matches.json")

def main():
    if OUT.exists():
        data = json.loads(OUT.read_text(encoding="utf-8"))
    else:
        data = {"updated_at": None, "items": []}

    # Pour l’instant : mise à jour de l’horodatage (UTC)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()

    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
