# Decisions

## 1. The renderer is loaded from a CDN

The widget code is a tool-call argument that the model writes out, so every character of it costs tokens and can be
mistyped. The script that builds it cannot call the widget tool, so the model has to pass the output on.

An inline template with all styles and behaviour was about 9 KB for a one-file diff, against about 1.4 KB with a
separate renderer (see [measurements.md](measurements.md)). So the widget code holds only the data and a loader, and
the renderer is fetched.

The widget therefore needs network access to the CDN, and the loader shows a plain message if the renderer cannot be
loaded. The renderer URL must not change under a published skill, hence the pin (decision 2).

## 2. jsDelivr, from a public GitHub repository, pinned to an immutable reference

Hosting is a public GitHub repo served by jsDelivr's GitHub route. jsDelivr is on the host's script allowlist, and a
widget in claude.ai loaded a script from it that way, pinned to a commit.

A commit hash or a version tag does not change, so what a skill version fetches is fixed. `tests/check_pin.py` refuses a
branch in `SCRIPT_URL`, because a branch moves, and verifies that the pinned file equals `src/diff.js`.

## 3. Counts are git's, rows are aligned for readability

The numbers in the header and per file come from `git diff --numstat`. If git is missing, GNU `diff` is used, then
`difflib` with a warning, because a hand-rolled algorithm can disagree with git by a line or two.

The rows are a different matter. A plain minimal diff can start a changed block (an object, a function) in the middle
and show it as unrelated additions and removals. `make_diff.py` re-aligns each changed region so that similar blocks
are shown modified in place. The result is verified to rebuild the new file exactly, and otherwise the minimal
alignment is used.

So a file's rows can differ from git's counts. The widget then shows a `?` with both figures, and the header keeps
git's. The resulting file is identical either way.

## 4. A checksum protects the data

The model writes the data out character by character, so a mistyped character would go unnoticed. The widget carries a
checksum that the renderer verifies (see [architecture.md](architecture.md#checksum)). On a mismatch it shows a warning
and turns copying off.

## 5. Readable renderer source, minified by jsDelivr

`src/diff.js` is plain JavaScript with no build step. The loader will request it minified: jsDelivr generates a
minified file when `.min` is added to a JavaScript file's name, so no minifier is needed in this repository.

This is not enabled yet. The delivery route has to be set up and checked first, and `tests/check_pin.py` will need to
compare against the minified form at that point.

## 6. Display defaults

- The first file is always open. Later files are open while the rows shown so far stay within 90. The rest start
  collapsed.
- Above 300 changed lines (git's counts) the widget lists files and counts only, and the user can ask for specific
  files. Larger widget code takes the model long to write out.
- Every run of added lines has a copy button. Within a removed run followed by an added run of the same length, the
  changed part of each line pair is highlighted.

## 7. Git is the oracle in the tests

Tests compare counts and patches against what git itself produces, and apply every generated patch to a copy of the
original to check that the result equals the edited tree.
