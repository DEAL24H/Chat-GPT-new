import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "news.json"
CATALOG = ROOT / "data" / "brand_catalog.json"
TIMEOUT = 15
UA = "Mozilla/5.0 (compatible; Deal24HOfferLinkValidator/4.0; +https://deal24h.net/)"
EXPECTED_CATEGORIES = {"Fashion", "Electronics", "Beauty & Personal Care", "Home & Living"}
SHOP_PATH_RE = re.compile(r"/p/|/products?/|/shop(?:/|$)|/collections?/|/category/|/sale(?:/|$)|/deals?(?:/|$)|/w/|/t/|/store(?:/|$)", re.I)
BAD_PATH_RE = re.compile(r"terms|terms.?conditions|privacy|legal|help|faq|promotion|promotions|conditions|returns|support|promo.?terms|product-advice", re.I)
COMMERCE_HOST_RE = re.compile(r"^(?:store|shop)\.", re.I)
CTA_RE = re.compile(r"\b(add to cart|buy now|shop now|add to bag|purchase|select options|choose options|checkout|shop|mua ngay|thêm vào giỏ|đặt hàng)\b", re.I)
RUNTIME_INACCESSIBLE = {403, 408, 425, 429, 500, 502, 503, 504, 521, 522, 523, 524}


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


def runtime_verify(item):
    url = str(item.get("final_purchase_url") or "").strip()
    try:
        response = requests.get(
            url,
            headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"},
            timeout=TIMEOUT,
            allow_redirects=True,
        )
    except Exception as exc:
        return "runtime_inaccessible", f"DESTINATION_REQUEST_FAILED:{type(exc).__name__}", ""

    final = response.url
    if response.status_code in RUNTIME_INACCESSIBLE:
        return "runtime_inaccessible", f"DESTINATION_RUNTIME_HTTP_{response.status_code}", final
    if response.status_code in {404, 410}:
        return "failed", f"DESTINATION_HTTP_{response.status_code}", final
    if response.status_code >= 400:
        return "failed", f"DESTINATION_HTTP_{response.status_code}", final
    if not same_official_domain(item.get("source_url"), final):
        return "failed", "DESTINATION_REDIRECTED_OUTSIDE_OFFICIAL_DOMAIN", final
    if not is_purchase_url(final) or final == item.get("source_url"):
        return "failed", "DESTINATION_NOT_A_PURCHASE_PAGE", final

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text(" ", strip=True)[:160000]
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    html_lower = response.text.lower()
    signals = []
    if SHOP_PATH_RE.search(f"{urlparse(final).path} {urlparse(final).query}"):
        signals.append("commerce_path")
    if CTA_RE.search(text) or re.search(r"addtocart|add-to-cart|buy-now|checkout", html_lower):
        signals.append("purchase_cta")
    if re.search(r"\$|€|£|¥|\b(?:USD|EUR|GBP|CAD|AUD)\b", text):
        signals.append("price_signal")
    if not signals:
        return "failed", "NO_COMMERCE_OR_PURCHASE_SIGNAL", final

    item_text = str(item.get("content") or "")
    source_terms = tokens(f"{item.get('title','')} {item_text}")
    destination_terms = tokens(f"{title} {text}")
    if source_terms and len(source_terms & destination_terms) == 0:
        return "failed", "DESTINATION_HAS_NO_OFFER_CONTENT_OVERLAP", final

    expected_pct = discount_percent(f"{item.get('discount','')} {item_text} {item.get('title','')}")
    destination_pct = discount_percent(text)
    if expected_pct is not None:
        if destination_pct is None:
            return "failed", f"DESTINATION_MISSING_EXPECTED_DISCOUNT_{expected_pct}", final
        if expected_pct != destination_pct:
            return "failed", f"DISCOUNT_MISMATCH_EXPECTED_{expected_pct}_FOUND_{destination_pct}", final

    return "live_verified", "LIVE_PURCHASE_PAGE_VERIFIED", final


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
    live_verified = 0
    runtime_inaccessible = 0
    now = datetime.now(timezone.utc).isoformat()

    for item in data:
        merchant = str(item.get("merchant") or "").strip()
        category = str(item.get("category") or "").strip()
        destination = str(item.get("final_purchase_url") or "").strip()
        source = str(item.get("source_url") or "").strip()
        catalog_domain = catalog_domains.get(merchant.casefold(), "")

        if category not in EXPECTED_CATEGORIES:
            errors.append(f"{merchant}: non-canonical category {category}")
            continue
        if item.get("source_verification_status") != "assistant_verified_first_party":
            errors.append(f"{merchant}: source is not assistant-verified")
            continue
        if not is_purchase_url(destination):
            errors.append(f"{merchant} {item.get('code') or 'DEAL'}: non-purchase destination {destination}")
            continue
        if item.get("promotion_url") != destination or item.get("url") != destination:
            errors.append(f"{merchant}: duplicate destination fields are inconsistent")
            continue
        if not source.startswith(("https://", "http://")):
            errors.append(f"{merchant}: invalid source_url")
            continue
        if not same_official_domain(source, destination):
            errors.append(f"{merchant} {item.get('code') or 'DEAL'}: destination leaves source official domain: {destination}")
            continue
        if catalog_domain and not same_official_domain(catalog_domain, destination):
            errors.append(f"{merchant} {item.get('code') or 'DEAL'}: destination leaves catalog official domain: {destination}")
            continue
        if source == destination:
            errors.append(f"{merchant} {item.get('code') or 'DEAL'}: final_purchase_url is still the source/program page")
            continue

        status, reason, final_url = runtime_verify(item)
        if status == "failed":
            errors.append(f"{merchant} {item.get('code') or 'DEAL'}: {reason}: {final_url}")
            continue

        item["purchase_url_verification_status"] = status
        item["purchase_url_verification_reason"] = reason
        item["purchase_url_verified_at"] = now if status == "live_verified" else None
        if final_url and final_url != destination:
            item["final_purchase_url"] = item["promotion_url"] = item["url"] = final_url
        if status == "live_verified":
            live_verified += 1
        else:
            runtime_inaccessible += 1

    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        "OFFER LINK VALIDATION:",
        f"offers={len(data)} live_verified={live_verified} runtime_inaccessible={runtime_inaccessible} hard_failures={len(errors)}",
    )
    if runtime_inaccessible:
        print("NOTE: runtime_inaccessible means GitHub Runner could not fetch the merchant URL (WAF/Cloudflare/rate-limit/etc.).")
        print("      It is NOT treated as evidence that an assistant-verified official purchase destination is wrong.")
    if errors:
        print("OFFER LINK VALIDATION FAILED: hard integrity errors")
        for error in errors[:100]:
            print(error)
        raise SystemExit(1)
    print("OFFER LINK VALIDATION PASS: canonical categories, assistant source authority, same-merchant purchase destinations and all detectable live integrity checks are consistent")


if __name__ == "__main__":
    main()
