# Fixtures

Small example inputs for the tests; the content is neutral sample data.

| Folder | Purpose |
|---|---|
| `before/`, `after/` | A small JSON configuration where one object is edited in place. The readable alignment shows the changed `"type"` row as removed and added, which a minimal diff would not. |
| `five-file-change/` | Five different file types (README, `package.json`, build script, two editor configurations) as `before/` and `after/` trees. Used for the header, the `?` badges, copying, the checksum and the patch round trip. |
| `count-bug/repro/` | A TypeScript file where `difflib` counts +8 −6 and git counts +7 −5, whichever git algorithm is used. Checks that the widget shows git's counts. |

The large change for summary mode and the 90-row rule is generated in `tests/run_all.py`. Expected counts come from git
at test time.
