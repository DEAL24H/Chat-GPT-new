import hashlib
import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from catalog_utils import canonicalize_item, category_for_brand
from news_bot import EXPLICIT_CODE_PATTERNS, clean, load_json, now, official_domain, parse_expiry, save_json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "news.json"
TIMEOUT = 20

# 19 additional brands per category. Marketplace sources are explicitly classified.
S=[('New Balance','newbalance.com','https://www.newbalance.com/promotions/','Thời trang','brand'),('Converse','converse.com','https://www.converse.com/c/promotions','Thời trang','brand'),('Foot Locker','footlocker.com','https://www.footlocker.com/c/promo-codes.html','Thời trang','brand'),('Finish Line','finishline.com','https://www.finishline.com/store/campaigns/','Thời trang','brand'),('Gap','gap.com','https://www.gap.com/browse/category.do?cid=5664','Thời trang','brand'),('Old Navy','oldnavy.gap.com','https://oldnavy.gap.com/browse/category.do?cid=1127651','Thời trang','brand'),('Banana Republic','bananarepublic.gap.com','https://bananarepublic.gap.com/browse/category.do?cid=6759','Thời trang','brand'),('Calvin Klein','calvinklein.us','https://www.calvinklein.us/en/sale','Thời trang','brand'),('Tommy Hilfiger','tommy.com','https://usa.tommy.com/en/sale','Thời trang','brand'),('Ralph Lauren','ralphlauren.com','https://www.ralphlauren.com/sale','Thời trang','brand'),('Under Armour','underarmour.com','https://www.underarmour.com/en-us/c/sale/','Thời trang','brand'),('ASICS','asics.com','https://www.asics.com/us/en-us/sale/','Thời trang','brand'),('Reebok','reebok.com','https://www.reebok.com/c/sale','Thời trang','brand'),('Skechers','skechers.com','https://www.skechers.com/sale/','Thời trang','brand'),('JD Sports','jdsports.com','https://www.jdsports.com/store/campaigns/','Thời trang','brand'),('Forever 21','forever21.com','https://www.forever21.com/us/shop/','Thời trang','brand'),('Urban Outfitters','urbanoutfitters.com','https://www.urbanoutfitters.com/sale','Thời trang','brand'),('Nordstrom','nordstrom.com','https://www.nordstrom.com/browse/sale','Thời trang','brand'),("Macy's",'macys.com','https://www.macys.com/shop/sale','Thời trang','brand'),('Ulta Beauty','ulta.com','https://www.ulta.com/promotion/all','Mỹ phẩm','brand'),('Douglas','douglas.de','https://www.douglas.de/de/c/sale/','Mỹ phẩm','brand'),('The Ordinary','theordinary.com','https://theordinary.com/en-us/offers','Mỹ phẩm','brand'),('Estée Lauder','esteelauder.com','https://www.esteelauder.com/offers','Mỹ phẩm','brand'),('Clinique','clinique.com','https://www.clinique.com/offers','Mỹ phẩm','brand'),("Kiehl's",'kiehls.com','https://www.kiehls.com/offers/','Mỹ phẩm','brand'),('Lancôme','lancome-usa.com','https://www.lancome-usa.com/offers/','Mỹ phẩm','brand'),('Fenty Beauty','fentybeauty.com','https://fentybeauty.com/collections/sale','Mỹ phẩm','brand'),('Glossier','glossier.com','https://www.glossier.com/collections/sale','Mỹ phẩm','brand'),('Benefit Cosmetics','benefitcosmetics.com','https://www.benefitcosmetics.com/en-us/promotions','Mỹ phẩm','brand'),('Tarte','tartecosmetics.com','https://tartecosmetics.com/shop/promotions/','Mỹ phẩm','brand'),('Too Faced','toofaced.com','https://www.toofaced.com/l/promotions','Mỹ phẩm','brand'),('Morphe','morphe.com','https://www.morphe.com/pages/sale','Mỹ phẩm','brand'),("Paula's Choice",'paulaschoice.com','https://www.paulaschoice.com/paulas-choice-coupons','Mỹ phẩm','brand'),('Drunk Elephant','drunkelephant.com','https://www.drunkelephant.com/','Mỹ phẩm','brand'),('Olay','olay.com','https://www.olay.com/en-us/offers/','Mỹ phẩm','brand'),('Neutrogena','neutrogena.com','https://www.neutrogena.com/offers/','Mỹ phẩm','brand'),('Dove','dove.com','https://www.dove.com/us/en/offers.html','Mỹ phẩm','brand'),('Bath & Body Works','bathandbodyworks.com','https://www.bathandbodyworks.com/c/sale','Mỹ phẩm','brand'),('GOG','gog.com','https://www.gog.com/en/','Game','brand'),('Green Man Gaming','greenmangaming.com','https://www.greenmangaming.com/','Game','brand'),('Fanatical','fanatical.com','https://www.fanatical.com/en/','Game','brand'),('GameStop','gamestop.com','https://www.gamestop.com/deals/','Game','brand'),('Razer','razer.com','https://www.razer.com/store','Game','brand'),('SteelSeries','steelseries.com','https://steelseries.com/sale','Game','brand'),('Corsair','corsair.com','https://www.corsair.com/us/en/c/sale','Game','brand'),('ASUS ROG','rog.asus.com','https://rog.asus.com/us/deals/','Game','brand'),('Alienware','alienware.com','https://www.dell.com/en-us/shop/alienware/scr/pcd/alienware','Game','brand'),('MSI Gaming','msi.com','https://us.msi.com/Promotion','Game','brand'),('CD PROJEKT','cdprojektred.com','https://www.cdprojektred.com/en/','Game','brand'),('itch.io','itch.io','https://itch.io/','Game','brand'),('Play-Asia','play-asia.com','https://www.play-asia.com/','Game','brand'),('GameSir','gamesir.hk','https://gamesir.hk/','Game','brand'),('8BitDo','8bitdo.com','https://www.8bitdo.com/','Game','brand'),('HyperX','hyperx.com','https://hyperx.com/collections/sale','Game','brand'),('Turtle Beach','turtlebeach.com','https://www.turtlebeach.com/collections/sale','Game','brand'),('NVIDIA GeForce NOW','nvidia.com','https://www.nvidia.com/en-us/geforce-now/','Game','brand'),('Meta Quest','meta.com','https://www.meta.com/quest/','Game','brand'),('Amazon','amazon.com','https://www.amazon.com/deals','Hàng tiêu dùng','marketplace'),('Walmart','walmart.com','https://www.walmart.com/shop/deals','Hàng tiêu dùng','marketplace'),('eBay','ebay.com','https://www.ebay.com/e/coupons','Hàng tiêu dùng','marketplace'),('Best Buy','bestbuy.com','https://www.bestbuy.com/site/electronics/coupons/pcmcat164400050000.c?id=pcmcat164400050000','Hàng tiêu dùng','brand'),('Target','target.com','https://www.target.com/circle/offers/-/N-55xpe','Hàng tiêu dùng','brand'),('Costco','costco.com','https://www.costco.com/coupons.html','Hàng tiêu dùng','brand'),('Home Depot','homedepot.com','https://www.homedepot.com/c/coupons','Hàng tiêu dùng','brand'),("Lowe's",'lowes.com','https://www.lowes.com/l/savings.html','Hàng tiêu dùng','brand'),('Wayfair','wayfair.com','https://www.wayfair.com/deals','Hàng tiêu dùng','marketplace'),('Newegg','newegg.com','https://www.newegg.com/promotions','Hàng tiêu dùng','marketplace'),('B&H Photo','bhphotovideo.com','https://www.bhphotovideo.com/c/browse/deals/ci/13002','Hàng tiêu dùng','brand'),('Micro Center','microcenter.com','https://www.microcenter.com/site/content/specialoffers.aspx','Hàng tiêu dùng','brand'),('Office Depot','officedepot.com','https://www.officedepot.com/cm/promotions','Hàng tiêu dùng','brand'),('Staples','staples.com','https://www.staples.com/deals','Hàng tiêu dùng','brand'),("Kohl's",'kohls.com','https://www.kohls.com/catalog/sale.jsp','Hàng tiêu dùng','brand'),('HomeGoods','homegoods.com','https://www.homegoods.com/','Hàng tiêu dùng','brand'),('Overstock','overstock.com','https://www.overstock.com/deals','Hàng tiêu dùng','brand'),('Bed Bath & Beyond','bedbathandbeyond.com','https://www.bedbathandbeyond.com/','Hàng tiêu dùng','brand'),("Sam's Club",'samsclub.com','https://www.samsclub.com/content/coupons','Hàng tiêu dùng','brand')]

