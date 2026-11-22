#!/usr/bin/env python3
"""Build the widget_code for a GitHub-style diff and, optionally, the matching git .patch.

Usage:
  make_diff.py --title T --old OLD --new NEW [--files REL ...] [--context N] [--exclude NAME ...]
               [--patch-out FILE.patch] [--limit 300] [--full] [--out FILE]

  OLD and NEW are two files or two directory trees (e.g. original and edited copies of a repo).
  Rows use the "readable" alignment; the +/- counts are always git's (git diff --numstat).

The output is a small loader plus the diff data. The loader pulls the renderer (src/diff.js of this repository) from
SCRIPT_URL, so the retyped widget code stays small. The script writes it to --out and prints a summary. Only the
Python standard library is used; git or GNU diff, when present, give the git-exact counts and the patch.
"""

import argparse
import difflib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------------------------------------------------

# The renderer is loaded from this URL. OWNER and REF are placeholders until the repository is published: while
# developing, pin a commit (.../diff-inline-widget@<commit sha>/src/diff.js); for a release, pin its tag (@v1.0.0).
# Both are immutable on jsDelivr. tests/check_pin.py verifies that the pinned file equals src/diff.js.
SCRIPT_URL = "https://cdn.jsdelivr.net/gh/OWNER/diff-inline-widget@REF/src/diff.js"

# The widget code: a heading for screen readers, the data, and the loader. __TITLE_HTML__, __DATA__ and __URL__ are
# filled in. No literal closing script tag or HTML comment may appear anywhere in it (the host cuts the code there).
LOADER = (
    '<h2 class="sr-only">GitHub-style diff: __TITLE_HTML__. Added lines are green, removed lines are red.</h2>\n'
    '<div id="root"></div>\n'
    "<script>\n"
    "(function(){\n"
    "var D=__DATA__;\n"
    'var root=document.getElementById("root");\n'
    'var s=document.createElement("script");\n'
    "var t=setTimeout(fail,8000);\n"
    'function fail(){root.textContent="The diff could not be drawn here because its script did not load. '
    'Use the patch file instead."}\n'
    "s.onload=function(){clearTimeout(t);DiffWidget.render(D,root)};\n"
    "s.onerror=function(){clearTimeout(t);fail()};\n"
    's.src="__URL__";\n'
    "(document.head||document.documentElement).appendChild(s)\n"
    "})();\n"
    "</script>\n"
)

DEFAULT_EXCLUDES = {".git", "node_modules", "target", "dist", "gen", "__pycache__", ".venv"}

HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

# ---------------------------------------------------------------------------------------------------------------------
# Reading the input
# ---------------------------------------------------------------------------------------------------------------------


def read_lines(path):
    """Lines of a text file without line endings, or None for a binary / non-UTF-8 file."""
    data = Path(path).read_bytes()
    if b"\0" in data[:8000]:
        return None

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None

    lines = [line.removesuffix("\r") for line in text.split("\n")]
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def collect(root, excludes):
    """{relative posix path: Path} for a file or for every file under a directory, skipping excluded directories."""
    root = Path(root)
    if root.is_file():
        return {root.name: root}

    found = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in excludes]
        for name in filenames:
            path = Path(dirpath) / name
            found[path.relative_to(root).as_posix()] = path
    return found


# ---------------------------------------------------------------------------------------------------------------------
# Readable alignment
#
# A plain difference algorithm can start a changed block (an object, a function) in the middle. The code below
# re-aligns each changed region so that similar blocks are shown modified in place. The result is checked
# (_valid) and replaced by the plain alignment if it does not rebuild the new file exactly.
# ---------------------------------------------------------------------------------------------------------------------


def _indent(line):
    """Width of the leading whitespace, or None for a blank line."""
    return len(line) - len(line.lstrip(" \t")) if line.strip() else None


def _is_closer(line):
    text = line.lstrip()
    return text[:1] in ("}", "]", ")") or text == "end"


def _is_opener(line):
    return line.rstrip().endswith(("{", "[", "(", ":"))


