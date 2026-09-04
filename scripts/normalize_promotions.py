import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "news.json"
HEADERS = {"User-Agent": "Deal24H/2.5 (+final purchase destination resolver)"}
TIMEOUT = 20
CODE_RE = re.compile(r"\b(?:code|promo code|coupon code|use code|enter (?:the )?(?:promo )?code)\s*[:\-]?\s*([A-Z0-9][A-Z0-9_-]{3,})\b", re.I)
CODE_TOKEN_RE = re.compile(r"\b[A-Z]{2,}\d[A-Z0-9_-]{2,}\b")
SHOP_RE = re.compile(r"\b(?:shop|shop now|buy|product|products|collection|collections|sale|deal|deals|eligible|men|women|kids|shoes|clothing|checkout|store)\b", re.I)
BAD_RE = re.compile(r"\b(?:terms|terms.?conditions|privacy|legal|help|faq|promotion|promotions|conditions|returns|support|promo.?terms|product-advice)\b", re.I)
SHOP_PATH_RE = re.compile(r"/p/|/products?/|/shop(?:/|$)|/collections?/|/category/|/sale(?:/|$)|/deals?(?:/|$)|/w/|/t/|/store(?:/|$)", re.I)
COMMERCE_HOST_RE = re.compile(r"^(?:store|shop)\.", re.I)
BAD_CODES = {"WILL", "CODE", "COUPON", "COUPONS", "TODAY", "DEAL", "DEALS", "SALE", "NEW", "SHOP", "HTTPS", "WWW", "CLICK", "VERIFY", "ACTIVE", "PROMO", "PROMOS", "OFFER", "OFFERS", "WITH", "ENTER", "THIS", "YOUR", "FROM", "ONLY", "APPLY", "HELP", "PAGE", "NEXT", "SIGN", "JOIN", "REQUIRED", "INTO"}


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


def is_purchase_url(url):
    if not str(url or "").startswith(("https://", "http://")):
        return False
    parsed = urlparse(str(url))
    path = f"{parsed.path} {parsed.query}".lower()
    if BAD_RE.search(path) and not SHOP_PATH_RE.search(path):
        return False
    host = (parsed.hostname or "").lower()
    return bool(SHOP_PATH_RE.search(path) or COMMERCE_HOST_RE.search(host))


def shopping_score(href, anchor_text, block_text, item_text, code):
    parsed = urlparse(href)
    path = f"{parsed.path} {parsed.query}".lower()
    hay = normalize(f"{anchor_text} {block_text} {item_text}")
    score = 0
    if code and code.lower() in hay:
        score += 120
    overlap = len(tokens(item_text) & tokens(hay))
    score += min(50, overlap * 5)
    if re.search(r"shop|buy|product|collection|sale|deal|eligible|checkout|store", anchor_text, re.I):
        score += 45
    if SHOP_PATH_RE.search(path):
        score += 40
    if COMMERCE_HOST_RE.search((parsed.hostname or "").lower()):
        score += 20
    if BAD_RE.search(path):
        score -= 80
    return score


def landing_from_source(item, code=""):
    source_url = str(item.get("source_url") or "").strip()
    if not source_url.startswith(("https://", "http://")):
        return ""
    try:
        response = requests.get(source_url, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
    except Exception:
        return ""

    if is_purchase_url(response.url) and not BAD_RE.search(urlparse(response.url).path):
        return response.url

    soup = BeautifulSoup(response.text, "html.parser")
    item_text = str(item.get("content") or "")
    candidates = []
    for tag in soup.find_all(["article", "li", "div", "section"]):
        block_text = normalize(tag.get_text(" ", strip=True))
        if not block_text or len(block_text) > 2500:
            continue
        if code and code.lower() not in block_text and not similar(item_text, block_text, 0.35):
            continue
        for anchor in tag.find_all("a", href=True):
            href = urljoin(response.url, anchor.get("href", "").strip())
            if not is_purchase_url(href):
                continue
            host = (urlparse(href).hostname or "").lower()
            source_host = (urlparse(response.url).hostname or "").lower()
            if host != source_host and not host.endswith("." + source_host.removeprefix("www.")):
                continue
            score = shopping_score(href, anchor.get_text(" ", strip=True), block_text, item_text, code)
            if score > 0:
                candidates.append((score, -len(href), href))

    if not candidates:
        for anchor in soup.find_all("a", href=True):
            href = urljoin(response.url, anchor.get("href", "").strip())
            if is_purchase_url(href):
                score = shopping_score(href, anchor.get_text(" ", strip=True), "", item_text, code)
                if score > 0:
                    candidates.append((score, -len(href), href))
    if not candidates:
        return ""
    candidates.sort(reverse=True)
    return candidates[0][2]


def program_match(a, b):
    if normalize(a.get("merchant")) != normalize(b.get("merchant")):
        return False
    ca, cb = explicit_code(a), explicit_code(b)
    if ca and cb:
        return ca == cb
    da, db = normalize(a.get("discount")), normalize(b.get("discount"))
    if da and db and da != db:
        return False
    return similar(a.get("content"), b.get("content"), 0.48 if ca or cb else 0.68)


def quality(item):
    score = 0
    if explicit_code(item):
        score += 50
    if is_purchase_url(item.get("final_purchase_url")):
        score += 50
    if item.get("official_source"):
        score += 10
    if item.get("verified"):
        score += 5
    return score


def main():
    data = load()
    cache = {}
    usable = []
    dropped = 0
    for item in data:
        item = dict(item)
        item.setdefault("source_url", item.get("url") or item.get("promotion_url") or "")
        code = explicit_code(item)
        existing = str(item.get("final_purchase_url") or item.get("promotion_url") or item.get("url") or "").strip()
        if is_purchase_url(existing):
            destination = existing
        else:
            key = (str(item.get("source_url") or ""), code)
            if key not in cache:
                cache[key] = landing_from_source(item, code)
            destination = cache[key]
        if not is_purchase_url(destination):
            dropped += 1
            continue
        item["final_purchase_url"] = destination
        item["promotion_url"] = destination
        item["url"] = destination
        item["code"] = code
        item["code_context"] = bool(code)
        usable.append(item)

    deduped = []
    for item in sorted(usable, key=quality, reverse=True):
        duplicate = next((i for i, previous in enumerate(deduped) if program_match(item, previous)), None)
        if duplicate is None:
            deduped.append(item)
        elif quality(item) > quality(deduped[duplicate]):
            deduped[duplicate] = item

    for item in deduped:
        item["id"] = hashlib.sha256(json.dumps({"merchant": item.get("merchant"), "code": explicit_code(item), "content": item.get("content"), "final_purchase_url": item.get("final_purchase_url")}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    deduped.sort(key=lambda x: str(x.get("last_checked") or x.get("detected_at") or ""), reverse=True)
    OUT.write_text(json.dumps(deduped[:4000], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"FINAL PURCHASE NORMALIZATION: before={len(data)}, after={len(deduped)}, dropped_no_purchase={dropped}")


if __name__ == "__main__":
    main()
