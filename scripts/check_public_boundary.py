"""Fail a public build on detected private material; never emit matched values."""
import argparse
import json
from pathlib import Path

from mgrb.public_boundary import audit_git_refs, audit_public_repository

parser = argparse.ArgumentParser()
parser.add_argument("--git-ref", action="append", default=[])
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
findings = audit_public_repository(root)
if args.git_ref:
    findings += audit_git_refs(root, args.git_ref)
print(json.dumps({"passed": not findings, "findings": findings}, indent=2))
raise SystemExit(bool(findings))
