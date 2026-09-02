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
HEADERS = {"User-Agent": "Deal24H/2.0 (+DEAL24H official-source coupon collector)"}
MAX_DEALS = 1200
PARSER_VERSION = 2

# Discovery is restricted to official merchant-owned domains.
# Third-party coupon aggregators are never accepted as publication sources.
SOURCES = [
    {"name":"Nike Official Promo Terms","url":"https://www.nike.com/gb/promo-terms-bts2026","domain":"nike.com","category":"Thời trang","merchant":"Nike"},
    {"name":"adidas Official Sale","url":"https://www.adidas.com/us/promotions","domain":"adidas.com","category":"Thời trang","merchant":"Adidas"},
    {"name":"Zara Official","url":"https://www.zara.com/vn/vi/","domain":"zara.com","category":"Thời trang","merchant":"Zara"},
    {"name":"H&M Official Offers","url":"https://www2.hm.com/en_us/index.html","domain":"hm.com","category":"Thời trang","merchant":"H&M"},
    {"name":"UNIQLO Official","url":"https://www.uniqlo.com/vn/vi/","domain":"uniqlo.com","category":"Thời trang","merchant":"UNIQLO"},
    {"name":"SHEIN Official Coupon Help","url":"https://m.shein.com/us/coupon-a-368.html","domain":"shein.com","category":"Thời trang","merchant":"SHEIN"},
    {"name":"ASOS Official Promo Help","url":"https://www.asos.com/customer-care/payment-promos-gift-vouchers/how-do-your-promo-codes-work/","domain":"asos.com","category":"Thời trang","merchant":"ASOS"},
    {"name":"Levi's Official Promotions","url":"https://help.levi.com/hc/en-us/articles/10872016647821-Levi-s-Promotional-Offers","domain":"levi.com","category":"Thời trang","merchant":"Levi's"},
    {"name":"PUMA Official Promotions","url":"https://vn.puma.com/vn/en/promotions-and-sale.html","domain":"puma.com","category":"Thời trang","merchant":"PUMA"},
    {"name":"Crocs Official Promotions","url":"https://www.crocs.com/c/promotions","domain":"crocs.com","category":"Thời trang","merchant":"Crocs"},
    {"name":"L'Oreal Paris Official","url":"https://www.lorealparisusa.com/","domain":"lorealparisusa.com","category":"Mỹ phẩm","merchant":"L'Oréal Paris"},
    {"name":"Maybelline Official","url":"https://www.maybelline.com/","domain":"maybelline.com","category":"Mỹ phẩm","merchant":"Maybelline"},
    {"name":"MAC Cosmetics Official Offers","url":"https://www.maccosmetics.com/pages/offer-details","domain":"maccosmetics.com","category":"Mỹ phẩm","merchant":"MAC Cosmetics"},
    {"name":"NYX Professional Makeup Promotions","url":"https://www.nyxcosmetics.com/promotions.html","domain":"nyxcosmetics.com","category":"Mỹ phẩm","merchant":"NYX Professional Makeup"},
    {"name":"e.l.f. Cosmetics Official","url":"https://www.elfcosmetics.com/","domain":"elfcosmetics.com","category":"Mỹ phẩm","merchant":"e.l.f. Cosmetics"},
    {"name":"CeraVe Official Coupon","url":"https://www.cerave.com/sb-coupon-offer","domain":"cerave.com","category":"Mỹ phẩm","merchant":"CeraVe"},
    {"name":"La Roche-Posay Official","url":"https://www.laroche-posay.us/","domain":"laroche-posay.us","category":"Mỹ phẩm","merchant":"La Roche-Posay"},
    {"name":"Rare Beauty Official Promotions","url":"https://www.rarebeauty.com/pages/salesandpromotions","domain":"rarebeauty.com","category":"Mỹ phẩm","merchant":"Rare Beauty"},
    {"name":"Charlotte Tilbury Official","url":"https://www.charlottetilbury.com/us/","domain":"charlottetilbury.com","category":"Mỹ phẩm","merchant":"Charlotte Tilbury"},
    {"name":"Sephora Official Beauty Offers","url":"https://www.sephora.com/beauty/beauty-offers","domain":"sephora.com","category":"Mỹ phẩm","merchant":"Sephora"},
    {"name":"Steam Official Store","url":"https://store.steampowered.com/","domain":"steampowered.com","category":"Game","merchant":"Steam"},
    {"name":"PlayStation Official Offers","url":"https://www.playstation.com/en-us/deals/","domain":"playstation.com","category":"Game","merchant":"PlayStation"},
    {"name":"Xbox Official Sales","url":"https://www.xbox.com/en-US/promotions/sales/sales-and-specials","domain":"xbox.com","category":"Game","merchant":"Xbox"},
    {"name":"Nintendo Official Store","url":"https://www.nintendo.com/us/store/","domain":"nintendo.com","category":"Game","merchant":"Nintendo"},
    {"name":"Epic Games Store","url":"https://store.epicgames.com/en-US/","domain":"epicgames.com","category":"Game","merchant":"Epic Games"},
    {"name":"Ubisoft Official Store","url":"https://store.ubisoft.com/","domain":"ubisoft.com","category":"Game","merchant":"Ubisoft"},
    {"name":"EA Official Offers","url":"https://www.ea.com/games","domain":"ea.com","category":"Game","merchant":"EA"},
    {"name":"Blizzard Official Shop","url":"https://www.blizzard.com/en-us/shop/","domain":"blizzard.com","category":"Game","merchant":"Blizzard"},
    {"name":"Riot Games Official","url":"https://www.riotgames.com/en","domain":"riotgames.com","category":"Game","merchant":"Riot Games"},
    {"name":"Humble Official Store","url":"https://www.humblebundle.com/store","domain":"humblebundle.com","category":"Game","merchant":"Humble"},
    {"name":"Apple Official Education Offers","url":"https://www.apple.com/us-edu/shop/buy-mac","domain":"apple.com","category":"Hàng tiêu dùng","merchant":"Apple"},
    {"name":"Samsung Official Promotions","url":"https://www.samsung.com/us/promotions/","domain":"samsung.com","category":"Hàng tiêu dùng","merchant":"Samsung"},
    {"name":"Sony Official","url":"https://electronics.sony.com/","domain":"sony.com","category":"Hàng tiêu dùng","merchant":"Sony"},
    {"name":"Dell Official Deals","url":"https://www.dell.com/en-us/shop/deals","domain":"dell.com","category":"Hàng tiêu dùng","merchant":"Dell"},
    {"name":"Lenovo Official Deals","url":"https://www.lenovo.com/us/en/d/deals/","domain":"lenovo.com","category":"Hàng tiêu dùng","merchant":"Lenovo"},
    {"name":"HP Official Coupons","url":"https://www.hp.com/us-en/shop/cv/coupons-promo","domain":"hp.com","category":"Hàng tiêu dùng","merchant":"HP"},
    {"name":"Logitech Official Promotions","url":"https://www.logitech.com/en-us/promotions","domain":"logitech.com","category":"Hàng tiêu dùng","merchant":"Logitech"},
    {"name":"Philips Official","url":"https://www.usa.philips.com/c-m/consumer","domain":"philips.com","category":"Hàng tiêu dùng","merchant":"Philips"},
    {"name":"IKEA Official Offers","url":"https://www.ikea.com/us/en/offers/","domain":"ikea.com","category":"Hàng tiêu dùng","merchant":"IKEA"},
    {"name":"Dyson Official Offers","url":"https://www.dyson.com/en","domain":"dyson.com","category":"Hàng tiêu dùng","merchant":"Dyson"},
]

