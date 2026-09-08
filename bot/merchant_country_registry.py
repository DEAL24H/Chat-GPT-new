"""Fixed country/market URL registry supplied for the 120-brand catalog."""
from __future__ import annotations
import csv
from pathlib import Path
from urllib.parse import urlparse
ROOT=Path(__file__).resolve().parents[1]
FILES=(ROOT/"data/merchant_country_urls_fashion.csv",ROOT/"data/merchant_country_urls_electronics.csv",ROOT/"data/merchant_country_urls_beauty.csv",ROOT/"data/merchant_country_urls_home.csv")
def _host(url): return (urlparse(str(url).strip()).hostname or "").lower().removeprefix("www.")
def load_registry():
 rows=[]
 for path in FILES:
  if not path.exists(): raise RuntimeError(f"COUNTRY URL REGISTRY MISSING: {path.name}")
  with path.open("r",encoding="utf-8",newline="") as fh:
   reader=csv.DictReader(fh)
   if set(reader.fieldnames or ()) != {"brand","market","url"}: raise RuntimeError(f"COUNTRY URL REGISTRY HEADER FAILED: {path.name}")
   rows.extend(dict(r) for r in reader)
 by_brand={}
 for row in rows:
  brand=row["brand"].strip(); market=row["market"].strip(); url=row["url"].strip()
  if not brand or not market or not url or not url.startswith(("http://","https://")): raise RuntimeError(f"COUNTRY URL REGISTRY ROW FAILED: {row!r}")
  by_brand.setdefault(brand,[]).append(row)
 if len(by_brand)!=120: raise RuntimeError(f"COUNTRY URL REGISTRY BRAND COUNT FAILED: {len(by_brand)} != 120")
 return by_brand
REGISTRY=load_registry()
def locales_for(merchant):
 seen=set(); result=[]
 for row in REGISTRY.get(str(merchant).strip(),()):
  if row["market"].strip().lower().startswith("gốc"): continue
  if row["url"] in seen: continue
  seen.add(row["url"]); result.append(row)
 return result
def allowed_hosts_for(merchant): return {_host(r["url"]) for r in locales_for(merchant) if _host(r["url"])}
