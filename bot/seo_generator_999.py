import html
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from catalog_utils import CATALOG, brand_slug, canonicalize_item, is_active_offer, resolve_brand

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "news.json"
BASE = "https://deal24h.net"
GA4 = "G-R7E164DCZL"
CATEGORY_SLUGS = {"Fashion": "fashion", "Electronics": "electronics", "Beauty & Personal Care": "beauty-personal-care", "Home & Living": "home-living"}


def esc(v):
    return html.escape(str(v or ""), quote=True)


def load_items():
    try:
        d = json.loads(DATA.read_text(encoding="utf-8"))
        return d if isinstance(d, list) else d.get("items", [])
    except Exception:
        return []


def domain(b):
    h = resolve_brand(b)
    return h.get("domain", "") if h else ""


def logo(b):
    d = domain(b)
    return f"https://www.google.com/s2/favicons?domain={quote(d)}&sz=128" if d else ""


def official_homepage(b):
    d = domain(b).strip().removeprefix("www.")
    return f"https://{d}/" if d else ""

# The remainder of the generator is intentionally kept identical to the existing
# TN01 implementation; only the canonical category contract above is changed.
