import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "news.json"
EXPECTED_CATEGORIES = {"Fashion", "Electronics", "Beauty & Personal Care", "Home & Living"}
SHOP_PATH_RE = re.compile(r"/p/|/products?/|/shop(?:/|$)|/collections?/|/category/|/sale(?:/|$)|/deals?(?:/|$)|/w/|/t/|/store(?:/|$)", re.I)
BAD_RE = re.compile(r"\b(?:terms|terms.?conditions|privacy|legal|help|faq|conditions|returns|support|promo.?terms|product-advice)\b", re.I)
COMMERCE_HOST_RE = re.compile(r"^(?:store|shop)\.", re.I)
BAD_CODES = {"WILL","CODE","COUPON","COUPONS","TODAY","DEAL","DEALS","SALE","NEW","SHOP","HTTPS","WWW","CLICK","VERIFY","ACTIVE","PROMO","PROMOS","OFFER","OFFERS","WITH","ENTER","THIS","YOUR","FROM","ONLY","APPLY","HELP","PAGE","NEXT","SIGN","JOIN","REQUIRED","INTO"}
CODE_RE = re.compile(r"\b(?:code|promo code|coupon code|use code|enter (?:the )?(?:promo )?code)\s*[:\-]?\s*([A-Z0-9][A-Z0-9_-]{3,})\b", re.I)
CODE_TOKEN_RE = re.compile(r"\b[A-Z]{2,}\d[A-Z0-9_-]{2,}\b")


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
    if not raw:
        return ""
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


def quality(item):
    score = 0
    if explicit_code(item): score += 50
    if is_purchase_url(item.get("final_purchase_url")): score += 50
    if same_official_domain(item.get("source_url"), item.get("final_purchase_url")): score += 30
    if item.get("official_source"): score += 10
    if item.get("source_verification_status") == "assistant_verified_first_party": score += 20
    return score


def main():
    data = load()
    usable = []
    dropped = 0

    for raw in data:
        item = dict(raw)
        if str(item.get("category") or "").strip() not in EXPECTED_CATEGORIES:
            dropped += 1
            continue
        if item.get("source_verification_status") != "assistant_verified_first_party":
            dropped += 1
            continue

        source = str(item.get("source_url") or "").strip()
        destination = str(item.get("final_purchase_url") or item.get("purchase_url") or item.get("promotion_url") or "").strip()
        if not source or not destination:
            dropped += 1
            continue

        # IMPORTANT: the discovery stage or previously verified canonical record
        # supplies the purchase URL. Do not discard it and re-crawl discovery pages.
        if not is_purchase_url(destination) or not same_official_domain(source, destination) or destination == source:
            dropped += 1
            continue

        item["final_purchase_url"] = destination
        item["promotion_url"] = destination
        item["url"] = destination
        item["code"] = explicit_code(item)
        item["code_context"] = bool(item["code"])
        item["purchase_url_verification_status"] = None
        item["purchase_url_verification_reason"] = "pending_live_verification_of_supplied_purchase_destination"
        item["purchase_url_verified_at"] = None
        usable.append(item)

    deduped = []
    for item in sorted(usable, key=quality, reverse=True):
        duplicate = next((i for i, previous in enumerate(deduped) if normalize(item.get("merchant")) == normalize(previous.get("merchant")) and normalize(item.get("category")) == normalize(previous.get("category")) and explicit_code(item) == explicit_code(previous) and (explicit_code(item) or similar(item.get("content"), previous.get("content"), 0.72))), None)
        if duplicate is None:
            deduped.append(item)
        elif quality(item) > quality(deduped[duplicate]):
            deduped[duplicate] = item

    for item in deduped:
        item["id"] = hashlib.sha256(json.dumps({"merchant": item.get("merchant"), "category": item.get("category"), "code": explicit_code(item), "content": item.get("content"), "final_purchase_url": item.get("final_purchase_url")}, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]

    OUT.write_text(json.dumps(deduped[:4000], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"SUPPLIED PURCHASE DESTINATION NORMALIZATION: before={len(data)}, after={len(deduped)}, dropped_missing_or_invalid_destination={dropped}")
    if not deduped:
        raise SystemExit("SUPPLIED PURCHASE DESTINATION NORMALIZATION FAILED: no offer had a supplied valid purchase destination")


if __name__ == "__main__":
    main()
