import json,re
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'data/news.json';CATALOG=ROOT/'data/brand_catalog.json';TIMEOUT=15
UA='Mozilla/5.0 (compatible; Deal24HOfferLinkValidator/6.0; +https://deal24h.net/)'
EXPECTED={'Fashion','Electronics','Beauty & Personal Care','Home & Living'}
SHOP=re.compile(r'/p/|/products?/|/shop(?:/|$)|/collections?/|/category/|/sale(?:/|$)|/deals?(?:/|$)|/w/|/t/|/store(?:/|$)',re.I)
BAD=re.compile(r'privacy|legal|terms|help|faq|support|returns?|contact|account|login|signin|search|wishlist|promo.?terms|product-advice',re.I)
CTA=re.compile(r'add to cart|buy now|shop now|add to bag|purchase|select options|choose options|checkout|\bshop\b|mua ngay|thêm vào giỏ|đặt hàng',re.I)
INACCESSIBLE={403,408,425,429,500,502,503,504,521,522,523,524}
def host(v):
 p=urlparse(v if '://' in str(v) else 'https://'+str(v));return(p.hostname or '').lower().removeprefix('www.')
def same(a,b):
 x,y=host(a),host(b);return bool(x and y and(x==y or x.endswith('.'+y) or y.endswith('.'+x)))
def purchase(v):
 if not str(v).startswith(('http://','https://')):return False
 p=urlparse(v);s=f'{p.path} {p.query}';return not(BAD.search(s) and not SHOP.search(s)) and bool(SHOP.search(s) or (p.hostname or '').lower().startswith(('shop.','store.')))
def live(item):
 u=str(item.get('final_purchase_url') or '').strip()
 try:r=requests.get(u,headers={'User-Agent':UA,'Accept':'text/html,application/xhtml+xml'},timeout=TIMEOUT,allow_redirects=True)
 except Exception as e:return'runtime_inaccessible',f'DESTINATION_REQUEST_FAILED:{type(e).__name__}',u
 f=r.url
 if r.status_code in INACCESSIBLE:return'runtime_inaccessible',f'DESTINATION_RUNTIME_HTTP_{r.status_code}',f
 if r.status_code>=400:return'failed',f'DESTINATION_HTTP_{r.status_code}',f
 if not same(item.get('official_homepage') or item.get('source_url'),f):return'failed','DESTINATION_LEFT_OFFICIAL_DOMAIN',f
 if not purchase(f):return'failed','DESTINATION_NOT_A_BRAND_SALES_OR_PRODUCT_PAGE',f
 soup=BeautifulSoup(r.text,'html.parser');text=soup.get_text(' ',strip=True)[:160000];html=r.text.lower()
 if not(SHOP.search(f'{urlparse(f).path} {urlparse(f).query}') or CTA.search(text) or re.search(r'addtocart|add-to-cart|buy-now|checkout',html) or re.search(r'\$|€|£|¥|\b(?:USD|EUR|GBP|CAD|AUD)\b',text)):return'failed','NO_COMMERCE_SIGNAL',f
 return'live_verified','LIVE_BRAND_SALES_DESTINATION_VERIFIED',f
def main():
 data=json.loads(DATA.read_text());catalog=json.loads(CATALOG.read_text()).get('categories',{});domains={str(e.get('name','')).casefold():str(e.get('domain','')) for es in catalog.values() for e in es}
 if not isinstance(data,list):raise SystemExit('news.json is not a list')
 published=[];rejected=[];now=datetime.now(timezone.utc).isoformat()
 for item in data:
  merchant=str(item.get('merchant') or '').strip();category=str(item.get('category') or '').strip();src=str(item.get('source_url') or '').strip();dest=str(item.get('final_purchase_url') or '').strip();reason=''
  if category not in EXPECTED:reason='NON_CANONICAL_CATEGORY'
  elif item.get('source_verification_status')!='assistant_verified_first_party':reason='SOURCE_NOT_ASSISTANT_VERIFIED'
  elif not src.startswith(('http://','https://')):reason='INVALID_SOURCE_URL'
  elif not purchase(dest):reason='DESTINATION_NOT_BRAND_SALES_OR_PRODUCT_PAGE'
  elif not same(domains.get(merchant.casefold(),src),dest):reason='DESTINATION_LEFT_CATALOG_DOMAIN'
  if reason:rejected.append((merchant,reason,dest));continue
  status,vr,final=live(item)
  if status!='live_verified':rejected.append((merchant,vr,final));continue
  item['purchase_url_verification_status']='live_verified';item['purchase_url_verification_reason']=vr;item['purchase_url_verified_at']=now;item['final_purchase_url']=item['promotion_url']=item['url']=final
  item['published_offer_authority']='assistant_verified_source_plus_live_exact_purchase_page';item['purchase_destination_kind']='brand_sales_or_product_page'
  published.append(item)
 DATA.write_text(json.dumps(published,ensure_ascii=False,indent=2)+'\n')
 print(f'OFFER LINK VALIDATION: discovered={len(data)} published={len(published)} rejected={len(rejected)}')
 for m,r,u in rejected[:100]:print(f'REJECT {m}: {r}: {u}')
 if not published:raise SystemExit('OFFER LINK VALIDATION FAILED: zero live brand sales destinations')
 print('OFFER LINK VALIDATION PASS: published offers use live purchase/sales destinations on the verified brand domain')
if __name__=='__main__':main()
