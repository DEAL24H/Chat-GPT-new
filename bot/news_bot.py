import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUT = DATA_DIR / "news.json"
STATE = DATA_DIR / "deal_state.json"
HEADERS = {"User-Agent": "Deal24H/1.0 (+GitHub Pages public coupon collector)"}
MAX_DEALS = 1200

# Public pages used as discovery sources. The bot only reads publicly visible offer data.
# If a source has not changed since the previous run, it is not parsed again.
SOURCES = [
    {"name": "CouponScouter", "url": "https://couponscouter.com/", "category": "Thời trang"},
    {"name": "Coupon Kent", "url": "https://couponkent.com/", "category": "Tổng hợp"},
    {"name": "DealAtlas", "url": "https://dealatlas.org/", "category": "Tổng hợp"},
    {"name": "SimplyCodes", "url": "https://simplycodes.com/", "category": "Tổng hợp"},
]

CATEGORIES = {
    "Thời trang": ["fashion", "apparel", "clothing", "shoes", "sneaker", "dress", "jeans", "bag", "accessories", "nike", "adidas", "puma", "shein", "asos", "zara", "h&m", "uniqlo"],
    "Mỹ phẩm": ["beauty", "cosmetic", "skincare", "makeup", "cosmetics", "sephora", "ulta", "nars", "mac", "cerave", "ordinary", "glossier", "clinique"],
    "Game": ["gaming", "game", "steam", "epic", "playstation", "xbox", "nintendo", "ubisoft", "ea", "humble", "fanatical"],
}

CODE_RE = re.compile(r"\b[A-Z][A-Z0-9_-]{3,24}\b")
DISCOUNT_RE = re.compile(r"(?:\$\s?\d+(?:\.\d+)?|\d{1,3}%|\d{1,3}\s?%\s?off|\d{1,3}%\s?off)", re.I)
BAD_CODES = {"COPY", "CODE", "COUPON", "TODAY", "DEAL", "SALE", "NEW", "SHOP", "SAVE", "HTTPS", "WWW", "CLICK", "VERIFY"}


def clean(text):
    return re.sub(r"\s+", " ", BeautifulSoup(text or "", "html.parser").get_text(" ")).strip()


def now():
    return datetime.now(timezone.utc).isoformat()


def load_json(path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def source_changed(html, previous):
    digest = hashlib.sha256(html.encode("utf-8", errors="ignore")).hexdigest()
    return digest, digest != previous.get("hash")


def category_for(text, fallback="Tổng hợp"):
    value = text.lower()
    for category, words in CATEGORIES.items():
        if any(re.search(r"\b" + re.escape(word) + r"\b", value) for word in words):
            return category
    return fallback


def merchant_from_context(context, source_name):
    context = clean(context)
    # Prefer a heading-like phrase before the offer text.
    bits = re.split(r"\s+[|·•–—]\s+", context)
    candidate = bits[0] if bits else context
    candidate = re.sub(r"^(verified|new|hot deal|deal|coupon|promo|code)\s*", "", candidate, flags=re.I).strip()
    candidate = candidate[:90]
    if not candidate or candidate.lower() in {source_name.lower(), "today's top coupons", "popular coupons"}:
        return ""
    return candidate


def extract_deals(html, source):
    soup = BeautifulSoup(html, "html.parser")
    blocks = []
    # Small visible blocks reduce false matches and keep the parser cheap.
    for tag in soup.find_all(["article", "li", "div", "section"]):
        text = clean(tag.get_text(" ", strip=True))
        if 25 <= len(text) <= 700 and re.search(r"\b(?:code|coupon|promo)\b", text, re.I):
            blocks.append(text)
    if not blocks:
        blocks = [clean(x) for x in soup.stripped_strings]

    deals = []
    seen = set()
    for block in blocks:
        codes = []
        for match in CODE_RE.findall(block.upper()):
            if match in BAD_CODES or len(match) < 4:
                continue
            # Require a code-like cue near the token. This prevents random headings being published.
            pos = block.upper().find(match)
            window = block[max(0, pos - 45):pos + len(match) + 45].lower()
            if "code" in window or "coupon" in window or "promo" in window:
                codes.append(match)
        if not codes:
            continue
        discount = DISCOUNT_RE.search(block)
        merchant = merchant_from_context(block, source["name"])
        if not merchant:
            merchant = source["name"]
        category = category_for(block + " " + merchant, source["category"])
        for code in codes[:3]:
            key = (merchant.lower(), code.lower())
            if key in seen:
                continue
            seen.add(key)
            deals.append({
                "id": hashlib.sha256((source["name"] + "|" + merchant + "|" + code).encode()).hexdigest()[:16],
                "title": f"{merchant} — {discount.group(0) if discount else 'Ưu đãi'}",
                "content": block[:500],
                "code": code,
                "discount": discount.group(0) if discount else "",
                "merchant": merchant,
                "category": category,
                "country": "Quốc tế",
                "url": source["url"],
                "source_url": source["url"],
                "source_label": source["name"],
                "detected_at": now(),
                "last_checked": now(),
                "status": "active",
                "verified": False,
                "images": [],
                "image": "",
                "summary_type": "public_coupon_discovery",
            })
    return deals


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    state = load_json(STATE, {"sources": {}, "deals": {}})
    existing = load_json(OUT, [])
    if not isinstance(existing, list):
        existing = []

    by_key = {(d.get("merchant", "").lower(), d.get("code", "").lower()): d for d in existing if d.get("code")}
    changed_sources = 0
    new_count = 0

    for source in SOURCES:
        previous = state["sources"].get(source["url"], {})
        try:
            response = requests.get(source["url"], headers=HEADERS, timeout=20)
            response.raise_for_status()
            html = response.text
            digest, changed = source_changed(html, previous)
            state["sources"][source["url"]] = {"hash": digest, "last_checked": now(), "last_changed": previous.get("last_changed") or now()}
            if not changed:
                print(f"SKIP unchanged: {source['name']}")
                continue
            state["sources"][source["url"]]["last_changed"] = now()
            changed_sources += 1
            deals = extract_deals(html, source)
            for deal in deals:
                key = (deal["merchant"].lower(), deal["code"].lower())
                old = by_key.get(key)
                if old:
                    old.update({"last_checked": now(), "status": "active", "source_url": deal["source_url"], "source_label": deal["source_label"]})
                else:
                    by_key[key] = deal
                    new_count += 1
            print(f"CHANGED {source['name']}: discovered {len(deals)} offers")
        except Exception as exc:
            state["sources"][source["url"]] = {**previous, "last_checked": now(), "last_error": str(exc)[:240]}
            print(f"SOURCE ERROR {source['name']}: {exc}")

    # Newest first; keep a bounded database so Pages stays fast.
    all_deals = list(by_key.values())
    all_deals.sort(key=lambda d: d.get("last_checked", ""), reverse=True)
    all_deals = all_deals[:MAX_DEALS]

    save_json(OUT, all_deals)
    save_json(STATE, state)
    print(f"DONE: changed_sources={changed_sources}, new_deals={new_count}, total={len(all_deals)}")


if __name__ == "__main__":
    main()
