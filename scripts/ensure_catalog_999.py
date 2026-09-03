import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "brand_catalog.json"
TARGET = 534
CATEGORY_TARGETS = {
    "Fashion": 89,
    "Beauty": 89,
    "Consumer": 89,
    "Home & Living": 89,
    "Food & Grocery": 89,
    "Travel & Hotels": 89,
}

FALLBACKS = {
    "Food & Grocery": [
        ("McDonald's", "mcdonalds.com"), ("Starbucks", "starbucks.com"), ("KFC", "kfc.com"),
        ("Subway", "subway.com"), ("Domino's", "dominos.com"), ("Pizza Hut", "pizzahut.com"),
        ("Burger King", "burgerking.com"), ("Taco Bell", "tacobell.com"), ("Wendy's", "wendys.com"),
        ("Chipotle", "chipotle.com"), ("Dunkin'", "dunkindonuts.com"), ("Panera Bread", "panerabread.com"),
        ("Popeyes", "popeyes.com"), ("Panda Express", "pandaexpress.com"), ("Papa Johns", "papajohns.com"),
        ("Little Caesars", "littlecaesars.com"), ("Jack in the Box", "jackinthebox.com"), ("Five Guys", "fiveguys.com"),
        ("Tim Hortons", "timhortons.com"), ("Pret A Manger", "pret.co.uk"), ("Costa Coffee", "costacoffee.com"),
        ("Krispy Kreme", "krispykreme.com"), ("Baskin-Robbins", "baskinrobbins.com"), ("Dairy Queen", "dairyqueen.com"),
        ("GNC", "gnc.com"), ("iHerb", "iherb.com"), ("Thrive Market", "thrivemarket.com"),
        ("HelloFresh", "hellofresh.com"), ("Blue Apron", "blueapron.com"), ("Instacart", "instacart.com"),
        ("Walmart Grocery", "walmart.com"), ("Target Grocery", "target.com"), ("Whole Foods Market", "wholefoodsmarket.com"),
        ("Trader Joe's", "traderjoes.com"), ("Aldi", "aldi.us"), ("Lidl", "lidl.com"),
        ("Carrefour", "carrefour.com"), ("Tesco", "tesco.com"), ("Sainsbury's", "sainsburys.co.uk"),
        ("Waitrose", "waitrose.com"), ("Morrisons", "morrisons.com"), ("Ocado", "ocado.com"),
        ("Iceland Foods", "iceland.co.uk"), ("Marks & Spencer Food", "marksandspencer.com"),
    ],
    "Travel & Hotels": [
        ("Booking.com", "booking.com"), ("Expedia", "expedia.com"), ("Hotels.com", "hotels.com"),
        ("Agoda", "agoda.com"), ("Trip.com", "trip.com"), ("Priceline", "priceline.com"),
        ("Kayak", "kayak.com"), ("Skyscanner", "skyscanner.net"), ("Travelocity", "travelocity.com"),
        ("Orbitz", "orbitz.com"), ("Vrbo", "vrbo.com"), ("Airbnb", "airbnb.com"),
        ("Hostelworld", "hostelworld.com"), ("TUI", "tui.com"), ("Tripadvisor", "tripadvisor.com"),
        ("Klook", "klook.com"), ("GetYourGuide", "getyourguide.com"), ("Viator", "viator.com"),
        ("Omio", "omio.com"), ("Rome2Rio", "rome2rio.com"), ("Trainline", "thetrainline.com"),
        ("Amtrak", "amtrak.com"), ("Greyhound", "greyhound.com"), ("FlixBus", "flixbus.com"),
        ("Southwest Airlines", "southwest.com"), ("Delta Air Lines", "delta.com"), ("United Airlines", "united.com"),
        ("American Airlines", "aa.com"), ("JetBlue", "jetblue.com"), ("Alaska Airlines", "alaskaair.com"),
        ("Air Canada", "aircanada.com"), ("British Airways", "britishairways.com"), ("Virgin Atlantic", "virginatlantic.com"),
        ("Lufthansa", "lufthansa.com"), ("Air France", "airfrance.com"), ("KLM", "klm.com"),
        ("Emirates", "emirates.com"), ("Qatar Airways", "qatarairways.com"), ("Etihad Airways", "etihad.com"),
        ("Singapore Airlines", "singaporeair.com"), ("Cathay Pacific", "cathaypacific.com"), ("ANA", "ana.co.jp"),
        ("Japan Airlines", "jal.co.jp"), ("Qantas", "qantas.com"), ("Ryanair", "ryanair.com"),
        ("easyJet", "easyjet.com"), ("Iberia", "iberia.com"), ("Turkish Airlines", "turkishairlines.com"),
        ("Marriott", "marriott.com"), ("Hilton", "hilton.com"), ("Hyatt", "hyatt.com"),
        ("IHG Hotels & Resorts", "ihg.com"), ("Accor", "all.accor.com"), ("Wyndham Hotels", "wyndhamhotels.com"),
        ("Radisson Hotels", "radissonhotels.com"), ("Best Western", "bestwestern.com"), ("Choice Hotels", "choicehotels.com"),
        ("Motel 6", "motel6.com"), ("Travelodge", "travelodge.com"), ("Premier Inn", "premierinn.com"),
        ("Holiday Inn", "ihg.com"), ("Crowne Plaza", "ihg.com"), ("InterContinental", "ihg.com"),
        ("Novotel", "all.accor.com"), ("Pullman Hotels", "all.accor.com"), ("Sofitel", "sofitel.com"),
        ("Fairmont", "fairmont.com"), ("Four Seasons", "fourseasons.com"), ("Shangri-La", "shangri-la.com"),
        ("Mandarin Oriental", "mandarinoriental.com"), ("Ritz-Carlton", "ritzcarlton.com"), ("W Hotels", "marriott.com"),
        ("Westin", "marriott.com"), ("Sheraton", "marriott.com"), ("Courtyard by Marriott", "marriott.com"),
        ("Residence Inn", "marriott.com"), ("Homewood Suites", "hilton.com"), ("Hampton by Hilton", "hilton.com"),
        ("DoubleTree by Hilton", "hilton.com"), ("Embassy Suites", "hilton.com"), ("Meliá Hotels", "melia.com"),
        ("NH Hotels", "nh-hotels.com"), ("Barceló Hotel Group", "barcelo.com"), ("Club Med", "clubmed.com"),
    ],
}