BAD={"COPY","CODE","COUPON","COUPONS","TODAY","DEAL","DEALS","SALE","NEW","SHOP","HTTPS","WWW","CLICK","VERIFY","POPULAR","LATEST","ACTIVE","EXCLUSIVE","PROMO","PROMOS","OFFER","OFFERS","WITH","ENTER","THIS","YOUR","FROM","ONLY","APPLY","HELP","PAGE","NEXT","SIGN","JOIN","REQUIRED","INTO","LIMITED"}
PROMO=re.compile(r"\b(?:sale|deal|deals|offer|offers|promotion|promotions|coupon|coupons|discount|save|savings|clearance)\b",re.I)


def official(s):
    host = official_domain(s[2]); domain = s[1].removeprefix("www.")
    return host == domain or host.endswith("." + domain)


def fetch(url):
    response = requests.get(url, headers={"User-Agent":"Deal24H/2.1 (+DEAL24H official-source collector)"}, timeout=TIMEOUT)
    response.raise_for_status()
    return response.text


def text_blocks(page):
    soup = BeautifulSoup(page, "html.parser")
    for node in soup(["script", "style", "noscript", "svg"]):
        node.decompose()
    out = []
    seen = set()
    for node in soup.find_all(["article", "section", "li", "p", "div"]):
        text = clean(node.get_text(" ", strip=True))
        key = re.sub(r"\W+", " ", text.lower()).strip()
        if 35 <= len(text) <= 600 and PROMO.search(text) and key not in seen:
            seen.add(key)
            out.append(text)
    return out[:6]


