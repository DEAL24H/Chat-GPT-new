import html
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "news.json"
BASE = "https://chayso2015-ctrl.github.io/Chat-GPT-new"
CATEGORIES = {"fashion": "Fashion", "beauty": "Beauty", "gaming": "Gaming"}
CATEGORY_ALIASES = {"Thời trang": "fashion", "Fashion": "fashion", "Mỹ phẩm": "beauty", "Beauty": "beauty", "Game": "gaming", "Gaming": "gaming"}
KNOWN_BRANDS = {
    "fashion": ["Nike", "Adidas", "PUMA", "SHEIN", "ASOS", "Zara", "H&M", "UNIQLO", "Mango", "Crocs", "Gap", "Converse", "Under Armour"],
    "beauty": ["Sephora", "Ulta", "NARS", "MAC", "CeraVe", "The Ordinary", "Glossier", "Clinique", "Paula's Choice", "Farmacy", "Bobbi Brown", "Kosas"],
    "gaming": ["Steam", "Epic Games", "PlayStation", "Xbox", "Nintendo", "Humble", "Fanatical", "Ubisoft", "EA"],
}
BRAND_DOMAINS = {"dell":"dell.com", "nike":"nike.com", "adidas":"adidas.com", "puma":"puma.com", "shein":"shein.com", "asos":"asos.com", "zara":"zara.com", "h&m":"hm.com", "uniqlo":"uniqlo.com", "mango":"shop.mango.com", "crocs":"crocs.com", "gap":"gap.com", "converse":"converse.com", "under armour":"underarmour.com", "sephora":"sephora.com", "ulta":"ulta.com", "nars":"narscosmetics.com", "mac":"maccosmetics.com", "cerave":"cerave.com", "the ordinary":"theordinary.com", "glossier":"glossier.com", "clinique":"clinique.com", "paula's choice":"paulaschoice.com", "farmacy":"farmacybeauty.com", "bobbi brown":"bobbibrowncosmetics.com", "kosas":"kosas.com", "steam":"store.steampowered.com", "epic games":"store.epicgames.com", "playstation":"playstation.com", "xbox":"xbox.com", "nintendo":"nintendo.com", "humble":"humblebundle.com", "fanatical":"fanatical.com", "ubisoft":"ubisoft.com", "ea":"ea.com", "reebok":"reebok.com", "iherb":"iherb.com", "lenovo":"lenovo.com", "hp":"hp.com", "best buy":"bestbuy.com"}

def slug(value):
    value = value.lower().replace("&", " and ").replace("'", "")
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")

def esc(value): return html.escape(str(value or ""), quote=True)
def load():
    try:
        data = json.loads(DATA.read_text(encoding="utf-8")); return data if isinstance(data, list) else data.get("items", [])
    except Exception: return []
def category_key(deal): return CATEGORY_ALIASES.get(deal.get("category"))
def brand_name(deal):
    merchant = str(deal.get("merchant", "")).strip(); low = merchant.lower()
    for brand in sum(KNOWN_BRANDS.values(), []):
        if brand.lower() in low: return brand
    return merchant.split("—")[0].strip()[:70]
def active(deal): return str(deal.get("status", "active")).lower() not in {"expired", "inactive"} and bool(deal.get("code"))
def brand_domain(brand):
    key = brand.lower(); return BRAND_DOMAINS.get(key, "")
def brand_logo(brand):
    domain = brand_domain(brand)
    return f"https://www.google.com/s2/favicons?domain={quote(domain)}&sz=128" if domain else ""
def page(title, description, canonical, body):
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="{esc(description)}"><meta name="robots" content="index,follow"><link rel="canonical" href="{esc(canonical)}"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}"><title>{esc(title)}</title><link rel="stylesheet" href="/Chat-GPT-new/assets/style.css"></head><body><header class="topbar"><div class="wrap nav"><a class="brand" href="/Chat-GPT-new/">DEAL <span>24H</span></a><a href="/Chat-GPT-new/">Home</a></div></header><main class="wrap">{body}</main><footer><div class="wrap">© {datetime.now(timezone.utc).year} DEAL 24H · Public coupon and deal data with source attribution.</div></footer></body></html>'''
def deal_card(deal):
    brand = brand_name(deal); logo = brand_logo(brand); code = esc(deal.get("code")); discount = esc(deal.get("discount") or "Coupon deal"); source = esc(deal.get("source_label") or "Public source"); url = esc(deal.get("url") or deal.get("source_url") or "#")
    initials = esc("".join(x[0] for x in re.findall(r"[A-Za-z0-9]+", brand)[:2]).upper() or brand[:2].upper())
    image = f'<img class="brandlogo-img" src="{esc(logo)}" alt="{esc(brand)} logo" loading="lazy" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'grid\'">' if logo else ""
    return f'<article class="card"><div class="brandrow"><div class="brandlogo">{image}<span class="brandfallback" style="display:{"none" if logo else "grid"}">{initials}</span></div><div class="brandinfo"><strong>{esc(brand)}</strong><span class="tag">{esc(CATEGORIES.get(category_key(deal), "Deals"))} coupon</span></div></div><h3>{esc(brand)} Coupon Code</h3><p>{discount}</p><div class="code"><strong>{code}</strong></div><a href="{url}" rel="nofollow noopener">Get deal at {esc(brand)}</a><small>Source: {source} · Last checked: {esc(deal.get("last_checked", ""))}</small></article>'
