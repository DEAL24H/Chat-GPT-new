import html
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "news.json"
BASE = "https://deal24h.github.io/Chat-GPT-new"
CATEGORIES = {"fashion": "Fashion", "beauty": "Beauty", "gaming": "Gaming", "consumer": "Consumer"}
CATEGORY_ALIASES = {"Thời trang": "fashion", "Fashion": "fashion", "Mỹ phẩm": "beauty", "Beauty": "beauty", "Game": "gaming", "Gaming": "gaming", "Hàng tiêu dùng": "consumer", "Consumer": "consumer"}
KNOWN_BRANDS = {'fashion': ['Nike', 'Adidas', 'Zara', 'H&M', 'UNIQLO', 'SHEIN', 'ASOS', "Levi's", 'PUMA', 'Crocs'], 'beauty': ["L'Oréal Paris", 'Maybelline', 'MAC Cosmetics', 'NYX Professional Makeup', 'e.l.f. Cosmetics', 'CeraVe', 'La Roche-Posay', 'Rare Beauty', 'Charlotte Tilbury', 'Sephora'], 'gaming': ['Steam', 'PlayStation', 'Xbox', 'Nintendo', 'Epic Games', 'Ubisoft', 'EA', 'Blizzard', 'Riot Games', 'Humble'], 'consumer': ['Apple', 'Samsung', 'Sony', 'Dell', 'Lenovo', 'HP', 'Logitech', 'Philips', 'IKEA', 'Dyson']}
BRAND_DOMAINS = {'nike': 'nike.com', 'adidas': 'adidas.com', 'zara': 'zara.com', 'h&m': 'hm.com', 'uniqlo': 'uniqlo.com', 'shein': 'shein.com', 'asos': 'asos.com', "levi's": 'levi.com', 'puma': 'puma.com', 'crocs': 'crocs.com', "l'oréal paris": 'lorealparisusa.com', 'maybelline': 'maybelline.com', 'mac cosmetics': 'maccosmetics.com', 'nyx professional makeup': 'nyxcosmetics.com', 'e.l.f. cosmetics': 'elfcosmetics.com', 'cerave': 'cerave.com', 'la roche-posay': 'laroche-posay.us', 'rare beauty': 'rarebeauty.com', 'charlotte tilbury': 'charlottetilbury.com', 'sephora': 'sephora.com', 'steam': 'store.steampowered.com', 'playstation': 'playstation.com', 'xbox': 'xbox.com', 'nintendo': 'nintendo.com', 'epic games': 'store.epicgames.com', 'ubisoft': 'ubisoft.com', 'ea': 'ea.com', 'blizzard': 'blizzard.com', 'riot games': 'riotgames.com', 'humble': 'humblebundle.com', 'apple': 'apple.com', 'samsung': 'samsung.com', 'sony': 'sony.com', 'dell': 'dell.com', 'lenovo': 'lenovo.com', 'hp': 'hp.com', 'logitech': 'logitech.com', 'philips': 'philips.com', 'ikea': 'ikea.com', 'dyson': 'dyson.com'}

def slug(value):
    value = value.lower().replace("&", " and ").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")

def esc(value):
    return html.escape(str(value or ""), quote=True)

