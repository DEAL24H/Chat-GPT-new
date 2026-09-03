import html,json,re
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import quote
from catalog_utils import CATALOG,brand_slug,canonicalize_item,is_active_offer,resolve_brand
ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'data/news.json';BASE='https://deal24h.net';GA4='G-R7E164DCZL'
CATEGORY_SLUGS={'Fashion':'fashion','Beauty':'beauty','Gaming':'gaming','Consumer':'consumer','Home & Living':'home-living','Sports & Outdoor':'sports-outdoor','Food & Grocery':'food-grocery','Travel & Hotels':'travel-hotels','Software & Digital Services':'software-digital-services','Baby, Kids & Family':'baby-kids-family','Automotive & Accessories':'automotive-accessories','Books, Education & Media':'books-education-media'}
def esc(v):return html.escape(str(v or ''),quote=True)
def load_items():
 try:
  d=json.loads(DATA.read_text(encoding='utf-8'));return d if isinstance(d,list) else d.get('items',[])
 except Exception:return []
def domain(b):
 h=resolve_brand(b);return h.get('domain','') if h else ''
def logo(b):
 d=domain(b);return f'https://www.google.com/s2/favicons?domain={quote(d)}&sz=128' if d else ''
def page(t,d,c,b,r='index,follow',s=None):
 ld=f'<script type="application/ld+json">{json.dumps(s,ensure_ascii=False,separators=(",",":"))}</script>' if s else ''
 ga=f'''<script async src="https://www.googletagmanager.com/gtag/js?id={GA4}"></script><script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','{GA4}',{{anonymize_ip:true}});</script>'''
 return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="{esc(d)}"><meta name="robots" content="{r}"><link rel="canonical" href="{esc(c)}"><meta property="og:title" content="{esc(t)}"><meta property="og:description" content="{esc(d)}"><meta property="og:url" content="{esc(c)}"><title>{esc(t)}</title>{ld}<link rel="stylesheet" href="/assets/style.css?v=20260903d">{ga}</head><body><header class="topbar"><div class="wrap nav"><a class="brand" href="/">DEAL <span>24H</span></a><a href="/">Home</a></div></header><main class="wrap">{b}</main><footer><div class="wrap">© {datetime.now(timezone.utc).year} DEAL 24H · Official merchant source attribution.</div></footer></body></html>'''
def card(x):
 b=x.get('merchant','Deal');code=x.get('code','');u=x.get('promotion_url') or x.get('url') or x.get('source_url') or '';text=re.sub(r'\s+',' ',str(x.get('content',''))).strip();p=re.search(r'\b(\d{1,3})\s*%\s*off\b',text,re.I);benefit=f'{p.group(1)}% OFF' if p else str(x.get('discount') or 'OFFICIAL DEAL').upper();title=re.sub(rf'^{re.escape(b)}\s*[—-]\s*','',str(x.get('title') or '').strip(),flags=re.I) or f'{b} official deal';text=text[:187].rsplit(' ',1)[0]+'…' if len(text)>190 else text;img=logo(b);ih=f'<img class="brandlogo-img" src="{esc(img)}" alt="{esc(b)} logo" loading="lazy">' if img else '';cta=f'<a class="cta" href="{esc(u)}" target="_blank" rel="nofollow noopener sponsored">{"GET CODE" if code else "GET DEAL"} ↗</a>' if u else '';ch=f'<div class="code"><small>CODE</small><strong>{esc(code)}</strong></div>' if code else ''
 return f'<article class="card offer-card"><div class="brandrow"><div class="brandlogo">{ih}</div><div class="brandinfo"><a class="brandname" href="/brand/{brand_slug(b)}/">{esc(b)}</a><span class="tag">{esc("PROMO CODE" if code else "DEAL")} · {esc(x.get("category","Deals"))}</span></div></div><div class="offer-benefit">{esc(benefit)}</div><h3>{esc(title)}</h3><p>{esc(text or "Official merchant offer.")}</p>{ch}<div class="meta">{cta}</div></article>'
def write(p,c):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(c,encoding='utf-8')
def main():
 deals=[canonicalize_item(x) for x in load_items() if is_active_offer(x)];bb=defaultdict(list);bc=defaultdict(list)
 for x in deals:
  h=resolve_brand(x.get('merchant'))
  if h:x['merchant']=h['name'];x['category']=h['category'];bb[h['name'].lower()].append(x);bc[h['category']].append(x)
 brand_urls=[];cat_urls=[]
 for cat,entries in CATALOG.items():
  cs=CATEGORY_SLUGS.get(cat,brand_slug(cat));cu=f'{BASE}/{cs}/';cat_urls.append(cu);active=bc.get(cat,[]);cards=''.join(card(x) for x in active[:60]) or '<p>No active coupons or deals are currently listed.</p>';links=''.join(f'<li><a href="/brand/{brand_slug(e["name"])}/">{esc(e["name"])} coupons & deals</a></li>' for e in entries if bb.get(e['name'].lower()));body=f'<section class="hero"><p class="eyebrow">COUPON CODES · PROMO CODES · DEALS</p><h1>{esc(cat)} Coupons, Promo Codes & Deals</h1><p class="lead">Active coupon codes, promo codes and official deals from merchant sources.</p></section><section><h2>Latest {esc(cat)} offers</h2><div class="grid">{cards}</div></section><section><h2>Brands</h2><ul>{links or "<li>No active brand offers currently listed.</li>"}</ul></section>';write(ROOT/cs/'index.html',page(f'{cat} Coupons, Promo Codes & Deals | DEAL 24H',f'Find active {cat.lower()} coupon codes, promo codes and deals from official merchant sources.',cu,body,s={'@context':'https://schema.org','@type':'CollectionPage','name':f'{cat} Coupons, Promo Codes & Deals','url':cu}))
  for e in entries:
   b=e['name'];u=f'{BASE}/brand/{brand_slug(b)}/';items=bb.get(b.lower(),[]);p=ROOT/'brand'/brand_slug(b)/'index.html'
   if not items:write(p,page(f'{b} Coupons, Promo Codes & Deals | DEAL 24H',f'No active {b} coupon codes or deals are currently listed on DEAL 24H.',u,f'<section class="hero"><p class="eyebrow">BRAND DIRECTORY</p><h1>{esc(b)} Coupons, Promo Codes & Deals</h1><p>No active offers are currently listed. Check back for new promotions.</p></section>',r='noindex,follow'));continue
   brand_urls.append(u);img=logo(b);ih=f'<img class="brandhero-img" src="{esc(img)}" alt="{esc(b)} logo" loading="eager">' if img else '';body=f'<section class="hero"><div class="brandhero"><div class="brandhero-logo">{ih}</div><div><p class="eyebrow">{esc(cat.upper())} · COUPONS & DEALS</p><h1>{esc(b)} Coupons, Promo Codes & Deals</h1></div></div><p class="lead">Active {esc(b)} coupon codes, promo codes and official deals from merchant sources.</p></section><section><h2>All active {esc(b)} offers</h2><div class="grid">{"".join(card(x) for x in items)}</div></section><p><a href="/{cs}/">← More {esc(cat)} offers</a></p>';els=[{'@type':'ListItem','position':i+1,'name':f'{b} '+('coupon code '+str(x.get('code')) if x.get('code') else 'deal'),'url':x.get('promotion_url') or x.get('url') or u} for i,x in enumerate(items)];schema={'@context':'https://schema.org','@graph':[{'@type':'Organization','name':b,'url':f'https://{domain(b)}'},{'@type':'WebPage','name':f'{b} Coupons, Promo Codes & Deals','url':u},{'@type':'ItemList','name':f'Active {b} offers','numberOfItems':len(items),'itemListElement':els}]};write(p,page(f'{b} Coupons, Promo Codes & Deals | DEAL 24H',f'Find active {b} coupon codes, promo codes and official deals from merchant sources on DEAL 24H.',u,body,s=schema))
 today=datetime.now(timezone.utc).date().isoformat()
 def sm(urls):return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'+'\n'.join(f'<url><loc>{esc(u)}</loc><lastmod>{today}</lastmod></url>' for u in sorted(set(urls)))+'\n</urlset>\n'
 write(ROOT/'sitemap-brands.xml',sm(brand_urls));write(ROOT/'sitemap.xml',sm([BASE+'/']+cat_urls+brand_urls));write(ROOT/'robots.txt',f'User-agent: *\nAllow: /\nSitemap: {BASE}/sitemap.xml\nSitemap: {BASE}/sitemap-brands.xml\n');print(f'SEO 999 catalog: brands={sum(len(v) for v in CATALOG.values())}, active_brand_pages={len(brand_urls)}, category_pages={len(cat_urls)}')
if __name__=='__main__':main()
