"""Validate that every public layer describes exactly one immutable release."""
import json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bot.release_contract import release_id_for_rows

def main():
 errors=[]; data=ROOT/'data'
 manifest=json.loads((data/'data-manifest.json').read_text(encoding='utf-8')); search=json.loads((data/'search-index.json').read_text(encoding='utf-8')); release=str(manifest.get('release_id') or '')
 shard_rows=[]; shard_ids=[]
 for slug,info in manifest.get('shards',{}).items():
  path=data/info['path']
  if not path.exists(): errors.append(f'MISSING_SHARD:{slug}'); continue
  payload=json.loads(path.read_text(encoding='utf-8')); rows=payload.get('items',[]) if isinstance(payload,dict) else []
  if payload.get('release_id')!=release:errors.append(f'SHARD_RELEASE_ID_MISMATCH:{slug}')
  if payload.get('category')!=info.get('category'):errors.append(f'SHARD_CATEGORY_MISMATCH:{slug}')
  if payload.get('count')!=len(rows) or len(rows)!=info.get('count'):errors.append(f'SHARD_COUNT_MISMATCH:{slug}')
  shard_rows.extend(rows); shard_ids.extend(str(x.get('id') or '') for x in rows)
 shard_ids=sorted(shard_ids); search_ids=sorted(str(x.get('id') or '') for x in search.get('items',[])); manifest_ids=sorted(str(x) for x in manifest.get('ids',[]))
 if manifest.get('total')!=len(shard_ids) or manifest.get('total')!=len(search_ids):errors.append('STATIC_COUNT_MISMATCH')
 if shard_ids!=search_ids or shard_ids!=manifest_ids:errors.append('STATIC_ID_SET_MISMATCH')
 calculated=release_id_for_rows(shard_rows)
 if release!=calculated or search.get('release_id')!=release:errors.append('STATIC_RELEASE_ID_MISMATCH')
 seo=json.loads((ROOT/'seo'/'seo-index.json').read_text(encoding='utf-8')); records=seo.get('offers',[]); seo_ids=sorted(str(x.get('id') or '') for x in records)
 if seo_ids!=shard_ids:errors.append(f'SEO_ID_SET_MISMATCH:static={len(shard_ids)}:seo={len(seo_ids)}')
 if seo.get('release_id')!=release:errors.append('SEO_RELEASE_ID_MISMATCH')
 seo_urls={str(x.get('canonical')) for x in records if x.get('canonical')}; sitemap=(ROOT/'sitemap-seo.xml').read_text(encoding='utf-8'); sitemap_urls=set(re.findall(r'<loc>(https://deal24h\.net/seo/[^<]+/)</loc>',sitemap))
 if seo_urls!=sitemap_urls:errors.append(f'SEO_SITEMAP_MISMATCH:missing={len(seo_urls-sitemap_urls)}:extra={len(sitemap_urls-seo_urls)}')
 main_sitemap=(ROOT/'sitemap.xml').read_text(encoding='utf-8'); brands_sitemap=(ROOT/'sitemap-brands.xml').read_text(encoding='utf-8'); main_urls=set(re.findall(r'<loc>(https://deal24h\.net/[^<]+/)</loc>',main_sitemap))
 if not seo_urls.issubset(main_urls):errors.append('MAIN_SITEMAP_MISSING_SEO_URL')
 for name,text in [('sitemap-seo.xml',sitemap),('sitemap.xml',main_sitemap),('sitemap-brands.xml',brands_sitemap)]:
  if f'deal24h-release:{release}' not in text:errors.append(f'SITEMAP_RELEASE_ID_MISMATCH:{name}')
 homepage=(ROOT/'index.html').read_text(encoding='utf-8')
 for marker in (f'data-release-id="{release}"',f'name="deal24h-release" content="{release}"',f'assets/style.css?v={release}',f'assets/app-home.js?v={release}'):
  if marker not in homepage:errors.append(f'HOMEPAGE_RELEASE_MARKER_MISSING:{marker}')
 html_files=list((ROOT/'seo').glob('*/index.html'))+list((ROOT/'brand').glob('*/index.html'))+[ROOT/slug/'index.html' for slug in ('fashion','electronics','beauty-personal-care','home-and-living')]
 for path in html_files:
  text=path.read_text(encoding='utf-8')
  if f'data-release-id="{release}"' not in text or f'name="deal24h-release" content="{release}"' not in text or f'/assets/style.css?v={release}' not in text:errors.append(f'HTML_RELEASE_ID_MISMATCH:{path.relative_to(ROOT)}')
 if errors:
  print('RELEASE CONSISTENCY FAILED'); [print('-',e) for e in errors[:100]]; raise SystemExit(1)
 print(f'RELEASE CONSISTENCY PASS: release_id={release} records={len(shard_ids)} seo_pages={len(seo_urls)} data_html_assets_sitemaps=same')
if __name__=='__main__':main()
