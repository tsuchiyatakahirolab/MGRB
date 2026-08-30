# MGRB Bootstrap Instructions for Codex

This package contains:
- the current MGRB source candidate;
- the complete `work/codex-v1-cartography/` Codex work package.

It intentionally does **not** contain a `.git` directory. The owner should create the canonical Git history locally so the initial commit SHA is genuine for this repository.

## 1. Replace the incomplete local directory

Target directory:

```text
<repository-root>
```

Back up or remove the existing incomplete directory first if it contains only `work\codex-v1-cartography`.

Extract the contents of this package directly into:

```text
<repository-root>
```

After extraction, the directory should contain at least:

```text
README.md
AGENTS.md
mgrb\
scripts\
styles\
tests\
work\codex-v1-cartography\
```

## 2. Initialize the canonical repository

Open PowerShell in:

```text
<repository-root>
```

Run:

```powershell
git init
git add .
git commit -m "Initialize MGRB public research base"
git branch -M main
```

If Git asks for identity, configure your normal Git identity first:

```powershell
git config user.name "YOUR NAME"
git config user.email "YOUR GIT EMAIL"
```

Then run the commit command again.

## 3. Verify the baseline

Run:

```powershell
git rev-parse --show-toplevel
git status --short --branch
git branch --show-current
git rev-parse HEAD
```

Expected:
- repository root resolves to the fresh clone's `<repository-root>`;
- current branch is `main`;
- `git rev-parse HEAD` returns a real SHA;
- working tree is clean.

That commit is the legitimate starting baseline for this new MGRB repository.

## 4. Start Codex

Then give Codex exactly:

```text
Read `work/codex-v1-cartography/CODEX_PROMPT.md` completely and execute it. Treat the current MGRB repository as the canonical source tree and do not modify files outside this repository. Work on branch `feat/v1-cartography-system`. Do not publish or tag v1.0. Do not declare completion until all automated acceptance criteria pass and the required real QGIS visual-review artifacts are generated. Stop at `READY_FOR_OWNER_VISUAL_REVIEW` and report exact commands, tests, output paths, branch, and start/end commit SHAs.
```

Codex should then create/switch to `feat/v1-cartography-system` and use the `main` commit SHA as the start SHA.

## Important

Do not initialize the repository until the actual source files are present. The source tree in this package is the intended baseline candidate; by committing it locally, the owner establishes it as the canonical Git baseline for subsequent Codex work.
