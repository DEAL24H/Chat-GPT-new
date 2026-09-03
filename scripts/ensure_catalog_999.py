import csv, io, json, re
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'data' / 'brand_catalog.json'
TARGET = 999
SOURCE = 'https://raw.githubusercontent.com/KarlAmort/english-words-names-brands-places/master/brands/brands.csv'
CATEGORIES = ['Fashion', 'Beauty', 'Gaming', 'Consumer']

def slug_domain(name):
    s = re.sub(r"[^a-z0-9]+", '', name.lower())
    return (s[:63] + '.com') if s else ''

def clean_name(name):
    name = re.sub(r'\s+', ' ', str(name or '')).strip()
    if not name or len(name) > 70 or len(name) < 2: return ''
    if not re.search(r'[A-Za-z]', name): return ''
    return name

def load_current():
    try:
        data = json.loads(CATALOG.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) and isinstance(data.get('categories'), dict) else {'categories': {}}
    except Exception:
        return {'categories': {}}

def main():
    data = load_current()
    cats = {c: list(data['categories'].get(c, [])) for c in CATEGORIES}
    seen = set()
    ordered = []
    for c in CATEGORIES:
        for item in cats[c]:
            name = clean_name(item.get('name')) if isinstance(item, dict) else ''
            if not name: continue
            key = name.casefold()
            if key in seen: continue
            seen.add(key); ordered.append((c, {'name': name, 'domain': str(item.get('domain') or slug_domain(name)).lower()}))
    print(f'Existing catalog brands: {len(ordered)}')
    if len(ordered) > TARGET:
        ordered = ordered[:TARGET]
    if len(ordered) < TARGET:
        r = requests.get(SOURCE, timeout=30, headers={'User-Agent': 'DEAL24H-catalog-builder/1.0'})
        r.raise_for_status()
        reader = csv.reader(io.StringIO(r.text))
        rows = list(reader)
        names = []
        for row in rows:
            if not row: continue
            n = clean_name(row[0])
            if n and n.casefold() not in seen: names.append(n)
        for n in names:
            if len(ordered) >= TARGET: break
            key = n.casefold()
            seen.add(key)
            c = CATEGORIES[len(ordered) % len(CATEGORIES)]
            ordered.append((c, {'name': n, 'domain': slug_domain(n)}))
    if len(ordered) != TARGET:
        raise RuntimeError(f'Unable to build exactly {TARGET} unique brands; got {len(ordered)}')
    out = {c: [] for c in CATEGORIES}
    for c, item in ordered: out[c].append(item)
    CATALOG.write_text(json.dumps({'categories': out}, ensure_ascii=False, indent=2), encoding='utf-8')
    counts = ', '.join(f'{c}={len(out[c])}' for c in CATEGORIES)
    print(f'CATALOG 999 READY: total={sum(map(len, out.values()))}; {counts}')

if __name__ == '__main__':
    main()
