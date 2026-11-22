# Architecture

`make_diff.py` builds the widget code from two sets of files. The chat's widget tool runs that code, and the loader in
it fetches the renderer (`src/diff.js`) from jsDelivr. The renderer draws the diff. Why the renderer is not part of the
widget code is explained in [decisions.md](decisions.md#1-the-renderer-is-loaded-from-a-cdn).

```
make_diff.py ---> widget code (loader + data) ---> show_widget
                                                       |
                                                       v  loader fetches
                  https://cdn.jsdelivr.net/gh/<owner>/diff-inline-widget@<ref>/src/diff.js
                                                       |
                                  DiffWidget.render(data, root) draws the diff
```

## Widget code

`make_diff.py` fills the `LOADER` template with the title and the data. The result is:

1. a visually hidden heading for screen readers,
2. an empty `div#root`,
3. one script that holds the data as a JavaScript object, appends a `<script src=...>` for the renderer to the document
   head, calls `DiffWidget.render(data, root)` when it loads, and writes a plain message into the root if the script
   fails to load or takes more than 8 seconds.

## Data contract

```js
{
  title,            // short title shown in the header
  sum,              // checksum of `files`, 8 hex digits (see below)
  files: [
    {
      p,            // path
      s,            // "" for a changed file, "new" or "deleted"
      g: [0, 0],    // [added, removed]: git's counts for this file (`git diff --numstat`)
      h: [          // hunks; an empty list shows the file with its counts only (summary mode)
        {
          o,        // first old line number of the hunk
          n,        // first new line number of the hunk
          r,        // rows as one string, one row per line: " " context, "-" removed, "+" added, then the text
        },
      ],
    },
  ],
}
```

The header totals are the sums of `g`.

### Checksum

`sum` is FNV-1a over the UTF-16 code units of path, status, counts and every hunk. `make_diff.py` computes it in Python
and the renderer recomputes it in the browser. If the two values differ, the widget shows a warning and does not offer
copying. The loader is not covered by the checksum.

## Renderer

`src/diff.js` defines `window.DiffWidget = { version, render, checksum }`. `render` injects the stylesheet once, draws
the header and the file blocks, and installs a single `copy` handler. The handler makes a copied selection contain only
the code: no line numbers, no markers, blank lines kept, and an empty line between files.

## Host constraints

The widget code runs in the chat page's sandbox. The rules that matter here:

- The widget code must not contain a literal closing script tag or an HTML comment start. The host cuts the code
  there. `js_json` writes the `<` of such sequences as `\u003c`, and the tests check every generated widget.
- The host may style buttons. The copy button sets `padding: 0 !important` and a fixed icon size so it is not squeezed.
  A test injects a hostile style to check this.
- Colours come from CSS variables that the host defines: `--border`, `--radius`, `--surface-1`, `--font-mono`,
  `--text-muted`, `--text-secondary`, `--text-success`, `--text-danger`. The tests define stand-in values.
- Scripts can only be loaded from four hosts: `cdnjs.cloudflare.com`, `esm.sh`, `cdn.jsdelivr.net` and `unpkg.com`.
  Google Fonts is allowed for fonts.

## Pinning

The loader names the renderer by an immutable reference, a commit hash on `dev` or a version tag for a release. See
[releasing.md](releasing.md).
