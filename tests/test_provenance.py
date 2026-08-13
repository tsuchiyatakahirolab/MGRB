from pathlib import Path
from mgrb.provenance import build_manifest, verify_manifest, write_manifest


def test_manifest(tmp_path: Path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "a.txt").write_text("abc", encoding="utf-8")
    m = build_manifest(data)
    assert m["schema"] == "mgrb-provenance-1.0"
    assert len(m["files"]) == 1
    assert m["files"][0]["sha256"] == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"

    manifest = tmp_path / "manifest.json"
    write_manifest(data, manifest)
    assert verify_manifest(data, manifest) == []
    (data / "a.txt").write_text("changed", encoding="utf-8")
    assert verify_manifest(data, manifest) == ["sha256:a.txt"]