def write(path, content): path.parent.mkdir(parents=True, exist_ok=True); path.write_text(content, encoding="utf-8")
def main():
    deals = [d for d in load() if active(d)]; grouped = defaultdict(list)
    for d in deals:
        cat = category_key(d)
        if cat: grouped[cat].append(d); grouped[(cat, brand_name(d).lower())].append(d)
    urls = {BASE + "/", BASE + "/fashion/", BASE + "/beauty/", BASE + "/gaming/"}
    for cat, label in CATEGORIES.items():
        items = grouped.get(cat, []); cards = "".join(deal_card(d) for d in items[:60]) or '<p>No active coupon codes are currently listed. Check back soon for new offers.</p>'
        links = []
        for brand in sorted({brand_name(d) for d in items if brand_name(d)}, key=str.lower):
            bslug = slug(brand); links.append(f'<li><a href="/Chat-GPT-new/{cat}/{bslug}-coupons/">{esc(brand)} coupons</a></li>'); urls.add(f"{BASE}/{cat}/{bslug}-coupons/")
        body = f'<section class="hero"><div><p class="eyebrow">INTERNATIONAL COUPON CODES</p><h1>{label} Coupons & Promo Codes</h1><p class="lead">Fresh public coupon codes and deals for {label.lower()} stores. Codes are collected from public sources and shown with source attribution.</p></div></section><section><h2>Latest {label} coupon codes</h2><div class="grid">{cards}</div></section><section><h2>Popular {label} brands</h2><ul>{"".join(links)}</ul></section>'
        write(ROOT / cat / "index.html", page(f"{label} Coupons & Promo Codes | DEAL 24H", f"Find international {label.lower()} coupon codes, promo codes and deals updated by DEAL 24H.", f"{BASE}/{cat}/", body))
    for cat in CATEGORIES:
        for brand in sorted({brand_name(d) for d in grouped.get(cat, []) if brand_name(d)}, key=str.lower):
            items = grouped.get((cat, brand.lower()), []); bslug = slug(brand)
            if not items: continue
            cards = "".join(deal_card(d) for d in items[:40]); logo = brand_logo(brand); initials = esc("".join(x[0] for x in re.findall(r"[A-Za-z0-9]+", brand)[:2]).upper() or brand[:2].upper())
            hero_img = f'<img class="brandhero-img" src="{esc(logo)}" alt="{esc(brand)} logo" loading="eager" onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'grid\'">' if logo else ""
            hero = f'<div class="brandhero"><div class="brandhero-logo">{hero_img}<span class="brandfallback" style="display:{"none" if logo else "grid"}">{initials}</span></div><div><p class="eyebrow">{esc(CATEGORIES[cat].upper())} · COUPON CODES</p><h1>{esc(brand)} Coupon Codes & Promo Codes</h1></div></div>'
            regions = ", ".join(sorted({str(d.get("country", "")).strip() for d in items if d.get("country")})[:8]) or "International"
            title = f"{brand} Coupon Codes & Promo Codes | DEAL 24H"; desc = f"Find active {brand} coupon codes, promo codes and deals. See discounts, source attribution and latest checks on DEAL 24H."
            body = f'<section class="hero">{hero}<p class="lead">Find the latest public coupon codes and deals for {esc(brand)}. Availability can vary by country, account, product and checkout.</p></section><section><h2>Active {esc(brand)} coupon codes</h2><div class="grid">{cards}</div></section><section><h2>Availability</h2><p>Known listing region: {esc(regions)}. Always check the merchant checkout for the final terms and eligibility.</p></section><p><a href="/Chat-GPT-new/{cat}/">← More {esc(CATEGORIES[cat])} coupons</a></p>'
            write(ROOT / cat / f"{bslug}-coupons" / "index.html", page(title, desc, f"{BASE}/{cat}/{bslug}-coupons/", body))
    write(ROOT / "robots.txt", f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\n")
    now = datetime.now(timezone.utc).date().isoformat(); sitemap = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url in sorted(urls): sitemap.append(f'<url><loc>{esc(url)}</loc><lastmod>{now}</lastmod></url>')
    sitemap.append('</urlset>'); write(ROOT / "sitemap.xml", "\n".join(sitemap) + "\n"); print(f"SEO generated: {len(urls)} indexable URLs")
if __name__ == "__main__": main()
