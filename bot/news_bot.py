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
HEADERS = {"User-Agent": "Deal24H/1.2 (+DEAL24H official-source coupon collector)"}
MAX_DEALS = 1200

# SECURITY RULE: coupon codes may only be published when discovered on the
# merchant's own domain. Third-party coupon aggregators are never published.
SOURCES = [
    {"name":"Nike Official UK Promo","url":"https://www.nike.com/gb/promo-code","domain":"nike.com","category":"Thời trang","merchant":"Nike"},
    {"name":"adidas Official Sale","url":"https://www.adidas.com/us/regular-sale","domain":"adidas.com","category":"Thời trang","merchant":"Adidas"},
    {"name":"Zara Official","url":"https://www.zara.com/vn/vi/","domain":"zara.com","category":"Thời trang","merchant":"Zara"},
    {"name":"H&M Official","url":"https://www2.hm.com/en_us/member/offers/bonus.html","domain":"hm.com","category":"Thời trang","merchant":"H&M"},
    {"name":"UNIQLO Official","url":"https://www.uniqlo.com/vn/vi/","domain":"uniqlo.com","category":"Thời trang","merchant":"UNIQLO"},
    {"name":"SHEIN Official Coupon Help","url":"https://m.shein.com/us/coupon-a-368.html","domain":"shein.com","category":"Thời trang","merchant":"SHEIN"},
    {"name":"ASOS Official Promo Help","url":"https://www.asos.com/customer-care/payment-promos-gift-vouchers/how-do-your-promo-codes-work/","domain":"asos.com","category":"Thời trang","merchant":"ASOS"},
    {"name":"Levi's Official Promotions","url":"https://help.levi.com/hc/en-us/articles/10872016647821-Levi-s-Promotional-Offers","domain":"levi.com","category":"Thời trang","merchant":"Levi's"},
    {"name":"PUMA Official Promotions","url":"https://vn.puma.com/vn/en/promotions-and-sale.html","domain":"puma.com","category":"Thời trang","merchant":"PUMA"},
    {"name":"Crocs Official Promotions","url":"https://www.crocs.com/c/promotions","domain":"crocs.com","category":"Thời trang","merchant":"Crocs"},
]

CATEGORIES = {
    "Thời trang": ["fashion", "apparel", "clothing", "shoes", "sneaker", "dress", "jeans", "bag", "accessories", "nike", "adidas", "puma", "shein", "asos", "zara", "h&m", "uniqlo", "levi", "crocs"],
    "Mỹ phẩm": ["beauty", "cosmetic", "skincare", "makeup", "cosmetics", "sephora", "ulta", "nars", "mac", "cerave", "ordinary", "glossier", "clinique", "paula's choice", "farmacy", "bobbi brown", "kosas"],
    "Game": ["gaming", "game", "steam", "epic", "playstation", "xbox", "nintendo", "ubisoft", "ea", "blizzard", "riot", "humble"],
    "Hàng tiêu dùng": ["consumer", "electronics", "electronic", "laptop", "computer", "phone", "smartphone", "tablet", "tv", "television", "headphone", "monitor", "printer", "home", "household", "kitchen", "appliance", "furniture", "mattress", "pet", "baby", "grocery", "food", "office", "apple", "samsung", "sony", "dell", "lenovo", "hp", "logitech", "philips", "ikea", "dyson"]
}

