#!/usr/bin/env bash
set -euo pipefail

REPO_NAME="${1:-maritime-geospatial-research-base}"
OWNER="${2:-$(gh api user --jq .login)}"
FULL_REPO="${OWNER}/${REPO_NAME}"

if ! command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI (gh) is required." >&2
  exit 1
fi

gh auth status >/dev/null

if [ ! -d .git ]; then
  git init -b main
fi

python3 - "$FULL_REPO" <<'PY'
from pathlib import Path
import sys
repo = sys.argv[1]
p = Path("CITATION.cff")
s = p.read_text(encoding="utf-8")
line = f'repository-code: "https://github.com/{repo}"\n'
if "repository-code:" in s:
    import re
    s = re.sub(r'^repository-code:.*$', line.rstrip(), s, flags=re.M) + ("\n" if not s.endswith("\n") else "")
else:
    marker = "license: Apache-2.0\n"
    s = s.replace(marker, marker + line)
p.write_text(s, encoding="utf-8")
PY

git add .
if ! git diff --cached --quiet; then
  git commit -m "Initialize MGRB public research infrastructure"
fi

gh repo create "$FULL_REPO" \
  --public \
  --source=. \
  --remote=origin \
  --push \
  --description "A reproducible, QGIS-ready geospatial base for maritime research"

echo "Published: https://github.com/${FULL_REPO}"
echo "Wait for core-ci and qgis-ci to pass before creating the v1.0.0 release tag."