def _expand(lines, start, stop, level):
    """Grow [start, stop) to the enclosing blocks at indentation `level` (opener line, deeper lines, closer)."""
    count = len(lines)

    new_start = start
    if not (start < stop and (_indent(lines[start]) or 0) <= level):
        k = start - 1
        while k >= 0 and (_indent(lines[k]) is None or _indent(lines[k]) > level):
            k -= 1
        if k >= 0:
            new_start = k if _is_opener(lines[k]) and not _is_closer(lines[k]) else k + 1

    m = stop
    while m < count and (_indent(lines[m]) is None or _indent(lines[m]) > level):
        m += 1
    new_stop = m + 1 if m < count and _is_closer(lines[m]) and _indent(lines[m]) == level else m

    return min(new_start, start), max(new_stop, stop)


def _chunks(lines, low, high, level):
    """Split lines[low:high] into blocks that each start at a line with indentation <= `level`."""
    chunks, start = [], None
    for k in range(low, high):
        indent = _indent(lines[k])
        if indent is not None and indent <= level and not _is_closer(lines[k]) and start is not None:
            chunks.append((start, k))
            start = k
        elif start is None:
            start = k
    if start is not None:
        chunks.append((start, high))
    return chunks


def _similarity(a, b, chunk_a, chunk_b):
    """0..1 similarity of two blocks; very short blocks are compared character by character."""
    lines_a, lines_b = a[chunk_a[0] : chunk_a[1]], b[chunk_b[0] : chunk_b[1]]
    if len(lines_a) <= 3 and len(lines_b) <= 3:
        return difflib.SequenceMatcher(None, "\n".join(lines_a), "\n".join(lines_b), autojunk=False).ratio()
    return difflib.SequenceMatcher(None, lines_a, lines_b, autojunk=False).ratio()


def _refine_region(a, b, a_start, a_stop, b_start, b_stop, level):
    """Opcodes for one region, pairing similar blocks by position so that changed blocks stay in place."""
    chunks_a, chunks_b = _chunks(a, a_start, a_stop, level), _chunks(b, b_start, b_stop, level)
    count_a, count_b = len(chunks_a), len(chunks_b)

    # Similarity of every block pair worth pairing; a pair at the same position gets a small bonus.
    similar = {}
    for i in range(count_a):
        for j in range(count_b):
            value = _similarity(a, b, chunks_a[i], chunks_b[j])
            if value >= 0.6:
                similar[i, j] = value + (0.08 if i == j else 0)

    # best[i][j]: the highest total similarity reachable from block pair (i, j) onwards.
    best = [[0.0] * (count_b + 1) for _ in range(count_a + 1)]
    for i in range(count_a - 1, -1, -1):
        for j in range(count_b - 1, -1, -1):
            paired = similar[i, j] + best[i + 1][j + 1] if (i, j) in similar else -1
            best[i][j] = max(best[i + 1][j], best[i][j + 1], paired)

    ops = []
    a_done, b_done = a_start, b_start

    def flush(a_end, b_end):
        """Emit the unpaired lines up to (a_end, b_end) as one delete, insert or replace."""
        nonlocal a_done, b_done
        if a_done < a_end and b_done < b_end:
            ops.append(("replace", a_done, a_end, b_done, b_end))
        elif a_done < a_end:
            ops.append(("delete", a_done, a_end, b_done, b_done))
        elif b_done < b_end:
            ops.append(("insert", a_done, a_done, b_done, b_end))
        a_done, b_done = a_end, b_end

    i = j = 0
    while i < count_a and j < count_b:
        if (i, j) in similar and abs(best[i][j] - (similar[i, j] + best[i + 1][j + 1])) < 1e-9:
            flush(chunks_a[i][0], chunks_b[j][0])
            block_a = a[chunks_a[i][0] : chunks_a[i][1]]
            block_b = b[chunks_b[j][0] : chunks_b[j][1]]
            for tag, x1, x2, y1, y2 in difflib.SequenceMatcher(None, block_a, block_b, autojunk=False).get_opcodes():
                ops.append((tag, chunks_a[i][0] + x1, chunks_a[i][0] + x2, chunks_b[j][0] + y1, chunks_b[j][0] + y2))
            a_done, b_done = chunks_a[i][1], chunks_b[j][1]
            i, j = i + 1, j + 1
        elif best[i][j] == best[i + 1][j]:
            i += 1
        else:
            j += 1

    flush(a_stop, b_stop)
    return ops


