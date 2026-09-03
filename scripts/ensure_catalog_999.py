import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "brand_catalog.json"
TARGET = 534
CATEGORY_TARGETS = {"Fashion": 89, "Beauty": 89, "Consumer": 89, "Home & Living": 89, "Food & Grocery": 89, "Travel & Hotels": 89}

# Additional high-demand brands used only when the existing verified catalog is short.
# New additions are SEO-only until their official domain is verified by the collector.
FALLBACK_NAMES = {
"Beauty": """L'Oréal|Maybelline|Sephora|Ulta Beauty|MAC Cosmetics|Estée Lauder|Clinique|Lancôme|Kiehl's|CeraVe|Neutrogena|La Roche-Posay|The Ordinary|Paula's Choice|COSRX|Laneige|SK-II|Shiseido|Tatcha|Fenty Beauty|Rare Beauty|Charlotte Tilbury|NARS|Benefit Cosmetics|NYX Professional Makeup|e.l.f. Cosmetics|Revlon|Covergirl|Olay|Dove Beauty|Aveeno|Cetaphil|Bioderma|Vichy|Avène|Eucerin|The Body Shop|Bath & Body Works|Lush|Rituals|Morphe|ColourPop|Anastasia Beverly Hills|Huda Beauty|Too Faced|Urban Decay|Bobbi Brown|Smashbox|Glossier|Drunk Elephant|Sunday Riley|SkinCeuticals|Youth To The People|First Aid Beauty|Supergoop!|Olaplex|Dyson Beauty|GHD|T3 Micro|Kérastase|Redken|Moroccanoil|Briogeo|Amika|Living Proof|Ouai|The Inkey List|Good Molecules|Glow Recipe|Hero Cosmetics|Farmacy|Peter Thomas Roth|Origins|Fresh|Dermalogica|Murad|StriVectin|Milk Makeup|Kosas|Ilia|Saie|Tower 28|Pat McGrath Labs|Hourglass|Vaseline|Aquaphor|Nivea|Hawaiian Tropic""".split("|"),
"Consumer": """Apple|Samsung|Sony|LG|Dell|HP|Lenovo|ASUS|Acer|Microsoft|Xbox|PlayStation|Nintendo|Best Buy|Newegg|B&H Photo Video|Micro Center|Adorama|GameStop|Target|Costco|Amazon|eBay|AliExpress|Walmart|Wayfair|QVC|Kohl's|Macy's|Nordstrom|JCPenney|Home Depot|Lowe's|IKEA|Harbor Freight|Staples|Office Depot|Epson|Canon|Nikon|GoPro|DJI|Bose|JBL|Sennheiser|Sonos|Beats|Anker|Belkin|Logitech|Razer|Corsair|SteelSeries|ASRock|MSI|Gigabyte|Intel|AMD|NVIDIA|Google Store|OnePlus|Motorola|Nothing|Garmin|Fitbit|Ring|Blink|Arlo|Roku|Chromecast|Amazon Fire TV|Meta Quest|Valve|Steam|Epic Games Store|Etsy|Temu|Overstock|Back Market|Swappa|Framework|iFixit|Crutchfield|T-Mobile|Verizon|AT&T|Refurbished Apple|Newegg Business|Best Buy Outlet""".split("|"),
"Home & Living": """IKEA|Wayfair|Home Depot|Lowe's|Pottery Barn|West Elm|Williams Sonoma|Crate & Barrel|CB2|RH|Restoration Hardware|Ashley|Rooms To Go|La-Z-Boy|Article|Overstock|Houzz|Bed Bath & Beyond|Kirkland's|At Home|World Market|The Container Store|Lamps Plus|Lulu and Georgia|Ruggable|Brooklinen|Parachute|Purple|Casper|Saatva|Tuft & Needle|Nectar|Sleep Number|Tempur-Pedic|Beautyrest|Serta|Sealy|Leesa|Avocado|Allswell|Boll & Branch|Coyuchi|The Company Store|Frontgate|Grandin Road|Ballard Designs|Joss & Main|Birch Lane|Mercury Row|AllModern|Walmart Home|Target Home|Costco Home|Amazon Home|QVC Home|Macy's Home|Nordstrom Home|Kohl's Home|Martha Stewart|BHG|Lands' End Home|The Citizenry|Serena & Lily|Parachute Home|Schoolhouse|Article Home|Floyd|Burrow|Joybird|Castlery|Poly & Bark|Inside Weather|Burke Decor|Chairish|1stDibs|Etsy Home|HAY|Design Within Reach|Herman Miller|Steelcase|Knoll|Vitra|Yeti|Hydro Flask|Stanley|Ninja Kitchen|KitchenAid|Cuisinart|Vitamix|Breville|Keurig|Nespresso|Le Creuset|Lodge Cast Iron|Dyson Home|Shark|Bissell|Roomba|Weber|Traeger|Solo Stove|Wyze|Philips Hue|Ring Home|Blink Home""".split("|"),
"Food & Grocery": """McDonald's|Starbucks|KFC|Subway|Domino's|Pizza Hut|Burger King|Taco Bell|Wendy's|Chipotle|Dunkin'|Panera Bread|Popeyes|Panda Express|Papa Johns|Little Caesars|Jack in the Box|Five Guys|Tim Hortons|Pret A Manger|Costa Coffee|Krispy Kreme|Baskin-Robbins|Dairy Queen|GNC|iHerb|Thrive Market|HelloFresh|Blue Apron|Instacart|Walmart Grocery|Target Grocery|Whole Foods Market|Trader Joe's|Aldi|Lidl|Carrefour|Tesco|Sainsbury's|Waitrose|Morrisons|Ocado|Iceland Foods|Marks & Spencer Food|Kroger|Publix|Safeway|Albertsons|H-E-B|Meijer|Giant Food|Stop & Shop|Wegmans|Food Lion|Sprouts Farmers Market|FreshDirect|Misfits Market|Hungryroot|EveryPlate|Factor|Daily Harvest|Omaha Steaks|Harry & David|Goldbelly|Myprotein|The Vitamin Shoppe|Vitamin Shoppe|Swanson Vitamins|Vitacost|Nature Made|Ritual|Care/of|Thrive Causemetics|Naked Wines|Wine.com|Total Wine & More|Drizly|Fresh Market|Gopuff|DoorDash|Uber Eats|Grubhub|Postmates|Deliveroo|Just Eat|HelloFresh Market|Eatfit|Too Good To Go""".split("|"),
"Travel & Hotels": """Booking.com|Expedia|Hotels.com|Agoda|Trip.com|Priceline|Kayak|Skyscanner|Travelocity|Orbitz|Vrbo|Airbnb|Hostelworld|TUI|Tripadvisor|Klook|GetYourGuide|Viator|Omio|Rome2Rio|Trainline|Amtrak|Greyhound|FlixBus|Southwest Airlines|Delta Air Lines|United Airlines|American Airlines|JetBlue|Alaska Airlines|Air Canada|British Airways|Virgin Atlantic|Lufthansa|Air France|KLM|Emirates|Qatar Airways|Etihad Airways|Singapore Airlines|Cathay Pacific|ANA|Japan Airlines|Qantas|Ryanair|easyJet|Iberia|Turkish Airlines|Marriott|Hilton|Hyatt|IHG Hotels & Resorts|Accor|Wyndham Hotels|Radisson Hotels|Best Western|Choice Hotels|Motel 6|Travelodge|Premier Inn|Holiday Inn|Crowne Plaza|InterContinental|Novotel|Pullman Hotels|Sofitel|Fairmont|Four Seasons|Shangri-La|Mandarin Oriental|Ritz-Carlton|W Hotels|Westin|Sheraton|Courtyard by Marriott|Residence Inn|Homewood Suites|Hampton by Hilton|DoubleTree by Hilton|Embassy Suites|Meliá Hotels|NH Hotels|Barceló Hotel Group|Club Med|Hyatt Place|Hilton Garden Inn|Hampton Inn|La Quinta|Comfort Inn|Comfort Suites|Ramada|Days Inn|Super 8|Extended Stay America|The Venetian|Caesars|MGM Resorts|Universal Orlando|Disney Hotels|Six Flags""".split("|")
}

