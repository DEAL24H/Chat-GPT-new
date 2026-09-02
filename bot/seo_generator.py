import html,json,re
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import quote
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/"data"/"news.json"; CATALOG=ROOT/"data"/"brand_catalog.json"; BASE="https://deal24h.net"
CATEGORIES={"fashion":"Fashion","beauty":"Beauty","gaming":"Gaming","consumer":"Consumer"}; ALIASES={"Thời trang":"fashion","Fashion":"fashion","Mỹ phẩm":"beauty","Beauty":"beauty","Game":"gaming","Gaming":"gaming","Hàng tiêu dùng":"consumer","Consumer":"consumer"}
def load_catalog():
    try:return json.loads(CATALOG.read_text(encoding="utf-8")).get("categories",{})
    except Exception:return {}
BRANDS=load_catalog(); KNOWN={k.lower():[x["name"] for x in v] for k,v in BRANDS.items()}; DOMAINS={x["name"].lower():x["domain"] for v in BRANDS.values() for x in v}
def slug(v): return re.sub(r"[^a-z0-9]+","-",v.lower().replace("&"," and ").replace("'","")).strip("-")
def esc(v): return html.escape(str(v or ""),quote=True)
def load():
    try:
        d=json.loads(DATA.read_text(encoding="utf-8")); return d if isinstance(d,list) else d.get("items",[])
    except Exception:return []
def catkey(d): return ALIASES.get(d.get("category"))
def brand_name(d):
    m=str(d.get("merchant","")).strip(); low=m.lower()
    for names in KNOWN.values():
        for b in names:
            if b.lower()==low:return b
    return m.split("—")[0].strip()[:70]
def active(d):
    if str(d.get("status","active")).lower() in {"expired","inactive"}:return False
    if not(d.get("code") or d.get("promotion_url")):return False
    e=str(d.get("expires_at","")).strip()
    if not e:return True
    try:
        dt=datetime.fromisoformat(e.replace("Z","+00:00")); dt=dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc); return dt>datetime.now(timezone.utc)
    except ValueError:return False
def domain(b):return DOMAINS.get(b.lower(),"")
def logo(b):
    d=domain(b); return f"https://www.google.com/s2/favicons?domain={quote(d)}&sz=128" if d else ""
def jsonld(x):return '<script type="application/ld+json">'+json.dumps(x,ensure_ascii=False,separators=(",",":"))+'</script>'
def page(title,desc,canonical,body,schema=None,robots="index,follow"):
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="{esc(desc)}"><meta name="robots" content="{esc(robots)}"><link rel="canonical" href="{esc(canonical)}"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}"><meta property="og:url" content="{esc(canonical)}"><title>{esc(title)}</title>{jsonld(schema) if schema else ""}<link rel="stylesheet" href="/assets/style.css"></head><body><header class="topbar"><div class="wrap nav"><a class="brand" href="/">DEAL <span>24H</span></a><a href="/">Home</a></div></header><main class="wrap">{body}</main><footer><div class="wrap">© {datetime.now(timezone.utc).year} DEAL 24H · Public coupon and deal data with source attribution.</div></footer></body></html>'''
def card(d):
    b=brand_name(d); code=esc(d.get("code")); disc=esc(d.get("discount") or "Promotion offer"); src=esc(d.get("source_label") or "Official merchant source"); url=esc(d.get("promotion_url") or d.get("source_url") or d.get("url") or "#"); exp=esc(d.get("expires_at") or ""); ch=f'<div class="code"><strong>{code}</strong></div>' if code else '<div class="code"><strong>Promotion offer</strong></div>'; label="Get deal" if code else "View promotion"
    return f'<article class="card"><div class="brandrow"><div class="brandinfo"><strong>{esc(b)}</strong><span class="tag">{esc(CATEGORIES.get(catkey(d),"Deals"))} offer</span></div></div><h3>{esc(d.get("title") or (f"{b} Coupon Code" if code else f"{b} Promotion"))}</h3><p>{disc}</p>{ch}<a href="{url}" rel="nofollow noopener">{label} at {esc(b)} ↗</a><small>Source: {src} · Last checked: {esc(d.get("last_checked",""))}</small>{f'<small>Expires: {exp}</small>' if exp else ''}</article>'
