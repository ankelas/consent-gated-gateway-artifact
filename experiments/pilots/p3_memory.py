"""Pilot 3: consistency of a long-horizon conversational agent.

Five scripted personas talk to the assistant over four sessions with a
gap-filling distractor in each.  Arm A sees only the current session; arm B
keeps a three-layer memory (working turns, episode summaries, semantic facts)
with relevance/recency/importance retrieval and a consistency check before the
reply is sent.  Probes at the end measure fact retention and whether the
assistant keeps the persona's earlier constraints.
"""

from __future__ import annotations

import re
import time

from pilot_common import Model, extract_json, parallel, rate, write_jsonl, DATA


PERSONAS = [
    {
        "name": "Ada",
        "facts": {"city": "Lisbon", "job": "marine biologist",
                  "pet": "a corgi named Pixel", "allergy": "shellfish",
                  "drink": "flat white", "hobby": "bouldering"},
        "distractor": "My sister, not me, is vegetarian.",
        "trap": "I am planning a seafood dinner this weekend - anything I should watch out for?",
        "trap_key": "shellfish",
    },
    {
        "name": "Bruno",
        "facts": {"city": "Chengdu", "job": "structural engineer",
                  "pet": "a rescue cat called Miso", "allergy": "peanuts",
                  "drink": "oolong tea", "hobby": "rowing"},
        "distractor": "My colleague, not me, runs marathons.",
        "trap": "I bought a bag of peanut snacks for the office - good idea?",
        "trap_key": "peanut",
    },
    {
        "name": "Chen",
        "facts": {"city": "Helsinki", "job": "game developer",
                  "pet": "two rabbits named Salt and Pepper", "allergy": "penicillin",
                  "drink": "black coffee", "hobby": "cross-country skiing"},
        "distractor": "My brother, not me, collects stamps.",
        "trap": "My doctor mentioned an antibiotic - should I flag anything?",
        "trap_key": "penicillin",
    },
    {
        "name": "Dalia",
        "facts": {"city": "Marrakesh", "job": "architect",
                  "pet": "a parrot named Zizou", "allergy": "latex",
                  "drink": "mint tea", "hobby": "pottery"},
        "distractor": "My flatmate, not me, is a night owl.",
        "trap": "I am buying new gloves for the workshop - anything to avoid?",
        "trap_key": "latex",
    },
    {
        "name": "Emil",
        "facts": {"city": "Tallinn", "job": "data engineer",
                  "pet": "a greyhound named Juno", "allergy": "bee stings",
                  "drink": "espresso", "hobby": "sailing"},
        "distractor": "My cousin, not me, keeps bees.",
        "trap": "We are planning a garden picnic with flowers everywhere - any risk?",
        "trap_key": "bee",
    },
]

SESSION_SCRIPT = [
    ["I live in {city}.", "I work as a {job}.", "I have {pet}."],
    ["I am allergic to {allergy}.", "My usual drink is a {drink}."],
    ["My main hobby is {hobby}."],
    [],
]

RECALL = [
    ("Which city do I live in?", "city"),
    ("What is my job?", "job"),
    ("What pet do I have?", "pet"),
    ("What am I allergic to?", "allergy"),
    ("What is my usual drink?", "drink"),
    ("What is my main hobby?", "hobby"),
]

ASSISTANT = "You are a friendly long-term assistant talking with {name}."

FACT_EXTRACTOR = (
    "Extract durable facts about the user from the conversation. Reply with JSON only: "
    '{"facts":[{"key":"...","value":"...","importance":0.0}]}. '
    "importance is 1.0 for constraints such as allergies, otherwise 0.6."
)

SUMMARISER = (
    "Summarise the episode in two sentences, keeping facts about the user and any open "
    "threads. Plain text."
)

