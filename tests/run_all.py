#!/usr/bin/env python3
"""Self-test for diff-inline-widget. Run from anywhere: python3 tests/run_all.py

Checks
  1. the readable alignment keeps an edited block in place; both alignments rebuild the new file (fuzzed),
  2. the +/- counts equal git's, on every counting path (git, GNU diff, difflib fallback),
  3. generated .patch files apply with `git apply` outside a repository and reproduce the new tree,
  4. the widget code: no sequence the host would cut, a pinned renderer URL, a size budget,
  5. the widgets in headless Chromium: collapse rule, ? icons, copy buttons, blank lines, checksum, summary mode and
     the fallback when the renderer cannot be loaded (needs node + playwright, skipped otherwise).

The counts are checked against git itself (an independent oracle), not against numbers copied from an earlier run.
"""
import filecmp
import importlib.util
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skill" / "diff-inline-widget" / "scripts" / "make_diff.py"
RENDER = ROOT / "tests" / "render_check.js"
RENDERER = ROOT / "src" / "diff.js"
TEST_URL = "https://cdn.jsdelivr.net/gh/test/diff-inline-widget@0000000/src/diff.js"



def load_module(path):
    """Import a Python file by path (make_diff.py is not on the import path)."""
    spec = importlib.util.spec_from_file_location("make_diff", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


md = load_module(SCRIPT)

fx = ROOT / "tests" / "fixtures"
fails = []
TMP = Path(tempfile.mkdtemp())


def check(name, ok, extra=""):
    print(("PASS " if ok else "FAIL ") + name + (f"  {extra}" if extra else ""))
    if not ok:
        fails.append(name)


def safe(name, text, strict=False):
    """The widget host cuts code at a literal </script (and chokes on <!-- and \\/): none may appear except the
    loader's own script tag."""
    ok = text.count("</script") == text.count("<script") and "<!--" not in text and (not strict or "\\/" not in text)
    check(f"{name}: no stray </script, <!-- (or \\/ in templates) in widget code", ok)


def run_script(*args):
    command = [sys.executable, str(SCRIPT), *map(str, args), "--script-url", TEST_URL]
    return subprocess.run(command, check=False, capture_output=True, text=True)


def apply(orig, hunks):
    out, pos = [], 0
    for h in hunks:
        rows = h["r"].split("\n")
        oc = sum(r[0] != "+" for r in rows)
        st = h["o"] - 1 if oc else h["o"]
        out += orig[pos:st] + [r[1:] for r in rows if r[0] != "-"]
        pos = st + oc
    return out + orig[pos:]


def same_tree(a, b):
    cmp = filecmp.dircmp(a, b)
    if cmp.left_only or cmp.right_only or cmp.diff_files or cmp.funny_files:
        return False
    return all(same_tree(Path(a) / d, Path(b) / d) for d in cmp.common_dirs)


def git_numstat(a, b):
    """git's own added/removed counts for one pair of files (None = the file does not exist on that side)."""
    command = ["git", "-c", "diff.algorithm=myers", "diff", "--no-index", "--numstat", "--"]
    command += [str(a) if a else os.devnull, str(b) if b else os.devnull]
    result = subprocess.run(command, check=False, capture_output=True, text=True)

    match = re.match(r"(\d+)\t(\d+)\t", result.stdout)
    if match is None:
        raise RuntimeError(f"git printed no numstat for {a} and {b}: {result.stdout!r} {result.stderr!r}")
    return [int(match.group(1)), int(match.group(2))]


def oracle_tree(old, new):
    """{path: [added, removed]} for every file that differs between two trees, counted by git."""
    a, b = md.collect(old, set()), md.collect(new, set())
    out = {}
    for n in sorted(set(a) | set(b)):
        if n in a and n in b and a[n].read_bytes() == b[n].read_bytes():
            continue
        out[n] = git_numstat(a.get(n), b.get(n))
    return out


def totals(orc):
    return sum(v[0] for v in orc.values()), sum(v[1] for v in orc.values())


def make_large(root):
    """Five files with many added lines: more than 300 changed lines in total, two files too big to open by default."""
    old, new = root / "large-old", root / "large-new"
    old.mkdir(parents=True)
    new.mkdir(parents=True)
    for k, (n, m) in enumerate([(30, 3), (30, 2), (60, 20), (120, 100), (140, 160)]):
        base = [f"function f{k}() {{"] + [f"  step_{k}_{i}();" for i in range(n)] + ["}"]
        edited = list(base)
        edited[20] = edited[20].replace("step", "STEP")
        edited[28] = edited[28].replace("step", "STEP")
        del edited[n - 2]
        edited[5:5] = [f"  added_{k}_{j}(); // new" for j in range(m)]
        (old / f"f{k}.ts").write_text("\n".join(base) + "\n")
        (new / f"f{k}.ts").write_text("\n".join(edited) + "\n")
    return old, new


safe("loader template", md.LOADER, strict=True)
check("renderer: valid JavaScript (node --check)",
      shutil.which("node") is None or subprocess.run(["node", "--check", str(RENDERER)], check=False).returncode == 0)

# 1. alignment
for readable in (False, True):
    d = md.diff_trees(str(fx / "before"), str(fx / "after"), [], 2, set(), readable)[0]
    rows = [r for h in d["h"] for r in h["r"].split("\n")]
    ok = apply(md.read_lines(fx / "before" / "config.json"), d["h"]) == md.read_lines(fx / "after" / "config.json")
    check(f"fixture reconstructs the new file (readable={readable})", ok,
          f"+{sum(r[0] == '+' for r in rows)} -{sum(r[0] == '-' for r in rows)}")
    if readable:
        check("readable: type change shown as -/+ pair",
              '-    "type": "pwa-chrome",' in rows and '+    "type": "pwa-msedge",' in rows)
    else:
        check("minimal: smallest diff (no -/+ type pair)", '-    "type": "pwa-chrome",' not in rows)

# a line appended to the end of a block that is followed by a blank line stays a plain insertion
table = ["| `npm test` | unit tests |", "| `npm run lint` | lint |", "", "## Layout"]
with_row = table[:2] + ["| `npm run build` | build |"] + table[2:]
appended = md.build_hunks(table, with_row, 2, True)
check("readable: a row appended before a blank line is one added row",
      md.row_counts({"h": appended}) == (1, 0), str(md.row_counts({"h": appended})))

rw = fx / "five-file-change"
orc5 = oracle_tree(rw / "before", rw / "after")
check("five-file fixture: five files differ", len(orc5) == 5, str(list(orc5)))
for readable in (False, True):
    data = md.diff_trees(str(rw / "before"), str(rw / "after"), [], 2, set(), readable)
    rebuilt = all(apply(md.read_lines(rw / "before" / f["p"]), f["h"]) == md.read_lines(rw / "after" / f["p"])
                  for f in data)
    check(f"five-file fixture reconstructs every after/ file (readable={readable})", rebuilt)
    check(f"five-file fixture: g counts are git's (readable={readable})", {f["p"]: f["g"] for f in data} == orc5)
    if not readable:
        check("five-file fixture: minimal rows equal git's counts",
              all(list(md.row_counts(f)) == f["g"] for f in data))

random.seed(7)


def gen(n):
    out = []
    for i in range(n):
        out += ["  {", f'    "label": "cfg {i}",', '    "adapter": "JS",', '    "type": "t",']
        out += ['    "port": 9222,', "  },"]
    return out


bad = 0
for _ in range(1500):
    a = gen(random.randint(2, 6))
    b = a[:]
    for _ in range(random.randint(1, 4)):
        k = random.random()
        i = random.randrange(len(b))
        if k < .3:
            b[i] += " x"
        elif k < .5:
            del b[i]
        elif k < .7:
            b.insert(i, f'    "extra": {random.randint(0, 9)},')
        elif k < .85:
            j = random.randrange(len(b))
            b[j:j] = b[i:i + random.randint(1, 9)]
        else:
            b[i:i] = ["  {", '    "label": "new",', "  },"]
    bad += not md._valid(a, b, md._Refined(None, a, b, autojunk=False).get_opcodes())
check("fuzz: 1500 random edits, readable opcodes always valid", bad == 0, f"invalid={bad}")

# 2. counts are git's
cb = fx / "count-bug"
large_old, large_new = make_large(TMP)
orc_large = oracle_tree(large_old, large_new)


def counts(old, new):
    data = md.diff_trees(str(old), str(new), [], 2, set())
    return {f["p"]: f["g"] for f in data}, [sum(f["g"][0] for f in data), sum(f["g"][1] for f in data)]


REAL_WHICH = shutil.which
for label, patcher in (("git", REAL_WHICH),
                       ("GNU diff (no git)", lambda c: None if c == "git" else REAL_WHICH(c)),
                       ("difflib (no git, no diff)", lambda c: None)):
    with mock.patch.object(md.shutil, "which", side_effect=patcher):
        md._warned.clear()
        _, rep = counts(cb / "repro" / "old.ts", cb / "repro" / "new.ts")
        per, tot = counts(large_old, large_new)
    if label.startswith("difflib"):
        check("counts: difflib last resort runs (may differ from git, with a warning)", "nogit" in md._warned,
              f"repro {rep} large {tot}")
    else:
        check(f"counts via {label}: repro is 7/5 and the large change matches git, per file",
              rep == [7, 5] and per == orc_large and tot == list(totals(orc_large)), f"repro {rep} large {tot}")

# 3. generated patches apply outside a repo
def roundtrip(name, old, new, extra=()):
    patch = TMP / (name + ".patch")
    out = TMP / (name + ".html")
    r = run_script("--title", name, "--old", old, "--new", new, "--patch-out", patch, "--out", out, "--full", *extra)
    work = TMP / (name + "-work")
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(old, work)
    c1 = subprocess.run(["git", "apply", "--check", str(patch)], check=False, cwd=work, capture_output=True, text=True)
    c2 = subprocess.run(["git", "apply", str(patch)], check=False, cwd=work, capture_output=True, text=True)
    if out.exists():
        safe(f"widget for {name}", out.read_text(encoding="utf-8"))
    check(f"patch-out {name}: git apply works outside a repo",
          r.returncode == 0 and c1.returncode == 0 and c2.returncode == 0,
          (r.stderr + c1.stderr + c2.stderr).strip()[:200])
    check(f"patch-out {name}: result identical to the new tree", same_tree(work, new))


if shutil.which("git"):
    roundtrip("five-file", rw / "before", rw / "after")
    roundtrip("large-change", large_old, large_new)
    edge_old, edge_new = TMP / "edge-old", TMP / "edge-new"
    for d in (edge_old, edge_new):
        (d / "sub dir").mkdir(parents=True)
    (edge_old / "gone.txt").write_text("bye\n")
    (edge_old / "crlf.txt").write_bytes(b"x1\r\nx2\r\nx3\r\n")
    (edge_new / "crlf.txt").write_bytes(b"x1\r\nx2 changed\r\nx3\r\n")
    (edge_old / "nonl.txt").write_bytes(b"one\ntwo")
    (edge_new / "nonl.txt").write_bytes(b"one\ntwo!")
    (edge_new / "sub dir" / "new file.txt").write_text("\u00fc \U0001F600 </script> <!-- x -->\n\n\nlast\n")
    (edge_old / "dashes.txt").write_text("a\n-- sql comment\n--- a/a/x\nb\n")
    (edge_new / "dashes.txt").write_text("a\n-- sql comment\n--- a/a/x\nB\n")
    # a moved file with a small edit: git would call it a rename unless told not to
    (edge_old / "old-name.txt").write_text("alpha\nbeta\ngamma\ndelta\n")
    (edge_new / "sub dir" / "new-name.txt").write_text("alpha\nbeta\ngamma\ndelta\nepsilon\n")
    roundtrip("edge-cases", edge_old, edge_new)
    data = md.diff_trees(str(edge_old), str(edge_new), [], 2, set())
    check("edge cases: new/deleted files and counts",
          {f["p"]: (f["s"], tuple(f["g"])) for f in data}["gone.txt"] == ("deleted", (0, 1)))

# 4. the widget code
unpinned_command = [sys.executable, str(SCRIPT), "--title", "x", "--old", str(fx / "before")]
unpinned_command += ["--new", str(fx / "after")]
unpinned_command += ["--out", str(TMP / "unpinned.html")]
pin = subprocess.run(unpinned_command, check=False, capture_output=True, text=True)
check("an unpinned renderer URL is refused",
      pin.returncode != 0 and "not pinned" in pin.stderr, pin.stderr.strip()[:120])
five = TMP / "five.html"
r = run_script("--title", "Five-file test", "--old", rw / "before", "--new", rw / "after", "--out", five)
code = five.read_text(encoding="utf-8")
safe("five-file widget", code)
check("widget code names the renderer URL exactly once", code.count(TEST_URL) == 1)
check("widget code stays small: five files under 6,000 characters (the old inline template needed 13,000)",
      len(code) < 6000, f"{len(code)} characters")

# 5. browser checks
if shutil.which("node"):
    def browser(name, html, exp, shot=None):
        command = ["node", str(RENDER), str(html), json.dumps(exp)] + ([str(shot)] if shot else [])
        r = subprocess.run(command, check=False, capture_output=True, text=True)
        if r.stdout.startswith("SKIP"):
            print("SKIP browser checks (playwright not found)")
            return None
        check(f"browser: {name}", r.returncode == 0, r.stdout.strip()[:300] + r.stderr.strip()[:200])
        return r

    def visible_lines(data, idx):
        return [r[1:] for i in idx for h in data[i]["h"] for r in h["r"].split("\n")]

    def first_run(f):
        run = []
        for h in f["h"]:
            for r in h["r"].split("\n"):
                if r[0] == "+":
                    run.append(r[1:])
                elif run:
                    return run
        return run

    def mismatched(data):
        return [i for i, f in enumerate(data) if tuple(md.row_counts(f)) != tuple(f["g"])]

    # five-file fixture: nothing collapses, ? where the readable rows differ from git's counts
    d5 = md.diff_trees(str(rw / "before"), str(rw / "after"), [], 2, set())
    a5, r5 = totals(orc5)
    q5 = mismatched(d5)
    exp = {"header": f"Diff: Five-file test - 5 files changed, {a5} lines added, {r5} lines removed",
           "collapsed": [], "q": q5, "part0": "\n".join(first_run(d5[0])),
           "selectAll": "\n\n".join("\n".join(visible_lines(d5, [i])) for i in range(5)),
           "toggle": True, "checksum": "ok"}
    if q5:
        exp["qTitle"] = f"git diff counts +{d5[q5[0]]['g'][0]} \u2212{d5[q5[0]]['g'][1]}"
    browser("five-file widget (header, ? icons, copy button, selection copy, toggle, checksum)", five, exp)
    # tampered data: one character of a row changed -> checksum warning, no copy buttons
    t = TMP / "tampered.html"
    t.write_text(code.replace('"useWebView', '"useWebview', 1), encoding="utf-8")
    check("tamper test really changed the widget code", t.read_text(encoding="utf-8") != code)
    browser("tampered widget data is flagged and copying is off", t, {"checksum": "bad"})
    # the renderer cannot be loaded -> the widget says so instead of staying empty
    browser("blocked renderer: a clear message instead of an empty widget", five,
            {"blockScript": True, "fallback": "did not load"})
    # large change: summary mode, then --full with the 90-row collapse rule
    sm = TMP / "large-summary.html"
    r = run_script("--title", "Large", "--old", large_old, "--new", large_new, "--out", sm)
    check("summary mode announced above 300 changed lines", "SUMMARY MODE" in r.stdout)
    al, rl = totals(orc_large)
    browser("summary widget lists files and counts only", sm,
            {"header": f"Diff: Large - 5 files changed, {al} lines added, {rl} lines removed"})
    full = TMP / "large-full.html"
    run_script("--title", "Large", "--old", large_old, "--new", large_new, "--full", "--out", full)
    dr = md.diff_trees(str(large_old), str(large_new), [], 2, set())
    cnt = [sum(len(h["r"].split("\n")) for h in f["h"]) for f in dr]
    used, stop, col = cnt[0], False, []
    for i in range(1, len(cnt)):
        if not stop and used + cnt[i] <= 90:
            used += cnt[i]
        else:
            stop = True
            col.append(i)
    check("90-row rule: the large fixture collapses at least one file", len(col) >= 1, f"rows {cnt}, collapsed {col}")
    browser(f"90-row rule: rows per file {cnt}, collapsed {col}", full,
            {"collapsed": col, "maxVisibleRows": max(90, cnt[0]), "q": mismatched(dr), "checksum": "ok"})
    # blank lines, unicode, </script> inside code
    bo, bn = TMP / "bl-old", TMP / "bl-new"
    bo.mkdir()
    bn.mkdir()
    (bo / "x.txt").write_text("a\nb\nc\nd\n")
    (bn / "x.txt").write_text("a\n\nB1\n\n\nB2 \U0001F600 </script> <!-- z -->\nc\nd\n")
    (bo / "y.txt").write_text("1\n2\n")
    (bn / "y.txt").write_text("1\n\n2\n")
    bl = TMP / "bl.html"
    run_script("--title", "Blank lines", "--old", bo, "--new", bn, "--out", bl)
    safe("blank-lines widget", bl.read_text(encoding="utf-8"))
    dbl = md.diff_trees(str(bo), str(bn), [], 2, set())
    browser("blank lines survive selection copy and the copy button", bl,
            {"part0": "\n".join(first_run(dbl[0])),
             "selectAll": "\n\n".join("\n".join(visible_lines(dbl, [i])) for i in range(2)), "checksum": "ok"})
else:
    print("SKIP browser checks (node not found)")

shutil.rmtree(TMP, ignore_errors=True)
print("\nALL PASSED" if not fails else "\nFAILED: " + ", ".join(fails))
sys.exit(1 if fails else 0)