def clean_name(value):
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    if not value or len(value) < 2 or len(value) > 80 or not re.search(r"[A-Za-z]", value):
        return ""
    return value


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")


def load_current():
    try:
        data = json.loads(CATALOG.read_text(encoding="utf-8"))
        categories = data.get("categories", {}) if isinstance(data, dict) else {}
        return categories if isinstance(categories, dict) else {}
    except Exception:
        return {}


def main():
    current = load_current()
    out = {category: [] for category in CATEGORY_TARGETS}
    seen = set()

    # Keep the existing real, enabled brands first: the current catalog is already ordered by priority.
    for category, entries in current.items():
        if category not in out or not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict) or entry.get("placeholder"):
                continue
            name = clean_name(entry.get("name"))
            domain = str(entry.get("domain") or "").strip().lower().removeprefix("www.")
            key = name.casefold()
            if not name or not domain or key in seen or len(out[category]) >= CATEGORY_TARGETS[category]:
                continue
            seen.add(key)
            item = dict(entry)
            item["name"] = name
            item["domain"] = domain
            item["enabled"] = True
            item.pop("placeholder", None)
            out[category].append(item)

    # Add real high-demand brands where the old category did not have enough coverage.
    for category, candidates in FALLBACKS.items():
        for name, domain in candidates:
            if len(out[category]) >= CATEGORY_TARGETS[category]:
                break
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            out[category].append({
                "name": name,
                "domain": domain,
                "enabled": True,
                "catalog_status": "priority_brand",
                "slug": slug(name),
            })

    missing = [f"{category}={CATEGORY_TARGETS[category]-len(out[category])}" for category in CATEGORY_TARGETS if len(out[category]) != CATEGORY_TARGETS[category]]
    if missing:
        raise RuntimeError("CATALOG BUILD FAILED: not enough real brands: " + ", ".join(missing))

    total = sum(len(v) for v in out.values())
    if total != TARGET:
        raise RuntimeError(f"CATALOG BUILD FAILED: expected {TARGET}, got {total}")

    CATALOG.write_text(json.dumps({"categories": out}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("CATALOG READY: 6 priority categories x 89 real brands = 534")
    for category, entries in out.items():
        print(f"  {category}: {len(entries)}")


if __name__ == "__main__":
    main()
