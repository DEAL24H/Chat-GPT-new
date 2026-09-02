import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "brand_catalog.json"
CATEGORY_LABELS = {"Fashion": "Fashion", "Beauty": "Beauty", "Gaming": "Gaming", "Consumer": "Consumer"}


def normalize_brand(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower().replace("’", "'")).strip()


def load_catalog():
    try:
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
        return data.get("categories", {}) if isinstance(data, dict) else {}
    except Exception:
        return {}


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


def is_active_offer(item):
    if str(item.get("status", "active")).lower() in {"expired", "inactive"}:
        return False
    if not (item.get("code") or item.get("promotion_url")):
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
