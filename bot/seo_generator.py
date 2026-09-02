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
def norm(v): return re.sub(r"[^a-z0-9]+"," ",str(v or "").lower().replace("’","'")).strip()
def brand_name(d):
    m=str(d.get("merchant","")).strip(); hit=next((b for names in KNOWN.values() for b in names if norm(b)==norm(m)),None); return hit or m.split("—")[0].strip()[:70]
def brand_category(b):
    nb=norm(b)
    for key,names in KNOWN.items():
        if any(norm(x)==nb for x in names): return key
    return ""
def catkey(d): return brand_category(brand_name(d)) or ALIASES.get(d.get("category"))
def active(d):
    if str(d.get("status","active")).lower() in {"expired","inactive"}:return False
    if not(d.get("code") or d.get("promotion_url")):return False
    e=str(d.get("expires_at","")).strip()
    if not e:return True
    try:
        dt=datetime.fromisoformat(e.replace("Z","+00:00")); dt=dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc); return dt>datetime.now(timezone.utc)
    except ValueError:return False
def parse_expiry(text):
    t=re.sub(r"\s+"," ",str(text or "")).strip()
    for p in [r"(?:valid|offer|promotion)[^.!?]{0,140}?(?:through|until|ends?\s+(?:on)?)[^\d]*(\w+\s+\d{1,2},?\s+\d{4})",r"(?:valid|offer|promotion)[^.!?]{0,80}?(\w+\s+\d{1,2},?\s+\d{4})"]:
        m=re.search(p,t,re.I)
        if not m: continue
        for fmt,raw in [("%b %d, %Y",m.group(1)),("%B %d %Y",m.group(1).replace(",",""))]:
            try:return datetime.strptime(raw,fmt).replace(tzinfo=timezone.utc).isoformat()
            except ValueError:pass
    return ""
def offer(d):
    b=brand_name(d); text=re.sub(r"\s+"," ",str(d.get("content","")).strip()); pct=re.search(r"\b(\d{1,3})\s*%\s*off\b",text,re.I); save=re.search(r"\bsave\s+\$\s*([\d,.]+)",text,re.I); free=re.search(r"\bfree\s+shipping\b",text,re.I); student=re.search(r"\b(?:student|educator)\b",text,re.I); member=re.search(r"\b(?:member|family|club)\b",text,re.I)
    if pct: benefit=f"{pct.group(1)}% OFF"
    elif save: benefit=f"SAVE ${save.group(1)}"
    elif free: benefit="FREE SHIPPING"
    elif student: benefit="STUDENT OFFER"
    elif member: benefit="MEMBER OFFER"
    elif d.get("discount") and re.search(r"%|off|save|shipping",str(d.get("discount")),re.I): benefit=str(d["discount"]).strip().upper()
    else: benefit="OFFICIAL DEAL"
    title=str(d.get("title") or "").strip(); generic=not title or re.search(r"[—-]\s*\$?\s*[\d,.]+(?:\s*[—-]\s*\$?\s*[\d,.]+)?$",title,re.I)
    if generic:
        if save:title=f"Save ${save.group(1)} on selected items"
        elif pct:title=f"{pct.group(1)}% off selected items"
        elif free:title="Free shipping offer"
        elif student:title="Student & educator offer"
        elif member:title=f"{b} member offer"
        else:title=f"{b} official deal"
    else:title=re.sub(rf"^{re.escape(b)}\s*[—-]\s*","",title,flags=re.I).strip()
    desc=re.sub(r"Review:\s*.*$","",text,flags=re.I); desc=re.sub(r"More options.*$","",desc,flags=re.I).strip()
    if len(desc)>190:desc=desc[:187].rsplit(" ",1)[0]+"…"
    expiry=d.get("expires_at") or parse_expiry(text); c=catkey(d); return {"brand":b,"category":c,"type":"PROMO CODE" if d.get("code") else "DEAL","benefit":benefit,"title":title,"description":desc,"expiry":expiry,"code":str(d.get("code") or ""),"url":d.get("promotion_url") or d.get("source_url") or d.get("url") or "#"}