def _changed(ops):
    """Number of lines on either side that the opcodes change."""
    return sum((op[2] - op[1]) + (op[4] - op[3]) for op in ops if op[0] != "equal")


def _trim_blank_edges(a, b, a_start, a_stop, b_start, b_stop):
    """Shrink a region by the blank lines both sides have at its start and end; they stay unchanged context."""
    while a_start < a_stop and b_start < b_stop and not a[a_start].strip() and not b[b_start].strip():
        a_start += 1
        b_start += 1

    while a_start < a_stop and b_start < b_stop and not a[a_stop - 1].strip() and not b[b_stop - 1].strip():
        a_stop -= 1
        b_stop -= 1

    return a_start, a_stop, b_start, b_stop


def refine_opcodes(a, b, opcodes):
    """Re-align each changed region so that blocks (objects, functions, ...) are modified in place."""
    # 1. Grow every change to the enclosing blocks; overlapping regions are merged.
    regions = []
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            continue

        indents = [x for x in (_indent(line) for line in a[i1:i2] + b[j1:j2]) if x is not None]
        if not indents:
            continue

        level = min(indents)
        grown_a, grown_b = _expand(a, i1, i2, level), _expand(b, j1, j2, level)
        if regions and (grown_a[0] < regions[-1][1] or grown_b[0] < regions[-1][3]):
            last = regions[-1]
            regions[-1] = (last[0], max(last[1], grown_a[1]), last[2], max(last[3], grown_b[1]), min(last[4], level))
        else:
            regions.append((grown_a[0], grown_a[1], grown_b[0], grown_b[1], level))

    # 2. Re-align each region, keeping the plain alignment where the refined one changes much more.
    out, a_done, b_done = [], 0, 0
    for a1, a2, b1, b2, level in regions:
        a1, a2, b1, b2 = _trim_blank_edges(a, b, a1, a2, b1, b2)
        if a1 > a_done:
            out.append(("equal", a_done, a1, b_done, b_done + (a1 - a_done)))

        plain = [
            (tag, a1 + x1, a1 + x2, b1 + y1, b1 + y2)
            for tag, x1, x2, y1, y2 in difflib.SequenceMatcher(None, a[a1:a2], b[b1:b2], autojunk=False).get_opcodes()
        ]
        refined = _refine_region(a, b, a1, a2, b1, b2, level)
        out += refined if _changed(refined) <= _changed(plain) * 1.6 + 6 else plain
        a_done, b_done = a2, b2

    if a_done < len(a) or b_done < len(b):
        out.append(("equal", a_done, len(a), b_done, len(b)))
    return out


def _merge_equal(ops):
    """Join neighbouring "equal" opcodes and drop empty ones."""
    merged = []
    for op in ops:
        if op[0] == "equal" and merged and merged[-1][0] == "equal":
            merged[-1] = ("equal", merged[-1][1], op[2], merged[-1][3], op[4])
        elif op[1] != op[2] or op[3] != op[4]:
            merged.append(op)
    return merged


def _valid(a, b, ops):
    """True if the opcodes cover both sequences without gaps and their "equal" parts really are equal."""
    a_pos = b_pos = 0
    for tag, i1, i2, j1, j2 in ops:
        if i1 != a_pos or j1 != b_pos:
            return False
        if tag == "equal" and a[i1:i2] != b[j1:j2]:
            return False
        a_pos, b_pos = i2, j2
    return a_pos == len(a) and b_pos == len(b)


