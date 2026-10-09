"""Typed advisory judgment consulted by the deployed gateway (J5, semantic replay).

The gateway keeps authorization, identity, state, and side effects in code. The
judgment layer is a plane that modules may consult: it answers one closed
question with a label and a probability, and it never authorizes anything.

Two modes, selected by ``JUDGMENT_MODE``:

* ``off`` (default): the pipeline is byte-for-byte the deployed behaviour; no
  model call is made and no log is written.
* ``advise``: the gateway consults the typed model for every inbound event that
  the event-level store has not already answered, and appends the verdict to
  ``JUDGMENT_LOG``. The verdict is recorded, never acted on, so the measured
  behaviour of routing, consent, and execution is unchanged.

Only prior *user* messages of the same conversation are sent, matching the
minimisation claim in the paper: the model receives a derived projection
(previous request texts), not assistant replies, phone numbers, or identifiers.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

SYSTEM_PROMPT = (
    "你是类型化判断模型，只回答一个封闭问题：当前这条用户消息，是否在语义上重复了"
    "本次会话里此前已经处理过的某个请求？措辞可以不同（改写、换序、同义替换都算重复），"
    "但只要请求的对象或意图不同就算新请求。"
    '只输出 JSON，格式为 {"label":"replay" 或 "new","p_replay":0 到 1 之间的小数}，不要输出解释。'
)


class ReplayJudgment:
    """J5: is this event a semantic replay of an already handled request?"""

    def __init__(
        self,
        *,
        mode: str,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float,
        threshold: float,
        log_path: str,
        max_prior: int,
    ) -> None:
        self.mode = (mode or "off").strip().lower()
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key or ""
        self.model = model or ""
        self.timeout = timeout
        self.threshold = threshold
        self.log_path = log_path
        self.max_prior = max_prior

    @property
    def enabled(self) -> bool:
        return self.mode == "advise" and bool(self.api_key) and bool(self.model)

    async def judge(self, text: str, prior_requests: list[str]) -> dict[str, Any]:
        started = time.monotonic()
        listing = "\n".join(f"{i + 1}. {item}" for i, item in enumerate(prior_requests[-self.max_prior:]))
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"本次会话此前已处理的用户请求：\n{listing or '（无，这是本会话的第一条用户消息）'}\n\n"
                    f"当前用户消息：\n{text}"
                ),
            },
        ]
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        verdict: dict[str, Any] = {"point": "J5", "mode": self.mode, "threshold": self.threshold}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    self.base_url + "/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            label = str(parsed.get("label", "")).strip().lower()
            probability = float(parsed.get("p_replay"))
            verdict.update({
                "label": label if label in {"replay", "new"} else "unparsed",
                "p_replay": max(0.0, min(1.0, probability)),
                "branch": "keyed_result" if probability >= self.threshold else "proceed",
            })
        except Exception as error:  # noqa: BLE001 - an advisory call never blocks ingress
            verdict.update({"label": "error", "p_replay": None, "branch": "proceed",
                            "error": f"{type(error).__name__}: {error}"[:160]})
        verdict["latency_ms"] = round((time.monotonic() - started) * 1000, 1)
        verdict["prior_requests"] = min(len(prior_requests), self.max_prior)
        return verdict

    def log(self, record: dict[str, Any]) -> None:
        try:
            path = Path(self.log_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass
