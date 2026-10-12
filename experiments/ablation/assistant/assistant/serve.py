"""Serve one personal assistant (HTTPS + mTLS, or plain HTTP for local runs).

    # production (certificate issued for this assistant's AIC)
    ASSISTANT_OWNER_PHONE=+8616600027093 ASSISTANT_TLS_PORT=9532 \
      PYTHONPATH=src .venv/bin/python -m assistant.serve

    # local wiring test (no TLS, identity binding off)
    ASSISTANT_OWNER_PHONE=+8616600027093 ASSISTANT_TLS_PORT=9532 ASSISTANT_ALLOW_PLAIN_HTTP=true \
      PYTHONPATH=src .venv/bin/python -m assistant.serve
"""

from __future__ import annotations

import os
import ssl
from pathlib import Path

import uvicorn

from acps_sdk.aip.aip_peer_cert import AipPeerCertH11Protocol

from .app import create_app


def main() -> None:
    host = os.getenv("ASSISTANT_TLS_HOST", "0.0.0.0")
    port = int(os.getenv("ASSISTANT_TLS_PORT", "9531"))
    certificate = os.getenv("ASSISTANT_TLS_CERT", "")
    private_key = os.getenv("ASSISTANT_TLS_KEY", "")
    client_ca = os.getenv("ASSISTANT_TLS_CA", "")
    app = create_app()

    if certificate and private_key and client_ca:
        missing = [path for path in (certificate, private_key, client_ca) if not Path(path).is_file()]
        if missing:
            raise SystemExit("缺少 mTLS 证书文件：" + "、".join(missing))
        uvicorn.run(
            app,
            host=host,
            port=port,
            http=AipPeerCertH11Protocol,
            ssl_certfile=certificate,
            ssl_keyfile=private_key,
            ssl_ca_certs=client_ca,
            ssl_cert_reqs=ssl.CERT_REQUIRED,
        )
        return

    if os.getenv("ASSISTANT_ALLOW_PLAIN_HTTP", "").strip().lower() not in {"1", "true", "yes", "on"}:
        raise SystemExit(
            "没有配置 ASSISTANT_TLS_CERT/KEY/CA。生产环境必须用 mTLS；"
            "本地联调请显式设置 ASSISTANT_ALLOW_PLAIN_HTTP=true。"
        )
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
