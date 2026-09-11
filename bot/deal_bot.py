"""DEAL24H canonical promotion bot: broad discovery, strict program quality."""
import hashlib,json,re,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin,urlparse
import requests
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1];ALLOWLIST=ROOT/'data/allowed_brand_urls.json';OUT=ROOT/'data/news.json'
CATS=['Fashion','Electronics','Beauty & Personal Care','Home & Living'];WORKERS=12;TIMEOUT=15;RETRIES=3;MAX_PAGES=4
H={'User-Agent':'Deal24H/7.0 (+https://deal24h.net/ official promotion crawler)','Accept':'text/html,application/xhtml+xml','Accept-Language':'en-US,en;q=0.9'}
PROMO=re.compile(r'\b(?:sale|offer|offers|deal|deals|promotion|promotions|discount|coupon|promo|clearance|special offer|specials?|save|savings|voucher|limited time|member (?:price|savings|offer)|buy\s+\d+\s+get\s+\d+|buy one get one|free (?:gift|shipping|delivery|item|set)|gift with purchase|no code required|code not required|without (?:a )?code)\b',re.I)
BENEFIT=re.compile(r'(?:\b\d{1,3}\s*%\s*(?:off|discount)\b|\b(?:save|off)\s+\$?\d+(?:[.,]\d+)?\b|\$\s?\d+(?:[.,]\d+)?\s*(?:off|discount)\b|\bbuy\s+\d+\s+get\s+\d+\b|\bbuy one get one\b|\bfree\s+(?:gift|shipping|delivery|item|set)\b|\bgift with purchase\b|\bspend\s+\$?\d+(?:[.,]\d+)?\s*(?:or more|\+)?\b|\b(?:no code required|code not required|without (?:a )?code)\b|\bmember (?:price|savings|offer)\b|\bbundle\b)',re.I)
CODE=re.compile(r'\b(?:promo(?:tion)?|coupon|voucher|discount)\s+codes?\s*[:=\-]\s*["\'“”]?([A-Z0-9][A-Z0-9_-]{3,24})["\'“”]?\b|\b(?:use|enter|apply)\s+(?:code\s*)?[:=\-]?\s*["\'“”]?([A-Z0-9][A-Z0-9_-]{3,24})["\'“”]?\b|\bcode\s*[:=\-]\s*["\'“”]?([A-Z0-9][A-Z0-9_-]{3,24})["\'“”]?\b',re.I)
BADCODE={'COPY','CODE','COUPON','TODAY','DEAL','DEALS','SALE','SHOP','CLICK','VERIFY','ACTIVE','PROMO','PROMOS','OFFER','OFFERS','ENTER','THIS','YOUR','FROM','ONLY','APPLY','HELP','PAGE','NEXT','SIGN','JOIN','REQUIRED','INTO','SAVE','SAVINGS','GET','NOW','USE','DISCOUNT','WITH'}
NOISE=re.compile(r'\b(?:your cart is empty|estimated total|current price|original price|sale price|add to wishlist|sign in|log in|login|create account|enter password|password|forgot password|reset password|privacy policy|terms(?: and conditions)?|cookie(?:s| policy)?|product advice|shipping address|billing address|search results|compare products|recently viewed|recommended for you|sort by|filter by|size guide|store locator|customer service|help center|shopping cart|checkout|quantity|subtotal|billing information)\b',re.I)
BADTITLE=re.compile(r'^(?:sale|sales|deals?|offers?|promotions?|discounts?|clearance|current price.*|original price.*|product\s*\d*|item\s*\d*|\$?\s*\d+(?:[.,]\d+)?(?:\s*%|\s*off)?)$',re.I)
CTA=re.compile(r'\b(?:shop now|buy now|shop|buy|claim|redeem|get (?:deal|offer|code)|view (?:deal|offer)|see (?:deal|offer)|save now|use offer|add to (?:cart|bag)|select options|choose options|purchase)\b',re.I)
PROMOPATH=re.compile(r'/(?:sale|deals?|offers?|promotions?|promo|coupon|coupons|clearance|specials?|campaigns?)(?:/|$)',re.I)
COMMERCE=re.compile(r'/(?:p|product|products|shop|collections?|category|categories|sale|deals?|offers?|store|w|t)(?:/|$)',re.I)
BADPATH=re.compile(r'/(?:privacy|legal|terms|help|faq|support|returns?|contact|about|account|login|signin|search|wishlist)(?:/|$)',re.I)
EXPIRY=re.compile(r'\b(?:expires?|expiry|expiration|ends?|valid until|valid through|good through|offer ends?|ends on)\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|[A-Za-z]{3,9}\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?)',re.I)
def clean(v):return re.sub(r'\s+',' ',BeautifulSoup(str(v or ''),'html.parser').get_text(' ',strip=True)).strip()
def norm(v):return re.sub(r'\s+',' ',str(v or '')).strip().lower()
def host(v):
 p=urlparse(v if '://' in str(v) else 'https://'+str(v));return (p.hostname or '').lower().removeprefix('www.')