CODE_RE = re.compile(r"\b[A-Z0-9][A-Z0-9_-]{3,24}\b")
DISCOUNT_RE = re.compile(r"(?:\$\s?\d+(?:\.\d+)?|\d{1,3}%|\d{1,3}\s?%\s?off|\d{1,3}%\s?off)", re.I)
BAD_CODES = {"COPY","CODE","COUPON","COUPONS","TODAY","DEAL","DEALS","SALE","NEW","SHOP","HTTPS","WWW","CLICK","VERIFY","AUTHORITY","EDITORS","EDITOR","HAND-TESTED","TESTED","POPULAR","LATEST","ACTIVE","EXCLUSIVE","PROMO","PROMOS","OFFER","OFFERS","WITH","ENTER","THIS","YOUR","FROM","ONLY","APPLY","HELP","PAGE","NEXT","SIGN","JOIN"}
KNOWN_BRANDS = ["Nike","Adidas","Zara","H&M","UNIQLO","SHEIN","ASOS","Levi's","PUMA","Crocs","L’Oréal Paris","Maybelline","MAC Cosmetics","NYX Professional Makeup","e.l.f. Cosmetics","CeraVe","La Roche-Posay","Rare Beauty","Charlotte Tilbury","Sephora","Steam","PlayStation","Xbox","Nintendo","Epic Games","Ubisoft","EA","Blizzard","Riot Games","Humble","Apple","Samsung","Sony","Dell","Lenovo","HP","Logitech","Philips","IKEA","Dyson"]


def clean(text):
    return re.sub(r"\s+", " ", BeautifulSoup(text or "", "html.parser").get_text(" ")).strip()


def now():
    return datetime.now(timezone.utc).isoformat()


def load_json(path, fallback):
    if not path.exists(): return fallback
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return fallback


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def source_changed(html, previous):
    digest = hashlib.sha256(html.encode("utf-8", errors="ignore")).hexdigest()
    return digest, digest != previous.get("hash")


def category_for(text, fallback="Tổng hợp"):
    value = text.lower()
    for category, words in CATEGORIES.items():
        if any(re.search(r"\b" + re.escape(word) + r"\b", value) for word in words): return category
    return "Hàng tiêu dùng" if fallback == "Tổng hợp" else fallback


def parse_expiry(text):
    text = clean(text)
    patterns = [
        r"(?:expires?|expiry|expiration|ends?|valid until|valid through|good through|offer ends?)\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
        r"(?:expires?|expiry|expiration|ends?|valid until|valid through|good through|offer ends?)\s*[:\-]?\s*([A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match: continue
        raw = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", match.group(1), flags=re.I).replace("/", "-")
        for fmt in ["%m-%d-%Y","%m-%d-%y","%d-%m-%Y","%d-%m-%y","%b %d, %Y","%B %d, %Y","%b %d %Y","%B %d %Y"]:
            try: return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc).isoformat()
            except ValueError: pass
    return ""


def official_domain(url): return urlparse(url).netloc.lower().removeprefix("www.")


def is_official_source(source):
    domain = official_domain(source.get("url", "")); allowed = source.get("domain", "").lower().removeprefix("www.")
    return bool(domain and allowed and (domain == allowed or domain.endswith("." + allowed)))


def valid_record(deal):
    code = str(deal.get("code", "")).strip().upper(); merchant = str(deal.get("merchant", "")).strip()
    source_url = str(deal.get("source_url", "")).strip(); source_domain = str(deal.get("source_domain", "")).strip().lower().removeprefix("www.")
    if not code or code in BAD_CODES or len(code) < 4 or not merchant: return False
    if code.isdigit(): return False
    if not re.fullmatch(r"[A-Z0-9_-]{4,25}", code): return False
    if not bool(deal.get("official_source")) or not source_url or not source_domain: return False
    host = official_domain(source_url)
    if not (host == source_domain or host.endswith("." + source_domain)): return False
    if re.search(r"couponkent|couponscouter|dealatlas|simplycodes", host, re.I): return False
    return True


