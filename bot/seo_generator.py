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
BASE = "https://deal24h.net"
CATEGORIES = {"Fashion": "Fashion", "Beauty": "Beauty", "Gaming": "Gaming", "Consumer": "Consumer"}


def esc(value):
    return html.escape(str(value or ""), quote=True)


def load_items():
    try:
        data = json.loads(DATA.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else data.get("items", [])
    except Exception:
        return []


def parse_expiry(text):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    patterns = [
        r"\b(?:valid|price valid)\s+[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4}\s*[-–]\s*(\w+\s+\d{1,2},?\s+\d{4})",
        r"\b(?:valid|price valid)[^.!?]{0,100}?\b(?:through|until|thru|ends?\s+(?:on)?)\s+([^.!?]{1,40})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if not match:
            continue
        raw = match.group(1).strip(" .")
        for fmt in ("%b %d %Y", "%B %d %Y"):
            try:
                return datetime.strptime(raw.replace(",", ""), fmt).replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                pass
        date_match = re.fullmatch(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", raw)
        if date_match:
            year = int(date_match.group(3)) if date_match.group(3) else datetime.now(timezone.utc).year
            if year < 100:
                year += 2000
            try:
                return datetime(year, int(date_match.group(1)), int(date_match.group(2)), tzinfo=timezone.utc).isoformat()
            except ValueError:
                pass
    return ""


def offer(item):
    item = canonicalize_item(item)
    brand = item.get("merchant", "").strip() or "Deal"
    text = re.sub(r"\s+", " ", str(item.get("content", "")).strip())
    pct = re.search(r"\b(\d{1,3})\s*%\s*off\b", text, re.I)
    save = re.search(r"\bsave\s+\$\s*([\d,.]+)", text, re.I)
    free = re.search(r"\bfree\s+shipping\b", text, re.I)
    student = re.search(r"\b(?:student|educator)\b", text, re.I)
    member = re.search(r"\b(?:member|family|club)\b", text, re.I)
    if pct:
        benefit = f"{pct.group(1)}% OFF"
    elif save:
        benefit = f"SAVE ${save.group(1)}"
    elif free:
        benefit = "FREE SHIPPING"
    elif student:
        benefit = "STUDENT OFFER"
    elif member:
        benefit = "MEMBER OFFER"
    elif item.get("discount") and re.search(r"%|off|save|shipping", str(item.get("discount")), re.I):
        benefit = str(item["discount"]).strip().upper()
    else:
        benefit = "OFFICIAL DEAL"

    title = str(item.get("title") or "").strip()
    generic = not title or re.search(r"[—-]\s*\$?\s*[\d,.]+(?:\s*[—-]\s*\$?\s*[\d,.]+)?$", title, re.I)
    if generic:
        if save:
            title = f"Save ${save.group(1)} on selected items"
        elif pct:
            title = f"{pct.group(1)}% off selected items"
        elif free:
            title = "Free shipping offer"
        elif student:
            title = "Student & educator offer"
        elif member:
            title = f"{brand} member offer"
        else:
            title = f"{brand} official deal"
    else:
        title = re.sub(rf"^{re.escape(brand)}\s*[—-]\s*", "", title, flags=re.I).strip()

    desc = re.sub(r"Review:\s*.*$", "", text, flags=re.I)
    desc = re.sub(r"More options.*$", "", desc, flags=re.I).strip()
    if len(desc) > 190:
        desc = desc[:187].rsplit(" ", 1)[0] + "…"

    expiry = item.get("expires_at") or parse_expiry(text)
    hit = resolve_brand(brand)
    return {
        "brand": brand,
        "category": hit["category"] if hit else "",
        "type": "PROMO CODE" if item.get("code") else "DEAL",
        "benefit": benefit,
        "title": title,
        "description": desc,
        "expiry": expiry,
        "code": str(item.get("code") or ""),
        "url": item.get("promotion_url") or item.get("source_url") or item.get("url") or "",
    }


def domain(brand):
    hit = resolve_brand(brand)
    return hit["domain"] if hit else ""


def logo(brand):
    value = domain(brand)
    return f"https://www.google.com/s2/favicons?domain={quote(value)}&sz=128" if value else ""


def jsonld(value):
    return '<script type="application/ld+json">' + json.dumps(value, ensure_ascii=False, separators=(",", ":")) + '</script>'


def page(title, desc, canonical, body, schema=None, robots="index,follow"):
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="{esc(desc)}"><meta name="robots" content="{esc(robots)}"><link rel="canonical" href="{esc(canonical)}"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}"><meta property="og:url" content="{esc(canonical)}"><title>{esc(title)}</title>{jsonld(schema) if schema else ""}<link rel="stylesheet" href="/assets/style.css?v=20260902i"></head><body><header class="topbar"><div class="wrap nav"><a class="brand" href="/">DEAL <span>24H</span></a><a href="/">Home</a></div></header><main class="wrap">{body}</main><footer><div class="wrap">© {datetime.now(timezone.utc).year} DEAL 24H · Official merchant source attribution.</div></footer></body></html>'''


def card(item):
    o = offer(item)
    brand = o["brand"]
    code = esc(o["code"])
    url = esc(o["url"])
    conditions = []
    logo_url = logo(brand)
    logo_html = f'<img class="brandlogo-img" src="{esc(logo_url)}" alt="{esc(brand)} logo" loading="lazy">' if logo_url else ""
    if o["expiry"]:
        try:
            conditions.append("Ends " + datetime.fromisoformat(str(o["expiry"]).replace("Z", "+00:00")).strftime("%b %-d, %Y"))
        except Exception:
            conditions.append("Ends " + str(o["expiry"]))
    if item.get("official_source"):
        conditions.append("✓ Official source")
    codebox = f'<div class="code"><span><small>CODE</small><strong>{code}</strong></span></div>' if code else ""
    cond = f'<div class="offer-conditions">{"".join("<span>" + esc(x) + "</span>" for x in conditions)}</div>' if conditions else ""
    cta = f'<a class="cta" href="{url}" target="_blank" rel="nofollow noopener sponsored">{"GET CODE" if code else "GET DEAL"} ↗</a>' if o["url"] else ""
    return f'<article class="card offer-card"><div class="brandrow"><div class="brandlogo">{logo_html}</div><div class="brandinfo"><a class="brandname" href="/brand/{brand_slug(brand)}/">{esc(brand)}</a><span class="tag">{esc(o["type"])} · {esc(o["category"] or "Deals")}</span></div></div><div class="offer-benefit">{esc(o["benefit"])}</div><h3>{esc(o["title"])}</h3><p>{esc(o["description"] or "Official merchant offer.")}</p>{codebox}{cond}<div class="meta">{cta}</div></article>'


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def main():
    deals = [canonicalize_item(d) for d in load_items() if is_active_offer(d)]
    grouped = defaultdict(list)
    for deal in deals:
        hit = resolve_brand(deal.get("merchant"))
        if not hit:
            continue
        category = hit["category"]
        grouped[category].append(deal)
        grouped[(category, hit["name"].lower())].append(deal)

    urls = {BASE + "/"}
    active_brands = []
    for category, label in CATEGORIES.items():
        items = grouped.get(category, [])
        cards = "".join(card(d) for d in items[:60]) or '<p>No active coupons or deals are currently listed. Check back soon for new offers.</p>'
        links = [f'<li><a href="/brand/{brand_slug(entry["name"])}/">{esc(entry["name"])} coupons & deals</a></li>' for entry in CATALOG.get(category, []) if grouped.get((category, entry["name"].lower()), [])]
        body = f'<section class="hero"><div><p class="eyebrow">COUPON CODES · PROMO CODES · DEALS</p><h1>{label} Coupons, Promo Codes & Deals</h1><p class="lead">Active coupon codes, promo codes and official deals for {label.lower()} brands. Offers are collected from official merchant sources.</p></div></section><section><h2>Latest {label} offers</h2><div class="grid">{cards}</div></section><section><h2>Brands with active offers</h2><ul>{"".join(links) or "<li>No active brand offers currently listed.</li>"}</ul></section>'
        write(ROOT / category.lower() / "index.html", page(f"{label} Coupons, Promo Codes & Deals | DEAL 24H", f"Find active {label.lower()} coupon codes, promo codes and deals from official merchant sources.", f"{BASE}/{category.lower()}/", body))

    for category, label in CATEGORIES.items():
        for entry in CATALOG.get(category, []):
            brand = entry["name"]
            items = grouped.get((category, brand.lower()), [])
            url = f"{BASE}/brand/{brand_slug(brand)}/"
            path = ROOT / "brand" / brand_slug(brand) / "index.html"
            if not items:
                write(path, page(f"{brand} Coupons, Promo Codes & Deals | DEAL 24H", f"No active {brand} coupon codes or deals are currently listed on DEAL 24H.", url, "<p>No active offers are currently listed.</p>", robots="noindex,follow"))
                continue

            active_brands.append((brand, category, items, url))
            cards = "".join(card(d) for d in items)
            logo_url = logo(brand)
            logo_html = f'<img class="brandhero-img" src="{esc(logo_url)}" alt="{esc(brand)} logo" loading="eager">' if logo_url else ""
            body = f'<section class="hero"><div class="brandhero"><div class="brandhero-logo">{logo_html}</div><div><p class="eyebrow">{esc(label.upper())} · COUPONS & DEALS</p><h1>{esc(brand)} Coupons, Promo Codes & Deals</h1></div></div><p class="lead">Find active {esc(brand)} coupon codes and official deals. Each offer is attributed to an official merchant source.</p></section><section><h2>Active {esc(brand)} offers</h2><div class="grid">{cards}</div></section><p><a href="/{category.lower()}/">← More {esc(label)} offers</a></p>'
            elements = []
            for i, deal in enumerate(items, 1):
                destination = deal.get("promotion_url") or deal.get("source_url") or deal.get("url") or url
                elements.append({"@type": "ListItem", "position": i, "name": f"{brand} " + (f"coupon code {deal.get('code')}" if deal.get("code") else "deal"), "url": destination})
            schema = {"@context": "https://schema.org", "@graph": [{"@type": "Organization", "name": brand, "url": f"https://{domain(brand)}"}, {"@type": "WebPage", "name": f"{brand} Coupons, Promo Codes & Deals", "url": url, "description": f"Active {brand} coupon codes and deals from official merchant sources."}, {"@type": "ItemList", "name": f"Active {brand} offers", "numberOfItems": len(items), "itemListElement": elements}]}
            write(path, page(f"{brand} Coupons, Promo Codes & Deals | DEAL 24H", f"Find active {brand} coupon codes, promo codes and deals from official merchant sources on DEAL 24H.", url, body, schema))
            urls.add(url)

    today = datetime.now(timezone.utc).date().isoformat()
    sitemap_brands = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sitemap_brands += [f'<url><loc>{esc(url)}</loc><lastmod>{today}</lastmod></url>' for _, _, _, url in sorted(active_brands, key=lambda x: x[0].lower())]
    sitemap_brands.append('</urlset>')
    write(ROOT / "sitemap-brands.xml", "\n".join(sitemap_brands) + "\n")

    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sitemap += [f'<url><loc>{esc(url)}</loc><lastmod>{today}</lastmod></url>' for url in sorted(urls)]
    sitemap.append('</urlset>')
    write(ROOT / "sitemap.xml", "\n".join(sitemap) + "\n")
    write(ROOT / "robots.txt", f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\nSitemap: {BASE}/sitemap-brands.xml\n")
    print(f"SEO offer-first generated: {len(active_brands)} active brand URLs; {len(urls)} total indexable URLs")


if __name__ == "__main__":
    main()