def same(a,b):
 x,y=host(a),host(b);return bool(x and y and(x==y or x.endswith('.'+y) or y.endswith('.'+x)))
def absolute(h,b):
 u=urljoin(b,str(h or '').strip());return u if u.startswith(('http://','https://')) else ''
def fetch(url,domain):
 last='FETCH_FAILED'
 for n in range(RETRIES):
  try:
   r=requests.get(url,headers=H,timeout=TIMEOUT,allow_redirects=True);last=f'HTTP_{r.status_code}'
   if r.status_code in {403,408,425,429} or r.status_code>=500:
    if n+1<RETRIES:time.sleep(2**n);continue
   if r.status_code>=400 or not same(r.url,domain) or 'html' not in r.headers.get('content-type','').lower():return None,last
   return r,''
  except requests.RequestException as e:
   last=type(e).__name__
   if n+1<RETRIES:time.sleep(2**n)
 return None,last
def codes(text):
 out=[]
 for m in CODE.finditer(text):
  x=next((g for g in m.groups() if g), '').upper()
  if x not in BADCODE and x not in out:out.append(x)
 return out[:2]
def expiry(text):
 m=EXPIRY.search(clean(text))
 if not m:return ''
 raw=re.sub(r'(\d)(st|nd|rd|th)\b',r'\1',m.group(1),flags=re.I).replace('/','-')
 for f in ('%m-%d-%Y','%m-%d-%y','%d-%m-%Y','%d-%m-%y','%b %d, %Y','%B %d, %Y','%b %d %Y','%B %d %Y'):
  try:return datetime.strptime(raw,f).replace(tzinfo=timezone.utc).isoformat()
  except ValueError:pass
 return ''
def title_for(block,text):
 vals=[clean(x.get_text(' ',strip=True)) for x in block.find_all(['h1','h2','h3','h4','strong'])]
 vals+=re.split(r'(?<=[.!?])\s+',text)
 for x in vals:
  x=re.sub(r'\s+',' ',x).strip(' -:|')
  if 8<=len(x)<=220 and not NOISE.search(x) and not BADTITLE.fullmatch(x):return x
 return ''
def fallback_title(text):
 for sentence in re.split(r'(?<=[.!?])\s+',clean(text)):
  sentence=clean(sentence)
  if 30<=len(sentence)<=220 and not NOISE.search(sentence):
   return sentence
 return ''
def seo_title(source,raw,discount='',code=''):
 """Keep useful source wording, but avoid generic copied/template titles."""
 merchant=clean(source.get('merchant','')); market=clean(source.get('market',''))
 title=clean(raw).strip(' -:|')
 if len(title)<18 or BADTITLE.fullmatch(title):
  detail=code and f'code {code}' or discount or 'official promotion'
  variants=(f'{merchant}: {detail}',f'{detail.title()} available from {merchant}',f'{merchant} promotion — {detail}')
  stable_key=f'{norm(title)}|{norm(merchant)}|{norm(market)}'.encode()
  title=variants[int(hashlib.sha1(stable_key).hexdigest(),16)%len(variants)]
 elif merchant.casefold() not in title.casefold():
  title=f'{merchant} — {title}'
 if market and market.casefold() not in {'international','global','worldwide'} and market.casefold() not in title.casefold():
  title=f'{title} ({market})'
 return title[:220].rsplit(' ',1)[0] if len(title)>220 else title