def domain(b):return DOMAINS.get(norm(b),"
def logo(b):
    d=domain(b); return f"https://www.google.com/s2/favicons?domain={quote(d)}&sz=128" if d else ""
def jsonld(x):return '<script type="application/ld+json">'+json.dumps(x,ensure_ascii=False,separators=(",",":"))+'</script>'
def page(title,desc,canonical,body,schema=None,robots="index,follow"):
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="{esc(desc)}"><meta name="robots" content="{esc(robots)}"><link rel="canonical" href="{esc(canonical)}"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}"><meta property="og:url" content="{esc(canonical)}"><title>{esc(title)}</title>{jsonld(schema) if schema else ""}<link rel="stylesheet" href="/assets/style.css?v=20260902i"></head><body><header class="topbar"><div class="wrap nav"><a class="brand" href="/">DEAL <span>24H</span></a><a href="/">Home</a></div></header><main class="wrap">{body}</main><footer><div class="wrap">© {datetime.now(timezone.utc).year} DEAL 24H · Official merchant source attribution.</div></footer></body></html>'''
def card(d):
    o=offer(d); b=o["brand"]; code=esc(o["code"]); url=esc(o["url"]); conditions=[]; logo_url=logo(b); logo_html=f'<img class="brandlogo-img" src="{esc(logo_url)}" alt="{esc(b)} logo" loading="lazy">' if logo_url else ''
    if o["expiry"]:
        try: conditions.append("Ends "+datetime.fromisoformat(str(o["expiry"]).replace("Z","+00:00")).strftime("%b %-d, %Y"))
        except Exception: conditions.append("Ends "+str(o["expiry"]))
    if d.get("official_source"):conditions.append("✓ Official source")
    codebox=f'<div class="code"><span><small>CODE</small><strong>{code}</strong></span></div>' if code else ''
    cond=f'<div class="offer-conditions">{"".join("<span>"+esc(x)+"</span>" for x in conditions)}</div>' if conditions else ''
    cta=f'<a class="cta" href="{url}" target="_blank" rel="nofollow noopener sponsored">{"GET CODE" if code else "GET DEAL"} ↗</a>' if url!="#" else ''
    return f'<article class="card offer-card"><div class="brandrow"><div class="brandlogo">{logo_html}</div><div class="brandinfo"><a class="brandname" href="/brand/{slug(b)}/">{esc(b)}</a><span class="tag">{esc(o["type"])} · {esc(CATEGORIES.get(o["category"],"Deals"))}</span></div></div><div class="offer-benefit">{esc(o["benefit"])}</div><h3>{esc(o["title"])}</h3><p>{esc(o["description"] or "Official merchant offer.")}</p>{codebox}{cond}<div class="meta">{cta}</div></article>'
