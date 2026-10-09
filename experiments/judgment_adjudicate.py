"""Adjudicate contested labels with a third model pass.

The constructed label and the independent review are treated as two
annotators. Items where they agree are settled; items where they disagree or
where the reviewer was uncertain go to a third pass that sees both readings and
their reasons and returns a final label or "uncertain". The presentation order
is randomised per item so the adjudicator cannot simply prefer the first
reading, and the mapping back is recorded.

The output is an adjudicated suite that keeps the same task ids, so the cached
predictions of the model under test can be re-scored against it without any new
calls to the model under test.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent))
from judgment_model_eval import ModelClient, load_credentials  # noqa: E402

SYSTEM = (
    "You are the adjudicator for a message-gateway labelling task. Two "
    "annotators labelled the same item and disagree. Decide which reading the "
    "text actually supports, using only the text, the question, and the option "
    "list. Reply with a single JSON object and nothing else."
)


def adjudication_prompt(item: Dict[str, Any], other: str, reason: str, flip: bool) -> str:
    options = ", ".join(list(item["options"]) + ["uncertain"])
    first, second = ("A", "B") if not flip else ("B", "A")
    labels = {first: item["label"], second: other}
    reasons = {
        first: "the reading recorded when the item was built",
        second: reason or "no reason recorded",
    }
    return (
        f"STATE:\n{item['state']}\n\n"
        f"QUESTION: {item['question']}\n"
        f"OPTIONS: {options}\n\n"
        f"READING A: {labels['A']}  ({reasons['A']})\n"
        f"READING B: {labels['B']}  ({reasons['B']})\n\n"
        'Decide which reading the text supports. Use "uncertain" only when the '
        'text genuinely cannot settle it.\n'
        'Reply with JSON: {"answer": "<one option exactly as written>", '
        '"reason": "<one short sentence>"}'
    )


def parse(content: str, options: List[str]) -> str:
    match = re.search(r'"answer"\s*:\s*"([^"]*)"', content)
    answer = match.group(1).strip() if match else "unparsed"
    return answer if answer in options or answer == "uncertain" else "unparsed"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review", type=Path, default=Path("data/judgment_llm_review.jsonl"))
    parser.add_argument("--suites", nargs="+", type=Path,
                        default=[Path("data/judgment_suite.jsonl"), Path("data/j7_stress_suite.jsonl")])
    parser.add_argument("--cache", type=Path, default=Path("data/judgment_adjudication.jsonl"))
    parser.add_argument("--out-dir", type=Path, default=Path("data"))
    parser.add_argument("--config", type=Path, default=Path("/home/caiyizhang/.hermes/config.yaml"))
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    items: Dict[str, Dict[str, Any]] = {}
    for path in args.suites:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                items[f"{path.name}:{item['task_id']}"] = item

    review = {}
    for line in args.review.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            review[row["key"]] = row

    contested = [key for key, row in review.items()
                 if row["review_answer"] == "uncertain" or row["review_answer"] != row["constructed_label"]]
    cache: Dict[str, Dict[str, Any]] = {}
    if args.cache.exists():
        for line in args.cache.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                cache[row["key"]] = row

    missing = [key for key in contested if key not in cache]
    if missing:
        base, api_key, model = load_credentials(args.config, None)
        client = ModelClient(base, api_key, model)

        def adjudicate(key: str) -> Dict[str, Any]:
            item, row = items[key], review[key]
            flip = int(hashlib.sha256(key.encode()).hexdigest(), 16) % 2 == 1
            content = client.complete(SYSTEM, adjudication_prompt(item, row["review_answer"], row["review_reason"], flip))
            return {"key": key, "task_id": item["task_id"], "suite": key.split(":")[0],
                    "final": parse(content, list(item["options"])), "raw": content[:300]}

        print(f"adjudicating {len(missing)} contested items with {model}", file=sys.stderr)
        with ThreadPoolExecutor(max_workers=args.workers) as pool, args.cache.open("a", encoding="utf-8") as handle:
            for row in pool.map(adjudicate, missing):
                cache[row["key"]] = row
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Build the adjudicated suites: agreement keeps the constructed label,
    # contested items take the adjudicator's definite answer, and unresolved
    # items keep the constructed label.
    changed = unresolved = 0
    by_suite: Dict[str, List[Dict[str, Any]]] = {}
    for path in args.suites:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        out_rows = []
        for item in rows:
            key = f"{path.name}:{item['task_id']}"
            row = dict(item)
            decision = cache.get(key, {}).get("final")
            if key in contested:
                if decision and decision != "uncertain":
                    if decision != item["label"]:
                        changed += 1
                    row["label"] = decision
                    row["label_source"] = "adjudicated"
                else:
                    unresolved += 1
                    row["label_source"] = "unresolved"
            else:
                row["label_source"] = "agreed"
            if "adversarial" in row:
                # Keep the injection flag consistent with the final label, or
                # flipped items would be counted in the wrong class.
                row["adversarial"] = row["label"] == "yes"
            out_rows.append(row)
        out_path = args.out_dir / path.name.replace(".jsonl", "_adjudicated.jsonl")
        out_path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in out_rows) + "\n", encoding="utf-8")
        by_suite[path.name] = out_rows
        print(f"{out_path}: {len(out_rows)} items")

    print(f"contested={len(contested)} changed={changed} unresolved={unresolved}")


if __name__ == "__main__":
    main()
