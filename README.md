# diff-inline-widget

A Claude skill that embeds a GitHub-style diff in a chat reply. Each changed file gets a collapsible block with its
own +/- counts, changed parts of lines are highlighted, and every run of added lines has a copy button. Line numbers
and +/- markers can't be selected or copied.

It needs Claude's inline widget tool (`show_widget`) and the code sandbox, so it only works in claude.ai chat. It has
been tried in a browser only. The desktop and mobile apps are untested. Anywhere else (Claude Code, the API) the skill
does not apply, and its instructions tell the agent to ignore it.

A script builds the diff from the real files, so the numbers in the header are `git diff --numstat` counts. The widget
code holds only the diff data and a loader, and the browser fetches the styles and behaviour from
[`src/diff.js`](src/diff.js) on jsDelivr. The widget also carries a checksum of the data it shows. If a character
changed on the way to the screen, it says so and turns copying off. The same script writes a git patch that
`git apply` accepts, with or without a repository.

## How it works

```
 original files + edited files
              |
              v
        make_diff.py  (git: counts and patch)
              |  widget code = loader + diff data
              v
        show_widget  ---- loads ---->  https://cdn.jsdelivr.net/gh/<owner>/diff-inline-widget@<ref>/src/diff.js
              ^                                          |
              +-------------- draws the diff ------------+
```

See [docs/architecture.md](docs/architecture.md) for the details and [docs/measurements.md](docs/measurements.md) for
the estimated token cost.

## Install

1. Pin the renderer URL (see [docs/releasing.md](docs/releasing.md)) and build the package:
   `python3 tools/package.py`. It writes `dist/diff-inline-widget.skill`.
2. Add the `.skill` file to Claude in the skills settings.

## Using the script directly

```
python3 skill/diff-inline-widget/scripts/make_diff.py --title "Fix the build" \
    --old original/ --new edited/ --patch-out change.patch --out widget.html
```

`--old` and `--new` take two files or two directory trees. `make_diff.py --help` lists the other options.

The instructions for the agent are in [`SKILL.md`](skill/diff-inline-widget/SKILL.md).

## Repository layout

| Path | Contents |
|---|---|
| `src/diff.js` | The renderer that jsDelivr serves: styles and behaviour. |
| `skill/diff-inline-widget/` | What gets packaged: `SKILL.md` and `scripts/make_diff.py` (the package also gets a copy of `LICENSE`). |
| `tests/` | The self-test, the browser check, the pin check and small fixtures. |
| `tools/package.py` | Builds `dist/diff-inline-widget.skill`. |
| `docs/` | Architecture, decisions, measurements, development and releasing. |
| `AGENTS.md` | Notes for coding agents working on this repository. |

## Development

```
python3 tests/run_all.py     # counts, patches, widget code and, if available, the browser checks
python3 tests/check_pin.py   # the pinned URL serves exactly src/diff.js
```

See [docs/development.md](docs/development.md) for setup.

## Limitations

- Text files only: binary and non-UTF-8 files are skipped and reported.
- Rows are aligned for readability, which can differ from git's alignment. Such a file gets a `?` that explains it, and
  the counts stay git's.
- Changes above 300 lines are listed with counts only, unless the full rows are requested.
- The widget needs network access to the CDN. If the script cannot be loaded, the widget says so.

## License

Source-available, free for noncommercial use. See [LICENSE](LICENSE).