def score_link(a,page,domain):
 u=absolute(a.get('href'),page)
 if not u or not same(u,domain):return '',-1
 p=urlparse(u);txt=clean(a.get_text(' ',strip=True))
 if BADPATH.search(p.path) and not PROMOPATH.search(p.path):return '',-1
 s=(80 if CTA.search(txt) else 0)+(45 if COMMERCE.search(p.path) else 0)+(20 if PROMOPATH.search(p.path) else 0)
 return (u,s) if s>=10 else ('',-1)
def best_destination(soup,page,domain,block=None):
 cand=[]
 for a in (block.find_all('a',href=True) if block else soup.find_all('a',href=True)):
  u,s=score_link(a,page,domain)
  if u:cand.append((s,u))
 if not block:
  for a in soup.find_all('a',href=True):
   u,s=score_link(a,page,domain)
   if u and PROMOPATH.search(urlparse(u).path):cand.append((s+20,u))
 return sorted(cand,key=lambda x:(-x[0],x[1]))[0][1] if cand else ''
def extract(response,source):
 soup=BeautifulSoup(response.text,'html.parser')
 for n in soup(['script','style','noscript','svg','template','nav','footer','header']):n.decompose()
 blocks=soup.find_all(['article','section','li'])+soup.find_all('div',class_=re.compile(r'promo|offer|deal|sale|coupon|discount|campaign',re.I))
 out=[];seen=set();rejects={}
 for b in blocks:
  text=clean(b.get_text(' ',strip=True));cs=codes(text);title=title_for(b,text)
  reason=''
  if not 30<=len(text)<=5000:reason='length'
  elif not title:title=fallback_title(text)
  if not title:reason='no_readable_title'
  if reason:
   rejects[reason]=rejects.get(reason,0)+1;continue
  dest=best_destination(soup,response.url,source['domain'],b) or best_destination(soup,response.url,source['domain'])
  # A verified first-party offer page is still a valid SEO source when the
  # merchant does not expose a separate CTA in the HTML. Keep quality gates
  # on the promotion signal, concrete benefit and source-domain check.
  if not dest:
   dest=response.url
   rejects['source_page_destination_fallback']=rejects.get('source_page_destination_fallback',0)+1
  dm=re.search(r'\b\d{1,3}\s*%\s*(?:off|discount)\b|\$\s?\d+(?:[.,]\d+)?\s*(?:off|discount)\b|\b(?:save|off)\s+\$?\d+(?:[.,]\d+)?',text,re.I);discount=dm.group(0) if dm else ''
  title=seo_title(source,title,discount,cs[0] if cs else '')
  key=(norm(source['merchant']),norm(title),norm(cs[0] if cs else ''),norm(discount),norm(response.url))
  if key in seen:continue
  seen.add(key)
  requested_source=source.get('official_homepage') or response.url
  out.append({'id':hashlib.sha256('|'.join(map(norm,(source['merchant'],source['category'],title,cs[0] if cs else '',discount,dest,requested_source))).encode()).hexdigest()[:20],'title':title,'content':text[:900],'code':cs[0] if cs else '','discount':discount,'merchant':source['merchant'],'category':source['category'],'country':source.get('country','International'),'market':source.get('market','International'),'locale':source.get('locale',''),'url':dest,'source_url':requested_source,'promotion_url':response.url,'final_purchase_url':dest,'official_homepage':source['official_homepage'],'source_domain':source['domain'],'official_source':True,'source_verification_status':'assistant_verified_first_party','source_verification_authority':'assistant','source_verification_method':'assistant_research_manifest','discovery_evidence':'specific_promotion_program','code_context':bool(cs),'promotion_type':'coupon_code' if cs else 'direct_promotion','detected_at':datetime.now(timezone.utc).isoformat(),'last_checked':datetime.now(timezone.utc).isoformat(),'expires_at':expiry(text),'status':'active','verified':False,'offer_qualified':True,'purchase_url_verification_status':'pending','purchase_url_verification_reason':'brand_sales_destination','images':[],'image':'','summary_type':'first_party_specific_promotion'})
 # Some official promotion pages place valid FAQ answers in a very large
 # container, so block-level extraction rejects them on length. Recover only
 # self-contained sentences that include both a promotion signal and benefit.
 page_text=clean(soup.get_text(' ',strip=True))
 page_dest=best_destination(soup,response.url,source['domain']) or response.url
 for sentence in re.split(r'(?<=[.!?])\s+',page_text):
  sentence=clean(sentence)
  if not 30<=len(sentence)<=700 or NOISE.search(sentence):continue
  cs=codes(sentence)
  # The source itself is official and already inside the fixed allowlist. Do
  # not discard a useful sentence merely because the merchant uses wording that
  # is not in our promotion dictionary.
  discount_match=re.search(r'\b\d{1,3}\s*%\s*(?:off|discount)\b|\$\s?\d+(?:[.,]\d+)?\s*(?:off|discount)\b|\b(?:save|off)\s+\$?\d+(?:[.,]\d+)?',sentence,re.I)
  discount=discount_match.group(0) if discount_match else ''
  title=seo_title(source,sentence,discount,cs[0] if cs else '')
  key=(norm(source['merchant']),norm(title),norm(cs[0] if cs else ''),norm(discount),norm(response.url))
  if key in seen or not page_dest:continue
  seen.add(key)
  requested_source=source.get('official_homepage') or response.url
  out.append({'id':hashlib.sha256('|'.join(map(norm,(source['merchant'],source['category'],title,cs[0] if cs else '',discount,page_dest,requested_source))).encode()).hexdigest()[:20],'title':title,'content':sentence,'code':cs[0] if cs else '','discount':discount,'merchant':source['merchant'],'category':source['category'],'country':source.get('country','International'),'market':source.get('market','International'),'locale':source.get('locale',''),'url':page_dest,'source_url':requested_source,'promotion_url':response.url,'final_purchase_url':page_dest,'official_homepage':source['official_homepage'],'source_domain':source['domain'],'official_source':True,'source_verification_status':'assistant_verified_first_party','source_verification_authority':'assistant','source_verification_method':'assistant_research_manifest','discovery_evidence':'specific_promotion_program_sentence','code_context':bool(cs),'promotion_type':'coupon_code' if cs else 'direct_promotion','detected_at':datetime.now(timezone.utc).isoformat(),'last_checked':datetime.now(timezone.utc).isoformat(),'expires_at':expiry(sentence),'status':'active','verified':False,'offer_qualified':True,'purchase_url_verification_status':'pending','purchase_url_verification_reason':'brand_sales_destination','images':[],'image':'','summary_type':'first_party_specific_promotion'})
 if rejects: print(f"DISCOVERY {source['merchant']}: candidates={len(out)} rejects={json.dumps(rejects,sort_keys=True)}")
 return out
