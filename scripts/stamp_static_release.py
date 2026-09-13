"""Stamp the canonical release into the homepage and versioned assets."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "data-manifest.json"
INDEX = ROOT / "index.html"


def main():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    release_id = str(manifest.get("release_id") or "").strip()
    if not re.fullmatch(r"[0-9a-f]{16}", release_id):
        raise SystemExit("STATIC RELEASE STAMP FAILED: invalid release_id")

    text = INDEX.read_text(encoding="utf-8")
    text = re.sub(r'<html lang="en"(?: data-release-id="[^"]*")?>', f'<html lang="en" data-release-id="{release_id}">', text, count=1)
    if 'data-release-id=' not in text:
        text = text.replace('<html lang="en">', f'<html lang="en" data-release-id="{release_id}">', 1)
    if 'name="deal24h-release"' in text:
        text = re.sub(
            r'<meta name="deal24h-release" content="[^"]*">',
            f'<meta name="deal24h-release" content="{release_id}">',
            text,
            count=1,
        )
    else:
        text = text.replace(
            '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',
            '<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="deal24h-release" content="{release_id}">',
            1,
        )
    text = re.sub(r'assets/style\.css\?v=[^"\s]+', f'assets/style.css?v={release_id}', text)
    text = re.sub(r'assets/app-home\.js\?v=[^"\s]+', f'assets/app-home.js?v={release_id}', text)
    INDEX.write_text(text, encoding="utf-8")
    print(f"STATIC RELEASE STAMP PASS: release_id={release_id}")


if __name__ == "__main__":
    main()
