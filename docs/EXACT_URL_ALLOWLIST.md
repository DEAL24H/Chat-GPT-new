# Exact source URL allowlist

The crawler now uses `data/allowed_brand_urls.json`, generated from `data/120_thuong_hieu_kem_trang_goc_va_quoc_gia.xlsx`.

The manifest contains **120 brands and 440 exact source URLs**. The runtime contract is:

- `allow_discovery=false`: the crawler never follows promotion/category links to create new source jobs.
- `allow_redirect_source_expansion=false`: redirects do not become new source jobs.
- Each source job has exactly one URL in `url_allowlist`.
- If the manifest is missing or invalid, the Bot fails closed and does not fall back to the legacy brand/source list.
- A page may still contain a `final_purchase_url` discovered from its own HTML. This is the destination presented to the user; it is not a new crawl source.
- Offers are tagged with the market from the workbook, while the source URL remains the exact URL that was requested.

To rebuild the manifest after changing the workbook:

```bash
python scripts/build_allowed_url_manifest.py
python scripts/test_exact_url_allowlist.py
```

The CI workflow rebuilds and checks the manifest before running the crawler.
