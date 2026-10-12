from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from .config import Settings


@dataclass(frozen=True)
class LlmDecision:
    action: str  # reply | discover | clarify
    reply: str = ""
    query: str = ""
    summary: str = ""


@dataclass(frozen=True)
class PendingChoiceDecision:
    action: str  # execute | wait | cancel | rediscover
    candidate_aic: str = ""
    instruction: str = ""
    reply: str = ""


class LlmRouter:
    """Optional OpenAI-compatible intent and explicit-choice routing layer."""

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def enabled(self) -> bool:
        s = self.settings
        return bool(s.llm_enabled and s.llm_api_key and s.llm_model)

    async def _chat(self, messages: list[dict[str, str]]) -> str | None:
        if not self.enabled:
            return None
        headers = {"Authorization": f"Bearer {self.settings.llm_api_key}", "Content-Type": "application/json"}
        payload = {"model": self.settings.llm_model, "messages": messages, "temperature": 0.2}
        url = self.settings.llm_base_url.rstrip("/") + "/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=self.settings.llm_timeout_seconds) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                content = response.json()["choices"][0]["message"]["content"]
                return content.strip() if isinstance(content, str) else None
        except Exception:
            return None

    @staticmethod
    def _json(text: str | None) -> dict[str, Any] | None:
        if not text:
            return None
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        try:
            value = json.loads(text)
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            first, last = text.find("{"), text.rfind("}")
            if first >= 0 and last > first:
                try:
                    value = json.loads(text[first : last + 1])
                    return value if isinstance(value, dict) else None
                except json.JSONDecodeError:
                    pass
        return None

    async def decide(self, user_text: str, history: list[dict[str, str]], conversation_summary: str) -> LlmDecision | None:
        content = await self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你是梧桐平台 iMessage 助手的意图路由器。先判断用户意图。"
                        "reply 仅用于不需要外部智能体的普通聊天、平台入口和一般说明；"
                        "discover 用于任何需要专业能力、实际执行、分析、创作、检索或用户明确想找智能体的需求；"
                        "clarify 仅用于无法理解且无法形成可用于发现的查询。"
                        "不要因为用户没有说‘找智能体’就把实际任务当作普通聊天。"
                        "只输出 JSON："
                        '{"action":"reply|discover|clarify","reply":"给用户的中文回复","query":"交给发现 Agent 的查询","summary":"不超过80字的会话摘要"}。'
                        "平台已知入口：WIT https://wt.ioa.pub/wit/；Flux https://wt.ioa.pub/flux/；"
                        "叮当 https://wt.ioa.pub/dingdang/；注册 https://wt.ioa.pub/registry/；文档 https://wt.ioa.pub/docs.html。"
                    ),
                },
                *history,
                {"role": "user", "content": f"会话摘要：{conversation_summary or '无'}\n本次消息：{user_text}"},
            ]
        )
        data = self._json(content)
        if not data:
            return None
        action = str(data.get("action", "")).lower()
        if action not in {"reply", "discover", "clarify"}:
            return None
        return LlmDecision(
            action=action,
            reply=str(data.get("reply", "")).strip(),
            query=str(data.get("query", "")).strip(),
            summary=str(data.get("summary", "")).strip()[:500],
        )

    async def decide_pending_choice(
        self, user_text: str, candidates: list[dict[str, Any]], history: list[dict[str, str]], conversation_summary: str
    ) -> PendingChoiceDecision | None:
        compact = [
            {
                "number": index + 1,
                "aic": candidate.get("aic", ""),
                "name": candidate.get("name", ""),
                "skill": candidate.get("skill_name", ""),
                "description": str(candidate.get("description", ""))[:300],
                "callable": bool(candidate.get("endpoint")),
            }
            for index, candidate in enumerate(candidates[:8])
        ]
        content = await self._chat(
            [
                {
                    "role": "system",
                    "content": (
                        "用户此前得到了一份智能体候选清单。只有同时满足："
                        "（1）用户明确选中清单中的某一个智能体；（2）用户给出了要它实际执行的明确指令，"
                        "才输出 execute。仅问候、追问候选能力、‘用一下’、‘第一个’、‘好的’都不是明确执行指令。"
                        "用户表示不需要则 cancel；提出新的独立需求则 rediscover；其余为 wait。"
                        "candidate_aic 必须精确来自候选清单；instruction 只能是用户明确要求目标执行的内容，不能编造。"
                        "只输出 JSON："
                        '{"action":"execute|wait|cancel|rediscover","candidate_aic":"","instruction":"","reply":""}。'
                    ),
                },
                {"role": "system", "content": f"候选清单：{json.dumps(compact, ensure_ascii=False)}"},
                *history[-6:],
                {"role": "user", "content": f"会话摘要：{conversation_summary or '无'}\n本次消息：{user_text}"},
            ]
        )
        data = self._json(content)
        if not data:
            return None
        action = str(data.get("action", "")).lower()
        if action not in {"execute", "wait", "cancel", "rediscover"}:
            return None
        candidate_aic = str(data.get("candidate_aic", "")).strip()
        if action == "execute" and (not candidate_aic or not str(data.get("instruction", "")).strip()):
            return PendingChoiceDecision(action="wait")
        return PendingChoiceDecision(
            action=action,
            candidate_aic=candidate_aic,
            instruction=str(data.get("instruction", "")).strip(),
            reply=str(data.get("reply", "")).strip(),
        )

    async def present_discovery(self, query: str, raw_result: str) -> str:
        content = await self._chat(
            [
                {
                    "role": "system",
                    "content": "把智能体发现结果整理成简洁、诚实的中文回复。不得补充结果中不存在的能力或链接；保留关键智能体名称、能力、调用提示。",
                },
                {"role": "user", "content": f"用户需求：{query}\n发现结果：{raw_result}"},
            ]
        )
        return content or raw_result