def load():
    try:
        data = json.loads(DATA.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else data.get("items", [])
    except Exception:
        return []

def category_key(deal):
    return CATEGORY_ALIASES.get(deal.get("category"))

def brand_name(deal):
    merchant = str(deal.get("merchant", "")).strip()
    low = merchant.lower()
    for brand in sum(KNOWN_BRANDS.values(), []):
        if brand.lower() == low or brand.lower() in low:
            return brand
    return merchant.split("—")[0].strip()[:70]

def active(deal):
    if str(deal.get("status", "active")).lower() in {"expired", "inactive"}:
        return False
    if not (deal.get("code") or deal.get("promotion_url") or deal.get("source_url") or deal.get("url")):
        return False
    expiry = str(deal.get("expires_at", "")).strip()
    if expiry:
        try:
            dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt > datetime.now(timezone.utc)
        except ValueError:
            return False
    return True

def brand_domain(brand):
    return BRAND_DOMAINS.get(brand.lower(), "")

def brand_logo(brand):
    domain = brand_domain(brand)
    return f"https://www.google.com/s2/favicons?domain={quote(domain)}&sz=128" if domain else ""

def jsonld(data):
    return '<script type="application/ld+json">' + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + '</script>'

def page(title, description, canonical, body, structured=None, robots="index,follow"):
    schema = jsonld(structured) if structured else ""
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="{esc(description)}"><meta name="robots" content="{esc(robots)}"><link rel="canonical" href="{esc(canonical)}"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}"><meta property="og:url" content="{esc(canonical)}"><title>{esc(title)}</title>{schema}<link rel="stylesheet" href="/Chat-GPT-new/assets/style.css"></head><body><header class="topbar"><div class="wrap nav"><a class="brand" href="/Chat-GPT-new/">DEAL <span>24H</span></a><a href="/Chat-GPT-new/">Home</a></div></header><main class="wrap">{body}</main><footer><div class="wrap">© {datetime.now(timezone.utc).year} DEAL 24H · Public coupon and deal data with source attribution.</div></footer></body></html>'''

def deal_card(deal):
    brand = brand_name(deal)
    code = esc(deal.get("code"))
    discount = esc(deal.get("discount") or "Promotion offer")
    source = esc(deal.get("source_label") or "Official merchant source")
    url = esc(deal.get("promotion_url") or deal.get("source_url") or deal.get("url") or "#")
    expires = esc(deal.get("expires_at") or "")
    code_html = f'<div class="code"><strong>{code}</strong></div>' if code else '<div class="code"><strong>Promotion offer</strong></div>'
    link_label = "Get deal" if code else "View promotion"
    return f'<article class="card"><div class="brandrow"><div class="brandinfo"><strong>{esc(brand)}</strong><span class="tag">{esc(CATEGORIES.get(category_key(deal), "Deals"))} offer</span></div></div><h3>{esc(deal.get("title") or (f"{brand} Coupon Code" if code else f"{brand} Promotion"))}</h3><p>{discount}</p>{code_html}<a href="{url}" rel="nofollow noopener">{link_label} at {esc(brand)} ↗</a><small>Source: {source} · Last checked: {esc(deal.get("last_checked", ""))}</small>{f'<small>Expires: {expires}</small>' if expires else ''}</article>'

def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

