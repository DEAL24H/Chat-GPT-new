import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "news.json"
HEADERS = {"User-Agent": "Deal24H/2.2 (+official promotion destination resolver)"}
TIMEOUT = 20
CODE_RE = re.compile(r"\b(?:code|promo code|coupon code)\s*[:\-]?\s*([A-Z0-9][A-Z0-9_-]{3,})\b", re.I)
SHOP_RE = re.compile(r"\b(?:shop|shop now|buy|product|products|collection|collections|sale|deal|deals|eligible)\b", re.I)
BAD_RE = re.compile(r"\b(?:terms|terms.?conditions|privacy|legal|help|faq|promotion|promotions|conditions)\b", re.I)


def load():
    try:
        value = json.loads(OUT.read_text(encoding="utf-8"))
        return value if isinstance(value, list) else []
    except Exception:
        return []


def normalize(text):
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def explicit_code(item):
    code = str(item.get("code") or "").strip().upper()
    if code:
        return code
    match = CODE_RE.search(str(item.get("content") or ""))
    return match.group(1).upper() if match else ""


def landing_from_source(item):
    source_url = str(item.get("source_url") or item.get("promotion_url") or item.get("url") or "").strip()
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
        if SHOP_RE.search(hay):
            score += 10
        if re.search(r"product|shop|collection|category|sale|deal", parsed.path, re.I):
            score += 6
        if BAD_RE.search(hay) and not SHOP_RE.search(text):
            score -= 12
        if href.rstrip("/") == source_url.rstrip("/"):
            score -= 8
        if score > 0:
            candidates.append((score, -len(href), href))
    if not candidates:
        return ""
    candidates.sort(reverse=True)
    return candidates[0][2]


def main():
    data = load()
    cache = {}
    for item in data:
        item.setdefault("source_url", item.get("promotion_url") or item.get("url") or "")
        key_source = str(item.get("source_url") or "")
        if key_source not in cache:
            cache[key_source] = landing_from_source(item)
        landing = cache[key_source]
        if landing:
            item["promotion_url"] = landing
            item["url"] = landing
        elif not item.get("promotion_url"):
            item["promotion_url"] = item.get("source_url") or item.get("url") or ""

    # One SEO-visible offer per merchant + explicit promo code. If the code only
    # appears in the description, it still identifies the same real promotion.
    chosen = {}
    no_code = []
    for item in data:
        merchant = normalize(item.get("merchant"))
        code = explicit_code(item)
        if code:
            key = (merchant, code)
            current = chosen.get(key)
            if current is None or (not current.get("code") and item.get("code")):
                chosen[key] = item
        else:
            no_code.append(item)

    deduped = list(chosen.values())
    seen_no_code = set()
    for item in no_code:
        key = (normalize(item.get("merchant")), normalize(item.get("discount")), normalize(item.get("content")))
        if key in seen_no_code:
            continue
        seen_no_code.add(key)
        deduped.append(item)

    for item in deduped:
        item["id"] = hashlib.sha256(json.dumps({"merchant": item.get("merchant"), "code": explicit_code(item), "content": item.get("content"), "promotion_url": item.get("promotion_url")}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    deduped.sort(key=lambda x: str(x.get("last_checked") or x.get("detected_at") or ""), reverse=True)
    OUT.write_text(json.dumps(deduped[:4000], ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PROMOTION NORMALIZE DONE: before={len(data)}, after={len(deduped)}, removed={len(data)-len(deduped)}")


if __name__ == "__main__":
    main()
