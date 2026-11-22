# Releasing

## The pin

`SCRIPT_URL` in `skill/diff-inline-widget/scripts/make_diff.py` names the renderer on jsDelivr:

```
https://cdn.jsdelivr.net/gh/<owner>/diff-inline-widget@<ref>/src/diff.js
```

`<ref>` is a commit hash while developing and a version tag (`v1.2.3`) for a release. `tests/check_pin.py` refuses a
branch name, because a branch moves. `make_diff.py` and `tools/package.py` refuse to run while `OWNER` and `REF` are
still placeholders.

## Branches

- `dev` is where work happens. Its pin is a commit hash.
- `master` holds releases, each tagged `vX.Y.Z`.

## Pinning on `dev`

1. Commit the renderer change (`src/diff.js` and its tests).
2. Set `<ref>` in `SCRIPT_URL` to that commit's hash.
3. Run `python3 tests/check_pin.py`. It checks that the pin is a commit or tag, and that the file at that ref in the
   local git history equals `src/diff.js`. Add `--online` to compare the bytes jsDelivr serves as well.
4. Run `python3 tests/run_all.py`.
5. Commit the new pin. This commit changes only `make_diff.py`, so the pin stays valid.

## Cutting a release

1. Update `VERSION` in `src/diff.js`, and make sure `SKILL.md` describes the current behaviour.
2. Set `SCRIPT_URL` to `@vX.Y.Z` (the tag name is known in advance) and commit.
3. Tag that commit `vX.Y.Z`. Never move or reuse a published tag.
4. Run `python3 tests/run_all.py` and `python3 tests/check_pin.py --online`.
5. Run `python3 tools/package.py`. The package is `dist/diff-inline-widget.skill`.
6. Merge to `master`.
7. Create a GitHub release from the tag. Its notes, written from the commit messages since the last tag, are the change
   record. There is no changelog file.

## Versioning

The script and the renderer are versioned together, because the script is pinned to the renderer that reads its data.
The data contract is internal to them and does not decide the version number on its own.

- **Patch**: fixes and internal changes that do not change how the skill works or looks.
- **Minor**: new features that keep the existing behaviour, including additions to the data contract.
- **Major**: substantial changes to how the skill works or looks.
