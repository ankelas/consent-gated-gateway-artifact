from __future__ import annotations

from fastapi import FastAPI

from acps_sdk.aip.aip_peer_cert import AipPeerCertificateMiddleware
from acps_sdk.aip.aip_rpc_server import add_aip_rpc_router

from .agent import PersonalAssistant
from .config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    assistant = PersonalAssistant(settings)
    app = FastAPI(title=f"Personal Assistant {settings.owner_phone}", version="0.1.0")
    app.state.assistant = assistant
    app.state.settings = settings

    # Needed so the AIP server can read the caller's AIC off the TLS connection.
    app.add_middleware(AipPeerCertificateMiddleware)

    add_aip_rpc_router(
        app,
        "/rpc",
        assistant.handlers,
        local_aic=settings.agent_aic or None,
        identity_binding_enabled=settings.identity_binding_enabled,
    )

    @app.get("/health")
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "owner": settings.owner_phone,
            "aic": settings.agent_aic,
            "sender": settings.sender_url,
            "identity_binding": settings.identity_binding_enabled,
            "directory_entries": sorted(settings.directory),
        }

    return app


# The app is built per process via ASSISTANT_* env (uvicorn --factory), so two
# assistants (one per owner) can run from the same code base.