class _Refined(difflib.SequenceMatcher[str]):
    """A SequenceMatcher whose opcodes use the readable alignment (the plain ones if that goes wrong)."""

    # SequenceMatcher sets these in set_seq1/set_seq2 but does not declare them for type checkers.
    a: list[str]
    b: list[str]

    def get_opcodes(self):
        plain = super().get_opcodes()
        try:
            refined = _merge_equal(refine_opcodes(self.a, self.b, plain))
        except Exception:  # noqa: BLE001 - whatever goes wrong here, the plain alignment is still correct
            return plain
        return refined if _valid(self.a, self.b, refined) else plain


# ---------------------------------------------------------------------------------------------------------------------
# Counts: always git's
# ---------------------------------------------------------------------------------------------------------------------

_warned = set()


def _warn_once(key, message):
    if key not in _warned:
        _warned.add(key)
        print("warning: " + message, file=sys.stderr)


def git_counts(path_a, path_b, lines_a, lines_b):
    """(added, removed, source) the way `git diff --numstat` counts them; falls back to GNU diff, then difflib."""
    a = str(path_a) if path_a else os.devnull
    b = str(path_b) if path_b else os.devnull

    if shutil.which("git"):
        result = subprocess.run(
            ["git", "-c", "diff.algorithm=myers", "diff", "--no-index", "--numstat", "--", a, b],
            check=False,
            capture_output=True,
            text=True,
        )
        match = re.match(r"(\d+)\t(\d+)\t", result.stdout)
        if match:
            return int(match.group(1)), int(match.group(2)), "git"

    if shutil.which("diff"):
        result = subprocess.run(
            ["diff", "-U0", "--", a, b], check=False, capture_output=True, text=True, errors="replace"
        )
        if result.returncode in (0, 1):
            lines = result.stdout.split("\n")[2:]
            added = sum(line.startswith("+") for line in lines)
            removed = sum(line.startswith("-") for line in lines)
            return added, removed, "diff"

    _warn_once(
        "nogit", "neither git nor GNU diff found: +/- counts come from difflib and may differ from git by a line or two"
    )
    opcodes = difflib.SequenceMatcher(None, lines_a, lines_b, autojunk=False).get_opcodes()
    changes = [op for op in opcodes if op[0] != "equal"]
    return sum(op[4] - op[3] for op in changes), sum(op[2] - op[1] for op in changes), "difflib"


def row_counts(file_data):
    """(added, removed) rows actually shown for one file; they can differ from git's counts."""
    rows = [row for hunk in file_data["h"] for row in hunk["r"].split("\n")]
    return sum(row[:1] == "+" for row in rows), sum(row[:1] == "-" for row in rows)


# ---------------------------------------------------------------------------------------------------------------------
# Diff data
# ---------------------------------------------------------------------------------------------------------------------


def build_hunks(a, b, context, readable):
    """Hunks [{o, n, r}] for one file: first old line, first new line and one row per line (" ", "-" or "+")."""
    matcher_class = _Refined if readable else difflib.SequenceMatcher
    matcher = matcher_class(None, a, b, autojunk=False)

    hunks = []
    for group in matcher.get_grouped_opcodes(context):
        rows = []
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                rows += [" " + line for line in a[i1:i2]]
            else:
                rows += ["-" + line for line in a[i1:i2]] + ["+" + line for line in b[j1:j2]]

        old_count = sum(1 for row in rows if row[0] != "+")
        new_count = sum(1 for row in rows if row[0] != "-")
        first_old = group[0][1] + (1 if old_count else 0)
        first_new = group[0][3] + (1 if new_count else 0)
        hunks.append({"o": first_old, "n": first_new, "r": "\n".join(rows)})
    return hunks


def diff_trees(old, new, only, context, excludes, readable=True):
    """The diff data for two files or trees: [{p: path, s: status, g: [added, removed], h: hunks}]."""
    old_files, new_files = collect(old, excludes), collect(new, excludes)
    if Path(old).is_file() and Path(new).is_file():
        new_files = {next(iter(old_files)): Path(new)}

    data, binary = [], []
    for name in only or sorted(set(old_files) | set(new_files)):
        path_a, path_b = old_files.get(name), new_files.get(name)
        if path_a and path_b and path_a.read_bytes() == path_b.read_bytes():
            continue

        a = read_lines(path_a) if path_a else []
        b = read_lines(path_b) if path_b else []
        if a is None or b is None:
            binary.append(name)
            continue
        if a == b:
            continue

        status = "new" if not path_a else "deleted" if not path_b else ""
        added, removed, _source = git_counts(path_a, path_b, a, b)
        data.append({"p": name, "s": status, "g": [added, removed], "h": build_hunks(a, b, context, readable)})

    if binary:
        shown = ", ".join(binary[:5]) + (f" and {len(binary) - 5} more" if len(binary) > 5 else "")
        print(
            f"skipped {len(binary)} changed binary / non-UTF-8 file(s): {shown} (not in the widget or the patch)",
            file=sys.stderr,
        )
    return data