CHECKER = (
    "You check a draft reply against known facts about the user. Reply with JSON only: "
    '{"conflict":true|false,"revised":"..."}. Set conflict=true and provide a corrected '
    "reply if the draft contradicts or ignores a stored constraint."
)


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def retrieve(memory: list[dict], query: str, keep: int = 6) -> list[dict]:
    scored = []
    for item in memory:
        relevance = len(tokens(item["value"]) & tokens(query))
        recency = item["session"] / 4
        score = relevance * 1.0 + 0.5 * recency + item["importance"]
        scored.append((score, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored[:keep]]


def memory_block(items: list[dict]) -> str:
    if not items:
        return ""
    lines = "\n".join(f"- {item['key']}: {item['value']}" for item in items)
    return "Known facts about the user:\n" + lines + "\n\n"


def consistency_check(model: Model, facts: list[dict], question: str, draft: str) -> str:
    verdict = extract_json(
        model.complete(
            CHECKER,
            memory_block(facts) + f"User message: {question}\nDraft reply: {draft}",
        )
    )
    if verdict.get("conflict") and verdict.get("revised"):
        return str(verdict["revised"])
    return draft


def run_persona(persona: dict, use_memory: bool) -> dict:
    model = Model(temperature=0.3)
    name = persona["name"]
    facts = [{"key": key, "value": value, "session": 0, "importance": 0.6}
             for key, value in persona["facts"].items()]
    for fact in facts:
        if fact["key"] == "allergy":
            fact["importance"] = 1.0

    working: list[str] = []
    transcript: list[dict] = []
    reflections = 0

    for session, lines in enumerate(SESSION_SCRIPT, start=1):
        session_lines = [line.format(**persona["facts"]) for line in lines]
        if session == 2:
            session_lines.append(persona["distractor"])
        for line in session_lines:
            retrieved = retrieve(
                [fact for fact in facts if fact["session"] < session], line
            ) if use_memory else []
            system = ASSISTANT.format(name=name)
            prompt = memory_block(retrieved) + f"User: {line}"
            if use_memory:
                prompt += "\n\nAlso keep the earlier turns of this session in mind: " \
                          + " | ".join(working[-4:])
            reply = model.complete(system, prompt)
            if use_memory:
                checked = consistency_check(model, retrieved, line, reply)
                if checked != reply:
                    reflections += 1
                reply = checked
            working.append(f"U: {line} | A: {reply[:160]}")
            transcript.append({"session": session, "user": line, "reply": reply})

        if use_memory:
            # End-of-session consolidation: episodic summary plus semantic facts.
            episode = "\n".join(f"User: {turn['user']}\nAssistant: {turn['reply']}"
                                for turn in transcript if turn["session"] == session)
            model.complete(SUMMARISER, episode)
            extracted = extract_json(
                model.complete(FACT_EXTRACTOR, episode)
            ).get("facts", [])
            for item in extracted:
                key = str(item.get("key", "")).lower()
                value = str(item.get("value", "")).strip()
                if not key or not value:
                    continue
                existing = next((fact for fact in facts if fact["key"] == key), None)
                importance = float(item.get("importance", 0.6) or 0.6)
                if existing:
                    existing["value"] = value
                    existing["session"] = session
                else:
                    facts.append({"key": key, "value": value, "session": session,
                                  "importance": importance})

    # Probes after the last session.
    probes = []
    for question, key in RECALL:
        expected = persona["facts"][key]
        retrieved = retrieve(facts, question) if use_memory else []
        reply = model.complete(
            ASSISTANT.format(name=name), memory_block(retrieved) + f"User: {question}"
        )
        hit = expected.lower() in reply.lower()
        probes.append({"kind": "recall", "question": question, "expected": expected,
                       "reply": reply, "correct": hit})

    for question, key in ((persona["trap"], persona["trap_key"]),):
        retrieved = retrieve(facts, question) if use_memory else []
        reply = model.complete(
            ASSISTANT.format(name=name), memory_block(retrieved) + f"User: {question}"
        )
        hit = key.lower() in reply.lower()
        probes.append({"kind": "constraint", "question": question, "expected": key,
                       "reply": reply, "correct": hit})

    return {
        "arm": "memory" if use_memory else "session_only",
        "persona": name,
        "reflections": reflections,
        "probes": probes,
        "calls": model.calls,
        "seconds": 0.0,
    }


def main() -> None:
    started = time.perf_counter()
    runs = parallel(PERSONAS, lambda persona: run_persona(persona, use_memory=False)) \
        + parallel(PERSONAS, lambda persona: run_persona(persona, use_memory=True))
    write_jsonl(DATA / "p3_memory.jsonl", runs)

    for arm in ("session_only", "memory"):
        rows = [run for run in runs if run["arm"] == arm]
        recall = [probe for run in rows for probe in run["probes"] if probe["kind"] == "recall"]
        constraint = [probe for run in rows for probe in run["probes"] if probe["kind"] == "constraint"]
        hits = sum(probe["correct"] for probe in recall)
        kept = sum(probe["correct"] for probe in constraint)
        calls = sum(run["calls"] for run in rows)
        print(f"{arm:13s} fact retention {rate(hits, len(recall))}  "
              f"constraint kept {rate(kept, len(constraint))}  model calls {calls}")
    print(f"probes: recall {len(RECALL)} per persona, constraint 1 per persona, "
          f"5 personas per arm; wall clock {time.perf_counter() - started:.0f}s")


if __name__ == "__main__":
    main()
