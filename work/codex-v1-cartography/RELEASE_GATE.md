# MGRB v1.0 Release Gate

Codex is not authorized to publish, tag, or declare v1.0 released.

## Codex terminal state

Codex may end only at:

`READY_FOR_OWNER_VISUAL_REVIEW`

after all automated criteria pass.

## Owner-only gate

The owner must review:
- canonical Taiwan East/South local map;
- alternate/custom-theme local map;
- regional map;
- Western Pacific map;
- Pacific-wide map;
- grayscale map;
- journal-width previews.

Only after owner approval should the repository proceed to:
1. final corrections;
2. clean CI rerun;
3. release commit;
4. `v1.0.0` tag;
5. GitHub Release;
6. citation/version metadata finalization;
7. public website linkage.

## Failure handling

If automated requirements fail, do not use `READY_FOR_OWNER_VISUAL_REVIEW`.

If only subjective design choices remain, explicitly list them in the final report and generate the review assets.

Do not conceal blockers or substitute mocked QGIS success for a real build.
