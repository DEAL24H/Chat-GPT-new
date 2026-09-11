"""Validate that all publication layers describe exactly one release."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 errors=[]; data=ROOT/'data'
 manifest=json.loads((data/'data-manifest.json').read_text(encoding='utf-8')); search=json.loads((data/'search-index.json').read_text(encoding='utf-8'))
 shard_ids=[]
 for slug,info in manifest.get('shards',{}).items():
  path=data/info['path']
  if not path.exists(): errors.append(f'MISSING_SHARD:{slug}'); continue
  rows=json.loads(path.read_text(encoding='utf-8')); shard_ids.extend(str(x.get('id') or '') for x in rows)
  if len(rows)!=info.get('count'): errors.append(f'SHARD_COUNT_MISMATCH:{slug}')
 shard_ids=sorted(shard_ids); search_ids=sorted(str(x.get('id') or '') for x in search.get('items',[])); manifest_ids=sorted(str(x) for x in manifest.get('ids',[]))
 if manifest.get('total')!=len(shard_ids) or manifest.get('total')!=len(search_ids): errors.append('STATIC_COUNT_MISMATCH')
 if shard_ids!=search_ids or shard_ids!=manifest_ids: errors.append('STATIC_ID_SET_MISMATCH')
 release=hashlib.sha256('|'.join(shard_ids).encode()).hexdigest()[:16]
 if manifest.get('release_id')!=release or search.get('release_id')!=release: errors.append('STATIC_RELEASE_ID_MISMATCH')
 seo=json.loads((ROOT/'seo'/'seo-index.json').read_text(encoding='utf-8')); records=seo.get('offers',[]); seo_ids=sorted(str(x.get('id') or '') for x in records)
 if seo_ids!=shard_ids: errors.append(f'SEO_ID_SET_MISMATCH:static={len(shard_ids)}:seo={len(seo_ids)}')
 if seo.get('release_id')!=release: errors.append('SEO_RELEASE_ID_MISMATCH')
 seo_urls={str(x.get('canonical')) for x in records if x.get('canonical')}; sitemap=(ROOT/'sitemap-seo.xml').read_text(encoding='utf-8'); sitemap_urls=set(re.findall(r'<loc>(https://deal24h\.net/seo/[^<]+/)</loc>',sitemap))
 if seo_urls!=sitemap_urls: errors.append(f'SEO_SITEMAP_MISMATCH:missing={len(seo_urls-sitemap_urls)}:extra={len(sitemap_urls-seo_urls)}')
 main_sitemap=(ROOT/'sitemap.xml').read_text(encoding='utf-8'); main_urls=set(re.findall(r'<loc>(https://deal24h\.net/[^<]+/)</loc>',main_sitemap))
 if not seo_urls.issubset(main_urls): errors.append('MAIN_SITEMAP_MISSING_SEO_URL')
 if errors:
  print('RELEASE CONSISTENCY FAILED'); [print('-',e) for e in errors]; raise SystemExit(1)
 print(f'RELEASE CONSISTENCY PASS: release_id={release} records={len(shard_ids)} seo_pages={len(seo_urls)} ids=same sitemap_layers=consistent')
if __name__=='__main__':main()
