"""Shared deterministic release identity for every public Deal24h layer."""
from __future__ import annotations

import hashlib
import json

PUBLIC_RELEASE_FIELDS = (
    "id",
    "title",
    "content",
    "code",
    "discount",
    "merchant",
    "category",
    "country",
    "locale",
    "source_url",
    "final_purchase_url",
    "promotion_url",
    "official_source",
    "expires_at",
    "status",
    "_shard",
)


def public_release_row(row: dict) -> dict:
    """Return only stable, user-visible fields that define a release."""
    return {key: row.get(key, "") for key in PUBLIC_RELEASE_FIELDS}


def release_id_for_rows(rows: list[dict]) -> str:
    """Hash sorted public payloads so meaningful content changes create a new release."""
    payload = [public_release_row(row) for row in rows]
    payload.sort(key=lambda row: (str(row.get("id") or ""), str(row.get("_shard") or "")))
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]
