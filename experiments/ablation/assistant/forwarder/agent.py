"""ACPs AIP v2.2 Partner Agent that forwards a message to a phone number."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from acps_sdk.aip.aip_base_model import (
    Product,
    StructuredDataItem,
    TaskCommand,
    TaskResult,
    TaskState,
    TextDataItem,
)
from acps_sdk.aip.aip_rpc_server import CommandHandlers, TaskManager

from .config import Settings
from .skill import NOT_ALLOWED, parse_forward_request

TERMINAL_STATES = {
    TaskState.Completed,
    TaskState.Canceled,
    TaskState.Failed,
    TaskState.Rejected,
}
ALLOWED_TRANSITIONS = {
    TaskState.Accepted: {TaskState.Working, TaskState.Canceled},
    TaskState.Working: {TaskState.AwaitingInput, TaskState.AwaitingCompletion, TaskState.Canceled, TaskState.Failed},
    TaskState.AwaitingInput: {TaskState.Working, TaskState.Canceled},
    TaskState.AwaitingCompletion: {TaskState.Working, TaskState.Completed, TaskState.Canceled},
}

AUDIT_PREVIEW_CHARS = 80


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def post_to_sender(settings: Settings, phone: str, text: str) -> dict[str, Any]:
    """Hand one message to the local iMessage sender sidecar."""
    async with httpx.AsyncClient(timeout=settings.sender_timeout_seconds) as client:
        response = await client.post(
            f"{settings.sender_url}/v1/imessage/send",
            headers={"x-internal-token": settings.internal_token},
            json={"phone": phone, "text": text},
        )
    if response.status_code != 200:
        detail = ""
        try:
            payload = response.json()
            detail = str(payload.get("detail") or payload.get("error") or "")
        except Exception:
            detail = response.text[:200]
        raise RuntimeError(f"sender returned HTTP {response.status_code}{f'：{detail}' if detail else ''}")
    return response.json()


class MessageForwarderAgent:
    """One skill: take a message and deliver it to the requested phone number.

    State machine follows AIP v2.2: Start creates Accepted, the background run
    moves to Working, then either publishes a Product (AwaitingCompletion, which
    the Leader confirms with Complete) or asks for the missing piece
    (AwaitingInput, which the Leader answers with Continue).
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        # task_id -> phone remembered while waiting for the content
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
            pass  # audit failures must never block a delivery

    def _finish(self, task_id: str, name: str, summary: str, structured: dict[str, Any]) -> None:
        TaskManager.set_products(
            task_id,
            [
                Product(
                    id=f"product-{uuid.uuid4()}",
                    name=name,
                    dataItems=[TextDataItem(text=summary), StructuredDataItem(data=structured)],
                )
            ],
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

    # -------- skill --------
    async def _forward(self, task_id: str, phone: str, text: str, originator: str = "") -> None:
        preview = text[:AUDIT_PREVIEW_CHARS] + ("…" if len(text) > AUDIT_PREVIEW_CHARS else "")
        # The recipient sees who the message came from when the caller labelled it.
        delivered = f"来自{originator}的消息：{text}" if originator else text
        if not self.settings.is_allowed(phone):
            # A blocked number is usually a typo rather than an attack, so say
            # which allow-listed number it looks like.
            suggestion = self.settings.closest_allowed(phone)
            reason = NOT_ALLOWED.format(phone=phone)
            if suggestion:
                reason += f"\n你可能是想转发到 {suggestion}？"
            self._audit(
                {
                    "at": _now(),
                    "taskId": task_id,
                    "target": phone,
                    "result": "blocked",
                    "originator": originator,
                    "suggestion": suggestion or "",
                    "preview": preview,
                }
            )
            self._fail(task_id, reason)
            return
        try:
            outcome = await post_to_sender(self.settings, phone, delivered)
        except Exception as exc:
            self._audit(
                {
                    "at": _now(),
                    "taskId": task_id,
                    "target": phone,
                    "result": "failed",
                    "originator": originator,
                    "error": str(exc),
                    "preview": preview,
                }
            )
            self._fail(task_id, f"转发到 {phone} 失败：{exc}")
            return
        message_id = str(outcome.get("messageId") or "")
        self._audit(
            {
                "at": _now(),
                "taskId": task_id,
                "target": phone,
                "result": "sent",
                "originator": originator,
                "messageId": message_id,
                "characters": len(text),
                "preview": preview,
            }
        )
        attribution = f"（来自 {originator}）" if originator else ""
        # Keep the original key set for unlabelled calls; add originator only when known.
        structured = {
            "target": phone,
            "messageId": message_id,
            "characters": len(text),
            "result": "sent",
        }
        if originator:
            structured["originator"] = originator
        self._finish(
            task_id,
            "消息转发结果",
            f"已把 {len(text)} 个字符转发到 {phone}{attribution}。"
            + (f"（messageId: {message_id}）" if message_id else ""),
            structured,
        )

    async def _run(self, task_id: str, raw_text: str) -> None:
        try:
            self._transition(task_id, TaskState.Working)
            request = parse_forward_request(raw_text)
            if not request.actionable:
                self._await_input(task_id, request.problem, request.phone)
                return
            await self._forward(task_id, request.phone or "", request.text, request.originator)
        except Exception as exc:
            self._fail(task_id, f"转发任务执行失败：{exc}")

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
        known_phone = self.pending_targets.get(task.taskId)
        if not known_phone:
            asyncio.create_task(self._run(task.taskId, text))
        else:
            self.pending_targets.pop(task.taskId, None)
            asyncio.create_task(self._continue_with_content(task.taskId, known_phone, text))
        return self._set_identity(task)

    async def _continue_with_content(self, task_id: str, phone: str, text: str) -> None:
        try:
            self._transition(task_id, TaskState.Working)
            await self._forward(task_id, phone, text)
        except Exception as exc:
            self._fail(task_id, f"转发任务执行失败：{exc}")

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
