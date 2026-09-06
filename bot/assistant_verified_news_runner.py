"""Discover active offers from assistant-verified first-party merchant pages only.

Purchase destinations are preserved from the previous canonical dataset when the
same offer is rediscovered. The pipeline must never throw away a known purchase
URL and then re-crawl discovery pages to guess another URL.
"""
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
import news_bot

ROOT = Path(__file__).resolve().parents[1]
SELECTION = ROOT / "data" / "assistant_verified_source_selection.json"
OUT = ROOT / "data" / "news.json"
EXPECTED_CATEGORIES = ["Fashion", "Electronics", "Beauty & Personal Care", "Home & Living"]
FETCH_WORKERS = 20
FETCH_TIMEOUT = 10
MAX_DISCOVERY_PAGES = 10
MAX_PAGE_LINKS = 12
HEADERS = {"User-Agent": "Deal24H/3.0 (+DEAL24H assistant-verified official offer discovery)"}
PROMO_TEXT_RE = re.compile(r"sale|offer|offers|deal|deals|promotion|promotions|discount|coupon|promo|clearance|special|save|off\b|shop now|limited time", re.I)
PROMO_PATH_RE = re.compile(r"(?:sale|offers?|deals?|promotions?|clearance|coupon|promo|specials?|discount)", re.I)
SHOP_PATH_RE = re.compile(r"/p/|/products?/|/shop(?:/|$)|/collections?/|/category/|/sale(?:/|$)|/deals?(?:/|$)|/w/|/t/|/store(?:/|$)", re.I)
COMMERCE_HOST_RE = re.compile(r"^(?:store|shop)\.", re.I)


def load_selection():
    data = json.loads(SELECTION.read_text(encoding="utf-8"))
    sources = data.get("sources", [])
    counts = data.get("counts", {})
    if data.get("total") != 120 or len(sources) != 120 or any(counts.get(c) != 30 for c in EXPECTED_CATEGORIES):
        raise SystemExit(f"ASSISTANT SOURCE GATE FAILED: counts={counts} sources={len(sources)}")
    if data.get("source_authority") != "assistant_verified_manifests" or data.get("runtime_source_identity_recheck") is not False:
        raise SystemExit("ASSISTANT SOURCE GATE FAILED: invalid authority contract")
    if not data.get("unique_merchants_per_category") or not all(x.get("verification_status") == "assistant_verified_first_party" for x in sources):
        raise SystemExit("ASSISTANT SOURCE GATE FAILED: unverified or duplicate source contract")
    return sources, counts


def host(value):
    raw = str(value or "").strip()
    if "://" not in raw:
        raw = "https://" + raw
    return (urlparse(raw).hostname or "").lower().removeprefix("www.")


def same_approved_domain(source, candidate):
    src, dst = host(source), host(candidate)
    return bool(src and dst and (dst == src or dst.endswith("." + src) or src.endswith("." + dst)))


def is_purchase_url(url):
    if not str(url or "").startswith(("https://", "http://")):
        return False
    parsed = urlparse(str(url))
    path = f"{parsed.path} {parsed.query}"
    return bool(SHOP_PATH_RE.search(path) or COMMERCE_HOST_RE.search((parsed.hostname or "").lower()))


def normalize(text):
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def tokens(text):
    return {x for x in re.findall(r"[a-z0-9%]+", normalize(text)) if len(x) > 2}


def similar(a, b, threshold=0.72):
    left, right = tokens(a), tokens(b)
    return bool(left and right and len(left & right) / max(1, len(left | right)) >= threshold)


def explicit_code(item):
    return str(item.get("code") or "").strip().upper()


def candidate_urls(source_url):
    root = f"{urlparse(source_url).scheme}://{urlparse(source_url).netloc}"
    paths = ["/sale", "/offers", "/deals", "/promotions", "/promotion", "/clearance", "/special-offers", "/specials", "/discounts", "/coupon", "/coupons", "/promo", "/collections/sale", "/collections/offers", "/collections/deals", "/shop/sale", "/shop/deals", "/shop/offers", "/store/sale", "/store/deals"]
    return list(dict.fromkeys([source_url] + [urljoin(root + "/", p.lstrip("/")) for p in paths]))


def linked_promo_urls(page_url, html, source_url):
    soup = BeautifulSoup(html, "html.parser")
    scored = []
    for anchor in soup.find_all("a", href=True):
        href = urljoin(page_url, anchor.get("href", "").strip())
        if not href.startswith(("https://", "http://")) or not same_approved_domain(source_url, href):
            continue
        text = " ".join(anchor.stripped_strings)
        combined = f"{text} {href}"
        if not PROMO_TEXT_RE.search(combined) and not PROMO_PATH_RE.search(urlparse(href).path):
            continue
        score = (4 if PROMO_TEXT_RE.search(text) else 0) + (5 if PROMO_PATH_RE.search(urlparse(href).path) else 0)
        if re.search(r"shop|buy|product|collection", text, re.I):
            score += 2
        scored.append((score, href))
    scored.sort(reverse=True)
    return [href for _, href in scored[:MAX_PAGE_LINKS]]


def fetch(url, source_url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=FETCH_TIMEOUT, allow_redirects=True)
        if response.status_code >= 400:
            return None, f"HTTP_{response.status_code}"
        if not same_approved_domain(source_url, response.url):
            return None, "REDIRECTED_OUTSIDE_APPROVED_DOMAIN"
        return response, None
    except Exception as exc:
        return None, type(exc).__name__