def main():
    all_deals = load()
    deals = [d for d in all_deals if active(d)]
    grouped = defaultdict(list)
    for d in deals:
        cat = category_key(d)
        if cat:
            grouped[cat].append(d)
            grouped[(cat, brand_name(d).lower())].append(d)

    urls = {BASE + "/", BASE + "/fashion/", BASE + "/beauty/", BASE + "/gaming/", BASE + "/consumer/"}
    active_brands = []

    for cat, label in CATEGORIES.items():
        items = grouped.get(cat, [])
        cards = "".join(deal_card(d) for d in items[:60]) or '<p>No active coupon codes or promotion offers are currently listed. Check back soon for new offers.</p>'
        links = []
        for brand in KNOWN_BRANDS[cat]:
            brand_items = grouped.get((cat, brand.lower()), [])
            if brand_items:
                bslug = slug(brand)
                links.append(f'<li><a href="/Chat-GPT-new/brand/{bslug}/">{esc(brand)} coupons & promotions</a></li>')
        body = f'<section class="hero"><div><p class="eyebrow">INTERNATIONAL DEALS</p><h1>{label} Coupons & Promotions</h1><p class="lead">Fresh public coupon codes and promotion links for {label.lower()} stores. Offers are collected only from official merchant sources and shown with source attribution.</p></div></section><section><h2>Latest {label} offers</h2><div class="grid">{cards}</div></section><section><h2>Brands with active offers</h2><ul>{"".join(links) or "<li>No active brand offers currently listed.</li>"}</ul></section>'
        write(ROOT / cat / "index.html", page(f"{label} Coupons & Promotions | DEAL 24H", f"Find international {label.lower()} coupon codes, promotions and deals updated by DEAL 24H.", f"{BASE}/{cat}/", body))

    for cat, label in CATEGORIES.items():
        for brand in KNOWN_BRANDS[cat]:
            items = grouped.get((cat, brand.lower()), [])
            bslug = slug(brand)
            brand_url = f"{BASE}/brand/{bslug}/"
            if not items:
                write(ROOT / "brand" / bslug / "index.html", page(f"{brand} Coupons | DEAL 24H", f"No active {brand} coupon codes or promotion offers are currently available on DEAL 24H.", brand_url, None, robots="noindex,follow"))
                continue

            active_brands.append((brand, cat, items, brand_url))
            cards = "".join(deal_card(d) for d in items)
            logo = brand_logo(brand)
            logo_html = f'<img class="brandhero-img" src="{esc(logo)}" alt="{esc(brand)} logo" loading="eager">' if logo else ""
            body = f'<section class="hero"><div class="brandhero"><div class="brandhero-logo">{logo_html}</div><div><p class="eyebrow">{esc(label.upper())} · COUPONS & PROMOTIONS</p><h1>{esc(brand)} Coupons, Promo Codes & Deals</h1></div></div><p class="lead">Find active {esc(brand)} coupon codes and official promotion links from merchant sources.</p></section><section><h2>Active {esc(brand)} offers</h2><div class="grid">{cards}</div></section><p><a href="/Chat-GPT-new/{cat}/">← More {esc(label)} offers</a></p>'
            item_list = []
            for pos, d in enumerate(items, 1):
                item_list.append({"@type": "ListItem", "position": pos, "name": f"{brand} {'coupon code ' + str(d.get('code')) if d.get('code') else 'promotion offer'}", "url": d.get("promotion_url") or d.get("source_url") or d.get("url") or brand_url})
            schema = {"@context": "https://schema.org", "@graph": [{"@type": "Organization", "name": brand, "url": f"https://{brand_domain(brand)}"}, {"@type": "WebPage", "name": f"{brand} Coupons, Promo Codes & Deals", "url": brand_url, "description": f"Active {brand} coupon codes and promotion offers from official merchant sources."}, {"@type": "ItemList", "name": f"Active {brand} offers", "numberOfItems": len(items), "itemListElement": item_list}]}
            write(ROOT / "brand" / bslug / "index.html", page(f"{brand} Coupons, Promo Codes & Deals | DEAL 24H", f"Find active {brand} coupon codes, promo codes and promotion offers from official merchant sources on DEAL 24H.", brand_url, body=body, structured=schema))
            urls.add(brand_url)

    today = datetime.now(timezone.utc).date().isoformat()
    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for _, _, _, url in sorted(active_brands, key=lambda x: x[0].lower()):
        sitemap.append(f'<url><loc>{esc(url)}</loc><lastmod>{today}</lastmod></url>')
    sitemap.append("</urlset>")
    write(ROOT / "sitemap-brands.xml", "\n".join(sitemap) + "\n")

    sitemap_all = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url in sorted(urls):
        sitemap_all.append(f'<url><loc>{esc(url)}</loc><lastmod>{today}</lastmod></url>')
    sitemap_all.append("</urlset>")
    write(ROOT / "sitemap.xml", "\n".join(sitemap_all) + "\n")
    write(ROOT / "robots.txt", f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\nSitemap: {BASE}/sitemap-brands.xml\n")
    print(f"SEO v1 generated: {len(active_brands)} active brand URLs; {len(urls)} total indexable URLs")

if __name__ == "__main__":
    main()