# ---------------------------------------------------------------------------------------------------------------------
# Patch
# ---------------------------------------------------------------------------------------------------------------------


def rewrite_patch(text):
    """Turn `git diff --no-index` paths into a/<path> b/<path> (it prints a/a/<path> b/b/<path>; for new files
    a/b/<path> b/b/<path>). Hunk lines are left alone."""
    out = []
    old_left = new_left = 0  # lines still to read in the current hunk

    for line in text.split("\n"):
        if old_left > 0 or new_left > 0:
            first = line[:1]
            if first in (" ", ""):
                old_left -= 1
                new_left -= 1
            elif first == "-":
                old_left -= 1
            elif first == "+":
                new_left -= 1
            out.append(line)
            continue

        hunk = HUNK_HEADER.match(line)
        if hunk:
            old_left = int(hunk.group(2)) if hunk.group(2) is not None else 1
            new_left = int(hunk.group(4)) if hunk.group(4) is not None else 1
        elif line.startswith("diff --git "):
            line = re.sub(r"^diff --git a/[ab]/(.*?) b/[ab]/(.*)$", r"diff --git a/\1 b/\2", line)
        elif re.match(r"^--- a/[ab]/", line):
            line = "--- a/" + line[8:]
        elif re.match(r"^\+\+\+ b/[ab]/", line):
            line = "+++ b/" + line[8:]
        out.append(line)

    return "\n".join(out)


def make_patch(old, new, names, excludes, context=3):
    """A git-format patch (applies with `git apply`, also outside a repository) for the named text files."""
    if not shutil.which("git"):
        raise SystemExit("--patch-out needs git (not found)")

    old_files, new_files = collect(old, excludes), collect(new, excludes)
    if Path(old).is_file() and Path(new).is_file():
        new_files = {next(iter(old_files)): Path(new)}

    work = Path(tempfile.mkdtemp())
    try:
        (work / "a").mkdir()
        (work / "b").mkdir()
        for name in names:
            for side, files in (("a", old_files), ("b", new_files)):
                if name in files:
                    target = work / side / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(files[name], target)

        result = subprocess.run(
            ["git", "-c", "core.quotepath=off", "-c", "diff.algorithm=myers", "diff", "--no-index", "--no-renames"]
            + [f"-U{context}", "--", "a", "b"],
            check=False,
            cwd=work,
            capture_output=True,
        )
        text = result.stdout.decode("latin-1")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    return rewrite_patch(text).encode("latin-1")


# ---------------------------------------------------------------------------------------------------------------------
# Widget code
# ---------------------------------------------------------------------------------------------------------------------


def fnv32(text):
    """FNV-1a over UTF-16 code units, the same value the widget computes in JavaScript."""
    value = 2166136261
    data = text.encode("utf-16-le", "surrogatepass")
    for i in range(0, len(data), 2):
        value = ((value ^ (data[i] | (data[i + 1] << 8))) * 16777619) & 0xFFFFFFFF
    return f"{value:08x}"


def canon_diff(data):
    """The text the checksum covers: path, status, counts and every hunk of every file."""
    files = []
    for f in data:
        parts = [f["p"], f["s"], str(f["g"][0]), str(f["g"][1])]
        parts += [f"{h['o']}\x1f{h['n']}\x1f{h['r']}" for h in f["h"]]
        files.append("\x1e".join(parts))
    return "\x1d".join(files)


