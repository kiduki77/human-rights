# Writing: plain sentences, in any language

Everything a human reads here is something they decide on: plans, task documents, requirements, test
steps, approval requests, chat reports. Filler wording costs them time and hides what you actually know.
These rules apply in every language you write in, including ones the runtime has no word list for.

## The test for each sentence

Ask two things before you keep a sentence:

1. **Could it appear unchanged in a document about a different feature?** Then it says nothing about this
   one. Replace it with the fact it stands in for, or delete it.
2. **Could the reader check it?** A claim names a number, a file, a behaviour, a condition, or a reason.
   "Improves reliability" cannot be checked. "Retries the upload up to 3 times, then marks the job failed"
   can.

## Rules

- **State the fact, not its importance.** Don't announce that something is important, key, notable, or
  worth knowing. If it matters, say what happens when it is ignored.
- **No praise for your own work.** Don't call a design clean, solid, efficient, complete, or easy to use.
  Describe what it does and let the reader judge.
- **Verbs with an actor.** "The server rejects the request" tells the reader who does what. Avoid
  sentences where something "is ensured", "is handled", or "is supported" by nobody.
- **One claim per sentence.** If a sentence has two "and"s joining different ideas, split it.
- **Use the plain word.** Use, not the longer synonym for use. Help, not a grander verb for help. If a
  word sounds like a brochure, pick the one you would say to a colleague.
- **No stock openers or closers.** Don't begin with a line that restates the heading, and don't end a
  section with a summary of what it just said.
- **No contrast for effect.** Don't write "not just X but Y" or "more than a simple X". Say what it is.
- **No padding in threes.** Don't list three adjectives or three benefits because three sounds complete.
  List what is true, however many that is.
- **Uncertainty goes where it applies.** Say what you did not verify, once, next to the claim. Don't soften
  every sentence.
- **Punctuation stays ordinary.** Use periods, commas, and colons. More than two em dashes in a document
  is a sign of asides that should be their own sentences or be cut.
- **Numbers carry units and a source.** "About 40 minutes (the last CI run)" beats "takes a while".

## Translating is not exempt

When you write in the user's language, write it the way a careful engineer who is a native speaker
would. Don't translate English filler word for word. Each language has its own brochure words and its own
stock transitions: avoid those too, even though no list here names them. Korean examples the runtime
checks: 혁신적, 원활한, 이를 통해, 뿐만 아니라, 것이 중요합니다, 단순한 ... 아니라.

## Before and after

| Filler | Plain |
|---|---|
| This change delivers a seamless and intuitive experience for operators. | The operator picks a vehicle once. Every command button then shows that vehicle's name. |
| It is important to note that robust error handling has been implemented. | A failed upload retries 3 times with a 2 s gap, then the job is marked failed and shown in the list. |
| 이를 통해 다양한 환경에서 원활한 운영이 가능합니다. | 전송 주기를 0.5초에서 10초 사이로 바꿀 수 있습니다. 범위를 벗어난 값은 시작 버튼을 비활성화합니다. |
| 본 기능은 단순한 설정 변경이 아니라 전체 구조를 혁신적으로 개선합니다. | 전역 연결 객체 하나를 기체별 세션으로 바꿉니다. 영향받는 모듈은 link, command, ui입니다. |

## What the runtime checks

`hr doc-check` scans the human-facing Markdown and the text fields of `requirements.json`,
`task-graph.json`, `test-plan.json` and `split.json` for a list of filler phrases in English and Korean and
for runs of em dashes. Code, inline code, generated `hr:*` blocks and template placeholders are skipped.
Each hit is an error, and a feature cannot enter an approval state while one remains.

The list catches the common cases only. Passing it does not make the text good: the two questions above
still apply to every sentence, and `hr-plan-reviewer` reads for them in whatever language the document is in.

When a hit is a real term in this repository (a product name, a field label), don't reword around it. Tell
the human, and they can add it to `docs.allowed_phrases` in `config.yaml`. A team adds its own banned words
with `docs.banned_phrases`. `docs.prose_check: warn` turns the errors into warnings; `off` disables the scan.
Changing these settings is the human's call.