def write(p,c):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(c,encoding="utf-8")
def main():
    deals=[d for d in load() if active(d)]; grouped=defaultdict(list)
    for d in deals:
        c=catkey(d)
        if c: grouped[c].append(d); grouped[(c,brand_name(d).lower())].append(d)
    urls={BASE+"/",*(BASE+f"/{c}/" for c in CATEGORIES)}; active_brands=[]
    for c,label in CATEGORIES.items():
        items=grouped.get(c,[]); cards="".join(card(d) for d in items[:60]) or '<p>No active coupons or deals are currently listed. Check back soon for new offers.</p>'; links=[f'<li><a href="/brand/{slug(b)}/">{esc(b)} coupons & deals</a></li>' for b in KNOWN.get(c,[]) if grouped.get((c,b.lower()),[])]
        body=f'<section class="hero"><div><p class="eyebrow">COUPON CODES · PROMO CODES · DEALS</p><h1>{label} Coupons, Promo Codes & Deals</h1><p class="lead">Active coupon codes, promo codes and official deals for {label.lower()} brands. Offers are collected from official merchant sources.</p></div></section><section><h2>Latest {label} offers</h2><div class="grid">{cards}</div></section><section><h2>Brands with active offers</h2><ul>{"".join(links) or "<li>No active brand offers currently listed.</li>"}</ul></section>'
        write(ROOT/c/"index.html",page(f"{label} Coupons, Promo Codes & Deals | DEAL 24H",f"Find active {label.lower()} coupon codes, promo codes and deals from official merchant sources.",f"{BASE}/{c}/",body))
    for c,label in CATEGORIES.items():
        for b in KNOWN.get(c,[]):
            items=grouped.get((c,b.lower()),[]); u=f"{BASE}/brand/{slug(b)}/"
            if not items:
                write(ROOT/"brand"/slug(b)/"index.html",page(f"{b} Coupons, Promo Codes & Deals | DEAL 24H",f"No active {b} coupon codes or deals are currently listed on DEAL 24H.",u,"<p>No active offers are currently listed.</p>",robots="noindex,follow")); continue
            active_brands.append((b,c,items,u)); cards="".join(card(d) for d in items); lg=logo(b); lh=f'<img class="brandhero-img" src="{esc(lg)}" alt="{esc(b)} logo" loading="eager">' if lg else ""
            body=f'<section class="hero"><div class="brandhero"><div class="brandhero-logo">{lh}</div><div><p class="eyebrow">{esc(label.upper())} · COUPONS & DEALS</p><h1>{esc(b)} Coupons, Promo Codes & Deals</h1></div></div><p class="lead">Find active {esc(b)} coupon codes and official deals. Each offer is attributed to an official merchant source.</p></section><section><h2>Active {esc(b)} offers</h2><div class="grid">{cards}</div></section><p><a href="/{c}/">← More {esc(label)} offers</a></p>'
            elems=[{"@type":"ListItem","position":i,"name":f"{b} {'coupon code '+str(d.get('code')) if d.get('code') else 'deal'}","url":d.get("promotion_url") or d.get("source_url") or d.get("url") or u} for i,d in enumerate(items,1)]
            schema={"@context":"https://schema.org","@graph":[{"@type":"Organization","name":b,"url":f"https://{domain(b)}"},{"@type":"WebPage","name":f"{b} Coupons, Promo Codes & Deals","url":u,"description":f"Active {b} coupon codes and deals from official merchant sources."},{"@type":"ItemList","name":f"Active {b} offers","numberOfItems":len(items),"itemListElement":elems}]}
            write(ROOT/"brand"/slug(b)/"index.html",page(f"{b} Coupons, Promo Codes & Deals | DEAL 24H",f"Find active {b} coupon codes, promo codes and deals from official merchant sources on DEAL 24H.",u,body,schema)); urls.add(u)
    today=datetime.now(timezone.utc).date().isoformat(); sb=['<?xml version="1.0" encoding="UTF-8"?>','<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']+[f'<url><loc>{esc(u)}</loc><lastmod>{today}</lastmod></url>' for _,_,_,u in sorted(active_brands,key=lambda x:x[0].lower())]+['</urlset>']; write(ROOT/"sitemap-brands.xml","\n".join(sb)+"\n")
    sa=['<?xml version="1.0" encoding="UTF-8"?>','<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']+[f'<url><loc>{esc(u)}</loc><lastmod>{today}</lastmod></url>' for u in sorted(urls)]+['</urlset>']; write(ROOT/"sitemap.xml","\n".join(sa)+"\n"); write(ROOT/"robots.txt",f"User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\nSitemap: {BASE}/sitemap-brands.xml\n"); print(f"SEO offer-first generated: {len(active_brands)} active brand URLs; {len(urls)} total indexable URLs")
if __name__=="__main__":main()
