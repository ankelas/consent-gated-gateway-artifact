from __future__ import annotations

from fastapi import FastAPI

from acps_sdk.aip.aip_peer_cert import AipPeerCertificateMiddleware
from acps_sdk.aip.aip_rpc_server import add_aip_rpc_router

from .agent import MessageForwarderAgent
from .config import Settings

settings = Settings.from_env()
agent = MessageForwarderAgent(settings)

app = FastAPI(title="Wutong Message Forwarder", version="0.1.0")

# The ACPs SDK reads the caller's AIC off the peer certificate, which the custom
# uvicorn protocol in forwarder/serve.py records per TLS connection. Without
# this middleware the request never sees the certificate, so a server running
# with identity binding on would reject every caller.
app.add_middleware(AipPeerCertificateMiddleware)

add_aip_rpc_router(
    app,
    "/rpc",
    agent.handlers,
    local_aic=settings.agent_aic or None,
    identity_binding_enabled=settings.identity_binding_enabled,
)


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "sender": settings.sender_url,
        "allowlist": list(settings.allowed_numbers),
        "open_to_any_number": not settings.allowed_numbers,
        "identity_binding": settings.identity_binding_enabled,
    }