CATEGORIES = {
    "Thời trang": ["fashion","apparel","clothing","shoes","sneaker","dress","jeans","bag","accessories","nike","adidas","puma","shein","asos","zara","h&m","uniqlo","levi","crocs"],
    "Mỹ phẩm": ["beauty","cosmetic","skincare","makeup","cosmetics","sephora","l'oreal","loreal","maybelline","mac","nyx","elf","cerave","la roche","rare beauty","charlotte tilbury"],
    "Game": ["gaming","game","steam","epic","playstation","xbox","nintendo","ubisoft","ea","blizzard","riot","humble"],
    "Hàng tiêu dùng": ["consumer","electronics","electronic","laptop","computer","phone","smartphone","tablet","tv","television","headphone","monitor","printer","home","household","kitchen","appliance","furniture","apple","samsung","sony","dell","lenovo","hp","logitech","philips","ikea","dyson"],
}

CODE_RE = r"[A-Z0-9][A-Z0-9_-]{3,24}"
EXPLICIT_CODE_PATTERNS = [
    re.compile(r"\b(?:use|enter)\s+(?:the\s+)?(?:promo(?:tion)?\s+)?code\s*(?:is\s*)?[:=]\s*[\"'“”]?((?:%s))[\"'“”]?\b" % CODE_RE, re.I),
    re.compile(r"\b(?:use|enter)\s+(?:the\s+)?(?:promo(?:tion)?\s+)?code\s+[\"'“”]((?:%s))[\"'“”]" % CODE_RE, re.I),
    re.compile(r"\b(?:promo(?:tion)?\s+code|coupon\s+code|voucher\s+code|code)\s*[:=]\s*[\"'“”]?((?:%s))[\"'“”]?\b" % CODE_RE, re.I),
]
DISCOUNT_RE = re.compile(r"(?:\$\s?\d+(?:\.\d+)?|\d{1,3}%|\d{1,3}\s?%\s?off|\d{1,3}%\s?off)", re.I)
BAD_CODES = {
    "COPY","CODE","COUPON","COUPONS","TODAY","DEAL","DEALS","SALE","NEW","SHOP","HTTPS","WWW",
    "CLICK","VERIFY","AUTHORITY","EDITORS","EDITOR","HAND-TESTED","TESTED","POPULAR","LATEST",
    "ACTIVE","EXCLUSIVE","PROMO","PROMOS","OFFER","OFFERS","WITH","ENTER","THIS","YOUR","FROM",
    "ONLY","APPLY","HELP","PAGE","NEXT","SIGN","JOIN","REQUIRED","INTO"
}

