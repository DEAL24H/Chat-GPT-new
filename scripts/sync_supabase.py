"""Synchronize the verified DEAL24H dataset to Supabase.

promotion_url = first-party URL where the promotion was discovered.
final_purchase_url/url = first-party live-verified destination where the user buys.
"""
import json, os, urllib.error, urllib.parse, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data/news.json'; SELECTION=ROOT/'data/assistant_verified_source_selection.json'
CATEGORIES=("Fashion","Electronics","Beauty & Personal Care","Home & Living")
def normalize_base_url(value):
 raw=str(value or '').strip().rstrip('/')
 if raw.lower().endswith('/rest/v1'): raw=raw[:-8].rstrip('/')
 p=urllib.parse.urlparse(raw)
 if not raw or p.scheme not in {'http','https'} or not p.netloc: raise RuntimeError('SUPABASE_URL must be a valid project URL')
 return raw
URL=normalize_base_url(os.getenv('SUPABASE_URL','')); KEY=os.getenv('SUPABASE_SERVICE_ROLE_KEY','')
if not URL or not KEY: raise SystemExit('Supabase sync requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY')
selection=json.loads(SELECTION.read_text(encoding='utf-8'))
if selection.get('total')!=120 or selection.get('counts')!={c:30 for c in CATEGORIES}: raise SystemExit(f"Supabase contract: invalid assistant source selection {selection.get('counts')}")
if selection.get('source_authority')!='assistant_verified_manifests': raise SystemExit('Supabase contract: unexpected source authority')
allowed={(str(r.get('merchant') or '').casefold(),str(r.get('category') or '')):r for r in selection.get('sources',[])}
if len(allowed)!=120: raise SystemExit(f'Supabase contract: expected 120 unique assistant-verified merchants, found {len(allowed)}')
raw=json.loads(DATA.read_text(encoding='utf-8')); items=raw if isinstance(raw,list) else raw.get('items',[]); rows=[]
for x in items:
 if not isinstance(x,dict) or x.get('status') in {'expired','inactive'}: continue
 merchant=str(x.get('merchant') or '').strip(); category=str(x.get('category') or '').strip(); source=allowed.get((merchant.casefold(),category))
 if category not in CATEGORIES: raise SystemExit(f'Supabase contract: non-canonical category for {merchant}: {category}')
 if not source: raise SystemExit(f'Supabase contract: merchant outside assistant allowlist: {merchant} / {category}')
 promotion=str(x.get('promotion_url') or '').strip(); final=str(x.get('final_purchase_url') or '').strip(); url=str(x.get('url') or '').strip()
 if not promotion or not final or url!=final: raise SystemExit(f'Supabase contract: inconsistent promotion/purchase destination for {merchant}')
 if x.get('source_verification_status')!='assistant_verified_first_party': raise SystemExit(f'Supabase contract: source not assistant-verified for {merchant}')
 if x.get('purchase_url_verification_status')!='live_verified': raise SystemExit(f'Supabase contract: purchase URL is not live_verified for {merchant}: {x.get("purchase_url_verification_status")}')
 if x.get('offer_qualified') is not True: raise SystemExit(f'Supabase contract: unqualified offer for {merchant}')
 rows.append({'id':str(x.get('id') or ''),'merchant':merchant,'category':category,'country':x.get('country') or 'International','title':x.get('title'),'content':x.get('content'),'code':x.get('code'),'discount':x.get('discount'),'promotion_url':promotion,'source_url':x.get('source_url'),'source_domain':source.get('domain'),'official_source':True,'status':x.get('status') or 'active','expires_at':x.get('expires_at') or None,'detected_at':x.get('detected_at') or None,'last_checked':x.get('last_checked') or None,'final_purchase_url':final,'source_verification_status':'assistant_verified_first_party','source_verification_authority':'assistant','purchase_url_verification_status':'live_verified','purchase_url_verification_reason':x.get('purchase_url_verification_reason'),'purchase_url_verified_at':x.get('purchase_url_verified_at') or None})
 if not rows[-1]['id']: raise SystemExit(f'Supabase contract: empty deal id for {merchant}')
by_category={c:[] for c in CATEGORIES}
for r in rows: by_category[r['category']].append(r)
headers={'apikey':KEY,'Authorization':f'Bearer {KEY}','Content-Type':'application/json','Prefer':'resolution=merge-duplicates,return=minimal'}
def request(method,table='deals',body=None,query='',prefer=None):
 endpoint=f'{URL}/rest/v1/{table}{query}'; payload=None if body is None else json.dumps(body,ensure_ascii=False).encode()
 h=dict(headers)
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
