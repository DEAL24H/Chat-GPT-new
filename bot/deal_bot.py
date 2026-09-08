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

def _collect_from_fixed_urls(source):
    targets=[{"market":"Gốc / Quốc tế","url":source["official_homepage"]}]
    targets.extend(locales_for(source.get("merchant")))
    seen=set(); all_items=[]; errors=[]
    for target in targets:
        url=target["url"]
        if url in seen: continue
        seen.add(url)
        regional=deepcopy(source)
        regional["official_homepage"]=url
        regional["country"]=target["market"]
        regional["locale"]=target["market"]
        _,items,locale_errors=_original_collect(regional)
        for item in items:
            item["country"]=target["market"]
            item["locale"]=target["market"]
            item["locale_source"]="user_provided_fixed_country_url_list" if target["market"] != "Gốc / Quốc tế" else "catalog_root_url"
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

deal_bot.collect=_collect_from_fixed_urls
deal_bot.extract=_extract_with_locale

def main(): deal_bot.main()
if __name__=='__main__': main()
