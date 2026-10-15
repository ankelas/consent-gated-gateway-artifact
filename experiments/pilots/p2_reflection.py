"""Pilot 2: forward planning with retrospective reflection over tools.

Twenty-four auto-generated tasks whose answers are computed in Python.  Arm A
plans once and executes; arm B adds online verification of the tool results and
a reflection round that repairs the plan when the check fails.
"""

from __future__ import annotations

import ast
import json
import math
import operator
import random
import time

from pilot_common import Model, extract_json, extract_number, parallel, rate, write_jsonl, DATA


WORD_LIST = ["banana", "triangle", "umbrella", "kangaroo", "mountain", "festival"]
TEMPS = {"beijing": 22, "tokyo": 27, "paris": 18, "cairo": 33, "sydney": 25}
OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.Div: operator.truediv, ast.Pow: operator.pow, ast.USub: operator.neg}


def is_prime(value: int) -> bool:
    return value > 1 and all(value % d for d in range(2, int(value ** 0.5) + 1))


def nth_prime(n: int) -> int:
    found, candidate = 0, 1
    while found < n:
        candidate += 1
        if is_prime(candidate):
            found += 1
    return candidate


def safe_eval(expression: str) -> float:
    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.BinOp):
            return OPS[type(node.op)](walk(node.left), walk(node.right))
        if isinstance(node, ast.UnaryOp):
            return OPS[type(node.op)](walk(node.operand))
        raise ValueError("unsupported expression")

    return walk(ast.parse(expression, mode="eval"))


TOOLS = {
    "calc": lambda expr: round(safe_eval(expr), 4),
    "nth_prime": lambda n: nth_prime(int(n)),
    "letters": lambda word: len(str(word).strip()),
    "temp": lambda city: TEMPS[str(city).strip().lower()],
    "convert": lambda value, frm, to: {
        ("km", "mi"): lambda v: round(v * 0.621371, 4),
        ("mi", "km"): lambda v: round(v / 0.621371, 4),
        ("c", "f"): lambda v: round(v * 9 / 5 + 32, 4),
        ("f", "c"): lambda v: round((v - 32) * 5 / 9, 4),
    }[(str(frm).strip().lower(), str(to).strip().lower())](float(value)),
}

TOOL_SPEC = json.dumps(
    {
        "calc": {"expr": "arithmetic expression, e.g. '12*(3+4)'"},
        "nth_prime": {"n": "positive integer"},
        "letters": {"word": "single word"},
        "temp": {"city": "one of beijing, tokyo, paris, cairo, sydney"},
        "convert": {"value": "number", "frm": "km|mi|c|f", "to": "km|mi|c|f"},
    },
    indent=2,
)


def build_tasks(count: int = 24) -> list[dict]:
    rng = random.Random(20261015)
    tasks = []
    for index in range(count):
        kind = index % 4
        if kind == 0:
            city = rng.choice(list(TEMPS))
            extra = rng.randint(2, 9)
            question = (f"What is the temperature in {city} degrees Celsius plus {extra}? "
                        "Give the final number.")
            answer = TEMPS[city] + extra
        elif kind == 1:
            value = rng.randint(10, 80)
            question = (f"Convert {value} kilometres to miles (1 km = 0.621371 mi) and round "
                        "to two decimals. Give the final number.")
            answer = round(value * 0.621371, 2)
        elif kind == 2:
            n = rng.randint(3, 11)
            word = rng.choice(WORD_LIST)
            question = (f"Multiply the {n}th prime by the number of letters in '{word}'. "
                        "Give the final number.")
            answer = nth_prime(n) * len(word)
        else:
            celsius = rng.randint(5, 35)
            question = (f"Convert {celsius} degrees Celsius to Fahrenheit using "
                        "F = C*9/5+32. Give the final number.")
            answer = round(celsius * 9 / 5 + 32, 2)
        tasks.append({"id": index + 1, "question": question, "answer": answer})
    return tasks


def build_hard_tasks() -> list[dict]:
    """Task families that actually create failure modes for a one-shot planner.

    * dependent: the second call needs the first call's output, so a plan that
      fixes both arguments up front cannot be executed as written;
    * failing: the natural first call fails (unknown city, unsupported unit),
      so the agent has to notice the error and repair the plan;
    * plain: an ordinary single-call task, kept as a control.
    """
    rng = random.Random(20261016)
    tasks: list[dict] = []
    for index in range(8):
        city = rng.choice(list(TEMPS))
        question = (
            f"Take the temperature in {city} (degrees Celsius) and convert exactly that many "
            "kilometres into miles at 0.621371 miles per kilometre. Give the final number "
            "to two decimals."
        )
        tasks.append({"id": f"dep-{index + 1}", "family": "dependent", "question": question,
                      "answer": round(TEMPS[city] * 0.621371, 2)})
    unknown = ["atlantis", "gotham", "shangri-la", "el-dorado"]
    for index in range(8):
        city = unknown[index % len(unknown)]
        extra = rng.randint(2, 9)
        question = (
            f"The temperature in {city} is recorded in the tool table. Add {extra} to it and "
            "report the number. If the city is not in the table, tell me the correct number "
            "for Beijing instead."
        )
        tasks.append({"id": f"fail-{index + 1}", "family": "failing", "question": question,
                      "answer": TEMPS["beijing"] + extra})
    for index in range(8):
        n = rng.randint(3, 11)
        word = rng.choice(WORD_LIST)
        question = (
            f"Multiply the {n}th prime by the number of letters in '{word}'. Give the final "
            "number."
        )
        tasks.append({"id": f"plain-{index + 1}", "family": "plain", "question": question,
                      "answer": nth_prime(n) * len(word)})
    return tasks


