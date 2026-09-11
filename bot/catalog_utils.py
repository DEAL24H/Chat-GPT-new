import json
import re
from bot.seo_market_scope import market_info
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "brand_catalog.json"
EXPECTED_CATEGORIES = ("Fashion", "Electronics", "Beauty & Personal Care", "Home & Living")
PUBLISHED_STATUS = "live_verified"
SOURCE_AUTHORITY = "assistant_verified_first_party"
PUBLISHED_AUTHORITY = "assistant_verified_source_plus_live_brand_purchase_destination"
VISIBLE_NOISE = re.compile(r"(?:your cart is empty|estimated total|current price|regular price|original price|add to wishlist|add to cart|checkout|\bcart\b|sign in|log in|login|create account|privacy policy|terms(?: and conditions)?|cookie(?:s| policy)?|product advice|shipping address|billing address|search results|compare products|recently viewed|recommended for you|sort by|filter by|size guide|store locator|customer service|help center|amazon devices small business deals)", re.I)

def _indexable_text(value):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    previous = None
    while text and text != previous:
        previous = text
        text = VISIBLE_NOISE.sub(" ", text)
        text = re.sub(r"\s*[|•·]+\s*", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
    return text

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
            BRAND_INDEX[normalize_brand(name)] = {"name": name, "category": category, "domain": str(entry.get("domain", "")).strip()}

def resolve_brand(value): return BRAND_INDEX.get(normalize_brand(value))
def canonical_brand_name(value):
    hit = resolve_brand(value); return hit["name"] if hit else str(value or "").strip()
def category_for_brand(value):
    hit = resolve_brand(value); return hit["category"] if hit else ""
def canonicalize_item(item):
    item = dict(item); hit = resolve_brand(item.get("merchant"))
    if hit: item["merchant"], item["category"] = hit["name"], hit["category"]
    return item
def brand_slug(value): return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower().replace("&", " and ").replace("'", "")).strip("-")
def _host(value):
    raw = str(value or "").strip()
    if not raw: return ""
    parsed = urlparse(raw if "://" in raw else "https://" + raw)
    return (parsed.hostname or "").lower().removeprefix("www.")
def _same_host(left, right):
    a,b=_host(left),_host(right)
    return bool(a and b) and (a==b or a.endswith("."+b) or b.endswith("."+a))
def _not_expired(item):
    if str(item.get("status","active")).lower() in {"expired","inactive"}: return False
    raw=str(item.get("expires_at","")).strip()
    if not raw: return True
    try:
        dt=datetime.fromisoformat(raw.replace("Z","+00:00"))
        if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
        return dt>datetime.now(timezone.utc)
    except ValueError: return False

def is_brand_host_allowed(merchant, value):
    """Single canonical host policy: catalog domain or configured country-market host."""
    hit = resolve_brand(merchant)
    h = _host(value)
    if not hit or not h:
        return False
    if _same_host(h, hit.get("domain", "")):
        return True
    from bot.merchant_country_registry import allowed_hosts_for
    return h in allowed_hosts_for(hit["name"])

def _brand_allowed_host(merchant, host):
    return is_brand_host_allowed(merchant, host)

def is_published_verified_offer(item):
    if not isinstance(item,dict) or item.get("category") not in EXPECTED_CATEGORIES: return False
    brand=resolve_brand(item.get("merchant"))
    if not brand or brand.get("category")!=item.get("category"): return False
    if item.get("offer_qualified") is not True or item.get("official_source") is not True: return False
    if item.get("source_verification_status")!=SOURCE_AUTHORITY: return False
    if item.get("purchase_url_verification_status") not in {PUBLISHED_STATUS,"official_destination_pending"}: return False
    if item.get("published_offer_authority")!=PUBLISHED_AUTHORITY: return False
    source=str(item.get("source_url") or "").strip(); promotion=str(item.get("promotion_url") or "").strip(); purchase=str(item.get("final_purchase_url") or "").strip(); url=str(item.get("url") or "").strip()
    official_domain=str(brand.get("domain") or "").strip()
    if not source or not promotion or not purchase or url!=purchase or not official_domain: return False
    if not _same_host(promotion,source): return False
    if not is_brand_host_allowed(brand["name"],source): return False
    if not is_brand_host_allowed(brand["name"],purchase): return False
    return _not_expired(item)

def has_indexable_content(item):
    title = _indexable_text(item.get("title")); content = _indexable_text(item.get("content"))
    merchant = _indexable_text(item.get("merchant"))
    title = re.sub(rf"^{re.escape(merchant)}\s*[—:-]\s*", "", title, flags=re.I)
    if not title or len(title) < 8 or not content or not str(item.get("final_purchase_url") or "").strip(): return False
    if re.fullmatch(r"(?:\$\s*)?\d+(?:[.,]\d+)?(?:\s*%|\s*off)?", title, re.I): return False
    return True

def is_indexable_offer(item):
    """Single final gate shared by every public publication layer."""
    return is_published_verified_offer(item) and has_indexable_content(item)

def publication_key(item):
    """Identity used to deduplicate equivalent offers in every output layer."""
    title=_indexable_text(item.get('title')); merchant=_indexable_text(item.get('merchant'))
    title=re.sub(rf'^{re.escape(merchant)}\s*[—:-]\s*','',title,flags=re.I)
    info=market_info(item)
    return '|'.join((merchant,title,str(item.get('code') or '').strip(),str(item.get('final_purchase_url') or '').strip(),_indexable_text(item.get('discount')), _indexable_text(item.get('content')),info['scope'],','.join(info['countries'])))

def is_active_offer(item): return is_published_verified_offer(item)
def published_items(items): return [item for item in items if is_published_verified_offer(item)]
