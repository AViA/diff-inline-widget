# Development

## Requirements

- Python 3 (developed and tested with 3.12, standard library only) and git.
- Optional: Node.js and Playwright with Chromium for the browser checks. Without them those checks are skipped, not
  failed.

## Tests

```
python3 tests/run_all.py
```

The checks are listed at the top of `tests/run_all.py`. Everything runs offline: the browser check answers the renderer
request with the local `src/diff.js`.

`tests/render_check.js` can also be run on its own on a generated widget. Its header lists the expectations it accepts.
A screenshot is written if a path is given:

```
python3 skill/diff-inline-widget/scripts/make_diff.py --title t --old A --new B \
    --script-url https://cdn.jsdelivr.net/gh/test/diff-inline-widget@0000000/src/diff.js --out /tmp/w.html
node tests/render_check.js /tmp/w.html '{}' /tmp/w.png
```

`DIFF_JS` points the check at a different renderer file. `tests/check_pin.py` checks the pin, and with `--online` it
fetches the file from jsDelivr as well (see [releasing.md](releasing.md)).

## Lint

`pyright` and `ruff check` run clean on `skill`, `tests` and `tools`, with the default settings.

## Conventions

- Line endings are LF on every platform (`.gitattributes`), so patches apply the same way everywhere.
- Python code uses the standard library only. The skill script has to work in the chat sandbox without installing
  anything.
- The renderer has no build step and no dependencies. Its CSS classes carry the prefix `dw-`, and state classes
  are `is-...`.
- The script and the renderer are split into sections, with the helpers separate from the code that draws or writes
  the output.
- Comments explain why. Every function has a one-line description.

## Changing the renderer

1. Edit `src/diff.js` and run the tests. The browser checks cover the rendering, copying and the checksum.
2. If the data contract changes, change `make_diff.py` and the contract in [architecture.md](architecture.md) in the
   same commit, and bump `VERSION` in `src/diff.js`.
3. The skill script is pinned to the renderer, so a renderer change reaches users only with a new pin
   ([releasing.md](releasing.md)).

## Fixtures

`tests/fixtures/` holds the small inputs the tests use. Its README describes them.
