"""Run the canonical deal bot with browser adapters and verified locales."""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot import deal_bot
from bot.site_adapters import SiteAdapterClient

REGIONS = ROOT / "data/merchant_regions.json"
_adapter = SiteAdapterClient(timeout=deal_bot.TIMEOUT, retries=deal_bot.RETRIES)
deal_bot.fetch = lambda url, domain: _adapter.fetch(url, domain, deal_bot.H)

_original_collect = deal_bot.collect
_original_extract = deal_bot.extract


def _locale_rows():
    if not REGIONS.exists():
        return {}
    data = json.loads(REGIONS.read_text(encoding="utf-8"))
    return data.get("brands", {})


def _collect_with_verified_locales(source):
    brands = _locale_rows()
    entry = brands.get(source.get("merchant"), {})
    locales = entry.get("locales") or []
    if not locales:
        return _original_collect(source)

    all_items = []
    errors = []
    # Locale URLs are supplied only by the verified merchant locale registry.
    # Keep canonical merchant/domain identity unchanged; only crawl destination
    # and resulting country/locale are varied.
    for locale in locales:
        regional = deepcopy(source)
        regional["official_homepage"] = locale["url"]
        regional["country"] = locale["country_code"]
        _, items, locale_errors = _original_collect(regional)
        for item in items:
            item["country"] = locale["country_code"]
            item["locale"] = locale.get("locale", locale["country_code"].lower())
            item["locale_source"] = locale["evidence"]
        all_items.extend(items)
        errors.extend(locale_errors)
    return source, all_items, errors[:20]


def _extract_with_locale(response, source):
    items = _original_extract(response, source)
    country = source.get("country", "International")
    for item in items:
        item["country"] = country
    return items


deal_bot.collect = _collect_with_verified_locales
deal_bot.extract = _extract_with_locale


def main() -> None:
    deal_bot.main()


if __name__ == "__main__":
    main()
