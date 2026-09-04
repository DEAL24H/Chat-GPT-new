import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "news.json"
HEADERS = {"User-Agent": "Deal24H/2.4 (+official promotion destination resolver)"}
TIMEOUT = 20
CODE_RE = re.compile(r"\b(?:code|promo code|coupon code|use code|enter (?:the )?(?:promo )?code)\s*[:\-]?\s*([A-Z0-9][A-Z0-9_-]{3,})\b", re.I)
CODE_TOKEN_RE = re.compile(r"\b[A-Z]{2,}\d[A-Z0-9_-]{2,}\b")
SHOP_RE = re.compile(r"\b(?:shop|shop now|buy|product|products|collection|collections|sale|deal|deals|eligible|men|women|kids|shoes|clothing|checkout)\b", re.I)
BAD_RE = re.compile(r"\b(?:terms|terms.?conditions|privacy|legal|help|faq|promotion|promotions|conditions|returns|support|promo.?terms|product-advice|promo-code)\b", re.I)
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
    if not left or not right:
        return False
    return len(left & right) / max(1, len(left | right)) >= threshold


def explicit_code(item):
    code = str(item.get("code") or "").strip().upper()
    if code and code not in BAD_CODES:
        return code
    content = str(item.get("content") or "")
    match = CODE_RE.search(content)
    if match:
        candidate = match.group(1).upper()
        if candidate not in BAD_CODES:
            return candidate
    candidates = CODE_TOKEN_RE.findall(content)
    for candidate in candidates:
        candidate = candidate.upper()
        if candidate not in BAD_CODES:
            return candidate
    return ""


def url_is_shopping(url):
    if not str(url).startswith(("https://", "http://")):
        return False
    parsed = urlparse(str(url))
    path = f"{parsed.path} {parsed.query}".lower()
    if BAD_RE.search(path) and not re.search(r"/shop(?:/|$)|/sale(?:/|$)|/deals?(?:/|$)|/collections?/|/products?/|/p/|/w/|/t/", path, re.I):
        return False
    return bool(
        SHOP_RE.search(path)
        or re.search(r"/p/|/products?/|/shop(?:/|$)|/collections?/|/category/|/sale(?:/|$)|/deals?(?:/|$)|/w/|/t/", path, re.I)
    )


def shopping_link_score(href, text, code=""):
    parsed = urlparse(href)
    path = f"{parsed.path} {parsed.query}".lower()
    hay = normalize(f"{text} {path}")
    score = 0
    if code and code.lower() in hay:
        score += 80
    if SHOP_RE.search(text):
        score += 35
    if re.search(r"product|shop|collection|category|sale|deal|eligible|shoes|clothing|checkout", parsed.path, re.I):
        score += 20
    if url_is_shopping(href):
        score += 25
    if BAD_RE.search(hay) and not SHOP_RE.search(text):
        score -= 45
    return score


