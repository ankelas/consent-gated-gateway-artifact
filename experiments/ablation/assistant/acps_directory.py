"""Structured lookup of a personal assistant by its owner's phone number.

Semantic discovery is a poor fit for "who serves +8616…?": an LLM answer can
mention a number inside prose and look like a match. The platform's discovery API
supports filtered queries over ACS fields, and each personal assistant tags its
skills with its owner's number, so this module resolves the assistant exactly.
"""

from __future__ import annotations

import httpx

DEFAULT_DISCOVERY_API_URL = "https://wt.ioa.pub/discovery"


def _digits(value: str) -> str:
    return "".join(char for char in (value or "") if char.isdigit())


async def find_assistant_for_number(
    number: str,
    *,
    base_url: str = DEFAULT_DISCOVERY_API_URL,
    timeout: float = 15.0,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, str] | None:
    """Return {endpoint, aic} of the assistant that serves `number`, or None."""
    digits = _digits(number)
    if not digits:
        return None
    payload = {
        "type": "filtered",
        "query": "",
        "limit": 10,
        "filter": {"conditions": [{"field": "skills.tags", "op": "anyOf", "value": [f"+{digits}"]}]},
    }
    async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
        response = await client.post(f"{base_url.rstrip('/')}/acps-adp-v2/discover", json=payload)
        response.raise_for_status()
        data = response.json()

    acs_map = ((data.get("result") or {}).get("acsMap")) or {}
    for aic, acs in acs_map.items():
        if not isinstance(acs, dict):
            continue
        owner_digits = _digits(str(((acs.get("entityMeta") or {}).get("ownerPhone") or "")))
        name_digits = _digits(str(acs.get("name") or ""))
        if digits not in {owner_digits} and digits not in name_digits:
            continue
        for endpoint in acs.get("endPoints") or []:
            url = str((endpoint or {}).get("url") or "")
            if url.startswith("https://") and url.endswith("/rpc"):
                return {"endpoint": url, "aic": str(aic)}
    return None
