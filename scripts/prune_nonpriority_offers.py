import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
NEWS = ROOT / 'data' / 'news.json'
CATALOG = ROOT / 'data' / 'brand_catalog.json'


def norm(value):
    return ' '.join(str(value or '').strip().casefold().replace('’', "'").split())


def host(value):
    return (urlparse(str(value or '')).hostname or '').lower().removeprefix('www.')


def same_domain(source_domain, destination):
    src = host(source_domain)
    dst = host(destination)
    return bool(src and dst and (dst == src or dst.endswith('.' + src)))


def main():
    catalog = json.loads(CATALOG.read_text(encoding='utf-8')).get('categories', {})
    allowed = {}
    for category, entries in catalog.items():
        for entry in entries:
            name = str(entry.get('name', '')).strip()
            domain = str(entry.get('domain', '')).strip()
            if name:
                allowed[norm(name)] = (name, category, domain)

    try:
        items = json.loads(NEWS.read_text(encoding='utf-8'))
    except Exception:
        items = []
    if not isinstance(items, list):
        items = []

    kept = []
    removed = 0
    removed_domain = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        merchant_key = norm(item.get('merchant') or item.get('brand'))
        hit = allowed.get(merchant_key)
        if not hit:
            removed += 1
            continue
        canonical_name, category, catalog_domain = hit
        item['merchant'] = canonical_name
        item['category'] = category
        destination = item.get('final_purchase_url') or item.get('promotion_url') or item.get('url') or ''
        if catalog_domain and not same_domain(catalog_domain, destination):
            removed += 1
            removed_domain += 1
            continue
        kept.append(item)

    NEWS.write_text(json.dumps(kept, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PRIORITY OFFER PRUNE: allowed_brands={len(allowed)}, kept={len(kept)}, removed={removed}, removed_wrong_catalog_domain={removed_domain}')


if __name__ == '__main__':
    main()