def fingerprint(item):
    value = {k: item.get(k) for k in ("merchant", "category", "title", "content", "code", "discount", "discovery_url")}
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:20]


def load_previous():
    try:
        data = json.loads(OUT.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def previous_purchase_url(item, previous):
    merchant = normalize(item.get("merchant"))
    category = normalize(item.get("category"))
    code = explicit_code(item)
    discount = normalize(item.get("discount"))
    best = None
    best_score = -1
    for old in previous:
        if normalize(old.get("merchant")) != merchant or normalize(old.get("category")) != category:
            continue
        url = str(old.get("final_purchase_url") or "").strip()
        if not url or not is_purchase_url(url) or not same_approved_domain(item.get("source_url"), url):
            continue
        if old.get("purchase_url_verification_status") != "live_verified":
            continue
        old_code = explicit_code(old)
        score = 0
        if code or old_code:
            if code != old_code:
                continue
            score += 100
        if discount and normalize(old.get("discount")) == discount:
            score += 30
        if normalize(old.get("title")) == normalize(item.get("title")):
            score += 50
        if similar(item.get("content"), old.get("content"), 0.72):
            score += 40
        if score > best_score:
            best_score, best = score, url
    return best if best_score >= (100 if code else 40) else ""


def collect_source(source, previous):
    source_url = source["official_homepage"]
    queue = candidate_urls(source_url)
    seen = set()
    found = []
    errors = []
    while queue and len(seen) < MAX_DISCOVERY_PAGES:
        page = queue.pop(0)
        if page in seen:
            continue
        seen.add(page)
        response, error = fetch(page, source_url)
        if error:
            errors.append(f"{page}:{error}")
            continue
        runtime_source = dict(source)
        runtime_source["url"] = source_url
        runtime_source["name"] = source["name"]
        runtime_source["merchant"] = source["merchant"]
        try:
            deals = news_bot.extract_deals(response.text, runtime_source) or []
        except Exception as exc:
            errors.append(f"{page}:PARSER_{type(exc).__name__}")
            deals = []
        for raw in deals:
            item = dict(raw)
            item.update({"merchant": source["merchant"], "category": source["category"], "country": "International", "official_source": True, "source_domain": source["domain"], "source_url": source_url, "official_homepage": source_url, "discovery_url": response.url, "source_verification_status": "assistant_verified_first_party", "source_verification_authority": "assistant", "source_verification_method": "assistant_research_manifest", "discovery_evidence": "official_first_party_page"})
            supplied = str(item.get("final_purchase_url") or item.get("purchase_url") or item.get("promotion_url") or "").strip()
            if supplied and is_purchase_url(supplied) and same_approved_domain(source_url, supplied):
                destination = supplied
            else:
                destination = previous_purchase_url(item, previous)
            if destination:
                item["final_purchase_url"] = destination
                item["promotion_url"] = destination
                item["url"] = destination
                item["purchase_url_verification_status"] = "live_verified" if any(str(x.get("final_purchase_url") or "") == destination and x.get("purchase_url_verification_status") == "live_verified" for x in previous) else None
                item["purchase_url_verification_reason"] = "preserved_previous_verified_purchase_destination" if item["purchase_url_verification_status"] == "live_verified" else "pending_live_verification_of_supplied_purchase_destination"
                item["purchase_url_verified_at"] = next((x.get("purchase_url_verified_at") for x in previous if str(x.get("final_purchase_url") or "") == destination and x.get("purchase_url_verification_status") == "live_verified"), None)
            else:
                item["final_purchase_url"] = item["promotion_url"] = item["url"] = ""
                item["purchase_url_verification_status"] = None
                item["purchase_url_verification_reason"] = "no_supplied_purchase_destination"
                item["purchase_url_verified_at"] = None
            found.append(item)
        for link in linked_promo_urls(response.url, response.text, source_url):
            if link not in seen and len(queue) < MAX_DISCOVERY_PAGES * 2:
                queue.append(link)
    return source, found, errors


def main():
    sources, counts = load_selection()
    previous = load_previous()
    all_deals = []
    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        futures = {pool.submit(collect_source, source, previous): source for source in sources}
        for future in as_completed(futures):
            source, deals, errors = future.result()
            all_deals.extend(deals)
            print(f"DISCOVERY {source['merchant']}: offers={len(deals)} fetch_issues={len(errors)}")

    deduped, seen = [], set()
    for item in all_deals:
        key = fingerprint(item)
        if key not in seen:
            seen.add(key)
            deduped.append(item)

    OUT.write_text(json.dumps(deduped, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    by_category = {c: 0 for c in EXPECTED_CATEGORIES}
    with_destination = 0
    for item in deduped:
        if item.get("category") in by_category:
            by_category[item["category"]] += 1
        if item.get("final_purchase_url"):
            with_destination += 1
    print(f"OFFER DISCOVERY COMPLETE: unique_offers={len(deduped)} category_counts={by_category} offers_with_supplied_destination={with_destination} approved_sources={len(sources)}")
    if not deduped:
        raise SystemExit("OFFER DISCOVERY FAILED: zero offers found from assistant-verified first-party sources")


if __name__ == "__main__":
    main()