def js_json(obj, **kwargs):
    """JSON for a JavaScript literal. The "<" of "</" and "<!--" is written as \\u003c, so the widget code never
    contains a literal closing script tag or HTML comment start."""
    return json.dumps(obj, ensure_ascii=False, **kwargs).replace("</", "\\u003c/").replace("<!--", "\\u003c!--")


def build_diff(title, data, script_url):
    """The widget code for a diff: loader, checksum and data (compact JSON)."""
    if "OWNER" in script_url or "@REF/" in script_url:
        raise SystemExit("the renderer URL is not pinned yet: set SCRIPT_URL in make_diff.py or pass --script-url")

    payload = {"title": title, "sum": fnv32(canon_diff(data)), "files": data}
    return (
        LOADER.replace("__TITLE_HTML__", html.escape(title))
        .replace("__DATA__", js_json(payload, separators=(",", ":")))
        .replace("__URL__", script_url)
    )


# ---------------------------------------------------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------------------------------------------------


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--title", required=True, help="short title, e.g. 'Fixing Zed tasks'")
    parser.add_argument("--old", help="original file or directory")
    parser.add_argument("--new", help="edited file or directory")
    parser.add_argument("--files", nargs="*", help="relative paths to compare (default: every file that differs)")
    parser.add_argument("--context", type=int, default=2, help="context lines around changes in the widget (default 2)")
    parser.add_argument("--exclude", nargs="*", default=[], help="extra directory names to skip")
    parser.add_argument(
        "--minimal", action="store_true", help="smallest-diff alignment instead of the readable one (tests only)"
    )
    parser.add_argument("--patch-out", help="also write a git .patch")
    parser.add_argument(
        "--limit",
        type=int,
        default=300,
        help="above this many changed lines (git counts) rows are left out (default 300)",
    )
    parser.add_argument(
        "--full", action="store_true", help="ignore --limit (use when the user asks to see specific files)"
    )
    parser.add_argument(
        "--script-url", default=SCRIPT_URL, help="renderer URL to put in the loader (default: SCRIPT_URL)"
    )
    parser.add_argument("--out", default="/home/claude/diff-inline-widget.html")

    args = parser.parse_args()
    if not (args.old and args.new):
        parser.error("give --old and --new")
    return args


def main():
    args = parse_args()
    excludes = DEFAULT_EXCLUDES | set(args.exclude)

    data = diff_trees(args.old, args.new, args.files, args.context, excludes, not args.minimal)
    if not data:
        raise SystemExit("no differences found")

    if args.patch_out:
        patch = make_patch(args.old, args.new, [f["p"] for f in data], excludes)
        Path(args.patch_out).write_bytes(patch)
        print(f"patch: {len(patch)} bytes -> {args.patch_out}  (apply: git apply --check FILE, then git apply FILE)")

    added = sum(f["g"][0] for f in data)
    removed = sum(f["g"][1] for f in data)
    summary_mode = not args.full and added + removed > args.limit
    shown = [dict(f, h=[]) for f in data] if summary_mode else data

    code = build_diff(args.title, shown, args.script_url)
    Path(args.out).write_text(code, encoding="utf-8")

    print(f"{len(data)} files changed, {added} lines added, {removed} lines removed (git counts)")
    for f in data:
        row_added, row_removed = row_counts(f)
        note = " (new file)" if f["s"] == "new" else " (deleted)" if f["s"] == "deleted" else ""
        differs = (row_added, row_removed) != tuple(f["g"])
        mark = f"   <- readable rows differ: +{row_added} -{row_removed}, the widget shows a ? icon" if differs else ""
        print(f"  {f['p']}{note}  +{f['g'][0]} -{f['g'][1]}{mark}")

    if summary_mode:
        print(
            f"SUMMARY MODE: {added + removed} changed lines is over the limit of {args.limit}, so the widget lists "
            "files and counts only. Tell the user; to show specific files use --files ... --full."
        )
    print(f"widget code: {len(code)} characters -> {args.out}")
    if len(code) > 40000:
        print("warning: large widget; consider --files to split it", file=sys.stderr)


if __name__ == "__main__":
    main()