def correct(value: float | None, expected: float) -> bool:
    return value is not None and abs(value - expected) < 0.02


PLANNER = (
    "You plan tool calls. Reply with JSON only: "
    '{"calls":[{"tool":"calc","args":{"expr":"..."}}]}. '
    "Available tools and their arguments:\n" + TOOL_SPEC
)

ANSWERER = (
    "You answer the question using the recorded tool outputs. Do not use outside knowledge. "
    "End with 'ANSWER: <number>'."
)

CHECKER = (
    "You verify whether the recorded tool outputs are sufficient and consistent with the "
    "question. Reply with JSON only: "
    '{"ok":true|false,"reason":"...","extra_calls":[{"tool":"...","args":{}}]}. '
    "Set ok=false only if a tool call is missing, wrong, or failed. Available tools:\n"
    + TOOL_SPEC
)


def run_calls(calls: list[dict]) -> tuple[list[str], list[str], list[dict]]:
    """Execute planned calls, returning transcripts plus the calls that worked."""
    transcripts, errors, executed = [], [], []
    for call in calls[:4]:
        name = str(call.get("tool", "")).strip()
        args = call.get("args") or {}
        try:
            if name == "convert":
                result = TOOLS[name](args.get("value"), args.get("frm"), args.get("to"))
            else:
                result = TOOLS[name](*[args[key] for key in args]) if isinstance(args, dict) else None
            transcripts.append(f"{name}({json.dumps(args)}) -> {result}")
            executed.append(call)
        except Exception as error:  # noqa: BLE001 - recorded as a failed call
            message = f"{name}({json.dumps(args)}) -> ERROR {type(error).__name__}"
            transcripts.append(message)
            errors.append(message)
    return transcripts, errors, executed


def plan_and_execute(task: dict, reflect: bool) -> dict:
    model = Model()
    started = time.perf_counter()
    question = task["question"]
    plan = extract_json(model.complete(PLANNER, question))
    calls = plan.get("calls") or []
    transcripts, errors, _ = run_calls(calls)
    tool_invocations = len(transcripts)
    reflections = 0

    if reflect:
        # Online verification of the tool outputs before answering.
        check = extract_json(
            model.complete(CHECKER, f"Question: {question}\nTool outputs:\n" + "\n".join(transcripts))
        )
        rounds = 0
        while check and not check.get("ok", True) and rounds < 2:
            reflections += 1
            repairs = check.get("extra_calls") or []
            extra_transcripts, extra_errors, _ = run_calls(repairs)
            transcripts += extra_transcripts
            errors += extra_errors
            tool_invocations += len(extra_transcripts)
            rounds += 1
            check = extract_json(
                model.complete(
                    CHECKER,
                    f"Question: {question}\nTool outputs:\n" + "\n".join(transcripts),
                )
            )

    answer = model.complete(
        ANSWERER, f"Question: {question}\nTool outputs:\n" + "\n".join(transcripts)
    )
    return {
        "arm": "reflect" if reflect else "plan_only",
        "id": task["id"],
        "answer": extract_number(answer),
        "expected": task["answer"],
        "tool_invocations": tool_invocations,
        "failed_calls": len(errors),
        "reflections": reflections,
        "calls": model.calls,
        "seconds": round(time.perf_counter() - started, 2),
    }


def main() -> None:
    tasks = build_hard_tasks()
    plan_only = parallel(tasks, lambda task: plan_and_execute(task, reflect=False))
    reflected = parallel(tasks, lambda task: plan_and_execute(task, reflect=True))
    write_jsonl(DATA / "p2_reflection.jsonl", plan_only + reflected)

    for arm, rows in (("plan only", plan_only), ("plan+reflect", reflected)):
        hits = sum(correct(row["answer"], row["expected"]) for row in rows)
        tools = sum(row["tool_invocations"] for row in rows) / len(rows)
        calls = sum(row["calls"] for row in rows) / len(rows)
        failed = sum(row["failed_calls"] for row in rows)
        print(f"{arm:12s} accuracy {rate(hits, len(rows))}  mean tool calls {tools:.2f}  "
              f"mean model calls {calls:.2f}  failed tool calls {failed}")
        for family in ("dependent", "failing", "plain"):
            subset = [row for row in rows if str(row["id"]).startswith(family[:3])]
            hits = sum(correct(row["answer"], row["expected"]) for row in subset)
            print(f"    {family:10s} {rate(hits, len(subset))}")
    triggered = [row for row in reflected if row["reflections"] > 0]
    recovered = sum(correct(row["answer"], row["expected"]) for row in triggered)
    print(f"reflection triggered on {len(triggered)}/{len(reflected)} tasks; "
          f"of those {rate(recovered, len(triggered))} finished correct")
    before = {row["id"]: row for row in plan_only if row["reflections"] == 0}
    broken = [row for row in plan_only if not correct(row["answer"], row["expected"])]
    fixed = [row for row in broken if correct(
        next(r["answer"] for r in reflected if r["id"] == row["id"]),
        row["expected"],
    )]
    print(f"tasks the first pass got wrong: {len(broken)}; reflection fixed {len(fixed)}")


if __name__ == "__main__":
    main()
