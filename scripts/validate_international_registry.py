"""Audit the assistant-verified first-party merchant source registry.

SOURCE IDENTITY AUTHORITY
-------------------------
The assistant-verified manifests are the single source of truth for merchant identity
and official ecommerce/source verification.  This script must never turn a GitHub
runner HTTP 403/429, WAF/Cloudflare response, timeout, or regional crawler block into
a source rejection. Those are runtime crawler-access conditions, not merchant identity
failures.

The separate offer-link validator is responsible for checking individual published
offers and their final purchase/deal destinations at runtime.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "data" / "international_brand_registry.json"
REPORT = ROOT / "data" / "international_source_audit.json"
ASSISTANT_MANIFESTS = [
    ROOT / "data" / "assistant_verified_sources.json",
    ROOT / "data" / "assistant_verified_electronics_additions.json",
    ROOT / "data" / "assistant_verified_beauty_additions.json",
    ROOT / "data" / "assistant_verified_home_additions.json",
]
EXPECTED_CATEGORIES = ["Fashion", "Electronics", "Beauty & Personal Care", "Home & Living"]


def clean_domain(value):
    return str(value or "").strip().lower().removeprefix("www.")


def load_assistant_verified():
    rows = []
    for path in ASSISTANT_MANIFESTS:
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

    seen = set()
    unique = []
    for row in rows:
        category = str(row.get("category", "")).strip()
        name = str(row.get("name", "")).strip()
        domain = clean_domain(row.get("domain"))
        key = (category, name.lower(), domain)
        if category not in EXPECTED_CATEGORIES or not name or not domain or key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def load_registry_ranks():
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    ranks = {}
    for category, category_data in data.get("categories", {}).items():
        entries = category_data if isinstance(category_data, list) else category_data.get("entries", [])
        ranks[category] = {
            str(x.get("name", "")).strip().lower(): int(x.get("rank", 9999))
            for x in entries
        }
    return ranks


def main():
    registry_ranks = load_registry_ranks()
    rows = load_assistant_verified()
    selected = {}
    results = []
    selection_log = {}

    for category in EXPECTED_CATEGORIES:
        candidates = [r for r in rows if str(r.get("category", "")).strip() == category]
        candidates.sort(key=lambda r: (
            int(r.get("rank", registry_ranks.get(category, {}).get(str(r.get("name", "")).lower(), 9999))),
            str(r.get("name", "")).lower(),
        ))

        category_results = []
        for entry in candidates:
            status = "verified_first_party" if entry.get("verification_status") == "verified_first_party" else "not_verified"
            row = {
                "rank": int(entry.get("rank", registry_ranks.get(category, {}).get(str(entry.get("name", "")).lower(), 9999))),
                "name": entry.get("name"),
                "category": category,
                "domain": entry.get("domain"),
                "official_homepage": entry.get("official_homepage"),
                "status": status,
                "verification_authority": "assistant",
                "verification_method": "assistant_research_manifest",
                "runtime_http_identity_check": "not_performed",
                "reason": "assistant_verified_source_of_truth" if status == "verified_first_party" else "manifest_status_not_verified",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "manifest": entry.get("_manifest"),
            }
            category_results.append(row)
            results.append(row)

        eligible = [x for x in category_results if x["status"] == "verified_first_party"]
        chosen = eligible[:30]
        selected[category] = [
            {
                "rank": x["rank"],
                "name": x["name"],
                "domain": x["domain"],
                "official_homepage": x["official_homepage"],
            }
            for x in chosen
        ]
        selection_log[category] = {
            "candidate_count": len(candidates),
            "assistant_verified_count": len(eligible),
            "selected_count": len(chosen),
            "promoted_ranks": [x["rank"] for x in chosen if x["rank"] > 30],
            "meets_target": len(chosen) == 30,
        }

    target_failures = [c for c, info in selection_log.items() if not info["meets_target"]]
    summary = {
        "schema_version": 4,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "registry_file": str(REGISTRY.relative_to(ROOT)),
        "execution_allowlist": [str(x.relative_to(ROOT)) for x in ASSISTANT_MANIFESTS if x.exists()],
        "source_authority": "assistant_verified_manifests",
        "runtime_source_identity_recheck": False,
        "selection_rule": "Preserve original researched rank order. Only genuinely unverified/missing assistant sources are replaced by the next assistant-verified candidate; crawler accessibility failures do not disqualify a source.",
        "total_candidates_audited": len(results),
        "verified_first_party": sum(x["status"] == "verified_first_party" for x in results),
        "not_verified": sum(x["status"] == "not_verified" for x in results),
        "target_categories_without_30_eligible": target_failures,
        "selection": selection_log,
        "selected": selected,
        "results": results,
    }
    REPORT.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "INTERNATIONAL SOURCE AUDIT: "
        f"candidates={len(results)} verified={summary['verified_first_party']} "
        f"not_verified={summary['not_verified']} categories_short={len(target_failures)}"
    )
    if target_failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
