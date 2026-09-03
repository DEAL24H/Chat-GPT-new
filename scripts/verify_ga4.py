from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GA4_ID = "G-R7E164DCZL"

# Public site pages only. Admin/dashboard are intentionally excluded.
paths = [ROOT / "index.html", ROOT / "post.html"]
for folder in ("fashion", "beauty", "gaming", "consumer", "brand"):
    paths.extend((ROOT / folder).rglob("index.html"))

missing = []
checked = 0
for path in sorted(set(paths)):
    if not path.exists():
        continue
    checked += 1
    text = path.read_text(encoding="utf-8", errors="replace")
    if GA4_ID not in text or "googletagmanager.com/gtag/js" not in text:
        missing.append(path.relative_to(ROOT).as_posix())

print(f"GA4 verification: checked {checked} public HTML pages")
if missing:
    print("Pages missing GA4 tracking:")
    for item in missing:
        print(f"- {item}")
    raise SystemExit(1)

print(f"GA4 verification passed: {GA4_ID} is present on every checked public page.")
