// Usage: node render_check.js widget.html '<json expectations>' [screenshot.png]
//
// Loads the widget code in headless Chromium with stand-in CSS variables and checks it in the browser. The renderer
// request (any URL ending in /src/diff.js) is answered with the local src/diff.js, so no network is needed.
//
// Expectation keys (all optional):
//   header        text of the header line
//   collapsed     indexes of the file blocks that must be collapsed
//   q             indexes of the file blocks that must show a "?" note
//   qTitle        substring of the first "?" note's tooltip
//   part0         text the first Copy button must copy
//   selectAll     text a copy of the whole visible code must give
//   toggle        true: clicking the 2nd file header must flip that block
//   checksum      "ok" | "bad"
//   maxVisibleRows
//   blockScript   true: the renderer request fails; fallback is then the text the widget must show
//
// Playwright is looked up via require, then PLAYWRIGHT_PATH, then the usual global path.

const fs = require("fs");
const path = require("path");

// Stand-ins for the CSS variables the chat host provides, plus a hostile button style to test the copy button.
const HOST_CSS = [
  ":root{--border:#30363d;--radius:8px;--surface-1:#161b22;--font-mono:ui-monospace,Consolas,monospace;",
  "--text-muted:#7d8590;--text-secondary:#9da7b3;--text-success:#3fb950;--text-danger:#f85149}",
  "button{padding:0 12px!important;font:inherit}",
  "body{background:#0d1117;color:#e6edf3;font:14px system-ui;margin:12px;max-width:700px}",
].join("");

function loadPlaywright() {
  const candidates = [
    "playwright",
    process.env.PLAYWRIGHT_PATH,
    "/home/claude/.npm-global/lib/node_modules/playwright",
  ];

  for (const candidate of candidates) {
    if (!candidate) continue;
    try {
      return require(candidate);
    } catch (error) {
      // try the next location
    }
  }
  return null;
}

/** Reads everything the checks need from the rendered page in one go. */
function readPage() {
  const all = (selector) => [...document.querySelectorAll(selector)];
  const indexesWhere = (selector, test) =>
    all(".dw-file")
      .map((file, i) => (test(file, selector) ? i : -1))
      .filter((i) => i >= 0);

  const root = document.querySelector("#root");
  return {
    files: all(".dw-file").length,
    overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    numbersSelectable: all(".dw-num,.dw-marker").some((e) => getComputedStyle(e).userSelect !== "none"),
    rootText: (root || {}).textContent || "",
    header: (document.querySelector("#root .dw-header span") || {}).textContent,
    stamp: (document.querySelector("#root .dw-header .dw-muted") || {}).textContent || "",
    collapsed: indexesWhere("", (file) => file.classList.contains("is-collapsed")),
    q: indexesWhere(".dw-note", (file, selector) => file.querySelector(selector)),
    qTitle: (document.querySelector(".dw-note") || {}).title || "",
    buttons: all(".dw-copy").length,
    visibleRows: all(".dw-row").filter((e) => e.offsetParent && !e.classList.contains("dw-hunk-head")).length,
  };
}

/** Copies the whole visible code the way a user selecting everything and pressing Ctrl+C would. */
function copyWholeSelection() {
  const cells = [...document.querySelectorAll(".dw-code")].filter((cell) => cell.offsetParent);
  const last = cells[cells.length - 1];

  const range = document.createRange();
  range.setStart(cells[0], 0);
  range.setEnd(last, last.childNodes.length);

  const selection = getSelection();
  selection.removeAllRanges();
  selection.addRange(range);

  const data = new DataTransfer();
  const event = new ClipboardEvent("copy", { clipboardData: data, bubbles: true, cancelable: true });
  document.dispatchEvent(event);
  return data.getData("text/plain");
}

