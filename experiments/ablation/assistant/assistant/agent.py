"""A personal assistant Agent: deliver to its owner, or relay on the owner's behalf."""

from __future__ import annotations

import asyncio
import json
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
from forwarder.agent import post_to_sender
from forwarder.skill import ORIGINATOR_PATTERN, parse_forward_request

from .config import Settings

TERMINAL_STATES = {TaskState.Completed, TaskState.Canceled, TaskState.Failed, TaskState.Rejected}
ACTIVE_STATES = {TaskState.Accepted, TaskState.Working}
ALLOWED_TRANSITIONS = {
    TaskState.Accepted: {TaskState.Working, TaskState.Canceled},
    TaskState.Working: {TaskState.AwaitingInput, TaskState.AwaitingCompletion, TaskState.Canceled, TaskState.Failed},
    TaskState.AwaitingInput: {TaskState.Working, TaskState.Canceled},
    TaskState.AwaitingCompletion: {TaskState.Working, TaskState.Completed, TaskState.Canceled},
}

NO_PEER = "没有找到 {phone} 对应的个人助手，无法投递。请确认对方也已注册个人助手。"
NOT_MINE = "本助手只服务 {owner}，无法代 {originator} 投递给其他人。"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _texts(result: TaskResult) -> list[str]:
    values: list[str] = []
    for product in result.products or []:
        for item in product.dataItems or []:
            if isinstance(item, TextDataItem) and item.text.strip():
                values.append(item.text.strip())
    for item in result.status.dataItems or []:
        if isinstance(item, TextDataItem) and item.text.strip():
            values.append(item.text.strip())
    return values


def split_originator(raw: str) -> tuple[str, str]:
    """Return (originator, content-without-metadata-lines)."""
    originator = ""
    kept: list[str] = []
    for line in (raw or "").splitlines():
        found = ORIGINATOR_PATTERN.search(line)
        if found:
            originator = found.group(1).strip() or originator
            continue
        kept.append(line)
    return originator, "\n".join(kept).strip()


async def call_peer(settings: Settings, endpoint: str, expected_aic: str, text: str) -> dict[str, Any]:
    """Run one AIP task on another assistant and return its product text."""
    ssl_context = None
    if settings.agent_cert_path and settings.agent_key_path:
        ssl_context = ssl.create_default_context(cafile=settings.platform_ca_bundle_path or None)
        ssl_context.load_cert_chain(settings.agent_cert_path, settings.agent_key_path)
    client = AipRpcClient(
        partner_url=endpoint,
        leader_id=settings.agent_aic,
        ssl_context=ssl_context,
        expected_partner_aic=expected_aic or None,
        identity_binding_enabled=bool(expected_aic),
        caller_service="personal-assistant",
        callee_aic=expected_aic,
        callee_service="personal-assistant",
    )
    session_id = f"assistant-{uuid.uuid4()}"
    try:
        result = await client.start_task(session_id, text)
        task_id = result.taskId
        deadline = asyncio.get_running_loop().time() + settings.peer_timeout_seconds
        while result.status.state in ACTIVE_STATES:
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("对方助手在等待时间内没有返回结果")
            await asyncio.sleep(1)
            result = await client.get_task(task_id, session_id)
        if result.status.state == TaskState.AwaitingCompletion:
            product = result
            await client.complete_task(task_id, session_id)
            result = product
        return {
            "state": result.status.state.value,
            "texts": _texts(result),
            "peerTaskId": task_id,
            "failed": result.status.state in {TaskState.Failed, TaskState.Rejected},
        }
    finally:
        await client.close()