def clean_name(value):
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    return value if 2 <= len(value) <= 80 and re.search(r"[A-Za-z]", value) else ""

def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")

def load_current():
    try:
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
        return data.get("categories", {}) if isinstance(data, dict) else {}
    except Exception:
        return {}

def main():
    current = load_current()
    out = {category: [] for category in CATEGORY_TARGETS}
    seen = set()

    for category, entries in current.items():
        if category not in out or not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("placeholder"):
                continue
            name = clean_name(entry.get("name")); domain = str(entry.get("domain") or "").strip().lower().removeprefix("www.")
            key = name.casefold()
            if not name or key in seen or len(out[category]) >= 89:
                continue
            seen.add(key)
            item = dict(entry); item["name"] = name; item["domain"] = domain; item["enabled"] = True
            item.pop("placeholder", None)
            out[category].append(item)

    for category, names in FALLBACK_NAMES.items():
        for name in names:
            if len(out[category]) >= 89:
                break
            name = clean_name(name); key = name.casefold()
            if not name or key in seen:
                continue
            seen.add(key)
            out[category].append({"name": name, "domain": "", "enabled": True, "seo_only": True, "catalog_status": "priority_brand_pending_domain", "slug": slug(name)})

    missing = [f"{c}={89-len(out[c])}" for c in CATEGORY_TARGETS if len(out[c]) != 89]
    if missing:
        raise RuntimeError("CATALOG BUILD FAILED: not enough unique real brands: " + ", ".join(missing))
    if sum(len(v) for v in out.values()) != TARGET:
        raise RuntimeError("CATALOG BUILD FAILED: expected 534 brands")
    CATALOG.write_text(json.dumps({"categories": out}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("CATALOG READY: 6 priority categories x 89 real brands = 534; SEO-only additions are marked pending-domain")

if __name__ == "__main__":
    main()
