# MGRB Codex v1.0 Cartography Work Package

This directory belongs inside the MGRB repository:

```text
MGRB/
  work/
    codex-v1-cartography/
      ...
```

Run Codex from the **MGRB repository root**, not from a parent directory containing other projects.

The current MGRB repository is the only implementation target. Do not unpack or create a separate MGRB project.

## Start command for Codex

From the MGRB repository root, give Codex this instruction:

> Read `work/codex-v1-cartography/CODEX_PROMPT.md` completely and execute it. Treat the current MGRB repository as the canonical source tree. Do not declare v1.0 complete or create a release. Stop only at `READY_FOR_OWNER_VISUAL_REVIEW` after all automated acceptance criteria pass and the required visual-review artifacts are generated.

## Work isolation

Use branch:

```text
feat/v1-cartography-system
```

Temporary downloads, render caches, and large upstream public datasets must not be committed unless the existing MGRB data policy explicitly permits them.

No AIS, SAR, vessel-level data, case library, anomaly-detection output, China-specific operational material, or research-group internal data may be added to this repository.
