import json
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[1] / 'data' / 'brand_catalog.json'
SEEDS = {
    'Food & Grocery': [('H Mart', 'hmart.com')],
}

def main():
    data = json.loads(CATALOG.read_text(encoding='utf-8'))
    categories = data.setdefault('categories', {})
    changed = False
    for category, brands in SEEDS.items():
        entries = categories.setdefault(category, [])
        names = {str(x.get('name','')).casefold() for x in entries if isinstance(x, dict)}
        for name, domain in brands:
            if name.casefold() not in names:
                entries.append({'name': name, 'domain': domain, 'enabled': True, 'catalog_status': 'priority_verified_seed'})
                changed = True
    if changed:
        CATALOG.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('PRIORITY SEEDS READY')

if __name__ == '__main__':
    main()