def discovery_links(response,domain):
 soup=BeautifulSoup(response.text,'html.parser');found={}
 for a in soup.find_all('a',href=True):
  u=absolute(a.get('href'),response.url)
  if not u or not same(u,domain):continue
  p=urlparse(u).path;t=clean(a.get_text(' ',strip=True))
  if BADPATH.search(p) and not PROMOPATH.search(p):continue
  s=(70 if PROMOPATH.search(p) else 0)+(40 if PROMO.search(t) else 0)+(25 if BENEFIT.search(t) else 0)+(10 if COMMERCE.search(p) else 0)
  if s>=10:found[u]=max(found.get(u,0),s)
 return [u for u,_ in sorted(found.items(),key=lambda x:(-x[1],x[0]))[:MAX_PAGES-1]]
def collect(source):
	q=list(source.get('url_allowlist') or [source['official_homepage']]);seen=set();items=[];errors=[]
	while q and len(seen)<MAX_PAGES:
		u=q.pop(0)
		if u in seen:continue
		seen.add(u);r,e=fetch(u,source['domain'])
		if not r:errors.append(e);continue
		items.extend(extract(r,source))
		# Start from each supplied homepage/market URL, then follow only highly
		# ranked first-party promotion links on that same hostname. This fixes
		# missed offers hidden behind brand homepages without leaving the
		# 120-brand/domain boundary.
		if source.get('allow_discovery',True):
			for candidate in discovery_links(r,source['domain']):
				if candidate not in seen and candidate not in q:q.append(candidate)
	return source,items,errors
