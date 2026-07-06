"""Wall taxonomy for LongMemEval failures over a --dump-context results.jsonl.

cov = fraction of gold-answer content tokens present in the concatenated
context blocks (lowercased, stopwords dropped). Buckets:
  wall1  cov < 0.5  — evidence (likely) never retrieved
  wall2  cov >= 0.5 and question asks for the superseded value
  wall3  cov >= 0.5 and question is ordering/counting
  other  cov >= 0.5, none of the above (incl. judge-boundary noise)
"""

import json
import re
import sys
from pathlib import Path

STOP = set(
    "the a an of to in on at for and or is was were be been i my me it this "
    "that with from as by".split()
)
W2_PAT = re.compile(
    r"\b(initial(ly)?|original(ly)?|previous(ly)?|at first|used to|"
    r"before (i|my|the)|old(er)? (one|place|time))\b",
    re.I,
)
W3_PAT = re.compile(
    r"\b(how many|how much|how often|count|number of|which .{0,40}\bfirst\b|"
    r"first .{0,30}\b(or|between)\b|order|sequence)\b",
    re.I,
)


def content_tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP}


def block_text(block) -> str:
    if isinstance(block, str):
        return block
    if isinstance(block, dict):
        return " ".join(str(v) for v in block.values() if isinstance(v, str))
    return str(block)


def main(results_path: str, oracle_path: str) -> None:
    rows = [json.loads(line) for line in Path(results_path).open()]
    oracle = {q["question_id"]: q for q in json.load(Path(oracle_path).open())}

    failures = [r for r in rows if not r.get("autoeval_label") and not r.get("error")]
    errors = [r for r in rows if r.get("error")]
    acc = sum(1 for r in rows if r.get("autoeval_label")) / max(1, len(rows) - len(errors))
    print(f"n={len(rows)} errors={len(errors)} accuracy={acc:.3f} failures={len(failures)}\n")

    buckets: dict[str, list] = {"wall1": [], "wall2": [], "wall3": [], "other": []}
    for r in failures:
        gold = str(oracle.get(r["question_id"], {}).get("answer", r.get("gold_answer", "")))
        ctx = " ".join(block_text(b) for b in r.get("context_blocks", []))
        gtok = content_tokens(gold)
        cov = len(gtok & content_tokens(ctx)) / len(gtok) if gtok else 0.0
        q = r["question"]
        if cov < 0.5:
            b = "wall1"
        elif W2_PAT.search(q):
            b = "wall2"
        elif W3_PAT.search(q):
            b = "wall3"
        else:
            b = "other"
        buckets[b].append((cov, r))

    for name, items in buckets.items():
        print(f"== {name} (n={len(items)}) ==")
        for cov, r in sorted(items, key=lambda t: t[0]):
            gold = str(oracle.get(r["question_id"], {}).get("answer", ""))[:60]
            print(
                f"  cov={cov:.2f} [{r['question_type'][:8]}|{r.get('question_shape','?')}]"
                f" {r['question_id']} q={r['question'][:80]!r} gold={gold!r}"
                f" hyp={str(r.get('hypothesis'))[:80]!r}"
            )
        print()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
