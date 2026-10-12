"""Serve the forwarding Agent over HTTPS with ACPs mTLS identity binding.

The ACPs SDK extracts the caller's AIC straight from the TLS socket
(`AipPeerCertH11Protocol`), so the process has to terminate TLS itself; the
plain `uvicorn --ssl-*` CLI flags cannot install that protocol class. This is the
same shape as the official demo-partner entrypoint.

Run (after the CA issued the certificate):

    PYTHONPATH=src .venv/bin/python -m forwarder.serve

Environment:
    FORWARDER_TLS_HOST   default 0.0.0.0
    FORWARDER_TLS_PORT   default 9530
    FORWARDER_TLS_CERT   default certs/forwarder/server.pem
    FORWARDER_TLS_KEY    default certs/forwarder/server.key
    FORWARDER_TLS_CA     default certs/forwarder/trust-bundle.pem
"""

from __future__ import annotations

import os
import ssl
from pathlib import Path

import uvicorn

from acps_sdk.aip.aip_peer_cert import AipPeerCertH11Protocol

from .app import app


def main() -> None:
    host = os.getenv("FORWARDER_TLS_HOST", "0.0.0.0")
    port = int(os.getenv("FORWARDER_TLS_PORT", "9530"))
    certificate = os.getenv("FORWARDER_TLS_CERT", "certs/forwarder/server.pem")
    private_key = os.getenv("FORWARDER_TLS_KEY", "certs/forwarder/server.key")
    client_ca = os.getenv("FORWARDER_TLS_CA", "certs/forwarder/trust-bundle.pem")

    missing = [path for path in (certificate, private_key, client_ca) if not Path(path).is_file()]
    if missing:
        raise SystemExit(
            "缺少 mTLS 证书文件：" + "、".join(missing) + "\n先执行： bash tools/register-forwarder.sh cert"
        )

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


if __name__ == "__main__":
    main()