class PersonalAssistant:
    """One owner, one phone number.

    Incoming AIP task -> if the sender is the owner, act as Leader and relay to the
    recipient's assistant; if the sender is somebody else's assistant, act as
    Partner and deliver to the owner's phone with a "来自<号码>的消息：" prefix.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.pending_targets: dict[str, str] = {}

    @property
    def handlers(self) -> CommandHandlers:
        return CommandHandlers(
            on_start=self.on_start,
            on_get=self.on_get,
            on_continue=self.on_continue,
            on_complete=self.on_complete,
            on_cancel=self.on_cancel,
        )

    # -------- plumbing --------
    @staticmethod
    def _command_text(command: TaskCommand) -> str:
        return "\n".join(
            item.text.strip()
            for item in command.dataItems or []
            if isinstance(item, TextDataItem) and item.text.strip()
        )

    def _set_identity(self, task: TaskResult) -> TaskResult:
        if self.settings.agent_aic:
            task.senderId = self.settings.agent_aic
        return task

    def _transition(self, task_id: str, next_state: TaskState, data_items: list[Any] | None = None) -> TaskResult:
        task = TaskManager.get_task(task_id)
        if not task:
            raise ValueError(f"task {task_id} does not exist")
        current = task.status.state
        if current == next_state:
            return task
        if next_state not in ALLOWED_TRANSITIONS.get(current, set()):
            raise RuntimeError(f"invalid AIP v2.2 transition: {current.value} -> {next_state.value}")
        return TaskManager.update_task_status(task_id, next_state, data_items)

    def _audit(self, record: dict[str, Any]) -> None:
        try:
            self.settings.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.settings.log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _finish(self, task_id: str, name: str, summary: str, structured: dict[str, Any]) -> None:
        TaskManager.set_products(
            task_id,
            [Product(id=f"product-{uuid.uuid4()}", name=name, dataItems=[TextDataItem(text=summary)])],
        )
        self._transition(task_id, TaskState.AwaitingCompletion)
        self.pending_targets.pop(task_id, None)

    def _await_input(self, task_id: str, prompt: str, phone: str | None) -> None:
        if phone:
            self.pending_targets[task_id] = phone
        self._transition(task_id, TaskState.AwaitingInput, [TextDataItem(text=prompt)])

    def _fail(self, task_id: str, text: str) -> None:
        task = TaskManager.get_task(task_id)
        if task and task.status.state not in TERMINAL_STATES:
            self._transition(task_id, TaskState.Failed, [TextDataItem(text=text)])

    # -------- Partner role: someone sends to my owner --------
    async def _deliver_to_owner(self, task_id: str, originator: str, content: str) -> None:
        if not content:
            self._fail(task_id, "收到的消息内容为空，没有投递。")
            return
        text = f"来自{originator}的消息：{content}"
        try:
            outcome = await post_to_sender(self.settings, self.settings.owner_phone, text)
        except Exception as exc:
            self._audit({"at": _now(), "taskId": task_id, "role": "deliver", "from": originator, "result": "failed", "error": str(exc)})
            self._fail(task_id, f"投递给 {self.settings.owner_phone} 失败：{exc}")
            return
        message_id = str(outcome.get("messageId") or "")
        self._audit(
            {
                "at": _now(),
                "taskId": task_id,
                "role": "deliver",
                "owner": self.settings.owner_phone,
                "from": originator,
                "messageId": message_id,
                "characters": len(content),
                "preview": content[:80],
                "result": "delivered",
            }
        )
        self._finish(
            task_id,
            "消息投递结果",
            f"已把来自 {originator} 的消息投递给 {self.settings.owner_phone}。（messageId: {message_id}）",
            {"owner": self.settings.owner_phone, "from": originator, "messageId": message_id, "result": "delivered"},
        )

    # -------- Leader role: my owner asks me to send to somebody --------
    async def _relay_for_owner(self, task_id: str, target: str, content: str) -> None:
        peer = self.settings.directory.get(target)
        if not peer:
            try:
                peer = await self._discover_peer(target)
            except Exception as exc:
                self._fail(task_id, f"查找 {target} 的个人助手失败：{exc}")
                return
        if not peer or not peer.get("endpoint"):
            self._fail(task_id, NO_PEER.format(phone=target))
            return
        forwarded = f"发送方号码：{self.settings.owner_phone}\n{content}"
        try:
            outcome = await call_peer(self.settings, peer["endpoint"], peer.get("aic", ""), forwarded)
        except Exception as exc:
            self._audit({"at": _now(), "taskId": task_id, "role": "relay", "to": target, "result": "failed", "error": str(exc)})
            self._fail(task_id, f"调用 {target} 的个人助手失败：{exc}")
            return
        texts = outcome.get("texts") or []
        self._audit(
            {
                "at": _now(),
                "taskId": task_id,
                "role": "relay",
                "owner": self.settings.owner_phone,
                "to": target,
                "peerAic": peer.get("aic", ""),
                "peerTaskId": outcome.get("peerTaskId"),
                "characters": len(content),
                "preview": content[:80],
                "result": "failed" if outcome.get("failed") else "relayed",
            }
        )
        if outcome.get("failed"):
            self._fail(task_id, f"{target} 的个人助手返回：\n" + ("\n".join(texts) or "未说明原因"))
            return
        self._finish(
            task_id,
            "转发结果",
            f"已通过 {target} 的个人助手投递。（对方回复：{texts[0] if texts else '已完成'}）",
            {"to": target, "peerAic": peer.get("aic", ""), "result": "relayed"},
        )

    @staticmethod
    def _candidate_blocks(text: str) -> list[str]:
        """Split a discovery answer into per-candidate blocks (each starts with "- ")."""
        blocks: list[str] = []
        current: list[str] = []
        for line in (text or "").splitlines():
            if line.strip().startswith("- "):
                if current:
                    blocks.append("\n".join(current))
                current = [line]
            elif current:
                current.append(line)
        if current:
            blocks.append("\n".join(current))
        return blocks

    async def _discover_peer(self, target: str) -> dict[str, str] | None:
        """Resolve the assistant that serves `target` with an exact, filtered query.

        The platform's discovery API supports filters over ACS fields, and every
        personal assistant tags its skills with its owner's number, so this is a
        deterministic lookup. Semantic search is deliberately *not* used: an LLM
        answer can echo the queried number inside a candidate's name line and
        produce a confident but wrong peer.
        """
        return await find_assistant_for_number(
            target, base_url=self.settings.discovery_api_url or DEFAULT_DISCOVERY_API_URL
        )

    # -------- AIP commands --------
    async def on_start(self, command: TaskCommand, existing: TaskResult | None) -> TaskResult:
        if existing:
            TaskManager.add_command_to_history(existing.taskId, command)
            return self._set_identity(existing)
        task = TaskManager.create_task(command, initial_state=TaskState.Accepted)
        asyncio.create_task(self._run(task.taskId, self._command_text(command)))
        snapshot = TaskResult.model_validate(task.model_dump())
        return self._set_identity(snapshot)

    async def on_get(self, command: TaskCommand, task: TaskResult) -> TaskResult:
        TaskManager.add_command_to_history(task.taskId, command)
        return self._set_identity(task)

    async def on_continue(self, command: TaskCommand, task: TaskResult) -> TaskResult:
        TaskManager.add_command_to_history(task.taskId, command)
        if task.status.state != TaskState.AwaitingInput:
            return self._set_identity(task)
        text = self._command_text(command)
        if not text:
            return self._set_identity(task)
        asyncio.create_task(self._run(task.taskId, text))
        return self._set_identity(task)

    async def on_complete(self, command: TaskCommand, task: TaskResult) -> TaskResult:
        TaskManager.add_command_to_history(task.taskId, command)
        if task.status.state == TaskState.AwaitingCompletion:
            self._transition(task.taskId, TaskState.Completed)
        return self._set_identity(TaskManager.get_task(task.taskId) or task)

    async def on_cancel(self, command: TaskCommand, task: TaskResult) -> TaskResult:
        TaskManager.add_command_to_history(task.taskId, command)
        if task.status.state not in TERMINAL_STATES:
            self._transition(task.taskId, TaskState.Canceled)
        return self._set_identity(TaskManager.get_task(task.taskId) or task)

    async def _run(self, task_id: str, raw_text: str) -> None:
        try:
            self._transition(task_id, TaskState.Working)
            originator, content = split_originator(raw_text)
            if originator and originator != self.settings.owner_phone:
                await self._deliver_to_owner(task_id, originator, content)
                return
            request = parse_forward_request(raw_text)
            if not request.actionable:
                self._await_input(task_id, request.problem, request.phone)
                return
            if request.phone == self.settings.owner_phone:
                await self._deliver_to_owner(task_id, self.settings.owner_phone, request.text)
                return
            await self._relay_for_owner(task_id, request.phone or "", request.text)
        except Exception as exc:
            self._fail(task_id, f"助手执行失败：{exc}")
