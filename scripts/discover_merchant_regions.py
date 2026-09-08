"""Discover and independently verify first-party country sales destinations for all 120 merchants.

A country/locale is written only when the merchant itself exposes the destination
and that destination can be reached on the official merchant domain with a
commercial/shopping page. No country URL is guessed and no locale is created
just because a country exists in the ISO list.
"""
from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bot.site_adapters import SiteAdapterClient

SELECTION = ROOT / "data/assistant_verified_source_selection.json"
OUT = ROOT / "data/merchant_regions.json"
WORKERS = 12
TIMEOUT = 15
ISO2 = set("AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW".split())
COUNTRY_PATH_RE = re.compile(r"^/([a-z]{2})(?:/|$)", re.I)
COUNTRY_SUBDOMAIN_RE = re.compile(r"^([a-z]{2})\.", re.I)
LANG_REGION_RE = re.compile(r"^[a-z]{2,3}-([a-z]{2})$", re.I)
CC_TLD = {".co.uk":"GB",".com.au":"AU",".co.nz":"NZ",".co.jp":"JP",".co.kr":"KR",".com.br":"BR",".com.mx":"MX",".com.tr":"TR",".com.sg":"SG",".com.my":"MY",".com.tw":"TW",".com.hk":"HK",".co.in":"IN",".co.za":"ZA",".com.cn":"CN",".com.ar":"AR",".com.ua":"UA",".com.vn":"VN",".fr":"FR",".de":"DE",".es":"ES",".it":"IT",".nl":"NL",".be":"BE",".at":"AT",".ch":"CH",".ca":"CA",".dk":"DK",".se":"SE",".no":"NO",".fi":"FI",".pl":"PL",".pt":"PT",".gr":"GR",".ie":"IE",".cz":"CZ",".ro":"RO",".hu":"HU",".nz":"NZ",".au":"AU",".jp":"JP"}
COUNTRY_LABELS = {"united states":"US","usa":"US","canada":"CA","united kingdom":"GB","uk":"GB","australia":"AU","new zealand":"NZ","japan":"JP","china":"CN","hong kong":"HK","taiwan":"TW","south korea":"KR","korea":"KR","singapore":"SG","india":"IN","germany":"DE","france":"FR","italy":"IT","spain":"ES","portugal":"PT","netherlands":"NL","belgium":"BE","switzerland":"CH","austria":"AT","denmark":"DK","sweden":"SE","norway":"NO","finland":"FI","poland":"PL","ireland":"IE","mexico":"MX","brazil":"BR","argentina":"AR","chile":"CL","colombia":"CO","peru":"PE","united arab emirates":"AE","saudi arabia":"SA","south africa":"ZA","thailand":"TH","malaysia":"MY","indonesia":"ID","vietnam":"VN","turkey":"TR","türkiye":"TR","greece":"GR","czech republic":"CZ","romania":"RO","hungary":"HU","ukraine":"UA","russia":"RU"}
# Deliberately exclude generic words such as "shop", "store", and "sale".
# A locale passes only with direct commerce evidence or Product/Offer JSON-LD.
DIRECT_SALES_TERMS = re.compile(r"(?:add to (?:bag|cart)|add-to-cart|buy now|shopping cart|checkout|select size|in stock|sku|product(?:s)?\b.{0,80}\b(?:price|\$|€|£)|(?:price|\$|€|£).{0,80}\bproduct)", re.I | re.S)

def host(url): return (urlparse(url).hostname or "").lower().removeprefix("www.")
def same_domain(url, domain):
    h,d=host(url),domain.lower().removeprefix("www."); return bool(h and d and (h==d or h.endswith("."+d)))
def code_from_url(url):
    h=host(url); m=COUNTRY_SUBDOMAIN_RE.match(h)
    if m and m.group(1).upper() in ISO2:return m.group(1).upper()
    m=COUNTRY_PATH_RE.match(urlparse(url).path)
    if m and m.group(1).upper() in ISO2:return m.group(1).upper()
    for suffix,code in sorted(CC_TLD.items(),key=lambda x:-len(x[0])):
        if h.endswith(suffix):return code
    return ""
def code_from_hreflang(value):
    m=LANG_REGION_RE.match(value.strip()); return m.group(1).upper() if m and m.group(1).upper() in ISO2 else ""
def explicit_country_code(text):
    t=re.sub(r"\s+"," ",text.lower()).strip()
    for label,code in sorted(COUNTRY_LABELS.items(),key=lambda x:-len(x[0])):
        if re.search(rf"\b{re.escape(label)}\b",t):return code
    return ""

def discover(source,client):
    homepage=source.get("official_homepage") or ""; domain=source.get("domain") or host(homepage)
    response,error=client.fetch(homepage,domain,{"User-Agent":"Deal24H/8.0 (+https://deal24h.net/ official locale verifier)","Accept":"text/html,application/xhtml+xml","Accept-Language":"en-US,en;q=0.9"})
    if not response:return source,[],{"stage":"homepage","error":error}
    soup=BeautifulSoup(response.text,"html.parser");found={}
    def add(code,url,evidence,locale=""):
        code=code.upper().strip()
        if code not in ISO2 or not url or not same_domain(url,domain):return
        url=url.split("#",1)[0]
        if url.rstrip("/")==homepage.rstrip("/"):return
        found[(code,url)]={"country_code":code,"locale":locale or code.lower(),"url":url,"evidence":evidence,"discovered_from":response.url}
    for link in soup.find_all("link",href=True):
        rel={str(x).lower() for x in link.get("rel",[])}
        if "alternate" in rel and link.get("hreflang"):
            code=code_from_hreflang(str(link.get("hreflang")))
            if code:add(code,urljoin(response.url,link["href"]),"hreflang",str(link["hreflang"]))
    for a in soup.find_all("a",href=True):
        raw=str(a.get("href"))
        if not raw.startswith(("http://","https://","/")):continue
        url=urljoin(response.url,raw)
        if not same_domain(url,domain):continue
        text=" ".join(a.stripped_strings); code=explicit_country_code(text)
        if code:add(code,url,"country_selector_link",text[:120])
        else:
            code=code_from_url(url)
            if code and re.search(r"\b(?:country|region|language|location|international|global)\b",text,re.I):add(code,url,"locale_link",text[:120])
        code=code_from_url(url)
        if code and explicit_country_code(text)==code:add(code,url,"country_link",text[:120])
    return source,list(found.values()),None

