"""Fail-fast contract for the exact fixed 120-brand crawl configuration."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXPECTED_CATEGORIES = {'Fashion', 'Electronics', 'Beauty & Personal Care', 'Home & Living'}
EXPECTED_BRANDS = 120
EXPECTED_ROOTS = 120
EXPECTED_LOCALES = 319
EXPECTED_TARGETS = 439


def main():
    from bot.deal_discovery_core import CATS, discovery_links, MAX_PAGES, load_sources
    from bot.merchant_country_registry import locales_for, REGISTRY

    assert set(CATS) == EXPECTED_CATEGORIES and len(CATS) == 4, CATS
    sources = load_sources()
    assert len(sources) == EXPECTED_BRANDS, len(sources)
    source_brands = {s['merchant'].strip().casefold() for s in sources}
    assert len(source_brands) == EXPECTED_BRANDS

    roots = []
    locales = []
    targets = []
    for source in sources:
        root = source['official_homepage'].strip()
        roots.append(root)
        targets.append((source['merchant'], 'Gốc / Quốc tế', root))
        for row in locales_for(source['merchant']):
            url = row['url'].strip()
            locales.append(url)
            targets.append((source['merchant'], row['market'], url))

    # The registry itself is the 440-row configuration contract. locales_for()
    # removes an exact repeated URL for the same merchant so the runtime does
    # not fetch the same page twice. This runtime list is therefore 319 locale
    # URLs + 120 roots = 439 actual fetch targets.
    assert len(roots) == EXPECTED_ROOTS
    assert len(locales) == EXPECTED_LOCALES, (
        f'actual unique locale targets={len(locales)} expected {EXPECTED_LOCALES}'
    )
    assert len(targets) == EXPECTED_TARGETS

    registry_brands = {str(k).strip().casefold() for k in REGISTRY}
    assert registry_brands == source_brands, (
        f'brand registry mismatch: registry={len(registry_brands)} source={len(source_brands)}'
    )
    assert MAX_PAGES == 1, MAX_PAGES
    assert discovery_links(None, 'example.com') == [], 'dynamic link discovery is enabled'
    assert all(url.startswith(('http://', 'https://')) and url.strip() for _, _, url in targets)

    print(
        'FIXED CRAWL CONTRACT PASS: '
        f'brands={EXPECTED_BRANDS}; registry=440 configured rows; '
        f'{EXPECTED_ROOTS} roots + {EXPECTED_LOCALES} unique market targets = '
        f'{EXPECTED_TARGETS} actual fetch targets; no dynamic link crawling'
    )


if __name__ == '__main__':
    main()