MONTHS = {
    "jan":1,"january":1,"feb":2,"february":2,"mar":3,"march":3,"apr":4,"april":4,
    "may":5,"jun":6,"june":6,"jul":7,"july":7,"aug":8,"august":8,"sep":9,
    "sept":9,"september":9,"oct":10,"october":10,"nov":11,"november":11,
    "dec":12,"december":12,
}

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
    return digest, digest != previous.get("hash") or previous.get("parser_version") != PARSER_VERSION

def category_for(text, fallback="Tổng hợp"):
    value = text.lower()
    for category, words in CATEGORIES.items():
        if any(re.search(r"\b" + re.escape(word) + r"\b", value) for word in words):
            return category
    return "Hàng tiêu dùng" if fallback == "Tổng hợp" else fallback

def parse_date(raw):
    raw = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", raw.strip(), flags=re.I)
    raw = re.sub(r"\s+", " ", raw).replace("/", "-")
    for fmt in ("%m-%d-%Y","%m-%d-%y","%d-%m-%Y","%d-%m-%y","%b %d, %Y","%B %d, %Y","%b %d %Y","%B %d %Y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            pass
    m = re.fullmatch(r"(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})", raw)
    if m:
        month = MONTHS.get(m.group(2).lower())
        if month:
            return datetime(int(m.group(3)), month, int(m.group(1)), tzinfo=timezone.utc).isoformat()
    return ""

def parse_expiry(text):
    text = clean(text)
    range_patterns = [
        r"\bvalid\s+from\s+\d{1,2}\s+[A-Za-z]{3,9}\s*[-–]\s*(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
        r"\b(?:from|starting)\s+\d{1,2}\s+[A-Za-z]{3,9}\s*[-–]\s*(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
    ]
    for pattern in range_patterns:
        match = re.search(pattern, text, re.I)
        if match:
            parsed = parse_date(match.group(1))
            if parsed:
                return parsed
    patterns = [
        r"\b(?:expires?|expiry|expiration|ends?|valid until|valid through|good through|offer ends?|ends on)\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"\b(?:expires?|expiry|expiration|ends?|valid until|valid through|good through|offer ends?|ends on)\s*[:\-]?\s*([A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            parsed = parse_date(match.group(1))
            if parsed:
                return parsed
    match = re.search(r"\b(?:valid|promotion|offer)[^.!?]{0,80}?\b(?:through|until)\s+([A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4}))", text, re.I)
    return parse_date(match.group(1)) if match else ""

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
    if not code or code in BAD_CODES or len(code) < 4 or not merchant or not bool(deal.get("code_context")):
        return False
    if code.isdigit() or not re.fullmatch(CODE_RE, code):
        return False
    if not bool(deal.get("official_source")) or not source_url or not source_domain:
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
    deals, seen = [], set()
    for block in blocks:
        explicit = []
        for pattern in EXPLICIT_CODE_PATTERNS:
            for match in pattern.findall(block):
                code = match.upper()
                if code not in BAD_CODES and code not in explicit:
                    explicit.append(code)
        if not explicit:
            continue
        merchant = source["merchant"]
        discount = DISCOUNT_RE.search(block)
        category = category_for(block + " " + merchant, source["category"])
        expires_at = parse_expiry(block)
        for code in explicit[:5]:
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
                "code_context": True,
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
    kept, removed, rejected = [], 0, 0
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
                "parser_version": PARSER_VERSION,
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
                        "code_context": True,
                        "category": deal["category"],
                        "content": deal["content"],
                        "discount": deal["discount"],
                    })
                    if deal.get("expires_at"):
                        old["expires_at"] = deal["expires_at"]
                else:
                    by_key[key] = deal
                    new_count += 1
            print(f"CHANGED official {source['name']}: discovered {len(deals)} offers")
        except Exception as exc:
            state["sources"][source["url"]] = {**previous, "last_checked": now(), "last_error": str(exc)[:240], "parser_version": PARSER_VERSION}
            print(f"OFFICIAL SOURCE ERROR {source['name']}: {exc}")

    all_deals = list(by_key.values())
    all_deals.sort(key=lambda d: d.get("last_checked", ""), reverse=True)
    save_json(OUT, all_deals[:MAX_DEALS])
    save_json(STATE, state)
    print(
        f"DONE: official_only=true, parser_version={PARSER_VERSION}, changed_sources={changed_sources}, "
        f"new_deals={new_count}, expired_removed={removed_expired}, invalid_removed={rejected_non_official}, "
        f"total={len(all_deals[:MAX_DEALS])}"
    )

if __name__ == "__main__": main()
