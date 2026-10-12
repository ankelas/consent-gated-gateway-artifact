from __future__ import annotations

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from acps_sdk.aip.aip_rpc_server import add_aip_rpc_router

from .agent import WutongIMessageAgent
from .config import Settings

settings = Settings.from_env()
agent = WutongIMessageAgent(settings)
app = FastAPI(title="Wutong iMessage Adapter", version="0.3.0")

add_aip_rpc_router(
    app, "/rpc", agent.handlers, local_aic=settings.adapter_aic or None,
    identity_binding_enabled=settings.aip_server_identity_binding_enabled,
)


class PhotonInbound(BaseModel):
    message_id: str = Field(min_length=1)
    chat_guid: str = Field(min_length=1)
    text: str = Field(min_length=1)
    photon_sender_id: str = Field(min_length=1, max_length=255)
    photon_sender_name: str = Field(default="", max_length=255)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "llm": "enabled" if agent.llm.enabled else "disabled"}


@app.post("/v1/photon/inbound")
async def photon_inbound(payload: PhotonInbound, x_internal_token: str = Header(default="")):
    # The bridge verifies the Photon HMAC. This endpoint verifies the separate
    # loopback credential, then derives identity from Photon sender_id only.
    if not settings.caller_for_token(x_internal_token):
        raise HTTPException(status_code=401, detail="invalid internal token")
    try:
        caller_id = settings.caller_for_photon_sender(payload.photon_sender_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid Photon sender identifier")
    agent.store.upsert_photon_caller(caller_id, payload.photon_sender_id, payload.photon_sender_name)
    return await agent.photon_message(caller_id, payload.message_id, payload.chat_guid, payload.text)
