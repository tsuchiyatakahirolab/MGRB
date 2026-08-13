from __future__ import annotations
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from . import __version__


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit(root: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return None


def build_manifest(root: Path, repository_root: Path | None = None) -> dict:
    root = root.resolve()
    repo = (repository_root or root).resolve()
    files = []
    if root.exists():
        for p in sorted(x for x in root.rglob("*") if x.is_file()):
            files.append({
                "path": p.relative_to(root).as_posix(),
                "bytes": p.stat().st_size,
                "sha256": sha256(p),
            })
    return {
        "schema": "mgrb-provenance-1.0",
        "mgrb_version": __version__,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "git_commit": git_commit(repo),
        "build_id": os.environ.get("MGRB_BUILD_ID"),
        "root": root.name,
        "files": files,
    }


def write_manifest(root: Path, output: Path, repository_root: Path | None = None) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(build_manifest(root, repository_root), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def verify_manifest(root: Path, manifest_path: Path) -> list[str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = {x["path"]: x for x in manifest.get("files", [])}
    errors: list[str] = []
    for rel, item in expected.items():
        p = root / rel
        if not p.exists():
            errors.append(f"missing:{rel}")
            continue
        actual = sha256(p)
        if actual != item.get("sha256"):
            errors.append(f"sha256:{rel}")
    return errors
