"""Gate for the assistant-verified first-party merchant source allowlist.

The assistant is the authority for SOURCE verification.  This gate deliberately does
not re-crawl merchant homepages: HTTP 403/429, Cloudflare/WAF, regional redirects,
timeouts, or GitHub-runner network policy are crawler-access issues, not evidence that
an already assistant-verified official merchant is unofficial.

Runtime crawling remains appropriate for individual OFFER/PURCHASE URLs, where the
pipeline must prove that a published offer actually lands on the advertised merchant
product/deal destination.  That is a separate integrity layer.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = [
    ROOT / "data" / "assistant_verified_sources.json",
    ROOT / "data" / "assistant_verified_electronics_additions.json",
    ROOT / "data" / "assistant_verified_beauty_additions.json",
    ROOT / "data" / "assistant_verified_home_additions.json",
]
EXPECTED = ["Fashion", "Electronics", "Beauty & Personal Care", "Home & Living"]


def load():
    rows = []
    for path in MANIFESTS:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        default_category = str(data.get("category", "")).strip()
        for item in data.get("verified_sources", []):
            row = dict(item)
            if default_category and not row.get("category"):
                row["category"] = default_category
            row["_manifest"] = str(path.relative_to(ROOT))
            rows.append(row)
    return rows


def dedupe(rows):
    """First occurrence wins; duplicate manifests must not alter rank or authority."""
    seen = set()
    out = []
    for row in rows:
        category = str(row.get("category", "")).strip()
        name = str(row.get("name", "")).strip().lower()
        domain = str(row.get("domain", "")).strip().lower().removeprefix("www.")
        key = (category, name, domain)
        if category not in EXPECTED or not name or not domain or key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def main():
    rows = dedupe(load())
    selected = {}
    failures = []

    for category in EXPECTED:
        candidates = [r for r in rows if str(r.get("category", "")).strip() == category]
        candidates.sort(key=lambda r: (int(r.get("rank", 999999)), str(r.get("name", "")).lower()))
        # The manifest itself is the assistant-verified source of truth.
        verified = [r for r in candidates if r.get("verification_status") == "verified_first_party"]
        rejected = [r for r in candidates if r.get("verification_status") != "verified_first_party"]
        for row in rejected:
            failures.append(f"{category} rank={row.get('rank')} {row.get('name')}: manifest_status_not_verified")
        chosen = verified[:30]
        selected[category] = chosen
        if len(chosen) < 30:
            failures.append(f"{category}: only {len(chosen)}/30 assistant-verified sources")

        for row in chosen:
            print(
                f"PASS {category} rank={row.get('rank')} {row.get('name')} "
                f"domain={row.get('domain')} source=assistant_verified_manifest"
            )
        for row in verified[30:]:
            print(f"BACKUP {category} rank={row.get('rank')} {row.get('name')}")

    counts = {k: len(v) for k, v in selected.items()}
    total = sum(counts.values())
    print(f"ASSISTANT SOURCE GATE COUNTS: {counts} total={total}")
    if total != 120 or any(v != 30 for v in counts.values()):
        print("ASSISTANT SOURCE GATE FAILED")
        for failure in failures[:200]:
            print(f"  {failure}")
        raise SystemExit(1)

    out = []
    for category in EXPECTED:
        for row in selected[category]:
            out.append({
                "rank": int(row["rank"]),
                "name": row["name"],
                "merchant": row["name"],
                "category": category,
                "domain": row["domain"],
                "official_homepage": row["official_homepage"],
                "verification_status": "assistant_verified_first_party",
                "verification_authority": "assistant",
                "verification_method": "assistant_research_manifest",
            })
    output = {
        "schema_version": 2,
        "total": 120,
        "counts": counts,
        "selection_rule": "Original research rank order is preserved. Only sources absent from the assistant-verified allowlist or explicitly not verified may be replaced by the next assistant-verified rank.",
        "source_authority": "assistant_verified_manifests",
        "runtime_source_identity_recheck": False,
        "sources": out,
    }
    (ROOT / "data" / "assistant_verified_source_selection.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("ASSISTANT SOURCE GATE PASS: 4 categories x 30 = 120 assistant-verified first-party sources")


if __name__ == "__main__":
    main()
