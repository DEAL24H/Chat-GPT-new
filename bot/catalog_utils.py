import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "brand_catalog.json"
EXPECTED_CATEGORIES = ("Fashion", "Electronics", "Beauty & Personal Care", "Home & Living")
CATEGORY_LABELS = {c: c for c in EXPECTED_CATEGORIES}
PUBLISHED_STATUS = "live_verified"
SOURCE_AUTHORITY = "assistant_verified_first_party"
PUBLISHED_AUTHORITY = "assistant_verified_source_plus_live_brand_purchase_destination"


def normalize_brand(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower().replace("’", "'")).strip()


def load_catalog():
    try:
        data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        categories = data.get("categories", {}) if isinstance(data, dict) else {}
        if set(categories) != set(EXPECTED_CATEGORIES):
            raise ValueError(f"Canonical catalog categories mismatch: {sorted(categories)}")
        if any(len(categories[c]) != 30 for c in EXPECTED_CATEGORIES):
            raise ValueError("Canonical catalog must contain exactly 30 brands per category")
        return categories
    except Exception as exc:
        raise RuntimeError(f"Cannot load canonical brand catalog: {exc}") from exc


CATALOG = load_catalog()
BRAND_INDEX = {}
for category, entries in CATALOG.items():
    for entry in entries:
        name = str(entry.get("name", "")).strip()
        if name:
            BRAND_INDEX[normalize_brand(name)] = {
                "name": name,
                "category": category,
                "domain": str(entry.get("domain", "")).strip(),
            }


def resolve_brand(value):
    return BRAND_INDEX.get(normalize_brand(value))


def canonical_brand_name(value):
    hit = resolve_brand(value)
    return hit["name"] if hit else str(value or "").strip()


def category_for_brand(value):
    hit = resolve_brand(value)
    return hit["category"] if hit else ""


def canonicalize_item(item):
    item = dict(item)
    hit = resolve_brand(item.get("merchant"))
    if hit:
        item["merchant"] = hit["name"]
        item["category"] = hit["category"]
    return item


def brand_slug(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower().replace("&", " and ").replace("'", "")).strip("-")


def _same_host(left, right):
    a = urlparse(str(left or "").strip()).hostname or ""
    b = urlparse(str(right or "").strip()).hostname or ""
    return bool(a and b) and a.lower().removeprefix("www.") == b.lower().removeprefix("www.")


def _not_expired(item):
    if str(item.get("status", "active")).lower() in {"expired", "inactive"}:
        return False
    raw = str(item.get("expires_at", "")).strip()
    if not raw:
        return True
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt > datetime.now(timezone.utc)
    except ValueError:
        return False


def is_published_verified_offer(item):
    """Single downstream publish contract for shards, SEO and Supabase."""
    if not isinstance(item, dict) or item.get("category") not in EXPECTED_CATEGORIES:
        return False
    brand = resolve_brand(item.get("merchant"))
    if not brand or brand.get("category") != item.get("category"):
        return False
    if item.get("offer_qualified") is not True:
        return False
    if item.get("official_source") is not True:
        return False
    if item.get("source_verification_status") != SOURCE_AUTHORITY:
        return False
    if item.get("purchase_url_verification_status") != PUBLISHED_STATUS:
        return False
    if item.get("published_offer_authority") != PUBLISHED_AUTHORITY:
        return False
    source = str(item.get("source_url") or "").strip()
    promotion = str(item.get("promotion_url") or "").strip()
    purchase = str(item.get("final_purchase_url") or "").strip()
    url = str(item.get("url") or "").strip()
    official_domain = str(brand.get("domain") or "").strip()
    if not source or not promotion or not purchase or url != purchase or not official_domain:
        return False
    if not _same_host(promotion, source) or not _same_host(source, official_domain):
        return False
    if not _same_host(purchase, official_domain) or not _not_expired(item):
        return False
    return True


def is_active_offer(item):
    """Compatibility alias: downstream code must use the published contract."""
    return is_published_verified_offer(item)


def published_items(items):
    return [item for item in items if is_published_verified_offer(item)]