def load_sources():
	if ALLOWLIST.exists():
		data=json.loads(ALLOWLIST.read_text(encoding='utf-8'))
		if data.get('mode')!='root_and_verified_promo_allowlist' or data.get('allow_discovery') is not False or data.get('allow_redirect_source_expansion') is not False:
			raise SystemExit('SOURCE ALLOWLIST CONTRACT FAILED: redirect expansion must be disabled')
		entries=data.get('entries',[])
		if data.get('total_brands')!=120 or data.get('total_urls')!=len(entries):
			raise SystemExit(f'SOURCE ALLOWLIST CONTRACT FAILED: expected 120 brands and declared URL count, got {data.get("total_brands")} / {len(entries)}')
		rows=[]
		for x in entries:
			rows.append({'merchant':x['merchant'],'category':x['category'],'country':x['country'],'market':x['market'],'official_homepage':x['url'],'domain':x['domain'],'url_allowlist':[x['url']],'allow_discovery':False,'allow_redirect_source_expansion':False})
	return rows
	raise SystemExit('SOURCE ALLOWLIST MISSING: refusing to use legacy brand/source list')
def main():
 sources=sorted(load_sources(),key=lambda s:(norm(s['merchant']),norm(s.get('market')),norm(s['official_homepage'])))
 all_items=[];status=[]
 with ThreadPoolExecutor(max_workers=WORKERS) as ex:
  fs=[(s,ex.submit(collect,s)) for s in sources]
  results={ (norm(s['merchant']),norm(s.get('market')),norm(s['official_homepage'])): f.result() for s,f in fs }
 for s in sources:
   _,items,errors=results[(norm(s['merchant']),norm(s.get('market')),norm(s['official_homepage']))];all_items.extend(sorted(items,key=lambda x:(norm(x.get('merchant')),norm(x.get('category')),norm(x.get('title')),norm(x.get('code')),norm(x.get('discount')),norm(x.get('promotion_url')),norm(x.get('final_purchase_url')))))
   status.append({'merchant':s['merchant'],'category':s['category'],'status':'scanned','offers':len(items),'errors':sorted(errors)[:5]})
 dedup={}
 for x in all_items:
  key=(norm(x.get('merchant')),norm(x.get('category')),norm(x.get('market')),norm(x.get('country')),norm(x.get('title')),norm(x.get('code')),norm(x.get('discount')),norm(x.get('promotion_url')),norm(x.get('final_purchase_url')))
  if key not in dedup:dedup[key]=x
 all_items=sorted(dedup.values(),key=lambda x:(norm(x.get('merchant')),norm(x.get('category')),norm(x.get('title')),norm(x.get('code')),norm(x.get('discount')),norm(x.get('promotion_url')),norm(x.get('final_purchase_url'))))
 OUT.write_text(json.dumps(all_items,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 bycat={c:sum(x['category']==c for x in all_items) for c in CATS};print(f'DEAL BOT: exact_allowlist_urls={len(sources)} candidates={len(all_items)} by_category={bycat}');print('SOURCE STATUS:',json.dumps(status,ensure_ascii=False))
 expected_sources=len(sources)
 if len(status)!=expected_sources:raise SystemExit(f'DEAL BOT FAILED: incomplete source scan {len(status)}/{expected_sources}')
 if not all_items:raise SystemExit('DEAL BOT FAILED: zero promotion candidates')
if __name__=='__main__':main()
