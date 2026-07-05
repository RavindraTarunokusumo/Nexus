# H9a Confirmation — CoN Confirmed (+0.21, p=0.003) After Controlling for Extraction Noise (2026-07-05)

**Goal:** confirm the temporal lift from productionizing `cot_leanprompt` (H9a).

**Resolution (read this first): CoN is CONFIRMED — +0.208 accuracy (0.547→0.755),
McNemar p=0.0034, 12 wrong→right vs 1 right→wrong** — once measured on *frozen*
contexts (matched answer-path A/B). The first attempt below (two fresh full runs)
read *flat* (p=0.61); that was a **false negative from extraction noise**, exactly
the confound the frozen-context method removes. Step-5 ablation is accuracy-neutral
(0.755→0.755, p=1.0), so the fresh-run abstention surge was context variance, not
step 5. **The two legs, in order:**

## Leg 1 (fresh full runs) — FALSE NEGATIVE

Matched-pair (same 55 question_ids, old prompt vs CoN, two **fresh** full runs):

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

## Leg 1 diagnosis (later DISPROVEN by Leg 2)

At the time, the surface reading was "CoN step 5 over-fires": 8 new abstentions
under CoN, 5 previously correct. That hypothesis was **wrong** — Leg 2 shows CoN
does not increase abstentions on matched contexts (8→8) and step-5 removal is
accuracy-neutral. The Leg-1 abstention surge (4→11) was driven by CoN meeting a
*different, freshly-extracted* context set, i.e. extraction variance, not the
prompt. Recorded here as the false trail the fresh-run design produced.

## Why Leg 1 read flat when the effect is real

Leg 1 used two **fresh full-pipeline runs**, each re-extracting stochastically, so
the before/after conflated the prompt change with extraction variance. Leg 2 (and
the original [H9 replay experiment](2026-07-04-longmemeval-answer-path.md)) freeze
the contexts, isolating the answer path — and the +0.21 effect is clear.
**Methodology miss:** an answer-path change must be confirmed by replay over a
frozen `--dump-context` cache, not a fresh full-run before/after.

## Leg 2 (frozen-context replay) — CONFIRMED

Built one `--dump-context` cache (freeze a single extraction), then replayed three
answer-path variants over the *identical* contexts (same judge). n=53 usable:

| variant | accuracy | tokens | abst | vs prev (McNemar) |
| --- | --- | --- | --- | --- |
| baseline (old prompt) | 0.547 | 2824 | 8 | — |
| **cot_leanprompt** | **0.755** | 2100 | 8 | 12 w→r / 1 r→w, **p=0.0034** |
| cot_leanprompt_nostep5 | 0.755 | 2075 | 6 | 2 / 2, p=1.0 |

- **CoN is a real, significant answer-path win: +0.208, p=0.0034**, 12:1
  fix:regress. The Leg-1 flatness was extraction variance masking it.
- **Step 5 is accuracy-neutral** (p=1.0); removing it trims 2 abstentions + 25
  tokens. Keep it as shipped (possible cross-category value on knowledge-update,
  untested here); dropping it is a harmless optional simplification. The Leg-1
  abstention surge (4→11) was context variance, NOT step 5 (frozen abst 8→8).

## Verdict

**H9a commit `bae772e` is confirmed** — CoN + lean prompt lifts the answer path
+0.21 (p=0.003) with −26% tokens. Absolute production accuracy will vary with
extraction per run (this frozen cache happened to have a hard 0.547 baseline); the
+0.21 *answer-path delta* is the robust, matched result.

## Methodology note (the real lesson)

The same change read **flat (p=0.61)** via fresh full-run before/after and
**+0.21 (p=0.003)** via frozen-context replay. An answer-path change MUST be
confirmed on frozen contexts — fresh full runs let extraction stochasticity
(the repo's ±0.25 noise) swamp the signal. Aggregate accuracy on a single fresh
run would have reported a spurious +0.056 "win"; matched-pair McNemar on the wrong
(fresh) design still read flat; only matched-pair on the *right* (frozen) design
recovered the truth. Design first, then statistics.
