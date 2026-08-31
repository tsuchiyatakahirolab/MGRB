"""Offline public verification only. No signing implementation or private key material."""
from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

DOMAIN = b"MGRB-EXPORT-RECEIPT/v1\x00"
SCHEMA = "mgrb-export-receipt-1"
DEV = "DEVELOPMENT_NOT_OFFICIAL"
OFFICIAL = "OFFICIAL_MGRB"
HASH_FIELDS = {"file_sha256", "build_spec_sha256", "source_manifest_sha256", "watermark_payload_hash"}
CLAIM_FIELDS = HASH_FIELDS | {
    "schema", "purpose", "export_id", "build_id", "mgrb_version", "created_at",
    "signing_key_id", "algorithm",
}
# Owner-reviewed trust anchors only. Empty until the production-key gate is resolved.
# Values will include public_key (base64 raw Ed25519), not_before, not_after, revoked.
PRODUCTION_KEYS: dict[str, dict[str, Any]] = {}


def _timestamp(value: str) -> datetime:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise ValueError("Timestamp must be UTC with second precision")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def canonical_claims(claims: dict[str, str]) -> bytes:
    """Restricted flat-string JSON contract; not a general-purpose JCS implementation."""
    if set(claims) != CLAIM_FIELDS or any(type(v) is not str for v in claims.values()):
        raise ValueError("Unexpected receipt fields or types")
    if any(not v.isascii() or len(v) > 160 for v in claims.values()):
        raise ValueError("Receipt values must be bounded ASCII strings")
    if claims["schema"] != SCHEMA or claims["algorithm"] != "Ed25519":
        raise ValueError("Unsupported receipt contract")
    if claims["purpose"] not in {DEV, OFFICIAL}:
        raise ValueError("Unknown receipt purpose")
    if str(UUID(claims["export_id"])) != claims["export_id"]:
        raise ValueError("Export ID must be a canonical UUID")
    _timestamp(claims["created_at"])
    for field in HASH_FIELDS:
        if not re.fullmatch(r"[0-9a-f]{64}", claims[field]):
            raise ValueError("Invalid SHA-256 field")
    for field in ("build_id", "mgrb_version", "signing_key_id"):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", claims[field]):
            raise ValueError("Invalid identifier")
    return DOMAIN + json.dumps(claims, sort_keys=True, separators=(",", ":")).encode("ascii")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("Duplicate JSON member")
        obj[key] = value
    return obj


def read_receipt(path: Path) -> dict[str, str]:
    if path.stat().st_size > 65536:
        raise ValueError("Oversized receipt")
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise TypeError("Receipt must be an object")
    return value


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_receipt(
    receipt: dict[str, str] | None,
    artifact: Path | None = None,
    *,
    development_keys: dict[str, str] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "OFFICIAL_SIGNATURE_ABSENT", "official": False,
        "signature_valid": False, "file_verified": False,
    }
    if receipt is None:
        return result
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        return {**result, "status": "VERIFICATION_UNAVAILABLE", "reason": "Install mgrb[authenticity]"}
    try:
        if set(receipt) != CLAIM_FIELDS | {"signature"}:
            raise ValueError("Unexpected receipt members")
        claims = {k: v for k, v in receipt.items() if k != "signature"}
        message = canonical_claims(claims)
        is_development = claims["purpose"] == DEV
        key_id = claims["signing_key_id"]
        if is_development:
            encoded_key = (development_keys or {}).get(key_id)
            if not encoded_key:
                return {**result, "status": "DEVELOPMENT_KEY_UNTRUSTED", "reason": DEV}
        else:
            # Caller-supplied development keys can NEVER establish official trust.
            key = PRODUCTION_KEYS.get(key_id)
            if not key or key["revoked"]:
                raise ValueError("Unknown or revoked production trust anchor")
            when = _timestamp(claims["created_at"])
            if not (_timestamp(key["not_before"]) <= when <= _timestamp(key["not_after"])):
                raise ValueError("Signing time outside key validity")
            encoded_key = key["public_key"]
        pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(encoded_key, validate=True))
        pub.verify(base64.b64decode(receipt["signature"], validate=True), message)
        result.update(signature_valid=True, export_id=claims["export_id"], purpose=claims["purpose"])
        if artifact is not None:
            if file_hash(artifact) != claims["file_sha256"]:
                return {**result, "status": "FILE_HASH_MISMATCH"}
            result["file_verified"] = True
        if is_development:
            result["status"] = (
                "DEVELOPMENT_SIGNATURE_VALID" if artifact is not None
                else "DEVELOPMENT_RECEIPT_VALID_FILE_UNCHECKED"
            )
        elif artifact is None:
            result["status"] = "RECEIPT_SIGNATURE_VALID_FILE_UNCHECKED"
        else:
            result.update(status="OFFICIAL_SIGNATURE_VALID", official=True)
        return result
    except (ValueError, TypeError, KeyError, OSError, InvalidSignature) as exc:
        return {**result, "status": "OFFICIAL_SIGNATURE_INVALID", "reason": type(exc).__name__}


def verify_target(
    target: Path, *, receipt_path: Path | None = None,
    artifact: Path | None = None, development_key: Path | None = None,
) -> dict[str, Any]:
    try:
        if target.name.endswith(".receipt.json"):
            receipt_path = target
        else:
            artifact = target
            receipt_path = receipt_path or target.with_name(target.name + ".receipt.json")
        if not receipt_path.exists():
            return verify_receipt(None, artifact)
        dev_keys = None
        if development_key:
            key = read_receipt(development_key)
            if set(key) != {"purpose", "key_id", "public_key"} or key["purpose"] != DEV:
                raise ValueError("Only a development public key may be supplied")
            dev_keys = {key["key_id"]: key["public_key"]}
        return verify_receipt(read_receipt(receipt_path), artifact, development_keys=dev_keys)
    except (ValueError, TypeError, OSError, KeyError) as exc:
        return {"status": "OFFICIAL_SIGNATURE_INVALID", "official": False,
                "signature_valid": False, "file_verified": False, "reason": type(exc).__name__}
