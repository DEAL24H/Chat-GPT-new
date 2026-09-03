from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GA4_ID = "G-R7E164DCZL"
SNIPPET = f'''<script async src="https://www.googletagmanager.com/gtag/js?id={GA4_ID}"></script><script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','{GA4_ID}',{{anonymize_ip:true}});</script>'''

paths = [ROOT / "index.html", ROOT / "post.html"]
for folder in ("fashion", "beauty", "gaming", "consumer", "brand"):
    paths.extend((ROOT / folder).rglob("index.html"))

changed = 0
for path in sorted(set(paths)):
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8", errors="replace")
    if GA4_ID in text and "googletagmanager.com/gtag/js" in text:
        continue
    if "</head>" not in text.lower():
        print(f"SKIP: no </head> in {path.relative_to(ROOT)}")
        continue
    marker = "</head>"
    idx = text.lower().find(marker)
    text = text[:idx] + SNIPPET + text[idx:]
    path.write_text(text, encoding="utf-8")
    changed += 1
    print(f"GA4 injected: {path.relative_to(ROOT)}")

print(f"GA4 injection complete: {changed} pages changed.")