def landing_from_source(item, required_code=""):
    source_url = str(item.get("source_url") or "").strip()
    if not source_url.startswith(("https://", "http://")):
        return ""
    try:
        response = requests.get(source_url, headers=HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
    except Exception:
        return ""

    soup = BeautifulSoup(response.text, "html.parser")
    base_host = (urlparse(source_url).hostname or "").lower().removeprefix("www.")
    domain = str(item.get("source_domain") or base_host).lower().removeprefix("www.")
    candidates = []

    for tag in soup.find_all(["article", "li", "div", "section"]):
        text = normalize(tag.get_text(" ", strip=True))
        if required_code and required_code.lower() not in text:
            continue
        if required_code and len(text) > 2500:
            continue
        for anchor in tag.find_all("a", href=True):
            href = urljoin(source_url, anchor.get("href", "").strip())
            parsed = urlparse(href)
            host = (parsed.hostname or "").lower().removeprefix("www.")
            if host != base_host and not host.endswith("." + domain):
                continue
            anchor_text = anchor.get_text(" ", strip=True)
            if not url_is_shopping(href):
                continue
            score = shopping_link_score(href, anchor_text, required_code)
            if score > 0:
                candidates.append((score + 60, -len(href), href))

    if not candidates:
        for anchor in soup.find_all("a", href=True):
            href = urljoin(source_url, anchor.get("href", "").strip())
            parsed = urlparse(href)
            host = (parsed.hostname or "").lower().removeprefix("www.")
            if host != base_host and not host.endswith("." + domain):
                continue
            if not url_is_shopping(href):
                continue
            score = shopping_link_score(href, anchor.get_text(" ", strip=True), required_code)
            if score > 0:
                candidates.append((score, -len(href), href))

    if not candidates:
        return ""
    candidates.sort(reverse=True)
    return candidates[0][2]


def resolve_destination(item, cache):
    code = explicit_code(item)
    existing = str(item.get("promotion_url") or item.get("url") or "").strip()
    source_url = str(item.get("source_url") or "").strip()

    if code:
        if url_is_shopping(existing):
            return existing
        cache_key = (source_url, code)
        if cache_key not in cache:
            cache[cache_key] = landing_from_source(item, code) if source_url else ""
        return cache[cache_key]

    if existing.startswith(("https://", "http://")):
        return existing
    if source_url.startswith(("https://", "http://")):
        return source_url
    return ""


def program_match(a, b):
    if normalize(a.get("merchant")) != normalize(b.get("merchant")):
        return False
    ca, cb = explicit_code(a), explicit_code(b)
    if ca and cb:
        return ca == cb
    if ca or cb:
        da = normalize(a.get("discount"))
        db = normalize(b.get("discount"))
        if da and db and da != db:
            return False
        return similar(a.get("content"), b.get("content"), threshold=0.48)
    da = normalize(a.get("discount"))
    db = normalize(b.get("discount"))
    if da and db and da != db:
        return False
    return similar(a.get("content"), b.get("content"), threshold=0.68)


def quality(item):
    score = 0
    code = explicit_code(item)
    if code:
        score += 40
        if str(item.get("code") or "").strip():
            score += 10
        if url_is_shopping(item.get("promotion_url") or item.get("url")):
            score += 35
    else:
        if str(item.get("promotion_url") or item.get("url") or "").startswith(("https://", "http://")):
            score += 30
    if item.get("official_source"):
        score += 10
    if item.get("verified"):
        score += 5
    if item.get("content"):
        score += min(5, len(str(item.get("content"))) // 120)
    return score


def main():
    data = load()
    cache = {}
    usable = []
    dropped_destination = 0
    unresolved_codes = 0

    for item in data:
        item.setdefault("source_url", item.get("promotion_url") or item.get("url") or "")
        code = explicit_code(item)
        destination = resolve_destination(item, cache)
        if not destination:
            dropped_destination += 1
            if code:
                unresolved_codes += 1
            continue
        item["promotion_url"] = destination
        item["url"] = destination
        if code:
            item["code"] = code
            item["code_context"] = True
        else:
            item["code"] = ""
            item["code_context"] = False
        usable.append(item)

    deduped = []
    for item in sorted(usable, key=quality, reverse=True):
        duplicate_index = next((i for i, previous in enumerate(deduped) if program_match(item, previous)), None)
        if duplicate_index is None:
            deduped.append(item)
            continue
        if quality(item) > quality(deduped[duplicate_index]):
            deduped[duplicate_index] = item

    for item in deduped:
        item["id"] = hashlib.sha256(json.dumps({
            "merchant": item.get("merchant"),
            "code": explicit_code(item),
            "content": item.get("content"),
            "promotion_url": item.get("promotion_url"),
        }, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]

    deduped.sort(key=lambda x: str(x.get("last_checked") or x.get("detected_at") or ""), reverse=True)
    OUT.write_text(json.dumps(deduped[:4000], ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"PROMOTION NORMALIZE DONE: before={len(data)}, after={len(deduped)}, "
        f"removed={len(data)-len(deduped)}, no_destination={dropped_destination}, "
        f"unresolved_code_destinations={unresolved_codes}"
    )


if __name__ == "__main__":
    main()
