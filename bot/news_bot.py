import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUT = DATA_DIR / "news.json"
STATE = DATA_DIR / "deal_state.json"
HEADERS = {"User-Agent": "Deal24H/1.1 (+DEAL24H official-source coupon collector)"}
MAX_DEALS = 1200

# SECURITY RULE: third-party coupon aggregators are discovery-only and are NOT
# allowed to publish coupon codes into DEAL 24H. A code must be found on an
# official merchant domain. Coupon Kent, CouponScouter, DealAtlas, SimplyCodes,
# etc. are intentionally excluded from SOURCES.
SOURCES = [
    {"name": "Nike Official", "url": "https://www.nike.com/promo-code/", "domain": "nike.com", "category": "Thời trang", "merchant": "Nike"},
    {"name": "adidas Official", "url": "https://www.adidas.com/us/promotions", "domain": "adidas.com", "category": "Thời trang", "merchant": "Adidas"},
]

CATEGORIES = {
    "Thời trang": ["fashion", "apparel", "clothing", "shoes", "sneaker", "dress", "jeans", "bag", "accessories", "nike", "adidas", "puma", "shein", "asos", "zara", "h&m", "uniqlo", "mango", "crocs", "gap", "converse", "under armour", "reebok"],
    "Mỹ phẩm": ["beauty", "cosmetic", "skincare", "makeup", "cosmetics", "sephora", "ulta", "nars", "mac", "cerave", "ordinary", "glossier", "clinique", "paula's choice", "farmacy", "bobbi brown", "kosas"],
    "Game": ["gaming", "game", "steam", "epic", "playstation", "xbox", "nintendo", "ubisoft", "ea", "humble", "fanatical"],
    "Hàng tiêu dùng": ["consumer", "electronics", "electronic", "laptop", "computer", "phone", "smartphone", "tablet", "tv", "television", "headphone", "monitor", "printer", "home", "household", "kitchen", "appliance", "furniture", "mattress", "pet", "baby", "grocery", "food", "supplement", "health", "office", "dell", "lenovo", "hp", "best buy", "amazon", "walmart", "target", "ikea", "wayfair", "iherb"]
}

CODE_RE = re.compile(r"\b[A-Z0-9][A-Z0-9_-]{3,24}\b")
DISCOUNT_RE = re.compile(r"(?:\$\s?\d+(?:\.\d+)?|\d{1,3}%|\d{1,3}\s?%\s?off|\d{1,3}%\s?off)", re.I)
BAD_CODES = {"COPY", "CODE", "COUPON", "COUPONS", "TODAY", "DEAL", "DEALS", "SALE", "NEW", "SHOP", "SAVE", "HTTPS", "WWW", "CLICK", "VERIFY", "AUTHORITY", "EDITORS", "EDITOR", "HAND-TESTED", "TESTED", "POPULAR", "LATEST", "ACTIVE", "EXCLUSIVE", "PROMO", "PROMOS", "OFFER", "OFFERS"}
KNOWN_BRANDS = ["Nike", "Adidas", "PUMA", "SHEIN", "ASOS", "Zara", "H&M", "UNIQLO", "Mango", "Crocs", "Gap", "Converse", "Under Armour", "Sephora", "Ulta", "NARS", "MAC", "CeraVe", "The Ordinary", "Glossier", "Clinique", "Paula's Choice", "Farmacy", "Bobbi Brown", "Kosas", "Steam", "Epic Games", "PlayStation", "Xbox", "Nintendo", "Humble", "Fanatical", "Ubisoft", "EA", "Dell", "Lenovo", "HP", "Best Buy", "Reebok", "iHerb", "Amazon", "Walmart", "Target", "IKEA", "Wayfair"]


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
    return "Hàng tiêu dùng" if fallback == "Tổng hợp" else fallback