def verify_locale(row,source,client):
    domain=source.get("domain") or host(source.get("official_homepage") or "")
    response,error=client.fetch(row["url"],domain,{"User-Agent":"Deal24H/8.0 (+https://deal24h.net/ official locale verifier)","Accept":"text/html,application/xhtml+xml","Accept-Language":"en-US,en;q=0.9"})
    if not response:return None,{"url":row["url"],"reason":error or "unreachable"}
    if response.status_code>=400 or not same_domain(response.url,domain):return None,{"url":row["url"],"reason":f"HTTP_{response.status_code}_or_non_official_redirect","final_url":response.url}
    soup=BeautifulSoup(response.text,"html.parser"); visible=soup.get_text(" ",strip=True)
    jsonld_text=" ".join(x.get_text(" ",strip=True) for x in soup.find_all("script",type=re.compile(r"ld\+json",re.I)))
    product_json=bool(re.search(r'"(?:@type"\s*:\s*"(?:Product|Offer)|Product|offers|priceCurrency|price)"',jsonld_text,re.I))
    direct_sales=bool(DIRECT_SALES_TERMS.search(visible))
    if not (direct_sales or product_json):
        return None,{"url":row["url"],"reason":"locale_page_not_verified_as_direct_sales_destination","final_url":response.url}
    verified=dict(row);verified.update({"verification_status":"verified_live_sales_destination","verified_url":response.url,"status_code":response.status_code,"sales_page_evidence":"direct_commerce_content_or_product_offer_jsonld","verified_on":date.today().isoformat()});return verified,None

def main():
    selection=json.loads(SELECTION.read_text(encoding="utf-8"));sources=selection.get("sources",[])
    if selection.get("total")!=120 or len(sources)!=120:raise SystemExit("LOCALE VERIFICATION CONTRACT FAILED: expected 120 verified sources")
    client=SiteAdapterClient(timeout=TIMEOUT,retries=2);errors=[];rejected=[];discovered=[]
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures=[pool.submit(discover,s,client) for s in sources]
        for f in as_completed(futures):
            source,rows,err=f.result();discovered.append((source,rows));merchant=source.get("merchant") or source.get("name")
            if err:errors.append({"merchant":merchant,**err})
    verified_by_merchant={};jobs=[]
    for source,rows in discovered:
        merchant=source.get("merchant") or source.get("name");verified_by_merchant[merchant]=[]
        jobs.extend((merchant,source,row) for row in rows)
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures={pool.submit(verify_locale,row,source,client):(merchant,row) for merchant,source,row in jobs}
        for f in as_completed(futures):
            merchant,row=futures[f]
            try:verified,reject=f.result()
            except Exception as exc:verified,reject=None,{"url":row["url"],"reason":type(exc).__name__}
            if verified:verified_by_merchant[merchant].append(verified)
            elif reject:rejected.append({"merchant":merchant,**reject})
    brands={}
    for source,_ in discovered:
        merchant=source.get("merchant") or source.get("name");rows=sorted(verified_by_merchant.get(merchant,[]),key=lambda x:(x["country_code"],x["url"]))
        brands[merchant]={"category":source.get("category"),"official_homepage":source.get("official_homepage"),"official_domain":source.get("domain") or host(source.get("official_homepage") or ""),"locales":rows,"locale_status":"verified" if rows else "no_verified_sales_locale_exposed"}
    payload={"version":3,"description":"First-party country sales destinations independently verified for all 120 catalog merchants. Only live official-domain commercial destinations are retained. No country URL is guessed.","source_authority":"assistant_verified_manifests_plus_first_party_locale_evidence","verification_method":"live_official_domain_and_commercial_sales_page_check","last_reviewed":date.today().isoformat(),"total_brands":len(brands),"brands_audited":len(brands),"brands_with_verified_locales":sum(bool(v["locales"]) for v in brands.values()),"discovered_locale_candidates":sum(len(rows) for _,rows in discovered),"verified_locale_destinations":sum(len(v["locales"]) for v in brands.values()),"rejected_locale_candidates":len(rejected),"brands":dict(sorted(brands.items())),"errors":errors,"rejected":rejected}
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("LOCALE AUDIT:",payload["brands_audited"],"/ 120 brands audited")
    print("LOCALE CANDIDATES:",payload["discovered_locale_candidates"])
    print("VERIFIED LIVE SALES DESTINATIONS:",payload["verified_locale_destinations"])
    print("REJECTED:",payload["rejected_locale_candidates"])
    if len(brands)!=120:raise SystemExit("LOCALE VERIFICATION FAILED: incomplete 120-brand audit")

if __name__=="__main__":main()
