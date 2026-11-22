# Notes for agents

Read [README.md](README.md) and the files in [docs/](docs/) first.

- `skill/diff-inline-widget/SKILL.md` is the runtime instructions of the skill itself. Keep it short and about
  presenting changes only. Maintainer information belongs in `docs/`.
- Run `python3 tests/run_all.py` after every change. Without Node.js and Playwright the browser checks are skipped,
  not failed, so say which checks ran.
- Keep `pyright` and `ruff check` clean on `skill`, `tests` and `tools`.
- Do not edit `src/diff.js` or `make_diff.py` without checking the host rules in
  [docs/architecture.md](docs/architecture.md#host-constraints). Breaking them leaves the widget blank.
- The widget host's design rules (CSS variables, allowed script hosts) can be read from the Visualizer's `read_me`
  tool. The skill itself does not call it. Read it again if the widget renders unstyled or blocked.
- Label every number in the docs as measured or estimated (see [docs/measurements.md](docs/measurements.md)).
- A widget cannot be seen from the sandbox. Real rendering, timing and token cost have to be checked by the user in a
  real chat.
