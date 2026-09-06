import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "news.json"
EXPECTED_CATEGORIES = {"Fashion", "Electronics", "Beauty & Personal Care", "Home & Living"}
HEADERS = {"User-Agent": "Deal24H/3.0 (+DEAL24H exact official offer destination resolver)"}
TIMEOUT = 12
WORKERS = 20
CODE_RE = re.compile(r"\b(?:code|promo code|coupon code|use code|enter (?:the )?(?:promo )?code)\s*[:\-]?\s*([A-Z0-9][A-Z0-9_-]{3,})\b", re.I)
CODE_TOKEN_RE = re.compile(r"\b[A-Z]{2,}\d[A-Z0-9_-]{2,}\b")
SHOP_PATH_RE = re.compile(r"/p/|/products?/|/shop(?:/|$)|/collections?/|/category/|/sale(?:/|$)|/deals?(?:/|$)|/w/|/t/|/store(?:/|$)", re.I)
BAD_RE = re.compile(r"\b(?:terms|terms.?conditions|privacy|legal|help|faq|conditions|returns|support|promo.?terms|product-advice)\b", re.I)
COMMERCE_HOST_RE = re.compile(r"^(?:store|shop)\.", re.I)
BAD_CODES = {"WILL","CODE","COUPON","COUPONS","TODAY","DEAL","DEALS","SALE","NEW","SHOP","HTTPS","WWW","CLICK","VERIFY","ACTIVE","PROMO","PROMOS","OFFER","OFFERS","WITH","ENTER","THIS","YOUR","FROM","ONLY","APPLY","HELP","PAGE","NEXT","SIGN","JOIN","REQUIRED","INTO"}


