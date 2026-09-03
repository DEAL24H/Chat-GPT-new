import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "brand_catalog.json"
TARGET = 534
EXPECTED = {
    "Fashion": 89,
    "Beauty": 89,
    "Consumer": 89,
    "Home & Living": 89,
    "Food & Grocery": 89,
    "Travel & Hotels": 89,
}

def main():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    categories = data.get("categories") if isinstance(data, dict) else None
    if not isinstance(categories, dict) or set(categories) != set(EXPECTED):
        raise SystemExit("CATALOG VALIDATION FAILED: expected 6 priority categories")
    names = set()
    for category, expected_count in EXPECTED.items():
        entries = categories.get(category)
        if not isinstance(entries, list) or len(entries) != expected_count:
            raise SystemExit(f"CATALOG VALIDATION FAILED: {category} must contain exactly {expected_count} brands")
        for entry in entries:
            if not isinstance(entry, dict):
                raise SystemExit(f"CATALOG VALIDATION FAILED: invalid entry in {category}")
            name = str(entry.get("name", "")).strip()
            key = name.casefold()
            domain = str(entry.get("domain", "")).strip()
            if not name or key in names:
                raise SystemExit(f"CATALOG VALIDATION FAILED: duplicate/empty brand: {name!r}")
            if entry.get("placeholder"):
                raise SystemExit(f"CATALOG VALIDATION FAILED: placeholder brand is forbidden: {name}")
            if entry.get("enabled") is False or not domain:
                raise SystemExit(f"CATALOG VALIDATION FAILED: every brand must be enabled and have a domain: {name}")
            names.add(key)
    if len(names) != TARGET:
        raise SystemExit(f"CATALOG VALIDATION FAILED: expected {TARGET} real brands, got {len(names)}")
    print("CATALOG VALID: 6 categories x 89 brands = 534 real enabled brands; no placeholders")

if __name__ == "__main__":
    main()
