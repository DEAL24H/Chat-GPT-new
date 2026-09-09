"""Build the exact source URL allowlist from the supplied workbook.

The crawler must use this manifest as an immutable source boundary: it may fetch
only these URLs and may not discover, enqueue, or expand additional source URLs.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path
from urllib.parse import urlparse
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
INPUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/120_thuong_hieu_kem_trang_goc_va_quoc_gia.xlsx"
OUTPUT = ROOT / "data/allowed_brand_urls.json"
EXPECTED_CATEGORIES = {"Fashion", "Electronics", "Beauty & Personal Care", "Home & Living"}


def main() -> None:
    wb = load_workbook(INPUT, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows or [str(x or "").strip() for x in rows[0]] != ["STT", "Thương hiệu", "Ngành hàng", "Quốc gia / Thị trường", "URL Website"]:
        raise SystemExit("ALLOWLIST INPUT CONTRACT FAILED: unexpected header")
    entries = []
    seen = set()
    for line, raw in enumerate(rows[1:], start=2):
        values = [str(x or "").strip() for x in raw[:5]]
        if not any(values):
            continue
        if len(values) != 5 or not all(values[1:]):
            raise SystemExit(f"ALLOWLIST INPUT CONTRACT FAILED: incomplete row {line}")
        number, merchant, category, market, url = values
        if category not in EXPECTED_CATEGORIES:
            raise SystemExit(f"ALLOWLIST INPUT CONTRACT FAILED: invalid category at row {line}: {category}")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
            raise SystemExit(f"ALLOWLIST INPUT CONTRACT FAILED: invalid source URL at row {line}: {url}")
        key = (merchant.casefold(), category, market.casefold(), url.rstrip("/"))
        if key in seen:
            raise SystemExit(f"ALLOWLIST INPUT CONTRACT FAILED: duplicate row {line}: {url}")
        seen.add(key)
        entries.append({
            "id": int(number) if number.isdigit() else number,
            "merchant": merchant,
            "category": category,
            "market": market,
            "country": "International" if "gốc" in market.casefold() or "quốc tế" in market.casefold() else market,
            "url": url,
            "domain": (parsed.hostname or "").lower().removeprefix("www."),
        })
    brands = sorted({x["merchant"] for x in entries}, key=str.casefold)
    if len(entries) != 440 or len(brands) != 120:
        raise SystemExit(f"ALLOWLIST INPUT CONTRACT FAILED: rows={len(entries)}, brands={len(brands)}; expected 440 rows/120 brands")
    payload = {
        "version": 1,
        "source": "120_thuong_hieu_kem_trang_goc_va_quoc_gia.xlsx",
        "mode": "exact_source_url_allowlist",
        "allow_discovery": False,
        "allow_redirect_source_expansion": False,
        "total_brands": len(brands),
        "total_urls": len(entries),
        "entries": entries,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"ALLOWLIST CREATED: brands={len(brands)} urls={len(entries)} output={OUTPUT}")


if __name__ == "__main__":
    main()
