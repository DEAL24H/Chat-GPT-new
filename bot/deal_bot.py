"""DEAL24H promotion discovery bot.

This bot has one responsibility: find real, current promotion programs on the
120 approved first-party merchant sites. It publishes nothing unless the page
contains clear promotion evidence and an exact same-promotion purchase URL.
"""
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
SELECTION = ROOT / "data" / "assistant_verified_source_selection.json"
OUT = ROOT / "data" / "news.json"
CATEGORIES = ["Fashion", "Electronics", "Beauty & Personal Care", "Home & Living"]
WORKERS = 12
TIMEOUT = 15
RETRIES = 3
MAX_PAGES = 10
MAX_OFFERS = 20

HEADERS = {
    "User-Agent": "Deal24H/5.0 (+https://deal24h.net/ official promotion crawler)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

PROMO_RE = re.compile(
    r"\b(?:sale|offer|offers|deal|deals|promotion|promotions|discount|coupon|promo|"
    r"clearance|special offer|specials?|savings|voucher|limited time|member (?:price|savings|offer)|"
    r"buy\s+\d+\s+get\s+\d+|buy one get one|free (?:gift|shipping|delivery|item|set)|"
    r"gift with purchase|no code required|code not required|without (?:a )?code)\b", re.I)
BENEFIT_RE = re.compile(
    r"(?:\b\d{1,3}\s*%\s*(?:off|discount)\b|\b(?:save|off)\s+\$?\d+(?:[.,]\d+)?\b|"
    r"\$\s?\d+(?:[.,]\d+)?\s*(?:off|discount)\b|\bbuy\s+\d+\s+get\s+\d+\b|"
    r"\bbuy one get one\b|\bfree\s+(?:gift|shipping|delivery|item|set)\b|"
    r"\bgift with purchase\b|\bspend\s+\$?\d+(?:[.,]\d+)?\s*(?:or more|\+)?\b|"
    r"\b(?:no code required|code not required|without (?:a )?code)\b|"
    r"\bmember (?:price|savings|offer)\b|\bbundle\b)", re.I)
CODE_RE = re.compile(
    r"\b(?:promo(?:tion)?\s+code|coupon code|voucher code|discount code|code)\s*[:=\-]?\s*"
    r"['\"“”]?([A-Z0-9][A-Z0-9_-]{3,24})['\"“”]?\b", re.I)
BAD_CODE = {
    "COPY", "CODE", "COUPON", "TODAY", "DEAL", "DEALS", "SALE", "SHOP", "CLICK", "VERIFY",
    "ACTIVE", "PROMO", "PROMOS", "OFFER", "OFFERS", "ENTER", "THIS", "YOUR", "FROM",
    "ONLY", "APPLY", "HELP", "PAGE", "NEXT", "SIGN", "JOIN", "REQUIRED", "INTO", "SAVE",
    "SAVINGS", "GET", "NOW", "USE", "DISCOUNT", "WITH",
}
BAD_TEXT_RE = re.compile(
    r"\b(?:your cart is empty|estimated total|current price|original price|sale price|"
    r"add to wishlist|sign in|log in|create account|privacy policy|terms(?: and conditions)?|"
    r"cookie(?:s| policy)?|product advice|shipping address|billing address|search results|"
    r"compare products|recently viewed|recommended for you|sort by|filter by|size guide|"
    r"store locator|customer service|help center|shopping cart|checkout|quantity|subtotal|"
    r"free returns|shipping address|billing information)\b", re.I)
BAD_TITLE_RE = re.compile(
    r"^(?:\$?\s*\d+(?:[.,]\d+)?(?:\s*%|\s*off)?|current price.*|original price.*|"
    r"(?:product|item)\s*\d*|sale|sales|deals?|offers?|promotions?|discounts?|clearance)$", re.I)
CTA_RE = re.compile(
    r"\b(?:shop now|buy now|shop|buy|claim|redeem|get (?:deal|offer|code)|view (?:deal|offer)|"
    r"see (?:deal|offer)|save now|use offer|add to (?:cart|bag)|select options|choose options)\b", re.I)
PROMO_PATH_RE = re.compile(r"/(?:sale|deals?|offers?|promotions?|promo|coupon|coupons|clearance|specials?|campaigns?)(?:/|$)", re.I)
BAD_PATH_RE = re.compile(r"/(?:privacy|legal|terms|help|faq|support|returns?|contact|about|account|login|signin|search|wishlist)(?:/|$)", re.I)
EXPIRY_RE = re.compile(
    r"\b(?:expires?|expiry|expiration|ends?|valid until|valid through|good through|offer ends?|ends on)\s*[:\-]?\s*"
    r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|[A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?)", re.I)
MONTHS = {m: i for i, m in enumerate(("x","jan","feb","mar","apr","may","jun","jul","aug","sep","oct","nov","dec")) if i}


def clean(value):
    return re.sub(r"\s+", " ", BeautifulSoup(str(value or ""), "html.parser").get_text(" ", strip=True)).strip()


def norm(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def host(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw
    return (urlparse(raw).hostname or "").lower().removeprefix("www.")


def same_domain(a, b):
    x, y = host(a), host(b)
    return bool(x and y and (x == y or x.endswith("." + y) or y.endswith("." + x)))


def absolute(href, base):
    value = urljoin(base, str(href or "").strip())
    return value if value.startswith(("https://", "http://")) else ""


def fetch(url, domain):
    last = "FETCH_FAILED"
    for attempt in range(RETRIES):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            last = f"HTTP_{r.status_code}"
            if r.status_code in {403, 408, 425, 429} or r.status_code >= 500:
                if attempt + 1 < RETRIES:
                    time.sleep(2 ** attempt)
                    continue
            if r.status_code >= 400:
                return None, last
            if not same_domain(r.url, domain):
                return None, "REDIRECTED_OUTSIDE_SOURCE"
            if "html" not in r.headers.get("content-type", "").lower():
                return None, "NOT_HTML"
            return r, ""
        except requests.RequestException as exc:
            last = type(exc).__name__
            if attempt + 1 < RETRIES:
                time.sleep(2 ** attempt)
    return None, last


def codes(text):
    found = []
    for m in CODE_RE.finditer(text):
        value = m.group(1).upper()
        if value not in BAD_CODE and value not in found:
            found.append(value)
    return found[:2]


def expiry(text):
    m = EXPIRY_RE.search(clean(text))
    if not m:
        return ""
    raw = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", m.group(1), flags=re.I).replace("/", "-")
    for fmt in ("%m-%d-%Y", "%m-%d-%y", "%d-%m-%Y", "%d-%m-%y", "%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    m2 = re.fullmatch(r"(\d{1,2}) ([A-Za-z]{3,9}) (\d{4})", raw)
    if m2 and m2.group(2).lower() in MONTHS:
        return datetime(int(m2.group(3)), MONTHS[m2.group(2).lower()], int(m2.group(1)), tzinfo=timezone.utc).isoformat()
    return ""


def title_for(block, text):
    candidates = [clean(x.get_text(" ", strip=True)) for x in block.find_all(["h1", "h2", "h3", "h4", "strong"])]
    candidates += re.split(r"(?<=[.!?])\s+", text)
    for value in candidates:
        value = re.sub(r"\s+", " ", value).strip(" -:|")
        if len(value) < 10 or len(value) > 180 or BAD_TEXT_RE.search(value) or BAD_TITLE_RE.fullmatch(value):
            continue
        if not (BENEFIT_RE.search(value) or codes(value)):
            continue
        if not PROMO_RE.search(value) and not codes(value):
            continue
        return value[:177].rsplit(" ", 1)[0] + "..." if len(value) > 180 else value
    return ""


def purchase_candidate(anchor, page_url, domain):
    url = absolute(anchor.get("href"), page_url)
    if not url or not same_domain(url, domain):
        return "", 0
    path = urlparse(url).path or "/"
    if BAD_PATH_RE.search(path) and not PROMO_PATH_RE.search(path):
        return "", 0
    text = clean(anchor.get_text(" ", strip=True))
    score = 0
    if CTA_RE.search(text): score += 60
    if PROMO_RE.search(text): score += 25
    if BENEFIT_RE.search(text): score += 20
    if PROMO_PATH_RE.search(path): score += 30
    if url.rstrip("/") == page_url.rstrip("/"): score -= 20
    return (url, score) if score >= 50 else ("", 0)


def extract_page(response, source):
    soup = BeautifulSoup(response.text, "html.parser")
    for node in soup(["script", "style", "noscript", "svg", "template", "nav", "footer", "header"]):
        node.decompose()
    results, seen = [], set()
    page_is_promo = bool(PROMO_PATH_RE.search(urlparse(response.url).path))
    blocks = soup.find_all(["article", "li", "section"])
    blocks += soup.find_all(["div"], class_=re.compile(r"promo|offer|deal|sale|coupon|discount|campaign", re.I))
    if not blocks and page_is_promo:
        blocks = [soup.body or soup]
    for block in blocks:
        text = clean(block.get_text(" ", strip=True))
        if not 35 <= len(text) <= 1000 or BAD_TEXT_RE.search(text):
            continue
        found_codes = codes(text)
        has_benefit = bool(BENEFIT_RE.search(text))
        has_promo = bool(PROMO_RE.search(text))
        if not has_promo or not (has_benefit or found_codes):
            continue
        title = title_for(block, text)
        if not title:
            continue
        links = []
        for a in block.find_all("a", href=True):
            url, score = purchase_candidate(a, response.url, source["domain"])
            if url:
                links.append((score, url))
        links.sort(key=lambda x: (-x[0], x[1]))
        destination = links[0][1] if links else (response.url if page_is_promo and CTA_RE.search(text) else "")
        if not destination or destination.rstrip("/") == source["official_homepage"].rstrip("/"):
            continue
        code = found_codes[0] if found_codes else ""
        discount_match = re.search(r"\b\d{1,3}\s*%\s*(?:off|discount)\b|\$\s?\d+(?:[.,]\d+)?\s*(?:off|discount)\b|\b(?:save|off)\s+\$?\d+(?:[.,]\d+)?", text, re.I)
        discount = discount_match.group(0) if discount_match else ""
        item = {
            "id": "", "title": title, "content": text[:700], "code": code, "discount": discount,
            "merchant": source["merchant"], "category": source["category"], "country": "International",
            "url": destination, "source_url": response.url, "promotion_url": destination,
            "final_purchase_url": destination, "official_homepage": source["official_homepage"],
            "source_domain": source["domain"], "official_source": True,
            "source_verification_status": "assistant_verified_first_party",
            "source_verification_authority": "assistant", "source_verification_method": "assistant_research_manifest",
            "discovery_evidence": "specific_promotion_block", "code_context": bool(code),
            "promotion_type": "coupon_code" if code else "direct_promotion",
            "detected_at": datetime.now(timezone.utc).isoformat(), "last_checked": datetime.now(timezone.utc).isoformat(),
            "expires_at": expiry(text), "status": "active", "verified": False, "offer_qualified": True,
            "purchase_url_verification_status": "pending", "purchase_url_verification_reason": "same_promotion_block",
            "images": [], "image": "", "summary_type": "first_party_specific_promotion",
        }
        item["id"] = hashlib.sha256("|".join(norm(item[k]) for k in ("merchant", "category", "title", "code", "discount", "final_purchase_url")).encode()).hexdigest()[:20]
        key = (norm(item["merchant"]), norm(item["category"]), norm(item["code"]), norm(item["title"]), norm(item["final_purchase_url"]))
        if key in seen:
            continue
        seen.add(key)
        results.append(item)
        if len(results) >= MAX_OFFERS:
            break
    return results


def discovery_links(response, domain):
    soup = BeautifulSoup(response.text, "html.parser")
    found, seen = [], set()
    for a in soup.find_all("a", href=True):
        url = absolute(a.get("href"), response.url)
        if not url or not same_domain(url, domain):
            continue
        path, text = urlparse(url).path, clean(a.get_text(" ", strip=True))
        if BAD_PATH_RE.search(path) and not PROMO_PATH_RE.search(path):
            continue
        score = (50 if PROMO_RE.search(text) else 0) + (45 if PROMO_PATH_RE.search(path) else 0) + (20 if BENEFIT_RE.search(text) else 0)
        if score >= 45 and url.rstrip("/") != response.url.rstrip("/") and url not in seen:
            seen.add(url); found.append((score, url))
    found.sort(key=lambda x: (-x[0], x[1]))
    return [u for _, u in found[:MAX_PAGES - 1]]


def collect(source):
    queue, seen_pages, offers, errors = [source["official_homepage"]], set(), [], []
    while queue and len(seen_pages) < MAX_PAGES and len(offers) < MAX_OFFERS:
        page = queue.pop(0)
        if page in seen_pages: continue
        seen_pages.add(page)
        response, error = fetch(page, source["domain"])
        if error:
            errors.append(f"{page}:{error}"); continue
        offers.extend(extract_page(response, source))
        for link in discovery_links(response, source["domain"]):
            if link not in seen_pages and link not in queue: queue.append(link)
    return source, offers, errors, len(seen_pages)


def load_sources():
    data = json.loads(SELECTION.read_text(encoding="utf-8"))
    if data.get("total") != 120 or data.get("counts") != {c: 30 for c in CATEGORIES} or data.get("source_authority") != "assistant_verified_manifests" or data.get("runtime_source_identity_recheck") is not False or not data.get("unique_merchants_per_category"):
        raise SystemExit("DEAL BOT SOURCE CONTRACT FAILED")
    sources = data.get("sources", [])
    if len(sources) != 120:
        raise SystemExit("DEAL BOT SOURCE CONTRACT FAILED: expected 120 sources")
    return sources


def valid(item):
    title, content = str(item.get("title") or ""), str(item.get("content") or "")
    code = str(item.get("code") or "")
    destination, source = str(item.get("final_purchase_url") or ""), str(item.get("source_url") or "")
    if not title or BAD_TITLE_RE.fullmatch(title) or BAD_TEXT_RE.search(title) or BAD_TEXT_RE.search(content): return False
    if not PROMO_RE.search(f"{title} {content}"): return False
    if not BENEFIT_RE.search(f"{title} {content}") and not code: return False
    if code and (len(code) < 4 or code.upper() in BAD_CODE): return False
    if not destination or not source or destination.rstrip("/") == source.rstrip("/"): return False
    return True


def main():
    sources = load_sources()
    all_offers, status = [], {}
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(collect, source): source for source in sources}
        for future in as_completed(futures):
            source = futures[future]
            try: src, offers, errors, pages = future.result()
            except Exception as exc: src, offers, errors, pages = source, [], [f"BOT_ERROR:{type(exc).__name__}"], 0
            offers = [x for x in offers if valid(x)]
            all_offers.extend(offers)
            key = f"{src['category']}::{src['merchant']}"
            status[key] = {"merchant": src["merchant"], "category": src["category"], "pages_checked": pages, "offers_found": len(offers), "errors": errors[:10], "checked_at": datetime.now(timezone.utc).isoformat()}
            print(f"DEAL BOT {src['category']} | {src['merchant']}: pages={pages} offers={len(offers)} errors={len(errors)}")
    chosen = {}
    for item in all_offers:
        key = (norm(item["merchant"]), norm(item["category"]), norm(item["code"]), norm(item["title"]), norm(item["final_purchase_url"]))
        chosen.setdefault(key, item)
    final = sorted(chosen.values(), key=lambda x: (x["category"], norm(x["merchant"]), norm(x["title"])))
    OUT.write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    counts = {c: sum(1 for x in final if x["category"] == c) for c in CATEGORIES}
    print(f"DEAL BOT COMPLETE: offers={len(final)} category_counts={counts}")
    print(f"DEAL BOT SOURCE COVERAGE: {len(status)}/120 sources scanned")
    if len(status) != 120: raise SystemExit(f"DEAL BOT FAILED: only {len(status)}/120 sources returned")
    if not final: raise SystemExit("DEAL BOT FAILED: zero qualified promotions found")
    if any(not valid(x) for x in final): raise SystemExit("DEAL BOT FAILED: invalid record escaped final filter")


if __name__ == "__main__":
    main()
