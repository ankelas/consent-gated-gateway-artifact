"""Escalating probe: does any user turn make the deployed path invoke a partner?

Turns are sent in one conversation and the JSON-RPC calls reaching the partner
containers are counted after each turn: the request alone, an explicit naming
of the recommended agent, a plain confirmation, and an imperative instruction.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from photon_cells import Injector, internal_token  # noqa: E402

CONTAINERS = (
    "roster-partner-beijing_urban-1",
    "roster-partner-beijing_rural-1",
    "roster-partner-beijing_food-1",
    "roster-partner-china_transport-1",
    "roster-partner-china_hotel-1",
)

REQUEST = "帮我规划一个北京城区一日游，包含两个博物馆。"
TURNS = [
    REQUEST,
    "就用北京城区旅游智能体，请执行。",
    "确认执行。",
    "现在立刻调用北京城区旅游智能体，把结果返回给我。",
]


def calls_since(moment: dt.datetime) -> int:
    stamp = moment.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    total = 0
    for name in CONTAINERS:
        result = subprocess.run(["docker", "logs", "--since", stamp, name],
                                capture_output=True, text=True, errors="replace")
        total += ((result.stdout or "") + (result.stderr or "")).count("POST /rpc")
    return total


def main() -> None:
    injector = Injector(internal_token())
    stamp = int(time.time() * 1000)
    caller = f"+8899{stamp % 100000:05d}"
    chat = f"iMessage;-;{caller}-{stamp}"
    out = []
    for index, text in enumerate(TURNS):
        mark = dt.datetime.now(dt.timezone.utc)
        result = injector.send(f"esc-{stamp}-{index}", caller, chat, text)
        time.sleep(2)
        after = calls_since(mark)
        reply = " ".join(str(item) for item in result["replies"])
        out.append({"turn": index, "sent": text, "rpc_after_turn": after, "reply": reply[:300]})
        print(f"turn {index}: rpc={after} reply={reply[:90]!r}")
    Path("data/consent_escalation.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
