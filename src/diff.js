/*!
 * diff-inline-widget renderer
 *
 * Draws a GitHub-style diff inside a chat widget. The widget code that Claude sends is only a small loader plus the
 * diff data; this script supplies the styles and the behaviour.
 *
 * Entry point: DiffWidget.render(data, root). The shape of `data` is described in docs/architecture.md
 * ("Data contract"); `root` is the element to draw into (default: the element with id "root").
 */
(function (global) {
  "use strict";

  // ===================================================================================================================
  // Constants
  // ===================================================================================================================

  const VERSION = "0.1.0";

  /** Files after the first are opened while the rows shown so far stay within this many. */
  const OPEN_ROW_LIMIT = 90;

  const STYLE_ID = "dw-style";

  const STYLE = `
    #action-btns {
      display: none !important;
    }

    .sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip: rect(0 0 0 0);
    }


    .dw-header {
      display: flex;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 12px;
      margin: 0 0 12px;
      font-size: 14px;
      font-weight: 500;
    }

    .dw-muted {
      font: 400 11px var(--font-mono);
      color: var(--text-muted);
    }


    .dw-file {
      margin: 0 0 14px;
      border: 0.5px solid var(--border);
      border-radius: var(--radius);
    }

    .dw-file-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 8px 12px;
      background: var(--surface-1);
      border-radius: var(--radius);
      font: 500 13px var(--font-mono);
      cursor: pointer;
    }

    .dw-file:not(.is-collapsed) .dw-file-head {
      border-bottom: 0.5px solid var(--border);
      border-radius: var(--radius) var(--radius) 0 0;
    }

    .dw-file.is-counts-only .dw-file-head {
      cursor: default;
    }

    .dw-file-head span {
      overflow-wrap: anywhere;
    }

    .dw-chevron {
      user-select: none;
      -webkit-user-select: none;
    }

    .dw-file-body {
      overflow: hidden;
      border-radius: 0 0 var(--radius) var(--radius);
      font: 12px/20px var(--font-mono);
    }

    .dw-file.is-collapsed .dw-file-body {
      display: none;
    }


    .dw-row {
      display: grid;
      grid-template-columns: 44px 44px 18px minmax(0, 1fr);
    }

    .dw-num,
    .dw-marker,
    .dw-hunk-head {
      user-select: none;
      -webkit-user-select: none;
    }

    .dw-num {
      padding: 0 8px;
      text-align: right;
      color: var(--text-muted);
    }

    .dw-marker {
      text-align: center;
      color: var(--text-secondary);
    }

    .dw-code {
      min-width: 0;
      padding: 0 16px 0 4px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }

    .dw-row.is-added {
      background: rgba(46, 160, 67, 0.13);
    }

    .dw-row.is-added .dw-num {
      background: rgba(46, 160, 67, 0.3);
    }

    .dw-row.is-removed {
      background: rgba(248, 81, 73, 0.12);
    }

    .dw-row.is-removed .dw-num {
      background: rgba(248, 81, 73, 0.3);
    }

    .dw-hunk-head {
      background: rgba(56, 139, 253, 0.15);
      color: var(--text-secondary);
    }

    .dw-hunk-text {
      grid-column: 4;
      padding: 0 4px;
    }

    .dw-mark {
      color: inherit;
      border-radius: 2px;
    }

    .dw-mark.is-added {
      background: rgba(46, 160, 67, 0.45);
    }

    .dw-mark.is-removed {
      background: rgba(248, 81, 73, 0.45);
    }


    .dw-add-group {
      position: relative;
    }

    .dw-add-group .dw-code {
      padding-right: 32px;
    }

    .dw-copy {
      position: absolute;
      top: 2px;
      right: 6px;
      z-index: 1;
      display: none;
      align-items: center;
      justify-content: center;
      box-sizing: border-box;
      width: 22px;
      height: 22px;
      padding: 0 !important;
      overflow: visible;
      background: var(--surface-1);
      color: var(--text-secondary);
      border: 0.5px solid var(--border);
      border-radius: 4px;
      cursor: pointer;
      user-select: none;
      -webkit-user-select: none;
    }

    .dw-copy svg {
      flex: none;
      width: 12px;
      height: 12px;
    }

    .dw-add-group:hover .dw-copy,
    .dw-copy:focus {
      display: flex;
    }

    @media (hover: none) {
      .dw-copy {
        display: flex;
      }
    }


    .dw-note {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 16px;
      height: 16px;
      margin-left: 8px;
      border: 0.5px solid var(--border);
      border-radius: 50%;
      font-size: 11px;
      color: var(--text-secondary);
      cursor: help;
    }
  `;

  const ICON_COPY =
    '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">' +
    '<rect x="5" y="5" width="9" height="9" rx="1.5"/>' +
    '<path d="M11 5V3.5A1.5 1.5 0 0 0 9.5 2h-6A1.5 1.5 0 0 0 2 3.5v6A1.5 1.5 0 0 0 3.5 11H5"/></svg>';

  const ICON_DONE =
    '<svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">' +
    '<path d="M3 8.5l3.5 3.5L13 4.5"/></svg>';

  const CHEVRON_OPEN = "\u25be";
  const CHEVRON_CLOSED = "\u25b8";

  // ===================================================================================================================
  // Helpers
  // ===================================================================================================================

  /** Creates an element with an optional class and text. */
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  /** FNV-1a over UTF-16 code units; make_diff.py computes the same value in Python. */
  function fnv1a(text) {
    let hash = 2166136261;

    for (let i = 0; i < text.length; i++) {
      hash ^= text.charCodeAt(i);
      hash = Math.imul(hash, 16777619);
    }

    return (hash >>> 0).toString(16).padStart(8, "0");
  }

  /** Checksum over everything that is shown, so a changed character in the data is noticed. */
  function checksum(files) {
    const canonicalFiles = files.map((file) => {
      const hunks = file.h.map((hunk) => hunk.o + "\x1f" + hunk.n + "\x1f" + hunk.r);
      return [file.p, file.s, file.g[0], file.g[1]].concat(hunks).join("\x1e");
    });

    return fnv1a(canonicalFiles.join("\x1d"));
  }

  /** Splits a hunk's rows string into { type, text } objects. */
  function parseRows(rowsText) {
    return rowsText.split("\n").map((row) => ({ type: row[0], text: row.slice(1) }));
  }

  /** Writes text into a code cell; the part inside range [from, to) is wrapped in a <mark>. */
  function fillCode(cell, text, range, markState) {
    if (!range) {
      cell.textContent = text;
      return;
    }

    const [from, to] = range;
    cell.append(document.createTextNode(text.slice(0, from)));
    if (to > from) cell.append(el("mark", "dw-mark " + markState, text.slice(from, to)));
    cell.append(document.createTextNode(text.slice(to)));
  }

  /** Sets row.range to the part of oldRow and newRow that differs; the shared prefix and suffix stay unmarked. */
  function markChangedPart(oldRow, newRow) {
    const a = oldRow.text;
    const b = newRow.text;

    let prefix = 0;
    while (prefix < a.length && prefix < b.length && a[prefix] === b[prefix]) prefix++;

    let suffix = 0;
    while (
      suffix < a.length - prefix &&
      suffix < b.length - prefix &&
      a[a.length - 1 - suffix] === b[b.length - 1 - suffix]
    ) {
      suffix++;
    }

    oldRow.range = [prefix, a.length - suffix];
    newRow.range = [prefix, b.length - suffix];
  }

  /**
   * Finds the changed part inside a removed row and its added counterpart: a run of removed rows directly followed by
   * a run of added rows of the same length is paired row by row.
   */
  function markPairs(rows) {
    let k = 0;

    while (k < rows.length) {
      if (rows[k].type !== "-") {
        k++;
        continue;
      }

      let removedEnd = k;
      while (removedEnd < rows.length && rows[removedEnd].type === "-") removedEnd++;

      let addedEnd = removedEnd;
      while (addedEnd < rows.length && rows[addedEnd].type === "+") addedEnd++;

      const runLength = removedEnd - k;
      if (runLength === addedEnd - removedEnd) {
        for (let offset = 0; offset < runLength; offset++) {
          markChangedPart(rows[k + offset], rows[removedEnd + offset]);
        }
      }

      k = addedEnd;
    }
  }

  // ===================================================================================================================
  // Copying
  // ===================================================================================================================

  /** Copies lines to the clipboard; falls back to a hidden textarea, then to selecting the lines. */
  function copyLines(lines, button, group) {
    const text = lines.join("\n");

    const showDone = () => {
      button.innerHTML = ICON_DONE;
      setTimeout(() => (button.innerHTML = ICON_COPY), 1500);
    };

    const selectInstead = () => {
      const cells = group.querySelectorAll(".dw-code");
      const range = document.createRange();
      range.setStartBefore(cells[0]);
      range.setEndAfter(cells[cells.length - 1]);

      const selection = getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      button.title = "Lines selected: press Ctrl+C";
    };

    const copyViaTextarea = () => {
      const area = document.createElement("textarea");
      area.value = text;
      area.style.cssText = "position:fixed;opacity:0";
      document.body.append(area);
      area.select();

      let copied = false;
      try {
        copied = document.execCommand("copy");
      } catch (error) {
        copied = false;
      }
      area.remove();

      if (copied) showDone();
      else selectInstead();
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(showDone, copyViaTextarea);
    } else {
      copyViaTextarea();
    }
  }

  function makeCopyButton() {
    const button = el("button", "dw-copy");
    button.type = "button";
    button.title = "Copy";
    button.setAttribute("aria-label", "Copy");
    button.innerHTML = ICON_COPY;
    return button;
  }

  let selectionCopyInstalled = false;

  /**
   * Copying a selection gives only the code: no line numbers, no +/- markers, blank lines kept, and an empty line
   * between files. Installed once per page.
   */
  function installSelectionCopy() {
    if (selectionCopyInstalled) return;
    selectionCopyInstalled = true;

    document.addEventListener("copy", (event) => {
      const selection = getSelection();
      if (!selection.rangeCount || selection.isCollapsed) return;

      const picked = selection.getRangeAt(0);
      const parts = [];
      let lastFile = null;

      document.querySelectorAll(".dw-code").forEach((cell) => {
        if (!cell.offsetParent || !picked.intersectsNode(cell)) return;

        // Clip the cell's contents to the selected part.
        const part = document.createRange();
        part.selectNodeContents(cell);
        if (picked.compareBoundaryPoints(Range.START_TO_START, part) > 0) {
          part.setStart(picked.startContainer, picked.startOffset);
        }
        if (picked.compareBoundaryPoints(Range.END_TO_END, part) < 0) {
          part.setEnd(picked.endContainer, picked.endOffset);
        }

        const file = cell.closest(".dw-file");
        if (lastFile && file !== lastFile) parts.push("");
        lastFile = file;
        parts.push(part.toString());
      });

      if (parts.length) {
        event.clipboardData.setData("text/plain", parts.join("\n"));
        event.preventDefault();
      }
    });
  }

  // ===================================================================================================================
  // Rendering
  // ===================================================================================================================

  /** One diff row: old and new line numbers, the +/- marker and the code. */
  function renderRow(row, oldLine, newLine) {
    const state = row.type === "+" ? "is-added" : row.type === "-" ? "is-removed" : "";
    const line = el("div", "dw-row " + state);

    line.append(
      el("i", "dw-num", row.type === "+" ? "" : oldLine),
      el("i", "dw-num", row.type === "-" ? "" : newLine),
      el("i", "dw-marker", row.type === " " ? "" : row.type)
    );

    const cell = el("div", "dw-code");
    fillCode(cell, row.text, row.range, state);
    line.append(cell);

    return line;
  }

  /** The blue "@@ -a,b +c,d @@" row that starts a hunk. */
  function renderHunkHeader(hunk, rows) {
    const oldCount = rows.filter((row) => row.type !== "+").length;
    const newCount = rows.filter((row) => row.type !== "-").length;

    const header = el("div", "dw-row dw-hunk-head");
    header.append(el("div", "dw-hunk-text", `@@ -${hunk.o},${oldCount} +${hunk.n},${newCount} @@`));
    return header;
  }

  /** Appends one hunk to body and returns how many added and removed rows it drew. */
  function renderHunk(hunk, body, copyEnabled) {
    const rows = parseRows(hunk.r);
    markPairs(rows);
    body.append(renderHunkHeader(hunk, rows));

    let oldLine = hunk.o;
    let newLine = hunk.n;
    let added = 0;
    let removed = 0;

    // A run of added rows is wrapped in a group that carries the copy button.
    let group = null;
    let groupLines = null;

    rows.forEach((row) => {
      const line = renderRow(row, oldLine, newLine);

      if (row.type === " ") {
        oldLine++;
        newLine++;
      } else if (row.type === "-") {
        oldLine++;
        removed++;
      } else {
        newLine++;
        added++;
      }

      if (row.type !== "+") {
        group = null;
        body.append(line);
        return;
      }

      if (!group) {
        group = el("div", "dw-add-group");
        groupLines = [];
        body.append(group);

        if (copyEnabled) {
          const button = makeCopyButton();
          const lines = groupLines;
          const owner = group;
          button.onclick = () => copyLines(lines, button, owner);
          group.append(button);
        }
      }

      group.append(line);
      groupLines.push(row.text);
    });

    return { added, removed };
  }

  /** Builds the rows of one file. Returns the body element and the added/removed rows actually drawn. */
  function renderBody(file, copyEnabled) {
    const body = el("div", "dw-file-body");
    let added = 0;
    let removed = 0;

    file.h.forEach((hunk) => {
      const drawn = renderHunk(hunk, body, copyEnabled);
      added += drawn.added;
      removed += drawn.removed;
    });

    return { body, added, removed };
  }

  /** The "?" badge that explains why the rows drawn differ from git's counts. */
  function renderCountNote(file, drawn) {
    const note = el("span", "dw-note", "?");
    note.title =
      "Shown with a more readable alignment: some unchanged lines appear as removed and re-added. " +
      `Rows here: +${drawn.added} \u2212${drawn.removed}; ` +
      `git diff counts +${file.g[0]} \u2212${file.g[1]}. The resulting file is identical.`;
    note.onclick = (event) => event.stopPropagation();
    return note;
  }

  /** "+3  −1" with the numbers coloured, plus the "?" badge where the drawn rows differ from git's counts. */
  function renderCounts(file, drawn, countsOnly) {
    const counts = el("span");

    const plus = el("span", "", "+" + file.g[0]);
    const minus = el("span", "", "  \u2212" + file.g[1]);
    plus.style.color = "var(--text-success)";
    minus.style.color = "var(--text-danger)";
    counts.append(plus, minus);

    const rowsDiffer = drawn.added !== file.g[0] || drawn.removed !== file.g[1];
    if (!countsOnly && rowsDiffer) counts.append(renderCountNote(file, drawn));

    return counts;
  }

  /** Makes the file header toggle its block open and closed (mouse, Enter and Space). */
  function makeCollapsible(box, head, chevron, open) {
    head.tabIndex = 0;
    head.setAttribute("role", "button");
    head.setAttribute("aria-expanded", open);

    const toggle = () => {
      const collapsed = box.classList.toggle("is-collapsed");
      chevron.textContent = collapsed ? CHEVRON_CLOSED : CHEVRON_OPEN;
      head.setAttribute("aria-expanded", !collapsed);
    };

    head.onclick = toggle;
    head.onkeydown = (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        toggle();
      }
    };
  }

  /** Draws one file: header with counts, and the collapsible body unless the file is listed with counts only. */
  function renderFile(file, index, open, copyEnabled) {
    const countsOnly = file.h.length === 0;
    const drawn = renderBody(file, copyEnabled);

    let boxClass = "dw-file";
    if (countsOnly) boxClass += " is-counts-only";
    else if (!open) boxClass += " is-collapsed";
    const box = el("div", boxClass);

    const head = el("div", "dw-file-head");
    const chevron = el("b", "dw-chevron", countsOnly ? "" : open ? CHEVRON_OPEN : CHEVRON_CLOSED);
    const status = file.s === "new" ? " (new file)" : file.s === "deleted" ? " (deleted)" : "";
    const name = el("span");
    name.append(chevron, document.createTextNode(` ${index + 1}. ${file.p}${status}`));

    head.append(name, renderCounts(file, drawn, countsOnly));
    box.append(head);

    if (!countsOnly) {
      box.append(drawn.body);
      makeCollapsible(box, head, chevron, open);
    }

    return box;
  }

  /**
   * Decides which files start open: the first always, the following ones while the rows shown so far stay within
   * OPEN_ROW_LIMIT. Once one file does not fit, every later file starts collapsed.
   */
  function makeOpenPolicy() {
    let rowsOpened = 0;
    let stopOpening = false;

    return function shouldOpen(index, rowCount) {
      if (index === 0) {
        rowsOpened = rowCount;
        return true;
      }

      if (!stopOpening && rowsOpened + rowCount <= OPEN_ROW_LIMIT) {
        rowsOpened += rowCount;
        return true;
      }

      stopOpening = true;
      return false;
    };
  }

  /** The title line with the totals, and the checksum stamp (or the warning when the data does not match). */
  function renderHeader(data, totals, tampered, got) {
    const fileWord = data.files.length === 1 ? " file" : " files";
    const title = el(
      "span",
      "",
      `Diff: ${data.title} - ${data.files.length}${fileWord} changed, ` +
        `${totals.added} lines added, ${totals.removed} lines removed`
    );

    const stamp = el(
      "span",
      "dw-muted",
      tampered
        ? `\u26a0 data differs from the source (expected ${data.sum}, got ${got}): do not copy from this widget`
        : "\u2713 " + data.sum
    );
    if (tampered) stamp.style.color = "var(--text-danger)";

    const header = el("div", "dw-header");
    header.append(title, stamp);
    return header;
  }

  function injectStyle() {
    if (document.getElementById(STYLE_ID)) return;

    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = STYLE;
    document.head.append(style);
  }

  /** Draws the diff described by data into root. */
  function render(data, root) {
    root = root || document.getElementById("root");
    injectStyle();
    root.textContent = "";

    const got = checksum(data.files);
    const tampered = got !== data.sum;
    const shouldOpen = makeOpenPolicy();

    const totals = { added: 0, removed: 0 };
    let someRowsLeftOut = false;
    const fragment = document.createDocumentFragment();

    data.files.forEach((file, index) => {
      totals.added += file.g[0];
      totals.removed += file.g[1];
      if (file.h.length === 0) someRowsLeftOut = true;

      const rowCount = file.h.reduce((sum, hunk) => sum + hunk.r.split("\n").length, 0);
      const open = shouldOpen(index, rowCount);
      fragment.append(renderFile(file, index, open, !tampered));
    });

    root.append(renderHeader(data, totals, tampered, got));
    if (someRowsLeftOut) {
      root.append(el("p", "dw-muted", "Rows are not shown here because the change is large. Ask for a specific file."));
    }
    root.append(fragment);

    installSelectionCopy();
  }

  global.DiffWidget = { version: VERSION, render: render, checksum: checksum };
})(window);
