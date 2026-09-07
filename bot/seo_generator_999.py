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

def esc(v): return html.escape(str(v or ""), quote=True)
def load_items():
    try:
        d=json.loads(DATA.read_text(encoding="utf-8")); return d if isinstance(d,list) else d.get("items",[])
    except Exception: return []
def load_seo_index():
    try:
        d=json.loads(SEO_INDEX.read_text(encoding="utf-8")); return d.get("offers",[]) if isinstance(d,dict) else []
    except Exception as exc:
        raise SystemExit(f"SEO NAVIGATION FAILED: missing canonical seo-index.json: {exc}")
def domain(b):
    h=resolve_brand(b); return h.get("domain","") if h else ""
def logo(b):
    d=domain(b); return f"https://www.google.com/s2/favicons?domain={quote(d)}&sz=128" if d else ""
def official_homepage(b):
    d=domain(b).strip().removeprefix("www."); return f"https://{d}/" if d else ""
def page(t,d,c,b,r="index,follow",s=None):
    ld=f'<script type="application/ld+json">{json.dumps(s,ensure_ascii=False,separators=(",",":"))}</script>' if s else ""
    ga=f'''<script async src="https://www.googletagmanager.com/gtag/js?id={GA4}"></script><script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','{GA4}',{{anonymize_ip:true}});</script>'''
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="{esc(d)}"><meta name="robots" content="{r}"><link rel="canonical" href="{esc(c)}"><meta property="og:title" content="{esc(t)}"><meta property="og:description" content="{esc(d)}"><meta property="og:url" content="{esc(c)}"><title>{esc(t)}</title>{ld}<link rel="stylesheet" href="/assets/style.css?v=20260903d">{ga}</head><body><header class="topbar"><div class="wrap nav"><a class="brand" href="/">DEAL 24H</a><a href="/">Home</a></div></header><main class="wrap">{b}</main><footer><div class="wrap">© {datetime.now(timezone.utc).year} DEAL 24H · Official merchant source attribution.</div></footer></body></html>'''
def card(x, seo_by_key):
    b=x.get("merchant","Deal"); code=x.get("code",""); u=x.get("final_purchase_url",""); text=re.sub(r"\s+"," ",str(x.get("content", ""))).strip(); p=re.search(r"\b(\d{1,3})\s*%\s*off\b",text,re.I); benefit=f"{p.group(1)}% OFF" if p else str(x.get("discount") or "OFFICIAL DEAL").upper(); title=re.sub(rf"^{re.escape(b)}\s*[—-]\s*", "", str(x.get("title") or "").strip(), flags=re.I) or f"{b} official deal"; text=text[:187].rsplit(" ",1)[0]+"…" if len(text)>190 else text; img=logo(b); ih=f'<img class="brandlogo-img" src="{esc(img)}" alt="{esc(b)} logo" loading="lazy">' if img else ""; cta=f'<a class="cta" href="{esc(u)}" target="_blank" rel="nofollow noopener sponsored">{"GET CODE" if code else "GET DEAL"} ↗</a>' if u else ""; ch=f'<div class="code"><small>CODE</small><strong>{esc(code)}</strong></div>' if code else ""; key=(str(b).casefold(),str(x.get("category")).casefold(),re.sub(r"\s+"," ",title).strip().casefold()); seo=seo_by_key.get(key); seo_link=f'<p><a href="{esc(seo["canonical"]) if seo else "#"}">{"Open SEO deal page ↗" if seo else ""}</a></p>' if seo else ""; return f'<article class="card offer-card"><div class="brandrow"><div class="brandlogo">{ih}</div><div class="brandinfo"><a class="brandname" href="/brand/{brand_slug(b)}/">{esc(b)}</a><span class="tag">{esc("PROMO CODE" if code else "DEAL")} · {esc(x.get("category", "Deals"))}</span></div></div><div class="offer-benefit">{esc(benefit)}</div><h3>{esc(title)}</h3><p>{esc(text or "Official merchant offer.")}</p>{ch}<div class="meta">{cta}{seo_link}</div></div></article>'
def brand_intro(brand,category):
    category_copy={"Fashion":"fashion and apparel","Electronics":"consumer electronics and technology","Beauty & Personal Care":"beauty and personal care","Home & Living":"home, furniture and everyday living products"}.get(category,category.lower()); official=official_homepage(brand); link=f'<a href="{esc(official)}" target="_blank" rel="noopener">Visit the official {esc(brand)} website</a>' if official else ""; return f'<section class="brand-about" aria-labelledby="brand-about-title"><h2 id="brand-about-title">About {esc(brand)}</h2><p>{esc(brand)} is a well-known name in {category_copy}. {link} to explore the brand’s official products and information.</p></section>'
def write(p,c): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(c,encoding="utf-8")
def main():
    seo_records=load_seo_index()
    seo_by_key={}
    seo_by_category=defaultdict(list)
    seo_by_brand=defaultdict(list)
    for r in seo_records:
        key=(str(r.get("merchant")).casefold(),str(r.get("category")).casefold(),str(r.get("title")).strip().casefold())
        if key in seo_by_key: raise SystemExit(f"SEO NAVIGATION FAILED: duplicate SEO identity {key}")
        seo_by_key[key]=r; seo_by_category[r.get("category")].append(r); seo_by_brand[r.get("merchant")].append(r)
    deals=[canonicalize_item(x) for x in load_items() if is_active_offer(x) and x.get("final_purchase_url")]; bb=defaultdict(list); bc=defaultdict(list)
    for x in deals:
        h=resolve_brand(x.get("merchant"))
        if h: x["merchant"]=h["name"]; x["category"]=h["category"]; bb[h["name"].lower()].append(x); bc[h["category"]].append(x)
    brand_urls=[]; cat_urls=[]
    for cat,entries in CATALOG.items():
        cs=CATEGORY_SLUGS.get(cat,brand_slug(cat)); cu=f"{BASE}/{cs}/"; cat_urls.append(cu); active=bc.get(cat,[]); cards="".join(card(x,seo_by_key) for x in active[:60]) or '<p>No active coupons or deals are currently listed.</p>'; links="".join(f'<li><a href="/brand/{brand_slug(e["name"] )}/">{esc(e["name"])} brand page</a></li>' for e in entries); seo_links=seo_by_category.get(cat,[]); seo_nav="".join(f'<li><a href="{esc(r["canonical"])}">{esc(r["merchant"])} — {esc(r["title"])}</a></li>' for r in seo_links); body=f'<section class="hero"><p class="eyebrow">BRANDS · OFFERS</p><h1>{esc(cat)} Brands & Offers</h1><p class="lead">Browse catalog brands and every verified offer SEO page in this category.</p></section><section><h2>Latest {esc(cat)} offers</h2><div class="grid">{cards}</div></section><section><h2>Verified offer pages</h2><ul>{seo_nav}</ul></section><section><h2>Brands</h2><ul>{links}</ul></section>'; write(ROOT/cs/"index.html",page(f"{cat} Brands & Offers | DEAL 24H",f"Browse {cat.lower()} brands and verified offers on DEAL 24H.",cu,body,s={"@context":"https://schema.org","@type":"CollectionPage","name":f"{cat} Brands & Offers","url":cu}))
        for e in entries:
            b=e["name"]; u=f"{BASE}/brand/{brand_slug(b)}/"; p=ROOT/"brand"/brand_slug(b)/"index.html"; img=logo(b); ih=f'<img class="brandhero-img" src="{esc(img)}" alt="{esc(b)} logo" loading="eager">' if img else '<span class="brandfallback" aria-hidden="true">B</span>'; permanent=brand_intro(b,cat); brand_seo=seo_by_brand.get(b,[]); offer_links="".join(f'<li><a href="{esc(r["canonical"])}">{esc(r["title"])}</a></li>' for r in brand_seo); offer_section=f'<section><h2>Verified {esc(b)} offers</h2><ul>{offer_links}</ul></section>' if brand_seo else '<section><h2>Verified offers</h2><p>No active verified offers are currently listed.</p></section>'; body=f'<section class="hero"><div class="brandhero"><div class="brandhero-logo">{ih}</div><div><p class="eyebrow">{esc(cat.upper())} · BRAND</p><h1>About {esc(b)}</h1></div></div><p class="lead">A short introduction to {esc(b)} and its official website.</p></section>{permanent}{offer_section}<p><a class="cta" href="{esc(official_homepage(b))}" target="_blank" rel="noopener">Visit {esc(b)} official website ↗</a></p>'; schema={"@context":"https://schema.org","@graph":[{"@type":"Organization","name":b,"url":official_homepage(b)},{"@type":"WebPage","name":f"About {b}","url":u}]}; write(p,page(f"About {b} | DEAL 24H",f"A short introduction to {b} with a link to the official {b} website.",u,body,s=schema)); brand_urls.append(u)
    today=datetime.now(timezone.utc).date().isoformat()
    def sm(urls): return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'+"\n".join(f'<url><loc>{esc(u)}</loc><lastmod>{today}</lastmod></url>' for u in sorted(set(urls)))+'\n</urlset>\n'
    seo_urls=[str(r["canonical"]) for r in seo_records]
    write(ROOT/"sitemap-brands.xml",sm(brand_urls)); write(ROOT/"sitemap.xml",sm([BASE+"/"]+cat_urls+brand_urls+seo_urls)); write(ROOT/"robots.txt",f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\nSitemap: {BASE}/sitemap-brands.xml\nSitemap: {BASE}/sitemap-seo.xml\n"); print(f"SEO 999 catalog: persistent_brand_pages={len(brand_urls)}, category_pages={len(cat_urls)}, active_offer_brands={sum(bool(v) for v in bb.values())}, linked_seo_pages={len(seo_records)}")
if __name__ == "__main__": main()
