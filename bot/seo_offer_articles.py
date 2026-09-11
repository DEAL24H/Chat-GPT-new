import hashlib
import html
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from bot.catalog_utils import brand_slug
from bot.seo_market_scope import market_info
DATA=ROOT/'data/news.json'; BASE='https://deal24h.net'
PROMO_RE=re.compile(r"\b(?:sale|offer|offers|deal|deals|promotion|promotions|discount|coupon|promo|clearance|special offer|save|savings|voucher|limited time|bundle|buy\s+\d+\s+get\s+\d+|buy one get one|free (?:gift|shipping|delivery|item|set)|gift with purchase|no code required|code not required|member (?:price|savings|offer))\b",re.I)
BENEFIT_RE=re.compile(r"(?:\b\d{1,3}\s*%\s*(?:off|discount)\b|\b(?:save|off)\s+\$?\d+(?:[.,]\d+)?\b|\$\s?\d+(?:[.,]\d+)?\s*(?:off|discount)\b|\bbuy\s+\d+\s+get\s+\d+\b|\bbuy one get one\b|\bfree\s+(?:gift|shipping|delivery|item|set)\b|\bgift with purchase\b|\bspend\s+\$?\d+(?:[.,]\d+)?\s*(?:or more|\+)?\b|\b(?:no code required|code not required|without (?:a )?code)\b|\bmember (?:price|savings|offer)\b|\bbundle\b)",re.I)
VISIBLE_NOISE_RE=re.compile(r"(?:your cart is empty|estimated total|current price|regular price|original price|add to wishlist|add to cart|checkout|\bcart\b|sign in|log in|login|create account|privacy policy|terms(?: and conditions)?|cookie(?:s| policy)?|product advice|shipping address|billing address|search results|compare products|recently viewed|recommended for you|sort by|filter by|size guide|store locator|customer service|help center|amazon devices small business deals)",re.I)
def esc(v):return html.escape(str(v or ''),quote=True)
def slug(v):return re.sub(r'[^a-z0-9]+','-',str(v or '').lower()).strip('-')
def clean(v):return re.sub(r'\s+',' ',str(v or '')).strip()
def sanitize_visible(v):
 t=clean(v); p=None
 while t and t!=p:
  p=t; t=VISIBLE_NOISE_RE.sub(' ',t); t=re.sub(r'\s*[|•·]+\s*',' ',t); t=clean(t)
 return t
def load():
 d=json.loads(DATA.read_text(encoding='utf-8')); return d if isinstance(d,list) else d.get('items',[])
def valid_offer(item):
 from bot.catalog_utils import is_published_verified_offer
 if not is_published_verified_offer(item):return False
 title=sanitize_visible(item.get('title')); content=sanitize_visible(item.get('content')); purchase=clean(item.get('final_purchase_url'))
 if not title or not content or not purchase:return False
 # The crawler already restricts records to first-party sources and the live
 # destination validator checks the official host. Do not reject a valid
 # campaign, member benefit, bundle, or marketplace promotion just because its
 # wording is absent from a keyword dictionary.
 if re.fullmatch(r'(?:\$\s*)?\d+(?:[.,]\d+)?(?:\s*%|\s*off)?',title,re.I):return False
 return True
def meaningful_title(item,merchant):
 title=sanitize_visible(item.get('title')); title=re.sub(rf'^{re.escape(merchant)}\s*[—:-]\s*','',title,flags=re.I)
 if title and len(title)>=8 and not re.fullmatch(r'(?:\$\s*)?\d+(?:[.,]\d+)?(?:\s*%|\s*off)?',title,re.I):return title[:140].rsplit(' ',1)[0] if len(title)>140 else title
 return ''
def editorial_title(item,merchant,title):
 angles=('Official promotion details','Current offer information','What shoppers should know','Verified savings update')
 angle=angles[int(hashlib.sha1((merchant+title+clean(item.get('market'))).encode()).hexdigest(),16)%len(angles)]
 return f'{merchant} — {angle}: {title}'
