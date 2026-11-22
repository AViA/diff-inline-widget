---
name: diff-inline-widget
description: Shows code changes as a GitHub-style diff widget presented mid-reply in a chat (green added and red removed lines, numbered files with git-exact +/- counts, collapsible blocks, copy buttons) and writes a git .patch. It needs the inline widget tool (show_widget) and the code sandbox, so use it only where both exist (claude.ai chat); elsewhere, such as Claude Code or the API, it does not apply. Use it when the user has to apply changes to their own copy, or when you show what you changed in one or more files (before/after, "what changed", multi-file edits). Not for plain examples, suggestions, commands or quotes of existing code: use an ordinary code block for those.
---

# diff-inline-widget

A script builds the widget code from the real files; you pass it to the widget tool unchanged. `<skill folder>` is the folder this SKILL.md was read from.

**This skill applies only when the inline widget tool (`show_widget`) is among your tools.** Otherwise ignore it completely: do not run the script, do not make a patch for it, do not mention it, and answer as if it did not exist.

## Steps

1. Have the original and the edited files side by side: two files, or two folders with the same relative paths. A version that exists only in the conversation has to be written to a file first.
2. Build:
   `python3 <skill folder>/scripts/make_diff.py --title "Short title" --old ORIGINAL --new EDITED --patch-out /mnt/user-data/outputs/<name>.patch --out /home/claude/diff-inline-widget.html`
   The title says what the change is. Leave out `--patch-out` when nothing is to be applied. Every differing text file is included (`.git`, `node_modules`, `target`, `dist`, `gen` are skipped; `--exclude NAME ...` adds more), unless `--files rel/path ...` limits it. `--context N` sets the context lines (default 2).
3. Read the printed summary and check it against what you changed. Quote its numbers, never your own count. Binary files are reported and skipped. If it says SUMMARY MODE, tell the user and offer specific files (`--files ... --full`).
4. `cat` the output file (`view` cuts long files) and pass the whole text as `widget_code` to `show_widget`: one widget per reply, all files together, no changes to the data, URL or escapes, no added comments.
5. If a patch was made, call `present_files` on it as the very last tool call, so its card sits under the widget. Never retype a patch. Tell the user to run, in the root of their copy, `git apply --check <file>` and then `git apply <file>` (no repository needed).
6. After the widget write a few lines: which files to touch, what to run, what is untested. Never repeat the code in text.

## About the widget (describe only when asked)

- The counts are git's. Rows use a readable alignment, so a "?" beside a file's counts means its rows differ slightly from git's count; the resulting file is identical.
- The first file is open. Later files stay open while the rows shown total at most 90; the rest start collapsed.
- Each run of added lines has a Copy button. Copying keeps blank lines and leaves out line numbers and markers.
- The header shows a checksum. A red warning means the data changed while it was written out: regenerate and resend, and do not let the user copy from it.
- Above 300 changed lines the widget lists files and counts only.

## If something fails

The patch is the fallback: send it as in step 5 and say what went wrong in one line, with no fenced diff blocks. This covers a widget that reports its script did not load (the patch card still follows), and a script that says the renderer URL is not pinned because the skill is not configured (the patch was already written, so skip steps 3-4).

## Rules

- Inline widget and file card only; never publish a page or artifact for this.
- An explicit instruction from the user (a file not to touch, no widget this time) outranks these steps.
- The script only reads its inputs and writes `--out` and `--patch-out`. Line endings stay as they are in the copies; prefer LF in new files. Without git and GNU diff the counts fall back to difflib, with a warning.
- Text files only.
