"""Build verified merchant locale destinations from first-party locale evidence.

No country URL is guessed. A locale is recorded only when the merchant's own
page exposes it through hreflang, an explicit country/region link, or a
country-coded official hostname/path that is itself linked from the merchant.
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from bot.site_adapters import SiteAdapterClient

ROOT = Path(__file__).resolve().parents[1]
SELECTION = ROOT / "data/assistant_verified_source_selection.json"
OUT = ROOT / "data/merchant_regions.json"
WORKERS = 12
TIMEOUT = 15

ISO2 = set("""
AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW
""".split())

COUNTRY_PATH_RE = re.compile(r"^/([a-z]{2})(?:/|$)", re.I)
COUNTRY_SUBDOMAIN_RE = re.compile(r"^([a-z]{2})\.", re.I)
LANG_REGION_RE = re.compile(r"^[a-z]{2,3}-([a-z]{2})$", re.I)
CC_TLD = {
    ".co.uk": "GB", ".com.au": "AU", ".co.nz": "NZ", ".co.jp": "JP",
    ".co.kr": "KR", ".com.br": "BR", ".com.mx": "MX", ".com.tr": "TR",
    ".com.sg": "SG", ".com.my": "MY", ".com.tw": "TW", ".com.hk": "HK",
    ".co.in": "IN", ".co.za": "ZA", ".com.cn": "CN", ".com.ar": "AR",
    ".com.ua": "UA", ".com.vn": "VN", ".fr": "FR", ".de": "DE", ".es": "ES",
    ".it": "IT", ".nl": "NL", ".be": "BE", ".at": "AT", ".ch": "CH",
    ".ca": "CA", ".dk": "DK", ".se": "SE", ".no": "NO", ".fi": "FI",
    ".pl": "PL", ".pt": "PT", ".gr": "GR", ".ie": "IE", ".cz": "CZ",
    ".ro": "RO", ".hu": "HU", ".nz": "NZ", ".au": "AU", ".jp": "JP",
}


def host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def same_domain(url: str, domain: str) -> bool:
    h = host(url)
    d = domain.lower().removeprefix("www.")
    return bool(h and d and (h == d or h.endswith("." + d)))


def code_from_url(url: str) -> str:
    h = host(url)
    m = COUNTRY_SUBDOMAIN_RE.match(h)
    if m and m.group(1).upper() in ISO2:
        return m.group(1).upper()
    p = urlparse(url).path
    m = COUNTRY_PATH_RE.match(p)
    if m and m.group(1).upper() in ISO2:
        return m.group(1).upper()
    for suffix, code in sorted(CC_TLD.items(), key=lambda x: -len(x[0])):
        if h.endswith(suffix):
            return code
    return ""


def code_from_hreflang(value: str) -> str:
    m = LANG_REGION_RE.match(value.strip())
    if m and m.group(1).upper() in ISO2:
        return m.group(1).upper()
    return ""


def explicit_country_code(text: str) -> str:
    # Conservative labels commonly exposed by first-party country selectors.
    labels = {
        "united states": "US", "usa": "US", "canada": "CA", "united kingdom": "GB",
        "uk": "GB", "australia": "AU", "new zealand": "NZ", "japan": "JP",
        "china": "CN", "hong kong": "HK", "taiwan": "TW", "south korea": "KR",
        "korea": "KR", "singapore": "SG", "india": "IN", "germany": "DE",
        "france": "FR", "italy": "IT", "spain": "ES", "portugal": "PT",
        "netherlands": "NL", "belgium": "BE", "switzerland": "CH", "austria": "AT",
        "denmark": "DK", "sweden": "SE", "norway": "NO", "finland": "FI",
        "poland": "PL", "ireland": "IE", "mexico": "MX", "brazil": "BR",
        "argentina": "AR", "chile": "CL", "colombia": "CO", "peru": "PE",
        "united arab emirates": "AE", "saudi arabia": "SA", "south africa": "ZA",
        "thailand": "TH", "malaysia": "MY", "indonesia": "ID", "vietnam": "VN",
        "turkey": "TR", "türkiye": "TR", "greece": "GR", "czech republic": "CZ",
        "romania": "RO", "hungary": "HU", "ukraine": "UA", "russia": "RU",
    }
    t = re.sub(r"\s+", " ", text.lower()).strip()
    for label, code in sorted(labels.items(), key=lambda x: -len(x[0])):
        if re.search(rf"\b{re.escape(label)}\b", t):
            return code
    return ""


def discover(source: dict, client: SiteAdapterClient) -> tuple[dict, list[dict], str]:
    homepage = source.get("official_homepage") or ""
    domain = source.get("domain") or host(homepage)
    response, error = client.fetch(homepage, domain, {
        "User-Agent": "Deal24H/8.0 (+https://deal24h.net/ official locale verifier)",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    })
    if not response:
        return source, [], error

    soup = BeautifulSoup(response.text, "html.parser")
    found: dict[str, dict] = {}

    def add(code: str, url: str, evidence: str, locale: str = ""):
        code = code.upper().strip()
        if code not in ISO2 or not url or not same_domain(url, domain):
            return
        url = url.split("#", 1)[0]
        if url == homepage.rstrip("/"):
            return
        key = (code, url)
        found[key] = {
            "country_code": code,
            "locale": locale or code.lower(),
            "url": url,
            "evidence": evidence,
            "verified_on": response.url,
        }

    for link in soup.find_all("link", href=True):
        rel = {str(x).lower() for x in link.get("rel", [])}
        if "alternate" not in rel or not link.get("hreflang"):
            continue
        code = code_from_hreflang(str(link.get("hreflang")))
        if code:
            add(code, link.get("href"), "hreflang", str(link.get("hreflang")))

    for a in soup.find_all("a", href=True):
        url = a.get("href")
        if not str(url).startswith(("http://", "https://", "/")):
            continue
        if str(url).startswith("/"):
            from urllib.parse import urljoin
            url = urljoin(response.url, url)
        if not same_domain(url, domain):
            continue
        text = " ".join(a.stripped_strings)
        code = explicit_country_code(text)
        if code:
            add(code, url, "country_selector_link", text[:120])
            continue
        code = code_from_url(url)
        if code and re.search(r"\b(?:country|region|language|location|international|global)\b", text, re.I):
            add(code, url, "locale_link", text[:120])

    # Some official stores expose country-specific hosts in their global selector.
    for a in soup.find_all("a", href=True):
        url = a.get("href")
        if not str(url).startswith(("http://", "https://")) or not same_domain(url, domain):
            continue
        code = code_from_url(url)
        text = " ".join(a.stripped_strings)
        if code and explicit_country_code(text) == code:
            add(code, url, "country_link", text[:120])

    rows = sorted(found.values(), key=lambda x: (x["country_code"], x["url"]))
    return source, rows, ""


def main() -> None:
    selection = json.loads(SELECTION.read_text(encoding="utf-8"))
    sources = selection.get("sources", [])
    if selection.get("total") != 120 or len(sources) != 120:
        raise SystemExit("LOCALE DISCOVERY CONTRACT FAILED: expected 120 verified sources")

    client = SiteAdapterClient(timeout=TIMEOUT, retries=2)
    brands = {}
    errors = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(discover, s, client) for s in sources]
        for future in as_completed(futures):
            source, rows, error = future.result()
            merchant = source.get("merchant") or source.get("name")
            brands[merchant] = {
                "category": source.get("category"),
                "official_homepage": source.get("official_homepage"),
                "official_domain": source.get("domain") or host(source.get("official_homepage") or ""),
                "locales": rows,
                "locale_status": "verified" if rows else "no_verified_locale_exposed",
            }
            if error:
                errors.append({"merchant": merchant, "error": error})

    payload = {
        "version": 2,
        "description": "Verified regional merchant destinations discovered only from first-party locale evidence. Empty locales mean the official site did not expose a verifiable locale destination during this scan; no country URL is guessed.",
        "source_authority": "assistant_verified_manifests_plus_first_party_locale_evidence",
        "last_reviewed": __import__("datetime").date.today().isoformat(),
        "total_brands": len(brands),
        "brands_with_verified_locales": sum(bool(v["locales"]) for v in brands.values()),
        "brands": dict(sorted(brands.items())),
        "errors": errors,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("MERCHANT LOCALE DISCOVERY:", payload["total_brands"], "brands;", payload["brands_with_verified_locales"], "with verified locales")
    if len(brands) != 120:
        raise SystemExit("LOCALE DISCOVERY FAILED: incomplete 120-brand scan")


if __name__ == "__main__":
    main()
