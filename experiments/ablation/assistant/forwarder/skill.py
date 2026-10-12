"""The forwarding skill: parse "转发给 <号码>：<内容>" style requests."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

from .config import normalize_phone

PHONE_PATTERN = re.compile(r"\+?\d[\d\s()\-.]{4,20}\d")

# An explicit instruction: 转发给/转发到/转给/发给 <号码> <分隔符> <同一行剩余内容>
INSTRUCTION_PATTERN = re.compile(
    r"(?:转发给|转发到|转给|发给)\s*(\+?\d[\d\s()\-.]{4,20}\d)[\s:：,，、;；\-—]*([^\n]*)"
)

# Who the message comes from. Upstream callers label it (the iMessage adapter sends
# "发送方号码：+8613…"), and users sometimes write it themselves ("来自 +8613… 的消息").
ORIGINATOR_PATTERN = re.compile(
    r"(?:发送方|发送者|发起方|来源|来自|发件人|用户号码|用户手机号|用户)\s*"
    r"(?:号码|手机号|电话)?\s*[:：]?\s*(\+?\d[\d\s()\-.]{4,20}\d)"
)

FILLER_PREFIX = re.compile(r"^(?:发消息|发短信|发个消息|短信|消息|告诉|通知|提醒|转告)\s*[，,：:、]?\s*")
SEPARATORS = "：:，,、;；-— \t\n\r"

DEFAULT_MAX_CONTENT_CHARS = 1000

TARGET_PROMPT = (
    "请给出目标号码和内容，例如：\n"
    "转发给 +8616600027093：明天上午十点开会\n"
    "也可以用「转发给 16600027093：内容」这种写法。"
)
CONTENT_PROMPT = "已记下目标号码 {phone}，请把要转发的具体内容发给我。"
NOT_ALLOWED = "目标号码 {phone} 不在本智能体的转发白名单里，本次没有发送。"
TOO_LONG = (
    "解析到要转发的内容有 {length} 个字符，超过单条上限 {limit} 字符，本次没有发送。\n"
    "请把内容精简后重发；确需转发长文本时，可由部署方调高 FORWARDER_MAX_CONTENT_CHARS。"
)


def max_content_chars() -> int:
    try:
        return max(1, int(os.getenv("FORWARDER_MAX_CONTENT_CHARS", str(DEFAULT_MAX_CONTENT_CHARS))))
    except ValueError:
        return DEFAULT_MAX_CONTENT_CHARS


@dataclass(frozen=True)
class ForwardRequest:
    """A parsed request. `problem` is non-empty when the request cannot run yet."""

    phone: str | None
    text: str
    problem: str = ""
    originator: str = ""

    @property
    def actionable(self) -> bool:
        return not self.problem and bool(self.phone) and bool(self.text)

    def delivered_text(self) -> str:
        """What the recipient actually receives."""
        if self.originator:
            return f"来自{self.originator}的消息：{self.text}"
        return self.text


def _too_long(phone: str, content: str, originator: str) -> ForwardRequest:
    limit = max_content_chars()
    return ForwardRequest(phone, "", TOO_LONG.format(length=len(content), limit=limit), originator)


def _strip_filler(content: str) -> str:
    cleaned = content
    for _ in range(2):
        stripped = FILLER_PREFIX.sub("", cleaned).strip(SEPARATORS).strip()
        if stripped == cleaned:
            break
        cleaned = stripped
    return cleaned


def parse_forward_request(raw: str) -> ForwardRequest:
    """Split a request into target number, content and (optionally) originator.

    Upstream callers (a Leader, or a planning layer such as 叮当) often wrap the
    real instruction in orchestration prose that itself contains example numbers
    and example instructions. So an explicit "转发给 <号码>：<内容>" form wins over
    a bare number, and the **last** such instruction wins, because that is where
    the user's own answer sits. Content is taken from that line only.
    """
    text = (raw or "").strip()
    if not text:
        return ForwardRequest(None, "", TARGET_PROMPT)

    originator = ""
    for line in text.splitlines():
        found = ORIGINATOR_PATTERN.search(line)
        if found:
            originator = normalize_phone(found.group(1)) or originator

    # Drop pure metadata lines so the originator number is never mistaken for
    # the forwarding target.
    cleaned_lines = [
        line
        for line in text.splitlines()
        if not (ORIGINATOR_PATTERN.search(line) and not INSTRUCTION_PATTERN.search(line))
    ]
    cleaned = "\n".join(cleaned_lines).strip() or text

    match = None
    for candidate in INSTRUCTION_PATTERN.finditer(cleaned):
        match = candidate
    if match is not None:
        phone = normalize_phone(match.group(1))
        if not phone:
            return ForwardRequest(None, "", f"「{match.group(1).strip()}」不像一个可用的手机号。\n\n{TARGET_PROMPT}", originator)
        content = _strip_filler(match.group(2).strip(SEPARATORS).strip())
        if not content:
            return ForwardRequest(phone, "", CONTENT_PROMPT.format(phone=phone), originator)
        if len(content) > max_content_chars():
            return _too_long(phone, content, originator)
        return ForwardRequest(phone, content, "", originator)

    # Fallback for callers that only send "号码 + 文本" with no explicit verb.
    fallback = PHONE_PATTERN.search(cleaned)
    if not fallback:
        return ForwardRequest(None, "", TARGET_PROMPT, originator)
    phone = normalize_phone(fallback.group(0))
    if not phone:
        return ForwardRequest(None, "", f"「{fallback.group(0).strip()}」不像一个可用的手机号。\n\n{TARGET_PROMPT}", originator)
    content = _strip_filler(cleaned[fallback.end():].strip(SEPARATORS).strip())
    if not content:
        return ForwardRequest(phone, "", CONTENT_PROMPT.format(phone=phone), originator)
    if len(content) > max_content_chars():
        return _too_long(phone, content, originator)
    return ForwardRequest(phone, content, "", originator)
