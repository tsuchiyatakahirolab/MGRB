import json
from pathlib import Path

import pytest

from mgrb.official import PRODUCTION_KEYS, read_receipt, verify_receipt, verify_target

FIXTURE = Path(__file__).parent / "fixtures" / "authenticity"
FILE = FIXTURE / "development.txt"
RECEIPT = FIXTURE / "development.txt.receipt.json"
KEY = FIXTURE / "development-public.json"


def test_development_never_becomes_official():
    assert not PRODUCTION_KEYS
    assert verify_target(FILE)["status"] == "DEVELOPMENT_KEY_UNTRUSTED"
    result = verify_target(FILE, development_key=KEY)
    assert result["status"] == "DEVELOPMENT_SIGNATURE_VALID"
    assert result["file_verified"] and result["signature_valid"] and not result["official"]
    assert verify_target(RECEIPT, development_key=KEY)["status"].endswith("FILE_UNCHECKED")


@pytest.mark.parametrize("field,value", [
    ("purpose", "OFFICIAL_MGRB"), ("build_id", "changed-build"),
    ("file_sha256", "0" * 64), ("algorithm", "none"),
    ("signing_key_id", "unknown"), ("created_at", "2026-08-31"),
])
def test_signed_claim_tampering_fails(field, value):
    receipt = read_receipt(RECEIPT)
    receipt[field] = value
    key = read_receipt(KEY)
    result = verify_receipt(receipt, FILE, development_keys={key["key_id"]:key["public_key"]})
    assert not result["official"] and not result["signature_valid"]


def test_modified_file_and_fork_without_receipt(tmp_path):
    target = tmp_path / "changed.txt"
    target.write_bytes(FILE.read_bytes() + b"changed")
    assert verify_target(target)["status"] == "OFFICIAL_SIGNATURE_ABSENT"
    result = verify_target(target, receipt_path=RECEIPT, development_key=KEY)
    assert result["status"] == "FILE_HASH_MISMATCH"
    assert result["signature_valid"] and not result["file_verified"] and not result["official"]


def test_untrusted_json_members_and_duplicate_names_fail_closed(tmp_path):
    receipt = read_receipt(RECEIPT)
    receipt["public_key"] = "attacker-supplied"
    assert verify_receipt(receipt)["status"] == "OFFICIAL_SIGNATURE_INVALID"
    path = tmp_path / "duplicate.receipt.json"
    path.write_text('{"purpose":"OFFICIAL_MGRB",' + json.dumps(read_receipt(RECEIPT))[1:])
    assert verify_target(path)["status"] == "OFFICIAL_SIGNATURE_INVALID"
