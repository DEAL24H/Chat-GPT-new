#!/usr/bin/env python3
"""Verify every catalog brand has a live, first-party source.

The catalog is kept at exactly 6 x 89 = 534 enabled brands. Missing/dead
first-party domains are resolved from a small set of explicit mappings, then
from search results. Brands whose official presence is genuinely gone are
replaced one-for-one from curated same-category replacement pools.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, quote_plus

import requests

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "brand_catalog.json"
TIMEOUT = 12
HEADERS = {"User-Agent": "DEAL24H-BrandVerifier/1.0 (+https://deal24h.pages.dev/)"}

# First-party mappings for ambiguous names/sub-brands. These are domains, not
# affiliate links, and are only accepted after a live HTTP check.
KNOWN = {
    "L'Oréal": "loreal.com", "COSRX": "cosrx.com", "Laneige": "us.laneige.com",
    "SK-II": "sk-ii.com", "Shiseido": "shiseido.com", "Tatcha": "tatcha.com",
    "NARS": "narscosmetics.com", "Revlon": "revlon.com", "Covergirl": "covergirl.com",
    "Dove Beauty": "dove.com", "Aveeno": "aveeno.com", "Cetaphil": "cetaphil.com",
    "Bioderma": "bioderma.us", "Vichy": "vichyusa.com", "Avène": "aveneusa.com",
    "Eucerin": "eucerinus.com", "The Body Shop": "thebodyshop.com", "Lush": "lush.com",
    "Rituals": "rituals.com", "ColourPop": "colourpop.com", "Anastasia Beverly Hills": "anastasiabeverlyhills.com",
    "Huda Beauty": "hudabeauty.com", "Urban Decay": "urbandecay.com", "Bobbi Brown": "bobbibrowncosmetics.com",
    "Smashbox": "smashbox.com", "Sunday Riley": "sundayriley.com", "SkinCeuticals": "skinceuticals.com",
    "Youth To The People": "youthtothepeople.com", "First Aid Beauty": "firstaidbeauty.com",
    "Supergoop!": "supergoop.com", "Olaplex": "olaplex.com", "Dyson Beauty": "dyson.com",
    "GHD": "ghdhair.com", "T3 Micro": "t3micro.com", "Kérastase": "kerastase-usa.com",
    "Redken": "redken.com", "Moroccanoil": "moroccanoil.com", "Briogeo": "briogeohair.com",
    "Amika": "loveamika.com", "Living Proof": "livingproof.com", "Ouai": "theouai.com",
    "The Inkey List": "theinkeylist.com", "Good Molecules": "goodmolecules.com", "Glow Recipe": "glowrecipe.com",
    "Hero Cosmetics": "herocosmetics.us", "Farmacy": "farmacybeauty.com", "Peter Thomas Roth": "drbrandtskincare.com",
    "Origins": "origins.com", "Fresh": "fresh.com", "Dermalogica": "dermalogica.com", "Murad": "murad.com",
    "StriVectin": "strivectin.com", "Milk Makeup": "milkmakeup.com", "Kosas": "kosas.com", "Ilia": "iliabeauty.com",
    "Saie": "saiehello.com", "Tower 28": "tower28beauty.com", "Pat McGrath Labs": "patmcgrath.com",
    "Hourglass": "hourglasscosmetics.com", "Vaseline": "vaseline.com",
    "LG": "lg.com", "ASUS": "asus.com", "Acer": "acer.com", "Microsoft": "microsoft.com", "Xbox": "xbox.com",
    "PlayStation": "playstation.com", "Nintendo": "nintendo.com", "B&H Photo Video": "bhphotovideo.com",
    "Adorama": "adorama.com", "GameStop": "gamestop.com", "AliExpress": "aliexpress.com", "QVC": "qvc.com",
    "JCPenney": "jcpenney.com", "Harbor Freight": "harborfreight.com", "Epson": "epson.com", "Canon": "usa.canon.com",
    "Nikon": "nikonusa.com", "GoPro": "gopro.com", "DJI": "dji.com", "Bose": "bose.com", "JBL": "jbl.com",
    "Sennheiser": "sennheiser.com", "Sonos": "sonos.com", "Beats": "beatsbydre.com", "Anker": "anker.com",
    "Belkin": "belkin.com", "Razer": "razer.com", "Corsair": "corsair.com", "SteelSeries": "steelseries.com",
    "ASRock": "asrock.com", "MSI": "msi.com", "Gigabyte": "gigabyte.com", "Intel": "intel.com", "AMD": "amd.com",
    "NVIDIA": "nvidia.com", "Google Store": "store.google.com", "OnePlus": "oneplus.com", "Motorola": "motorola.com",
    "Nothing": "nothing.tech", "Garmin": "garmin.com", "Fitbit": "fitbit.com", "Ring": "ring.com", "Blink": "blinkforhome.com",
    "Arlo": "arlo.com", "Roku": "roku.com", "Chromecast": "store.google.com", "Amazon Fire TV": "amazon.com",
    "Meta Quest": "meta.com", "Valve": "valvesoftware.com", "Steam": "steampowered.com", "Epic Games Store": "epicgames.com",
    "Etsy": "etsy.com", "Temu": "temu.com", "Back Market": "backmarket.com", "Swappa": "swappa.com",
    "Framework": "frame.work", "iFixit": "ifixit.com", "Crutchfield": "crutchfield.com", "T-Mobile": "t-mobile.com", "Verizon": "verizon.com",
    "Pottery Barn": "potterybarn.com", "West Elm": "westelm.com", "Williams Sonoma": "williams-sonoma.com",
    "Crate & Barrel": "crateandbarrel.com", "CB2": "cb2.com", "RH": "rh.com", "Restoration Hardware": "rh.com",
    "Ashley": "ashleyfurniture.com", "Rooms To Go": "roomstogo.com", "La-Z-Boy": "la-z-boy.com", "Article": "article.com",
    "Houzz": "houzz.com", "Kirkland's": "kirklands.com", "At Home": "athome.com", "World Market": "worldmarket.com",
    "The Container Store": "containerstore.com", "Lamps Plus": "lampsplus.com", "Lulu and Georgia": "luluandgeorgia.com",
    "Ruggable": "ruggable.com", "Brooklinen": "brooklinen.com", "Parachute": "parachutehome.com", "Purple": "purple.com",
    "Casper": "casper.com", "Saatva": "saatva.com", "Tuft & Needle": "tuftandneedle.com", "Nectar": "nectarsleep.com",
    "Sleep Number": "sleepnumber.com", "Tempur-Pedic": "tempurpedic.com", "Beautyrest": "beautyrest.com", "Serta": "serta.com",
    "Sealy": "sealy.com", "Leesa": "leesa.com", "Avocado": "avocadogreenbrands.com", "Allswell": "walmart.com",
    "Boll & Branch": "bollandbranch.com", "Coyuchi": "coyuchi.com", "The Company Store": "thecompanystore.com",
    "Frontgate": "frontgate.com", "Grandin Road": "grandinroad.com", "Ballard Designs": "ballarddesigns.com",
    "Joss & Main": "jossandmain.com", "Birch Lane": "birchlane.com", "Mercury Row": "mercuryrow.com", "AllModern": "allmodern.com",
    "Walmart Home": "walmart.com", "Target Home": "target.com", "Costco Home": "costco.com", "Amazon Home": "amazon.com",
    "QVC Home": "qvc.com", "Macy's Home": "macys.com", "Nordstrom Home": "nordstrom.com", "Kohl's Home": "kohls.com",
    "Martha Stewart": "marthastewart.com", "BHG": "bhg.com", "Lands' End Home": "landsend.com", "The Citizenry": "the-citizenry.com",
    "Serena & Lily": "serenaandlily.com", "Parachute Home": "parachutehome.com", "Schoolhouse": "schoolhouse.com",
    "Article Home": "article.com", "Floyd": "floydhome.com", "Burrow": "burrow.com", "Joybird": "joybird.com", "Castlery": "castlery.com",
    "Poly & Bark": "polyandbark.com", "Inside Weather": "insideweather.com", "Burke Decor": "burkedecor.com", "Chairish": "chairish.com",
    "1stDibs": "1stdibs.com", "Etsy Home": "etsy.com", "HAY": "hay.com", "Design Within Reach": "dwr.com",
    "Herman Miller": "hermanmiller.com", "Steelcase": "steelcase.com", "Knoll": "knoll.com", "Vitra": "vitra.com", "Yeti": "yeti.com",
    "Hydro Flask": "hydroflask.com", "Stanley": "stanley1913.com", "Ninja Kitchen": "sharkninja.com", "KitchenAid": "kitchenaid.com",
    "Cuisinart": "cuisinart.com", "Vitamix": "vitamix.com", "Breville": "breville.com", "Keurig": "keurig.com", "Nespresso": "nespresso.com",
    "Le Creuset": "lecreuset.com", "Lodge Cast Iron": "lodgecastiron.com", "Dyson Home": "dyson.com",
    "McDonald's": "mcdonalds.com", "Starbucks": "starbucks.com", "KFC": "kfc.com", "Subway": "subway.com", "Domino's": "dominos.com",
    "Pizza Hut": "pizzahut.com", "Burger King": "bk.com", "Taco Bell": "tacobell.com", "Wendy's": "wendys.com", "Chipotle": "chipotle.com",
    "Dunkin'": "dunkindonuts.com", "Panera Bread": "panerabread.com", "Popeyes": "popeyes.com", "Panda Express": "pandaexpress.com",
    "Papa Johns": "papajohns.com", "Little Caesars": "littlecaesars.com", "Jack in the Box": "jackinthebox.com", "Five Guys": "fiveguys.com",
    "Tim Hortons": "timhortons.com", "Pret A Manger": "pret.co.uk", "Costa Coffee": "costacoffee.com", "Krispy Kreme": "krispykreme.com",
    "Baskin-Robbins": "baskinrobbins.com", "Dairy Queen": "dairyqueen.com", "GNC": "gnc.com", "iHerb": "iherb.com", "Thrive Market": "thrivemarket.com",
    "HelloFresh": "hellofresh.com", "Blue Apron": "blueapron.com", "Instacart": "instacart.com", "Walmart Grocery": "walmart.com",
    "Target Grocery": "target.com", "Whole Foods Market": "wholefoodsmarket.com", "Trader Joe's": "traderjoes.com", "Aldi": "aldi.us",
    "Lidl": "lidl.com", "Carrefour": "carrefour.com", "Tesco": "tesco.com", "Sainsbury's": "sainsburys.co.uk", "Waitrose": "waitrose.com",
    "Morrisons": "morrisons.com", "Ocado": "ocado.com", "Iceland Foods": "iceland.co.uk", "Marks & Spencer Food": "marksandspencer.com",
    "Kroger": "kroger.com", "Publix": "publix.com", "Safeway": "safeway.com", "Albertsons": "albertsons.com", "H-E-B": "heb.com",
    "Meijer": "meijer.com", "Giant Food": "giantfood.com", "Stop & Shop": "stopandshop.com", "Wegmans": "wegmans.com", "Food Lion": "foodlion.com",
    "Sprouts Farmers Market": "sprouts.com", "FreshDirect": "freshdirect.com", "Misfits Market": "misfitsmarket.com", "Hungryroot": "hungryroot.com",
    "EveryPlate": "everyplate.com", "Factor": "factor75.com", "Daily Harvest": "daily-harvest.com", "Omaha Steaks": "omahasteaks.com",
    "Harry & David": "harryanddavid.com", "Goldbelly": "goldbelly.com", "Myprotein": "myprotein.com", "The Vitamin Shoppe": "vitaminshoppe.com",
    "Vitamin Shoppe": "vitaminshoppe.com", "Swanson Vitamins": "swansonvitamins.com", "Vitacost": "vitacost.com", "Nature Made": "naturemade.com",
    "Ritual": "ritual.com", "Care/of": "careof.com", "Thrive Causemetics": "thrivecausemetics.com", "Naked Wines": "nakedwines.com",
    "Wine.com": "wine.com", "Total Wine & More": "totalwine.com", "Drizly": "drizly.com", "Fresh Market": "thefreshmarket.com", "Gopuff": "gopuff.com",
    "DoorDash": "doordash.com", "Uber Eats": "ubereats.com", "Grubhub": "grubhub.com", "Postmates": "postmates.com", "Deliveroo": "deliveroo.com",
    "Just Eat": "justeat.com", "HelloFresh Market": "hellofresh.com", "Eatfit": "eatfit.com", "Too Good To Go": "toogoodtogo.com",
    "Booking.com": "booking.com", "Expedia": "expedia.com", "Hotels.com": "hotels.com", "Agoda": "agoda.com", "Trip.com": "trip.com",
    "Priceline": "priceline.com", "Kayak": "kayak.com", "Skyscanner": "skyscanner.net", "Travelocity": "travelocity.com", "Orbitz": "orbitz.com",
    "Vrbo": "vrbo.com", "Airbnb": "airbnb.com", "Hostelworld": "hostelworld.com", "TUI": "tui.com", "Tripadvisor": "tripadvisor.com",
    "Klook": "klook.com", "GetYourGuide": "getyourguide.com", "Viator": "viator.com", "Omio": "omio.com", "Rome2Rio": "rome2rio.com",
    "Trainline": "thetrainline.com", "Amtrak": "amtrak.com", "Greyhound": "greyhound.com", "FlixBus": "flixbus.com", "Southwest Airlines": "southwest.com",
    "Delta Air Lines": "delta.com", "United Airlines": "united.com", "American Airlines": "aa.com", "JetBlue": "jetblue.com", "Alaska Airlines": "alaskaair.com",
    "Air Canada": "aircanada.com", "British Airways": "britishairways.com", "Virgin Atlantic": "virginatlantic.com", "Lufthansa": "lufthansa.com",
    "Air France": "airfrance.com", "KLM": "klm.com", "Emirates": "emirates.com", "Qatar Airways": "qatarairways.com", "Etihad Airways": "etihad.com",
    "Singapore Airlines": "singaporeair.com", "Cathay Pacific": "cathaypacific.com", "ANA": "ana.co.jp", "Japan Airlines": "jal.com", "Qantas": "qantas.com",
    "Ryanair": "ryanair.com", "easyJet": "easyjet.com", "Iberia": "iberia.com", "Turkish Airlines": "turkishairlines.com", "Marriott": "marriott.com",
    "Hilton": "hilton.com", "Hyatt": "hyatt.com", "IHG Hotels & Resorts": "ihg.com", "Accor": "accor.com", "Wyndham Hotels": "wyndhamhotels.com",
    "Radisson Hotels": "radissonhotels.com", "Best Western": "bestwestern.com", "Choice Hotels": "choicehotels.com", "Motel 6": "motel6.com",
    "Travelodge": "travelodge.com", "Premier Inn": "premierinn.com", "Holiday Inn": "ihg.com", "Crowne Plaza": "ihg.com", "InterContinental": "ihg.com",
    "Novotel": "novotel.com", "Pullman Hotels": "pullmanhotels.com", "Sofitel": "sofitel.com", "Fairmont": "fairmont.com", "Four Seasons": "fourseasons.com",
    "Shangri-La": "shangri-la.com", "Mandarin Oriental": "mandarinoriental.com", "Ritz-Carlton": "ritzcarlton.com", "W Hotels": "marriott.com", "Westin": "westin.com",
    "Sheraton": "sheraton.com", "Courtyard by Marriott": "marriott.com", "Residence Inn": "marriott.com", "Homewood Suites": "hilton.com", "Hampton by Hilton": "hilton.com",
    "DoubleTree by Hilton": "hilton.com", "Embassy Suites": "hilton.com", "Meliá Hotels": "melia.com", "NH Hotels": "nh-hotels.com", "Barceló Hotel Group": "barcelo.com",
    "Club Med": "clubmed.us", "Hyatt Place": "hyatt.com", "Hilton Garden Inn": "hilton.com", "Hampton Inn": "hilton.com", "La Quinta": "wyndhamhotels.com", "Comfort Inn": "choicehotels.com",
}

# Brands known to have been discontinued/absorbed; replacements are same-category,
# established merchants with first-party commerce. The verifier will only use a
# replacement not already present in the catalog.
REPLACEMENTS = {
    "Beauty": ["Kylie Cosmetics", "Make Up For Ever", "Sigma Beauty", "Dermstore", "SkinStore"],
    "Consumer": ["TCL", "Hisense", "Vizio", "TP-Link", "Ubiquiti"],
    "Home & Living": ["Lovesac", "Cratejoy", "Home Decorators Collection", "World Market", "Ethan Allen"],
    "Food & Grocery": ["Shake Shack", "CAVA", "Sweetgreen", "Wingstop", "Jersey Mike's", "Raising Cane's", "Culver's", "Chick-fil-A", "P.F. Chang's"],
    "Travel & Hotels": ["Choice Hotels", "IHG Hotels & Resorts", "Marriott", "Hilton", "Hyatt", "Accor", "Wyndham Hotels", "Best Western"],
    "Fashion": ["J.Crew Factory", "Quince", "Gap Factory", "Express", "Banana Republic Factory"],
}

REPLACEMENT_DOMAINS = {
    "Kylie Cosmetics": "kyliecosmetics.com", "Make Up For Ever": "makeupforever.com", "Sigma Beauty": "sigmabeauty.com", "Dermstore": "dermstore.com", "SkinStore": "skinstore.com",
    "TCL": "tcl.com", "Hisense": "hisense.com", "Vizio": "vizio.com", "TP-Link": "tp-link.com", "Ubiquiti": "ui.com",
    "Lovesac": "lovesac.com", "Cratejoy": "cratejoy.com", "Home Decorators Collection": "homedepot.com", "Ethan Allen": "ethanallen.com",
    "Shake Shack": "shakeshack.com", "CAVA": "cava.com", "Sweetgreen": "sweetgreen.com", "Wingstop": "wingstop.com", "Jersey Mike's": "jerseymikes.com", "Raising Cane's": "raisingcanes.com", "Culver's": "culvers.com", "Chick-fil-A": "chick-fil-a.com", "P.F. Chang's": "pfchangs.com",
    "J.Crew Factory": "factory.jcrew.com", "Quince": "quince.com", "Gap Factory": "gapfactory.com", "Express": "express.com", "Banana Republic Factory": "bananarepublicfactory.gapfactory.com",
}


def norm_domain(value: str) -> str:
    value = (value or "").strip().lower().replace("https://", "").replace("http://", "")
    return value.split("/")[0].removeprefix("www.")


def live(domain: str) -> bool:
    if not domain:
        return False
    for scheme in ("https", "http"):
        try:
            r = requests.get(f"{scheme}://{domain}/", headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            if r.status_code >= 200 and r.status_code < 500:
                final = urlparse(r.url).netloc.lower().removeprefix("www.")
                # Refuse obvious parking/search/dead destinations.
                if final and not any(x in final for x in ("google.com", "bing.com", "duckduckgo.com")):
                    text = (r.text or "")[:400000].lower()
                    bad = ("domain for sale", "buy this domain", "this domain is parked", "404 not found")
                    if not any(x in text for x in bad):
                        return True
        except requests.RequestException:
            pass
    return False


def search_domain(name: str) -> str:
    q = quote_plus(f"{name} official website")
    urls = [f"https://www.google.com/search?q={q}", f"https://html.duckduckgo.com/html/?q={q}"]
    candidates = []
    for u in urls:
        try:
            r = requests.get(u, headers=HEADERS, timeout=TIMEOUT)
            for href in re.findall(r'https?://[^\"\s<>]+', r.text):
                host = urlparse(href).netloc.lower().removeprefix("www.")
                if host and not any(bad in host for bad in ("google.", "duckduckgo.", "facebook.", "instagram.", "wikipedia.", "youtube.", "tiktok.", "reddit.", "linkedin.", "yelp.", "pinterest.")):
                    candidates.append(host)
        except requests.RequestException:
            continue
        for host in candidates[:12]:
            if live(host):
                return host
    return ""


def main() -> int:
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    cats = data.get("categories", {})
    if set(cats) != {"Fashion", "Beauty", "Consumer", "Home & Living", "Food & Grocery", "Travel & Hotels"}:
        raise SystemExit("catalog must contain exactly six required categories")
    total = sum(len(v) for v in cats.values())
    if total != 534:
        raise SystemExit(f"catalog must start at exactly 534 entries, found {total}")

    existing_names = {str(x.get("name", "")).strip() for vals in cats.values() for x in vals}
    changed = 0
    unresolved = []
    replaced = []

    for category, vals in cats.items():
        for entry in vals:
            name = str(entry.get("name", "")).strip()
            domain = norm_domain(str(entry.get("domain", "")))
            if domain and live(domain):
                entry["domain"] = domain
                entry["catalog_status"] = "verified_first_party"
                entry.pop("seo_only", None)
                changed += 1
                continue
            candidate = norm_domain(KNOWN.get(name, ""))
            if candidate and live(candidate):
                entry["domain"] = candidate
                entry["catalog_status"] = "verified_first_party"
                entry.pop("seo_only", None)
                changed += 1
                continue
            candidate = search_domain(name)
            if candidate and live(candidate):
                entry["domain"] = candidate
                entry["catalog_status"] = "verified_first_party_search"
                entry.pop("seo_only", None)
                changed += 1
                continue
            # Do not keep a dead/non-first-party brand. Replace it one-for-one.
            pool = REPLACEMENTS.get(category, [])
            replacement = next((x for x in pool if x not in existing_names and live(REPLACEMENT_DOMAINS.get(x, ""))), None)
            if replacement:
                entry.clear()
                entry.update({"name": replacement, "domain": REPLACEMENT_DOMAINS[replacement], "enabled": True, "catalog_status": "verified_replacement"})
                existing_names.add(replacement)
                replaced.append((category, name, replacement))
                changed += 1
            else:
                unresolved.append((category, name))
            time.sleep(0.05)

    if unresolved:
        print("UNRESOLVED:")
        for x in unresolved:
            print(f"- {x[0]}: {x[1]}")
        raise SystemExit(f"unable to verify/replace {len(unresolved)} catalog brands")

    for vals in cats.values():
        vals.sort(key=lambda x: str(x.get("name", "")).lower())
    out = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    CATALOG.write_text(out, encoding="utf-8")
    print(f"Verified/updated {changed}/534 brands; replacements={len(replaced)}")
    for cat, old, new in replaced:
        print(f"REPLACED [{cat}] {old} -> {new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
