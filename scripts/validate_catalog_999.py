import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "brand_catalog.json"
TARGET = 999
EXPECTED = {
    "Fashion": 209, "Beauty": 149, "Gaming": 109, "Consumer": 149,
    "Home & Living": 100, "Sports & Outdoor": 80, "Food & Grocery": 60,
    "Travel & Hotels": 50, "Software & Digital Services": 45,
    "Baby, Kids & Family": 25, "Automotive & Accessories": 15,
    "Books, Education & Media": 8,
}

def main():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    categories = data.get("categories") if isinstance(data, dict) else None
    if not isinstance(categories, dict) or set(categories) != set(EXPECTED):
        raise SystemExit("CATALOG VALIDATION FAILED: category set mismatch")
    names = set()
    enabled = 0
    placeholders = 0
    for category, expected_count in EXPECTED.items():
        entries = categories.get(category)
        if not isinstance(entries, list) or len(entries) != expected_count:
            raise SystemExit(f"CATALOG VALIDATION FAILED: {category} count mismatch")
        for entry in entries:
            if not isinstance(entry, dict):
                raise SystemExit(f"CATALOG VALIDATION FAILED: invalid entry in {category}")
            name = str(entry.get("name", "")).strip()
            key = name.casefold()
            if not name or key in names:
                raise SystemExit(f"CATALOG VALIDATION FAILED: duplicate/empty brand: {name!r}")
            names.add(key)
            if entry.get("placeholder"):
                placeholders += 1
                if entry.get("enabled") is not False or entry.get("domain"):
                    raise SystemExit(f"CATALOG VALIDATION FAILED: placeholder must be disabled: {name}")
            else:
                enabled += 1
                if entry.get("enabled", True) and not str(entry.get("domain", "")).strip():
                    raise SystemExit(f"CATALOG VALIDATION FAILED: enabled brand has no domain: {name}")
    if len(names) != TARGET:
        raise SystemExit(f"CATALOG VALIDATION FAILED: expected {TARGET} unique names, got {len(names)}")
    print(f"CATALOG VALID: total={len(names)}, enabled={enabled}, pending_slots={placeholders}")

if __name__ == "__main__":
    main()
