import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "brand_catalog.json"
ALLOWED_CATEGORY_SLUGS = {"fashion", "electronics", "beauty", "home-living"}


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower().replace("&", " and ").replace("'", "")).strip("-")


def main():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    categories = data.get("categories", {})
    allowed_brands = {slug(e.get("name")) for entries in categories.values() for e in entries}
    removed_brands = 0
    removed_categories = 0

    brand_root = ROOT / "brand"
    if brand_root.exists():
        for child in brand_root.iterdir():
            if child.is_dir() and child.name not in allowed_brands:
                shutil.rmtree(child)
                removed_brands += 1

    for child in ROOT.iterdir():
        if child.is_dir() and (child / "index.html").exists() and child.name not in ALLOWED_CATEGORY_SLUGS and child.name not in {"brand", "assets", ".git"}:
            shutil.rmtree(child)
            removed_categories += 1

    print(f"LEGACY SEO CLEANUP: removed_brand_pages={removed_brands}, removed_category_pages={removed_categories}, active_catalog_brands={len(allowed_brands)}")


if __name__ == "__main__":
    main()
