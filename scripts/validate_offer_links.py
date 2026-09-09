import json,re
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'data/news.json';CATALOG=ROOT/'data/brand_catalog.json';TIMEOUT=15
UA='Mozilla/5.0 (compatible; Deal24HOfferLinkValidator/7.0; +https://deal24h.net/)'
EXPECTED={'Fashion','Electronics','Beauty & Personal Care','Home & Living'}
BAD=re.compile(r'/(?:privacy|legal|terms|help|faq|support|returns?|contact|account|login|signin|search|wishlist)(?:/|$)',re.I)
SHOP_PATH=re.compile(r'/(?:p|product|products|shop|collections?|category|categories|sale|deals?|offers?|store)(?:/|$)',re.I)
CTA=re.compile(r'add to cart|buy now|shop now|add to bag|purchase|select options|choose options|checkout|\bshop\b|mua ngay|thêm vào giỏ|đặt hàng',re.I)
INACCESSIBLE={403,408,425,429,500,502,503,504,521,522,523,524}
def host(v):
 p=urlparse(v if '://' in str(v) else 'https://'+str(v));return(p.hostname or '').lower().removeprefix('www.')
def same(a,b):
 x,y=host(a),host(b);return bool(x and y and(x==y or x.endswith('.'+y) or y.endswith('.'+x)))
def purchase(v):
 if not str(v).startswith(('http://','https://')):return False
 p=urlparse(v);path=f'{p.path} {p.query}'
 return bool(host(v)) and not(BAD.search(p.path) and not SHOP_PATH.search(p.path))
def live(item):
 u=str(item.get('final_purchase_url') or '').strip()
 try:r=requests.get(u,headers={'User-Agent':UA,'Accept':'text/html,application/xhtml+xml'},timeout=(5,TIMEOUT),allow_redirects=True)
 except Exception as e:return'runtime_inaccessible',f'DESTINATION_REQUEST_FAILED:{type(e).__name__}',u
 f=r.url
 if r.status_code in INACCESSIBLE:return'runtime_inaccessible',f'DESTINATION_RUNTIME_HTTP_{r.status_code}',f
 if r.status_code>=400:return'failed',f'DESTINATION_HTTP_{r.status_code}',f
 if not same(item.get('official_homepage') or item.get('source_url'),f):return'failed','DESTINATION_LEFT_OFFICIAL_DOMAIN',f
 if not purchase(f):return'failed','DESTINATION_NOT_ALLOWED_PAGE',f
 soup=BeautifulSoup(r.text,'html.parser');text=soup.get_text(' ',strip=True)[:160000];html=r.text.lower();path=urlparse(f).path
 commerce=bool(SHOP_PATH.search(path) or CTA.search(text) or re.search(r'addtocart|add-to-cart|buy-now|checkout',html) or re.search(r'\$|€|£|¥|\b(?:USD|EUR|GBP|CAD|AUD)\b',text))
 if not commerce:return'failed','NO_COMMERCE_SIGNAL',f
 return'live_verified','LIVE_BRAND_SALES_DESTINATION_VERIFIED',f
def main():
 data=json.loads(DATA.read_text(encoding='utf-8'));catalog=json.loads(CATALOG.read_text(encoding='utf-8')).get('categories',{});domains={str(e.get('name','')).casefold():str(e.get('domain','')) for es in catalog.values() for e in es}
 if not isinstance(data,list):raise SystemExit('news.json is not a list')
 published=[];rejected=[];now=datetime.now(timezone.utc).isoformat()
 def validate_one(item):
  merchant=str(item.get('merchant') or '').strip();category=str(item.get('category') or '').strip();src=str(item.get('source_url') or '').strip();promotion=str(item.get('promotion_url') or '').strip();dest=str(item.get('final_purchase_url') or '').strip();reason=''
  if category not in EXPECTED:reason='NON_CANONICAL_CATEGORY'
  elif item.get('source_verification_status')!='assistant_verified_first_party':reason='SOURCE_NOT_ASSISTANT_VERIFIED'
  elif not src.startswith(('http://','https://')):reason='INVALID_SOURCE_URL'
  elif not promotion.startswith(('http://','https://')) or not same(promotion,src):reason='PROMOTION_URL_NOT_SOURCE_DOMAIN'
  elif not purchase(dest):reason='DESTINATION_NOT_ALLOWED_PAGE'
  elif not same(domains.get(merchant.casefold(),src),dest):reason='DESTINATION_LEFT_CATALOG_DOMAIN'
  if reason:return None,(merchant,reason,dest)
  status,vr,final=live(item)
  if status!='live_verified':return None,(merchant,vr,final)
  item['purchase_url_verification_status']='live_verified';item['purchase_url_verification_reason']=vr;item['purchase_url_verified_at']=now;item['final_purchase_url']=final;item['url']=final
  item['published_offer_authority']='assistant_verified_source_plus_live_brand_purchase_destination';item['purchase_destination_kind']='brand_sales_or_product_page'
  return item,None
 with ThreadPoolExecutor(max_workers=12) as pool:
  futures=[pool.submit(validate_one,item) for item in data]
  for f in as_completed(futures):
   item,reject=f.result()
   if item:published.append(item)
   elif reject:rejected.append(reject)
 DATA.write_text(json.dumps(published,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(f'OFFER LINK VALIDATION: discovered={len(data)} published={len(published)} rejected={len(rejected)}')
 for m,r,u in rejected[:100]:print(f'REJECT {m}: {r}: {u}')
 if not published:raise SystemExit('OFFER LINK VALIDATION FAILED: zero live brand sales destinations')
 print('OFFER LINK VALIDATION PASS: promotion source and purchase destination are independently preserved and verified; shared official sales destinations are allowed')
if __name__=='__main__':main()