def page(title,description,canonical,body):
 return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="index,follow"><link rel="canonical" href="{esc(canonical)}"><meta name="description" content="{esc(description)}"><title>{esc(title)}</title><link rel="stylesheet" href="/assets/style.css?v=20260903d"></head><body><header class="topbar"><div class="wrap nav"><a class="brand" href="/">DEAL 24H</a><a href="/">Home</a></div></header><main class="wrap">{body}</main><footer><div class="wrap">© {datetime.now(timezone.utc).year} DEAL 24H · Verified merchant promotion. <small>Some links may be affiliate links; any commission does not change your price.</small></div></footer></body></html>'''
def make_article(item):
 merchant=sanitize_visible(item.get('merchant')) or 'Merchant'
 if not valid_offer(item):return None
 title=meaningful_title(item,merchant)
 if not title:return None
 code=clean(item.get('code')); purchase=clean(item.get('final_purchase_url')); discount=sanitize_visible(item.get('discount')); content=sanitize_visible(item.get('content'))
 market=market_info(item); identity='|'.join((merchant,title,code,purchase,discount,content,market['scope'],','.join(market['countries'])))
 digest=hashlib.sha1(identity.encode()).hexdigest()[:10]
 canonical=f"{BASE}/seo/{slug(merchant)}-{slug(title)[:70]}-{digest}/"; label='Promo code' if code else 'Direct deal'
 code_html=f'<div class="code"><span><small>CODE</small><strong>{esc(code)}</strong></span><button class="copy-code" type="button" data-code="{esc(code)}">Copy code</button></div>' if code else ''
 affiliate=bool(item.get('is_affiliate') and item.get('affiliate_tracking_url'))
 destination=clean(item.get('affiliate_tracking_url')) if affiliate else purchase
 rel='sponsored nofollow noopener noreferrer' if affiliate else 'nofollow noopener noreferrer'
 cta=f'<a class="cta" href="{esc(destination)}" target="_blank" rel="{rel}">{"GET CODE" if code else "GET DEAL"} ↗</a>'
 source=clean(item.get('source_url')); source_link=f'<p><a href="{esc(source)}" target="_blank" rel="noopener">View the official source</a></p>' if source else ''
 market_html=f'<div class="market-scope"><strong>Availability:</strong> {esc(market["label"])}</div>'
 category=clean(item.get('category')); category_slug={'Fashion':'fashion','Electronics':'electronics','Beauty & Personal Care':'beauty-personal-care','Home & Living':'home-and-living'}.get(category)
 checked=clean(item.get('purchase_url_verified_at') or item.get('last_checked') or item.get('detected_at'))
 checked_html=f'<p class="verification-meta"><strong>Last verified:</strong> {esc(checked)}</p>' if checked else '<p class="verification-meta"><strong>Verification:</strong> Official source checked by the publishing pipeline.</p>'
 public_title=editorial_title(item,merchant,title)
 editorial=f'Deal24h checked the official {merchant} source and presents this {label.lower()} as a reference for shoppers. Availability and conditions can vary by market, product, account, or campaign period.'
 body=f'<section class="hero"><p class="eyebrow">{esc(label.upper())}</p><h1>{esc(public_title)}</h1><p class="lead">{esc((discount+" — ") if discount else "")}{esc(label)} for {esc(merchant)}.</p></section><article><h2>Offer details from the official source</h2>{market_html}<p>{esc(editorial)}</p><blockquote>{esc(content)}</blockquote>{code_html}{checked_html}<p>{cta}</p><p class="source-note">The quoted details come from the official {esc(merchant)} source; check the merchant page for the latest conditions.</p>{source_link}<p><a href="/brand/{brand_slug(merchant)}/">More verified {esc(merchant)} offers</a></p>{f'<p><a href="/{category_slug}/">More {esc(category)} offers</a></p>' if category_slug else ''}</article>'
 return canonical,page(public_title+' | DEAL 24H',f'{merchant} {label.lower()}: {title}. Official source checked by Deal24h with market and condition context.',canonical,body),label,{'id':str(item.get('id') or ''),'canonical':canonical,'merchant':merchant,'category':category,'title':public_title,'label':label,'market_scope':market['scope'],'countries':market['countries'],'market_label':market['label']}
def main():
 out=ROOT/'seo'
 if out.exists():shutil.rmtree(out)
 out.mkdir(parents=True,exist_ok=True)
 urls=[]; records=[]; counts={'code':0,'direct':0}; rejected=0; duplicate=0; seen=set()
 for item in load():
  if not valid_offer(item):rejected+=1;continue
  merchant=sanitize_visible(item.get('merchant')) or 'Merchant'; title=meaningful_title(item,merchant)
  if not title:rejected+=1;continue
  market=market_info(item); identity='|'.join((merchant,title,clean(item.get('code')),clean(item.get('final_purchase_url')),sanitize_visible(item.get('discount')),sanitize_visible(item.get('content')),market['scope'],','.join(market['countries'])))
  if identity in seen:duplicate+=1;continue
  seen.add(identity)
  result=make_article(item)
  if not result:rejected+=1;continue
  canonical,html_text,label,record=result; path=ROOT/canonical.removeprefix(BASE+'/').rstrip('/')/'index.html'; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(html_text,encoding='utf-8'); urls.append(canonical); records.append(record); counts['code' if label=='Promo code' else 'direct']+=1
 if len(urls)!=len(set(urls)):raise SystemExit('SEO OFFER ARTICLES FAILED: duplicate canonical URLs')
 class VisibleText(HTMLParser):
  def __init__(self):super().__init__();self.parts=[];self.skip_depth=0
  def handle_starttag(self,tag,attrs):
   if tag.lower() in {'script','style','template','noscript'}:self.skip_depth+=1
  def handle_endtag(self,tag):
   if tag.lower() in {'script','style','template','noscript'} and self.skip_depth:self.skip_depth-=1
  def handle_data(self,data):
   if not self.skip_depth:self.parts.append(data)
  def text(self):return ' '.join(self.parts)
 bad=[]
 for p in out.glob('*/index.html'):
  parser=VisibleText();parser.feed(p.read_text(encoding='utf-8'))
  if VISIBLE_NOISE_RE.search(parser.text()):bad.append(str(p))
 if bad:raise SystemExit('SEO OFFER ARTICLES FAILED: visible UI noise remained: '+', '.join(bad[:20]))
 today=datetime.now(timezone.utc).date().isoformat(); sitemap='<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'+''.join(f'<url><loc>{esc(u)}</loc><lastmod>{today}</lastmod></url>\n' for u in sorted(urls))+'</urlset>\n'
 (ROOT/'sitemap-seo.xml').write_text(sitemap,encoding='utf-8')
 ids=sorted(str(x.get('id') or '') for x in records)
 release_id=hashlib.sha256('|'.join(ids).encode()).hexdigest()[:16]
 generated_at=datetime.now(timezone.utc).isoformat()
 (out/'seo-index.json').write_text(json.dumps({'schema':3,'release_id':release_id,'generated_at':generated_at,'counts':counts,'urls':len(urls),'ids':ids,'rejected_non_qualified':rejected,'deduplicated_equivalent_offers':duplicate,'visible_text_noise':0,'offers':sorted(records,key=lambda x:x['canonical'])},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 (out/'seo-modes.json').write_text(json.dumps({'schema':3,'release_id':release_id,'generated_at':generated_at,'counts':counts,'urls':len(urls),'ids':ids,'rejected_non_qualified':rejected,'deduplicated_equivalent_offers':duplicate,'visible_text_noise':0},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(f"SEO OFFER ARTICLES: code={counts['code']} direct={counts['direct']} total={len(urls)} rejected={rejected} deduplicated_equivalent={duplicate} visible_text_noise=0")
if __name__=='__main__':main()
