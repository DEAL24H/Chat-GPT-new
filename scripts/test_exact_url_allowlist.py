import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main():
    manifest = json.loads((ROOT / 'data/allowed_brand_urls.json').read_text(encoding='utf-8'))
    assert manifest['mode'] == 'root_and_verified_promo_allowlist'
    assert manifest['allow_discovery'] is False
    assert manifest['allow_redirect_source_expansion'] is False
    assert manifest['total_brands'] == 120
    assert manifest['total_brands'] == 120
    assert len(manifest['entries']) == manifest['total_urls']

    from bot import deal_bot
    sources = deal_bot.load_sources()
    assert len(sources) == manifest['total_urls']
    assert all(not source.get('allow_discovery') for source in sources)
    assert all(not source.get('allow_internal_discovery') for source in sources)
    assert all(len(source.get('url_allowlist', [])) == 1 for source in sources)

    source = sources[0]
    fake_response = type('Response', (), {'text': '<html><body>No offer here</body></html>', 'url': source['official_homepage']})()
    with patch.object(deal_bot, 'fetch', return_value=(fake_response, '')):
        with patch.object(deal_bot, 'discovery_links', return_value=[]):
            result = deal_bot.collect(source)
    assert result[0] is source
    assert result[2] == []
    assert len({source['merchant'] for source in sources}) == 120
    print(f"ROOT+VERIFIED ALLOWLIST TEST PASS: 120 brands, {len(sources)} URLs, discovery disabled")


if __name__ == '__main__':
    main()
