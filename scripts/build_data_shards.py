"""Build browser-friendly data shards and a compact global search index."""
import hashlib
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]; DATA=ROOT/'data'; SOURCE=DATA/'news.json'; OUT=DATA/'shards'
CATEGORY_SLUGS={'Fashion':'fashion','Electronics':'electronics','Beauty & Personal Care':'beauty-and-personal-care','Home & Living':'home-and-living'}
def norm(value):return re.sub(r'[^a-z0-9]+',' ',str(value or '').lower()).strip()
def stable_id(item):
 raw=str(item.get('id') or ''); return raw or hashlib.sha1(json.dumps(item,sort_keys=True).encode()).hexdigest()[:16]
def active(item):
 return isinstance(item,dict) and item.get('status') not in {'expired','inactive'} and item.get('offer_qualified') is True and item.get('purchase_url_verification_status')=='live_verified' and bool(item.get('final_purchase_url'))
def compact(item,shard):
 destination=item.get('final_purchase_url') or ''; promotion=item.get('promotion_url') or item.get('source_url') or ''
 return {'id':stable_id(item),'title':item.get('title',''),'content':item.get('content',''),'code':item.get('code',''),'discount':item.get('discount',''),'merchant':item.get('merchant',''),'category':item.get('category',''),'final_purchase_url':destination,'promotion_url':promotion,'official_source':bool(item.get('official_source')),'expires_at':item.get('expires_at',''),'status':item.get('status','active'),'_shard':shard}
def main():
 raw=json.loads(SOURCE.read_text(encoding='utf-8')); items=raw if isinstance(raw,list) else raw.get('items',[]); OUT.mkdir(parents=True,exist_ok=True)
 for old in OUT.glob('*.json'):old.unlink()
 shards={slug:[] for slug in CATEGORY_SLUGS.values()}; search=[]; skipped=set()
 for item in items:
  if not active(item):continue
  category=item.get('category') or ''; slug=CATEGORY_SLUGS.get(category)
  if not slug:
   if category:skipped.add(str(category))
   continue
  row=compact(item,f'shards/{slug}.json'); shards[slug].append(row)
  search.append({'id':row['id'],'shard':row['_shard'],'merchant':row['merchant'],'category':row['category'],'text':norm(' '.join([row['merchant'],row['title'],row['code'],row['content']]))[:600]})
 counts={category:len(shards[slug]) for category,slug in CATEGORY_SLUGS.items()}
 total=sum(counts.values())
 manifest={'version':3,'categories':list(CATEGORY_SLUGS),'total':total,'counts':counts,'shards':{},'search':'search-index.json'}
 for category,slug in CATEGORY_SLUGS.items():
  rows=shards[slug]; rows.sort(key=lambda x:(norm(x.get('merchant')),x.get('id','')))
  (OUT/f'{slug}.json').write_text(json.dumps(rows,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
  manifest['shards'][slug]={'path':f'shards/{slug}.json','count':len(rows),'category':category}
 search.sort(key=lambda x:(norm(x['merchant']),x['id']))
 search_payload={'version':1,'count':len(search),'items':search}
 if manifest['total'] != len(search):
  raise RuntimeError(f'CANONICAL DATA BUILD MISMATCH: manifest.total={manifest["total"]} search.count={len(search)}')
 if manifest['total'] != sum(manifest['counts'].values()):
  raise RuntimeError(f'CANONICAL DATA BUILD MISMATCH: manifest.total={manifest["total"]} counts_sum={sum(manifest["counts"].values())}')
 if any(manifest['shards'][slug]['count'] != manifest['counts'][category] for category,slug in CATEGORY_SLUGS.items()):
  raise RuntimeError('CANONICAL DATA BUILD MISMATCH: shard counts differ from category counts')
 (DATA/'search-index.json').write_text(json.dumps(search_payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
 (DATA/'data-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
 print(f"Built {sum(bool(v) for v in shards.values())} active data shards, {len(shards)} total category shards and {len(search)} search records; manifest total={total} counts={counts}"+(f"; skipped non-priority categories: {', '.join(sorted(skipped))}" if skipped else ''))
if __name__=='__main__':main()
