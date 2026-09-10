import html
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from catalog_utils import CATALOG, brand_slug, canonicalize_item, is_active_offer, resolve_brand

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "news.json"
SEO_INDEX = ROOT / "seo" / "seo-index.json"
BASE = "https://deal24h.net"
GA4 = "G-R7E164DCZL"
CATEGORY_SLUGS = {"Fashion": "fashion", "Electronics": "electronics", "Beauty & Personal Care": "beauty-personal-care", "Home & Living": "home-and-living"}


def esc(v):
    return html.escape(str(v or ""), quote=True)


def load_items():
    try:
        data = json.loads(DATA.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else data.get("items", [])
    except Exception:
        return []


def load_seo_index():
    if not SEO_INDEX.exists():
        raise SystemExit("SEO NAVIGATION FAILED: missing canonical seo-index.json")
    data = json.loads(SEO_INDEX.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("offers"), list):
        raise SystemExit("SEO NAVIGATION FAILED: invalid canonical seo-index.json")
    return data["offers"]


def domain(brand):
    entry = resolve_brand(brand)
    return entry.get("domain", "") if entry else ""


def logo(brand):
    d = domain(brand)
    return f"https://www.google.com/s2/favicons?domain={quote(d)}&sz=128" if d else ""


def official_homepage(brand):
    d = domain(brand).strip().removeprefix("www.")
    return f"https://{d}/" if d else ""


def page(title, description, canonical, body, schema=None):
    ld = f'<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False, separators=(",", ":"))}</script>' if schema else ""
    ga = f'''<script async src="https://www.googletagmanager.com/gtag/js?id={GA4}"></script><script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','{GA4}',{{anonymize_ip:true}});</script>'''
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="{esc(description)}"><meta name="robots" content="index,follow"><link rel="canonical" href="{esc(canonical)}"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(description)}"><meta property="og:url" content="{esc(canonical)}"><title>{esc(title)}</title>{ld}<link rel="stylesheet" href="/assets/style.css?v=20260903d">{ga}</head><body><header class="topbar"><div class="wrap nav"><a class="brand" href="/">DEAL 24H</a><a href="/">Home</a></div></header><main class="wrap">{body}</main><footer><div class="wrap">© {datetime.now(timezone.utc).year} DEAL 24H · Official merchant source attribution.</div></footer></body></html>'''


def offer_card(item):
    brand = item.get("merchant", "Deal")
    code = str(item.get("code") or "").strip()
    purchase = str(item.get("final_purchase_url") or "").strip()
    text = re.sub(r"\s+", " ", str(item.get("content") or "")).strip()
    match = re.search(r"\b(\d{1,3})\s*%\s*off\b", text, re.I)
    benefit = f"{match.group(1)}% OFF" if match else str(item.get("discount") or "OFFICIAL DEAL").upper()
    title = re.sub(rf"^{re.escape(brand)}\s*[—-]\s*", "", str(item.get("title") or "").strip(), flags=re.I) or f"{brand} official deal"
    text = text[:187].rsplit(" ", 1)[0] + "…" if len(text) > 190 else text
    img = logo(brand)
    image = f'<img class="brandlogo-img" src="{esc(img)}" alt="{esc(brand)} logo" loading="lazy">' if img else ""
    affiliate = bool(item.get("is_affiliate") and item.get("affiliate_tracking_url"))
    destination = str(item.get("affiliate_tracking_url") or purchase).strip() if affiliate else purchase
    rel = "sponsored nofollow noopener" if affiliate else "nofollow noopener noreferrer"
    cta = f'<a class="cta" href="{esc(destination)}" target="_blank" rel="{rel}">{"GET CODE" if code else "GET DEAL"} ↗</a>' if destination else ""
    code_html = f'<div class="code"><small>CODE</small><strong>{esc(code)}</strong></div>' if code else ""
    return f'<article class="card offer-card"><div class="brandrow"><div class="brandlogo">{image}</div><div class="brandinfo"><a class="brandname" href="/brand/{brand_slug(brand)}/">{esc(brand)}</a><span class="tag">{esc("PROMO CODE" if code else "DEAL")} · {esc(item.get("category", "Deals"))}</span></div></div><div class="offer-benefit">{esc(benefit)}</div><h3>{esc(title)}</h3><p>{esc(text or "Official merchant offer.")}</p>{code_html}<div class="meta">{cta}</div></article>'


