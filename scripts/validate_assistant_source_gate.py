"""Gate for the assistant-verified first-party merchant source allowlist.

The assistant is the authority for SOURCE verification. This gate does not re-crawl
merchant homepages. Runtime HTTP failures are crawler-access issues, not source identity
failures. The gate enforces 30 UNIQUE merchants per canonical category.
"""
import json
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
    """First occurrence wins; a merchant cannot occupy two slots because of regional domains."""
    seen_merchants = set()
    seen_domains = set()
    out = []
    for row in rows:
        category = str(row.get("category", "")).strip()
        name = str(row.get("name", "")).strip()
        merchant_key = (category, name.casefold())
        domain = str(row.get("domain", "")).strip().lower().removeprefix("www.")
        domain_key = (category, domain)
        if category not in EXPECTED or not name or not domain:
            continue
        if merchant_key in seen_merchants:
            continue
        if domain_key in seen_domains:
            continue
        seen_merchants.add(merchant_key)
        seen_domains.add(domain_key)
        out.append(row)
    return out


def main():
    rows = dedupe(load())
    selected = {}
    failures = []

    for category in EXPECTED:
        candidates = [r for r in rows if str(r.get("category", "")).strip() == category]
        candidates.sort(key=lambda r: (int(r.get("rank", 999999)), str(r.get("name", "")).lower()))
        verified = [r for r in candidates if r.get("verification_status") == "verified_first_party"]
        rejected = [r for r in candidates if r.get("verification_status") != "verified_first_party"]
        for row in rejected:
            failures.append(f"{category} rank={row.get('rank')} {row.get('name')}: manifest_status_not_verified")
        chosen = verified[:30]
        selected[category] = chosen
        if len(chosen) < 30:
            failures.append(f"{category}: only {len(chosen)}/30 UNIQUE assistant-verified merchants")

        for row in chosen:
            print(f"PASS {category} rank={row.get('rank')} {row.get('name')} domain={row.get('domain')} source=assistant_verified_manifest")
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
        "schema_version": 3,
        "total": 120,
        "counts": counts,
        "unique_merchants_per_category": True,
        "selection_rule": "Preserve original demand rank order. If an original candidate is not assistant-verified or duplicates an already selected merchant, take the next assistant-verified unique merchant rank.",
        "source_authority": "assistant_verified_manifests",
        "runtime_source_identity_recheck": False,
        "sources": out,
    }
    (ROOT / "data" / "assistant_verified_source_selection.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("ASSISTANT SOURCE GATE PASS: 4 categories x 30 UNIQUE merchants = 120 assistant-verified first-party sources")


if __name__ == "__main__":
    main()
