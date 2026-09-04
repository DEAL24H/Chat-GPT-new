import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "brand_catalog.json"
TARGET = 534
EXPECTED = {"Fashion": 89, "Beauty": 89, "Consumer": 89, "Home & Living": 89, "Food & Grocery": 89, "Travel & Hotels": 89}
FORBIDDEN = {"w3.org", "google.com", "bing.com", "yahoo.com", "facebook.com", "instagram.com", "tiktok.com", "x.com", "twitter.com", "wikipedia.org"}

def normalize_domain(value):
    raw = str(value or "").strip().lower().removeprefix("www.")
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else "https://" + raw)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    return host

def main():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    categories = data.get("categories") if isinstance(data, dict) else None
    if not isinstance(categories, dict) or set(categories) != set(EXPECTED):
        raise SystemExit("CATALOG VALIDATION FAILED: expected exactly 6 locked priority categories")
    names = set()
    domains = set()
    for category, expected_count in EXPECTED.items():
        entries = categories.get(category)
        if not isinstance(entries, list) or len(entries) != expected_count:
            raise SystemExit(f"CATALOG VALIDATION FAILED: {category} must contain exactly 89 brands")
        for entry in entries:
            if not isinstance(entry, dict):
                raise SystemExit(f"CATALOG VALIDATION FAILED: invalid entry in {category}")
            name = str(entry.get("name", "")).strip()
            key = name.casefold()
            domain = normalize_domain(entry.get("domain"))
            if not name or key in names:
                raise SystemExit(f"CATALOG VALIDATION FAILED: duplicate/empty brand: {name!r}")
            if entry.get("placeholder") or entry.get("enabled") is False:
                raise SystemExit(f"CATALOG VALIDATION FAILED: disabled/placeholder brand is forbidden: {name}")
            if entry.get("seo_only") is True:
                raise SystemExit(f"CATALOG VALIDATION FAILED: seo_only/pending-domain brand remains in locked catalog: {name}")
            if not domain or "." not in domain:
                raise SystemExit(f"CATALOG VALIDATION FAILED: missing/invalid official domain: {name}")
            if domain in FORBIDDEN or any(domain.endswith("." + x) for x in FORBIDDEN):
                raise SystemExit(f"CATALOG VALIDATION FAILED: forbidden/search/social domain: {name} -> {domain}")
            if not re.fullmatch(r"[a-z0-9.-]+", domain):
                raise SystemExit(f"CATALOG VALIDATION FAILED: invalid domain syntax: {name} -> {domain}")
            names.add(key)
            domains.add(domain)
    if len(names) != TARGET:
        raise SystemExit(f"CATALOG VALIDATION FAILED: expected {TARGET} brands, got {len(names)}")
    print(f"CATALOG LOCK VALID: 6 categories x 89 = 534 brands; all 534 have non-placeholder official domains")

if __name__ == "__main__":
    main()
