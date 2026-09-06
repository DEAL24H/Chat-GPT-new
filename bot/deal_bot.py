"""DEAL24H canonical promotion bot.

One job: find real promotions on the 120 assistant-approved first-party merchant
sources and publish only offers that have an exact purchase destination attached
to the same promotion/page.

The bot never treats a product price, cart text, navigation, policy text, or a
generic sale/product page as a promotion.
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
MAX_PROMOTIONS_PER_SOURCE = 20

HEADERS = {
    "User-Agent": "Deal24H/4.0 (+https://deal24h.net/ official promotion crawler)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

PROMO_RE = re.compile(
    r"\b(?:sale|offer|offers|deal|deals|promotion|promotions|discount|coupon|"
    r"promo|clearance|special offer|specials?|save|savings|voucher|"
    r"limited time|member (?:price|savings|offer)|bundle|"
    r"buy\s+\d+\s+get\s+\d+|buy one get one|free (?:gift|shipping|delivery|item|set)|"
    r"gift with purchase|no code required|code not required|without (?:a )?code)\b",
    re.I,
)
BENEFIT_RE = re.compile(
    r"(?:\b\d{1,3}\s*%\s*(?:off|discount)\b|"
    r"\b(?:save|off)\s+\$?\d+(?:[.,]\d+)?\b|"
    r"\$\s?\d+(?:[.,]\d+)?\s*(?:off|discount)\b|"
    r"\bbuy\s+\d+\s+get\s+\d+\b|"
    r"\bbuy one get one\b|"
    r"\bfree\s+(?:gift|shipping|delivery|item|set)\b|"
    r"\bgift with purchase\b|"
    r"\bspend\s+\$?\d+(?:[.,]\d+)?\s*(?:or more|\+)?\b|"
    r"\b(?:no code required|code not required|without (?:a )?code)\b|"
    r"\bmember (?:price|savings|offer)\b|"
    r"\bbundle\b)",
    re.I,
)
CODE_RE = re.compile(
    r"\b(?:use|enter)\s+(?:the\s+)?(?:promo(?:tion)?\s+)?code\s*[:=]?\s*['\"“”]?([A-Z0-9][A-Z0-9_-]{3,24})['\"“”]?\b",
    re.I,
)
CODE_LABEL_RE = re.compile(
    r"\b(?:promo(?:tion)? code|coupon code|voucher code|code)\s*[:=]\s*['\"“”]?([A-Z0-9][A-Z0-9_-]{3,24})['\"“”]?\b",
    re.I,
)
BAD_CODE = {
    "COPY", "CODE", "COUPON", "COUPONS", "TODAY", "DEAL", "DEALS", "SALE",
    "NEW", "SHOP", "HTTPS", "WWW", "CLICK", "VERIFY", "ACTIVE", "PROMO",
    "PROMOS", "OFFER", "OFFERS", "WITH", "ENTER", "THIS", "YOUR", "FROM",
    "ONLY", "APPLY", "HELP", "PAGE", "NEXT", "SIGN", "JOIN", "REQUIRED",
    "INTO", "SAVE", "SAVINGS", "GET", "NOW", "USE",
}
BAD_TEXT_RE = re.compile(
    r"\b(?:your cart is empty|estimated total|current price|original price|"
    r"add to wishlist|sign in|log in|create account|privacy policy|terms(?: and conditions)?|"
    r"cookie(?:s| policy)?|product advice|shipping address|billing address|"
    r"search results|compare products|recently viewed|recommended for you|"
    r"sort by|filter by|size guide|store locator|customer service|help center)\b",
    re.I,
)
CTA_RE = re.compile(
    r"\b(?:shop now|buy now|shop|buy|claim|redeem|get (?:deal|offer|code)|"
    r"view (?:deal|offer)|see (?:deal|offer)|save now|use offer|"
    r"add to (?:cart|bag)|select options|choose options|checkout)\b",
    re.I,
)
COMMERCE_PATH_RE = re.compile(
    r"/(?:p|product|products|shop|collections?|category|sale|deals?|offers?|"
    r"promotions?|promo|coupon|coupons|clearance|specials?|store|campaigns?)(?:/|$)",
    re.I,
)
BAD_PATH_RE = re.compile(
    r"/(?:privacy|legal|terms|help|faq|support|returns?|contact|about|"
    r"account|login|signin|search|wishlist)(?:/|$)",
    re.I,
)
EXPIRY_RE = re.compile(
    r"\b(?:expires?|expiry|expiration|ends?|valid until|valid through|good through|"
    r"offer ends?|ends on)\s*[:\-]?\s*"
    r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|[A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?)",
    re.I,
)
MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


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
    left, right = host(a), host(b)
    return bool(left and right and (left == right or left.endswith("." + right) or right.endswith("." + left)))


def absolute(url, base):
    value = urljoin(base, str(url or "").strip())
    return value if value.startswith(("https://", "http://")) else ""


def fetch(url, source_domain):
    last = ""
    for attempt in range(1, RETRIES + 1):
        try:
            response = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            last = f"HTTP_{response.status_code}"
            if response.status_code >= 500 or response.status_code in {403, 408, 425, 429}:
                if attempt < RETRIES:
                    time.sleep(min(2 ** (attempt - 1), 4))
                    continue
            if response.status_code >= 400:
                return None, last
            if not same_domain(response.url, source_domain):
                return None, "REDIRECTED_OUTSIDE_SOURCE"
            content_type = response.headers.get("content-type", "").lower()
            if "html" not in content_type and "xhtml" not in content_type:
                return None, "NOT_HTML"
            return response, ""
        except requests.RequestException as exc:
            last = type(exc).__name__
            if attempt < RETRIES:
                time.sleep(min(2 ** (attempt - 1), 4))
    return None, last or "FETCH_FAILED"


def parse_expiry(text):
    match = EXPIRY_RE.search(clean(text))
    if not match:
        return ""
    raw = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", match.group(1), flags=re.I)
    raw = re.sub(r"\s+", " ", raw).replace("/", "-")
    formats = (
        "%m-%d-%Y", "%m-%d-%y", "%d-%m-%Y", "%d-%m-%y",
        "%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    match2 = re.fullmatch(r"(\d{1,2}) ([A-Za-z]{3,9}) (\d{4})", raw)
    if match2 and MONTHS.get(match2.group(2).lower()):
        return datetime(
            int(match2.group(3)), MONTHS[match2.group(2).lower()], int(match2.group(1)),
            tzinfo=timezone.utc,
        ).isoformat()
    return ""


def extract_codes(text):
    found = []
    for pattern in (CODE_RE, CODE_LABEL_RE):
        for match in pattern.finditer(text):
            code = match.group(1).upper()
            if code not in BAD_CODE and code not in found:
                found.append(code)
    return found[:3]


def purchase_url_candidate(href, anchor_text, page_url, source_domain):
    url = absolute(href, page_url)
    if not url or not same_domain(url, source_domain):
        return "", 0
    parsed = urlparse(url)
    path = parsed.path or "/"
    if BAD_PATH_RE.search(path) and not COMMERCE_PATH_RE.search(path):
        return "", 0
    score = 0
    text = norm(anchor_text)
    if CTA_RE.search(text):
        score += 60
    if COMMERCE_PATH_RE.search(path):
        score += 30
    if BENEFIT_RE.search(text):
        score += 15
    if url.rstrip("/") == page_url.rstrip("/"):
        score -= 20
    if re.search(r"terms|privacy|legal|help|faq|support", text, re.I):
        score -= 25
    if score < 25:
        return "", 0
    return url, score


def extract_title(tag, text, merchant):
    headings = [
        clean(node.get_text(" ", strip=True))
        for node in tag.find_all(["h1", "h2", "h3", "h4", "strong"])
    ]
    candidates = headings + re.split(r"(?<=[.!?])\s+", text)
    for candidate in candidates:
        candidate = clean(candidate).strip(" -:|")
        if not candidate or len(candidate) < 8:
            continue
        candidate = re.sub(rf"^{re.escape(merchant)}\s*[—:-]\s*", "", candidate, flags=re.I)
        if BAD_TEXT_RE.search(candidate):
            continue
        if candidate.casefold() in {
            "sale", "sales", "deals", "offers", "offer", "promotion",
            "promotions", "discount", "clearance", "special offers", "shop sale",
        }:
            continue
        if not (BENEFIT_RE.search(candidate) or extract_codes(candidate)):
            continue
        if re.fullmatch(r"(?:\$\s*)?\d+(?:[.,]\d+)?(?:\s*%|\s*off)?", candidate, re.I):
            continue
        if len(candidate) > 140:
            candidate = candidate[:137].rsplit(" ", 1)[0] + "..."
        return candidate
    return ""


def offer_fingerprint(item):
    value = "|".join([
        norm(item.get("merchant")), norm(item.get("category")), norm(item.get("title")),
        norm(item.get("code")), norm(item.get("discount")), norm(item.get("content")),
        norm(item.get("final_purchase_url")),
    ])
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def load_previous():
    try:
        value = json.loads(OUT.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except Exception:
        return []


def previous_match(item, previous):
    best = None
    best_score = 0
    for old in previous:
        if norm(old.get("merchant")) != norm(item.get("merchant")):
            continue
        if norm(old.get("category")) != norm(item.get("category")):
            continue
        url = str(old.get("final_purchase_url") or "").strip()
        if not url or old.get("purchase_url_verification_status") != "live_verified":
            continue
        score = 0
        if norm(old.get("code")) and norm(old.get("code")) == norm(item.get("code")):
            score += 100
        if norm(old.get("discount")) and norm(old.get("discount")) == norm(item.get("discount")):
            score += 30
        if norm(old.get("title")) and norm(old.get("title")) == norm(item.get("title")):
            score += 45
        old_content = set(re.findall(r"[a-z0-9]+", norm(old.get("content"))))
        new_content = set(re.findall(r"[a-z0-9]+", norm(item.get("content"))))
        if old_content and new_content:
            score += int(35 * len(old_content & new_content) / max(1, len(new_content)))
        if score >= (100 if item.get("code") else 55) and same_domain(item.get("source_url"), url):
            best_score = max(best_score, score)
            best = url
    return best


def extract_from_page(response, source, previous):
    soup = BeautifulSoup(response.text, "html.parser")
    for node in soup(["script", "style", "noscript", "svg", "template"]):
        node.decompose()
    results = []
    seen = set()
    for tag in soup.find_all(["article", "li", "section", "div"]):
        text = clean(tag.get_text(" ", strip=True))
        if not 35 <= len(text) <= 900:
            continue
        if BAD_TEXT_RE.search(text):
            continue
        promo = bool(PROMO_RE.search(text))
        benefit = bool(BENEFIT_RE.search(text))
        codes = extract_codes(text)
        if not promo or not (benefit or codes):
            continue
        if len(re.findall(r"\b(?:sale|offer|deal|discount|coupon|save)\b", text, re.I)) > 12:
            continue

        title = extract_title(tag, text, source["merchant"])
        if not title:
            continue
        discount_match = re.search(
            r"\b\d{1,3}\s*%\s*(?:off|discount)\b|"
            r"\$\s?\d+(?:[.,]\d+)?\s*(?:off|discount)\b|"
            r"\b(?:save|off)\s+\$?\d+(?:[.,]\d+)?",
            text, re.I,
        )
        discount = discount_match.group(0) if discount_match else ""
        code = codes[0] if codes else ""
        links = []
        for anchor in tag.find_all("a", href=True):
            candidate, score = purchase_url_candidate(
                anchor.get("href"), anchor.get_text(" ", strip=True), response.url, source["domain"]
            )
            if candidate:
                links.append((score, candidate))
        links.sort(key=lambda item: (-item[0], item[1]))
        destination = links[0][1] if links else ""

        if not destination:
            path = urlparse(response.url).path
            if (PROMO_RE.search(path) or BENEFIT_RE.search(text)) and CTA_RE.search(text):
                destination = response.url
        if not destination:
            destination = previous_match(
                {
                    "merchant": source["merchant"], "category": source["category"],
                    "title": title, "code": code, "discount": discount,
                    "content": text, "source_url": source["official_homepage"],
                },
                previous,
            )
        if not destination or destination.rstrip("/") == source["official_homepage"].rstrip("/"):
            continue

        content = text[:700]
        item = {
            "id": "",
            "title": title,
            "content": content,
            "code": code,
            "discount": discount,
            "merchant": source["merchant"],
            "category": source["category"],
            "country": "International",
            "url": destination,
            "source_url": response.url,
            "promotion_url": destination,
            "final_purchase_url": destination,
            "official_homepage": source["official_homepage"],
            "source_domain": source["domain"],
            "official_source": True,
            "source_verification_status": "assistant_verified_first_party",
            "source_verification_authority": "assistant",
            "source_verification_method": "assistant_research_manifest",
            "discovery_evidence": "same_promotion_block_or_promotion_landing_page",
            "code_context": bool(code),
            "promotion_type": "coupon_code" if code else "direct_promotion",
            "detected_at": datetime.now(timezone.utc).isoformat(),
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "expires_at": parse_expiry(text),
            "status": "active",
            "verified": False,
            "offer_qualified": True,
            "purchase_url_verification_status": "pending",
            "purchase_url_verification_reason": "attached_to_same_promotion_block",
            "images": [],
            "image": "",
            "summary_type": "first_party_specific_promotion",
        }
        item["id"] = offer_fingerprint(item)
        key = (
            norm(item["merchant"]), norm(item["category"]), norm(item["code"]),
            norm(item["title"]), norm(item["final_purchase_url"]),
        )
        if key in seen:
            continue
        seen.add(key)
        results.append(item)
        if len(results) >= MAX_PROMOTIONS_PER_SOURCE:
            break
    return results


def discovery_links(response, source_domain):
    soup = BeautifulSoup(response.text, "html.parser")
    links = []
    seen = set()
    for anchor in soup.find_all("a", href=True):
        url = absolute(anchor.get("href"), response.url)
        if not url or not same_domain(url, source_domain):
            continue
        parsed = urlparse(url)
        if BAD_PATH_RE.search(parsed.path) and not COMMERCE_PATH_RE.search(parsed.path):
            continue
        text = clean(anchor.get_text(" ", strip=True))
        score = 0
        if PROMO_RE.search(text):
            score += 50
        if PROMO_RE.search(parsed.path):
            score += 45
        if BENEFIT_RE.search(text):
            score += 20
        if CTA_RE.search(text):
            score += 10
        if score < 35 or url.rstrip("/") == response.url.rstrip("/"):
            continue
        if url not in seen:
            seen.add(url)
            links.append((score, url))
    links.sort(key=lambda x: (-x[0], x[1]))
    return [url for _, url in links[: MAX_PAGES - 1]]


def collect_source(source, previous):
    source_domain = source["domain"]
    homepage = source["official_homepage"]
    queue = [homepage]
    seen_pages = set()
    offers = []
    errors = []
    while queue and len(seen_pages) < MAX_PAGES:
        page_url = queue.pop(0)
        if page_url in seen_pages:
            continue
        seen_pages.add(page_url)
        response, error = fetch(page_url, source_domain)
        if error:
            errors.append(f"{page_url}:{error}")
            continue
        offers.extend(extract_from_page(response, source, previous))
        for link in discovery_links(response, source_domain):
            if link not in seen_pages and link not in queue:
                queue.append(link)
        if len(offers) >= MAX_PROMOTIONS_PER_SOURCE:
            break
    return source, offers, errors, len(seen_pages)


def load_sources():
    data = json.loads(SELECTION.read_text(encoding="utf-8"))
    expected = {category: 30 for category in CATEGORIES}
    if (
        data.get("total") != 120
        or data.get("counts") != expected
        or data.get("source_authority") != "assistant_verified_manifests"
        or data.get("runtime_source_identity_recheck") is not False
        or not data.get("unique_merchants_per_category")
    ):
        raise SystemExit("DEAL BOT SOURCE CONTRACT FAILED")
    sources = data.get("sources", [])
    if len(sources) != 120:
        raise SystemExit("DEAL BOT SOURCE CONTRACT FAILED: expected 120 sources")
    return sources


def dedupe(items):
    chosen = {}
    for item in items:
        key = (
            norm(item.get("merchant")), norm(item.get("category")), norm(item.get("code")),
            norm(item.get("title")), norm(item.get("final_purchase_url")),
        )
        if key not in chosen:
            chosen[key] = item
    return list(chosen.values())


def main():
    sources = load_sources()
    previous = load_previous()
    all_offers = []
    status = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(collect_source, source, previous): source for source in sources}
        for future in as_completed(futures):
            source = futures[future]
            try:
                src, offers, errors, pages = future.result()
            except Exception as exc:
                src, offers, errors, pages = source, [], [f"BOT_ERROR:{type(exc).__name__}"], 0
            all_offers.extend(offers)
            status_key = f"{source['category']}::{source['merchant']}"
            status[status_key] = {
                "merchant": source["merchant"],
                "category": source["category"],
                "domain": source["domain"],
                "pages_checked": pages,
                "offers_found": len(offers),
                "errors": errors[:10],
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            print(
                f"DEAL BOT {source['category']} | {source['merchant']}: "
                f"pages={pages} offers={len(offers)} errors={len(errors)}"
            )

    final = dedupe(all_offers)
    final.sort(key=lambda item: (item.get("category", ""), norm(item.get("merchant")), norm(item.get("title"))))
    OUT.write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    category_counts = {category: 0 for category in CATEGORIES}
    for item in final:
        category_counts[item["category"]] += 1
    print(f"DEAL BOT COMPLETE: offers={len(final)} category_counts={category_counts}")
    print(f"DEAL BOT SOURCE COVERAGE: {len(status)}/120 sources scanned")
    if len(status) != 120:
        raise SystemExit(f"DEAL BOT FAILED: only {len(status)}/120 sources returned")
    if not final:
        raise SystemExit("DEAL BOT FAILED: zero qualified promotions found")


if __name__ == "__main__":
    main()
