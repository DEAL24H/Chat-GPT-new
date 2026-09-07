"""Canonical definition of a publishable, verified DEAL24H offer."""
from datetime import datetime, timezone
from urllib.parse import urlparse

from catalog_utils import EXPECTED_CATEGORIES, resolve_brand

PUBLISHED_STATUS = "live_verified"
SOURCE_AUTHORITY = "assistant_verified_first_party"
PUBLISHED_AUTHORITY = "assistant_verified_source_plus_live_brand_purchase_destination"


def _same_host(left, right):
    a = urlparse(str(left or "").strip()).hostname or ""
    b = urlparse(str(right or "").strip()).hostname or ""
    return a.lower().removeprefix("www.") == b.lower().removeprefix("www.") and bool(a and b)


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
    """Return True only for offers safe for public data, SEO and Supabase."""
    if not isinstance(item, dict):
        return False
    if item.get("category") not in EXPECTED_CATEGORIES:
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
    if not _same_host(promotion, source):
        return False
    if not _same_host(source, official_domain):
        return False
    if not _same_host(purchase, official_domain):
        return False
    if not _not_expired(item):
        return False
    return True


def published_items(items):
    return [item for item in items if is_published_verified_offer(item)]
