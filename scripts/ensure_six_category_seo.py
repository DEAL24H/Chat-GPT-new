import json
import re
from pathlib import Path
from html import escape
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "brand_catalog.json"
PUBLIC = ROOT
CATEGORY_SLUGS = {
    "Fashion": "fashion",
    "Beauty": "beauty",
    "Consumer": "consumer",
    "Home & Living": "home-living",
    "Food & Grocery": "food-grocery",
    "Travel & Hotels": "travel-hotels",
}

def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")

def load():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    return data["categories"]

def base_brand_page(category, brand):
    name = brand["name"]
    domain = brand["domain"]
    brand_slug = slug(name)
    today = date.today().isoformat()
    title = f"{name} Coupons & Promo Codes | DEAL24H"
    description = f"Find active {name} coupons, promo codes and deals. Check offers from the official {name} website on DEAL24H."
    official = f'<p><a href="https://{escape(domain)}" rel="nofollow">Visit official {escape(name)} website</a></p>' if domain else '<p>Official website verification is being completed for this priority brand.</p>'
    return f'''<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title>
<meta name="description" content="{escape(description)}">
<meta name="robots" content="index,follow">
<link rel="canonical" href="https://deal24h.net/brand/{escape(brand_slug)}/">
<meta property="og:title" content="{escape(title)}"><meta property="og:description" content="{escape(description)}">
<script async src="https://www.googletagmanager.com/gtag/js?id=G-R7E164DCZL"></script><script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}gtag('js',new Date());gtag('config','G-R7E164DCZL');</script>
</head><body>
<main><p><a href="/">DEAL24H</a> · <a href="/{CATEGORY_SLUGS[category]}/">{escape(category)}</a></p>
<h1>{escape(name)} Coupons & Promo Codes</h1>
<p>Official-domain offers and verified deal updates for {escape(name)}. This page is maintained for ongoing SEO and offer discovery.</p>
{official}
<p>Last catalog update: {today}</p>
</main></body></html>'''

def ensure_brand_page(category, brand):
    path = PUBLIC / "brand" / slug(brand["name"]) / "index.html"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(base_brand_page(category, brand), encoding="utf-8")
        return
    text = path.read_text(encoding="utf-8")
    robots = r'<meta\s+name=["\']robots["\'][^>]*>'
    replacement = '<meta name="robots" content="index,follow">'
    if re.search(robots, text, flags=re.I):
        text = re.sub(robots, replacement, text, count=1, flags=re.I)
    else:
        text = text.replace("</head>", replacement + "\n</head>", 1)
    path.write_text(text, encoding="utf-8")

def ensure_category_page(category, brands):
    cat_slug = CATEGORY_SLUGS[category]
    path = PUBLIC / cat_slug / "index.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    links = "\n".join(f'<li><a href="/brand/{escape(slug(b["name"]))}/">{escape(b["name"])}</a></li>' for b in brands)
    title = f"{category} Coupons, Promo Codes & Deals | DEAL24H"
    description = f"Browse 89 popular {category.lower()} brands on DEAL24H and find coupons, promo codes and deals from official websites."
    today = date.today().isoformat()
    html = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title><meta name="description" content="{escape(description)}"><meta name="robots" content="index,follow"><link rel="canonical" href="https://deal24h.net/{cat_slug}/"><script async src="https://www.googletagmanager.com/gtag/js?id=G-R7E164DCZL"></script><script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments)}}gtag('js',new Date());gtag('config','G-R7E164DCZL');</script></head><body><main><p><a href="/">DEAL24H</a></p><h1>{escape(category)} Coupons & Promo Codes</h1><p>Browse 89 priority brands in this category. Each brand has a dedicated SEO page and official-domain offer destination.</p><ul>{links}</ul><p>Last catalog update: {today}</p></main></body></html>'''
    path.write_text(html, encoding="utf-8")

def main():
    categories = load()
    if set(categories) != set(CATEGORY_SLUGS):
        raise SystemExit("SEO BUILD FAILED: category set mismatch")
    for category, brands in categories.items():
        if len(brands) != 89:
            raise SystemExit(f"SEO BUILD FAILED: {category} must have 89 brands")
        ensure_category_page(category, brands)
        for brand in brands:
            ensure_brand_page(category, brand)
    print("SEO READY: 6 category hubs + 534 indexable brand pages")

if __name__ == "__main__":
    main()
