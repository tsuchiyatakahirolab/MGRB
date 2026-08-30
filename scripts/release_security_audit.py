#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PREFIXES = (
    ".git/",
    ".local/",
    ".tmp/",
    ".cache/",
    ".tools/",
    ".venv/",
    "build/",
    "data/raw/",
    "data/derived/",
    "outputs/",
    "qgis-projects/generated/",
)
FORBIDDEN_TRACKED_PREFIXES = (".local/", ".tmp/", "data/raw/", "data/derived/")
TEXT_LIMIT = 8 * 1024 * 1024
SELF_PATH = "scripts/release_security_audit.py"
PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "bearer_token": re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{20,}={0,2}"),
    "google_oauth_token": re.compile(r"\bya29\.[A-Za-z0-9_-]{20,}"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{8,}\b"),
    "assigned_secret": re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?token|secret|password)\s*[:=]\s*"
        r"['\"]?[A-Za-z0-9._~+/-]{20,}"
    ),
    "owner_dropbox_path": re.compile(r"(?i)(?:SFC-CNS Dropbox|AIS_DATA|events-mmsi-)"),
    "local_absolute_path": re.compile(r"(?i)\b[A-Z]:\\Users\\[^\\\s]+\\"),
}


@dataclass(frozen=True)
class Finding:
    scope: str
    check: str
    path: str
    commit: str | None
    line: int | None
    severity: str
    excerpt: str


def _git(*args: str, text: bool = True) -> str | bytes:
    options = {"text": True, "errors": "replace"} if text else {}
    return subprocess.check_output(["git", *args], cwd=ROOT, **options)


def _text_findings(content: str, *, scope: str, path: str, commit: str | None) -> list[Finding]:
    findings = []
    for line_number, line in enumerate(content.splitlines(), 1):
        for name, pattern in PATTERNS.items():
            if pattern.search(line):
                if name == "owner_dropbox_path" and path.startswith("tests/test_data_census_"):
                    continue
                severity = "BLOCKER" if name != "local_absolute_path" else "REVIEW"
                findings.append(
                    Finding(
                        scope,
                        name,
                        path,
                        commit,
                        line_number,
                        severity,
                        pattern.sub("[REDACTED-MATCH]", line)[:240],
                    )
                )
    return findings


def scan_working_tree() -> list[Finding]:
    findings = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT).as_posix()
        if (
            relative == SELF_PATH
            or relative.startswith(EXCLUDED_PREFIXES)
            or path.stat().st_size > TEXT_LIMIT
        ):
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        findings.extend(_text_findings(content, scope="working_tree", path=relative, commit=None))
    return findings


def scan_tracked_files() -> tuple[list[Finding], list[str]]:
    tracked = [line for line in str(_git("ls-files")).splitlines() if line]
    forbidden = [
        path
        for path in tracked
        if path.startswith(FORBIDDEN_TRACKED_PREFIXES) and not path.endswith("/.gitkeep")
    ]
    findings = []
    for relative in tracked:
        if relative == SELF_PATH:
            continue
        path = ROOT / relative
        if not path.is_file() or path.stat().st_size > TEXT_LIMIT:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        findings.extend(_text_findings(content, scope="tracked", path=relative, commit=None))
    return findings, forbidden


def scan_history() -> list[Finding]:
    findings = []
    seen_blobs: set[str] = set()
    commits = str(_git("rev-list", "HEAD")).splitlines()
    for commit in commits:
        entries = str(_git("ls-tree", "-r", commit)).splitlines()
        for entry in entries:
            metadata, path = entry.split("\t", 1)
            _, kind, blob = metadata.split()
            if path == SELF_PATH or kind != "blob" or blob in seen_blobs:
                continue
            seen_blobs.add(blob)
            size = int(str(_git("cat-file", "-s", blob)).strip())
            if size > TEXT_LIMIT:
                continue
            content = _git("cat-file", "blob", blob, text=False)
            try:
                decoded = bytes(content).decode("utf-8")
            except UnicodeDecodeError:
                continue
            findings.extend(_text_findings(decoded, scope="git_history", path=path, commit=commit))
    return findings


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    working = scan_working_tree()
    tracked, forbidden_tracked = scan_tracked_files()
    history = scan_history()
    all_findings = [*working, *tracked, *history]
    blockers = [finding for finding in all_findings if finding.severity == "BLOCKER"]
    payload = {
        "schema": "mgrb-release-security-audit-1.0",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "head": str(_git("rev-parse", "HEAD")).strip(),
        "branch": str(_git("branch", "--show-current")).strip(),
        "excluded_local_roots": list(EXCLUDED_PREFIXES),
        "tracked_forbidden_paths": forbidden_tracked,
        "findings": [asdict(finding) for finding in all_findings],
        "summary": {
            "working_tree_findings": len(working),
            "tracked_findings": len(tracked),
            "history_findings": len(history),
            "blockers": len(blockers) + len(forbidden_tracked),
            "review_items": sum(finding.severity == "REVIEW" for finding in all_findings),
        },
        "passed": not blockers and not forbidden_tracked,
        "interpretation": (
            "Local absolute development paths are REVIEW findings. Credentials, owner/private "
            "dataset paths, private keys, tokens, and forbidden tracked roots are blockers."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    raise SystemExit(0 if payload["passed"] else 1)


if __name__ == "__main__":
    main()