def extract_deals(html, source):
    if not is_official_source(source): return []
    soup = BeautifulSoup(html, "html.parser"); blocks = []
    for tag in soup.find_all(["article","li","div","section"]):
        text = clean(tag.get_text(" ", strip=True))
        if 25 <= len(text) <= 700 and re.search(r"\b(?:code|coupon|promo|voucher)\b", text, re.I): blocks.append(text)
    if not blocks: blocks = [clean(x) for x in soup.stripped_strings]
    deals = []; seen = set()
    for block in blocks:
        codes = []; upper = block.upper()
        for match in CODE_RE.findall(upper):
            if match in BAD_CODES or len(match) < 4 or match.isdigit(): continue
            pos = upper.find(match); window = block[max(0,pos-90):pos+len(match)+90].lower()
            cue = bool(re.search(r"\b(?:coupon|promo|promotion|voucher)\s*(?:code|codes)?\b|\bcode\b|\benter\s+code\b|\buse\s+code\b", window))
            if cue: codes.append(match)
        if not codes: continue
        merchant = source["merchant"]; discount = DISCOUNT_RE.search(block); category = category_for(block + " " + merchant, source["category"]); expires_at = parse_expiry(block)
        for code in codes[:5]:
            deal = {"id":hashlib.sha256((source["name"]+"|"+merchant+"|"+code).encode()).hexdigest()[:16],"title":f"{merchant} — {discount.group(0) if discount else 'Official promo code'}","content":block[:500],"code":code,"discount":discount.group(0) if discount else "","merchant":merchant,"category":category,"country":"International","url":source["url"],"source_url":source["url"],"source_label":source["name"],"source_domain":source["domain"],"official_source":True,"detected_at":now(),"last_checked":now(),"expires_at":expires_at,"status":"active","verified":False,"verification_method":"official_merchant_page","images":[],"image":"","summary_type":"official_merchant_discovery"}
            if valid_record(deal) and (merchant.lower(),code.lower()) not in seen: seen.add((merchant.lower(),code.lower())); deals.append(deal)
    return deals


def purge_expired(existing):
    current = datetime.now(timezone.utc); kept=[]; removed=0; rejected=0
    for deal in existing:
        if not valid_record(deal): rejected += 1; continue
        expiry = str(deal.get("expires_at", "")).strip()
        if expiry:
            try:
                if datetime.fromisoformat(expiry.replace("Z","+00:00")) <= current: removed += 1; continue
            except ValueError: pass
        kept.append(deal)
    return kept, removed, rejected


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True); state=load_json(STATE,{"sources":{},"deals":{}}); existing=load_json(OUT,[])
    if not isinstance(existing,list): existing=[]
    existing,removed_expired,rejected_non_official=purge_expired(existing)
    by_key={(d.get("merchant","").lower(),d.get("code","").lower()):d for d in existing if d.get("code")}; changed_sources=0; new_count=0
    for source in SOURCES:
        previous=state["sources"].get(source["url"],{})
        try:
            if not is_official_source(source): print(f"BLOCKED NON-OFFICIAL SOURCE: {source['url']}"); continue
            response=requests.get(source["url"],headers=HEADERS,timeout=25); response.raise_for_status(); html=response.text
            digest,changed=source_changed(html,previous); state["sources"][source["url"]]={"hash":digest,"last_checked":now(),"last_changed":previous.get("last_changed") or now(),"official_domain":source["domain"]}
            if not changed: print(f"SKIP unchanged official source: {source['name']}"); continue
            state["sources"][source["url"]]["last_changed"]=now(); changed_sources += 1; deals=extract_deals(html,source)
            for deal in deals:
                key=(deal["merchant"].lower(),deal["code"].lower()); old=by_key.get(key)
                if old:
                    old.update({"last_checked":now(),"status":"active","source_url":deal["source_url"],"source_label":deal["source_label"],"source_domain":deal["source_domain"],"official_source":True,"verification_method":"official_merchant_page","category":deal["category"],"content":deal["content"],"discount":deal["discount"]})
                    if deal.get("expires_at"): old["expires_at"]=deal["expires_at"]
                else: by_key[key]=deal; new_count += 1
            print(f"CHANGED official {source['name']}: discovered {len(deals)} offers")
        except Exception as exc:
            state["sources"][source["url"]]={**previous,"last_checked":now(),"last_error":str(exc)[:240]}; print(f"OFFICIAL SOURCE ERROR {source['name']}: {exc}")
    all_deals=list(by_key.values()); all_deals.sort(key=lambda d:d.get("last_checked",""),reverse=True); save_json(OUT,all_deals[:MAX_DEALS]); save_json(STATE,state)
    print(f"DONE: official_only=true, changed_sources={changed_sources}, new_deals={new_count}, expired_removed={removed_expired}, non_official_removed={rejected_non_official}, total={len(all_deals[:MAX_DEALS])}")

if __name__ == "__main__": main()
