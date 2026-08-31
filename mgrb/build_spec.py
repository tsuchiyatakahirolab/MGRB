"""Versioned public build contract loader; no hosted orchestration or signing authority."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from .product import ProductBuildSpec


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate Build Spec JSON member")
        result[key] = value
    return result


def load_build_spec(path: Path, root: Path) -> ProductBuildSpec:
    """Read at most 1 MiB, reject unknown/version-incompatible semantics, resolve local paths.

    Relative input paths resolve beside the spec, independent of the current directory.
    Loading validates choices only; it never fetches inputs or runs a build.
    """
    with path.open("rb") as stream:
        raw = stream.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("Build Spec exceeds 1 MiB")
    payload = json.loads(raw, object_pairs_hook=_unique)
    schema = json.loads((root / "schema/product_build.schema.json").read_text())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    if payload.get("schema_version") != "mgrb-build-spec-1":
        raise ValueError("A versioned Build Spec is required for --spec")
    spec = ProductBuildSpec.from_dict(payload)
    spec.validate(root)
    replacements = {name: str((path.parent / name).resolve()) for name in spec.input_files}
    resolved = spec.to_dict()
    resolved["input_files"] = [replacements[name] for name in spec.input_files]
    for key in ("input_kinds", "input_metadata", "field_maps"):
        if resolved[key] is not None:
            resolved[key] = {
                replacements.get(name, name): value for name, value in resolved[key].items()
            }
    return ProductBuildSpec.from_dict(resolved)
