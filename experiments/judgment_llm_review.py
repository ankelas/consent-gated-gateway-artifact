"""Independent model review of the judgment labels.

The suite's labels come from the construction: the generator fixes the latent
answer and then writes the surface text. This script has a hosted model read
each item as an independent annotator, with no access to the constructed label
or to any prediction of the model under test, and reports how often the two
readings disagree. It is a check for disputed items, not a substitute for human
adjudication.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from judgment_model_eval import ModelClient, load_credentials  # noqa: E402

SYSTEM = (
    "You are an independent annotator producing ground-truth labels for a "
    "message gateway. You have not seen any model output or any earlier label. "
    "Judge only the supplied text against the question and the option list. "
    "Reply with a single JSON object and nothing else."
)


def definitions(path: Path) -> Dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {point["id"]: point["question"] for point in data["judgment_points"]}


def prompt(item: Dict[str, Any], definition: str) -> str:
    options = ", ".join(list(item["options"]) + ["uncertain"])
    return (
        f"DEFINITION: {definition}\n\n"
        f"STATE:\n{item['state']}\n\n"
        f"QUESTION: {item['question']}\n"
        f"OPTIONS: {options}\n\n"
        'Choose exactly one option. Use "uncertain" only when the text genuinely '
        'does not determine the answer.\n'
        'Reply with JSON: {"answer": "<one option exactly as written>", '
        '"reason": "<one short sentence>"}'
    )


def parse(content: str, options: List[str]) -> Tuple[str, str]:
    # The state text can itself contain braces, so pull the two fields out of
    # the reply rather than trusting the first "{".
    answer_match = re.search(r'"answer"\s*:\s*"([^"]*)"', content)
    reason_match = re.search(r'"reason"\s*:\s*"([^"]*)"', content, re.DOTALL)
    answer = (answer_match.group(1).strip() if answer_match else "unparsed")
    if answer not in options and answer != "uncertain":
        answer = "unparsed"
    reason = (reason_match.group(1).strip() if reason_match else "")
    return answer, reason[:200].replace("\n", " ")


def kappa(pairs: List[Tuple[str, str]]) -> float:
    if not pairs:
        return float("nan")
    labels = sorted({value for pair in pairs for value in pair})
    n = len(pairs)
    observed = sum(1 for a, b in pairs if a == b) / n
    expected = sum(
        (sum(1 for a, _ in pairs if a == label) / n) * (sum(1 for _, b in pairs if b == label) / n)
        for label in labels
    )
    return (observed - expected) / (1 - expected) if expected < 1 else float("nan")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", nargs="+", required=True, type=Path)
    parser.add_argument("--points", type=Path, default=Path("judgment_points.json"))
    parser.add_argument("--cache", type=Path, default=Path("data/judgment_llm_review.jsonl"))
    parser.add_argument("--config", type=Path, default=Path("/home/caiyizhang/.hermes/config.yaml"))
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    definitions_map = definitions(args.points)
    items: List[Dict[str, Any]] = []
    for path in args.suite:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                item["_suite"] = path.name
                items.append(item)

    cache: Dict[str, Dict[str, Any]] = {}
    if args.cache.exists():
        for line in args.cache.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                # Drop empty or unparsed reviews so they are retried.
                if (row.get("raw") or "").strip() and row.get("review_answer") != "unparsed":
                    cache[row["key"]] = row

    missing = [item for item in items if f"{item['_suite']}:{item['task_id']}" not in cache]
    if missing:
        base, key, model = load_credentials(args.config, None)
        client = ModelClient(base, key, model)

        def review(item: Dict[str, Any]) -> Dict[str, Any]:
            content = client.complete(
                SYSTEM, prompt(item, definitions_map.get(item["judgment_point"], item["question"])),
                max_tokens=1200)
            answer, reason = parse(content, list(item["options"]))
            return {
                "key": f"{item['_suite']}:{item['task_id']}",
                "suite": item["_suite"],
                "task_id": item["task_id"],
                "judgment_point": item["judgment_point"],
                "split": item["split"],
                "constructed_label": item["label"],
                "review_answer": answer,
                "review_reason": reason,
                "raw": content[:400],
                "state": item["state"],
            }

        print(f"reviewing {len(missing)} items with {model}", file=sys.stderr)
        with ThreadPoolExecutor(max_workers=args.workers) as pool, args.cache.open("a", encoding="utf-8") as handle:
            for index, row in enumerate(pool.map(review, missing), 1):
                cache[row["key"]] = row
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                if index % 40 == 0:
                    print(f"  {index}/{len(missing)}", file=sys.stderr)

    rows = [cache[f"{item['_suite']}:{item['task_id']}"] for item in items]
    report = Path("data/judgment_llm_review_report.md")
    with report.open("w", encoding="utf-8") as out:
        out.write("# Independent model review of the judgment labels\n\n")
        out.write("| Suite | Point | n | Agree | Uncertain | Disagree | Kappa | Unparsed |\n")
        out.write("| --- | --- | --- | --- | --- | --- | --- | --- |\n")
        for suite in sorted({row["suite"] for row in rows}):
            for point in sorted({row["judgment_point"] for row in rows}):
                group = [row for row in rows if row["suite"] == suite and row["judgment_point"] == point]
                if not group:
                    continue
                definite = [row for row in group if row["review_answer"] != "uncertain"]
                definite = [row for row in definite if row["review_answer"] != "unparsed"]
                unparsed = sum(1 for row in group if row["review_answer"] == "unparsed")
                agree = sum(1 for row in definite if row["review_answer"] == row["constructed_label"])
                uncertain = len(group) - len(definite) - unparsed
                pairs = [(row["constructed_label"], row["review_answer"]) for row in definite]
                out.write(
                    f"| {suite} | {point} | {len(group)} | {agree} | {uncertain} "
                    f"| {len(definite) - agree} | {kappa(pairs):.3f} | {unparsed} |\n"
                )

        out.write("\n## Disputed items\n\n")
        disputed = [
            row for row in rows
            if row["review_answer"] != "uncertain" and row["review_answer"] != row["constructed_label"]
        ]
        out.write(f"{len(disputed)} of {len(rows)} items were given a different definite label.\n\n")
        for row in disputed[:40]:
            out.write(
                f"- **{row['task_id']}** ({row['judgment_point']}, {row['split']}): "
                f"constructed `{row['constructed_label']}` vs review `{row['review_answer']}` — "
                f"{row['review_reason']}\n  - {row['state'][:160]}\n"
            )
    print(f"wrote {report}")


if __name__ == "__main__":
    main()
