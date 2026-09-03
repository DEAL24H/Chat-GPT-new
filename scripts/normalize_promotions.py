import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "news.json"
HEADERS = {"User-Agent": "Deal24H/2.3 (+official promotion destination resolver)"}
TIMEOUT = 20
CODE_RE = re.compile(r"\b(?:code|promo code|coupon code|use code|enter (?:the )?(?:promo )?code)\s*[:\-]?\s*([A-Z0-9][A-Z0-9_-]{3,})\b", re.I)
CODE_TOKEN_RE = re.compile(r"\b[A-Z]{2,}\d[A-Z0-9_-]{2,}\b")
SHOP_RE = re.compile(r"\b(?:shop|shop now|buy|product|products|collection|collections|sale|deal|deals|eligible|men|women|kids|shoes|clothing)\b", re.I)
BAD_RE = re.compile(r"\b(?:terms|terms.?conditions|privacy|legal|help|faq|promotion|promotions|conditions|returns|support)\b", re.I)


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
    if code:
        return code
    content = str(item.get("content") or "")
    match = CODE_RE.search(content)
    if match:
        return match.group(1).upper()
    candidates = CODE_TOKEN_RE.findall(content)
    return candidates[0].upper() if candidates else ""


def url_is_shopping(url):
    if not str(url).startswith(("https://", "http://")):
        return False
    parsed = urlparse(str(url))
    path = f"{parsed.path} {parsed.query}".lower()
    if BAD_RE.search(path) and not SHOP_RE.search(path):
        return False
    return bool(SHOP_RE.search(path) or re.search(r"/p/|/products?/|/shop(?:/|$)|/collections?/|/category/|/sale(?:/|$)|/deals?(?:/|$)", path, re.I))


def landing_from_source(item):
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
    for anchor in soup.find_all("a", href=True):
        href = urljoin(source_url, anchor.get("href", "").strip())
        parsed = urlparse(href)
        host = (parsed.hostname or "").lower().removeprefix("www.")
        if host != base_host and not host.endswith("." + domain):
            continue
        text = normalize(anchor.get_text(" ", strip=True))
        hay = f"{text} {parsed.path} {parsed.query}"
        score = 0
        if SHOP_RE.search(text):
            score += 18
        if re.search(r"product|shop|collection|category|sale|deal|eligible|shoes|clothing", parsed.path, re.I):
            score += 10
        if BAD_RE.search(hay) and not SHOP_RE.search(text):
            score -= 25
        if href.rstrip("/") == source_url.rstrip("/"):
            score -= 10
        if url_is_shopping(href):
            score += 8
        if score > 0 and url_is_shopping(href):
            candidates.append((score, -len(href), href))
    if not candidates:
        return ""
    candidates.sort(reverse=True)
    return candidates[0][2]


def resolve_destination(item, cache):
    source_url = str(item.get("source_url") or "").strip()
    if source_url not in cache:
        cache[source_url] = landing_from_source(item) if source_url else ""
    landing = cache[source_url]
    if landing:
        return landing
    existing = str(item.get("promotion_url") or item.get("url") or "").strip()
    if url_is_shopping(existing):
        return existing
    if url_is_shopping(source_url):
        return source_url
    return ""


def program_match(a, b):
    if normalize(a.get("merchant")) != normalize(b.get("merchant")):
        return False
    ca, cb = explicit_code(a), explicit_code(b)
    if ca and cb:
        return ca == cb
    if ca or cb:
        # A code-bearing offer and a code-less representation can still be the
        # same promotion when their merchant/discount/content clearly match.
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

    for item in data:
        item.setdefault("source_url", item.get("promotion_url") or item.get("url") or "")
        destination = resolve_destination(item, cache)
        if not destination:
            dropped_destination += 1
            continue
        item["promotion_url"] = destination
        item["url"] = destination
        if explicit_code(item):
            item["code"] = explicit_code(item)
            item["code_context"] = True
        usable.append(item)

    deduped = []
    for item in sorted(usable, key=quality, reverse=True):
        duplicate_index = next((i for i, previous in enumerate(deduped) if program_match(item, previous)), None)
        if duplicate_index is None:
            deduped.append(item)
            continue
        # Keep the stronger representation: code + copyable code + shopping URL.
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
    print(f"PROMOTION NORMALIZE DONE: before={len(data)}, after={len(deduped)}, removed={len(data)-len(deduped)}, no_shopping_destination={dropped_destination}")


if __name__ == "__main__":
    main()
