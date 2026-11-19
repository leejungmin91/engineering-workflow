---
name: korean-copy
description: "Use when writing, translating, or reviewing Korean text that users will read: app screens, buttons, errors, notifications, store listings, release notes. Keeps one speech level, the app's own terms, and earlier corrections, with a script that fails on mixed speech levels, avoided words, common misspellings, and broken placeholders. 한국어 문구, 말투, 맞춤법, 번역투, 존댓말, 해요체, 합니다체."
metadata:
  keywords: 한국어 문구, 말투, 맞춤법, 번역투, 존댓말, 현지화, Korean copy, localization, speech level, style sheet
---

# Korean copy

Korean product text goes wrong in ways a reader notices at once and a model often does not: `합니다` on one
screen and `해요` on the next, two words for one thing, a wording the user already corrected coming back, and
sentences that read as translated. The first three are mechanical, so a script checks them. The last needs a
read, and the list below says what to look for.

## Before writing

1. Read the app's style sheet, `.harness/copy-style.json`, and its correction log,
   `.harness/copy-corrections.md`. The formats are in [references/style-sheet.md](references/style-sheet.md).
2. If the app has no style sheet, read 20 or more existing strings, write down the speech level and the terms they
   already use, and create the sheet from that. Ask the user only about a real conflict, such as two speech levels
   in equal use.
3. Write Korean directly from what the screen has to say. Do not write English first and translate it.

## Check

```bash
python3 scripts/copy_check.py                      # the sources listed in the style sheet
python3 scripts/copy_check.py lib/l10n/app_ko.arb --base lib/l10n/app_en.arb
```

It reads `.json`, `.arb`, `.strings`, `.properties`, Android `strings.xml`, and plain text, and checks only text
that contains Hangul. Exit 0 means no errors, 1 means errors (or warnings with `--strict`), 2 means the check could
not run.

| Rule | Fails when |
| --- | --- |
| `speech-level` | A sentence ends in a different style than the sheet's `level`. Without a sheet level, the minority style fails, and so does one text that mixes two |
| `term` | A word the sheet lists under a preferred term appears |
| `corrected` | A wording from the left side of the correction log appears |
| `banned` | A phrase from the sheet's `banned` list appears |
| `spelling` | One of a short list of misspellings that are never right appears, such as `되요` or `몇일` |
| `spacing` | Two spaces in a row, or a space before closing punctuation |
| `period` | The text breaks the sheet's `period` rule |
| `length` | The text is longer than the sheet's limit for its key |
| `placeholder` | With `--base`, the placeholders differ from the same key in the base file |
| `paired-particle` | Warning: `을(를)`, `이(가)`, and the like |
| `translated` | Warning: a few phrases that usually mark translated text, such as `되어집니다` or `당신` |

Labels that end in a noun, such as `설정` or `저장하기`, have no speech level and are not judged. A finding that is
right for this app goes into the sheet's `allow` list, with the reason in the commit message. Do not reword a
string only to get past the check.

## Read it once more

The script cannot tell whether a sentence sounds like a person. After it passes, read every changed string in
its place on the screen and fix these:

- A subject or `당신` that Korean would leave out.
- Passive voice where the app did something: `저장되었습니다` is fine, `저장되어졌습니다` is not, and `저장했어요`
  is often better.
- Noun chains joined by `의`, and `~에 대한`, `~를 통해`, `~하는 것이 가능합니다` where a verb would do.
- An apology or an exclamation the situation does not call for.
- An error that says what went wrong and not what to do next.
- A particle that does not fit the word a placeholder will be filled with. Reword so that no particle follows
  the placeholder, or choose the particle in code.
- A button that does not say what happens when it is pressed.
- Honorifics applied to things: `결제가 완료되셨습니다`.

## When the user corrects a wording

Add one line to `.harness/copy-corrections.md` in the same change: `- wrong => right | reason`. The check then
fails whenever the old wording comes back, in this file or any other. If the correction is a choice between two
words for one thing, add it to `terms` in the style sheet as well.

## Limits

- Speech level is read from the last word of each sentence. Unusual endings and quoted speech can be missed or
  misread. `allow` covers the second case.
- The misspelling list holds only forms that are wrong in every context. It is not a spell checker.
- The script does not judge tone, clarity, or whether the text fits its space on screen.
