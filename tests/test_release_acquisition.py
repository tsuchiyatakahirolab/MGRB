import hashlib
import io
import urllib.error

import pytest

from scripts import prepare_owner_review


def test_download_uses_pinned_fallback_and_verifies_hash(tmp_path, monkeypatch):
    payload = b"pinned public archive"
    expected = hashlib.sha256(payload).hexdigest()

    def fake_urlopen(request, timeout):
        assert timeout == 180
        if request.full_url == "https://primary.example/archive.zip":
            raise urllib.error.URLError("unavailable")
        return io.BytesIO(payload)

    monkeypatch.setattr(prepare_owner_review, "ROOT", tmp_path)
    monkeypatch.setattr(prepare_owner_review.urllib.request, "urlopen", fake_urlopen)
    target = tmp_path / "data" / "archive.zip"

    retrieval_url = prepare_owner_review.download(
        (
            "https://primary.example/archive.zip",
            "https://fallback.example/archive.zip",
        ),
        target,
        expected,
    )

    assert retrieval_url == "https://fallback.example/archive.zip"
    assert target.read_bytes() == payload


def test_download_rejects_unpinned_content(tmp_path, monkeypatch):
    monkeypatch.setattr(prepare_owner_review, "ROOT", tmp_path)
    monkeypatch.setattr(
        prepare_owner_review.urllib.request,
        "urlopen",
        lambda request, timeout: io.BytesIO(b"wrong archive"),
    )
    target = tmp_path / "data" / "archive.zip"

    with pytest.raises(RuntimeError, match="all download locations failed"):
        prepare_owner_review.download(
            "https://example.test/archive.zip",
            target,
            hashlib.sha256(b"expected archive").hexdigest(),
        )

    assert not target.exists()
