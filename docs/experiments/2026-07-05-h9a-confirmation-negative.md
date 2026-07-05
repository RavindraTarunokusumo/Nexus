# H9a Confirmation — CoN Did NOT Reproduce the Replay Lift (2026-07-05)

**Goal:** confirm the +16pt temporal lift from productionizing `cot_leanprompt`
(H9a) on the real pipeline.

**Result: NOT confirmed — statistically flat with an abstention regression.**
Matched-pair (same 55 question_ids, old prompt vs CoN, fresh full runs):

| metric | baseline | CoN | |
| --- | --- | --- | --- |
| accuracy (n=54 usable) | 0.630 | 0.685 | +0.056 aggregate |
| matched pairs | — | — | 9 wrong→right, 6 right→wrong = **+3 net** |
| McNemar exact p | — | — | **0.61 (not significant)** |
| abstentions | 4 | **11** | +7 |
| mean answer tokens | 2832 | 2106 | −26% (lean works) |

**The aggregate +5.6pts is noise** (p=0.61). Reporting it without the matched-pair
test would have been a false positive — this is exactly the single-run/aggregate
trap the repo's own "multi-run averaging" TODO warns about.

## Diagnosis — CoN step 5 over-fires

8 new abstentions under CoN; **5 were answered correctly before** (pure loss). All
are ordering/counting/duration temporal questions CoN was meant to *fix* ("who
became a parent first", "how many days before I bought the iPhone", "how long to
finish two books"). CoN's step-5 instruction ("if the question's subject doesn't
exactly match the evidence, abstain") is too aggressive against the **production**
retrieval's contexts, which differ from the frozen replay cache the original
experiment used. Reasoning steps 1–4 (date resolution, ordering, counting) do help
(9 wrong→right); step 5 is the liability here.

## Why replay said +16 and production says flat

The [H9 replay experiment](2026-07-04-longmemeval-answer-path.md) measured CoN over
a **frozen** context cache — same retrieved blocks for baseline and CoN, isolating
the answer path. My confirmation used two **fresh full-pipeline runs**, each
re-extracting stochastically, so the comparison conflates the prompt change with
extraction variance AND exposes CoN to production contexts the replay never saw.
**Methodology miss:** an answer-path change should be confirmed by replay over a
frozen `--dump-context` cache (the tool built for exactly this), not a fresh
full-run before/after.

## Next — the clean experiment

1. Run the 55-baseline with `--dump-context` (freeze one extraction → context cache).
2. Replay over that fixed cache: **old prompt** vs **full CoN** vs **CoN-minus-step5**.
   Matched, no extraction noise, cheap (answer-only). McNemar between them.
3. If CoN-minus-step5 clears the old prompt at p<0.05, ship that; if CoN is flat
   even on frozen contexts, the replay result doesn't transfer and H9a is not the
   lever the diagnostic implied. Either way, decided by a controlled test, not a
   noisy full run.

H9a commit `bae772e` stands on the branch (valid code, tests green, −26% tokens
real) but its accuracy gate is **unmet** pending this clean test.
