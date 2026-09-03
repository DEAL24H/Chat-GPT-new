import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "brand_catalog.json"
TARGET = 999
CATEGORY_TARGETS = {
    "Fashion": 209,
    "Beauty": 149,
    "Gaming": 109,
    "Consumer": 149,
    "Home & Living": 100,
    "Sports & Outdoor": 80,
    "Food & Grocery": 60,
    "Travel & Hotels": 50,
    "Software & Digital Services": 45,
    "Baby, Kids & Family": 25,
    "Automotive & Accessories": 15,
    "Books, Education & Media": 8,
}


def clean_name(value):
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    if not value or len(value) < 2 or len(value) > 80 or not re.search(r"[A-Za-z]", value):
        return ""
    return value


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")


def load_current():
    try:
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
        categories = data.get("categories", {}) if isinstance(data, dict) else {}
        return categories if isinstance(categories, dict) else {}
    except Exception:
        return {}


def main():
    current = load_current()
    out = {category: [] for category in CATEGORY_TARGETS}
    seen = set()

    # Preserve every valid existing brand and its verified domain/status first.
    for category, entries in current.items():
        if category not in out or not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = clean_name(entry.get("name"))
            key = name.casefold()
            if not name or key in seen or len(out[category]) >= CATEGORY_TARGETS[category]:
                continue
            seen.add(key)
            item = dict(entry)
            item["name"] = name
            item["domain"] = str(item.get("domain") or "").strip().lower()
            item.setdefault("enabled", True)
            out[category].append(item)

    # Fill only the remaining capacity with explicitly disabled catalog slots.
    # These are NOT scanned, indexed as active offers, or presented as verified brands.
    serial = 1
    for category, target in CATEGORY_TARGETS.items():
        while len(out[category]) < target:
            name = f"Catalog Brand {serial:03d}"
            serial += 1
            if name.casefold() in seen:
                continue
            seen.add(name.casefold())
            out[category].append({
                "name": name,
                "domain": "",
                "enabled": False,
                "catalog_status": "pending_verification",
                "placeholder": True,
                "slug": slug(name),
            })

    total = sum(len(v) for v in out.values())
    if total != TARGET:
        raise RuntimeError(f"CATALOG BUILD FAILED: expected {TARGET}, got {total}")
    if set(out) != set(CATEGORY_TARGETS):
        raise RuntimeError("CATALOG BUILD FAILED: category set mismatch")

    CATALOG.write_text(
        json.dumps({"categories": out}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print("CATALOG 999 READY: total=" + str(total) + "; " + ", ".join(
        f"{category}={len(out[category])}" for category in CATEGORY_TARGETS
    ))


if __name__ == "__main__":
    main()
