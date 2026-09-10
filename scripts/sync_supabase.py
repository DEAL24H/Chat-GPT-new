"""Synchronize the verified DEAL24H dataset to Supabase.

Only source URLs from data/allowed_brand_urls.json may be synchronized. The
manifest is generated from the supplied workbook and is the sole source
allowlist for the runtime pipeline.
"""
import json, os, urllib.error, urllib.parse, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/news.json'
ALLOWLIST=ROOT/'data/allowed_brand_urls.json'
CATEGORIES=("Fashion","Electronics","Beauty & Personal Care","Home & Living")
def normalize_base_url(value):
 raw=str(value or '').strip().rstrip('/')
 if raw.lower().endswith('/rest/v1'): raw=raw[:-8].rstrip('/')
 p=urllib.parse.urlparse(raw)
 if not raw or p.scheme not in {'http','https'} or not p.netloc: raise RuntimeError('SUPABASE_URL must be a valid project URL')
 return raw
URL=normalize_base_url(os.getenv('SUPABASE_URL','')); KEY=os.getenv('SUPABASE_SERVICE_ROLE_KEY','')
if not URL or not KEY: raise SystemExit('Supabase sync requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY')
manifest=json.loads(ALLOWLIST.read_text(encoding='utf-8'))
if manifest.get('mode')!='root_and_verified_promo_allowlist' or manifest.get('allow_discovery') is not False or len(manifest.get('entries',[]))!=manifest.get('total_urls') or manifest.get('total_brands')!=120:
 raise SystemExit('Supabase contract: invalid root and verified promo URL allowlist')
allowed={str(r.get('url','')).rstrip('/'):r for r in manifest['entries']}
raw=json.loads(DATA.read_text(encoding='utf-8')); items=raw if isinstance(raw,list) else raw.get('items',[]); rows=[]
for x in items:
 if not isinstance(x,dict) or x.get('status') in {'expired','inactive'}: continue
 merchant=str(x.get('merchant') or '').strip(); category=str(x.get('category') or '').strip(); source_url=str(x.get('source_url') or '').strip().rstrip('/')
 if category not in CATEGORIES: raise SystemExit(f'Supabase contract: non-canonical category for {merchant}: {category}')
 source=allowed.get(source_url)
 if not source: raise SystemExit(f'Supabase contract: source URL outside exact allowlist: {source_url}')
 if source.get('merchant')!=merchant or source.get('category')!=category: raise SystemExit(f'Supabase contract: source identity mismatch for {merchant}')
 promotion=str(x.get('promotion_url') or '').strip(); final=str(x.get('final_purchase_url') or '').strip(); url=str(x.get('url') or '').strip()
 if not promotion or not final or url!=final: raise SystemExit(f'Supabase contract: inconsistent promotion/purchase destination for {merchant}')
 if x.get('source_verification_status')!='assistant_verified_first_party': raise SystemExit(f'Supabase contract: source not assistant-verified for {merchant}')
 if x.get('purchase_url_verification_status')!='live_verified': raise SystemExit(f'Supabase contract: purchase URL is not live_verified for {merchant}: {x.get("purchase_url_verification_status")}')
 if x.get('offer_qualified') is not True: raise SystemExit(f'Supabase contract: unqualified offer for {merchant}')
 rows.append({'id':str(x.get('id') or ''),'merchant':merchant,'category':category,'country':x.get('country') or source.get('country') or 'International','title':x.get('title'),'content':x.get('content'),'code':x.get('code'),'discount':x.get('discount'),'promotion_url':promotion,'source_url':x.get('source_url'),'source_domain':source.get('domain'),'official_source':True,'status':x.get('status') or 'active','expires_at':x.get('expires_at') or None,'detected_at':x.get('detected_at') or None,'last_checked':x.get('last_checked') or None,'final_purchase_url':final,'source_verification_status':'assistant_verified_first_party','source_verification_authority':'assistant','purchase_url_verification_status':'live_verified','purchase_url_verification_reason':x.get('purchase_url_verification_reason'),'purchase_url_verified_at':x.get('purchase_url_verified_at') or None})
 if not rows[-1]['id']: raise SystemExit(f'Supabase contract: empty deal id for {merchant}')
by_category={c:[] for c in CATEGORIES}
for r in rows: by_category[r['category']].append(r)
headers={'apikey':KEY,'Authorization':f'Bearer {KEY}','Content-Type':'application/json','Prefer':'resolution=merge-duplicates,return=minimal'}
def request(method,table='deals',body=None,query='',prefer=None):
 endpoint=f'{URL}/rest/v1/{table}{query}'; payload=None if body is None else json.dumps(body,ensure_ascii=False).encode(); h=dict(headers)
 if prefer:h['Prefer']=prefer
 try:
  with urllib.request.urlopen(urllib.request.Request(endpoint,data=payload,method=method,headers=h),timeout=60) as r:return r.status,r.headers,r.read()
 except urllib.error.HTTPError as e: raise RuntimeError(f'Supabase {method} {endpoint} failed: HTTP {e.code}: {e.read().decode(errors="replace")[:1000]}') from e
 except urllib.error.URLError as e: raise RuntimeError(f'Supabase {method} {endpoint} failed: {e.reason}') from e
def exact_count(query=''):
 _,h,_=request('GET','deals',query=f'?select=id&limit=1{query}',prefer='count=exact'); cr=h.get('Content-Range','')
 if '/' not in cr: raise RuntimeError('Supabase deals: missing Content-Range verification header')
 return int(cr.rsplit('/',1)[1])
ids=[r['id'] for r in rows]
if rows: request('POST','deals',rows)
if ids:
 encoded=','.join(urllib.parse.quote(i,safe='') for i in ids); request('DELETE','deals',query=f'?id=not.in.({encoded})')
else: request('DELETE','deals',query='?id=not.is.null')
actual=exact_count()
if actual!=len(rows): raise RuntimeError(f'Supabase deals: expected {len(rows)} rows, found {actual}')
for c in CATEGORIES:
 actual_c=exact_count('&category=eq.'+urllib.parse.quote(c,safe=''))
 if actual_c!=len(by_category[c]): raise RuntimeError(f'Supabase deals category {c!r}: expected {len(by_category[c])} rows, found {actual_c}')
print('SUPABASE CANONICAL SYNC PASS:',f'deals={actual}',', '.join(f'{c}={len(by_category[c])}' for c in CATEGORIES))
