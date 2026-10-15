"""Pilot 1: hierarchical decomposition with confidence-based routing.

Single-agent baseline versus a planner/router/specialist/aggregator/verifier
chain on 24 auto-generated multi-step arithmetic tasks with computed ground
truth.  Both arms answer the same questions; the treatment differs only in how
the work is decomposed and routed.
"""

from __future__ import annotations

import random
import time

from pilot_common import Model, extract_json, extract_number, parallel, rate, write_jsonl, DATA


WORDS = ["banana", "triangle", "umbrella", "kangaroo", "mountain", "festival", "lighthouse"]


def is_prime(value: int) -> bool:
    if value < 2:
        return False
    for divisor in range(2, int(value ** 0.5) + 1):
        if value % divisor == 0:
            return False
    return True


def nth_prime(n: int) -> int:
    found, candidate = 0, 1
    while found < n:
        candidate += 1
        if is_prime(candidate):
            found += 1
    return candidate


def build_tasks(count: int = 24) -> list[dict]:
    """Deterministic task set; every answer is computed, never authored.

    Chains are deliberately long and use three-digit operands so that a
    single-pass solver has something to get wrong.
    """
    rng = random.Random(20261015)
    tasks: list[dict] = []
    for index in range(count):
        kind = index % 3
        if kind == 0:
            a = rng.randint(120, 980)
            b = rng.randint(3, 12)
            c = rng.randint(40, 300)
            d = rng.randint(50, 900)
            e = rng.randint(2, 9)
            f = rng.randint(11, 90)
            question = (
                f"Start with {a}. Multiply by {b}, subtract {c}, add {d}, divide by {e}, "
                f"then subtract {f}. Give the final number to two decimals."
            )
            answer = round((a * b - c + d) / e - f, 2)
        elif kind == 1:
            word = rng.choice(WORDS)
            k2 = rng.randint(3, 9)
            b = rng.randint(3, 11)
            c = rng.randint(20, 120)
            question = (
                f"Take the {k2}th prime number, multiply it by the number of letters in the "
                f"word '{word}', then add {c}, then multiply the whole thing by "
                f"{len(word)}. Give the final number."
            )
            answer = (nth_prime(k2) * len(word) + c) * len(word)
        else:
            km = rng.randint(70, 480)
            factor = rng.randint(3, 9)
            subtract = rng.randint(20, 260)
            question = (
                f"Convert {km} kilometres to miles (1 kilometre = 0.621371 miles), multiply "
                f"the result by {factor}, subtract {subtract}, then report the number rounded "
                "to two decimals."
            )
            answer = round(km * 0.621371 * factor - subtract, 2)
        tasks.append({"id": index + 1, "kind": kind, "question": question, "answer": answer})
    return tasks


def build_long_chain_tasks(count: int = 8) -> list[dict]:
    """Twelve-step chains: the same family, stretched until errors can appear."""
    rng = random.Random(20261017)
    tasks: list[dict] = []
    for index in range(count):
        start = rng.randint(2000, 9000)
        running = float(start)
        steps: list[str] = []
        for _ in range(12):
            operation = rng.choice(["add", "sub", "mul", "div"])
            operand = rng.choice([rng.randint(11, 99), rng.randint(2, 9)])
            if operation == "add":
                running += operand
            elif operation == "sub":
                running -= operand
            elif operation == "mul":
                running *= operand
            else:
                running /= operand
            steps.append(f"{operation} {operand}")
        tasks.append({
            "id": f"long-{index + 1}",
            "kind": "long",
            "question": (
                f"Begin with {start} and apply these twelve operations in order: "
                + ", then ".join(steps)
                + ". Give the final number rounded to two decimals."
            ),
            "answer": round(running, 2),
        })
    return tasks


def correct(value: float | None, expected: float) -> bool:
    if value is None:
        return False
    return abs(value - expected) <= max(0.02, abs(expected) * 1e-4)


SOLVER = (
    "You are a careful arithmetic assistant. Work step by step, then finish with a line "
    "'ANSWER: <number>'."
)

PLANNER = (
    "You decompose a task into independent subtasks. Reply with JSON only: "
    '{"subtasks":[{"id":1,"kind":"calc","desc":"...","confidence":0.0}]}. '
    "kind is one of calc, lookup, verify. confidence is your probability that a general "
    "agent can complete this subtask without help."
)

SPECIALIST = (
    "You are a calculator specialist. You receive exactly one subtask and must answer it "
    "precisely. Show the arithmetic and end with 'RESULT: <number>'."
)

AGGREGATOR = (
    "You combine subtask results into the final answer to the original question. "
    "End with 'ANSWER: <number>'."
)

VERIFIER = (
    "You verify a draft answer to an arithmetic question. Recompute independently; if the "
    "draft is wrong, correct it. End with 'ANSWER: <number>'."
)


def single_agent(task: dict) -> dict:
    model = Model()  # one client per task keeps call accounting per-item exact
    started = time.perf_counter()
    reply = model.complete(SOLVER, task["question"])
    return {
        "arm": "single",
        "id": task["id"],
        "answer": extract_number(reply),
        "expected": task["answer"],
        "calls": model.calls,
        "seconds": round(time.perf_counter() - started, 2),
    }


def multi_agent(task: dict) -> dict:
    model = Model()
    started = time.perf_counter()
    plan = extract_json(model.complete(PLANNER, task["question"]))
    subtasks = plan.get("subtasks") or [{"id": 1, "kind": "calc", "desc": task["question"],
                                        "confidence": 0.5}]

    results: list[str] = []
    routed_to_specialist = 0
    for subtask in subtasks[:3]:
        confidence = float(subtask.get("confidence", 0.5) or 0.5)
        description = str(subtask.get("desc", task["question"]))
        if confidence < 0.7 or str(subtask.get("kind")) == "calc":
            routed_to_specialist += 1
            reply = model.complete(SPECIALIST, description)
        else:
            reply = model.complete(SOLVER, description)
        results.append(reply.strip())

    combined = (
        f"Question: {task['question']}\n\n"
        + "\n".join(f"Subtask result {index + 1}: {text}" for index, text in enumerate(results))
    )
    draft = model.complete(AGGREGATOR, combined)
    final = model.complete(VERIFIER, f"Question: {task['question']}\nDraft answer: {draft}")
    return {
        "arm": "multi",
        "id": task["id"],
        "subtasks": len(subtasks[:3]),
        "routed_to_specialist": routed_to_specialist,
        "answer": extract_number(final),
        "expected": task["answer"],
        "calls": model.calls,
        "seconds": round(time.perf_counter() - started, 2),
    }


def main() -> None:
    tasks = build_tasks()
    singles = parallel(tasks, single_agent)
    multis = parallel(tasks, multi_agent)
    write_jsonl(DATA / "p1_decomposition.jsonl", singles + multis)

    def summarise(rows: list[dict], arm: str) -> None:
        hits = sum(correct(row["answer"], row["expected"]) for row in rows)
        calls = sum(row["calls"] for row in rows) / len(rows)
        seconds = sum(row["seconds"] for row in rows) / len(rows)
        print(f"{arm:7s} accuracy {rate(hits, len(rows))}  "
              f"mean model calls {calls:.2f}  mean latency {seconds:.1f}s")

    print(f"tasks: {len(tasks)}")
    summarise(singles, "single")
    summarise(multis, "multi")
    specialist = sum(row["routed_to_specialist"] for row in multis) / len(multis)
    print(f"mean subtasks routed to the specialist: {specialist:.2f}")


if __name__ == "__main__":
    main()
