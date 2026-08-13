import json
from pathlib import Path

from mgrb.provenance import sha256
from mgrb.verification import verify_generated_file, write_artifact_sidecar, write_sha256sums


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")


def test_artifact_lineage_verifies_and_detects_tampering(tmp_path: Path):
    artifact = tmp_path / "map.pdf"
    artifact.write_bytes(b"publication-output")
    source = tmp_path / "mgrb-source-manifest.json"
    style = tmp_path / "mgrb-style-manifest.json"
    build = tmp_path / "mgrb-build.json"
    _write(source, {"schema": "mgrb-source-manifest-1.0", "manifest_id": "build-sources"})
    _write(style, {"schema": "style", "palette_sha256": "a" * 64})
    _write(
        build,
        {
            "schema": "mgrb-build-1.0",
            "mgrb_version": "1.0.0",
            "git_commit": "b" * 40,
            "build_id": "build",
            "source_manifest_id": "build-sources",
            "source_manifest_sha256": sha256(source),
            "theme": {"palette_sha256": "a" * 64},
            "canonical_repository": None,
            "canonical_release": {},
        },
    )
    sidecar = write_artifact_sidecar(artifact, build, source, style)
    write_sha256sums([artifact, sidecar, build, source, style], tmp_path / "SHA256SUMS", tmp_path)
    result = verify_generated_file(artifact)
    assert result["ok"] is True
    assert result["is_mgrb"] is True
    assert result["mgrb_version"] == "1.0.0"
    assert result["warnings"] == [
        "canonical-repository-not-configured-before-publication",
        "canonical-release-manifest-anchor-not-configured",
    ]

    artifact.write_bytes(b"modified-after-build")
    changed = verify_generated_file(artifact)
    assert changed["ok"] is False
    assert "artifact-sha256-mismatch" in changed["errors"]


def test_unrelated_file_is_not_claimed_as_mgrb(tmp_path: Path):
    target = tmp_path / "unrelated.png"
    target.write_bytes(b"not mgrb")
    result = verify_generated_file(target)
    assert result["ok"] is False
    assert result["is_mgrb"] is False
