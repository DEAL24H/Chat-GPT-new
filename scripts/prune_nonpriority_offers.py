import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEWS = ROOT / 'data' / 'news.json'
CATALOG = ROOT / 'data' / 'brand_catalog.json'


def norm(value):
    return ' '.join(str(value or '').strip().casefold().replace('’', "'").split())


def main():
    catalog = json.loads(CATALOG.read_text(encoding='utf-8')).get('categories', {})
    allowed = {}
    for category, entries in catalog.items():
        for entry in entries:
            name = str(entry.get('name', '')).strip()
            if name:
                allowed[norm(name)] = (name, category)

    try:
        items = json.loads(NEWS.read_text(encoding='utf-8'))
    except Exception:
        items = []
    if not isinstance(items, list):
        items = []

    kept = []
    removed = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        merchant_key = norm(item.get('merchant') or item.get('brand'))
        hit = allowed.get(merchant_key)
        if not hit:
            removed += 1
            continue
        canonical_name, category = hit
        item['merchant'] = canonical_name
        item['category'] = category
        kept.append(item)

    NEWS.write_text(json.dumps(kept, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'PRIORITY OFFER PRUNE: allowed_brands={len(allowed)}, kept={len(kept)}, removed={removed}')


if __name__ == '__main__':
    main()
