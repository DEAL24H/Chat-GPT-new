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
CODE_RE = re.compile(r"\b[A-Z0-9][A-Z0-9_-]{3,24}\b")
DISCOUNT_RE = re.compile(r"(?:\$\s?\d+(?:\.\d+)?|\d{1,3}%|\d{1,3}\s?%\s?off|\d{1,3}%\s?off)", re.I)
BAD_CODES = {"COPY", "CODE", "COUPON", "COUPONS", "TODAY", "DEAL", "DEALS", "SALE", "NEW", "SHOP", "SAVE", "HTTPS", "WWW", "CLICK", "VERIFY", "AUTHORITY", "EDITORS", "EDITOR", "HAND-TESTED", "TESTED", "POPULAR", "LATEST", "ACTIVE", "EXCLUSIVE", "PROMO", "PROMOS", "OFFER", "OFFERS"}
GENERIC_MERCHANTS = {"dealatlas", "couponscouter", "coupon kent", "simplycodes", "today's top coupons", "popular coupons", "latest coupons"}
KNOWN_BRANDS = ["Nike", "Adidas", "PUMA", "SHEIN", "ASOS", "Zara", "H&M", "UNIQLO", "Mango", "Crocs", "Gap", "Converse", "Under Armour", "Sephora", "Ulta", "NARS", "MAC", "CeraVe", "The Ordinary", "Glossier", "Clinique", "Paula's Choice", "Farmacy", "Bobbi Brown", "Kosas", "Steam", "Epic Games", "PlayStation", "Xbox", "Nintendo", "Humble", "Fanatical", "Ubisoft", "EA", "Dell", "Lenovo", "HP", "Best Buy", "Reebok", "iHerb"]

def clean(text): return re.sub(r"\s+", " ", BeautifulSoup(text or "", "html.parser").get_text(" ")).strip()
def now(): return datetime.now(timezone.utc).isoformat()
def load_json(path, fallback):
    if not path.exists(): return fallback
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return fallback
def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
def source_changed(html, previous):
    digest = hashlib.sha256(html.encode("utf-8", errors="ignore")).hexdigest(); return digest, digest != previous.get("hash")
def category_for(text, fallback="Tổng hợp"):
    value = text.lower()
    for category, words in CATEGORIES.items():
        if any(re.search(r"\b" + re.escape(word) + r"\b", value) for word in words): return category
    return fallback
def merchant_from_context(context, source_name):
    context = clean(context); low = context.lower()
    for brand in KNOWN_BRANDS:
        if re.search(r"\b" + re.escape(brand.lower()) + r"\b", low): return brand
    bits = re.split(r"\s+[|·•–—:]\s+", context); candidate = bits[0] if bits else context
    candidate = re.sub(r"^(verified|new|hot deal|deal|coupon|promo|code|use)\s*", "", candidate, flags=re.I).strip()[:90]
    if not candidate or candidate.lower() in GENERIC_MERCHANTS or candidate.lower() == source_name.lower(): return ""
    if re.fullmatch(r"[A-Z0-9_-]{4,30}", candidate) or re.search(r"\b(authority|editors|hand-tested|verified codes|not bots)\b", candidate, re.I): return ""
    return candidate
def valid_record(deal):
    code = str(deal.get("code", "")).strip().upper(); merchant = str(deal.get("merchant", "")).strip()
    if not code or code in BAD_CODES or len(code) < 4 or not merchant: return False
    if re.fullmatch(r"[A-Z_-]{4,30}", code) and not any(ch.isdigit() for ch in code): return False
    if merchant.lower() in GENERIC_MERCHANTS: return False
    if re.search(r"\b(authority|editors|hand-tested|not bots|popular coupons|latest coupons)\b", merchant, re.I): return False
    return True
def extract_deals(html, source):
    soup = BeautifulSoup(html, "html.parser"); blocks = []
    for tag in soup.find_all(["article", "li", "div", "section"]):
        text = clean(tag.get_text(" ", strip=True))
        if 25 <= len(text) <= 700 and re.search(r"\b(?:code|coupon|promo)\b", text, re.I): blocks.append(text)
    if not blocks: blocks = [clean(x) for x in soup.stripped_strings]
    deals = []; seen = set()
    for block in blocks:
        codes = [] ; upper = block.upper()
        for match in CODE_RE.findall(upper):
            if match in BAD_CODES or len(match) < 4: continue
            pos = upper.find(match); window = block[max(0, pos-55):pos+len(match)+55].lower()
            cue = bool(re.search(r"\b(?:coupon|promo)\s*(?:code|codes)?\b|\bcode\b|\buse\s+this\b", window))
            if cue and (any(ch.isdigit() for ch in match) or len(match) >= 5): codes.append(match)
        if not codes: continue
        merchant = merchant_from_context(block, source["name"])
        if not merchant: continue
        discount = DISCOUNT_RE.search(block); category = category_for(block + " " + merchant, source["category"])
        for code in codes[:3]:
            deal = {"id": hashlib.sha256((source["name"] + "|" + merchant + "|" + code).encode()).hexdigest()[:16], "title": f"{merchant} — {discount.group(0) if discount else 'Coupon code'}", "content": block[:500], "code": code, "discount": discount.group(0) if discount else "", "merchant": merchant, "category": category, "country": "International", "url": source["url"], "source_url": source["url"], "source_label": source["name"], "detected_at": now(), "last_checked": now(), "status": "active", "verified": False, "images": [], "image": "", "summary_type": "public_coupon_discovery"}
            if valid_record(deal) and (merchant.lower(), code.lower()) not in seen:
                seen.add((merchant.lower(), code.lower())); deals.append(deal)
    return deals
def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True); state = load_json(STATE, {"sources": {}, "deals": {}}); existing = load_json(OUT, [])
    if not isinstance(existing, list): existing = []
    # Purge legacy false positives before merging fresh discoveries.
    existing = [d for d in existing if valid_record(d)]
    by_key = {(d.get("merchant", "").lower(), d.get("code", "").lower()): d for d in existing if d.get("code")}
    changed_sources = 0; new_count = 0
    for source in SOURCES:
        previous = state["sources"].get(source["url"], {})
        try:
            response = requests.get(source["url"], headers=HEADERS, timeout=20); response.raise_for_status(); html = response.text
            digest, changed = source_changed(html, previous); state["sources"][source["url"]] = {"hash": digest, "last_checked": now(), "last_changed": previous.get("last_changed") or now()}
            if not changed: print(f"SKIP unchanged: {source['name']}"); continue
            state["sources"][source["url"]]["last_changed"] = now(); changed_sources += 1; deals = extract_deals(html, source)
            for deal in deals:
                key = (deal["merchant"].lower(), deal["code"].lower()); old = by_key.get(key)
                if old: old.update({"last_checked": now(), "status": "active", "source_url": deal["source_url"], "source_label": deal["source_label"]})
                else: by_key[key] = deal; new_count += 1
            print(f"CHANGED {source['name']}: discovered {len(deals)} offers")
        except Exception as exc:
            state["sources"][source["url"]] = {**previous, "last_checked": now(), "last_error": str(exc)[:240]}; print(f"SOURCE ERROR {source['name']}: {exc}")
    all_deals = list(by_key.values()); all_deals.sort(key=lambda d: d.get("last_checked", ""), reverse=True); all_deals = all_deals[:MAX_DEALS]
    save_json(OUT, all_deals); save_json(STATE, state); print(f"DONE: changed_sources={changed_sources}, new_deals={new_count}, total={len(all_deals)}")
if __name__ == "__main__": main()
