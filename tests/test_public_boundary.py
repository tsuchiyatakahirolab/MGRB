import io
import sqlite3
import zipfile
from pathlib import Path

import pytest

from mgrb.public_boundary import audit_paths, audit_payload


def archive(name: str, data: bytes) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(name, data)
    return stream.getvalue()


def test_nested_archive_cannot_hide_private_source_or_browser_profile():
    payload = b"MGRB_WEB_" + b"PRIVATE_IMPLEMENTATION"
    findings = audit_payload("download.zip", archive("inner.zip", archive("client.js", payload)))
    assert any("secret-or-private-source" in f for f in findings)
    assert audit_payload("assets.zip", archive("browser-profile/Default/Cookies", b"fixture"))


def test_disguised_database_and_path_traversal_are_blocked():
    db = sqlite3.connect(":memory:")
    db.execute("create table placeholder(value text)")
    assert any("unapproved-database" in f for f in audit_payload("image.png", db.serialize()))
    db.close()
    assert audit_payload("demo.zip", archive("../outside", b"fixture"))


def test_large_unreviewed_archive_and_unreadable_file_fail_closed(tmp_path: Path):
    findings = audit_payload("demo.zip", archive("large.txt", b"0" * 20000), budget=[10000, 10])
    assert any("unreviewed-resource-limit" in f for f in findings)
    assert audit_paths([tmp_path / "missing"]) == ["unreadable:missing"]


@pytest.mark.parametrize("name", ["mgrb-web/server.py", "private-inputs/test.csv", "receipt.db"])
def test_forbidden_classes(name):
    assert audit_payload(name, b"fixture")


def test_public_receipt_and_ordinary_code_are_allowed():
    assert not audit_payload("export.receipt.json", b'{"purpose":"DEVELOPMENT_NOT_OFFICIAL"}')
    assert not audit_payload("source.py", b"def add(a, b): return a + b")
