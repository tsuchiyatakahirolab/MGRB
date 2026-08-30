from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable
from pathlib import Path

FORBIDDEN_PARTS = {
    ".local",
    "gfw-browser-profile",
    "browser-profile",
    "gfw-track-archive",
    "private-inputs",
}
FORBIDDEN_NAMES = re.compile(
    r"(?i)(?:gfw_acquisition\.sqlite3?|collector.*\.sqlite3?|cookies?|session[-_]?state|"
    r"owner.*gfw.*\.(?:zip|csv|gpkg)|private.*(?:ais|sar).*\.(?:zip|csv|gpkg))"
)
SECRET_CONTENT = re.compile(
    rb"(?i)(?:Bearer\s+[A-Za-z0-9._-]{12,}|GFW_API_TOKEN\s*=\s*[^\s$<{]{8,}|"
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)"
)


def audit_paths(paths: Iterable[Path]) -> list[str]:
    findings: list[str] = []
    for path in paths:
        normalized = path.as_posix()
        lowered_parts = {part.casefold() for part in path.parts}
        if lowered_parts & FORBIDDEN_PARTS or FORBIDDEN_NAMES.search(path.name):
            findings.append(f"forbidden-path:{normalized}")
            continue
        if path.is_file() and path.stat().st_size <= 5 * 1024 * 1024:
            try:
                payload = path.read_bytes()
            except OSError:
                continue
            if SECRET_CONTENT.search(payload):
                findings.append(f"secret-content:{normalized}")
    return findings


def audit_public_repository(root: Path) -> list[str]:
    tracked = (
        subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"])
        .decode("utf-8")
        .split("\0")
    )
    return audit_paths(root / item for item in tracked if item)


def assert_public_package(root: Path) -> None:
    findings = audit_paths(path for path in root.rglob("*") if path.is_file())
    if findings:
        raise RuntimeError("PUBLIC_PRIVATE_FIREWALL_BLOCKED: " + "; ".join(findings))
