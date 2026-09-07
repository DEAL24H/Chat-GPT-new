"""Canonical SEO market classification used by downstream SEO rendering.

The crawl/publish pipeline supplies the market value. This module only normalizes
that already-supplied value; it does not guess a country from a URL or merchant.
"""
import re

GLOBAL_VALUES = {
    "international", "global", "worldwide", "all countries", "all markets",
    "global/international", "international/global", "worldwide/international",
}


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def classify_market(value):
    raw = _clean(value)
    if not raw:
        return {"scope": "unspecified", "countries": [], "label": "Market not specified"}
    if raw.casefold() in GLOBAL_VALUES:
        return {"scope": "global", "countries": [], "label": "Applies internationally"}

    parts = [p.strip() for p in re.split(r"\s*(?:,|;|\||/|&|\band\b)\s*", raw, flags=re.I) if p.strip()]
    countries = []
    for part in parts:
        if part.casefold() in GLOBAL_VALUES:
            return {"scope": "global", "countries": [], "label": "Applies internationally"}
        if part not in countries:
            countries.append(part)
    if len(countries) == 1:
        label = f"Only available in {countries[0]}"
    else:
        label = "Only available in " + ", ".join(countries)
    return {"scope": "country_specific", "countries": countries, "label": label}


def market_info(item):
    """Use the canonical upstream country/market field without inventing scope."""
    return classify_market(item.get("country") or item.get("market_scope") or "")