def write(p,c):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(c,encoding="utf-8")
def main():
    deals=[d for d in load() if active(d)]; grouped=defaultdict(list)
    for d in deals:
        c=catkey(d)
        if c: grouped[c].append(d); grouped[(c,brand_name(d).lower())].append(d)
    urls={BASE+"/",*(BASE+f"/{c}/" for c in CATEGORIES)}; active_brands=[]
    for c,label in CATEGORIES.items():
        items=grouped.get(c,[]); cards="".join(card(d) for d in items[:60]) or '<p>No active coupon codes or promotion offers are currently listed. Check back soon for new offers.</p>'
        links=[f'<li><a href="/brand/{slug(b)}/">{esc(b)} coupons & promotions</a></li>' for b in KNOWN.get(c,[]) if grouped.get((c,b.lower()),[])]
        body=f'<section class="hero"><div><p class="eyebrow">INTERNATIONAL DEALS</p><h1>{label} Coupons & Promotions</h1><p class="lead">Fresh public coupon codes and promotion links for {label.lower()} stores. Offers are collected only from official merchant sources.</p></div></section><section><h2>Latest {label} offers</h2><div class="grid">{cards}</div></section><section><h2>Brands with active offers</h2><ul>{"".join(links) or "<li>No active brand offers currently listed.</li>"}</ul></section>'
        write(ROOT/c/"index.html",page(f"{label} Coupons & Promotions | DEAL 24H",f"Find international {label.lower()} coupon codes, promotions and deals updated by DEAL 24H.",f"{BASE}/{c}/",body))
    for c,label in CATEGORIES.items():
        for b in KNOWN.get(c,[]):
            items=grouped.get((c,b.lower()),[]); u=f"{BASE}/brand/{slug(b)}/"
            if not items:
                write(ROOT/"brand"/slug(b)/"index.html",page(f"{b} Coupons | DEAL 24H",f"No active {b} coupon codes or promotion offers are currently available on DEAL 24H.",u,"<p>No active offers are currently listed.</p>",robots="noindex,follow")); continue
            active_brands.append((b,c,items,u)); cards="".join(card(d) for d in items); lg=logo(b); lh=f'<img class="brandhero-img" src="{esc(lg)}" alt="{esc(b)} logo" loading="eager">' if lg else ""
            body=f'<section class="hero"><div class="brandhero"><div class="brandhero-logo">{lh}</div><div><p class="eyebrow">{esc(label.upper())} · COUPONS & PROMOTIONS</p><h1>{esc(b)} Coupons, Promo Codes & Deals</h1></div></div><p class="lead">Find active {esc(b)} coupon codes and official promotion links from merchant sources.</p></section><section><h2>Active {esc(b)} offers</h2><div class="grid">{cards}</div></section><p><a href="/{c}/">← More {esc(label)} offers</a></p>'
            elems=[{"@type":"ListItem","position":i,"name":f"{b} {'coupon code '+str(d.get('code')) if d.get('code') else 'promotion offer'}","url":d.get("promotion_url") or d.get("source_url") or d.get("url") or u} for i,d in enumerate(items,1)]
            schema={"@context":"https://schema.org","@graph":[{"@type":"Organization","name":b,"url":f"https://{domain(b)}"},{"@type":"WebPage","name":f"{b} Coupons, Promo Codes & Deals","url":u,"description":f"Active {b} coupon codes and promotion offers from official merchant sources."},{"@type":"ItemList","name":f"Active {b} offers","numberOfItems":len(items),"itemListElement":elems}]}
            write(ROOT/"brand"/slug(b)/"index.html",page(f"{b} Coupons, Promo Codes & Deals | DEAL 24H",f"Find active {b} coupon codes, promo codes and promotion offers from official merchant sources on DEAL 24H.",u,body,schema)); urls.add(u)
    today=datetime.now(timezone.utc).date().isoformat(); sb=['<?xml version="1.0" encoding="UTF-8"?>','<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']+[f'<url><loc>{esc(u)}</loc><lastmod>{today}</lastmod></url>' for _,_,_,u in sorted(active_brands,key=lambda x:x[0].lower())]+['</urlset>']; write(ROOT/"sitemap-brands.xml","\n".join(sb)+"\n")
    sa=['<?xml version="1.0" encoding="UTF-8"?>','<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']+[f'<url><loc>{esc(u)}</loc><lastmod>{today}</lastmod></url>' for u in sorted(urls)]+['</urlset>']; write(ROOT/"sitemap.xml","\n".join(sa)+"\n"); write(ROOT/"robots.txt",f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\nSitemap: {BASE}/sitemap-brands.xml\n"); print(f"SEO v2 generated: {len(active_brands)} active brand URLs; {len(urls)} total indexable URLs")
if __name__=="__main__":main()
