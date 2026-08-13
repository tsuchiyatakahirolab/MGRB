from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .provenance import sha256

SIDECAR_SUFFIX = ".mgrb.json"


def canonical_json_hash(data: Any) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    import hashlib

    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def write_artifact_sidecar(
    artifact: Path,
    build_manifest: Path,
    source_manifest: Path,
    style_manifest: Path,
    *,
    base_dir: Path | None = None,
) -> Path:
    base = (base_dir or artifact.parent).resolve()
    artifact = artifact.resolve()
    manifests = {
        "build": build_manifest.resolve(),
        "source": source_manifest.resolve(),
        "style": style_manifest.resolve(),
    }
    payload = {
        "schema": "mgrb-artifact-lineage-1.0",
        "artifact": Path(os.path.relpath(artifact, base)).as_posix(),
        "artifact_sha256": sha256(artifact),
        "manifests": {
            name: {
                "path": Path(os.path.relpath(path, base)).as_posix(),
                "sha256": sha256(path),
            }
            for name, path in manifests.items()
        },
    }
    sidecar = artifact.with_name(artifact.name + SIDECAR_SUFFIX)
    sidecar.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return sidecar


def write_sha256sums(paths: list[Path], output: Path, base_dir: Path) -> None:
    unique = sorted({path.resolve() for path in paths})
    lines = [
        f"{sha256(path)}  {path.relative_to(base_dir.resolve()).as_posix()}" for path in unique
    ]
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _find_sidecar(target: Path) -> Path | None:
    direct = target.with_name(target.name + SIDECAR_SUFFIX)
    if direct.exists():
        return direct
    if target.name.endswith(SIDECAR_SUFFIX):
        return target
    return None


def verify_generated_file(target: Path) -> dict[str, Any]:
    target = target.resolve()
    sidecar = _find_sidecar(target)
    errors: list[str] = []
    warnings: list[str] = []
    if sidecar is None:
        return {
            "ok": False,
            "is_mgrb": False,
            "errors": ["missing-artifact-lineage-sidecar"],
            "warnings": [],
        }
    lineage = json.loads(sidecar.read_text(encoding="utf-8"))
    artifact = sidecar.parent / lineage["artifact"]
    if not artifact.exists():
        errors.append("missing-artifact")
    elif sha256(artifact) != lineage["artifact_sha256"]:
        errors.append("artifact-sha256-mismatch")

    loaded: dict[str, Any] = {}
    for name in ("build", "source", "style"):
        item = lineage.get("manifests", {}).get(name)
        if not item:
            errors.append(f"missing-{name}-manifest-reference")
            continue
        path = sidecar.parent / item["path"]
        if not path.exists():
            errors.append(f"missing-{name}-manifest")
            continue
        if sha256(path) != item["sha256"]:
            errors.append(f"{name}-manifest-sha256-mismatch")
            continue
        loaded[name] = json.loads(path.read_text(encoding="utf-8"))

    build = loaded.get("build", {})
    source = loaded.get("source", {})
    style = loaded.get("style", {})
    if build and source:
        source_path = sidecar.parent / lineage["manifests"]["source"]["path"]
        if build.get("source_manifest_sha256") != sha256(source_path):
            errors.append("build-source-manifest-link-mismatch")
        if build.get("source_manifest_id") != source.get("manifest_id"):
            errors.append("build-source-manifest-id-mismatch")
    if build and style:
        theme = build.get("theme") or {}
        if theme.get("palette_sha256") != style.get("palette_sha256"):
            errors.append("build-style-theme-hash-mismatch")
    canonical_release = build.get("canonical_release") or {}
    if not build.get("canonical_repository"):
        warnings.append("canonical-repository-not-configured-before-publication")
    if not canonical_release.get("manifest_sha256"):
        warnings.append("canonical-release-manifest-anchor-not-configured")

    return {
        "ok": not errors,
        "is_mgrb": lineage.get("schema") == "mgrb-artifact-lineage-1.0",
        "artifact": artifact.as_posix(),
        "mgrb_version": build.get("mgrb_version"),
        "git_commit": build.get("git_commit"),
        "build_id": build.get("build_id"),
        "canonical_repository": build.get("canonical_repository"),
        "canonical_release": canonical_release,
        "errors": errors,
        "warnings": warnings,
    }
