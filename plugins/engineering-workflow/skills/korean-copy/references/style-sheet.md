# Style sheet and correction log

Both files live in the app's repository, so every session and every agent reads the same decisions.

## `.harness/copy-style.json`

```json
{
  "level": "haeyo",
  "period": "never",
  "terms": {
    "로그인": ["로그 인", "사인인"],
    "구입": ["구매"]
  },
  "banned": ["죄송합니다만"],
  "max_length": {"button.*": 8},
  "paired_particles": "error",
  "allow": ["legal.*", "최신 가요"],
  "sources": ["lib/l10n/app_ko.arb"],
  "log": ".harness/copy-corrections.md"
}
```

Every key is optional. An unknown key stops the check, so a typo in a key name is not silently ignored.

| Key | Meaning |
| --- | --- |
| `level` | `haeyo` (해요), `hapsyo` (합니다), or `plain` (한다). Sentences in another style fail |
| `period` | `never`: no text ends with a single period. `always`: every text that ends in a sentence has closing punctuation |
| `terms` | The word to use, and the words to avoid in its favor. A word to avoid is not reported inside the preferred word |
| `banned` | Phrases that must not appear |
| `max_length` | Key pattern (`*` and `?`) to the largest number of characters |
| `paired_particles` | `allow`, `warn` (default), or `error` for `을(를)` and the like |
| `allow` | Exact texts, or key patterns, that are exempt from every rule |
| `sources` | Files to check when the command names none, relative to the repository |
| `log` | Correction log path, relative to the repository. Default `.harness/copy-corrections.md` |

When the sheet is at `.harness/copy-style.json`, `sources` and `log` are resolved from the folder above
`.harness`, so the check gives the same result from any working directory when `--style` names the sheet.

## `.harness/copy-corrections.md`

```markdown
# Copy corrections

- `로그인 하기` => `로그인하기` | one word (2026-11-19)
- 구매 => 구입 | the store screen says 구입
```

One correction per list line: the wording that was wrong, `=>`, the wording that replaced it, and after `|` the
reason. Backticks are optional. Lines in any other shape are ignored, so the file can carry headings and notes.

## Key names

- `.json` and `.arb`: the path to the string, such as `button.save` or `steps[2]`. In `.arb`, entries whose name
  starts with `@` are descriptions and are skipped.
- `.strings` and `.properties`: the key on the left of `=` (or `:` in `.properties`). `\n` and `\uXXXX` are decoded before the text is checked.
- Android `strings.xml`: the `name` of each `<string>`. Plurals and arrays are not read.
- Any other file: the line number.

## Placeholders

With `--base`, each text is compared with the text of the same key in the base file. Format codes such as `%d`,
`%1$s`, and `%02d` must match one for one. Named placeholders such as `{count}` are compared by name, so a
Korean text may use `{count}` where the base wraps it in a plural form, but it may not drop or rename it.

## Running it for every change

The script needs only Python 3 and no network. To make it a required check, add it to the project's checks or CI
with the paths it should read, for example:

```bash
python3 path/to/korean-copy/scripts/copy_check.py --base lib/l10n/app_en.arb lib/l10n/app_ko.arb
```
