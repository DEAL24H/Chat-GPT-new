"""Optional server-side sync for the canonical deal store.

The workflow calls this only when SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY
are configured. The public browser never receives the service-role key.
"""
import json, os, urllib.error, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/news.json'
URL=os.getenv('SUPABASE_URL','').rstrip('/')
KEY=os.getenv('SUPABASE_SERVICE_ROLE_KEY','')

if not URL or not KEY:
    print('Supabase sync skipped: credentials are not configured.')
    raise SystemExit(0)

raw=json.loads(DATA.read_text(encoding='utf-8'))
items=raw if isinstance(raw,list) else raw.get('items',[])
rows=[]
for x in items:
    if not isinstance(x,dict) or x.get('status')=='expired': continue
    rows.append({
        'id':str(x.get('id') or ''), 'merchant':x.get('merchant') or 'Unknown',
        'category':x.get('category') or 'Consumer', 'country':x.get('country'),
        'title':x.get('title'), 'content':x.get('content'), 'code':x.get('code'),
        'discount':x.get('discount'), 'promotion_url':x.get('promotion_url') or x.get('url'),
        'source_url':x.get('source_url'), 'source_domain':x.get('source_domain'),
        'official_source':bool(x.get('official_source')), 'status':x.get('status') or 'active',
        'expires_at':x.get('expires_at') or None, 'detected_at':x.get('detected_at') or None,
        'last_checked':x.get('last_checked') or None,
    })
rows=[r for r in rows if r['id']]
endpoint=f'{URL}/rest/v1/deals?on_conflict=category,id'
# PostgREST accepts JSON arrays for bulk upsert.
body=json.dumps(rows,ensure_ascii=False).encode('utf-8')
req=urllib.request.Request(endpoint,data=body,method='POST',headers={
    'apikey':KEY,'Authorization':f'Bearer {KEY}','Content-Type':'application/json','Prefer':'resolution=merge-duplicates,return=minimal'
})
try:
    with urllib.request.urlopen(req,timeout=60) as response:
        print(f'Supabase sync OK: {len(rows)} rows, HTTP {response.status}')
except urllib.error.HTTPError as e:
    print(e.read().decode('utf-8','replace'))
    raise