def load():
    try:
        value = json.loads(OUT.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except Exception:
        return []


def normalize(text):
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def tokens(text):
    return {x for x in re.findall(r"[a-z0-9%]+", normalize(text)) if len(x) > 2}


def similar(a, b, threshold=0.68):
    left, right = tokens(a), tokens(b)
    return bool(left and right and len(left & right) / max(1, len(left | right)) >= threshold)


def explicit_code(item):
    code = str(item.get("code") or "").strip().upper()
    if code and code not in BAD_CODES:
        return code
    content = str(item.get("content") or "")
    match = CODE_RE.search(content)
    if match and match.group(1).upper() not in BAD_CODES:
        return match.group(1).upper()
    for candidate in CODE_TOKEN_RE.findall(content):
        candidate = candidate.upper()
        if candidate not in BAD_CODES:
            return candidate
    return ""


def normalized_host(value):
    raw = str(value or "").strip()
    if "://" not in raw:
        raw = "https://" + raw
    return (urlparse(raw).hostname or "").lower().removeprefix("www.")


def same_official_domain(source, destination):
    src, dst = normalized_host(source), normalized_host(destination)
    return bool(src and dst and (dst == src or dst.endswith("." + src) or src.endswith("." + dst)))


def is_purchase_url(url):
    if not str(url or "").startswith(("https://", "http://")):
        return False
    parsed = urlparse(str(url))
    path = f"{parsed.path} {parsed.query}".lower()
    if BAD_RE.search(path) and not SHOP_PATH_RE.search(path):
        return False
    return bool(SHOP_PATH_RE.search(path) or COMMERCE_HOST_RE.search((parsed.hostname or "").lower()))


def shopping_score(href, anchor_text, block_text, item_text, code):
    parsed = urlparse(href)
    path = f"{parsed.path} {parsed.query}".lower()
    hay = normalize(f"{anchor_text} {block_text} {item_text}")
    score = 0
    if code and code.lower() in hay: score += 160
    score += min(70, len(tokens(item_text) & tokens(hay)) * 7)
    if re.search(r"shop|buy|product|collection|sale|deal|eligible|checkout|store", anchor_text, re.I): score += 45
    if SHOP_PATH_RE.search(path): score += 40
    if COMMERCE_HOST_RE.search((parsed.hostname or "").lower()): score += 20
    if BAD_RE.search(path): score -= 100
    return score


def landing_from_discovery(item, code=""):
    source_url = str(item.get("source_url") or "").strip()
    discovery_url = str(item.get("discovery_url") or source_url).strip()
    if not discovery_url.startswith(("https://", "http://")) or not same_official_domain(source_url, discovery_url):
        return ""
    try:
        response = requests.get(discovery_url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
        response.raise_for_status()
        if not same_official_domain(source_url, response.url):
            return ""
    except Exception:
        return ""
    item_text = str(item.get("content") or "")
    candidates = []
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup.find_all(["article", "li", "div", "section"]):
        block_text = normalize(tag.get_text(" ", strip=True))
        if not block_text or len(block_text) > 2500:
            continue
        # The exact offer/program evidence must be present in the same page block.
        if code and code.lower() not in block_text and not similar(item_text, block_text, 0.30):
            continue
        if not code and not similar(item_text, block_text, 0.42):
            continue
        for anchor in tag.find_all("a", href=True):
            href = urljoin(response.url, anchor.get("href", "").strip())
            if not is_purchase_url(href) or not same_official_domain(source_url, href):
                continue
            score = shopping_score(href, anchor.get_text(" ", strip=True), block_text, item_text, code)
            if score > 35:
                candidates.append((score, -len(href), href))
    if not candidates:
        return ""
    candidates.sort(reverse=True)
    return candidates[0][2]


def program_match(a, b):
    if normalize(a.get("merchant")) != normalize(b.get("merchant")):
        return False
    if normalize(a.get("category")) != normalize(b.get("category")):
        return False
    ca, cb = explicit_code(a), explicit_code(b)
    if ca and cb:
        return ca == cb
    da, db = normalize(a.get("discount")), normalize(b.get("discount"))
    if da and db and da != db:
        return False
    return similar(a.get("content"), b.get("content"), 0.55 if ca or cb else 0.72)


def quality(item):
    score = 0
    if explicit_code(item): score += 50
    if is_purchase_url(item.get("final_purchase_url")): score += 50
    if same_official_domain(item.get("source_url"), item.get("final_purchase_url")): score += 30
    if item.get("official_source"): score += 10
    if item.get("source_verification_status") == "assistant_verified_first_party": score += 20
    if item.get("discovery_url"): score += 10
    return score


def resolve_key(key, representative):
    return key, landing_from_discovery(representative, explicit_code(representative))


def main():
    data = load()
    usable, dropped = [], 0
    pending = {}
    for raw in data:
        item = dict(raw)
        if str(item.get("category") or "").strip() not in EXPECTED_CATEGORIES:
            dropped += 1
            continue
        if item.get("source_verification_status") != "assistant_verified_first_party":
            dropped += 1
            continue
        source = str(item.get("source_url") or "").strip()
        discovery = str(item.get("discovery_url") or source).strip()
        if not source or not discovery or not same_official_domain(source, discovery):
            dropped += 1
            continue
        code = explicit_code(item)
        existing = str(item.get("final_purchase_url") or "").strip()
        # Never trust a previous URL just because it is syntactically a shop URL.
        # It must be re-associated with the exact offer block from the discovery page.
        key = (source, discovery, code, normalize(item.get("content")))
        pending.setdefault(key, item)

    resolved = {}
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(resolve_key, key, item): key for key, item in pending.items()}
        for future in as_completed(futures):
            key, destination = future.result()
            resolved[key] = destination

    for key, item in pending.items():
        destination = resolved.get(key, "")
        source = str(item.get("source_url") or "").strip()
        if not (is_purchase_url(destination) and same_official_domain(source, destination) and destination != source):
            dropped += 1
            continue
        item["final_purchase_url"] = item["promotion_url"] = item["url"] = destination
        item["code"] = explicit_code(item)
        item["code_context"] = bool(item["code"])
        item["purchase_url_verification_status"] = None
        item["purchase_url_verification_reason"] = "pending_exact_offer_destination_runtime_validation"
        item["purchase_url_verified_at"] = None
        usable.append(item)

    deduped = []
    for item in sorted(usable, key=quality, reverse=True):
        duplicate = next((i for i, previous in enumerate(deduped) if program_match(item, previous)), None)
        if duplicate is None:
            deduped.append(item)
        elif quality(item) > quality(deduped[duplicate]):
            deduped[duplicate] = item

    for item in deduped:
        item["id"] = hashlib.sha256(json.dumps({"merchant": item.get("merchant"), "category": item.get("category"), "code": explicit_code(item), "content": item.get("content"), "final_purchase_url": item.get("final_purchase_url")}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]

    OUT.write_text(json.dumps(deduped[:4000], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"EXACT OFFER DESTINATION RESOLUTION: before={len(data)}, after={len(deduped)}, dropped_invalid_or_unmatched={dropped}, workers={WORKERS}")
    if not deduped:
        raise SystemExit("EXACT OFFER DESTINATION RESOLUTION FAILED: no offer had an exact same-merchant purchase destination")


if __name__ == "__main__":
    main()
