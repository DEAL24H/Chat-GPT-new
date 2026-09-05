import json
import re
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "news.json"
CATALOG = ROOT / "data" / "brand_catalog.json"
TIMEOUT = 15
UA = "Mozilla/5.0 (compatible; Deal24HOfferLinkValidator/2.0; +https://deal24h.net/)"
SHOP_PATH_RE = re.compile(r"/p/|/products?/|/shop(?:/|$)|/collections?/|/category/|/sale(?:/|$)|/deals?(?:/|$)|/w/|/t/|/store(?:/|$)", re.I)
BAD_PATH_RE = re.compile(r"terms|terms.?conditions|privacy|legal|help|faq|promotion|promotions|conditions|returns|support|promo.?terms|product-advice", re.I)
COMMERCE_HOST_RE = re.compile(r"^(?:store|shop)\.", re.I)
CTA_RE = re.compile(r"\b(add to cart|buy now|shop now|add to bag|purchase|select options|choose options|checkout|shop)\b", re.I)


def host(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else "https://" + raw)
    return (parsed.hostname or "").lower().removeprefix("www.")


def is_purchase_url(value):
    if not str(value or "").startswith(("https://", "http://")):
        return False
    parsed = urlparse(str(value))
    path = f"{parsed.path} {parsed.query}"
    if BAD_PATH_RE.search(path) and not SHOP_PATH_RE.search(path):
        return False
    return bool(SHOP_PATH_RE.search(path) or COMMERCE_HOST_RE.search((parsed.hostname or "").lower()))


def same_official_domain(source, destination):
    src, dst = host(source), host(destination)
    return bool(src and dst and (dst == src or dst.endswith("." + src) or src.endswith("." + dst)))


def tokens(text):
    return {x for x in re.findall(r"[a-z0-9]+", str(text or "").lower()) if len(x) >= 4}


def discount_percent(text):
    m = re.search(r"\b(\d{1,3})\s*%\s*(?:off|discount)\b", str(text or ""), re.I)
    return int(m.group(1)) if m else None


def live_destination(item):
    url = str(item.get("final_purchase_url") or "").strip()
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"}, timeout=TIMEOUT, allow_redirects=True)
    except Exception as exc:
        return False, f"DESTINATION_REQUEST_FAILED:{type(exc).__name__}", ""
    final = r.url
    if r.status_code >= 400:
        return False, f"DESTINATION_HTTP_{r.status_code}", final
    if not same_official_domain(item.get("source_url"), final):
        return False, "DESTINATION_REDIRECTED_OUTSIDE_OFFICIAL_DOMAIN", final
    if not is_purchase_url(final) or final == item.get("source_url"):
        return False, "DESTINATION_NOT_A_PURCHASE_PAGE", final
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text(" ", strip=True)[:160000]
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    signals = []
    if SHOP_PATH_RE.search(f"{urlparse(final).path} {urlparse(final).query}"):
        signals.append("commerce_path")
    if CTA_RE.search(text):
        signals.append("purchase_cta")
    if re.search(r"\$|€|£|¥|\b(?:USD|EUR|GBP|CAD|AUD)\b", text):
        signals.append("price_signal")
    if not signals:
        return False, "NO_COMMERCE_OR_PURCHASE_SIGNAL", final
    item_text = str(item.get("content") or "")
    source_terms = tokens(f"{item.get('title','')} {item_text}")
    destination_terms = tokens(f"{title} {text}")
    overlap = len(source_terms & destination_terms)
    if source_terms and overlap == 0:
        return False, "DESTINATION_HAS_NO_OFFER_CONTENT_OVERLAP", final
    expected_pct = discount_percent(f"{item.get('discount','')} {item_text} {item.get('title','')}")
    destination_pct = discount_percent(text)
    if expected_pct is not None and destination_pct is not None and expected_pct != destination_pct:
        return False, f"DISCOUNT_MISMATCH_EXPECTED_{expected_pct}_FOUND_{destination_pct}", final
    return True, "LIVE_PURCHASE_PAGE_VERIFIED", final


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    catalog = json.loads(CATALOG.read_text(encoding="utf-8")).get("categories", {})
    catalog_domains = {}
    for entries in catalog.values():
        for entry in entries:
            name = str(entry.get("name", "")).strip().casefold()
            if name:
                catalog_domains[name] = str(entry.get("domain", "")).strip()

    if not isinstance(data, list):
        raise SystemExit("news.json is not a list")
    errors = []
    verified = 0
    for item in data:
        merchant = str(item.get("merchant") or "").strip()
        destination = str(item.get("final_purchase_url") or "").strip()
        source = str(item.get("source_url") or "").strip()
        catalog_domain = catalog_domains.get(merchant.casefold(), "")
        if not is_purchase_url(destination):
            errors.append(f"{merchant} {item.get('code') or 'DEAL'}: non-purchase destination {destination}")
            continue
        if item.get("promotion_url") != destination or item.get("url") != destination:
            errors.append(f"{merchant}: duplicate destination fields are inconsistent")
        if not source.startswith(("https://", "http://")):
            errors.append(f"{merchant}: invalid source_url")
            continue
        if not same_official_domain(source, destination):
            errors.append(f"{merchant} {item.get('code') or 'DEAL'}: destination leaves source's official domain: {destination}")
            continue
        if catalog_domain and not same_official_domain(catalog_domain, destination):
            errors.append(f"{merchant} {item.get('code') or 'DEAL'}: destination leaves catalog official domain: {destination}")
            continue
        if source == destination:
            errors.append(f"{merchant} {item.get('code') or 'DEAL'}: final_purchase_url is still the program/source page")
            continue
        ok, reason, final_url = live_destination(item)
        if not ok:
            errors.append(f"{merchant} {item.get('code') or 'DEAL'}: {reason}: {final_url}")
            continue
        verified += 1
    if errors:
        print(f"OFFER LINK VALIDATION FAILED: errors={len(errors)} live_verified={verified}")
        for error in errors[:100]:
            print(error)
        raise SystemExit(1)
    print(f"OFFER LINK VALIDATION OK: offers={len(data)} live_verified={verified}; destinations are live, official-domain and purchase-capable")


if __name__ == "__main__":
    main()
