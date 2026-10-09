"""Sample set for the deployed J5 (semantic replay) judgment.

Each conversation carries three events:

* ``base``       - the first request of the conversation (baseline);
* ``paraphrase`` - the same intent in different words, sent with a new message
  id, so the event-level store cannot answer it;
* ``different``  - a request in the same capability domain but with a different
  object or intent, used as a hard negative.

Requests come from the routing suite, so the replay experiment runs on the same
distribution as the rest of the study. Paraphrases and negatives are generated
by the same pinned model, as in the routing suite.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import urllib.request

SYSTEM = (
    "你在为一个智能体网关构造语义重放测试集。给定一条用户请求 A，输出 JSON："
    '{"paraphrase": "...", "different": "..."}。'
    "paraphrase 要与 A 表达同一个意图与同一个对象，只改措辞、语序或句式；"
    "different 要与 A 属于同一能力领域，但对象或意图明显不同。"
    "两条都用简体中文，长度接近 A，不要照抄 A 的整句。"
)


def credentials() -> tuple[str, str, str]:
    base = os.environ.get("GEN_BASE_URL")
    key = os.environ.get("GEN_API_KEY")
    model = os.environ.get("GEN_MODEL")
    if not (base and key and model):
        raise SystemExit("set GEN_BASE_URL/GEN_API_KEY/GEN_MODEL")
    return base.rstrip("/"), key, model


def generate(base_url: str, key: str, model: str, request: str) -> dict[str, str]:
    payload = {
        "model": model,
        "temperature": 0.8,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"用户请求 A：{request}"},
        ],
    }
    request = urllib.request.Request(
        base_url + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        body = json.loads(response.read().decode("utf-8"))
    return json.loads(body["choices"][0]["message"]["content"])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("data/live_samples_v2.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("data/judgment_advise_samples.jsonl"))
    parser.add_argument("--count", type=int, default=20)
    args = parser.parse_args()

    base_url, key, model = credentials()
    rows = [json.loads(line) for line in args.source.read_text(encoding="utf-8").splitlines() if line.strip()]
    direct = [row for row in rows if row.get("class") == "direct"][: args.count]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as handle:
        for index, row in enumerate(direct):
            made = generate(base_url, key, model, row["text"])
            record = {
                "conversation": f"j5-{index:02d}",
                "domain": row.get("target_name", ""),
                "base": row["text"],
                "paraphrase": made["paraphrase"].strip(),
                "different": made["different"].strip(),
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            handle.flush()
            print(f"[{index + 1}/{len(direct)}] {record['domain'][:14]:16s} {record['paraphrase'][:38]}")
    print(f"wrote {len(direct)} conversations to {args.out}")


if __name__ == "__main__":
    main()
