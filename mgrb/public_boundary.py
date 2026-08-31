"""Public distribution checks. Findings report locations, never matched values."""
from __future__ import annotations

import io
import re
import subprocess
import tarfile
import time
import zipfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

FORBIDDEN_PARTS = {
    ".local", ".dev-secrets", "gfw-browser-profile", "browser-profile",
    "gfw-track-archive", "private-inputs", "mgrb-web", "mgrb-collector",
}
FORBIDDEN_NAMES = re.compile(
    r"(?i)(?:gfw_acquisition\.sqlite3?|collector.*\.sqlite3?|cookies?|session[-_]?state|"
    r"owner.*gfw.*\.(?:zip|csv|gpkg)|private.*(?:ais|sar|china|track).*\.(?:zip|csv|gpkg|db)|"
    r"(?:signing|watermark|private)[-_]?(?:key|secret)|receipt.*\.(?:db|sqlite3?)|"
    r"(?:chrome|chromium).*profile|\.env(?:\..+)?$)"
)
SECRET_CONTENT = re.compile(
    rb"(?i)(?:Bearer\s+[A-Za-z0-9._~-]{20,}|"
    rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})|"
    rb"-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----|"
    rb"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{8,}|"
    rb"(?:GFW_API_TOKEN|OCI_SECRET|WATERMARK_SECRET)\s*[:=]\s*[^\s$<{]{16,})"
)
PRIVATE_SOURCE_MARKER = b"MGRB_WEB_" + b"PRIVATE_IMPLEMENTATION"
MAX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_MEMBERS = 10000


def _name_findings(name: str) -> list[str]:
    normalized = name.replace("\\", "/")
    p = PurePosixPath(normalized)
    if p.is_absolute() or ".." in p.parts or re.match(r"^[A-Za-z]:", normalized):
        return [f"unsafe-path:{name}"]
    if {part.casefold() for part in p.parts} & FORBIDDEN_PARTS or FORBIDDEN_NAMES.search(p.name):
        return [f"forbidden-path:{name}"]
    return []


def audit_payload(
    name: str, payload: bytes, *, depth: int = 0, budget: list[int] | None = None,
) -> list[str]:
    """Inspect bytes and nested archives; failures/resource limits block publication."""
    budget = budget if budget is not None else [MAX_EXPANDED_BYTES, MAX_MEMBERS]
    budget[0] -= len(payload)
    budget[1] -= 1
    findings = _name_findings(name)
    if budget[0] < 0 or budget[1] < 0 or depth > 5 or len(payload) > MAX_MEMBER_BYTES:
        return findings + [f"unreviewed-resource-limit:{name}"]
    if SECRET_CONTENT.search(payload) or PRIVATE_SOURCE_MARKER in payload:
        findings.append(f"secret-or-private-source:{name}")
    if payload.startswith(b"SQLite format 3\x00") and (
        not name.lower().endswith(".gpkg") or b"gpkg_contents" not in payload
    ):
        findings.append(f"unapproved-database:{name}")
    if payload.startswith(b"0") and len(payload) < 65536:
        try:
            from cryptography.hazmat.primitives.serialization import load_der_private_key
            load_der_private_key(payload, password=None)
        except (ImportError, ValueError, TypeError):
            pass
        else:
            findings.append(f"private-key-der:{name}")
    stream = io.BytesIO(payload)
    try:
        if zipfile.is_zipfile(stream):
            with zipfile.ZipFile(stream) as archive:
                for item in archive.infolist():
                    if item.is_dir():
                        continue
                    nested = name + "!" + item.filename
                    if item.file_size > min(MAX_MEMBER_BYTES, budget[0]) or budget[1] <= 0:
                        findings.append(f"unreviewed-resource-limit:{nested}")
                        break
                    if (item.external_attr >> 16) & 0o170000 == 0o120000:
                        findings.append(f"archive-link:{nested}")
                        continue
                    findings += [f"{name}!{f}" for f in audit_payload(
                        item.filename, archive.read(item), depth=depth+1, budget=budget)]
        elif name.lower().endswith((".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz")):
            with tarfile.open(fileobj=stream, mode="r:*") as archive:
                for item in archive:
                    if item.isdir():
                        continue
                    if not item.isfile():
                        findings.append(f"archive-link-or-device:{name}!{item.name}")
                        continue
                    if item.size > min(MAX_MEMBER_BYTES, budget[0]) or budget[1] <= 0:
                        findings.append(f"unreviewed-resource-limit:{name}!{item.name}")
                        break
                    member = archive.extractfile(item)
                    if member is None:
                        findings.append(f"unreadable:{name}!{item.name}")
                    else:
                        findings += [f"{name}!{f}" for f in audit_payload(
                            item.name, member.read(), depth=depth+1, budget=budget)]
        elif name.lower().endswith((".zip", ".qgz")):
            findings.append(f"unreadable-archive:{name}")
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, tarfile.TarError):
        findings.append(f"unreadable-archive:{name}")
    return findings


def audit_paths(paths: Iterable[Path], *, root: Path | None = None) -> list[str]:
    findings: list[str] = []
    for path in paths:
        name = path.relative_to(root).as_posix() if root is not None else path.name
        if path.is_symlink():
            findings.append(f"unreviewed-link:{name}")
            continue
        try:
            if path.stat().st_size > MAX_MEMBER_BYTES:
                findings.append(f"unreviewed-resource-limit:{name}")
                continue
            for attempt in range(3):
                try:
                    payload = path.read_bytes()
                    break
                except PermissionError:
                    if attempt == 2:
                        raise
                    time.sleep(0.05)
            findings += audit_payload(name, payload)
        except OSError:
            findings.append(f"unreadable:{name}")
    return findings


def audit_public_repository(root: Path) -> list[str]:
    tracked = subprocess.check_output(
        ["git", "-C", str(root), "ls-files", "-z"]
    ).decode().split("\0")
    return audit_paths((root / item for item in tracked if item), root=root)


def audit_git_refs(root: Path, refs: list[str]) -> list[str]:
    """Check blobs reachable from selected refs, including removed files."""
    cmd = ["git", "-C", str(root)]
    objects = subprocess.check_output(cmd + ["rev-list", "--objects", *refs]).decode().splitlines()
    findings: list[str] = []
    object_ids = [line.split(" ", 1)[0] for line in objects]
    result = subprocess.run(
        cmd + ["cat-file", "--batch"],
        input=("\n".join(object_ids)+"\n").encode(), capture_output=True, check=True,
    )
    output = io.BytesIO(result.stdout)
    for line in objects:
        oid, _, name = line.partition(" ")
        header = output.readline().decode().split()
        if len(header) != 3:
            findings.append(f"unreadable-git-object:{oid}")
            break
        _, kind, size = header
        payload = output.read(int(size))
        output.read(1)
        if kind == "blob":
            findings += [f"{oid}:{f}" for f in audit_payload(name, payload)]
        elif kind in {"commit", "tag"} and SECRET_CONTENT.search(payload):
            findings.append(f"secret-git-metadata:{oid}")
    return findings


def assert_public_package(root: Path) -> None:
    findings = audit_paths(
        (p for p in root.rglob("*") if p.is_file() or p.is_symlink()), root=root,
    )
    if findings:
        raise RuntimeError("PUBLIC_PRIVATE_FIREWALL_BLOCKED: " + "; ".join(findings))