def codes(text):
    out = []
    for pattern in EXPLICIT_CODE_PATTERNS:
        for match in pattern.finditer(text):
            code = match.group(1).upper()
            if code not in BAD and code not in out:
                out.append(code)
    return out[:6]


def rec(source, content, code=""):
    discount_match = re.search(r"(?:\$\s?\d+(?:\.\d+)?|\d{1,3}%\s?(?:off)?|\d{1,3}\s?%\s?off)", content, re.I)
    discount = discount_match.group(0) if discount_match else ""
    name, host, url, fallback_category, source_type = source
    category = category_for_brand(name) or fallback_category
    rid = hashlib.sha256(f"{host}|{name}|{code}|{content}".encode()).hexdigest()[:16]
    return {
        "id": rid,
        "title": f"{name} — {discount or ('Coupon code ' + code if code else 'Official promotion')}",
        "content": content,
        "code": code,
        "discount": discount,
        "merchant": name,
        "category": category,
        "country": "International",
        "url": url,
        "source_url": url,
        "promotion_url": url,
        "source_label": f"{name} Official {'Marketplace' if source_type == 'marketplace' else 'Promotions'}",
        "source_domain": host,
        "official_source": True,
        "code_context": bool(code),
        "detected_at": now(),
        "last_checked": now(),
        "expires_at": parse_expiry(content) or "",
        "status": "active",
        "verified": False,
        "verification_method": "official_merchant_page",
        "images": [],
        "image": "",
        "summary_type": "official_marketplace_coupon_discovery" if source_type == "marketplace" else "official_merchant_promotion_discovery",
        "expanded_source_collector": True,
    }


def main():
    data = load_json(OUT, [])
    data = data if isinstance(data, list) else []
    domains = {source[1] for source in S}
    added = 0
    failures = 0
    for source in S:
        if not official(source):
            failures += 1
            continue
        try:
            page = fetch(source[2])
            raw = clean(page)
            blocks = text_blocks(page)
            found_codes = codes(raw)
            local = []
            for code in found_codes:
                context = next((block for block in blocks if code.lower() in block.lower()), f"Official promotion code {code} published on the merchant's official website.")
                local.append(rec(source, context, code))
            if not found_codes:
                local.extend(rec(source, block) for block in blocks[:3])
            data = [x for x in data if not (x.get("source_domain") == source[1] and x.get("expanded_source_collector"))]
            data.extend(local)
            added += len(local)
        except Exception:
            failures += 1

    deduped = {}
    for item in data:
        item = canonicalize_item(item)
        key = (item.get("source_domain"), item.get("merchant"), item.get("code"), re.sub(r"\s+", " ", item.get("content", "")).strip().lower())
        deduped[key] = item
    save_json(OUT, list(deduped.values())[-4000:])
    print(f"Expanded official source scan: {len(S)} sources, {added} records added, {failures} source failures.")


if __name__ == "__main__":
    main()
