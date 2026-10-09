"""Run LLM-generated samples through the live personal-assistant Leader.

Each sample is injected with a fresh caller and conversation, because the
adapter caches a reply per conversation and a reused conversation would return
an unrelated stored answer. The selected partner(s) are read back from the
assistant's own reply text, which names the chosen capability; that extraction
is lexical and is reported as such.

No outbound message is produced: the adapter returns its reply as JSON.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

from photon_cells import Injector, internal_token


NO_AGENT_MARKERS = ("没有找到", "暂未找到", "无法完成", "没有合适的", "暂无", "找不到")
CLARIFY_MARKERS = ("请补充", "请提供", "请说明", "需要您", "能否告诉", "请问您")


def entry_from_roster(path: Path, extra: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Return name->aic and aic->name maps for the live partners."""
    roster = json.loads(path.read_text(encoding="utf-8"))
    name_to_aic: dict[str, str] = {}
    aic_to_name: dict[str, str] = {}
    for entry in roster:
        acs = extra / entry["file"] / "acs.json"
        if not acs.exists():
            continue
        name = json.loads(acs.read_text(encoding="utf-8")).get("name") or entry["name"]
        name_to_aic[name] = entry["aic"]
        aic_to_name[entry["aic"]] = name
    return name_to_aic, aic_to_name


SECTION_HEADER = re.compile(r"\*\*([^*]+)\*\*")
BULLET = re.compile(r"^\s*[-*]\s*(.+?)\s*(?:（|\(| / |：|:)", re.M)
QUOTED_NAME = re.compile(r"[「『\"]([^」』\"\n]{2,60})[」』\"]")


def _sections(reply: str) -> tuple[str, list[tuple[str, str]]]:
    """Split the reply into its preamble and its bold-marked sections."""
    sections: list[tuple[str, str]] = []
    cursor = 0
    heading: str | None = None
    for match in SECTION_HEADER.finditer(reply):
        if heading is not None:
            sections.append((heading, reply[cursor:match.start()]))
        heading = match.group(1)
        cursor = match.end()
    if heading is not None:
        sections.append((heading, reply[cursor:]))
    first = SECTION_HEADER.search(reply)
    return (reply[:first.start()] if first else reply), sections


def recommended_agents(reply: str) -> list[str]:
    """Leading names of the bullets in the reply's recommendation section."""
    preamble, sections = _sections(reply)
    leading: list[str] = []
    for heading, body in sections:
        name = heading.strip()
        if name.startswith("推荐") or ("推荐" in name and "组合" in name):
            leading.extend(entry.strip() for entry in BULLET.findall(body))
    if not leading:
        leading = QUOTED_NAME.findall(preamble)
    return leading


def extract(reply: str, name_to_aic: dict[str, str]) -> tuple[list[str], list[str]]:
    """Recommended names, read from the reply's recommendation section.

    A name counts only when it leads a bullet inside the bold section whose
    heading announces the recommendation. Names that appear elsewhere are not
    selections: the recall line counts how many agents the index returned, the
    AIC/Endpoint sections echo the same block, and the closing candidate list
    offers every retrieved agent, including ones the recommendation rejects.
    """
    leading = recommended_agents(reply)

    def canonical(value: str) -> str:
        return re.split(r"[（(]", value)[0].strip()

    names: list[str] = []
    for name in name_to_aic:
        if not name:
            continue
        short = canonical(name)
        if any(short in entry for entry in leading):
            names.append(name)
    return names, [name_to_aic[name] for name in names]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=Path, default=Path("experiments/data/live_samples.jsonl"))
    parser.add_argument("--roster", type=Path,
                        default=Path("/data/caiyizhang/acps-public-demo/roster/roster.json"))
    parser.add_argument("--acs-dir", type=Path,
                        default=Path("/data/caiyizhang/acps-public-demo/roster/runtime"))
    parser.add_argument("--out", type=Path, default=Path("experiments/data/live_sample_runs.jsonl"))
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    name_to_aic, _ = entry_from_roster(args.roster, args.acs_dir)
    samples = [json.loads(line) for line in args.samples.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        samples = samples[:args.limit]

    injector = Injector(internal_token())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for index, sample in enumerate(samples, 1):
            stamp = int(time.time() * 1000)
            caller = f"+88{index:08d}"
            chat = f"iMessage;-;{caller}-{stamp}"
            result = injector.send(f"ls-{stamp}-{index}", caller, chat, sample["text"])
            reply = " ".join(str(item) for item in result["replies"])
            names, aics = extract(reply, name_to_aic)
            recommended = recommended_agents(reply)
            row: dict[str, Any] = {
                **sample,
                "selected_names": names,
                "selected_aics": aics,
                "recommended_agents": recommended,
                "target_hit": bool(sample["target_aic"]) and sample["target_aic"] in aics,
                "no_agent": any(marker in reply for marker in NO_AGENT_MARKERS),
                "clarification": any(marker in reply for marker in CLARIFY_MARKERS),
                "reply_head": reply[:160],
                "reply": reply,
                "t_ms": result["t_ms"],
                "error": result["error"],
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            print(f"[{index}/{len(samples)}] {sample['class']:13s} target={(sample['target_name'] or '-')[:12]:14s} "
                  f"selected={[n[:10] for n in names] or 'NONE'} hit={row['target_hit']} t={result['t_ms']:.0f}ms")
    print(f"wrote {len(samples)} runs to {args.out}")


if __name__ == "__main__":
    main()