def parse_expiry(text):
    text = clean(text)
    patterns = [
        r"(?:expires?|expiry|expiration|ends?|valid until|valid through|good through|offer ends?)\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"(?:expires?|expiry|expiration|ends?|valid until|valid through|good through|offer ends?)\s*[:\-]?\s*([A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        raw = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", match.group(1), flags=re.I).replace("/", "-")
        for fmt in ["%m-%d-%Y", "%m-%d-%y", "%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y"]:
            try:
                return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                pass
    return ""


def official_domain(url):
    return urlparse(url).netloc.lower().removeprefix("www.")


def is_official_source(source):
    domain = official_domain(source.get("url", ""))
    allowed = source.get("domain", "").lower().removeprefix("www.")
    return bool(domain and allowed and (domain == allowed or domain.endswith("." + allowed)))


def valid_record(deal):
    code = str(deal.get("code", "")).strip().upper()
    merchant = str(deal.get("merchant", "")).strip()
    source_url = str(deal.get("source_url", "")).strip()
    source_domain = str(deal.get("source_domain", "")).strip().lower().removeprefix("www.")
    official = bool(deal.get("official_source"))
    if not code or code in BAD_CODES or len(code) < 4 or not merchant:
        return False
    if code.isdigit():
        return False
    if re.fullmatch(r"[A-Z_-]{4,30}", code) and not any(ch.isdigit() for ch in code):
        return False
    if not official or not source_url or not source_domain:
        return False
    host = official_domain(source_url)
    if not (host == source_domain or host.endswith("." + source_domain)):
        return False
    if re.search(r"couponkent|couponscouter|dealatlas|simplycodes", host, re.I):
        return False
    return True


def extract_deals(html, source):
    if not is_official_source(source):
        return []
    soup = BeautifulSoup(html, "html.parser")
    blocks = []
    for tag in soup.find_all(["article", "li", "div", "section"]):
        text = clean(tag.get_text(" ", strip=True))
        if 25 <= len(text) <= 700 and re.search(r"\b(?:code|coupon|promo|voucher)\b", text, re.I):
            blocks.append(text)
    if not blocks:
        blocks = [clean(x) for x in soup.stripped_strings]
    deals = []
    seen = set()
    for block in blocks:
        codes = []
        upper = block.upper()
        for match in CODE_RE.findall(upper):
            if match in BAD_CODES or len(match) < 4 or match.isdigit():
                continue
            pos = upper.find(match)
            window = block[max(0, pos - 70):pos + len(match) + 70].lower()
            cue = bool(re.search(r"\b(?:coupon|promo|promotion|voucher)\s*(?:code|codes)?\b|\bcode\b|\benter\s+code\b", window))
            if cue and (any(ch.isdigit() for ch in match) or len(match) >= 6):
                codes.append(match)
        if not codes:
            continue
        merchant = source["merchant"]
        discount = DISCOUNT_RE.search(block)
        category = category_for(block + " " + merchant, source["category"])
        expires_at = parse_expiry(block)
        for code in codes[:3]:
            deal = {
                "id": hashlib.sha256((source["name"] + "|" + merchant + "|" + code).encode()).hexdigest()[:16],
                "title": f"{merchant} — {discount.group(0) if discount else 'Official promo code'}",
                "content": block[:500],
                "code": code,
                "discount": discount.group(0) if discount else "",
                "merchant": merchant,
                "category": category,
                "country": "International",
                "url": source["url"],
                "source_url": source["url"],
                "source_label": source["name"],
                "source_domain": source["domain"],
                "official_source": True,
                "detected_at": now(),
                "last_checked": now(),
                "expires_at": expires_at,
                "status": "active",
                "verified": False,
                "verification_method": "official_merchant_page",
                "images": [],
                "image": "",
                "summary_type": "official_merchant_discovery",
            }
            if valid_record(deal) and (merchant.lower(), code.lower()) not in seen:
                seen.add((merchant.lower(), code.lower()))
                deals.append(deal)
    return deals


def purge_expired(existing):
    current = datetime.now(timezone.utc)
    kept = []
    removed = 0
    rejected = 0
    for deal in existing:
        if not valid_record(deal):
            rejected += 1
            continue
        expiry = str(deal.get("expires_at", "")).strip()
        if expiry:
            try:
                if datetime.fromisoformat(expiry.replace("Z", "+00:00")) <= current:
                    removed += 1
                    continue
            except ValueError:
                pass
        kept.append(deal)
    return kept, removed, rejected


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    state = load_json(STATE, {"sources": {}, "deals": {}})
    existing = load_json(OUT, [])
    if not isinstance(existing, list):
        existing = []

    # Critical migration: remove all historical codes that came from third-party
    # coupon aggregators. They must never remain published after this security fix.
    existing, removed_expired, rejected_non_official = purge_expired(existing)
    by_key = {(d.get("merchant", "").lower(), d.get("code", "").lower()): d for d in existing if d.get("code")}
    changed_sources = 0
    new_count = 0

    for source in SOURCES:
        previous = state["sources"].get(source["url"], {})
        try:
            if not is_official_source(source):
                print(f"BLOCKED NON-OFFICIAL SOURCE: {source['url']}")
                continue
            response = requests.get(source["url"], headers=HEADERS, timeout=25)
            response.raise_for_status()
            html = response.text
            digest, changed = source_changed(html, previous)
            state["sources"][source["url"]] = {
                "hash": digest,
                "last_checked": now(),
                "last_changed": previous.get("last_changed") or now(),
                "official_domain": source["domain"],
            }
            if not changed:
                print(f"SKIP unchanged official source: {source['name']}")
                continue
            state["sources"][source["url"]]["last_changed"] = now()
            changed_sources += 1
            deals = extract_deals(html, source)
            for deal in deals:
                key = (deal["merchant"].lower(), deal["code"].lower())
                old = by_key.get(key)
                if old:
                    old.update({
                        "last_checked": now(),
                        "status": "active",
                        "source_url": deal["source_url"],
                        "source_label": deal["source_label"],
                        "source_domain": deal["source_domain"],
                        "official_source": True,
                        "verification_method": "official_merchant_page",
                        "category": deal["category"],
                    })
                    if deal.get("expires_at"):
                        old["expires_at"] = deal["expires_at"]
                else:
                    by_key[key] = deal
                    new_count += 1
            print(f"CHANGED official {source['name']}: discovered {len(deals)} offers")
        except Exception as exc:
            state["sources"][source["url"]] = {**previous, "last_checked": now(), "last_error": str(exc)[:240]}
            print(f"OFFICIAL SOURCE ERROR {source['name']}: {exc}")

    all_deals = list(by_key.values())
    all_deals.sort(key=lambda d: d.get("last_checked", ""), reverse=True)
    all_deals = all_deals[:MAX_DEALS]
    save_json(OUT, all_deals)
    save_json(STATE, state)
    print(f"DONE: official_only=true, changed_sources={changed_sources}, new_deals={new_count}, expired_removed={removed_expired}, non_official_removed={rejected_non_official}, total={len(all_deals)}")


if __name__ == "__main__":
    main()
