"""Generate live test samples with a real model instead of hand-written templates.

The generator is given each registered partner's advertised skills and asks the
pinned model for realistic user messages that should reach that partner. Two
extra classes are generated to probe the boundaries:

* ``ambiguous``  -- a request that plausibly fits two advertised partners;
* ``out_of_scope`` -- a request that no registered partner can serve.

Labels come from the generation request (the target the prompt asks for), and the
model that generates them is the same pinned model used elsewhere; the split
discipline (generator is never the evaluator) still applies, which is why the
runner that scores these samples is a separate script.

Responses are cached so a re-run is free.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = Path("/home/caiyizhang/.hermes/config.yaml")
SYSTEM = (
    "You write realistic user requests for an iMessage personal-assistant test set. "
    "The user is an ordinary person; requests must sound natural, be one or two "
    "sentences, and never mention testing, evaluation, labels, or agent names. "
    "Write every request in Simplified Chinese."
)


def credentials(config_path: Path) -> tuple[str, str, str]:
    base = os.environ.get("GEN_BASE_URL")
    key = os.environ.get("GEN_API_KEY")
    model = os.environ.get("GEN_MODEL")
    if config_path.exists():
        import yaml
        entry = (yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}).get("model", {})
        base = base or entry.get("base_url")
        key = key or entry.get("api_key")
        model = model or entry.get("default")
    if not (base and key and model):
        raise SystemExit("no model credentials; set GEN_BASE_URL/GEN_API_KEY/GEN_MODEL")
    return base.rstrip("/"), key, model


def complete(base: str, key: str, model: str, prompt: str) -> str:
    # No max_tokens: the request leaves the output budget to the model default.
    payload = {
        "model": model, "temperature": 0.8,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
    }
    request = urllib.request.Request(
        base + "/chat/completions", data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
    )
    last: Exception | None = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.load(response)["choices"][0]["message"].get("content") or ""
        except Exception as error:  # noqa: BLE001
            last = error
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"generation failed: {last}")


def parse_messages(content: str, count: int) -> list[str]:
    lines = [line.strip(" -\t") for line in content.splitlines() if line.strip()]
    messages: list[str] = []
    for line in lines:
        line = re.sub(r"^\d+[.)]\s*", "", line).strip().strip('"')
        if len(line) >= 8 and not line.endswith(":"):
            messages.append(line)
    return messages[:count]


def prompt_for_partner(count: int, partner: dict[str, Any]) -> str:
    skills = "\n".join(
        f"- {s.get('name')}: {s.get('description','')} tags={s.get('tags',[])}"
        for s in partner["skills_detail"]
    )
    return (
        f"Write {count} different user requests that should be handled by this assistant capability.\n"
        f"Capability: {partner['name']}\n{skills}\n\n"
        "Vary the phrasing: some indirect, some explicit, some mentioning dates or budget. "
        "Output one request per line, no numbering, no commentary."
    )


def prompt_for_ambiguous(count: int, pairs: list[tuple[str, str]]) -> str:
    listing = "\n".join(f"- {a} vs {b}" for a, b in pairs)
    return (
        f"Write {count} user requests that genuinely fit TWO different capabilities at once, "
        f"so a routing layer would be uncertain.\nOverlapping capability pairs:\n{listing}\n\n"
        "Output one request per line, no numbering, no commentary."
    )


def prompt_for_out_of_scope(count: int, covered: list[str]) -> str:
    return (
        f"Write {count} user requests for tasks that are clearly NOT covered by any of these "
        f"capabilities: {', '.join(covered)}.\n"
        "They must still be plausible requests a person would send to an assistant "
        "(for example legal, medical, or hardware problems).\n"
        "Output one request per line, no numbering, no commentary."
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--roster", type=Path,
                        default=Path("/data/caiyizhang/acps-public-demo/roster/roster.json"))
    parser.add_argument("--acs-dir", type=Path,
                        default=Path("/data/caiyizhang/acps-public-demo/roster/runtime"))
    parser.add_argument("--per-target", type=int, default=5)
    parser.add_argument("--pairs", type=int, default=6)
    parser.add_argument("--out-of-scope", type=int, default=6)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--cache", type=Path, default=Path("experiments/data/live_samples_raw.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("experiments/data/live_samples.jsonl"))
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    base, key, model = credentials(args.config)
    roster = [x for x in json.loads(args.roster.read_text(encoding="utf-8"))
              if x["file"] != "message_forwarder"]
    partners: list[dict[str, Any]] = []
    for entry in roster:
        acs_path = args.acs_dir / entry["file"] / "acs.json"
        if not acs_path.exists():
            continue
        acs = json.loads(acs_path.read_text(encoding="utf-8"))
        partners.append({**entry, "skills_detail": acs.get("skills", [])})

    jobs: list[tuple[str, str, str]] = []  # (class, target aic, prompt)
    for partner in partners:
        jobs.append(("direct", partner["aic"], prompt_for_partner(args.per_target, partner)))
    names = [p["name"] for p in partners]
    pairs = [(names[i], names[(i + 1) % len(names)]) for i in range(min(len(names), 3))]
    jobs.append(("ambiguous", "", prompt_for_ambiguous(args.pairs, pairs)))
    jobs.append(("out_of_scope", "", prompt_for_out_of_scope(args.out_of_scope, names)))

    cache: dict[str, str] = {}
    if args.cache.exists():
        for line in args.cache.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                cache[record["prompt_hash"]] = record["content"]

    def run(job: tuple[str, str, str]) -> tuple[str, str, str, str, str]:
        klass, target, prompt = job
        digest = hashlib.sha256((model + prompt).encode()).hexdigest()[:16]
        if digest in cache:
            return klass, target, prompt, cache[digest], digest
        return klass, target, prompt, complete(base, key, model, prompt), digest

    results: list[tuple[str, str, str, str, str]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(run, jobs):
            results.append(result)
    with args.cache.open("a", encoding="utf-8") as handle:
        for klass, target, prompt, content, digest in results:
            if digest not in cache:
                handle.write(json.dumps({"prompt_hash": digest, "content": content}, ensure_ascii=False) + "\n")
                cache[digest] = content

    by_aic = {p["aic"]: p["name"] for p in partners}
    samples: list[dict[str, Any]] = []
    for klass, target, prompt, content, digest in results:
        count = args.per_target if klass == "direct" else (args.pairs if klass == "ambiguous" else args.out_of_scope)
        for index, text in enumerate(parse_messages(content, count)):
            samples.append({
                "sample_id": f"{klass}-{digest[:6]}-{index:02d}",
                "class": klass,
                "target_aic": target,
                "target_name": by_aic.get(target, ""),
                "text": text,
                "text_hash": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
                "generator_model": model,
                "prompt_hash": digest,
            })
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for sample in samples:
            handle.write(json.dumps(sample, ensure_ascii=False) + "\n")
    counts: dict[str, int] = {}
    for sample in samples:
        counts[sample["class"]] = counts.get(sample["class"], 0) + 1
    print(f"wrote {len(samples)} samples to {args.out} using {model}: {counts}")
    for sample in samples[:3]:
        print("  ", sample["class"], "|", sample["text"][:70])


if __name__ == "__main__":
    main()
