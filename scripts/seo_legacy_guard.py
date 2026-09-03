import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Only retired category hubs are legacy now. The six priority hubs remain indexable.
LEGACY_ROOTS = ("gaming", "sports-outdoor", "software-digital-services", "baby-kids-family", "automotive-accessories", "books-education-media")


def ensure_noindex(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    robots = '<meta name="robots" content="noindex,follow">'
    pattern = r'<meta\s+name=["\']robots["\']\s+content=["\'][^"\']*["\']\s*/?>'
    if re.search(pattern, text, flags=re.I):
        text = re.sub(pattern, robots, text, count=1, flags=re.I)
    else:
        text = re.sub(r"(<meta charset=[^>]+>)", r"\1" + robots, text, count=1, flags=re.I)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main():
    changed = 0
    legacy_pages = 0
    for root_name in LEGACY_ROOTS:
        root = ROOT / root_name
        if not root.exists():
            continue
        for path in root.glob("*/index.html"):
            legacy_pages += 1
            if ensure_noindex(path):
                changed += 1

    for path in (ROOT / "admin" / "index.html", ROOT / "admin" / "admin.html", ROOT / "post.html"):
        if path.exists() and ensure_noindex(path):
            changed += 1

    print(f"SEO LEGACY GUARD: checked {legacy_pages} retired pages; updated {changed} files to noindex,follow")


if __name__ == "__main__":
    main()
