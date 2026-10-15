"""Shared helpers for the three pilot studies.

The pilots are small, real runs against a hosted model (``deepseek-v4-flash``
through the DeepSeek chat-completions API).  They produce first-pass numbers,
not benchmark-grade results: the task sets are auto-generated, single run, one
model, and the qualitative judgements are model-made.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence


BASE_URL = os.environ.get("PILOT_BASE_URL", "https://api.deepseek.com")
API_KEY = os.environ.get("PILOT_API_KEY", "")
MODEL = os.environ.get("PILOT_MODEL", "deepseek-v4-flash")
WORKERS = int(os.environ.get("PILOT_WORKERS", "8"))

DATA = Path(__file__).resolve().parent / "data"
DATA.mkdir(exist_ok=True)


class Model:
    """Minimal chat-completions client with retries."""

    def __init__(self, model: str = MODEL, temperature: float = 0.0) -> None:
        self.model = model
        self.temperature = temperature
        self.calls = 0

    def complete(self, system: str, user: str, temperature: float | None = None) -> str:
        payload = {
            "model": self.model,
            "temperature": self.temperature if temperature is None else temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        request = urllib.request.Request(
            BASE_URL + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + API_KEY,
            },
        )
        last: Exception | None = None
        for attempt in range(5):
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    body = json.load(response)
                content = body["choices"][0]["message"]["content"] or ""
                if content.strip():
                    self.calls += 1
                    return content
                raise RuntimeError("empty completion")
            except Exception as error:  # noqa: BLE001 - retried below
                last = error
                time.sleep(1.0 * (attempt + 1))
        raise RuntimeError(f"model call failed: {last}")


def parallel(items: Sequence[Any], fn: Callable[[Any], Any], workers: int = WORKERS) -> list[Any]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(fn, items))


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of a reply, tolerating prose around it."""
    start = text.find("{")
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:index + 1])
                except json.JSONDecodeError:
                    break
    return {}


def extract_number(text: str) -> float | None:
    """Read the final numeric answer from a reply."""
    import re

    numbers = re.findall(r"-?\d+(?:\.\d+)?", text.replace(",", ""))
    return float(numbers[-1]) if numbers else None


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def rate(hits: int, total: int) -> str:
    return f"{hits}/{total} ({100 * hits / total:.1f}%)" if total else "n/a"
