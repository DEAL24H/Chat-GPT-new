"""DEAL24H single canonical Bot runtime."""
from __future__ import annotations
import sys
from copy import deepcopy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from bot import deal_discovery_core as deal_bot
from bot.site_adapters import SiteAdapterClient
from bot.merchant_country_registry import locales_for
_adapter=SiteAdapterClient(timeout=deal_bot.TIMEOUT,retries=deal_bot.RETRIES)
deal_bot.fetch=lambda url,domain:_adapter.fetch(url,domain,deal_bot.H)
_original_collect=deal_bot.collect
_original_extract=deal_bot.extract

def _collect_from_fixed_country_urls(source):
    locales=locales_for(source.get("merchant"))
    if not locales:
        return source,[],[f"No fixed country URL listed for {source.get('merchant')}"]
    all_items=[]; errors=[]
    for locale in locales:
        regional=deepcopy(source)
        regional["official_homepage"]=locale["url"]
        regional["country"]=locale["market"]
        regional["locale"]=locale["market"]
        _,items,locale_errors=_original_collect(regional)
        for item in items:
            item["country"]=locale["market"]
            item["locale"]=locale["market"]
            item["locale_source"]="user_provided_fixed_country_url_list"
            item["official_homepage"]=source.get("official_homepage")
            item["source_domain"]=source.get("domain")
        all_items.extend(items)
        errors.extend(locale_errors)
    return source,all_items,errors[:20]

def _extract_with_locale(response,source):
    items=_original_extract(response,source)
    country=source.get("country","International")
    for item in items:item["country"]=country
    return items

deal_bot.collect=_collect_from_fixed_country_urls
deal_bot.extract=_extract_with_locale

def main(): deal_bot.main()
if __name__=='__main__': main()