(async () => {
  const playwright = loadPlaywright();
  if (!playwright) {
    console.log("SKIP: playwright not found");
    process.exit(0);
  }

  const widgetHtml = fs.readFileSync(process.argv[2], "utf8");
  const expect = JSON.parse(process.argv[3] || "{}");
  const screenshotPath = process.argv[4];

  const browser = await playwright.chromium.launch();
  const page = await browser.newPage({ viewport: { width: 760, height: 900 } });

  const scriptErrors = [];
  const failures = [];
  page.on("pageerror", (error) => scriptErrors.push(String(error)));

  // Answer the renderer request locally, or fail it for the "script cannot load" check.
  const rendererSource = fs.readFileSync(process.env.DIFF_JS || path.join(__dirname, "..", "src", "diff.js"), "utf8");
  await page.route(/\/src\/diff\.js$/, (route) =>
    expect.blockScript
      ? route.abort()
      : route.fulfill({ status: 200, contentType: "application/javascript", body: rendererSource })
  );

  await page.setContent("<style>" + HOST_CSS + "</style>" + widgetHtml);
  await page.waitForFunction(
    () => document.querySelector("#root") && document.querySelector("#root").childNodes.length > 0,
    null,
    { timeout: 15000 }
  );

  const result = await page.evaluate(readPage);

  const need = (name, ok, got) => {
    if (!ok) failures.push(`${name} (got ${JSON.stringify(got)})`);
  };
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

  need("overflow", !result.overflow, result.overflow);
  need("numbers not selectable", !result.numbersSelectable, result.numbersSelectable);

  if (expect.fallback !== undefined) {
    need("fallback message", result.rootText.includes(expect.fallback), result.rootText.slice(0, 120));
  }
  if (expect.header !== undefined) need("header", result.header === expect.header, result.header);
  if (expect.collapsed) need("collapsed blocks", same(result.collapsed, expect.collapsed), result.collapsed);
  if (expect.q) need("? icons", same(result.q, expect.q), result.q);
  if (expect.qTitle) need("? tooltip text", result.qTitle.includes(expect.qTitle), result.qTitle);
  if (expect.maxVisibleRows) {
    need("visible rows <= limit", result.visibleRows <= expect.maxVisibleRows, result.visibleRows);
  }

  if (expect.checksum) {
    const stampOk = result.stamp.startsWith("\u2713") && result.buttons > 0;
    const stampBad = result.stamp.startsWith("\u26a0") && result.buttons === 0;
    need("checksum " + expect.checksum, expect.checksum === "ok" ? stampOk : stampBad, [result.stamp, result.buttons]);
  }

  if (expect.part0 !== undefined) {
    await page.evaluate(() => {
      const clipboard = {
        writeText: (text) => {
          window.__copied = text;
          return Promise.resolve();
        },
      };
      Object.defineProperty(navigator, "clipboard", { value: clipboard, configurable: true });
    });

    const firstButton = page.locator(".dw-copy").first();
    await firstButton.locator("xpath=..").hover();
    const shown = await firstButton.isVisible();
    need("copy button shows on hover", shown, shown);

    await firstButton.click();
    const copied = await page.evaluate(() => window.__copied);
    need("copy button text", copied === expect.part0, copied);

    const sizes = await page.evaluate(() => {
      const button = document.querySelector(".dw-copy").getBoundingClientRect();
      const icon = document.querySelector(".dw-copy svg").getBoundingClientRect();
      return [Math.round(button.width), Math.round(icon.width)];
    });
    need("copy icon is drawn (button 22px, icon 12px) even if the host styles buttons", same(sizes, [22, 12]), sizes);
  }

  if (expect.selectAll !== undefined) {
    const copied = await page.evaluate(copyWholeSelection);
    need("selection copy keeps blank lines, no numbers or markers", copied === expect.selectAll, copied);
  }

  if (expect.toggle) {
    const isCollapsed = () =>
      page.evaluate(() => document.querySelectorAll(".dw-file")[1].classList.contains("is-collapsed"));
    const before = await isCollapsed();
    await page.locator(".dw-file-head").nth(1).click();
    const after = await isCollapsed();
    need("header click toggles a block", before !== after, [before, after]);
  }

  if (screenshotPath) await page.screenshot({ path: screenshotPath, fullPage: true });
  await browser.close();

  const summary = {
    files: result.files,
    header: result.header,
    collapsed: result.collapsed,
    q: result.q,
    visibleRows: result.visibleRows,
    stamp: result.stamp,
  };
  console.log(
    JSON.stringify(summary),
    scriptErrors.length ? "ERRORS: " + scriptErrors.join("; ") : "no script errors",
    failures.length ? "FAILED: " + failures.join(" | ") : "all checks ok"
  );
  process.exit(scriptErrors.length || failures.length ? 1 : 0);
})();
