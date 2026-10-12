from __future__ import annotations

import json
import os

import asyncio
import re
import ssl
import uuid
from datetime import datetime, timezone
from time import time
from typing import Any

from acps_sdk.aip.aip_base_model import (
    Product,
    StructuredDataItem,
    TaskCommand,
    TaskResult,
    TaskState,
    TextDataItem,
)
from acps_sdk.aip.aip_rpc_client import AipRpcClient
from acps_sdk.aip.aip_rpc_server import CommandHandlers, TaskManager

from acps_directory import DEFAULT_DISCOVERY_API_URL, find_assistant_for_number
from forwarder.skill import parse_forward_request

from .config import Settings
from .llm import LlmRouter
from .store import StateStore

TERMINAL_STATES = {TaskState.Completed, TaskState.Canceled, TaskState.Failed, TaskState.Rejected}
ACTIVE_STATES = {TaskState.Accepted, TaskState.Working}
ALLOWED_TRANSITIONS = {
    TaskState.Accepted: {TaskState.Working, TaskState.Canceled},
    TaskState.Working: {TaskState.AwaitingInput, TaskState.AwaitingCompletion, TaskState.Canceled, TaskState.Failed},
    TaskState.AwaitingInput: {TaskState.Working, TaskState.Canceled},
    TaskState.AwaitingCompletion: {TaskState.Working, TaskState.Completed, TaskState.Canceled},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _texts(result: TaskResult) -> list[str]:
    """Return presentable text without depending on an Agent's chat formatting."""
    values: list[str] = []
    for product in result.products or []:
        for item in product.dataItems or []:
            if isinstance(item, TextDataItem) and item.text.strip():
                values.append(item.text.strip())
    for item in result.status.dataItems or []:
        if isinstance(item, TextDataItem) and item.text.strip():
            values.append(item.text.strip())
    return values


class WutongIMessageAgent:
    """Photon ingress plus an ACPs AIP v2.2 Leader orchestration layer.

    Photon is only the outside message transport.  For cross-agent work this
    service is the Leader: it calls Discovery first, then invokes one safe,
    discoverable AIP JSON-RPC Partner using this adapter's own mTLS identity.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.store = StateStore(settings.state_db_path)
        self.llm = LlmRouter(settings)
        # The SDK TaskManager is process-local. SQLite keeps only replay-safe
        # Photon state and context, never a pretend resumable SDK task.
        self.contexts: dict[str, dict[str, Any]] = {}
        # owner phone -> personal assistant endpoint/aic (or None when unknown)
        self._assistant_cache: dict[str, dict[str, str] | None] = {}

    @property
    def handlers(self) -> CommandHandlers:
        return CommandHandlers(
            on_start=self.on_start,
            on_get=self.on_get,
            on_continue=self.on_continue,
            on_complete=self.on_complete,
            on_cancel=self.on_cancel,
        )

    def _set_identity(self, task: TaskResult) -> TaskResult:
        if self.settings.adapter_aic:
            task.senderId = self.settings.adapter_aic
        return task

    @staticmethod
    def _command_text(command: TaskCommand) -> str:
        return "\n".join(
            item.text.strip()
            for item in command.dataItems or []
            if isinstance(item, TextDataItem) and item.text.strip()
        )

    def _persist(self, task_id: str) -> None:
        context = self.contexts.get(task_id)
        if context and context.get("caller_id"):
            self.store.save_task_context(context["caller_id"], task_id, context)

    def _transition(
        self, task_id: str, next_state: TaskState, data_items: list[Any] | None = None
    ) -> TaskResult:
        """Apply only the transitions defined by the AIP v2.2 state table."""
        task = TaskManager.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} does not exist")
        current = task.status.state
        if current == next_state:
            return task
        if next_state not in ALLOWED_TRANSITIONS.get(current, set()):
            raise RuntimeError(f"invalid AIP v2.2 transition: {current.value} -> {next_state.value}")
        return TaskManager.update_task_status(task_id, next_state, data_items)

    async def _start(
        self, command: TaskCommand, caller_id: str, chat_guid: str = "", initial_context: dict[str, Any] | None = None
    ) -> TaskResult:
        # v2.2 Start creates Accepted (not Working); the background execution
        # transitions it to Working once it has been scheduled.
        task = self._set_identity(TaskManager.create_task(command, initial_state=TaskState.Accepted))
        self.contexts[task.taskId] = {
            "caller_id": caller_id,
            "chat_guid": chat_guid,
            "text": self._command_text(command),
            "session_id": task.sessionId or "",
            "waiting_on": None,
            "discovery": {},
            "partner": {},
            **(initial_context or {}),
        }
        self._persist(task.taskId)
        # Return an Accepted snapshot. The background coroutine mutates the
        # TaskManager object independently and must not race response encoding.
        accepted_snapshot = TaskResult.model_validate(task.model_dump())
        asyncio.create_task(self._run(task.taskId))
        return accepted_snapshot

    async def on_start(self, command: TaskCommand, existing: TaskResult | None) -> TaskResult:
        # Idempotent Start is a v2.2 requirement.
        if existing:
            TaskManager.add_command_to_history(existing.taskId, command)
            return self._set_identity(existing)
        caller = f"aip:{command.senderId}" if self.settings.aip_server_identity_binding_enabled else "aip:direct"
        return await self._start(command, caller_id=caller)

    async def on_get(self, command: TaskCommand, task: TaskResult) -> TaskResult:
        TaskManager.add_command_to_history(task.taskId, command)
        return self._set_identity(task)

    async def on_continue(self, command: TaskCommand, task: TaskResult) -> TaskResult:
        if task.status.state not in {TaskState.AwaitingInput, TaskState.AwaitingCompletion}:
            TaskManager.add_command_to_history(task.taskId, command)
            return self._set_identity(task)
        text = self._command_text(command)
        if not text:
            TaskManager.add_command_to_history(task.taskId, command)
            return self._set_identity(task)
        TaskManager.add_command_to_history(task.taskId, command)
        self._transition(task.taskId, TaskState.Working)
        context = self.contexts.setdefault(
            task.taskId,
            {"caller_id": "aip:direct", "chat_guid": "", "session_id": task.sessionId or "", "discovery": {}, "partner": {}},
        )
        context["text"] = text
        self._persist(task.taskId)
        asyncio.create_task(self._run(task.taskId, continuing=True))
        return self._set_identity(TaskManager.get_task(task.taskId))

    async def on_complete(self, command: TaskCommand, task: TaskResult) -> TaskResult:
        """The external Leader accepts a completed local product explicitly."""
        TaskManager.add_command_to_history(task.taskId, command)
        if task.status.state == TaskState.AwaitingCompletion:
            self._transition(task.taskId, TaskState.Completed)
            self._persist(task.taskId)
        return self._set_identity(TaskManager.get_task(task.taskId))

    async def on_cancel(self, command: TaskCommand, task: TaskResult) -> TaskResult:
        TaskManager.add_command_to_history(task.taskId, command)
        if task.status.state not in TERMINAL_STATES:
            self._transition(task.taskId, TaskState.Canceled)
        self._persist(task.taskId)
        return self._set_identity(TaskManager.get_task(task.taskId))

    def _simple_reply(self, text: str) -> str | None:
        normal = text.strip().lower()
        if normal in {"help", "帮助", "你好", "hi", "hello"}:
            return "你好，我可以介绍梧桐平台入口，也可以帮你寻找合适的智能体。直接描述你的需求即可。"
        if "注册" in text or "registry" in normal:
            return "智能体注册平台：https://wt.ioa.pub/registry/"
        if "wit" in normal or "梧庭" in text:
            return "WIT 入口：https://wt.ioa.pub/wit/\n使用说明：https://wt.ioa.pub/docs.html"
        if "flux" in normal or "凤翎" in text or "雁羽" in text or "yanyu" in normal:
            return "Flux 入口：https://wt.ioa.pub/flux/\n雁羽入口：https://wt.ioa.pub/yanyu/"
        if "叮当" in text or "dingdang" in normal:
            return "叮当入口：https://wt.ioa.pub/dingdang/"
        if "文档" in text or "docs" in normal or "指南" in text:
            return "梧桐平台使用指南：https://wt.ioa.pub/docs.html"
        return None

    def _aip_client(self, endpoint: str, expected_aic: str, label: str) -> AipRpcClient:
        s = self.settings
        if not s.adapter_aic:
            raise RuntimeError("未配置本适配器 AIC（IMESSAGE_ADAPTER_AIC）")
        context = ssl.create_default_context(cafile=s.platform_ca_bundle_path or None)
        # ACPs identity is the AIC carried in the certificate URI SAN, not the
        # host name, so keep chain verification but not host-name matching.
        context.check_hostname = False
        if s.agent_cert_path and s.agent_key_path:
            context.load_cert_chain(s.agent_cert_path, s.agent_key_path)
        elif s.discovery_identity_binding_enabled:
            raise RuntimeError(f"mTLS 调用{label}需要 AGENT_CERT_PATH 和 AGENT_KEY_PATH")
        return AipRpcClient(
            partner_url=endpoint,
            leader_id=s.adapter_aic,
            ssl_context=context,
            expected_partner_aic=expected_aic or None,
            identity_binding_enabled=s.discovery_identity_binding_enabled,
            caller_service="imessage-aip-leader",
            callee_aic=expected_aic,
            callee_service=label,
        )

    async def _run_remote(
        self,
        task_id: str,
        remote_name: str,
        endpoint: str,
        partner_aic: str,
        text: str,
        *,
        continuing: bool,
    ) -> TaskResult:
        """Run one downstream AIP task, acknowledging its product as Leader.

        A downstream Partner's AwaitingCompletion is not a terminal result: the
        Leader first sends Complete, then uses the preserved product to produce
        its own local product.
        """
        context = self.contexts[task_id]
        remote = context.setdefault(remote_name, {})
        client = self._aip_client(endpoint, partner_aic, remote_name)
        try:
            remote_task_id = remote.get("task_id")
            remote_session_id = remote.get("session_id") or f"imessage-{remote_name}-{task_id}"
            if continuing and remote_task_id:
                result = await client.continue_task(remote_task_id, remote_session_id, text)
            else:
                result = await client.start_task(remote_session_id, text)
                remote_task_id = result.taskId
            remote.update(
                task_id=remote_task_id,
                session_id=remote_session_id,
                endpoint=endpoint,
                partner_aic=partner_aic,
                state=result.status.state.value,
            )
            self._persist(task_id)

            deadline = asyncio.get_running_loop().time() + self.settings.discovery_timeout_seconds
            while result.status.state in ACTIVE_STATES:
                if asyncio.get_running_loop().time() >= deadline:
                    raise TimeoutError(f"{remote_name}在等待时间内未返回可处理状态")
                await asyncio.sleep(1)
                result = await client.get_task(remote_task_id, remote_session_id)
                remote["state"] = result.status.state.value
                self._persist(task_id)

            if result.status.state == TaskState.AwaitingCompletion:
                product_result = result
                confirmed = await client.complete_task(remote_task_id, remote_session_id)
                remote["state"] = confirmed.status.state.value
                self._persist(task_id)
                return product_result
            return result
        finally:
            await client.close()

    @staticmethod
    def _extract_assistant(texts: list[str], number: str) -> dict[str, str] | None:
        """Pick the candidate whose block mentions `number` and return its endpoint/AIC."""
        digits = "".join(char for char in number if char.isdigit())
        for text in texts:
            for block in re.split(r"\n(?=- )", text or ""):
                name_line = block.splitlines()[0] if block.splitlines() else ""
                mentions = any(
                    "".join(char for char in token if char.isdigit()) == digits
                    for token in re.findall(r"\+?\d[\d\s\-]{6,20}", name_line)
                )
                if not mentions:
                    continue
                endpoint = re.search(r"(https://[^\s，,、）)]*/rpc)\b", block)
                aic = re.search(r"AIC[:：]\s*(1\.2\.156\.3088[0-9A-Za-z.]*)", block)
                if endpoint and aic:
                    return {"endpoint": endpoint.group(1), "aic": aic.group(1)}
        return None

    async def _find_owner_assistant(self, number: str) -> dict[str, str] | None:
        """Resolve the personal assistant serving `number` (cached per process)."""
        if number in self._assistant_cache:
            return self._assistant_cache[number]
        try:
            peer = await find_assistant_for_number(
                number, base_url=self.settings.discovery_api_url or DEFAULT_DISCOVERY_API_URL
            )
        except Exception:
            peer = None
        self._assistant_cache[number] = peer
        return peer

    async def _unused_semantic_lookup(self, number: str) -> dict[str, str] | None:
        peer: dict[str, str] | None = None
        if self.settings.discovery_agent_url and self.settings.discovery_agent_aic:
            client = None
            try:
                client = self._aip_client(
                    self.settings.discovery_agent_url, self.settings.discovery_agent_aic, "discovery"
                )
                session_id = f"assistant-lookup-{uuid.uuid4()}"
                result = await client.start_task(
                    session_id, f"个人助手 {number}：负责把消息投递给号码 {number} 的主人"
                )
                remote_task_id = result.taskId
                deadline = asyncio.get_running_loop().time() + self.settings.discovery_timeout_seconds
                while result.status.state in ACTIVE_STATES:
                    if asyncio.get_running_loop().time() >= deadline:
                        raise TimeoutError("personal assistant lookup timed out")
                    await asyncio.sleep(1)
                    result = await client.get_task(remote_task_id, session_id)
                if result.status.state == TaskState.AwaitingCompletion:
                    product = result
                    await client.complete_task(remote_task_id, session_id)
                    result = product
                peer = self._extract_assistant(_texts(result), number)
            except Exception:
                peer = None
            finally:
                if client is not None:
                    await client.close()
        self._assistant_cache[number] = peer
        return peer

    def _discovery_payload(self, result: TaskResult) -> dict[str, Any]:
        """Read the v2.2 structured Product from Discovery Agent, not its prose."""
        for product in result.products or []:
            for item in product.dataItems or []:
                if isinstance(item, StructuredDataItem) and isinstance(item.data, dict):
                    if "selected_combination" in item.data:
                        return item.data
        return {}

    @staticmethod
    def _pending_candidates(discovery: dict[str, Any]) -> list[dict[str, str]]:
        """Turn Discovery's structured v2.2 combination into user-selectable choices."""
        combo = discovery.get("selected_combination")
        if not isinstance(combo, list):
            return []
        choices: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in combo:
            if not isinstance(item, dict):
                continue
            agent = item.get("agent") if isinstance(item.get("agent"), dict) else item
            aic = str(item.get("aic") or agent.get("aic") or "").strip()
            if not aic or aic in seen:
                continue
            seen.add(aic)
            skill = item.get("skill") if isinstance(item.get("skill"), dict) else {}
            endpoints = item.get("endPoints") or item.get("endpoints") or agent.get("endPoints") or agent.get("endpoints") or []
            safe_endpoint = ""
            if isinstance(endpoints, list):
                for endpoint in endpoints:
                    if not isinstance(endpoint, dict):
                        continue
                    url = str(endpoint.get("url") or "").strip()
                    transport = str(endpoint.get("transport") or "").replace("-", "").upper()
                    if url.startswith("https://") and transport in {"JSONRPC", "AIPRPC"}:
                        safe_endpoint = url
                        break
            choices.append(
                {
                    "aic": aic,
                    "name": str(agent.get("name") or aic),
                    "skill_name": str(skill.get("name") or item.get("skillId") or ""),
                    "description": str(skill.get("description") or agent.get("description") or ""),
                    "endpoint": safe_endpoint,
                }
            )
        return choices

    @staticmethod
    def _choice_prompt(raw: str, candidates: list[dict[str, str]]) -> str:
        if not candidates:
            return raw
        lines = [raw.rstrip(), "", "可选择的智能体："]
        for index, candidate in enumerate(candidates, start=1):
            name = candidate.get("name") or candidate.get("aic") or "未命名智能体"
            skill = candidate.get("skill_name") or "未标注技能"
            description = str(candidate.get("description") or "").strip()
            line = f"{index}. {name}（{skill}）"
            if description:
                line += f"：{description}"
            if not candidate.get("endpoint"):
                line += "（当前仅可查看，不支持由适配器直接调用）"
            lines.append(line)
        lines.extend([
            "", "如果你希望我继续调用其中一个智能体，请明确回复：",
            "使用 1：<希望它完成的具体任务>",
            "例如：使用 1：根据我接下来提供的病例资料生成会诊意见。",
            "也可以回复“暂不使用”或直接提出新的需求。",
        ])
        return "\n".join(lines)

    async def _pending_choice(
        self, text: str, pending: dict[str, Any], caller_id: str, chat_guid: str
    ) -> tuple[str, dict[str, str] | None, str, str]:
        """Return action, selected candidate, explicit instruction and reply."""
        candidates = [item for item in pending.get("candidates", []) if isinstance(item, dict)]
        conversation = self.store.conversation(caller_id, chat_guid) or {}
        history = self.store.history(caller_id, chat_guid, self.settings.llm_max_history_messages)
        decision = await self.llm.decide_pending_choice(text, candidates, history, conversation.get("summary", ""))
        if decision:
            if decision.action == "execute":
                candidate = next((item for item in candidates if item.get("aic") == decision.candidate_aic), None)
                if candidate and candidate.get("endpoint") and decision.instruction:
                    return "execute", candidate, decision.instruction, decision.reply
                return "wait", None, "", "所选智能体暂未提供可安全调用的 HTTPS JSON-RPC 接口，请选择其他候选或直接访问其页面。"
            return decision.action, None, "", decision.reply

        normalized = text.strip().lower()
        if normalized in {"暂不使用", "不使用", "取消", "算了", "不用了"}:
            return "cancel", None, "", "好的，本次不会调用候选智能体。"
        if "重新" in text and any(word in text for word in ("找", "发现", "搜索")):
            return "rediscover", None, "", ""
        # Without an LLM, deliberately require a strict, unambiguous fallback.
        match = re.match(r"^(?:使用|用)\s*(?:第\s*)?(\d+)\s*(?:个)?\s*[:：]\s*(.+)$", text.strip(), flags=re.S)
        if match:
            index, instruction = int(match.group(1)) - 1, match.group(2).strip()
            if 0 <= index < len(candidates) and instruction and candidates[index].get("endpoint"):
                return "execute", candidates[index], instruction, ""
        return "wait", None, "", ""

    def _finish(self, task_id: str, name: str, text: str) -> None:
        """Publish a local product then wait for the upstream Leader's Complete."""
        TaskManager.set_products(
            task_id,
            [Product(id=f"product-{uuid.uuid4()}", name=name, dataItems=[TextDataItem(text=text)])],
        )
        self._transition(task_id, TaskState.AwaitingCompletion)
        self.contexts.get(task_id, {})["waiting_on"] = None

    def _await_input(self, task_id: str, source: str, result: TaskResult) -> None:
        prompt = _texts(result) or ["请补充更多需求或上下文。"]
        self.contexts[task_id]["waiting_on"] = source
        self._transition(task_id, TaskState.AwaitingInput, [TextDataItem(text="\n".join(prompt))])

    def _fail(self, task_id: str, text: str) -> None:
        task = TaskManager.get_task(task_id)
        if task and task.status.state not in TERMINAL_STATES:
            self._transition(task_id, TaskState.Failed, [TextDataItem(text=text)])

    async def _handle_partner_result(self, task_id: str, result: TaskResult) -> None:
        if result.status.state == TaskState.AwaitingInput:
            self._await_input(task_id, "partner", result)
            return
        if result.status.state in {TaskState.AwaitingCompletion, TaskState.Completed}:
            answer = "\n\n".join(_texts(result) or ["目标智能体已完成，但没有返回可展示的结果。"])
            self._finish(task_id, "协作智能体结果", answer)
            return
        detail = "\n".join(_texts(result))
        self._fail(
            task_id,
            f"目标智能体返回状态：{result.status.state.value}" + (f"\n{detail}" if detail else ""),
        )

    async def _discover_and_offer(self, task_id: str, text: str, *, continuing: bool) -> None:
        """Discover, complete the remote discovery task, then wait for user choice.

        No target Partner is started in this method. Waiting is represented only
        by a small expiring SQLite record, not by a live socket or remote task.
        """
        result = await self._run_remote(
            task_id,
            "discovery",
            self.settings.discovery_agent_url,
            self.settings.discovery_agent_aic,
            text,
            continuing=continuing,
        )
        if result.status.state == TaskState.AwaitingInput:
            self._await_input(task_id, "discovery", result)
            return
        if result.status.state not in {TaskState.AwaitingCompletion, TaskState.Completed}:
            self._fail(task_id, f"发现 Agent 返回状态：{result.status.state.value}")
            return

        discovery = self._discovery_payload(result)
        raw = "\n\n".join(_texts(result) or ["发现 Agent 已完成，但没有返回可展示的结果。"])
        answer = await self.llm.present_discovery(text, raw) if self.llm.enabled else raw
        candidates = self._pending_candidates(discovery)
        context = self.contexts[task_id]
        caller_id, chat_guid = context.get("caller_id", ""), context.get("chat_guid", "")
        if candidates and caller_id and chat_guid:
            self.store.save_pending_agent_choices(
                caller_id,
                chat_guid,
                text,
                candidates,
                answer,
                int(time()) + max(60, self.settings.pending_selection_ttl_seconds),
            )
            answer = self._choice_prompt(answer, candidates)
        self._finish(task_id, "智能体发现结果", answer)

    @staticmethod
    def _originator_number(caller_id: str) -> str:
        """Return the requester's phone number from a caller namespace, if any."""
        prefix, _, tail = caller_id.partition(":")
        if prefix in {"photon", "telegram", "webchat"} and tail.startswith("+"):
            return tail
        return ""

    def _partner_text(self, context: dict[str, Any], text: str) -> str:
        """Tell a downstream Agent which number the request came from.

        The AIP client only carries text, so the originator travels as a labelled
        first line. The message forwarding Agent turns it into
        "来自<号码>的消息：<内容>" for whoever receives the forward.
        """
        number = self._originator_number(str(context.get("caller_id") or ""))
        return f"发送方号码：{number}\n{text}" if number else text

    async def _run(self, task_id: str, continuing: bool = False) -> None:
        task = TaskManager.get_task(task_id)
        if not task or task.status.state in TERMINAL_STATES:
            return
        try:
            if task.status.state == TaskState.Accepted:
                self._transition(task_id, TaskState.Working)
            context = self.contexts.get(task_id, {})
            text = str(context.get("text") or "")
            if not text:
                self._fail(task_id, "没有收到可处理的文本内容。")
                return

            waiting_on = context.get("waiting_on") if continuing else None
            if waiting_on == "partner":
                remote = context.get("partner") or {}
                partner_result = await self._run_remote(
                    task_id,
                    "partner",
                    str(remote.get("endpoint") or ""),
                    str(remote.get("partner_aic") or ""),
                    self._partner_text(context, text),
                    continuing=True,
                )
                await self._handle_partner_result(task_id, partner_result)
                return
            if waiting_on == "discovery":
                await self._discover_and_offer(task_id, text, continuing=True)
                return

            # Per-user personal assistants: when a user asks to send a message to
            # somebody, hand the whole request to *that user's* assistant, which
            # discovers the recipient's assistant and relays through it
            # (用户A -> 智能体A -> 智能体B -> 用户B).
            owner_number = self._originator_number(str(context.get("caller_id") or ""))
            if owner_number and not continuing and parse_forward_request(text).actionable:
                assistant = await self._find_owner_assistant(owner_number)
                if assistant:
                    assistant_result = await self._run_remote(
                        task_id,
                        "assistant",
                        assistant["endpoint"],
                        assistant["aic"],
                        self._partner_text(context, text),
                        continuing=False,
                    )
                    await self._handle_partner_result(task_id, assistant_result)
                    return

            # A selected Partner has already been confirmed by the user. Do not
            # send its instruction through the first-stage intent router again.
            if context.get("selected_partner"):
                candidate = context["selected_partner"]
                partner_result = await self._run_remote(
                    task_id, "partner", candidate["endpoint"], candidate["aic"], self._partner_text(context, text), continuing=False
                )
                await self._handle_partner_result(task_id, partner_result)
                return

            decision = None
            caller_id, chat_guid = context.get("caller_id", "aip:direct"), context.get("chat_guid", "")
            conversation = self.store.conversation(caller_id, chat_guid) if chat_guid else None
            if self.llm.enabled:
                history = self.store.history(caller_id, chat_guid, self.settings.llm_max_history_messages) if chat_guid else []
                decision = await self.llm.decide(text, history, (conversation or {}).get("summary", ""))
                if decision and chat_guid and decision.summary:
                    self.store.save_conversation(caller_id, chat_guid, summary=decision.summary)
            if decision and decision.action == "reply" and decision.reply:
                self._finish(task_id, "梧桐平台说明", decision.reply)
                return
            if decision and decision.action == "clarify":
                self.contexts[task_id]["waiting_on"] = "local"
                self._transition(task_id, TaskState.AwaitingInput, [TextDataItem(text=decision.reply or "请补充更多需求或上下文。")])
                return
            simple = None if (continuing or decision) else self._simple_reply(text)
            if simple:
                self._finish(task_id, "梧桐平台说明", simple)
                return
            if not self.settings.discovery_agent_url or not self.settings.discovery_agent_aic:
                raise RuntimeError("未配置发现 Agent 地址或 AIC")
            await self._discover_and_offer(task_id, decision.query if decision and decision.query else text, continuing=False)
        except Exception as exc:
            self._fail(task_id, f"处理请求失败：{exc}")
        finally:
            self._persist(task_id)

    async def photon_message(self, caller_id: str, message_id: str, chat_guid: str, text: str) -> dict[str, Any]:
        # STAGING ABLATION ONLY (copy under /data/caiyizhang/ablation):
        # ABLATION_SKIP_DEDUP=1 removes the event-level dedup lookup. The
        # execution log is written only when a delivery actually enters
        # processing, so it counts executions rather than deliveries; the state
        # table itself would collapse duplicates because of its primary key.
        cached = None if os.getenv("ABLATION_SKIP_DEDUP") == "1" else self.store.event_response(caller_id, message_id)
        if cached:
            return cached
        _exec_log = os.getenv("ABLATION_EXEC_LOG", "")
        if _exec_log:
            with open(_exec_log, "a", encoding="utf-8") as _fh:
                _fh.write(json.dumps({"caller_id": caller_id, "message_id": message_id}, ensure_ascii=False) + "\n")
        self.store.add_message(caller_id, chat_guid, "user", text)
        conversation = self.store.conversation(caller_id, chat_guid)
        task: TaskResult | None = None
        continuing = False
        if conversation and conversation.get("local_task_id"):
            task = TaskManager.get_task(conversation["local_task_id"])
            continuing = bool(task and task.status.state == TaskState.AwaitingInput)

        # A completed discovery has no live remote task. Its candidates remain
        # as a short-lived per-user/per-chat SQLite choice only.
        selected_candidate: dict[str, str] | None = None
        selected_instruction = ""
        if not continuing:
            pending = self.store.pending_agent_choices(caller_id, chat_guid, int(time()))
            if pending:
                action, candidate, instruction, reply = await self._pending_choice(text, pending, caller_id, chat_guid)
                if action == "cancel":
                    self.store.clear_pending_agent_choices(caller_id, chat_guid)
                    messages = [reply or "好的，本次不会调用候选智能体。"]
                    for message in messages:
                        self.store.add_message(caller_id, chat_guid, "assistant", message)
                    response = {"messages": messages}
                    self.store.save_event_response(caller_id, message_id, response)
                    return response
                if action == "wait":
                    reminder = reply or self._choice_prompt(pending.get("discovery_reply", ""), pending.get("candidates", []))
                    messages = [reminder]
                    for message in messages:
                        self.store.add_message(caller_id, chat_guid, "assistant", message)
                    response = {"messages": messages}
                    self.store.save_event_response(caller_id, message_id, response)
                    return response
                if action == "execute":
                    if not self.settings.selected_agent_execution_enabled:
                        messages = ["当前适配器未启用已选智能体调用。你可以先查看上述候选说明，或稍后再试。"]
                        for message in messages:
                            self.store.add_message(caller_id, chat_guid, "assistant", message)
                        response = {"messages": messages}
                        self.store.save_event_response(caller_id, message_id, response)
                        return response
                    self.store.clear_pending_agent_choices(caller_id, chat_guid)
                    selected_candidate, selected_instruction = candidate, instruction
                elif action == "rediscover":
                    self.store.clear_pending_agent_choices(caller_id, chat_guid)

        if continuing and task:
            command = TaskCommand(
                id=f"cmd-{uuid.uuid4()}", sentAt=_now(), senderRole="leader",
                senderId=self.settings.adapter_aic or "imessage-photon", command="continue",
                taskId=task.taskId, sessionId=task.sessionId, dataItems=[TextDataItem(text=text)],
            )
            await self.on_continue(command, task)
        else:
            task_id, session_id = f"task-{uuid.uuid4()}", f"photon-{uuid.uuid4()}"
            command = TaskCommand(
                id=f"cmd-{uuid.uuid4()}", sentAt=_now(), senderRole="leader",
                senderId=self.settings.adapter_aic or "imessage-photon", command="start",
                taskId=task_id, sessionId=session_id, dataItems=[TextDataItem(text=text)],
            )
            # Only an explicit choice plus an explicit instruction reaches a
            # selected Partner. All other new messages go through intent → discovery.
            command_text = selected_instruction or text
            if selected_instruction:
                command.dataItems = [TextDataItem(text=command_text)]
            task = await self._start(
                command,
                caller_id=caller_id,
                chat_guid=chat_guid,
                initial_context={"selected_partner": selected_candidate} if selected_candidate else None,
            )
            self.store.save_conversation(caller_id, chat_guid, session_id=session_id, local_task_id=task.taskId)

        deadline = asyncio.get_running_loop().time() + self.settings.local_task_timeout_seconds
        while task.status.state in ACTIVE_STATES and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.3)
            task = TaskManager.get_task(task.taskId) or task
        # Photon is a transport, not an AIP Leader.  It receives only text;
        # AIP state is negotiated with downstream Agents in _run_remote.
        messages = _texts(task)
        if task.status.state == TaskState.AwaitingInput and not messages:
            messages = ["请补充更多信息后继续。"]
        if task.status.state in ACTIVE_STATES:
            messages = ["我仍在处理中，请稍后再发送一条消息继续查看结果。"]
        if task.status.state == TaskState.Failed and not messages:
            messages = ["这次处理没有完成，请稍后重试。"]
        # A local TaskManager object is only an implementation detail for the
        # Photon conversation. Its product has already been handed to the
        # bridge, so clean it up without creating a Photon-facing AIP round.
        if task.status.state == TaskState.AwaitingCompletion:
            self._transition(task.taskId, TaskState.Completed)
            task = TaskManager.get_task(task.taskId) or task
        response = {"messages": messages}
        for message in messages:
            self.store.add_message(caller_id, chat_guid, "assistant", message)
        self.store.save_event_response(caller_id, message_id, response)
        current = self.contexts.get(task.taskId, {})
        active_remote = current.get(current.get("waiting_on") or "partner") or current.get("discovery") or {}
        self.store.save_conversation(
            caller_id,
            chat_guid,
            session_id=task.sessionId or "",
            local_task_id=task.taskId,
            upstream_task_id=active_remote.get("task_id"),
            upstream_session_id=active_remote.get("session_id"),
            upstream_state=active_remote.get("state"),
        )
        return response