def brand_intro(brand, category):
    category_copy = {"Fashion": "fashion and apparel", "Electronics": "consumer electronics and technology", "Beauty & Personal Care": "beauty and personal care", "Home & Living": "home, furniture and everyday living products"}.get(category, category.lower())
    official = official_homepage(brand)
    link = f'<a href="{esc(official)}" target="_blank" rel="noopener">Visit the official {esc(brand)} website</a>' if official else ""
    return f'<section class="brand-about" aria-labelledby="brand-about-title"><h2 id="brand-about-title">About {esc(brand)}</h2><p>{esc(brand)} is a well-known name in {category_copy}. {link} to explore the brand’s official products and information.</p></section>'


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main():
    seo_records = load_seo_index()
    seo_by_category = defaultdict(list)
    seo_by_brand = defaultdict(list)
    seo_title_counts = defaultdict(int)
    for record in seo_records:
        canonical = str(record.get("canonical") or "").strip()
        merchant = str(record.get("merchant") or "").strip()
        category = str(record.get("category") or "").strip()
        title = str(record.get("title") or "").strip()
        if not canonical or not merchant or not category or not title:
            raise SystemExit("SEO NAVIGATION FAILED: incomplete canonical SEO record")
        seo_by_category[category].append(record)
        seo_by_brand[merchant].append(record)
        seo_title_counts[(merchant.casefold(), category.casefold(), title.casefold())] += 1

    # A title is descriptive text, not a unique offer identity. Multiple verified
    # offers may legitimately share the same title while having different URLs.
    duplicate_titles = sum(1 for count in seo_title_counts.values() if count > 1)
    if len({str(r.get("canonical")) for r in seo_records}) != len(seo_records):
        raise SystemExit("SEO NAVIGATION FAILED: duplicate canonical URLs")

    deals = [canonicalize_item(x) for x in load_items() if is_active_offer(x) and x.get("final_purchase_url")]
    by_category = defaultdict(list)
    for item in deals:
        resolved = resolve_brand(item.get("merchant"))
        if resolved:
            item["merchant"] = resolved["name"]
            item["category"] = resolved["category"]
            by_category[resolved["category"]].append(item)

    brand_urls = []
    category_urls = []
    for category, entries in CATALOG.items():
        category_slug = CATEGORY_SLUGS.get(category, brand_slug(category))
        category_url = f"{BASE}/{category_slug}/"
        category_urls.append(category_url)
        active = by_category.get(category, [])
        cards = "".join(offer_card(x) for x in active[:60]) or '<p>No active coupons or deals are currently listed.</p>'
        brand_links = "".join(f'<li><a href="/brand/{brand_slug(e["name"])}/">{esc(e["name"])} brand page</a></li>' for e in entries)
        seo_links = "".join(f'<li><a href="{esc(r["canonical"])}">{esc(r["merchant"])} — {esc(r["title"])}</a></li>' for r in seo_by_category.get(category, []))
        body = f'<section class="hero"><p class="eyebrow">BRANDS · OFFERS</p><h1>{esc(category)} Brands & Offers</h1><p class="lead">Browse catalog brands and every verified offer SEO page in this category.</p></section><section><h2>Latest {esc(category)} offers</h2><div class="grid">{cards}</div></section><section><h2>Verified offer pages</h2><ul>{seo_links}</ul></section><section><h2>Brands</h2><ul>{brand_links}</ul></section>'
        schema = {"@context": "https://schema.org", "@type": "CollectionPage", "name": f"{category} Brands & Offers", "url": category_url}
        write(ROOT / category_slug / "index.html", page(f"{category} Brands & Offers | DEAL 24H", f"Browse {category.lower()} brands and verified offers on DEAL 24H.", category_url, body, schema))

        for entry in entries:
            brand = entry["name"]
            brand_url = f"{BASE}/brand/{brand_slug(brand)}/"
            path = ROOT / "brand" / brand_slug(brand) / "index.html"
            img = logo(brand)
            image = f'<img class="brandhero-img" src="{esc(img)}" alt="{esc(brand)} logo" loading="eager">' if img else '<span class="brandfallback" aria-hidden="true">B</span>'
            brand_seo = seo_by_brand.get(brand, [])
            offer_links = "".join(f'<li><a href="{esc(r["canonical"])}">{esc(r["title"])}</a></li>' for r in brand_seo)
            offer_section = f'<section><h2>Verified {esc(brand)} offers</h2><ul>{offer_links}</ul></section>' if brand_seo else '<section><h2>Verified offers</h2><p>No active verified offers are currently listed.</p></section>'
            has_verified_offers = bool(brand_seo)
            robots = "index,follow" if has_verified_offers else "noindex,follow"
            body = f'<section class="hero"><div class="brandhero"><div class="brandhero-logo">{image}</div><div><p class="eyebrow">{esc(category.upper())} · BRAND</p><h1>About {esc(brand)}</h1></div></div><p class="lead">A short introduction to {esc(brand)} and its official website.</p></section>{brand_intro(brand, category)}{offer_section}<p><a class="cta" href="{esc(official_homepage(brand))}" target="_blank" rel="noopener">Visit {esc(brand)} official website ↗</a></p>'
            schema = {"@context": "https://schema.org", "@graph": [{"@type": "Organization", "name": brand, "url": official_homepage(brand)}, {"@type": "WebPage", "name": f"About {brand}", "url": brand_url}]}
            write(path, page(f"About {brand} | DEAL 24H", f"A short introduction to {brand} with a link to the official {brand} website.", brand_url, body, schema).replace('<meta name="robots" content="index,follow">', f'<meta name="robots" content="{robots}">'))
            if has_verified_offers:
                brand_urls.append(brand_url)

    today = datetime.now(timezone.utc).date().isoformat()

    def sitemap(urls):
        unique = sorted(set(urls))
        return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(f'<url><loc>{esc(u)}</loc><lastmod>{today}</lastmod></url>' for u in unique) + '\n</urlset>\n'

    seo_urls = [str(r["canonical"]) for r in seo_records]
    write(ROOT / "sitemap-brands.xml", sitemap(brand_urls))
    write(ROOT / "sitemap.xml", sitemap([BASE + "/"] + category_urls + brand_urls + seo_urls))
    write(ROOT / "robots.txt", f"User-agent: *\nAllow: /\nDisallow: /admin/\nDisallow: /dashboard/\nDisallow: /data/\nSitemap: {BASE}/sitemap.xml\nSitemap: {BASE}/sitemap-brands.xml\nSitemap: {BASE}/sitemap-seo.xml\n")
    print(f"SEO 999 catalog: persistent_brand_pages={len(brand_urls)}, category_pages={len(category_urls)}, linked_seo_pages={len(seo_records)}, duplicate_title_groups={duplicate_titles}")


if __name__ == "__main__":
    main()
