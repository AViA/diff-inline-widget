# Measurements

Sizes are measured. Token figures are estimates that assume 3.5 characters per token. A real count needs the model's
tokenizer.

## Sizes (measured)

| Item | Size |
|---|---|
| Widget code, one-file diff (`tests/fixtures/before`, `after`) | 1,368 characters |
| Widget code, five-file diff (`tests/fixtures/five-file-change`) | 4,873 characters |
| Fixed part of the widget code (the loader) | 607 characters |
| `SKILL.md` | 4,146 characters, of which the description is 673 |
| `src/diff.js` (fetched by the browser, never seen by the model) | 21,174 bytes |

The widget code sizes were measured with the one-letter title `t` and a placeholder URL. A full commit hash in the real
URL adds about 33 characters.

For comparison, an inline template with the renderer inside the widget code came to 8,965 characters for the same
one-file diff.

## Estimated token cost of the skill

The model reads the widget code once, when it prints the script's output file, and writes it once as the `show_widget`
argument, so it counts twice. The build command is about 230 characters and the script's printed summary 280 to 390.

| Part | When | Characters | Tokens (estimate) |
|---|---|---|---|
| Skill description | every chat, in the skill list | 673 | 190 |
| `SKILL.md` | once per chat, when the skill is used | 4,146 | 1,190 |
| One-file diff | each diff | 230 + 280 + 2 × 1,372 | 930 |
| Five-file diff | each diff | 230 + 390 + 2 × 4,897 | 3,000 |

A chat with one five-file diff therefore costs roughly 4,400 tokens in total, and each further diff only its own row.
The text the model writes around the widget is not counted.

## Not measured

- How long a widget call takes.
- How jsDelivr treats a commit pushed seconds ago.
- Rendering in light mode and on mobile.
- Python versions other than 3.12.
